from django.urls import path
from . import views

urlpatterns = [
    # ... existing auth and chat paths ...
    path('', views.chat_interface_view, name='chat_interface'),
    path('api/chat/<str:phone_number>/', views.get_chat_history_json, name='get_chat_history'),
    
    # --- ADD THIS NEW LINE ---
    path('api/start_chat/', views.start_new_chat_view, name='start_new_chat'),

    path('webhook', views.webhook_view, name='webhook'),

    path('health/', views.health_check_view, name='health_check'),
]

