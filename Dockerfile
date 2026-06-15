FROM python:3.12-slim

LABEL org.opencontainers.image.title="Terraria Connection Logger" \
      org.opencontainers.image.description="Monitors a Terraria server container's Docker logs and records connection attempts to a CSV." \
      org.opencontainers.image.source="https://github.com/yourname/terraria-connection-logger"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONUNBUFFERED=1 \
    TERRARIA_CONTAINER="terraria" \
    LOG_FILE="/logs/terraria_connection_attempts.log" \
    PRINT_TO_CONSOLE="true" \
    RETRY_SECONDS="15"

VOLUME ["/logs"]

# Consider the logger healthy as long as the main process is alive.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD pgrep -f app/main.py > /dev/null || exit 1

CMD ["python", "-u", "app/main.py"]
