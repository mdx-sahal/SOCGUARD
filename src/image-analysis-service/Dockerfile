FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (none needed for basic Pillow/Torch)
# RUN apt-get update && apt-get install -y ...

COPY requirements.txt .
# Install PyTorch CPU first to avoid downloading huge CUDA wheels
RUN pip install --default-timeout=1000 --no-cache-dir torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

COPY image_analyzer.py .

CMD ["python", "image_analyzer.py"]
