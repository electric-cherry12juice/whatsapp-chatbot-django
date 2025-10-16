from django.urls import path
from . import views

urlpatterns = [
    # Auth URLs
    path('login/', views.login_view, name='login_view'),
    path('verify/', views.verify_view, name='verify_view'),
    path('logout/', views.logout_view, name='logout_view'),

    # Main application URL
    path('', views.chat_interface_view, name='chat_interface'),

    # API URL for fetching chat history
    path('api/chat/<str:phone_number>/', views.get_chat_history_json, name='get_chat_history'),

    # Webhook URL
    path('webhook', views.webhook_view, name='webhook'),

    path('health/', views.health_check_view, name='health_check'),
]

