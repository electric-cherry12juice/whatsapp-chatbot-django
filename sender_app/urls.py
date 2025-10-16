from django.urls import path
from . import views

urlpatterns = [
    # --- Authentication URLs ---
    # The login page where the user enters their username
    path('login/', views.login_view, name='login_view'),

    # The page where the user enters the OTP code
    path('verify/', views.verify_view, name='verify_view'),

    # The endpoint to handle logging out
    path('logout/', views.logout_view, name='logout_view'),


    # --- Main Application URL ---
    # The root of the site, which loads the main chat interface
    path('', views.chat_interface_view, name='chat_interface'),


    # --- API Endpoints (for JavaScript) ---
    # Fetches the chat history for a specific contact
    path('api/chat/<str:phone_number>/', views.get_chat_history_json, name='get_chat_history'),

    # Starts a new conversation with a contact via a template message
    path('api/start_chat/', views.start_new_chat_view, name='start_new_chat'),


    # --- Webhook for Meta ---
    # The endpoint that receives incoming message notifications from WhatsApp
    path('webhook', views.webhook_view, name='webhook'),


    path('health/', views.health_check_view, name='health_check'),
]

