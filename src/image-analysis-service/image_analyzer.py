import json
import logging
import time
import requests
import os
import io
import torch
import numpy as np
import base64
from PIL import Image
from confluent_kafka import Consumer, Producer, KafkaError
from lime import lime_image
from skimage.segmentation import mark_boundaries
from transformers import pipeline

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Kafka Configuration
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:29092')
INPUT_TOPIC = 'social-media-feed'
OUTPUT_TOPIC = 'processed_alerts'
GROUP_ID = 'image-analysis-group'

# Initialize Model
# Priority: use locally fine-tuned model if available, otherwise fallback to public model.
LOCAL_MODEL_PATH = "./fine_tuned_model"
PUBLIC_MODEL_NAME = "prithivMLmods/Deep-Fake-Detector-v2-Model"

# Model state — loaded in background to prevent cold-start blocking
pipe = None
_model_ready = threading.Event()

def load_model():
    global pipe
    logger.info("Loading Deepfake Detection Model (background)...")
    t0 = time.time()
    if os.path.exists(LOCAL_MODEL_PATH):
        try:
            pipe = pipeline("image-classification", model=LOCAL_MODEL_PATH, device=-1)
            logger.info(f"Local ViT model loaded in {time.time()-t0:.1f}s")
        except Exception as e:
            logger.error(f"Local model load failed: {e}")
            raise
    else:
        logger.error(f"No local model found at {LOCAL_MODEL_PATH}. Exiting.")
        raise FileNotFoundError(f"Local model not found at {LOCAL_MODEL_PATH}")
    _model_ready.set()

# LIME explainer — lazy initialized
_explainer = None

def get_explainer():
    global _explainer
    if _explainer is None:
        _explainer = lime_image.LimeImageExplainer()
    return _explainer

def lime_predict_wrapper(images):
    """
    Wrapper for LIME.
    images: Numpy array of images (N, H, W, C)
    Returns: Probabilities (N, num_classes)
    """
    # The pipeline expects PIL images or paths.
    # Convert numpy images back to PIL
    pil_images = [Image.fromarray(img.astype('uint8')) for img in images]
    
    # Run batch inference
    results = pipe(pil_images, top_k=2) # Returns list of lists
    
    # Convert results to matrix
    # Result format: [[{'label': 'REAL', 'score': 0.9}, ...], ...]
    probs = []
    for res in results:
        p_real = 0.0
        p_fake = 0.0
        for item in res:
            label_upper = item['label'].upper()
            if 'REAL' in label_upper:
                p_real = item['score']
            elif 'FAKE' in label_upper or 'AI' in label_upper:
                p_fake = item['score']
        
        # Normalize to ensure sum is 1.0 (LIME requirement)
        total = p_real + p_fake
        if total > 0:
            probs.append([p_real/total, p_fake/total])
        else:
            probs.append([0.5, 0.5]) 
        
    return np.array(probs)

def generate_explanation(pil_image):
    """
    Generates a LIME explanation overlay. Uses lazy-loaded explainer.
    """
    try:
        np_img = np.array(pil_image)
        explainer = get_explainer()

        explanation = explainer.explain_instance(
            np_img,
            lime_predict_wrapper,
            top_labels=1,
            hide_color=0,
            num_samples=50,    # kept low for speed; increase to 200 for better quality
        )
        
        temp, mask = explanation.get_image_and_mask(
            explanation.top_labels[0], 
            positive_only=True, 
            num_features=5, 
            hide_rest=False
        )
        
        img_boundry = mark_boundaries(temp / 255.0, mask)
        explanation_pil = Image.fromarray((img_boundry * 255).astype(np.uint8))
        
        buffered = io.BytesIO()
        explanation_pil.save(buffered, format="JPEG")
        return "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode('utf-8')
        
    except Exception as e:
        logger.error(f"Failed to generate explanation: {e}")
        return None

def analyze_image(image_url):
    """
    Downloads and analyzes image for deepfake signs.
    Waits up to 5s for model to be ready if still loading.
    """
    if not _model_ready.wait(timeout=5):
        return "Pending", 0, "Model still loading, message will be retried", None
    if not pipe:
        return "Error", 0, "Model not initialized", None

    explanation_image = None
    
    # 1. Download or Decode
    try:
        if image_url.startswith('data:image/'):
            header, encoded = image_url.split(",", 1)
            image_data = base64.b64decode(encoded)
            image = Image.open(io.BytesIO(image_data)).convert('RGB')
        else:
            response = requests.get(image_url, timeout=5)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert('RGB')
    except Exception as e:
        return "Error", 0, f"Image fetch/decode failed: {str(e)}", None

    threat_label = "Authentic Image"
    severity = 0
    reasoning = "Image classified as Authentic by Vision Transformer model."

    # 2. Deepfake Check
    # We prioritize severity across models.
    try:
        results = pipe(image) 
        logger.info(f"Deepfake Prediction Raw: {results}")
        
        # Detect if model is the fine-tuned one with specific binary labels
        # Assuming our fine-tuned model has labels like 'REAL' and 'FAKE'
        
        fake_score = 0.0
        real_score = 0.0
        
        for res in results:
            label_upper = res['label'].upper()
            if 'FAKE' in label_upper or 'AI' in label_upper:
                fake_score = res['score']
            elif 'REAL' in label_upper:
                real_score = res['score']
        
        logger.info(f"Scores - Fake: {fake_score:.4f}, Real: {real_score:.4f}")

        # Confidence gate: if the margin between fake/real is too small, model is
        # uncertain — suppress alert to avoid noise from borderline Bluesky images.
        CONFIDENCE_GAP = 0.15
        FAKE_THRESHOLD  = 0.60

        confidence_margin = abs(fake_score - real_score)
        deepfake_severity = 0
        df_label = "Authentic Image"

        if fake_score > FAKE_THRESHOLD and confidence_margin >= CONFIDENCE_GAP:
            deepfake_severity = int(fake_score * 100)
            if fake_score > 0.80:
                df_label = "Confirmed Deepfake Image"
            else:
                df_label = "Suspected Deepfake Image"
        elif fake_score > FAKE_THRESHOLD and confidence_margin < CONFIDENCE_GAP:
            logger.info(f"Uncertain prediction (gap={confidence_margin:.3f} < {CONFIDENCE_GAP}). Suppressing alert.")

        # Determine Winner
        if deepfake_severity > severity:
            threat_label = df_label
            severity = deepfake_severity
            reasoning = (
                f"Image classified as {df_label} by Vision Transformer "
                f"(Fake: {fake_score:.1%}, Real: {real_score:.1%}, Gap: {confidence_margin:.1%})"
            )

            # XAI: Only for high-confidence deepfakes (>80%) to avoid LIME latency
            if severity > 80:
                logger.info(f"Generating LIME explanation for {threat_label}...")
                try:
                    explanation_image = generate_explanation(image)
                except Exception as e:
                    logger.error(f"LIME failed: {e}")
             
    except Exception as e:
        logger.error(f"Deepfake Inference failed: {e}")
        if severity == 0:
             return "Error", 0, f"Inference error: {str(e)}", None


    return threat_label, severity, reasoning, explanation_image

def create_consumer():
    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': GROUP_ID,
        'auto.offset.reset': 'earliest',
        'fetch.message.max.bytes': 10485760
    })
    consumer.subscribe([INPUT_TOPIC])
    return consumer

def create_producer():
    return Producer({
        'bootstrap.servers': KAFKA_BROKER,
        'message.max.bytes': 10485760
    })

def delivery_report(err, msg):
    if err is not None:
        logger.error(f'Message delivery failed: {err}')
    else:
        logger.debug(f'Alert delivered to {msg.topic()}')

def main():
    import threading
    threading.Thread(target=load_model, daemon=True, name="load-vit").start()

    # Wait for model before consuming from Kafka
    logger.info("Waiting for ViT model to load...")
    _model_ready.wait()
    logger.info("ViT model ready. Connecting to Kafka...")

    consumer = create_consumer()
    producer = create_producer()

    logger.info(f"Image Analysis Service started. Listening on {INPUT_TOPIC}...")

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
                    logger.error(msg.error())
                    time.sleep(1)
                    continue

            try:
                data = json.loads(msg.value().decode('utf-8'))
                
                # VERBOSE LOGGING FOR ALL MESSAGES
                platform = data.get('platform', 'unknown')
                content_type = data.get('content_type', 'text')
                logger.info(f"--- MSG CHECK: [{platform}] --- Type: {content_type}")

                image_url = data.get('image_url')

                
                if not image_url:
                    continue

                logger.info(f"Processing image: {image_url}")
                
                start_time = time.time()
                threat_label, severity, reasoning, explanation_image = analyze_image(image_url)
                duration = time.time() - start_time
                logger.info(f"Analysis took {duration:.2f}s")

                # Filter out Safe/Real images
                # if severity == 0 or "Real" in threat_label:
                #    logger.info(f"Image is safe ({threat_label}). Skipping alert.")
                #    producer.poll(0)
                #    continue

                alert = {
                    "content_id": f"{data.get('content_id')}_image",
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "original_url": image_url,
                    "platform": data.get('platform', 'unknown'),
                    "threat_category": threat_label,
                    "severity_score": severity,
                    "reasoning": reasoning,
                    "explanation_image": explanation_image,
                    "author_username": data.get('author_username'),
                    "original_text": data.get('content')
                }

                producer.produce(
                    OUTPUT_TOPIC,
                    key=data.get('content_id'),
                    value=json.dumps(alert),
                    callback=delivery_report
                )
                producer.poll(0)

            except Exception as e:
                logger.error(f"Error processing message: {e}")

    except KeyboardInterrupt:
        logger.info("Stopping service...")
    finally:
        consumer.close()
        producer.flush()

if __name__ == '__main__':
    main()
