"""All runtime configuration, read from environment variables.

Only TERRARIA_CONTAINER normally needs setting; everything else has a sensible
default baked into the image.
"""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# --- Target container -------------------------------------------------------
TERRARIA_CONTAINER = (
    os.getenv("TERRARIA_CONTAINER")
    or os.getenv("TERRARIA_CONTAINER_NAME")
    or "terraria"
).strip()

# --- Storage ----------------------------------------------------------------
DATA_DIR = os.getenv("DATA_DIR", "/data")
LOG_FILE = os.getenv("LOG_FILE", os.path.join(DATA_DIR, "connection_log.csv"))
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")
WHITELIST_FILE = os.path.join(DATA_DIR, "whitelist.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")

# --- Log parsing / monitoring ----------------------------------------------
PRINT_TO_CONSOLE = _bool("PRINT_TO_CONSOLE", True)
RETRY_SECONDS = _int("RETRY_SECONDS", 15)
# Max gap between an "is connecting" line and a "has joined" line to pair them.
JOIN_WINDOW_SECONDS = _int("JOIN_WINDOW_SECONDS", 30)

# --- Web UI -----------------------------------------------------------------
WEB_PORT = _int("WEB_PORT", 8780)
# Optional HTTP basic auth. Leave WEB_PASSWORD empty to disable.
WEB_USER = os.getenv("WEB_USER", "admin")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")

# --- Auto-blacklist ---------------------------------------------------------
AUTO_BLACKLIST = _bool("AUTO_BLACKLIST", True)
# An IP that produces this many "is connecting" lines without ever joining,
# within ATTEMPT_WINDOW seconds, gets auto-blacklisted.
ATTEMPT_THRESHOLD = _int("ATTEMPT_THRESHOLD", 6)
ATTEMPT_WINDOW = _int("ATTEMPT_WINDOW", 600)

# --- Firewall enforcement (opt-in) -----------------------------------------
# Requires the container to run with: --network host --cap-add NET_ADMIN
FIREWALL_ENABLED = _bool("FIREWALL_ENABLED", False)
TERRARIA_PORT = _int("TERRARIA_PORT", 7777)

# --- Sending commands to the server console --------------------------------
# The ich777 image runs the server inside a screen session; we send keystrokes
# to it. These are auto-detected at runtime but can be overridden.
SCREEN_SESSION = os.getenv("SCREEN_SESSION", "").strip()
SCREEN_USER = os.getenv("SCREEN_USER", "").strip()
# What "Enter" looks like to the server's console. cr (carriage return) matches
# a real key press through screen's pty; switch to lf if commands don't register.
_NEWLINE = os.getenv("CMD_NEWLINE", "cr").strip().lower()
CMD_NEWLINE = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}.get(_NEWLINE, "\r")
