FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SEED_REFLECTIONS_HOST=0.0.0.0 \
    SEED_REFLECTIONS_PORT=8476 \
    SEED_REFLECTIONS_DATA_DIR=/data \
    SEED_REFLECTIONS_UPLOAD_JOBS_DIR=/data/uploads/jobs \
    SEED_REFLECTIONS_MIGRATE_LEGACY=0

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system seed \
    && adduser --system --ingroup seed seed \
    && mkdir -p /data/uploads/jobs \
    && chown -R seed:seed /data

COPY --chown=seed:seed . .
USER seed
EXPOSE 8476
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8476/api/v2/health',timeout=3))['status']=='healthy'"
CMD ["python", "server.py"]
