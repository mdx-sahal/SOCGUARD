import os
import time
import base64
import logging
import io
from PIL import Image
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

CLIENT_ID = os.environ.get('EMAIL_CLIENT_ID')
CLIENT_SECRET = os.environ.get('EMAIL_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('EMAIL_REFRESH_TOKEN')

def get_gmail_service():
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        logger.warning("Gmail API credentials missing. Email ingestion disabled.")
        return None

    try:
        creds = Credentials(
            None,
            refresh_token=REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {e}")
        return None

def start_email_listener(callback):
    """
    Polls Gmail API for new emails.
    """
    service = get_gmail_service()
    if not service:
        return

    logger.info("Starting Gmail API Listener...")
    seen_message_ids = set()

    while True:
        try:
            # Query the unread messages in primary inbox and spam
            results = service.users().messages().list(userId='me', maxResults=10).execute()
            messages = results.get('messages', [])

            for msg in messages:
                msg_id = msg['id']
                if msg_id in seen_message_ids:
                    continue
                seen_message_ids.add(msg_id)

                # Fetch full message payload
                msg_detail = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])

                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'unknown')
                timestamp = msg_detail.get('internalDate', str(int(time.time()*1000))) 
                timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(int(timestamp)/1000))

                # Extract Body & Image
                body = ""
                image_url = None
                parts = [payload]
                while parts:
                    part = parts.pop()
                    if part.get('parts'):
                        parts.extend(part['parts'])
                    mime = part.get('mimeType', '')
                    if mime == 'text/plain':
                        data = part.get('body', {}).get('data', '')
                        if data:
                            data = data + '=' * (-len(data) % 4)
                            body += base64.urlsafe_b64decode(data).decode('utf-8')
                    elif mime == 'text/html' and not body:
                        data = part.get('body', {}).get('data', '')
                        if data:
                            data = data + '=' * (-len(data) % 4)
                            body += base64.urlsafe_b64decode(data).decode('utf-8')
                    elif mime.startswith('image/') and not image_url:
                        attach_id = part.get('body', {}).get('attachmentId')
                        img_data = part.get('body', {}).get('data')
                        if attach_id:
                            try:
                                attach = service.users().messages().attachments().get(
                                    userId='me', messageId=msg_id, id=attach_id
                                ).execute()
                                img_data = attach.get('data')
                            except Exception as e:
                                logger.error(f"Failed to fetch image attachment: {e}")
                        if img_data:
                            try:
                                img_data = img_data + '=' * (-len(img_data) % 4)
                                raw_bytes = base64.urlsafe_b64decode(img_data)
                                
                                # Resize image to prevent Kafka size overflow
                                img = Image.open(io.BytesIO(raw_bytes))
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                                img.thumbnail((800, 800))
                                
                                out_io = io.BytesIO()
                                img.save(out_io, format='JPEG', quality=85)
                                resized_bytes = out_io.getvalue()
                                
                                std_b64 = base64.b64encode(resized_bytes).decode('utf-8')
                                image_url = f"data:image/jpeg;base64,{std_b64}"
                            except Exception as e:
                                logger.error(f"Failed to decode or resize image attachment: {e}")

                event_data = {
                    'content_id': msg_id,
                    'timestamp': timestamp,
                    'platform': 'email',
                    'content_type': 'image' if image_url else 'text',
                    'content': f"Subject: {subject}\n\n{body}",
                    'image_url': image_url,
                    'author_id': sender,
                    'author_username': sender.split('<')[0].strip() if '<' in sender else sender,
                    'is_verified': False
                }

                logger.info(f"New Gmail Received: {subject[:30]}")
                callback(event_data)

            time.sleep(30) # Poll every 30 seconds

        except Exception as e:
            logger.error(f"Gmail API Polling Error: {e}")
            time.sleep(60)
