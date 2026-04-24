import json
import logging
import time
import os
import re
import threading
import sys
from confluent_kafka import Consumer, Producer, KafkaError
from transformers import pipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Kafka Configuration
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:29092')
INPUT_TOPIC  = 'social-media-feed'
OUTPUT_TOPIC = 'processed_alerts'
GROUP_ID     = 'text-analysis-group-v6'

# ── Model state ──────────────────────────────────────────────────────────────
classifier          = None
phishing_classifier = None
_model_ready        = threading.Event()   # signals main loop when primary is up

# ── Performance: cache repeated content to avoid re-running inference ────────
_inference_cache: dict = {}
CACHE_MAX = 500


def _cache_get(text: str):
    return _inference_cache.get(text[:512])


def _cache_put(text: str, result):
    if len(_inference_cache) >= CACHE_MAX:
        # Drop oldest 100 entries
        for k in list(_inference_cache.keys())[:100]:
            del _inference_cache[k]
    _inference_cache[text[:512]] = result


def load_primary_model():
    """Load Toxic-BERT in a background thread so the process starts fast."""
    global classifier
    logger.info("Loading Toxic-BERT (martin-ha/toxic-comment-model)...")
    t0 = time.time()
    try:
        classifier = pipeline(
            "text-classification",
            model="martin-ha/toxic-comment-model",
            top_k=None,
            device=-1,          # CPU
        )
        logger.info(f"Toxic-BERT loaded in {time.time()-t0:.1f}s")
        _model_ready.set()
    except Exception as e:
        logger.critical(f"Primary model load FAILED: {e}")
        sys.exit(1)


def load_secondary_model():
    """Load phishing model in background after primary is ready."""
    global phishing_classifier
    _model_ready.wait()   # wait until primary is done first
    logger.info("Loading Phishing model (background)...")
    try:
        phishing_classifier = pipeline(
            "text-classification",
            model="ealvaradob/bert-finetuned-phishing",
            top_k=None,
            device=-1,
        )
        logger.info("Phishing model loaded.")
    except Exception as e:
        logger.error(f"Phishing model load FAILED: {e}")


# ── Threat patterns ──────────────────────────────────────────────────────────
THREAT_PATTERNS = {
    "Threatening Language": ["kill", "murder", "shoot", "stab", "bomb", "attack",
                             "destroy", "die", "death", "weapon"],
    "Hate Speech":          ["racist", "sexist", "homophob", "transphob", "slur", "supremac"],
    "Abusive Language":     ["idiot", "moron", "stupid", "dumb", "trash", "scum", "ugly"],
    "Harassment":           ["stalk", "harass", "bully", "dox", "find you", "leak", "ruin"],
    "Offensive Language":   [],
}

PHISHING_PATTERNS = [
    r"bit\.ly", r"tinyurl", r"goo\.gl", r"t\.co",
    r"login", r"verify", r"update-account",
    r"gift-card", r"prize", r"winner",
    r"unusual-activity", r"security-alert", r"click-here",
    r"secure-upd",                  # catches secure-update, secure-upd, etc.
    r"account.confirm",
]

TOXICITY_THRESHOLD = 0.65   # raised from 0.40 to cut false-positives


def analyze_text(text: str):
    """Returns (threat_label, severity_int, reasoning_str)."""
    if not classifier:
        return "Pending", 0, "Model loading — message will be reprocessed"

    content_key = text[:512]

    # ── Check inference cache ──────────────────────────────────────────────
    cached = _cache_get(content_key)
    if cached:
        return cached

    text_lower = text.lower()

    # ── Step 1: Phishing heuristic (fast path) ─────────────────────────────
    for kw in PHISHING_PATTERNS:
        if re.search(kw, text_lower):
            result = ("Phishing Link", 85,
                      f"Heuristic match: probable phishing pattern '{kw}'")
            _cache_put(content_key, result)
            return result

    # ── Step 2: ML phishing on extracted URLs ─────────────────────────────
    if phishing_classifier:
        urls = re.findall(r'(https?://[^\s>]+)', text)
        for url in urls:
            try:
                url_clean = url.strip(".,;:?!()[]{}'\"")[:512]
                results    = phishing_classifier(url_clean)[0]
                p_score    = max(
                    (r['score'] for r in results
                     if any(x in r['label'].upper() for x in ('LABEL_1', 'PHISH', 'SPAM'))),
                    default=0.0
                )
                if p_score > 0.65:
                    result = ("Phishing Link", int(p_score * 100),
                              f"AI phishing URL: {url_clean[:30]} ({p_score:.1%})")
                    _cache_put(content_key, result)
                    return result
            except Exception as e:
                logger.debug(f"URL phishing check error: {e}")

    # ── Step 3: Toxicity model ────────────────────────────────────────────
    try:
        t0          = time.time()
        raw_results = classifier(content_key)[0]
        elapsed     = time.time() - t0
        logger.info(f"Inference complete in {elapsed:.2f}s. Results: {raw_results}")

        toxic_score = max(
            (r['score'] for r in raw_results
             if r['label'].lower() in ('toxic', 'threat', 'insult',
                                       'severe_toxic', 'identity_hate')),
            default=0.0
        )

        if toxic_score > TOXICITY_THRESHOLD:
            category = "Offensive Language"
            for cat, keywords in THREAT_PATTERNS.items():
                if any(k in text_lower for k in keywords):
                    category = cat
                    break
            result = (category, int(toxic_score * 100),
                      f"Detected {category} (Score: {toxic_score:.1%})")
            _cache_put(content_key, result)
            return result

    except Exception as e:
        logger.error(f"Toxicity inference error: {e}")
        return "Error", 0, f"Analysis failed: {e}"

    result = ("Safe Content", 0, "No threats detected")
    _cache_put(content_key, result)
    return result


# ── Kafka helpers ─────────────────────────────────────────────────────────────
def make_consumer():
    return Consumer({
        'bootstrap.servers':        KAFKA_BROKER,
        'group.id':                 GROUP_ID,
        'auto.offset.reset':        'earliest',
        'enable.auto.commit':       True,
        'max.poll.interval.ms':     300000,
        'session.timeout.ms':       30000,
        'fetch.min.bytes':          1,
        'fetch.wait.max.ms':        500,
    })


def make_producer():
    return Producer({
        'bootstrap.servers':    KAFKA_BROKER,
        'linger.ms':            50,       # batch up to 50ms for throughput
        'compression.type':     'lz4',    # compress large alert payloads
        'acks':                 1,
    })


def delivery_cb(err, msg):
    if err:
        logger.error(f"Delivery failed: {err}")


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    logger.info(f"Text Analysis Service starting (group={GROUP_ID})")

    # Start model loading in background threads
    threading.Thread(target=load_primary_model,   daemon=True, name="load-primary").start()
    threading.Thread(target=load_secondary_model, daemon=True, name="load-secondary").start()

    # Wait for the primary model before setting up Kafka
    logger.info("Waiting for primary model to load...")
    _model_ready.wait()
    logger.info("Primary model ready. Connecting to Kafka...")

    consumer = make_consumer()
    producer  = make_producer()
    consumer.subscribe([INPUT_TOPIC])
    logger.info(f"Listening on topic: {INPUT_TOPIC}")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.warning(f"Kafka error: {msg.error()}")
                time.sleep(1)
                continue

            try:
                data     = json.loads(msg.value().decode('utf-8'))
                content  = data.get('content', '')
                platform = data.get('platform', 'unknown')

                if not content:
                    continue

                logger.info(f"Processing [{platform}]: {content[:60]}...")

                threat_label, severity, reasoning = analyze_text(content)

                # Only produce alerts for actual threats (severity > 0)
                if severity == 0 and threat_label == "Safe Content":
                    continue

                alert = {
                    "content_id":     f"{data.get('content_id')}_text",
                    "timestamp":      time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "original_text":  content,
                    "platform":       platform,
                    "threat_category": threat_label,
                    "severity_score": severity,
                    "reasoning":      reasoning,
                    "author_username": data.get('author_username'),
                }

                producer.produce(
                    OUTPUT_TOPIC,
                    key=str(data.get('content_id', '')),
                    value=json.dumps(alert).encode('utf-8'),
                    callback=delivery_cb,
                )
                producer.poll(0)   # non-blocking flush of pending callbacks

            except Exception as e:
                logger.error(f"Message processing error: {e}", exc_info=True)

    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        consumer.close()
        producer.flush(10)


if __name__ == '__main__':
    main()
