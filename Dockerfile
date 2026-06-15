FROM python:3.12-slim

LABEL org.opencontainers.image.title="Terraria Connection Manager" \
      org.opencontainers.image.description="Web control panel for a Terraria server container: console, players, kick/ban, and auto-blacklisting of abusive IPs." \
      org.opencontainers.image.source="https://github.com/Smart-Speaker/Terraria-Connection-Manager"

WORKDIR /app

# iptables: optional firewall enforcement. procps: pgrep for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iptables procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONUNBUFFERED=1 \
    TERRARIA_CONTAINER="terraria" \
    DATA_DIR="/data" \
    PRINT_TO_CONSOLE="true" \
    RETRY_SECONDS="15" \
    WEB_PORT="8780" \
    AUTO_BLACKLIST="true" \
    ATTEMPT_THRESHOLD="6" \
    ATTEMPT_WINDOW="600" \
    FIREWALL_ENABLED="false"

VOLUME ["/data"]
EXPOSE 8780

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.getenv('WEB_PORT','8780'))" || exit 1

CMD ["python", "-u", "app/main.py"]
