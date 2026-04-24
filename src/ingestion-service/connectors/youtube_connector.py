
import os
import time
import logging
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# Logging
logger = logging.getLogger(__name__)

# Config
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
YOUTUBE_SEARCH_QUERY = os.environ.get('YOUTUBE_SEARCH_QUERY', 'cybersecurity threat news')
POLL_INTERVAL = int(os.environ.get('YOUTUBE_POLL_INTERVAL', 60))  # seconds

def start_youtube_listener(callback):
    """
    Polls YouTube Data API for new videos/comments matching search criteria.
    """
    if not YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY is missing. Real-time YouTube ingestion disabled.")
        return

    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        logger.info(f"Connected to YouTube Data API. Query: '{YOUTUBE_SEARCH_QUERY}'")
    except Exception as e:
        logger.error(f"Failed to connect to YouTube API: {e}")
        return

    # Track seen videos
    seen_ids = set()
    
    # Initial "last check" time (e.g., now - 1 hour)
    last_check_time = (datetime.utcnow() - timedelta(hours=1)).isoformat() + 'Z'

    while True:
        try:
            logger.info("Polling YouTube for new content...")
            
            # Search for new videos
            request = youtube.search().list(
                part="snippet",
                q=YOUTUBE_SEARCH_QUERY,
                type="video",
                order="date",
                publishedAfter=last_check_time,
                maxResults=10
            )
            response = request.execute()

            items = response.get("items", [])
            if not items:
                logger.debug("No new videos found.")
            
            # Update last check time for next iteration
            # (Note: simpler to just use publishedAt of newest item, 
            #  but current time is safer to avoid gaps/dupes if API lags)
            current_poll_time = datetime.utcnow().isoformat() + 'Z' 

            for item in items:
                video_id = item['id']['videoId']
                if video_id in seen_ids:
                    continue
                
                seen_ids.add(video_id)
                snippet = item['snippet']
                
                # Extract Data
                title = snippet['title']
                description = snippet['description']
                channel_title = snippet['channelTitle']
                publish_time = snippet['publishedAt']
                thumbnail = snippet['thumbnails']['high']['url']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                content = f"{title}\n{description}"
                
                logger.info(f"New YouTube Video: {title[:30]}...")

                event_data = {
                    'content_id': video_id,
                    'timestamp': publish_time,
                    'platform': 'youtube',
                    'content_type': 'video',
                    'content': content,
                    'image_url': thumbnail, 
                    'original_url': video_url,
                    'author_id': snippet['channelId'],
                    'author_username': channel_title,
                    'is_verified': False, # API doesn't return verification status in snippet easy
                    'is_bot': False
                }
                
                callback(event_data)
                
                # Optional: Fetch comments for this video
                # fetch_comments(youtube, video_id, callback)

            # Update time
            last_check_time = current_poll_time
            
            # Sleep
            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"YouTube Polling Error: {e}")
            time.sleep(60) # Backoff on error
