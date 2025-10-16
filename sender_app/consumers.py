import json
import os
import requests
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatMessage

# Get our custom logger
meta_api_logger = logging.getLogger('meta_api_logger')

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['phone_number']
        self.room_group_name = f'chat_{self.room_name}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_content = text_data_json['message']
        message_type = text_data_json.get('type', 'text')
        
        phone_number = self.room_name

        await self.save_message_to_db(phone_number, message_content, is_from_user=False)
        self.send_whatsapp_message(phone_number, message_content, message_type)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_content,
                'is_from_user': False
            }
        )

    @staticmethod
    def send_whatsapp_message(to_number, message_content, message_type):
        access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
        phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
        version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
        
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        if message_type == 'template':
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "template",
                "template": {"name": message_content, "language": {"code": "en_US"}},
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "text": {"body": message_content},
            }

        meta_api_logger.info(f"Sending to {to_number}. Payload: {json.dumps(payload)}")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            meta_api_logger.info(f"Response from Meta for {to_number}: Status {response.status_code}, Body: {response.text}")
        except requests.exceptions.RequestException as e:
            meta_api_logger.error(f"Request failed for {to_number}: {e}")

    async def chat_message(self, event):
        message = event['message']
        is_from_user = event['is_from_user']
        await self.send(text_data=json.dumps({'message': message, 'is_from_user': is_from_user}))

    @database_sync_to_async
    def save_message_to_db(self, sender_id, message_text, is_from_user):
        ChatMessage.objects.create(sender_id=sender_id, message_text=message_text, is_from_user=is_from_user)

