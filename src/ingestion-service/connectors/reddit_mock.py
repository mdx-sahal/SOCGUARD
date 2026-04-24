import time
import uuid
import random

# Mock Data Pools
PHISHING_TEXTS = [
    ("URGENT: Your account is locked!", "Click here https://bit.ly/fake to verify identity."),
    ("Free Bitcoin Giveaway", "Send 0.1 BTC to receive 1.0 BTC. Limited time!"),
    ("Security Alert", "Unusual login detected. Reset password at http://secure-login.net"),
]

SAFE_TEXTS = [
    ("Python Help", "How do I reverse a list in Python?"),
    ("Cute Cat", "Look at this cat video I found!"),
    ("Weather Update", "It's sunny in San Francisco today."),
]

# Using placeholders that our heuristic logic will flag (e.g. "synthetic" in URL)
DEEPFAKE_IMAGES = [
    "https://example.com/synthetic_face_v2.jpg",
    "https://ai-generated-media.net/deepfake_sample.png"
]

SAFE_IMAGES = [
    "https://picsum.photos/200", 
    "https://via.placeholder.com/150"
]

SYNTHETIC_AUDIO = [
    "https://example.com/audio/synthetic_voice_cloning.wav",
    "https://deep-voice.io/demo/fake_ceo.mp3"
]

NATURAL_AUDIO = [
    "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_copyright_sample.wav",
    "https://www2.cs.uic.edu/~i101/SoundFiles/BabyElephantWalk60.wav"
]

def start_multi_modal_mock():
    """
    Generator that simulates a stream of multi-modal content.
    Rotates between Text, Image, Audio, and specific Metadata Anomalies.
    """
    while True:
        content_id = str(uuid.uuid4())
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        
        # 0=Text, 1=Image, 2=Audio, 3=MetadataAnomaly
        scenario = random.choice(['text', 'text', 'image', 'audio', 'metadata_anomaly'])
        
        data = {
            'content_id': content_id,
            'timestamp': timestamp,
            'platform': 'reddit_sim', # Distinguished from real reddit
            'author_karma': random.randint(100, 10000),
            'upvote_ratio': random.uniform(0.7, 1.0),
            'followers_count': random.randint(50, 5000),
            'following_count': random.randint(10, 1000),
            'posts_count': random.randint(10, 1000),
            'account_age_days': random.randint(30, 3650), # Default healthy age
            'is_verified': False,
            'is_bot': False
        }

        if scenario == 'text':
            # 30% chance of threat
            if random.random() < 0.3:
                title, body = random.choice(PHISHING_TEXTS)
                data.update({
                    'content_type': 'text',
                    'content': f"{title} {body}"
                })
            else:
                title, body = random.choice(SAFE_TEXTS)
                data.update({
                    'content_type': 'text',
                    'content': f"{title} {body}"
                })

        elif scenario == 'image':
            # 40% chance of deepfake
            if random.random() < 0.4:
                url = random.choice(DEEPFAKE_IMAGES)
                data.update({
                    'content_type': 'image',
                    'image_url': url,
                    'content': f"Check this image: {url}"
                })
            else:
                url = random.choice(SAFE_IMAGES)
                data.update({
                    'content_type': 'image',
                    'image_url': url,
                    'content': f"Look at this: {url}"
                })

        elif scenario == 'audio':
            # 40% chance of synthetic audio
            if random.random() < 0.4:
                url = random.choice(SYNTHETIC_AUDIO)
                data.update({
                    'content_type': 'audio',
                    'audio_url': url,
                    'content': f"Listen to this: {url}"
                })
            else:
                url = random.choice(NATURAL_AUDIO)
                data.update({
                    'content_type': 'audio',
                    'audio_url': url,
                    'content': f"Voice note: {url}"
                })

        elif scenario == 'metadata_anomaly':
            # Simulate a bot farm account (New account + High frequency)
            # This targets the IsolationForest model in metadata-service
            data.update({
                'content_type': 'text', # Content doesn't matter, metadata does
                'content': "Generic bot comment for metadata analysis.",
                'account_age_days': random.randint(1, 5), # Very new
                'posts_count': random.randint(500, 1000), # Suspiciously high for new account
                'followers_count': 1,
                'following_count': 500 # Follows many, followed by few
            })

        yield data
        time.sleep(5) # Emit every 5 seconds
