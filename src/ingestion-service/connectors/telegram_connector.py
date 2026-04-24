import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import sys

# Logging Setup
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Configuration
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Create a resilient HTTP session with automatic retries
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

def start_telegram_listener(callback):
    """
    Listens for new messages using Telegram Bot API (Long Polling).
    """
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing. Cannot start listener.")
        return

    logger.info(f"Starting Telegram Bot Listener (HTTP Polling)...")

    # Verify Token
    try:
        me = session.get(f"{BASE_URL}/getMe", timeout=10).json()
        if not me.get('ok'):
            logger.error(f"Bot Token Invalid: {me}")
            return
        logger.info(f"Bot Connected: @{me['result']['username']} (ID: {me['result']['id']})")
    except Exception as e:
        logger.error(f"Failed to connect to Telegram API: {e}")
        return

    offset = 0
    
    logger.info("Listening for messages...")
    
    while True:
        try:
            # Long polling: wait up to 30s for new messages
            params = {'offset': offset + 1, 'timeout': 30}
            response = session.get(f"{BASE_URL}/getUpdates", params=params, timeout=40)
            
            if response.status_code != 200:
                logger.error(f"Telegram API Error: {response.status_code} - {response.text}")
                time.sleep(5)
                continue

            data = response.json()
            if not data.get('ok'):
                continue

            updates = data.get('result', [])
            
            for update in updates:
                update_id = update['update_id']
                offset = max(offset, update_id)

                message = update.get('message') or update.get('channel_post')
                if not message:
                    continue
                
                # Determine Content Type
                content_type = 'text'
                content = message.get('text', '') or message.get('caption', '')
                image_url = None
                audio_url = None

                # Handle Photos
                if 'photo' in message:
                    try:
                        # detailed photo logic
                        photos = message['photo']
                        # Get largest photo (last in array)
                        best_photo = photos[-1]
                        file_id = best_photo['file_id']
                        
                        # Get File Path
                        file_res = session.get(f"{BASE_URL}/getFile", params={'file_id': file_id}, timeout=10).json()
                        if file_res.get('ok'):
                            file_path = file_res['result']['file_path']
                            # Construct Download URL
                            image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                            content_type = 'image'
                            logger.info(f"Image received. URL: {image_url}")
                        else:
                            logger.error(f"Failed to get file path: {file_res}")
                    except Exception as e:
                        logger.error(f"Error processing photo: {e}")

                # Handle Audio / Voice
                if 'voice' in message or 'audio' in message:
                    try:
                        audio_obj = message.get('voice') or message.get('audio')
                        file_id = audio_obj['file_id']
                        
                        # Get File Path
                        file_res = session.get(f"{BASE_URL}/getFile", params={'file_id': file_id}, timeout=10).json()
                        if file_res.get('ok'):
                            file_path = file_res['result']['file_path']
                            # Construct Download URL
                            audio_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                            content_type = 'audio'
                            logger.info(f"Audio received. URL: {audio_url}")
                        else:
                            logger.error(f"Failed to get audio file path: {file_res}")
                    except Exception as e:
                        logger.error(f"Error processing audio: {e}")

                # Skip if no content and no image and no audio
                if not content and not image_url and not audio_url:
                    continue

                # Extract Sender
                sender = message.get('from', {})
                chat = message.get('chat', {})
                username = sender.get('username') or chat.get('username') or "Unknown"
                
                logger.info(f"MSG RECV [{username}] Type={content_type}: {content[:30]}...")

                event_data = {
                    'content_id': str(message.get('message_id')),
                    'timestamp': str(message.get('date')), 
                    'platform': 'telegram',
                    'content_type': content_type,
                    'content': content,
                    'image_url': image_url, # New Field
                    'audio_url': audio_url, # Audio Field

                    'author_id': str(sender.get('id', 'Unknown')),
                    'author_username': username,
                    'is_verified': False,
                    'is_bot': sender.get('is_bot', False)
                }
                
                callback(event_data)

        except Exception as e:
            logger.error(f"Polling Error: {e}")
            time.sleep(5)
