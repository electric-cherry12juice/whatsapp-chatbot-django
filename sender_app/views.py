import json
import os
import requests
import random
import logging
from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import ChatMessage

# Get our custom logger
meta_api_logger = logging.getLogger('meta_api_logger')


# --- Helper Function to Send OTP to Admin ---
def send_otp_to_admin(code, username):
    """
    Sends the generated OTP code to the admin's number as a plain text message.
    """
    admin_phone = settings.ADMIN_PHONE_NUMBER
    if not admin_phone:
        meta_api_logger.error("ADMIN_PHONE_NUMBER is not set in settings.")
        return False

    access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    message_body = f"Login request from user: {username}\nYour verification code is: {code}"
    
    payload = {
        "messaging_product": "whatsapp",
        "to": admin_phone,
        "type": "text",
        "text": {"body": message_body},
    }

    meta_api_logger.info(f"Sending OTP to ADMIN for user {username}. Payload: {json.dumps(payload)}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        meta_api_logger.info(f"OTP Send Response to ADMIN: Status {response.status_code}, Body: {response.text}")
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        meta_api_logger.error(f"OTP Send Request to ADMIN failed: {e}")
        return False


# --- Authentication Views ---
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        if username:
            otp_code = random.randint(100000, 999999)
            request.session['otp_code'] = otp_code
            request.session['otp_username'] = username
            
            if send_otp_to_admin(otp_code, username):
                return redirect(reverse('verify_view'))
            else:
                return render(request, 'sender_app/login.html', {'error': 'Could not send verification code to administrator.'})
    return render(request, 'sender_app/login.html')

def verify_view(request):
    username = request.session.get('otp_username')
    if not username:
        return redirect(reverse('login_view'))

    if request.method == 'POST':
        entered_code = request.POST.get('otp_code')
        stored_code = request.session.get('otp_code')

        if entered_code and stored_code and int(entered_code) == stored_code:
            request.session['is_authenticated'] = True
            request.session['authenticated_user'] = username
            request.session.set_expiry(60 * 60 * 11) # 11 hours
            
            del request.session['otp_code']
            del request.session['otp_username']
            return redirect(reverse('chat_interface'))
        else:
            return render(request, 'sender_app/verify.html', {'error': 'Invalid code.', 'username': username})
    return render(request, 'sender_app/verify.html', {'username': username})

def logout_view(request):
    request.session.flush()
    return redirect(reverse('login_view'))


# --- Custom Decorator to Check Authentication ---
def custom_login_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('is_authenticated'):
            return redirect(reverse('login_view'))
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# --- Main Application Views (Now Secured) ---
@custom_login_required
def chat_interface_view(request):
    contacts = ChatMessage.objects.values_list('sender_id', flat=True).distinct().order_by('-timestamp')
    return render(request, 'sender_app/chat_interface.html', {
        'contacts': contacts,
        'username': request.session.get('authenticated_user')
    })

@custom_login_required
def get_chat_history_json(request, phone_number):
    messages = ChatMessage.objects.filter(sender_id=phone_number).order_by('timestamp')
    data = {"messages": list(messages.values('message_text', 'is_from_user', 'timestamp'))}
    return JsonResponse(data)


# --- API Endpoint to Start a Chat ---
@custom_login_required
def start_new_chat_view(request):
    if request.method == 'POST':
        # ... [This function remains the same as your latest version] ...
        # (It's included in the full code block for completeness)
        data = json.loads(request.body)
        phone_number = data.get('phone_number')
        template_name = data.get('template_name')
        if not phone_number or not template_name:
            return JsonResponse({'success': False, 'error': 'Phone number and template name are required.'}, status=400)
        
        # This helper needs to be defined
        def send_template_message(phone_number, template_name):
            access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
            phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
            version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
            url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "template", "template": {"name": template_name, "language": {"code": "en_US"}}}
            meta_api_logger.info(f"Starting new chat with {phone_number}. Payload: {json.dumps(payload)}")
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=15)
                response_data = response.json()
                meta_api_logger.info(f"Start Chat Response: Status {response.status_code}, Body: {response.text}")
                if response.status_code == 200: return {'success': True, 'data': response_data}
                else: return {'success': False, 'error': response_data.get('error', {}).get('message', 'An unknown error occurred.')}
            except requests.exceptions.RequestException as e:
                meta_api_logger.error(f"Start Chat Request failed: {e}")
                return {'success': False, 'error': 'A network error occurred.'}

        result = send_template_message(phone_number, template_name)
        if result['success']:
            ChatMessage.objects.create(sender_id=phone_number, message_text=f"Started chat with template: '{template_name}'", is_from_user=False)
            return JsonResponse({'success': True, 'phone_number': phone_number})
        else:
            return JsonResponse({'success': False, 'error': result['error']}, status=400)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# --- Webhook ---
@csrf_exempt
def webhook_view(request):
    if request.method == "POST":
        data = json.loads(request.body)
        meta_api_logger.info(f"Webhook received: {json.dumps(data)}")
        try:
            if 'object' in data and data['object'] == 'whatsapp_business_account':
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messages' in change['value']:
                            message_data = change['value']['messages'][0]
                            phone_number = message_data['from']
                            message_text = message_data['text']['body']
                            
                            ChatMessage.objects.create(
                                sender_id=phone_number,
                                message_text=message_text,
                                is_from_user=True
                            )
                            
                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                f"chat_{phone_number}",
                                {
                                    "type": "chat_message",
                                    "message": message_text,
                                    "is_from_user": True
                                }
                            )
        except Exception as e:
            meta_api_logger.error(f"Error processing webhook: {e}")
        return HttpResponse(status=200)

    elif request.method == "GET":
        verify_token = request.GET.get("hub.verify_token")
        if verify_token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            return HttpResponse(request.GET.get("hub.challenge"), status=200)
        else:
            return HttpResponse("Invalid verification token", status=403)
    return HttpResponse(status=405)




def health_check_view(request):
    return JsonResponse({"status": "ok"})