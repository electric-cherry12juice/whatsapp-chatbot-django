import json
import os
import requests
import logging
import threading
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from .models import ChatMessage

meta_api_logger = logging.getLogger('meta_api_logger')

class ChatConsumer(WebsocketConsumer):
    def connect(self):
        self.phone_number = self.scope['url_route']['kwargs']['phone_number']
        self.room_group_name = f'chat_{self.phone_number}'
        async_to_sync(self.channel_layer.group_add)(self.room_group_name, self.channel_name)
        self.accept()
        meta_api_logger.info(f"WebSocket connected for {self.phone_number}")

    def disconnect(self, close_code):
        meta_api_logger.info(f"WebSocket disconnected for {self.phone_number}")
        async_to_sync(self.channel_layer.group_discard)(self.room_group_name, self.channel_name)

    def receive(self, text_data):
        """
        Receive payload from client websocket. We:
         - parse safely
         - persist the message to DB immediately
         - broadcast to group so UI updates quickly
         - offload the external WhatsApp API call to a background thread
        """
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get('message', '')
        except Exception as e:
            meta_api_logger.error(f"WebSocket parse error for {self.phone_number}: {e} - raw: {text_data}")
            return

        if message is None:
            return

        # server-side length guard (avoid huge payloads)
        MAX_LEN = 8000  # adjust if needed
        if isinstance(message, str) and len(message) > MAX_LEN:
            meta_api_logger.warning(f"Message too long from {self.phone_number}: {len(message)} chars")
            # Save truncated system note and notify client
            ChatMessage.objects.create(sender_id=self.phone_number,
                                       message_text='[Message truncated: too long]',
                                       is_from_user=False,
                                       message_type='system')
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {'type': 'chat_message', 'message': '[Message truncated: too long]', 'is_from_user': False, 'sender_id': self.phone_number}
            )
            return

        # Determine if it's a media link or text
        is_media_url = False
        if isinstance(message, str):
            is_media_url = any(message.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp3', '.ogg', '.amr', '.wav', '.m4a'])

        # Persist immediately
        if is_media_url:
            message_type = 'image' if any(message.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) else 'audio'
            ChatMessage.objects.create(sender_id=self.phone_number, media_url=message, is_from_user=False, message_type=message_type)
        else:
            ChatMessage.objects.create(sender_id=self.phone_number, message_text=message, is_from_user=False, message_type='text')

        # Broadcast to all connected clients in the group (fast UI update)
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {'type': 'chat_message', 'message': message, 'is_from_user': False, 'sender_id': self.phone_number}
        )

        # Offload external API calls to a thread to avoid blocking the consumer
        threading.Thread(target=self._send_outbound, args=(self.phone_number, message, is_media_url), daemon=True).start()

    def chat_message(self, event):
        # send to client
        self.send(text_data=json.dumps({
            'message': event['message'],
            'is_from_user': event['is_from_user'],
            'sender_id': event['sender_id']
        }))

    # background worker
    def _send_outbound(self, phone_number, message, is_media_url):
        """
        Called in a background thread. Sends message to WhatsApp Cloud API.
        """
        try:
            if is_media_url:
                message_type = 'image' if any(message.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) else 'audio'
                self.send_media_to_whatsapp(phone_number, message, message_type)
            else:
                self.send_text_to_whatsapp(phone_number, message)
        except Exception as e:
            meta_api_logger.error(f"Error sending outbound message for {phone_number}: {e}")

    # Keep _send_request and the two helpers, but add error handling
    def _send_request(self, payload):
        access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
        phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
        version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        meta_api_logger.info(f"--- META API SEND --- URL: {url} | Payload-size: {len(json.dumps(payload))}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            meta_api_logger.info(f"--- META API RESPONSE --- Status: {response.status_code} | Body: {response.text}")
        except requests.exceptions.RequestException as e:
            meta_api_logger.error(f"--- CRITICAL ERROR --- The API call failed: {e}")

    def send_text_to_whatsapp(self, phone_number, message):
        payload = {"messaging_product": "whatsapp", "to": phone_number, "text": {"body": message}}
        self._send_request(payload)

    def send_media_to_whatsapp(self, phone_number, media_url, media_type):
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": media_type,
            media_type: {"link": media_url}
        }
        self._send_request(payload)

    