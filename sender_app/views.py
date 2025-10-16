import json
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import ChatMessage
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# New view to list all conversations
def contact_list_view(request):
    # Get all unique phone numbers (sender_id) from messages
    contacts = ChatMessage.objects.values_list('sender_id', flat=True).distinct()
    return render(request, 'sender_app/contact_list.html', {'contacts': contacts})

# New view for a specific chat room
def chat_room_view(request, phone_number):
    messages = ChatMessage.objects.filter(sender_id=phone_number).order_by('timestamp')
    context = {
        'messages': messages,
        'phone_number': phone_number,
    }
    return render(request, 'sender_app/chat_room.html', context)

# --- UPDATED WEBHOOK ---
@csrf_exempt
def webhook_view(request):
    if request.method == "GET":
        # ... (verification logic is the same) ...
        verify_token = request.GET.get("hub.verify_token")
        if verify_token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            return HttpResponse(request.GET.get("hub.challenge"), status=200)
        return HttpResponse("Invalid verification token", status=403)

    if request.method == "POST":
        data = json.loads(request.body)
        try:
            message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
            sender_id = message_data["from"]
            message_text = message_data["text"]["body"]
            
            # Save the incoming message
            ChatMessage.objects.create(sender_id=sender_id, message_text=message_text, is_from_user=True)

            # --- BROADCAST THE MESSAGE VIA CHANNELS ---
            channel_layer = get_channel_layer()
            room_group_name = f'chat_{sender_id}'
            
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chat_message', # This calls the chat_message method in the consumer
                    'message': message_text,
                    'is_from_user': True
                }
            )
        except (KeyError, IndexError):
            pass
        return HttpResponse(status=200)
    return HttpResponse(status=405)

def health_check_view(request):
    return JsonResponse({"status": "ok"})

