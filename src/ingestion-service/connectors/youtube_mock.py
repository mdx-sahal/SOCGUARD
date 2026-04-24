import time
import uuid
import random

# Mock Data Pools
YOUTUBE_VIDEOS = [
    ("Crypto Scam Live", "Double your BTC now! Live event.", "https://youtube.com/watch?v=scam123"),
    ("Legit Tutorial", "How to code in Python", "https://youtube.com/watch?v=py123"),
    ("Deepfake Celebrity", "Famous person says controversial thing", "https://youtube.com/watch?v=fake456"),
]

YOUTUBE_COMMENTS = [
    "Great video!",
    "Click this link for free money: http://malicious.link",
    "Sub for sub?",
    "This is clearly AI generated.",
]

def start_youtube_mock():
    """
    Generator that simulates a stream of YouTube content (videos and comments).
    """
    while True:
        content_id = str(uuid.uuid4())
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        
        # 0=Video, 1=Comment
        msg_type = random.choice(['video', 'comment'])
        
        data = {
            'content_id': content_id,
            'timestamp': timestamp,
            'platform': 'YouTube',
            'author_channel': f"User_{random.randint(1000, 9999)}",
            'subscribers_count': random.randint(0, 1000000),
            'is_verified': random.random() > 0.9,
        }

        if msg_type == 'video':
            title, desc, url = random.choice(YOUTUBE_VIDEOS)
            # Simulate some threat logic
            is_threat = "Scam" in title or "Deepfake" in title
            
            data.update({
                'content_type': 'video',
                'title': title,
                'content': f"{title} - {desc}", # Unified content field
                'url': url,
                'video_duration': random.randint(60, 3600)
            })
        else:
            comment = random.choice(YOUTUBE_COMMENTS)
            data.update({
                'content_type': 'comment',
                'content': comment,
                'video_id': f"v_{random.randint(100, 999)}"
            })

        yield data
        time.sleep(7) # Emit every 7 seconds
