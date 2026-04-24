#!/bin/bash

echo "Waiting for Kafka to be ready..."
until kafka-topics --bootstrap-server kafka:29092 --list > /dev/null 2>&1; do
  echo "  Kafka not ready yet, retrying in 3s..."
  sleep 3
done

echo "Kafka is ready. Creating topics..."

# social-media-feed: 3 partitions for parallel ingestion
# Use --if-not-exists so restarts are safe
kafka-topics --create --if-not-exists \
  --bootstrap-server kafka:29092 \
  --replication-factor 1 \
  --partitions 3 \
  --topic social-media-feed

# processed_alerts: 3 partitions for parallel persistence
kafka-topics --create --if-not-exists \
  --bootstrap-server kafka:29092 \
  --replication-factor 1 \
  --partitions 3 \
  --topic processed_alerts

# Legacy topics kept for compatibility
for topic in raw_text raw_image raw_audio raw_metadata; do
  kafka-topics --create --if-not-exists \
    --bootstrap-server kafka:29092 \
    --replication-factor 1 \
    --partitions 1 \
    --topic "$topic"
done

echo "Topic initialization complete."
kafka-topics --bootstrap-server kafka:29092 --list
