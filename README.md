# SOCGUARD Infrastructure

This repository contains the infrastructure setup for the SOCGUARD real-time threat detection system.

## Prerequisites

- Docker
- Docker Compose

## Directory Structure

```
/
├── docker-compose.yml      # Main infrastructure definition
├── docker/
│   └── scripts/
│       └── init-kafka.sh   # Script to initialize Kafka topics
└── src/                    # Source code placeholders
    ├── ingestion-service
    ├── text-analysis-service
    ├── image-analysis-service
    ├── audio-analysis-service
    ├── backend-api
    └── frontend
```

## Getting Started

1.  **Start the infrastructure:**

    ```bash
    docker-compose up -d
    ```

    This will start Zookeeper, Kafka, Postgres, and Kafka UI. It will also run the `init-kafka` container to create the required topics.

2.  **Verify Services:**

    - **Kafka UI**: Open [http://localhost:8080](http://localhost:8080) to view the Kafka cluster and topics. You should see `raw_text`, `raw_image`, `raw_audio`, `raw_metadata`, and `processed_alerts`.
    - **Postgres**: Accessible on port 5432. Credentials are in `docker-compose.yml`.

3.  **Stop the infrastructure:**

    ```bash
    docker-compose down
    ```

## Services

- **Zookeeper**: Port 2181
- **Kafka**: Port 9092
- **Postgres**: Port 5432
- **Kafka UI**: Port 8080

## Next Steps

- Implement the microservices in the `src/` directories.
- Uncomment the services in `docker-compose.yml` as you add Dockerfiles to them.
