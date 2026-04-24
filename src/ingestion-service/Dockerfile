FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY connectors ./connectors
COPY producer.py .

CMD ["python", "producer.py"]
