import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import sender_app.routing

# Set the DJANGO_SETTINGS_MODULE environment variable.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'whatsapp_sender.settings')

# This is the crucial line that fixes the error.
# It initializes the Django settings and app registry before any other imports.
django.setup()

# The rest of your ASGI configuration remains the same.
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            sender_app.routing.websocket_urlpatterns
        )
    ),
})
