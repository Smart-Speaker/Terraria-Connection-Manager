"""Thread-safe in-memory state plus JSON persistence.

A single Store instance is shared between the log-monitor thread and the Flask
web threads, so every method guards shared state with a reentrant lock.
"""
import json
import os
import tempfile
import threading
import time
from collections import deque

import config


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.console = deque(maxlen=600)   # (epoch, line)
        self.players = {}                  # name -> {ip, port, joined_at}
        self.attempts = {}                 # ip  -> deque[epoch] (connects w/o join)
        self.blacklist = _read_json(config.BLACKLIST_FILE, {})   # ip -> {...}
        self.whitelist = _read_json(config.WHITELIST_FILE, {})   # ip -> {...}
        self.status = {
            "container": config.TERRARIA_CONTAINER,
            "docker": "starting",
            "screen": "",
            "screen_user": "",
            "firewall": "on" if config.FIREWALL_ENABLED else "off",
            "last_error": "",
        }

    # --- console ------------------------------------------------------------
    def add_console_line(self, line: str) -> None:
        with self._lock:
            self.console.append((time.time(), line))

    def console_since(self, t0: float):
        with self._lock:
            return [line for ts, line in self.console if ts >= t0]

    # --- status -------------------------------------------------------------
    def set_status(self, **fields) -> None:
        with self._lock:
            self.status.update(fields)

    # --- players ------------------------------------------------------------
    def player_joined(self, name: str, ip: str, port: str) -> None:
        with self._lock:
            self.players[name] = {"ip": ip, "port": port, "joined_at": now_str()}

    def player_left(self, name: str):
        with self._lock:
            info = self.players.pop(name, {"ip": "", "port": ""})
            return info.get("ip", ""), info.get("port", "")

    def replace_players(self, found) -> None:
        """Replace the active player list from parsed `playing` output."""
        with self._lock:
            self.players = {
                name: {"ip": ip, "port": port, "joined_at": now_str()}
                for name, ip, port in found
            }

    # --- connection attempts (for auto-blacklist) ---------------------------
    def record_attempt(self, ip: str) -> int:
        with self._lock:
            bucket = self.attempts.setdefault(ip, deque())
            now = time.time()
            bucket.append(now)
            cutoff = now - config.ATTEMPT_WINDOW
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            return len(bucket)

    def clear_attempts(self, ip: str) -> None:
        with self._lock:
            self.attempts.pop(ip, None)

    # --- blacklist ----------------------------------------------------------
    def is_blacklisted(self, ip: str) -> bool:
        with self._lock:
            return ip in self.blacklist

    def blacklist_add(self, ip: str, reason: str, auto: bool) -> bool:
        with self._lock:
            if ip in self.blacklist:
                return False
            self.blacklist[ip] = {"reason": reason, "added_at": now_str(), "auto": auto}
            _write_json(config.BLACKLIST_FILE, self.blacklist)
            return True

    def blacklist_remove(self, ip: str) -> bool:
        with self._lock:
            if self.blacklist.pop(ip, None) is None:
                return False
            _write_json(config.BLACKLIST_FILE, self.blacklist)
            return True

    def blacklist_ips(self):
        with self._lock:
            return list(self.blacklist.keys())

    # --- whitelist ----------------------------------------------------------
    def is_whitelisted(self, ip: str) -> bool:
        with self._lock:
            return ip in self.whitelist

    def whitelist_add(self, ip: str, note: str) -> bool:
        with self._lock:
            if ip in self.whitelist:
                return False
            self.whitelist[ip] = {"note": note, "added_at": now_str()}
            _write_json(config.WHITELIST_FILE, self.whitelist)
            return True

    def whitelist_remove(self, ip: str) -> bool:
        with self._lock:
            if self.whitelist.pop(ip, None) is None:
                return False
            _write_json(config.WHITELIST_FILE, self.whitelist)
            return True

    # --- snapshot for the API ----------------------------------------------
    def snapshot(self):
        with self._lock:
            return {
                "status": dict(self.status),
                "players": [dict(name=n, **info) for n, info in self.players.items()],
                "console": [line for _, line in list(self.console)[-200:]],
                "blacklist": [dict(ip=ip, **info) for ip, info in self.blacklist.items()],
                "whitelist": [dict(ip=ip, **info) for ip, info in self.whitelist.items()],
            }
