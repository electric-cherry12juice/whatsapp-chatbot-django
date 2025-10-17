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
from django.db.models import Max, Q

# Get our custom logger
meta_api_logger = logging.getLogger('meta_api_logger')


# --- Helper Function to Send OTP to Admin ---
def send_otp_to_admin(code):
    admin_number = settings.ADMIN_PHONE_NUMBER
    if not admin_number:
        meta_api_logger.critical("ADMIN_PHONE_NUMBER is not set in environment variables!")
        return False
    # ... rest of the function is the same ...
    access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    message_body = f"Your login verification code is: {code}"
    payload = {"messaging_product": "whatsapp", "to": admin_number, "type": "text", "text": {"body": message_body}}
    meta_api_logger.info(f"Sending OTP to ADMIN. Payload: {json.dumps(payload)}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        meta_api_logger.info(f"OTP Send Response to ADMIN: Status {response.status_code}, Body: {response.text}")
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        meta_api_logger.error(f"OTP Send Request failed for ADMIN: {e}")
        return False

# --- Authentication Views ---
def login_view(request):
    if request.session.get('is_authenticated'):
        return redirect('chat_interface')
    if request.method == 'POST':
        otp_code = random.randint(100000, 999999)
        request.session['otp_code_for_verification'] = otp_code
        if send_otp_to_admin(otp_code):
            return redirect(reverse('verify_view'))
        else:
            return render(request, 'sender_app/login.html', {'error': 'Could not send verification code to administrator.'})
    return render(request, 'sender_app/login.html')

def verify_view(request):
    if 'otp_code_for_verification' not in request.session:
        return redirect(reverse('login_view'))
    if request.method == 'POST':
        entered_code = request.POST.get('otp_code')
        stored_code = request.session.get('otp_code_for_verification')
        if entered_code and stored_code and int(entered_code) == stored_code:
            request.session['is_authenticated'] = True
            request.session['authenticated_user'] = "Admin"
            request.session.set_expiry(60 * 60 * 11)
            del request.session['otp_code_for_verification']
            return redirect(reverse('chat_interface'))
        else:
            return render(request, 'sender_app/verify.html', {'error': 'Invalid code.'})
    return render(request, 'sender_app/verify.html')

def logout_view(request):
    request.session.flush()
    return redirect(reverse('login_view'))

# --- Custom Decorator ---
def custom_login_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('is_authenticated'):
            return redirect(reverse('login_view'))
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# --- Main Application Views ---
@custom_login_required
def chat_interface_view(request):
    contacts = ChatMessage.objects.values('sender_id').annotate(
        latest_message=Max('timestamp')
    ).order_by('-latest_message').values_list('sender_id', flat=True)
    
    return render(request, 'sender_app/chat_interface.html', {
        'contacts': contacts, 
        'username': request.session.get('authenticated_user')
    })

@custom_login_required
def get_chat_history_json(request, phone_number):
    messages = ChatMessage.objects.filter(sender_id=phone_number).order_by('timestamp')
    message_list = list(messages.values('message_text', 'is_from_user'))
    return JsonResponse({'messages': message_list})

@custom_login_required
def search_chats_json(request):
    query = request.GET.get('q', '')
    if not query:
        contacts = ChatMessage.objects.values('sender_id').annotate(
            latest_message=Max('timestamp')
        ).order_by('-latest_message').values_list('sender_id', flat=True)
    else:
        matching_contacts = ChatMessage.objects.filter(
            Q(message_text__icontains=query) | Q(sender_id__icontains=query)
        ).values('sender_id').annotate(
            latest_message=Max('timestamp')
        ).order_by('-latest_message').values_list('sender_id', flat=True)
        contacts = list(matching_contacts)
    return JsonResponse({'contacts': contacts})


def send_template_message(phone_number, template_name):
    # This helper function logic remains the same
    access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": phone_number, "type": "template",
        "template": {"name": template_name, "language": {"code": "en_US"}},
    }
    meta_api_logger.info(f"Starting new chat with {phone_number}. Payload: {json.dumps(payload)}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response_data = response.json()
        meta_api_logger.info(f"Start Chat Response: Status {response.status_code}, Body: {response.text}")
        if response.status_code == 200:
            return {'success': True, 'data': response_data}
        else:
            error_message = response_data.get('error', {}).get('message', 'An unknown error occurred.')
            if "not a valid WhatsApp user" in error_message or "Recipient phone number not in allowed list" in error_message:
                return {'success': False, 'error': 'This phone number is not a valid WhatsApp user.'}
            return {'success': False, 'error': error_message}
    except requests.exceptions.RequestException as e:
        meta_api_logger.error(f"Start Chat Request failed: {e}")
        return {'success': False, 'error': 'A network error occurred.'}

@custom_login_required
def start_new_chat_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        phone_number = data.get('phone_number')
        template_name = data.get('template_name')
        if not phone_number or not template_name:
            return JsonResponse({'success': False, 'error': 'Phone number and template name are required.'}, status=400)
        result = send_template_message(phone_number, template_name)
        if result['success']:
            ChatMessage.objects.create(
                sender_id=phone_number,
                message_text=f"Started chat with template: '{template_name}'",
                is_from_user=False
            )
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
            if 'entry' in data and data['entry'][0].get('changes', [{}])[0].get('value', {}).get('messages'):
                message_data = data['entry'][0]['changes'][0]['value']['messages'][0]
                sender_id = message_data['from']
                message_text = message_data['text']['body']
                
                ChatMessage.objects.create(sender_id=sender_id, message_text=message_text, is_from_user=True)
                
                channel_layer = get_channel_layer()
                # THE FIX IS HERE: We now include the sender_id in the broadcast event
                async_to_sync(channel_layer.group_send)(
                    f'chat_{sender_id}',
                    {
                        'type': 'chat_message',
                        'message': message_text,
                        'is_from_user': True,
                        'sender_id': sender_id # This was missing!
                    }
                )
        except (IndexError, KeyError) as e:
            meta_api_logger.warning(f"Could not parse webhook data: {e} - Data: {json.dumps(data)}")
        return HttpResponse(status=200)

    if request.method == "GET":
        verify_token = os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN')
        if request.GET.get("hub.verify_token") == verify_token:
             return HttpResponse(request.GET.get("hub.challenge"), status=200)
        else:
             return HttpResponse("Invalid verification token", status=403)
    return HttpResponse(status=405)

def health_check_view(request):
    return JsonResponse({"status": "ok"})

