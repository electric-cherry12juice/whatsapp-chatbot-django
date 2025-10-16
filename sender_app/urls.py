from django.urls import path
from . import views

# This defines the URL patterns for the 'sender_app'.
# When a user navigates to the root of our site ('/'),
# Django will look here to find which view to execute.

urlpatterns = [
    # The empty string "" represents the root URL.
    # When a request comes to this URL, it will be handled by the
    # 'send_message_view' function from our views.py file.
    # The 'name' argument gives this URL a unique identifier,
    # which is useful for referring to it elsewhere in the Django project.
    path("", views.send_message_view, name="send_message"),
]

