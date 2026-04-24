from confluent_kafka import Producer
import json
import time

KAFKA_BROKER = 'localhost:9092'  # On host machine

def delivery_report(err, msg):
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')

def inject_mock_threat():
    p = Producer({'bootstrap.servers': KAFKA_BROKER})
    
    # ── Mock Toxic Text Event ──
    text_data = {
        'content_id': f'mock_text_{int(time.time())}',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'platform': 'mock_test',
        'content_type': 'text',
        'content': 'I am going to kill you and your family you fat pig.',
        'author_username': 'test_adversary'
    }
    
    print("Injecting Mock TOXIC TEXT...")
    p.produce('social-media-feed', json.dumps(text_data).encode('utf-8'), callback=delivery_report)
    
    # ── Mock Phishing Event (Suspicious Domain) ──
    phish_data = {
        'content_id': f'mock_phish_url_{int(time.time())}',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'platform': 'mock_test',
        'content_type': 'text',
        'content': 'Major update required! Visit: http://secure-session-92837.xyz/verify for more info.',
        'author_username': 'alert_bot'
    }

    print("Injecting Mock URL PHISHING...")
    p.produce('social-media-feed', json.dumps(phish_data).encode('utf-8'), callback=delivery_report)




    
    p.flush()
    print("Mock alerts injected successfully.")

if __name__ == '__main__':
    inject_mock_threat()
