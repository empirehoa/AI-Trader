# Containerized autonomous loop. Build from the repo root:
#   docker build -f deploy/Dockerfile -t ai-trader-loop .
#   docker run --env-file .env.secrets -v "$PWD/trader/state:/app/trader/state" ai-trader-loop
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir "requests>=2.31.0"

COPY trader/ /app/trader/
COPY deploy/ /app/deploy/

ENV PYTHONUNBUFFERED=1
CMD ["bash", "deploy/run-loop.sh"]
