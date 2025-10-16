from django.urls import path
from . import views

urlpatterns = [
    # The root URL will now be the contact list
    path('', views.contact_list_view, name='contact_list'),
    # The URL for a specific chat room
    path('chat/<str:phone_number>/', views.chat_room_view, name='chat_room'),
    path('webhook', views.webhook_view, name='webhook'),
    path('health/', views.health_check_view, name='health_check'),
]



