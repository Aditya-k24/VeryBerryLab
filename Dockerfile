FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# --preload: data_cache.initialize() (~12s Excel/stats load) runs once in the
# master process before fork, so extra workers don't re-parse the workbooks.
# Cloud Run injects $PORT (defaults to 8080 locally via `docker run -p`).
CMD ["sh", "-c", "exec gunicorn --preload --workers 2 --threads 4 --timeout 120 -b 0.0.0.0:${PORT:-8080} app:server"]
