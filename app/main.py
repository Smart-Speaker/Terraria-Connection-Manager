import os
import re
import sys
import time
from datetime import datetime

import docker
from docker.errors import NotFound, DockerException


# Accept either a container NAME (recommended, stable across updates) or a
# container ID (e.g. 8ec2734d585e). TERRARIA_CONTAINER is the preferred var;
# TERRARIA_CONTAINER_NAME is kept for backwards compatibility.
TERRARIA_CONTAINER = (
    os.getenv("TERRARIA_CONTAINER")
    or os.getenv("TERRARIA_CONTAINER_NAME")
    or "terraria"
).strip()
LOG_FILE = os.getenv("LOG_FILE", "/logs/terraria_connection_attempts.log")
PRINT_TO_CONSOLE = os.getenv("PRINT_TO_CONSOLE", "true").lower() == "true"
RETRY_SECONDS = int(os.getenv("RETRY_SECONDS", "15"))

CONNECTING_PATTERN = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)\s+is connecting",
    re.IGNORECASE,
)


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_timestamp()}] {message}", flush=True)


def ensure_log_file() -> None:
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as file:
            file.write("timestamp,ip,port,raw_line\n")


def csv_escape(value: str) -> str:
    value = value.replace('"', '""')
    return f'"{value}"'


def write_attempt(ip: str, port: str, raw_line: str) -> None:
    timestamp = now_timestamp()

    row = ",".join(
        [
            csv_escape(timestamp),
            csv_escape(ip),
            csv_escape(port),
            csv_escape(raw_line),
        ]
    )

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(row + "\n")

    if PRINT_TO_CONSOLE:
        log(f"Terraria connection attempt - IP: {ip} | Port: {port}")


def get_container(client: docker.DockerClient):
    try:
        return client.containers.get(TERRARIA_CONTAINER)
    except NotFound:
        log(f"ERROR: Container '{TERRARIA_CONTAINER}' not found (by name or ID).")
        return None
    except DockerException as error:
        log(f"ERROR: Could not look up container '{TERRARIA_CONTAINER}': {error}")
        return None


def monitor_logs() -> None:
    ensure_log_file()

    log("Starting Terraria connection logger")
    log(f"Watching container: {TERRARIA_CONTAINER}")
    log(f"Writing log file: {LOG_FILE}")

    try:
        client = docker.from_env()
    except DockerException as error:
        log(f"ERROR: Could not connect to Docker: {error}")
        log("Is /var/run/docker.sock mounted into this container?")
        sys.exit(1)

    while True:
        container = get_container(client)

        if container is None:
            log(f"Retrying in {RETRY_SECONDS} seconds...")
            time.sleep(RETRY_SECONDS)
            continue

        try:
            log(f"Connected to logs of '{container.name}' ({container.short_id}).")

            for raw in container.logs(stream=True, follow=True, since=int(time.time())):
                line = raw.decode("utf-8", errors="replace").strip()

                match = CONNECTING_PATTERN.search(line)
                if not match:
                    continue

                ip = match.group("ip")
                port = match.group("port")

                write_attempt(ip, port, line)

            # Stream ended (container stopped/restarted) — loop and reconnect.
            log("Log stream ended. Reconnecting...")

        except DockerException as error:
            log(f"Docker log stream error: {error}")
            log(f"Reconnecting in {RETRY_SECONDS} seconds...")
            time.sleep(RETRY_SECONDS)

        except KeyboardInterrupt:
            log("Stopping logger.")
            break

        except Exception as error:
            log(f"Unexpected error: {error}")
            log(f"Reconnecting in {RETRY_SECONDS} seconds...")
            time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    monitor_logs()
