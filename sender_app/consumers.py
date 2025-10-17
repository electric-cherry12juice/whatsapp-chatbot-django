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

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()
        meta_api_logger.info(f"WebSocket connected for {self.phone_number}")


    def disconnect(self, close_code):
        # Leave room group
        meta_api_logger.info(f"WebSocket disconnected for {self.phone_number}")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket (when you send a message from the UI)
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        meta_api_logger.info(f"Received message from WebSocket for {self.phone_number}: {message}")


        # Save the outgoing message to the database
        ChatMessage.objects.create(
            sender_id=self.phone_number,
            message_text=message,
            is_from_user=False # It's a message sent FROM you
        )

        # Send the message to the actual WhatsApp contact
        self.send_message_to_whatsapp(self.phone_number, message)

        # **THIS IS THE CRITICAL FIX FOR SENT MESSAGES**
        # Broadcast the message back to the sender's own UI so it appears instantly.
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'is_from_user': False, # Mark as an outgoing message
                'sender_id': self.phone_number
            }
        )

    # Receive message from room group (broadcast from the webhook or from self)
    def chat_message(self, event):
        message = event['message']
        is_from_user = event['is_from_user']
        sender_id = event['sender_id']

        # Send message to the WebSocket (to the browser)
        self.send(text_data=json.dumps({
            'message': message,
            'is_from_user': is_from_user,
            'sender_id': sender_id
        }))

    # Helper function to send message to the WhatsApp API
    def send_message_to_whatsapp(self, phone_number, message):
        access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
        phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
        version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone_number, "text": {"body": message}}
        
        meta_api_logger.info(f"--- META API SEND --- URL: {url} | Payload: {json.dumps(payload)}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            meta_api_logger.info(f"--- META API RESPONSE --- Status: {response.status_code} | Body: {response.text}")
        except requests.exceptions.RequestException as e:
            meta_api_logger.error(f"--- CRITICAL ERROR --- The API call failed: {e}")

