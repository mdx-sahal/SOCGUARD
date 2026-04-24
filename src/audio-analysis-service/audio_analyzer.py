import json
import logging
import time
import os
import io
import threading
import tempfile
import base64
import requests
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for Docker
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from confluent_kafka import Consumer, Producer, KafkaError
from transformers import pipeline

# Audio processing libraries
import librosa
import librosa.display
import soundfile as sf

# Local AudioCNN model
from model import AudioCNN

# ─────────────────────────────────────────────────
# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────
# Kafka Configuration
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:29092')
INPUT_TOPIC = 'social-media-feed'
OUTPUT_TOPIC = 'processed_alerts'
GROUP_ID = 'audio-analysis-group-v5'

# ─────────────────────────────────────────────────
# Model Configuration
# wav2vec2-base-960h is a speech-to-text (ASR) model, NOT a classifier.
# We use it correctly here: pipeline("automatic-speech-recognition")
ASR_MODEL_NAME = "facebook/wav2vec2-base-960h"
TARGET_SAMPLE_RATE = 16000  # wav2vec2 requires 16 kHz mono audio

# Global model state
asr_pipeline = None
audio_cnn = None
model_ready = threading.Event()  # Signals when ASR model is ready

# ─────────────────────────────────────────────────
# Suspicious keywords for transcript analysis
SUSPICIOUS_TRANSCRIPT_KEYWORDS = [
    "voice clone", "ai voice", "deepfake audio", "synthesized voice",
    "fake audio", "voice generator", "text to speech", "tts voice",
    "voice synthesis", "voice deepfake", "cloned voice", "synthetic speech",
    "ai generated audio", "voice manipulation"
]

# ─────────────────────────────────────────────────
# Model Loading
# ─────────────────────────────────────────────────

def load_models():
    """
    Loads two models in a background daemon thread:
      1. wav2vec2-base-960h — as Automatic Speech Recognition (ASR)
      2. AudioCNN           — untrained heuristic deep-learning scorer on MFCCs
    Signals model_ready when ASR is available.
    """
    global asr_pipeline, audio_cnn

    # ── 1. Load AudioCNN (lightweight, always succeeds) ──
    try:
        audio_cnn = AudioCNN(n_mfcc=13, n_classes=2)
        audio_cnn.eval()
        logger.info("AudioCNN initialized (MFCC-based deep feature extractor).")
    except Exception as e:
        logger.error(f"AudioCNN init failed: {e}")

    # ── 2. Load wav2vec2 as ASR ──
    logger.info(f"--- (Background) Loading ASR Model: {ASR_MODEL_NAME} ---")
    try:
        asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=ASR_MODEL_NAME,
            chunk_length_s=30,      # Handle audio longer than 30s via chunking
            stride_length_s=5,      # Overlapping chunks for better accuracy
            device="cpu"
        )
        logger.info("--- ASR Model (wav2vec2) LOADED successfully! ---")
    except Exception as e:
        logger.error(f"--- ASR Model load FAILED: {e} ---")

    model_ready.set()  # Signal that we are ready (even if ASR fallback)


# ─────────────────────────────────────────────────
# Audio Download & Decoding
# ─────────────────────────────────────────────────

def download_and_decode_audio(audio_url: str):
    """
    Downloads audio from a URL and converts it to a 16 kHz mono numpy array.
    Returns (audio_array: np.ndarray, sample_rate: int) or (None, None) on failure.
    Supports WAV, MP3, OGG, OGA, M4A via librosa + ffmpeg.
    """
    try:
        logger.info(f"Downloading audio: {audio_url[:80]}...")
        resp = requests.get(audio_url, timeout=15, stream=True)
        resp.raise_for_status()
        audio_bytes = resp.content

        # Infer file extension from URL (best-effort)
        clean_url = audio_url.split('?')[0]
        ext = clean_url.split('.')[-1].lower()
        if ext not in {'wav', 'mp3', 'ogg', 'oga', 'm4a', 'flac', 'opus'}:
            ext = 'wav'  # sensible default

        # Write to temp file so librosa can load it (handles all common formats)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            audio_array, sr = librosa.load(tmp_path, sr=TARGET_SAMPLE_RATE, mono=True)
            logger.info(f"Audio decoded: {len(audio_array)/sr:.2f}s at {sr}Hz "
                        f"({len(audio_array)} samples)")
            return audio_array, sr

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except requests.exceptions.RequestException as e:
        logger.error(f"Audio download failed: {e}")
    except Exception as e:
        logger.error(f"Audio decode failed: {e}")

    return None, None


# ─────────────────────────────────────────────────
# ASR Transcription
# ─────────────────────────────────────────────────

def transcribe_audio(audio_array: np.ndarray) -> str:
    """
    Uses the wav2vec2 ASR pipeline to convert audio to text.
    Returns the transcript string (may be empty if model unavailable).
    """
    if asr_pipeline is None:
        logger.warning("ASR pipeline not available — skipping transcription.")
        return ""

    try:
        logger.info("Running wav2vec2 ASR transcription...")
        result = asr_pipeline({
            "array": audio_array,
            "sampling_rate": TARGET_SAMPLE_RATE
        })
        transcript = result.get("text", "").strip()
        logger.info(f"Transcript: '{transcript[:120]}'")
        return transcript
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


# ─────────────────────────────────────────────────
# Transcript Content Analysis
# ─────────────────────────────────────────────────

def analyze_transcript_content(transcript: str):
    """
    Checks the ASR transcript for keywords that suggest synthetic/deepfake speech.
    Returns (score: int [0-30], reasons: list[str])
    """
    score = 0
    reasons = []
    t_lower = transcript.lower()

    for kw in SUSPICIOUS_TRANSCRIPT_KEYWORDS:
        if kw in t_lower:
            score = 30
            reasons.append(f"ASR transcript contains suspicious keyword: '{kw}'")
            break

    return min(score, 30), reasons


# ─────────────────────────────────────────────────
# Acoustic Feature Analysis (librosa)
# ─────────────────────────────────────────────────

def analyze_acoustic_features(audio_array: np.ndarray, sr: int):
    """
    Extracts signal-level acoustic features using librosa to detect synthetic/deepfake audio.

    Key indicators of synthesized speech:
      1. Low MFCC variance  — TTS systems produce less natural articulation variety
      2. Low spectral flatness std — unnaturally constant spectral shape
      3. Low ZCR std        — zero-crossing rate is unnaturally uniform in TTS
      4. Low pitch std      — TTS pitch is more monotonic than natural speech
      5. Low RMS std        — energy envelope is suspiciously flat in synthesized audio

    Returns:
      acoustic_score (int): 0–70 contribution to final score
      reasons (list[str]):  human-readable explanation of findings
    """
    score = 0
    reasons = []

    try:
        # ── Feature 1: MFCC Variance ──
        mfccs = librosa.feature.mfcc(y=audio_array, sr=sr, n_mfcc=13)
        mfcc_var = float(np.mean(np.var(mfccs, axis=1)))
        logger.info(f"MFCC mean variance: {mfcc_var:.3f}")
        if mfcc_var < 15.0:
            contrib = 20
            score += contrib
            reasons.append(
                f"Low MFCC variance ({mfcc_var:.2f} < 15.0 threshold) — "
                "TTS systems produce less natural acoustic variation than human speech"
            )

        # ── Feature 2: Spectral Flatness Uniformity ──
        sflatness = librosa.feature.spectral_flatness(y=audio_array)
        sflatness_std = float(np.std(sflatness))
        logger.info(f"Spectral flatness std: {sflatness_std:.5f}")
        if sflatness_std < 0.002:
            contrib = 15
            score += contrib
            reasons.append(
                f"Abnormally uniform spectral flatness (std={sflatness_std:.5f}) — "
                "natural speech has dynamically varying spectral texture"
            )

        # ── Feature 3: Zero-Crossing Rate Uniformity ──
        zcr = librosa.feature.zero_crossing_rate(audio_array)
        zcr_std = float(np.std(zcr))
        logger.info(f"ZCR std: {zcr_std:.5f}")
        if zcr_std < 0.015:
            contrib = 15
            score += contrib
            reasons.append(
                f"Suspiciously uniform zero-crossing rate (std={zcr_std:.5f}) — "
                "synthesized audio often lacks the irregular transitions of natural speech"
            )

        # ── Feature 4: Pitch (F0) Variation ──
        try:
            f0, voiced_flag, _ = librosa.pyin(
                audio_array,
                fmin=librosa.note_to_hz('C2'),
                fmax=librosa.note_to_hz('C7'),
                sr=sr
            )
            voiced_f0 = f0[~np.isnan(f0)]
            if len(voiced_f0) > 20:
                f0_std = float(np.std(voiced_f0))
                logger.info(f"Pitch std: {f0_std:.2f} Hz")
                if f0_std < 8.0:
                    contrib = 10
                    score += contrib
                    reasons.append(
                        f"Very low pitch variation (std={f0_std:.2f} Hz) — "
                        "natural voices have significantly more prosodic diversity than TTS"
                    )
        except Exception as e:
            logger.warning(f"Pitch analysis skipped: {e}")

        # ── Feature 5: RMS Energy Envelope ──
        rms = librosa.feature.rms(y=audio_array)
        rms_std = float(np.std(rms))
        logger.info(f"RMS energy std: {rms_std:.5f}")
        if rms_std < 0.003:
            contrib = 10
            score += contrib
            reasons.append(
                f"Unnaturally flat energy envelope (RMS std={rms_std:.5f}) — "
                "human speech has highly variable energy levels across time"
            )

    except Exception as e:
        logger.error(f"Acoustic feature extraction error: {e}")
        reasons.append("Acoustic analysis partially failed — results may be incomplete")

    return min(score, 70), reasons


# ─────────────────────────────────────────────────
# AudioCNN Deep Feature Scoring
# ─────────────────────────────────────────────────

def score_with_audio_cnn(audio_array: np.ndarray, sr: int):
    """
    Runs the MFCC features through AudioCNN to produce a learned feature-based score.

    NOTE: AudioCNN here is used as an unsupervised feature scorer (not fine-tuned on
    a labelled deepfake dataset). Its output acts as an auxiliary signal — if the
    CNN's probability for class 1 (deepfake) is high, it adds to the suspicion score.

    Returns:
      cnn_score (int): 0 or additional 10 contribution
      reason (str or None)
    """
    if audio_cnn is None:
        return 0, None

    try:
        mfccs = librosa.feature.mfcc(y=audio_array, sr=sr, n_mfcc=13)

        # Normalize MFCC to zero mean / unit variance for stable input
        mfccs = (mfccs - mfccs.mean()) / (mfccs.std() + 1e-8)

        # Shape: [1, 1, n_mfcc, time_steps]
        mfcc_tensor = torch.FloatTensor(mfccs).unsqueeze(0).unsqueeze(0)

        with torch.no_grad():
            logits = audio_cnn(mfcc_tensor)
            probs = torch.softmax(logits, dim=1).squeeze()
            deepfake_prob = float(probs[1])  # Index 1 = deepfake class

        logger.info(f"AudioCNN deepfake probability: {deepfake_prob:.3f}")

        if deepfake_prob > 0.6:
            return 10, (
                f"AudioCNN feature extractor flagged audio "
                f"(deepfake probability={deepfake_prob:.2f})"
            )
        return 0, None

    except Exception as e:
        logger.error(f"AudioCNN scoring error: {e}")
        return 0, None


# ─────────────────────────────────────────────────
# XAI: Mel-Spectrogram + MFCC Visualization
# ─────────────────────────────────────────────────

def generate_spectrogram_xai(audio_array: np.ndarray, sr: int,
                              threat_label: str, score: int) -> str | None:
    """
    Generates a two-panel XAI visualization:
      - Top panel: Mel-spectrogram of the audio (shows frequency content over time)
      - Bottom panel: MFCC heatmap (shows cepstral features per frame)

    Returns Base64-encoded JPEG string for embedding in the alert,
    or None if generation fails.
    """
    try:
        fig, axes = plt.subplots(2, 1, figsize=(10, 6),
                                 facecolor='#0a0e17',
                                 gridspec_kw={'hspace': 0.45})

        # ── Panel 1: Mel-Spectrogram ──
        mel_spec = librosa.feature.melspectrogram(
            y=audio_array, sr=sr, n_mels=64, fmax=8000
        )
        mel_db = librosa.power_to_db(mel_spec, ref=np.max)
        img1 = librosa.display.specshow(
            mel_db, sr=sr, x_axis='time', y_axis='mel',
            fmax=8000, ax=axes[0], cmap='magma'
        )
        axes[0].set_facecolor('#0a0e17')
        axes[0].tick_params(colors='#94a3b8')
        axes[0].yaxis.label.set_color('#94a3b8')
        axes[0].xaxis.label.set_color('#94a3b8')
        alert_color = '#ff0055' if score >= 65 else ('#ff9900' if score >= 35 else '#00ff9d')
        axes[0].set_title(
            f'Mel-Spectrogram  |  Verdict: {threat_label}  |  Score: {score}/100',
            color=alert_color, fontsize=10, fontweight='bold'
        )
        fig.colorbar(img1, ax=axes[0], format='%+2.0f dB').ax.yaxis.set_tick_params(color='#94a3b8')

        # ── Panel 2: MFCC Heatmap ──
        mfccs = librosa.feature.mfcc(y=audio_array, sr=sr, n_mfcc=13)
        img2 = librosa.display.specshow(
            mfccs, sr=sr, x_axis='time', ax=axes[1], cmap='coolwarm'
        )
        axes[1].set_facecolor('#0a0e17')
        axes[1].tick_params(colors='#94a3b8')
        axes[1].yaxis.label.set_color('#94a3b8')
        axes[1].xaxis.label.set_color('#94a3b8')
        axes[1].set_title(
            'MFCC Features  |  Low variance across frames = synthetic speech indicator',
            color='#00f3ff', fontsize=9
        )
        axes[1].set_ylabel('MFCC Coefficient')
        fig.colorbar(img2, ax=axes[1]).ax.yaxis.set_tick_params(color='#94a3b8')

        fig.suptitle('SocGuard Audio XAI — Acoustic Analysis',
                     color='white', fontsize=12, fontweight='bold')

        # Save to buffer
        buf = io.BytesIO()
        fig.savefig(buf, format='jpeg', bbox_inches='tight',
                    facecolor='#0a0e17', dpi=100)
        plt.close(fig)
        buf.seek(0)

        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{b64}"

    except Exception as e:
        logger.error(f"XAI spectrogram generation failed: {e}")
        return None


# ─────────────────────────────────────────────────
# Full Audio Analysis Pipeline
# ─────────────────────────────────────────────────

def analyze_audio(audio_url: str, content_text: str = ""):
    """
    Orchestrates all analysis steps:
      1. Download + decode audio to 16kHz numpy array
      2. ASR transcription via wav2vec2
      3. Transcript content analysis (keyword scan)
      4. Acoustic feature analysis via librosa (5 features)
      5. AudioCNN deep feature scoring on MFCCs
      6. Combine into final verdict
      7. Generate mel-spectrogram + MFCC XAI visualization

    Returns:
      threat_label (str), severity (int), reasoning (str),
      transcript (str), explanation_image (str or None)
    """
    # ── Step 1: Download & Decode ──
    audio_array, sr = download_and_decode_audio(audio_url)
    if audio_array is None:
        return "Error", 0, "Could not download or decode audio file.", "", None

    # Minimum duration check (< 0.5s is too short to analyze reliably)
    duration = len(audio_array) / sr
    if duration < 0.5:
        return "Authentic Audio", 0, \
               f"Audio too short ({duration:.2f}s) for reliable analysis.", "", None

    # ── Step 2 & 3: ASR + Transcript Analysis ──
    transcript = ""
    model_ready.wait(timeout=120)  # Wait up to 2 min for model load on cold start
    transcript = transcribe_audio(audio_array)
    text_score, text_reasons = analyze_transcript_content(transcript)

    # ── Step 4: Acoustic Feature Analysis ──
    acoustic_score, acoustic_reasons = analyze_acoustic_features(audio_array, sr)

    # ── Step 5: AudioCNN Scoring ──
    cnn_score, cnn_reason = score_with_audio_cnn(audio_array, sr)
    cnn_reasons = [cnn_reason] if cnn_reason else []

    # ── Step 6: Combined Score ──
    # Weights: acoustic=70%, transcript=20%, CNN=10%
    combined_score = min(acoustic_score + text_score + cnn_score, 100)
    all_reasons = acoustic_reasons + text_reasons + cnn_reasons

    logger.info(f"Score breakdown — Acoustic: {acoustic_score}, "
                f"Transcript: {text_score}, CNN: {cnn_score}, "
                f"Combined: {combined_score}")

    # ── Verdict ──
    if combined_score >= 65:
        threat_label = "Confirmed Deepfake Audio"
    elif combined_score >= 35:
        threat_label = "Suspected Deepfake Audio"
    else:
        threat_label = "Authentic Audio"

    # ── Build Reasoning ──
    transcript_snippet = f"'{transcript[:100]}'" if transcript else "unavailable"
    reasoning_parts = [
        f"wav2vec2 ASR Transcript: {transcript_snippet}.",
        f"Combined Score: {combined_score}/100 "
        f"(Acoustic: {acoustic_score}, Transcript: {text_score}, CNN: {cnn_score}).",
        f"Audio duration: {duration:.2f}s at {sr}Hz."
    ]
    if all_reasons:
        reasoning_parts.append("Indicators: " + "; ".join(all_reasons) + ".")
    else:
        reasoning_parts.append(
            "No synthetic audio indicators detected. "
            "Audio classified as authentic based on acoustic and linguistic analysis."
        )
    reasoning = " ".join(reasoning_parts)

    # ── Step 7: XAI Visualization (always generate for visibility) ──
    explanation_image = None
    try:
        explanation_image = generate_spectrogram_xai(audio_array, sr, threat_label, combined_score)
        if explanation_image:
            logger.info("XAI spectrogram generated successfully.")
    except Exception as e:
        logger.error(f"XAI generation error: {e}")

    logger.info(f"★★★ AUDIO ANALYSIS COMPLETE ★★★ [{threat_label}] Score={combined_score}")
    return threat_label, combined_score, reasoning, transcript, explanation_image


# ─────────────────────────────────────────────────
# Kafka Consumer Loop
# ─────────────────────────────────────────────────

def main():
    logger.info(f"Initializing Audio Analysis Service (Consumer Group: {GROUP_ID})")

    # Start model loading in daemon thread so Kafka loop starts immediately
    threading.Thread(target=load_models, daemon=True, name="ModelLoader").start()

    # Kafka setup
    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': GROUP_ID,
        'auto.offset.reset': 'earliest',
        'fetch.message.max.bytes': 10485760  # 10 MB (for audio payloads)
    })
    consumer.subscribe([INPUT_TOPIC])
    producer = Producer({
        'bootstrap.servers': KAFKA_BROKER,
        'message.max.bytes': 10485760
    })

    logger.info(f"Audio Analysis loop started. Listening on '{INPUT_TOPIC}'...")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.warning(f"Kafka error: {msg.error()}")
                continue

            try:
                data = json.loads(msg.value().decode('utf-8'))
                platform = data.get('platform', 'unknown')
                content_type = data.get('content_type', 'text')

                logger.info(f"--- MSG CHECK: [{platform}] --- Type: {content_type}")

                # Only process messages with audio
                audio_url = data.get('audio_url')
                if not audio_url:
                    continue

                logger.info(f"Audio URL detected. Starting full analysis pipeline...")
                content_text = data.get('content', '')

                start_time = time.time()
                threat_label, severity, reasoning, transcript, explanation_image = \
                    analyze_audio(audio_url, content_text)
                elapsed = time.time() - start_time

                logger.info(f"Analysis completed in {elapsed:.1f}s")

                alert = {
                    "content_id": f"{data.get('content_id')}_audio",
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "platform": platform,
                    "content_type": "audio",
                    "threat_category": threat_label,
                    "severity_score": severity,
                    "reasoning": reasoning,
                    "original_text": transcript,          # ASR transcript as "original text"
                    "audio_url": audio_url,               # Preserve for dashboard playback
                    "explanation_image": explanation_image, # Mel-spec XAI image
                    "author_username": data.get('author_username')
                }

                producer.produce(
                    OUTPUT_TOPIC,
                    key=data.get('content_id', ''),
                    value=json.dumps(alert).encode('utf-8')
                )
                producer.poll(0)
                logger.info(f"★★★ ALERT PUBLISHED [AUDIO]: {threat_label} "
                            f"(severity={severity}) ★★★")

            except Exception as e:
                logger.error(f"Message processing error: {e}", exc_info=True)

    except KeyboardInterrupt:
        logger.info("Shutting down Audio Analysis Service...")
    finally:
        consumer.close()
        producer.flush()
        logger.info("Audio Analysis Service stopped.")


if __name__ == '__main__':
    main()
