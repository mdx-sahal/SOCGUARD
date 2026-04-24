FROM python:3.9-slim-bullseye

WORKDIR /app

# We rely on binary wheels for confluent-kafka and psycopg2-binary
# to avoid installing system dependencies via apt-get (which is timing out).
# If wheels are missing, this will fail.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "persistence.py"]
