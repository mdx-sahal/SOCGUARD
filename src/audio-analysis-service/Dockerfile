FROM python:3.9-slim

WORKDIR /app

# System dependencies:
#   libsndfile1 — soundfile / librosa WAV I/O
#   ffmpeg      — librosa audio decoding (MP3, OGG, M4A, OPUS, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# Copy service files
COPY model.py .
COPY audio_analyzer.py .

CMD ["python", "audio_analyzer.py"]
