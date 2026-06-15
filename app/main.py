import os
import re
import sys
import time
from collections import deque
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

# A connecting IP is only paired with a player name if the "has joined" line
# arrives within this many seconds of the "is connecting" line.
JOIN_WINDOW_SECONDS = int(os.getenv("JOIN_WINDOW_SECONDS", "30"))

CSV_HEADER = "timestamp,event,name,ip,port,raw_line\n"

CONNECTING_PATTERN = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)\s+is connecting",
    re.IGNORECASE,
)
JOINED_PATTERN = re.compile(r"^(?P<name>.+?) has joined\.?\s*$")
LEFT_PATTERN = re.compile(r"^(?P<name>.+?) has left\.?\s*$")


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
            file.write(CSV_HEADER)


def csv_escape(value: str) -> str:
    value = value.replace('"', '""')
    return f'"{value}"'


def write_event(event: str, name: str, ip: str, port: str, raw_line: str) -> None:
    timestamp = now_timestamp()

    row = ",".join(
        csv_escape(value)
        for value in (timestamp, event, name, ip, port, raw_line)
    )

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(row + "\n")

    if PRINT_TO_CONSOLE:
        if event == "connecting":
            log(f"Connection attempt   - IP: {ip}:{port}")
        elif event == "joined":
            who = f"{ip}:{port}" if ip else "unknown IP"
            log(f"Player joined        - {name} ({who})")
        elif event == "left":
            who = f"{ip}:{port}" if ip else "unknown IP"
            log(f"Player left          - {name} ({who})")


class PlayerTracker:
    """Pairs player names with the IP that connected just before they joined.

    Terraria logs a connection and then the join on the next line, e.g.:
        86.24.220.78:45738 is connecting...
        Nic has joined.
    so the most recent connection within JOIN_WINDOW_SECONDS is the joiner.
    """

    def __init__(self) -> None:
        self.recent_connects: deque = deque(maxlen=20)
        self.active_players: dict = {}

    def on_connecting(self, ip: str, port: str, raw_line: str) -> None:
        self.recent_connects.append((ip, port, time.time()))
        write_event("connecting", "", ip, port, raw_line)

    def on_joined(self, name: str, raw_line: str) -> None:
        ip, port = self._claim_recent_connect()
        if ip:
            self.active_players[name] = (ip, port)
        write_event("joined", name, ip, port, raw_line)

    def on_left(self, name: str, raw_line: str) -> None:
        ip, port = self.active_players.pop(name, ("", ""))
        write_event("left", name, ip, port, raw_line)

    def _claim_recent_connect(self):
        cutoff = time.time() - JOIN_WINDOW_SECONDS
        while self.recent_connects:
            ip, port, ts = self.recent_connects.pop()
            if ts >= cutoff:
                return ip, port
        return "", ""


def handle_line(line: str, tracker: PlayerTracker) -> None:
    connecting = CONNECTING_PATTERN.search(line)
    if connecting:
        tracker.on_connecting(connecting.group("ip"), connecting.group("port"), line)
        return

    joined = JOINED_PATTERN.match(line)
    if joined:
        tracker.on_joined(joined.group("name").strip(), line)
        return

    left = LEFT_PATTERN.match(line)
    if left:
        tracker.on_left(left.group("name").strip(), line)


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

    tracker = PlayerTracker()

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
                if line:
                    handle_line(line, tracker)

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
