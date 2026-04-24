
import os
import time
import logging
from atproto import Client
from datetime import datetime, timedelta

# Logging
logger = logging.getLogger(__name__)

# Config
BSKY_USERNAME = os.environ.get('BSKY_USERNAME')
BSKY_PASSWORD = os.environ.get('BSKY_PASSWORD')
BSKY_SEARCH_QUERY = os.environ.get('BSKY_SEARCH_QUERY', 'cybersecurity')
POLL_INTERVAL = int(os.environ.get('BSKY_POLL_INTERVAL', 60))

def start_bluesky_listener(callback):
    """
    Polls Bluesky for new posts matching search criteria.
    """
    if not BSKY_USERNAME or not BSKY_PASSWORD:
        logger.warning("BSKY_USERNAME or BSKY_PASSWORD missing. Bluesky ingestion disabled.")
        return

    client = Client()
    try:
        client.login(BSKY_USERNAME, BSKY_PASSWORD)
        logger.info(f"Connected to Bluesky as {BSKY_USERNAME}. Query: '{BSKY_SEARCH_QUERY}'")
    except Exception as e:
        logger.error(f"Failed to login to Bluesky: {e}")
        return

    # Track seen posts
    seen_cids = set()
    logger.info("Starting fresh Bluesky poll loop.")

    while True:
        try:
            # Search
            logger.info(f"Polling Bluesky... Query: '{BSKY_SEARCH_QUERY}'")
            
            # Using params dict as per error message
            logger.info(f"Polling Bluesky with params...")
            response = client.app.bsky.feed.search_posts(params={'q': BSKY_SEARCH_QUERY, 'limit': 10})
            
            # Check structure
            if hasattr(response, 'posts'):
                posts = response.posts
            else:
                posts = []
                logger.warning(f"Response has no 'posts' attribute: {dir(response)}")
            
            if not posts:
                logger.info(f"No new posts found. (Response type: {type(response)})")
            else:
                logger.info(f"Found {len(posts)} posts. First CID: {posts[0].cid if posts else 'N/A'}")

            for post in posts:
                cid = post.cid
                if cid in seen_cids:
                    continue
                
                seen_cids.add(cid)
                
                # Extract Data
                record = post.record
                text = record.text
                author = post.author
                handle = author.handle
                
                content_id = post.uri
                
                # Image extraction
                image_url = None
                if post.embed and hasattr(post.embed, 'images'):
                     try:
                         if len(post.embed.images) > 0:
                             image_url = post.embed.images[0].fullsize
                     except:
                         pass

                logger.info(f"New Bluesky Post: {text[:50]}...")

                event_data = {
                    'content_id': content_id,
                    'timestamp': record.created_at,
                    'platform': 'bluesky',
                    'content_type': 'text' if not image_url else 'image',
                    'content': text,
                    'image_url': image_url, 
                    'original_url': f"https://bsky.app/profile/{handle}/post/{post.uri.split('/')[-1]}",
                    'author_id': author.did,
                    'author_username': handle,
                    'is_verified': False, 
                    'is_bot': False
                }
                
                callback(event_data)

            # Sleep
            logger.info(f"Sleeping for 15 seconds...")
            time.sleep(15)

        except Exception as e:
            logger.error(f"Bluesky Polling Error: {e}")
            time.sleep(60)
