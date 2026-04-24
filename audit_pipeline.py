import json
import time
from confluent_kafka import Producer

KAFKA_BROKER = 'localhost:9092'
topic = 'social-media-feed'

conf = {'bootstrap.servers': KAFKA_BROKER}
p = Producer(conf)

def delivery_report(err, msg):
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')

# Mock data for Telegram
mock_msg = {
    'content_id': f'test_audit_{int(time.time())}',
    'timestamp': str(int(time.time())),
    'platform': 'telegram',
    'content_type': 'text',
    'content': 'URGENT: Click here to verify your account and win free bitcoin!',
    'author_id': '12345',
    'author_username': 'audit_tester',
    'is_verified': False,
    'is_bot': False
}

print(f"Producing test message to {topic}...")
p.produce(topic, json.dumps(mock_msg).encode('utf-8'), callback=delivery_report)
p.flush()
print("Done.")
