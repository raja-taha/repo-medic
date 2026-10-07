FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest ruff \
    && npm install -g jest eslint typescript

WORKDIR /workspace
CMD ["bash"]