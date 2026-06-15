"""Talks to the Terraria container over the Docker socket.

Two jobs:
  * stream the container's console logs (read), and
  * inject console commands into the server's screen session (write).

The ich777 image runs the server inside a `screen` session (that's what its
web console attaches to). We send keystrokes to that session with
`screen -X stuff`, which is exactly what typing into the console would do.
"""
import time

import docker
from docker.errors import NotFound, DockerException

import config


class TerrariaControl:
    def __init__(self, store) -> None:
        self.store = store
        self.client = None
        self._screen = config.SCREEN_SESSION
        self._user = config.SCREEN_USER

    # --- connection ---------------------------------------------------------
    def connect(self) -> None:
        self.client = docker.from_env()
        # Probe so a missing socket fails here, not later.
        self.client.ping()

    def get_container(self):
        if self.client is None:
            self.connect()
        return self.client.containers.get(config.TERRARIA_CONTAINER)

    def stream_logs(self, container):
        return container.logs(stream=True, follow=True, since=int(time.time()))

    # --- screen session discovery ------------------------------------------
    def detect_screen(self, container) -> None:
        """Find the screen session name and owning user inside the container.

        Screen sockets live in /run/screen/S-<user>/<pid>.<session>, readable
        without being that user, so we can derive both from the directory.
        """
        if self._screen and self._user:
            return
        code, output = container.exec_run(
            "sh -c 'ls -1d /run/screen/S-* /var/run/screen/S-* 2>/dev/null'"
        )
        dirs = output.decode("utf-8", "replace").split() if code == 0 else []
        if not dirs:
            return
        session_dir = dirs[0]
        user = session_dir.rstrip("/").split("S-", 1)[-1]
        code, output = container.exec_run(f"sh -c 'ls -1 {session_dir} 2>/dev/null'")
        entries = output.decode("utf-8", "replace").split() if code == 0 else []
        if not entries:
            return
        socket_name = entries[0]                       # e.g. "123.Terraria"
        session = socket_name.split(".", 1)[1] if "." in socket_name else socket_name
        self._screen = self._screen or session
        self._user = self._user or user
        self.store.set_status(screen=self._screen, screen_user=self._user)

    # --- sending commands ---------------------------------------------------
    def send_command(self, command: str) -> None:
        command = command.strip()
        if not command:
            raise ValueError("empty command")
        container = self.get_container()
        self.detect_screen(container)
        if not self._screen:
            raise RuntimeError(
                "No screen session found in the Terraria container. "
                "Set SCREEN_SESSION/SCREEN_USER if this image is non-standard."
            )
        payload = command + config.CMD_NEWLINE
        result = container.exec_run(
            ["screen", "-S", self._screen, "-p", "0", "-X", "stuff", payload],
            user=self._user or "root",
        )
        if result.exit_code != 0:
            raise RuntimeError(
                result.output.decode("utf-8", "replace").strip()
                or f"screen exited {result.exit_code}"
            )

    def run_capture(self, command: str, wait: float = 1.3):
        """Send a command and return the console lines it produced."""
        t0 = time.time()
        self.send_command(command)
        time.sleep(wait)
        return self.store.console_since(t0)
