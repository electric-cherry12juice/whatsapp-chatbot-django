import json
import os
import requests
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatMessage

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract the phone number from the URL
        self.room_name = self.scope['url_route']['kwargs']['phone_number']
        self.room_group_name = f'chat_{self.room_name}'

        # Add detailed logging for debugging connection
        print(f"--- WebSocket Connection ---")
        print(f"Attempting to connect to room: {self.room_name}")
        print(f"Assigning to group: {self.room_group_name}")

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WebSocket connection ACCEPTED for group: {self.room_group_name}")
        print(f"--------------------------")


    async def disconnect(self, close_code):
        # Log disconnection
        print(f"--- WebSocket Disconnected ---")
        print(f"Disconnected from group: {self.room_group_name} with code: {close_code}")
        print(f"----------------------------")
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_content = text_data_json['message']
        message_type = text_data_json.get('type', 'text') # Default to text
        
        phone_number = self.room_name

        # --- THIS IS THE CRITICAL NEW SECTION FOR SENDING ---
        # 1. Save our own message to the database first
        await self.save_message_to_db(phone_number, message_content, is_from_user=False)

        # 2. Send the message to the Meta API with robust logging
        self.send_whatsapp_message(phone_number, message_content, message_type)
        
        # 3. Broadcast the message to the room so it appears in our UI instantly
        # (This part is the "optimistic update")
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_content,
                'is_from_user': False
            }
        )

    # This is a synchronous helper function to make the API call.
    # We run it in a separate thread to avoid blocking the async event loop.
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
        else: # Default to text
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "text": {"body": message_content},
            }

        print("--- META API SEND ---")
        print(f"URL: {url}")
        print(f"Payload: {json.dumps(payload)}")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            
            print("--- META API RESPONSE ---")
            print(f"Status Code: {response.status_code}")
            try:
                # Try to print JSON body, but fall back to text if it's not JSON
                print(f"Response Body: {response.json()}")
            except json.JSONDecodeError:
                print(f"Response Body (not JSON): {response.text}")
            print("-----------------------")

        except requests.exceptions.RequestException as e:
            print("--- CRITICAL ERROR ---")
            print(f"The API call failed before getting a response: {e}")
            print("----------------------")


    # Receive message from room group
    async def chat_message(self, event):
        message = event['message']
        is_from_user = event['is_from_user']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'is_from_user': is_from_user
        }))

    @database_sync_to_async
    def save_message_to_db(self, sender_id, message_text, is_from_user):
        ChatMessage.objects.create(
            sender_id=sender_id,
            message_text=message_text,
            is_from_user=is_from_user
        )

