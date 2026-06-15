"""Reads the Terraria console stream and turns it into structured state.

Parses connection/join/leave lines, writes the CSV, keeps the live player list,
and auto-blacklists IPs that hammer the server without ever joining.
"""
import os
import re
import time
from collections import deque
from datetime import datetime

from docker.errors import NotFound, DockerException

import config

CSV_HEADER = "timestamp,event,name,ip,port,raw_line\n"

CONNECTING_PATTERN = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)\s+is connecting",
    re.IGNORECASE,
)
JOINED_PATTERN = re.compile(r"^(?P<name>.+?) has joined\.?\s*$")
LEFT_PATTERN = re.compile(r"^(?P<name>.+?) has left\.?\s*$")
# Output of the `playing` command: "Nic (86.24.220.78:45738)"
PLAYING_PATTERN = re.compile(
    r"^(?P<name>.+?) \((?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)\)\s*$"
)


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def csv_escape(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def ensure_log_file() -> None:
    log_dir = os.path.dirname(config.LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    if not os.path.exists(config.LOG_FILE):
        with open(config.LOG_FILE, "w", encoding="utf-8") as handle:
            handle.write(CSV_HEADER)


def write_event(event: str, name: str, ip: str, port: str, raw_line: str) -> None:
    row = ",".join(
        csv_escape(v) for v in (now_timestamp(), event, name, ip, port, raw_line)
    )
    with open(config.LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(row + "\n")


def parse_players(lines):
    """Pull "name (ip:port)" rows out of `playing` command output."""
    found = []
    for line in lines:
        match = PLAYING_PATTERN.match(line.strip())
        if match:
            found.append((match.group("name").strip(), match.group("ip"), match.group("port")))
    return found


class Monitor:
    def __init__(self, control, store, firewall) -> None:
        self.control = control
        self.store = store
        self.firewall = firewall
        self.recent_connects = deque(maxlen=20)

    def log(self, message: str) -> None:
        line = f"[{now_timestamp()}] [logger] {message}"
        self.store.add_console_line(line)
        if config.PRINT_TO_CONSOLE:
            print(line, flush=True)

    # --- main loop ----------------------------------------------------------
    def run(self) -> None:
        ensure_log_file()
        self.log(f"Watching container: {config.TERRARIA_CONTAINER}")
        self.log(f"Writing log file: {config.LOG_FILE}")

        while True:
            try:
                container = self.control.get_container()
            except NotFound:
                self.store.set_status(docker="container-not-found")
                self.log(f"Container '{config.TERRARIA_CONTAINER}' not found. Retrying...")
                time.sleep(config.RETRY_SECONDS)
                continue
            except DockerException as error:
                self.store.set_status(docker="error", last_error=str(error))
                self.log(f"Could not reach Docker: {error}. Is docker.sock mounted? Retrying...")
                time.sleep(config.RETRY_SECONDS)
                continue

            try:
                self.control.detect_screen(container)
                self.store.set_status(docker="connected", last_error="")
                self.log(f"Connected to logs of '{container.name}' ({container.short_id}).")
                for raw in self.control.stream_logs(container):
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.strip():
                        self.handle_line(line)
                self.log("Log stream ended. Reconnecting...")
            except DockerException as error:
                self.store.set_status(docker="error", last_error=str(error))
                self.log(f"Log stream error: {error}. Reconnecting...")
                time.sleep(config.RETRY_SECONDS)
            except Exception as error:  # noqa: BLE001
                self.store.set_status(last_error=str(error))
                self.log(f"Unexpected error: {error}. Reconnecting...")
                time.sleep(config.RETRY_SECONDS)

    # --- line handling ------------------------------------------------------
    def handle_line(self, line: str) -> None:
        self.store.add_console_line(line)

        connecting = CONNECTING_PATTERN.search(line)
        if connecting:
            self.on_connecting(connecting.group("ip"), connecting.group("port"), line)
            return

        joined = JOINED_PATTERN.match(line)
        if joined:
            self.on_joined(joined.group("name").strip(), line)
            return

        left = LEFT_PATTERN.match(line)
        if left:
            self.on_left(left.group("name").strip(), line)

    def on_connecting(self, ip: str, port: str, line: str) -> None:
        self.recent_connects.append((ip, port, time.time()))
        write_event("connecting", "", ip, port, line)
        if config.PRINT_TO_CONSOLE:
            print(f"[{now_timestamp()}] Connection attempt   - IP: {ip}:{port}", flush=True)

        count = self.store.record_attempt(ip)
        if (
            config.AUTO_BLACKLIST
            and not self.store.is_whitelisted(ip)
            and not self.store.is_blacklisted(ip)
            and count >= config.ATTEMPT_THRESHOLD
        ):
            reason = f"auto: {count} connection attempts without joining"
            if self.store.blacklist_add(ip, reason, auto=True):
                self.firewall.add(ip)
                dropped = "dropped" if self.firewall.enabled else "recorded (firewall off)"
                self.log(f"Auto-blacklisted {ip} - {count} attempts, {dropped}")

    def on_joined(self, name: str, line: str) -> None:
        ip, port = self._claim_recent_connect()
        self.store.player_joined(name, ip, port)
        self.store.clear_attempts(ip)
        write_event("joined", name, ip, port, line)
        if config.PRINT_TO_CONSOLE:
            who = f"{ip}:{port}" if ip else "unknown IP"
            print(f"[{now_timestamp()}] Player joined        - {name} ({who})", flush=True)

    def on_left(self, name: str, line: str) -> None:
        ip, port = self.store.player_left(name)
        write_event("left", name, ip, port, line)
        if config.PRINT_TO_CONSOLE:
            who = f"{ip}:{port}" if ip else "unknown IP"
            print(f"[{now_timestamp()}] Player left          - {name} ({who})", flush=True)

    def _claim_recent_connect(self):
        cutoff = time.time() - config.JOIN_WINDOW_SECONDS
        while self.recent_connects:
            ip, port, ts = self.recent_connects.pop()
            if ts >= cutoff:
                return ip, port
        return "", ""
