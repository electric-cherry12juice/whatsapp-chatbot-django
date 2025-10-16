from django.urls import path
from . import views

urlpatterns = [
    # The root URL '/' will show the message sending form
    path('', views.send_message_view, name='send_message'),
    
    # The '/webhook' URL is for Meta to send incoming messages
    path('webhook', views.webhook_view, name='webhook'),
    
    # The '/health/' URL is for Render's health check
    path('health/', views.health_check_view, name='health_check'),
]
