import json
import logging
import os
import asyncio
from dotenv import load_dotenv
from confluent_kafka import Producer

# Connectors
from connectors.telegram_connector import start_telegram_listener
from connectors.bluesky_connector import start_bluesky_listener
from connectors.email_connector import start_email_listener

# Logging Config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load Env
load_dotenv()

# Kafka Producer Config
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'localhost:9092')
conf = {
    'bootstrap.servers': KAFKA_BROKER,
    'client.id': 'ingestion-producer',
    'message.max.bytes': 10485760
}

producer = None
try:
    producer = Producer(conf)
    logger.info(f"Connected to Kafka at {KAFKA_BROKER}")
except Exception as e:
    logger.error(f"Failed to connect to Kafka: {e}")

def delivery_report(err, msg):
    if err is not None:
        logger.error(f'Message delivery failed: {err}')
    else:
        # logger.debug(f'Message delivered to {msg.topic()} [{msg.partition()}]')
        pass

def produce_to_kafka(data):
    """
    Publishes a dictionary as a JSON message to the 'social-media-feed' topic.
    """
    if not producer:
        return

    try:
        # Topic name
        topic = 'social-media-feed'
        
        # Serialize
        val = json.dumps(data).encode('utf-8')
        
        # Produce
        logger.info(f"★★★ PRODUCING TO KAFKA: [{topic}] PLATFORM: {data.get('platform')} ★★★")
        producer.produce(topic, val, callback=delivery_report)

        producer.flush(timeout=1.0) # Force delivery for immediate real-time ingest
        
    except Exception as e:
        logger.error(f"Failed to produce message: {e}")

async def main():
    logger.info("Starting Connected Ingestion Service (Async Orchestrator)...")
    
    loop = asyncio.get_running_loop()
    
    # Define tasks
    tasks = [
        # Telegram manages its own loop via blocking calls, so we run it in an executor
        loop.run_in_executor(None, lambda: start_telegram_listener(callback=produce_to_kafka)),
        # Bluesky Listener (Real-time polling)
        loop.run_in_executor(None, lambda: start_bluesky_listener(callback=produce_to_kafka)),
        # Email Listener
        loop.run_in_executor(None, lambda: start_email_listener(callback=produce_to_kafka))
    ]
    
    # Wait for all
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopping Ingestion Service...")
        if producer:
            producer.flush()
