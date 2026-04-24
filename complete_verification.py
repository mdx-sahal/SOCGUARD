import json
import time
import psycopg2
from confluent_kafka import Producer

KAFKA_BROKER = 'localhost:9092'
TOPIC = 'social-media-feed'

# Database Configuration
DB_HOST = "127.0.0.1"
DB_PORT = "5435"
DB_NAME = "socguard_db"
DB_USER = "socguard_user"
DB_PASS = "socguard_password"

def delivery_report(err, msg):
    if err is not None:
        print(f'   [X] Message delivery failed: {err}')
    else:
        print(f'   [+] Message delivered to {msg.topic()} [{msg.partition()}]')

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def main():
    print("=========================================")
    print(" SOCGUARD COMPREHENSIVE VERIFICATION RUN")
    print("=========================================\n")
    
    # 1. Produce Messages
    try:
        producer = Producer({'bootstrap.servers': KAFKA_BROKER})
    except Exception as e:
        print(f"Failed to connect to Kafka: {e}")
        return

    base_time = int(time.time())

    test_payloads = [
        # Test 1: Text Analysis (Toxicity)
        {
            'content_id': f'test_txt_{base_time}',
            'timestamp': str(base_time),
            'platform': 'telegram',
            'content_type': 'text',
            'content': 'I am going to destroy you! You are terrible!',
            'author_username': 'text_tester'
        },
        # Test 2: Image Analysis (Should trigger image processing)
        {
            'content_id': f'test_img_{base_time}',
            'timestamp': str(base_time),
            'platform': 'telegram',
            'content_type': 'image',
            'content': 'Check out this picture',
            'image_url': 'https://upload.wikimedia.org/wikipedia/commons/e/e0/Placeholder_1.png', # Clean test Image
            'author_username': 'image_tester'
        },
        # Test 3: Audio Analysis & Phishing Check
        {
            'content_id': f'test_aud_{base_time}',
            'timestamp': str(base_time),
            'platform': 'email',
            'content_type': 'audio',
            'content': 'Please verify your bank login at http://secure-update-login.com to unlock your fund',
            'audio_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
            'author_username': 'audio_tester'
        },
        # Test 4: Bot & Metadata Analysis
        {
            'content_id': f'test_bot_{base_time}',
            'timestamp': str(base_time),
            'platform': 'twitter',
            'content_type': 'text',
            'content': 'Just a normal tweet',
            'author_username': 'bot_tester',
            'followers_count': 1,
            'following_count': 5000,
            'account_age_days': 2,
            'posts_count': 1000,
            'is_bot': True,
            'is_verified': False
        }
    ]

    print("[*] Dispatching Mock Data to Kafka 'social-media-feed' Pipeline...")
    for payload in test_payloads:
        producer.produce(TOPIC, json.dumps(payload).encode('utf-8'), callback=delivery_report)
    producer.flush()
    
    print("\n[*] Waiting 20 seconds for analysis services to process payloads...")
    time.sleep(20)
    
    print("\n[*] Querying Database for Analysis Results...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        for payload in test_payloads:
            cid = payload['content_id']
            # Analysis services often append suffixes like _meta, _audio, _text to content_id
            cur.execute(f"SELECT threat_category, severity_score, reasoning, platform FROM alerts WHERE content_id LIKE '{cid}%'")
            results = cur.fetchall()
            
            print(f"\nResults for Platform: '{payload['platform']}' | Base ID: {cid}")
            if not results:
                print("   -> NO ALERTS GENERATED (or processing too slow)")
            else:
                for res in results:
                    threat, score, reasoning, platform = res
                    print(f"   -> [ALERT CAUGHT] Platform: {platform} | Threat: '{threat}' | Severity: {score}")
                    print(f"      Reasoning Extract: {reasoning[:200]}...")
                    
    except Exception as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    main()
