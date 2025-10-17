import json
import os
import requests
import logging
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

    # UPGRADED: Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        meta_api_logger.info(f"Received from WebSocket for {self.phone_number}: {message}")

        # Check if the message is a URL for media
        is_media_url = any(message.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp3', '.ogg', '.amr'])
        
        if is_media_url:
            message_type = 'image' if any(message.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) else 'audio'
            # Save media message to DB
            ChatMessage.objects.create(sender_id=self.phone_number, media_url=message, is_from_user=False, message_type=message_type)
            # Send media message to WhatsApp API
            self.send_media_to_whatsapp(self.phone_number, message, message_type)
        else:
            # Save text message to DB
            ChatMessage.objects.create(sender_id=self.phone_number, message_text=message, is_from_user=False, message_type='text')
            # Send text message to WhatsApp API
            self.send_text_to_whatsapp(self.phone_number, message)

        # Broadcast the message back to the sender's own UI
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message, # This will be the text or the URL
                'is_from_user': False,
                'sender_id': self.phone_number
            }
        )

    # Receive message from room group
    def chat_message(self, event):
        # This function is unchanged from your version
        self.send(text_data=json.dumps({
            'message': event['message'],
            'is_from_user': event['is_from_user'],
            'sender_id': event['sender_id']
        }))
    
    # --- NEW: Refactored sending logic ---
    def _send_request(self, payload):
        access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
        phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
        version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        
        meta_api_logger.info(f"--- META API SEND --- URL: {url} | Payload: {json.dumps(payload)}")
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