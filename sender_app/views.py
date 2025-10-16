import requests
import json
from django.shortcuts import render
from django.conf import settings
from django.http import HttpRequest, HttpResponse

def send_message_view(request: HttpRequest) -> HttpResponse:
    """
    Handles the view for sending a WhatsApp message.
    Supports both text and template messages.
    """
    context = {}
    if request.method == "POST":
        recipient_number = request.POST.get("recipient_number")
        message_type = request.POST.get("message_type") # 'text' or 'template'

        if not recipient_number or not message_type:
            context['error'] = {"error": {"message": "Recipient number and message type are required."}}
            return render(request, "sender_app/index.html", context)

        # Construct the API URL
        url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

        # Prepare headers
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        # --- CONSTRUCT PAYLOAD BASED ON MESSAGE TYPE ---
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_number,
        }

        if message_type == "text":
            message_text = request.POST.get("message_text")
            if not message_text:
                context['error'] = {"error": {"message": "Message text is required for this message type."}}
                return render(request, "sender_app/index.html", context)

            payload["type"] = "text"
            payload["text"] = {"preview_url": False, "body": message_text}

        elif message_type == "template":
            template_name = request.POST.get("template_name")
            if not template_name:
                context['error'] = {"error": {"message": "Template name is required for this message type."}}
                return render(request, "sender_app/index.html", context)

            payload["type"] = "template"
            payload["template"] = {
                "name": template_name,
                "language": {"code": "ru"} # NOTE: Hardcoded for simplicity, can be made dynamic later
            }
        else:
            context['error'] = {"error": {"message": "Invalid message type selected."}}
            return render(request, "sender_app/index.html", context)
        # --- END PAYLOAD CONSTRUCTION ---

        try:
            # Make the API call
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()

            response_data = response.json()
            context['success'] = True
            context['response'] = json.dumps(response_data, indent=2)

        except requests.exceptions.RequestException as e:
            context['success'] = False
            # Try to get more detailed error from Meta's response if available
            error_message = f"API request failed: {e}"
            try:
                error_details = e.response.json()
                error_message += f"\nDetails: {json.dumps(error_details, indent=2)}"
            except (ValueError, AttributeError):
                pass # No JSON in response
            context['error'] = error_message


    return render(request, "sender_app/index.html", context)

