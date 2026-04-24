import os
import json
import logging
import time
from datetime import datetime
from confluent_kafka import Consumer, KafkaError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from models import Base, Alert

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:29092')
KAFKA_TOPIC = 'processed_alerts'
KAFKA_GROUP_ID = 'alert-persistence-group'

DB_USER = os.environ.get('DB_USER', 'socguard_user')
DB_PASS = os.environ.get('DB_PASS', 'socguard_password')
DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_NAME = os.environ.get('DB_NAME', 'socguard_db')
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

# Database Setup
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def wait_for_db():
    """Wait for the database to be ready."""
    max_retries = 30
    for i in range(max_retries):
        try:
            engine.connect()
            logger.info("Connected to database.")
            return
        except Exception as e:
            logger.warning(f"Database not ready yet, retrying in 2 seconds... ({i+1}/{max_retries})")
            time.sleep(2)
    raise Exception("Could not connect to database after multiple retries.")

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(engine)
    logger.info("Database tables initialized.")

def finalize_alert(data):
    """Process incoming alert data and generate reasoning if missing."""
    score = float(data.get('severity_score', 0.0))
    reasoning = data.get('reasoning')

    if not reasoning:
        if score > 90:
            reasoning = "CRITICAL: High-confidence detection matching known threat signatures."
        elif score > 75:
            reasoning = "WARNING: Suspicious patterns detected. Manual review recommended."
        elif score < 50:
            reasoning = "INFO: Low-risk anomaly detected."
        else:
            reasoning = "Medium risk activity detected."
    
    data['reasoning'] = reasoning
    return data

def process_message(msg_value, session):
    """Process a single Kafka message and save to DB."""
    try:
        data = json.loads(msg_value)
        logger.info(f"Received alert: {data.get('content_id')}")

        finalized_data = finalize_alert(data)

        # Parse timestamp if it's a string
        timestamp_str = finalized_data.get('timestamp')
        if isinstance(timestamp_str, str):
            try:
                # Attempt to parse ISO format
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                # Fallback to current time if parsing fails
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        alert = Alert(
            content_id=finalized_data.get('content_id'),
            timestamp=timestamp,
            platform=finalized_data.get('platform', 'unknown'),
            threat_category=finalized_data.get('threat_category', 'unknown'),
            severity_score=finalized_data.get('severity_score', 0.0),
            reasoning=finalized_data.get('reasoning'),
            original_url=finalized_data.get('original_url'),
            audio_url=finalized_data.get('audio_url'),
            content_type=finalized_data.get('content_type'),
            original_text=finalized_data.get('original_text'),
            explanation_image=finalized_data.get('explanation_image'),
            author=finalized_data.get('author_username'),
            is_resolved=finalized_data.get('is_resolved', False)
        )

        session.add(alert)
        session.commit()
        logger.info(f"Alert saved: {alert.content_id}")

    except IntegrityError:
        session.rollback()
        logger.warning(f"Duplicate alert detected: {data.get('content_id')}. Skipping.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing message: {e}")

def main():
    wait_for_db()
    init_db()

    consumer_conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': KAFKA_GROUP_ID,
        'auto.offset.reset': 'earliest'
    }

    consumer = Consumer(consumer_conf)
    consumer.subscribe([KAFKA_TOPIC])

    logger.info(f"Listening for alerts on topic '{KAFKA_TOPIC}'...")

    session = Session()

    try:
        while True:
            msg = consumer.poll(1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

            process_message(msg.value().decode('utf-8'), session)

    except KeyboardInterrupt:
        logger.info("Stopping consumer...")
    finally:
        session.close()
        consumer.close()

if __name__ == "__main__":
    main()
