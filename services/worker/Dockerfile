FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git docker.io build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services/worker ./services/worker
COPY apps/api ./apps/api

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/packages:/app/services/worker
WORKDIR /app/services/worker

CMD ["arq", "worker.WorkerSettings"]