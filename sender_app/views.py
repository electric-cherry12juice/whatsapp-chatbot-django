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
from uuid import uuid4
import mimetypes
from django.http import FileResponse, Http404

meta_api_logger = logging.getLogger('meta_api_logger')

# --- NEW HELPER: Downloads and saves media from WhatsApp ---
def process_whatsapp_media(media_id):
    """
    Download media from WhatsApp/Meta, save into MEDIA_ROOT/<type>/<uuid>.<ext>
    Return a web-accessible path: /media/<type>/<filename> and the file type (image|audio).
    """
    access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')

    url_get_media = f"https://graph.facebook.com/{version}/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response_get_url = requests.get(url_get_media, headers=headers, timeout=15)
        if response_get_url.status_code != 200:
            meta_api_logger.error(f"Failed to get media metadata for ID {media_id}. Response: {response_get_url.text}")
            return None, None

        media_data = response_get_url.json()
        download_url = media_data.get('url') or media_data.get('uri')  # sometimes named differently
        mime_type = media_data.get('mime_type') or media_data.get('mimetype')
        if not download_url:
            meta_api_logger.error(f"No download URL in media data for ID {media_id}: {media_data}")
            return None, None

        # download the actual file (use same auth header)
        response_download = requests.get(download_url, headers=headers, timeout=20)
        if response_download.status_code != 200:
            meta_api_logger.error(f"Failed to download media from {download_url}. Status: {response_download.status_code}")
            return None, None

        # determine extension and type
        if not mime_type:
            mime_type = response_download.headers.get('Content-Type', '')

        file_extension = 'bin'
        if mime_type:
            guessed_ext = mimetypes.guess_extension(mime_type.split(';')[0].strip())
            if guessed_ext:
                file_extension = guessed_ext.lstrip('.')  # remove leading dot

        file_type = (mime_type.split('/')[0] if mime_type else '').lower()
        if file_type not in ['image', 'audio']:
            # fallback: inspect extension from url
            if any(download_url.lower().endswith(ext) for ext in ('.jpg','.jpeg','.png','.gif','.webp')):
                file_type = 'image'
            elif any(download_url.lower().endswith(ext) for ext in ('.mp3','.ogg','.amr','.wav','.m4a')):
                file_type = 'audio'
            else:
                meta_api_logger.warning(f"Unsupported media type: {mime_type} for id {media_id}")
                return None, None

        # secure filename
        file_name = f"{uuid4()}.{file_extension}"
        # save into MEDIA_ROOT/<file_type>/<file_name>
        media_dir = os.path.join(settings.MEDIA_ROOT, file_type)
        os.makedirs(media_dir, exist_ok=True)
        file_full_path = os.path.join(media_dir, file_name)
        with open(file_full_path, 'wb') as f:
            f.write(response_download.content)

        # log the real disk path + public path
        web_path = f"/media/{file_type}/{file_name}"
        meta_api_logger.info(f"Saved media for {media_id} to {file_full_path} -> {web_path}")
        return web_path, file_type


    except requests.exceptions.RequestException as e:
        meta_api_logger.error(f"Network error while processing media ID {media_id}: {e}")
        return None, None
    except Exception as e:
        meta_api_logger.error(f"Unexpected error saving media ID {media_id}: {e}")
        return None, None
    


def serve_media(request, path):
    """
    Serve files from MEDIA_ROOT for /media/<path> requests.
    Temporary solution for Render until you move to object storage.
    """
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(full_path):
        meta_api_logger.warning(f"Media file not found: {full_path}")
        raise Http404("Media not found")
    content_type, _ = mimetypes.guess_type(full_path)
    try:
        return FileResponse(open(full_path, 'rb'), content_type=content_type or 'application/octet-stream')
    except Exception as e:
        meta_api_logger.error(f"Error sending media file {full_path}: {e}")
        raise Http404("Media read error")


# --- Your existing helper ---
def send_otp_to_admin(code):
    # This function is unchanged
    admin_number = settings.ADMIN_PHONE_NUMBER
    if not admin_number:
        meta_api_logger.critical("ADMIN_PHONE_NUMBER is not set in environment variables!")
        return False
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

# --- Your existing auth views (unchanged) ---
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

def custom_login_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('is_authenticated'):
            return redirect(reverse('login_view'))
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# --- Main Application Views (chat_history UPGRADED) ---
@custom_login_required
def chat_interface_view(request):
    contacts = ChatMessage.objects.values('sender_id').annotate(
        latest_message=Max('timestamp')
    ).order_by('-latest_message').values_list('sender_id', flat=True)
    return render(request, 'sender_app/chat_interface.html', {'contacts': contacts})

@custom_login_required
def get_chat_history_json(request, phone_number):
    messages = ChatMessage.objects.filter(sender_id=phone_number).order_by('timestamp')
    # UPGRADED: Now returns media_url as well for displaying old media
    message_list = list(messages.values('message_text', 'media_url', 'is_from_user'))
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


# --- send_template_message (UPGRADED for number validation) ---
def send_template_message(phone_number, template_name):
    access_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    version = os.environ.get('WHATSAPP_API_VERSION', 'v20.0')
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "template", "template": {"name": template_name, "language": {"code": "ru_RU"}}}
    meta_api_logger.info(f"Starting new chat with {phone_number}. Payload: {json.dumps(payload)}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response_data = response.json()
        meta_api_logger.info(f"Start Chat Response: Status {response.status_code}, Body: {response.text}")
        if response.status_code == 200:
            return {'success': True, 'data': response_data}
        else:
            error_message = response_data.get('error', {}).get('message', 'An unknown error occurred.')
            error_details = response_data.get('error', {}).get('error_data', {}).get('details', '')
            if "not a valid WhatsApp user" in error_message or "Recipient phone number not in allowed list" in error_message or "does not exist" in error_details:
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

# --- Webhook (UPGRADED for media) ---

@csrf_exempt
def webhook_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception as e:
            meta_api_logger.error(f"Webhook payload JSON parse error: {e} - raw: {request.body}")
            return HttpResponse(status=400)

        meta_api_logger.info(f"Webhook received: {json.dumps(data)[:8000]}")  # avoid logging giant payloads fully

        try:
            entries = data.get('entry', [])
            for entry in entries:
                changes = entry.get('changes', [])
                for change in changes:
                    value = change.get('value', {})
                    messages = value.get('messages') or []
                    for message_data in messages:
                        sender_id = message_data.get('from')
                        message_type = message_data.get('type')
                        content_for_broadcast = None

                        if message_type == 'text':
                            message_text = message_data.get('text', {}).get('body')
                            if message_text:
                                ChatMessage.objects.create(sender_id=sender_id, message_text=message_text, is_from_user=True, message_type='text')
                                content_for_broadcast = message_text

                        elif message_type in ['image', 'audio', 'video', 'document']:
                            # prefer the webhook-provided url if available (some webhooks include it)
                            media_obj = message_data.get(message_type, {})
                            media_id = media_obj.get('id')
                            webhook_url = media_obj.get('url') or media_obj.get('link')
                            meta_api_logger.info(f"Incoming media: type={message_type} id={media_id} url={webhook_url}")

                            web_path = None
                            media_type_str = 'image' if message_type == 'image' else 'audio' if message_type == 'audio' else message_type

                            # If webhook already included a ready-to-download url, try that first
                            if webhook_url:
                                try:
                                    r = requests.get(webhook_url, timeout=20)
                                    if r.status_code == 200:
                                        # determine extension from headers or url
                                        content_type = r.headers.get('Content-Type', '')
                                        ext = content_type.split('/')[-1].split(';')[0] or 'bin'
                                        file_name = f"{uuid4()}.{ext}"
                                        media_dir = os.path.join(settings.MEDIA_ROOT, media_type_str)
                                        os.makedirs(media_dir, exist_ok=True)
                                        file_full_path = os.path.join(media_dir, file_name)
                                        with open(file_full_path, 'wb') as f:
                                            f.write(r.content)
                                        web_path = f"/media/{media_type_str}/{file_name}"
                                        meta_api_logger.info(f"Saved webhook-provided media to {file_full_path} -> {web_path}")
                                except Exception as e:
                                    meta_api_logger.warning(f"Failed to download webhook url {webhook_url}: {e}")

                            # fallback to the media-id flow (Graph API /{media-id})
                            if not web_path and media_id:
                                web_path, mt = process_whatsapp_media(media_id)
                                media_type_str = mt or media_type_str

                            if web_path:
                                ChatMessage.objects.create(sender_id=sender_id, media_url=web_path, is_from_user=True, message_type=media_type_str)
                                content_for_broadcast = web_path
                            else:
                                meta_api_logger.error(f"Could not obtain media for id {media_id} from webhook for sender {sender_id}")

                        # Broadcast if we have content
                        if content_for_broadcast:
                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                f'chat_{sender_id}',
                                {'type': 'chat_message', 'message': content_for_broadcast, 'is_from_user': True, 'sender_id': sender_id}
                            )
        except Exception as e:
            meta_api_logger.exception(f"Unhandled exception processing webhook: {e} - Data: {json.dumps(data)[:8000]}")
        return HttpResponse(status=200)

    if request.method == "GET":
        verify_token = os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN')
        if request.GET.get("hub.verify_token") == verify_token:
            return HttpResponse(request.GET.get("hub.challenge"), status=200)
        else:
            return HttpResponse("Invalid verification token", status=403)

    return HttpResponse(status=405)


@custom_login_required
def delete_chat_view(request, phone_number):
    if request.method == 'DELETE':
        # Find all messages associated with the phone number and delete them
        deleted_count, _ = ChatMessage.objects.filter(sender_id=phone_number).delete()
        if deleted_count > 0:
            return JsonResponse({'success': True, 'message': f'Chat history with {phone_number} deleted.'})
        else:
            return JsonResponse({'success': False, 'error': 'No chat history found for this number.'}, status=404)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

def health_check_view(request):
    return JsonResponse({"status": "ok"})
