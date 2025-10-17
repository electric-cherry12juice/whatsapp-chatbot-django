from django.db import models

class ChatMessage(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('system', 'System'), # For messages like "Started chat with template..."
    ]

    sender_id = models.CharField(max_length=20)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default='text')
    message_text = models.TextField(blank=True, null=True)
    media_url = models.CharField(max_length=255, blank=True, null=True) # Will store local path like /media/image.jpg
    timestamp = models.DateTimeField(auto_now_add=True)
    is_from_user = models.BooleanField()

    def __str__(self):
        direction = "IN" if self.is_from_user else "OUT"
        content = self.message_text or self.media_url
        return f"{direction} {self.sender_id}: {content[:30]}"
