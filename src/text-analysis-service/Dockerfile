FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (if any needed for torch/kafka)
# RUN apt-get update && apt-get install -y ...

COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

COPY text_analyzer.py .

CMD ["python", "text_analyzer.py"]
