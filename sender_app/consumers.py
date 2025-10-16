import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatMessage
import requests
from django.conf import settings

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.phone_number = self.scope['url_route']['kwargs']['phone_number']
        self.room_group_name = f'chat_{self.phone_number}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket (from the user's browser)
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_text = data['message']
        to_number = self.phone_number

        # Send message to WhatsApp API
        # This part is synchronous, so we run it in a thread to not block async code
        await database_sync_to_async(self.send_whatsapp_message)(to_number, message_text)
        
        # Save our own message to the database
        await self.save_message(to_number, message_text, is_from_user=False)

        # Broadcast the message to the room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_text,
                'is_from_user': False
            }
        )
    
    # Receive message from room group (broadcast handler)
    async def chat_message(self, event):
        message = event['message']
        is_from_user = event['is_from_user']

        # Send message to WebSocket (to the browser)
        await self.send(text_data=json.dumps({
            'message': message,
            'is_from_user': is_from_user
        }))
        
    # Helper methods
    @database_sync_to_async
    def save_message(self, phone, text, is_from_user):
        ChatMessage.objects.create(sender_id=phone, message_text=text, is_from_user=is_from_user)

    def send_whatsapp_message(self, to_number, message_text):
        url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message_text}
        }
        try:
            response = requests.post(url, headers=headers, json=payload)
            print(f"Meta API Response: {response.json()}")
        except Exception as e:
            print(f"Error sending to Meta API: {e}")
