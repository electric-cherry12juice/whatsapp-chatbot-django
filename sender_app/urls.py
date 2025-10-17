from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # --- Authentication URLs ---
    path('login/', views.login_view, name='login_view'),
    path('verify/', views.verify_view, name='verify_view'),
    path('logout/', views.logout_view, name='logout_view'),

    # --- Main Application URL ---
    path('', views.chat_interface_view, name='chat_interface'),

    # --- API Endpoints (for JavaScript) ---
    path('api/chat/<str:phone_number>/', views.get_chat_history_json, name='get_chat_history'),
    path('api/start_chat/', views.start_new_chat_view, name='start_new_chat'),
    path('api/search_chats/', views.search_chats_json, name='search_chats'),
    
    # --- ADD THIS NEW LINE FOR DELETING CHATS ---
    path('api/delete_chat/<str:phone_number>/', views.delete_chat_view, name='delete_chat'),

    # --- Webhook for Meta ---
    path('webhook', views.webhook_view, name='webhook'),
    path('media/<path:path>', views.serve_media, name='serve_media'),
    # --- Health Check for Render ---
    path('health/', views.health_check_view, name='health_check'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

