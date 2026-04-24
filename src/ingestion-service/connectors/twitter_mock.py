import time
import uuid
import random
from faker import Faker

fake = Faker()

def start_twitter_mock():
    """
    Generator that yields fake Tweets.
    """
    while True:
        content_id = str(uuid.uuid4())
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        
        data = {
            'content_id': content_id,
            'tweet_id': str(random.randint(100000000, 999999999)),
            'timestamp': timestamp,
            'platform': 'twitter',
            'content_type': 'text',
            'content': fake.text(max_nb_chars=280),
            'followers_count': random.randint(0, 10000),
            'following_count': random.randint(0, 5000),
            'is_verified': random.choice([True, False])
        }
        
        yield data
        time.sleep(15)
