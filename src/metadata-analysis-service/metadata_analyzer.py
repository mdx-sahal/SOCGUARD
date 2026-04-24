import json
import logging
import os
import time
from datetime import datetime
from confluent_kafka import Consumer, Producer, KafkaError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Kafka Configuration
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:29092')
INPUT_TOPIC = 'social-media-feed'
OUTPUT_TOPIC = 'processed_alerts'
GROUP_ID = 'metadata-analysis-group-v2'


def calculate_bot_score(data):
    """
    Calculates a heuristic 'Bot Score' based on account metadata.
    Works with the actual fields sent by our ingestion connectors:
    - is_bot (from Telegram API)
    - is_verified
    - author_username
    - account_age_days (if available)
    - followers_count, following_count, posts_count (if available)
    
    Returns: score (0-100), reasons (list of strings)
    """
    score = 0
    reasons = []

    # ── Extract available features ──
    is_bot = data.get('is_bot', False)
    is_verified = data.get('is_verified', False)
    username = data.get('author_username', '')
    platform = data.get('platform', 'unknown')
    account_age_days = data.get('account_age_days')
    followers = data.get('followers_count')
    following = data.get('following_count')
    posts = data.get('posts_count')

    # ── 1. Telegram Bot Flag (Direct API indicator) ──
    if is_bot:
        score += 90
        reasons.append("Account flagged as automated bot by platform API")

    # ── 2. Verification Check (trusted accounts) ──
    if is_verified:
        # Verified accounts get a significant score reduction
        score = max(0, score - 50)
        reasons.append("Account is verified — reduced suspicion")
        if score == 0:
            return 0, ["Account is verified by the platform"]

    # ── 3. Username Pattern Analysis ──
    if username:
        username_lower = username.lower()

        # Bot-like username patterns: random strings, numbers at end
        digit_count = sum(1 for c in username if c.isdigit())
        digit_ratio = digit_count / len(username) if len(username) > 0 else 0

        if digit_ratio > 0.5 and len(username) > 8:
            score += 25
            reasons.append(f"Username contains high digit ratio ({digit_ratio:.0%}): '{username}'")

        # Check for generic bot name patterns
        bot_patterns = ['bot', '_auto', 'spam', 'promo', 'marketing', 'news_feed']
        for pattern in bot_patterns:
            if pattern in username_lower:
                score += 20
                reasons.append(f"Username contains bot-like pattern: '{pattern}'")
                break

        # Extremely short or single-character usernames
        if len(username) <= 2:
            score += 15
            reasons.append(f"Suspiciously short username: '{username}'")

    # ── 4. Account Age (if available) ──
    if account_age_days is not None:
        if account_age_days < 3:
            score += 40
            reasons.append(f"Extremely new account ({account_age_days} days old)")
        elif account_age_days < 30:
            score += 20
            reasons.append(f"New account ({account_age_days} days old)")

    # ── 5. Follower/Following Ratio (if available) ──
    if followers is not None and following is not None and following > 0:
        ratio = followers / following
        if following > 100 and ratio < 0.1:
            score += 30
            reasons.append(f"Suspicious follower ratio ({ratio:.2f})")

    # ── 6. Post Frequency (if available) ──
    if posts is not None and account_age_days is not None and account_age_days > 0:
        post_frequency = posts / account_age_days
        if post_frequency > 50:
            score += 40
            reasons.append(f"Inhuman post frequency ({post_frequency:.1f} posts/day)")
        elif post_frequency > 20:
            score += 20
            reasons.append(f"High post frequency ({post_frequency:.1f} posts/day)")

    # ── 7. Missing Author/Anonymous ──
    if not username or username in ('Unknown', 'anonymous', ''):
        score += 15
        reasons.append("No identifiable author/username")

    # Cap score at 100
    score = min(score, 100)

    # If no reasons were triggered, account looks normal
    if not reasons:
        reasons.append("No suspicious account indicators detected")

    return score, reasons


def delivery_report(err, msg):
    if err is not None:
        logger.error(f'Message delivery failed: {err}')
    else:
        logger.debug(f'Alert delivered to {msg.topic()}')


def main():
    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': GROUP_ID,
        'auto.offset.reset': 'earliest'
    })
    consumer.subscribe([INPUT_TOPIC])

    producer = Producer({'bootstrap.servers': KAFKA_BROKER})

    logger.info(f"Metadata Analysis Service (Bot Scorer) started. Listening on {INPUT_TOPIC}...")

    try:
        while True:
            msg = consumer.poll(1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                elif msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    logger.warning(f"Topic not ready yet: {msg.error()}")
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                    time.sleep(1)
                    continue

            try:
                data = json.loads(msg.value().decode('utf-8'))

                content_id = data.get('content_id')
                if not content_id:
                    continue

                # Analyze ALL messages for bot characteristics
                # The bot scorer works on account metadata embedded in every message
                score, reasons = calculate_bot_score(data)

                # Assign formal threat categories
                if score >= 70:
                    threat_category = "Confirmed Bot Account"
                elif score >= 40:
                    threat_category = "Suspected Bot Account"
                else:
                    threat_category = "Legitimate Account"

                severity = score if score >= 40 else 0
                reasoning_text = f"Bot Score: {score}/100. {'; '.join(reasons)}"

                logger.info(f"[{content_id}] {threat_category} (score={score}): {', '.join(reasons[:2])}")

                # Only produce alerts for suspicious accounts
                if severity > 0:
                    alert = {
                        "content_id": f"{content_id}_metadata",
                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        "platform": data.get('platform', 'unknown'),
                        "content_type": "metadata",
                        "threat_category": threat_category,
                        "severity_score": severity,
                        "reasoning": reasoning_text,
                        "author_username": data.get('author_username'),
                        "original_text": data.get('content', ''),
                        "original_url": data.get('original_url'),
                        "explanation_image": None
                    }

                    producer.produce(
                        OUTPUT_TOPIC,
                        key=alert["content_id"],
                        value=json.dumps(alert),
                        callback=delivery_report
                    )
                    producer.poll(0)
                    logger.info(f"Bot alert published for {content_id}")

            except Exception as e:
                logger.error(f"Error processing message: {e}")

    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        producer.flush()
        logger.info("Metadata Analysis Service stopped.")


if __name__ == "__main__":
    main()
