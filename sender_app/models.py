from django.db import models

# Defines the database table for storing messages.
class ChatMessage(models.Model):
    # The WhatsApp ID of the user.
    sender_id = models.CharField(max_length=255)
    # The content of the message.
    message_text = models.TextField()
    # The timestamp when the message was saved.
    timestamp = models.DateTimeField(auto_now_add=True)
    # A boolean to distinguish between incoming (user) and outgoing messages.
    is_from_user = models.BooleanField(default=True)

    def __str__(self):
        # A simple string representation for the Django admin interface.
        direction = "From" if self.is_from_user else "To"
        return f"{direction} {self.sender_id}: {self.message_text[:30]}"
