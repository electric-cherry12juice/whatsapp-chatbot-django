from django.urls import path
from . import views

urlpatterns = [
    # Auth routes
    path('login/', views.login_view, name='login_view'),
    path('verify/', views.verify_view, name='verify_view'),
    path('logout/', views.logout_view, name='logout_view'),
    
    # App routes
    path('', views.contact_list_view, name='contact_list'),
    path('chat/<str:phone_number>/', views.chat_room_view, name='chat_room'),
    
    # Webhook
    path('webhook', views.webhook_view, name='webhook'),
]
