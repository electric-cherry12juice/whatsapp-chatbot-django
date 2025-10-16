from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import requests
import json
from .models import ChatMessage

# View for the main page to send messages.
def send_message_view(request):
    if request.method == 'POST':
        to_number = request.POST.get('to_number')
        message_type = request.POST.get('message_type')
        
        url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
        }

        # Build the correct payload based on message type
        if message_type == "text":
            message_text = request.POST.get('message_text')
            payload["type"] = "text"
            payload["text"] = {"body": message_text}
        elif message_type == "template":
            template_name = request.POST.get('template_name')
            payload["type"] = "template"
            payload["template"] = {"name": template_name, "language": {"code": "en_US"}}

        response = requests.post(url, headers=headers, json=payload)
        
        # Save the outgoing message to our database if sent successfully
        if response.status_code == 200:
            message_content = request.POST.get('message_text') or f"Template: {request.POST.get('template_name')}"
            ChatMessage.objects.create(
                sender_id=to_number,
                message_text=message_content,
                is_from_user=False
            )
        
        return redirect('send_message')

    # For a GET request, just display the page
    return render(request, 'sender_app/index.html')

# View for the WhatsApp webhook
@csrf_exempt
def webhook_view(request):
    # Handles the initial verification challenge from Meta
    if request.method == "GET":
        verify_token = request.GET.get("hub.verify_token")
        if verify_token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            return HttpResponse(request.GET.get("hub.challenge"), status=200)
        return HttpResponse("Invalid verification token", status=403)

    # Handles incoming messages
    if request.method == "POST":
        data = json.loads(request.body)
        try:
            # Parse the incoming message data
            message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
            sender_id = message_data["from"]
            message_text = message_data["text"]["body"]
            
            # Save the incoming message to our database
            ChatMessage.objects.create(
                sender_id=sender_id,
                message_text=message_text,
                is_from_user=True
            )
        except (KeyError, IndexError):
            # Handles other webhook events (like status updates) gracefully
            pass
        return HttpResponse(status=200)

    return HttpResponse(status=405) # Method not allowed

# View for the Render health check
def health_check_view(request):
    """A simple view that returns a 200 OK response for Render."""
    return JsonResponse({"status": "ok"})
