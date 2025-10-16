from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # This regex matches a phone number for the chat room
    re_path(r'ws/chat/(?P<phone_number>\d+)/$', consumers.ChatConsumer.as_asgi()),
]
