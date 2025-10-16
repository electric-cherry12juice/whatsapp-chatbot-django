from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import requests
import json
from .models import ChatMessage

def send_message_view(request):
    # Initialize a context dictionary to pass data to the template
    context = {}

    if request.method == 'POST':
        # --- STEP 1: VERIFY SECRETS ARE LOADED ---
        print("--- DEBUG INFO ---")
        print(f"DEBUG: Phone Number ID: {settings.WHATSAPP_PHONE_NUMBER_ID}")
        print(f"DEBUG: Access Token is present: {bool(settings.WHATSAPP_ACCESS_TOKEN)}")
        print("--------------------")

        to_number = request.POST.get('to_number')
        message_type = request.POST.get('message_type')
        
        url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        
        payload = { "messaging_product": "whatsapp", "to": to_number }

        if message_type == "text":
            message_text = request.POST.get('message_text')
            payload["type"] = "text"
            payload["text"] = {"body": message_text}
        elif message_type == "template":
            template_name = request.POST.get('template_name')
            payload["type"] = "template"
            payload["template"] = {"name": template_name, "language": {"code": "en_US"}}

        # --- STEP 2: CATCH ANY CRASHES DURING THE API CALL ---
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            response_data = response.json()
            # Store the response in the context dictionary
            context['response_status'] = response.status_code
            context['response_body'] = json.dumps(response_data, indent=4) # Format for readability
            
            print(f"Meta API Response Status: {response.status_code}")
            print(f"Meta API Response Body: {response_data}")
            
            if response.status_code == 200:
                message_content = request.POST.get('message_text') or f"Template: {request.POST.get('template_name')}"
                ChatMessage.objects.create(
                    sender_id=to_number,
                    message_text=message_content,
                    is_from_user=False
                )
        except Exception as e:
            # If the call crashes, store the error in the context
            error_message = f"The API call failed before getting a response: {e}"
            context['error_message'] = error_message
            print(f"--- CRITICAL ERROR ---")
            print(error_message)
            print(f"----------------------")
        
        # Instead of redirecting, re-render the page with the context
        return render(request, 'sender_app/index.html', context)

    # For a GET request, just render the page with an empty context
    return render(request, 'sender_app/index.html', context)

# ... (the rest of the file remains the same) ...
@csrf_exempt
def webhook_view(request):
    # ... (no changes here) ...
    if request.method == "GET":
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
            ChatMessage.objects.create(
                sender_id=sender_id,
                message_text=message_text,
                is_from_user=True
            )
        except (KeyError, IndexError):
            pass
        return HttpResponse(status=200)

    return HttpResponse(status=405)

def health_check_view(request):
    return JsonResponse({"status": "ok"})

