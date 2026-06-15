"""Terraria Connection Manager entrypoint.

Starts the log-monitor in a background thread and serves the web control panel
on the main thread.
"""
import threading
import time

import config
from store import Store
from terraria import TerrariaControl
from firewall import Firewall
from monitor import Monitor
from webapp import create_app


def main() -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting Terraria Connection Manager", flush=True)

    store = Store()
    control = TerrariaControl(store)
    firewall = Firewall(store)            # applies existing blacklist if enabled
    monitor = Monitor(control, store, firewall)

    worker = threading.Thread(target=monitor.run, name="monitor", daemon=True)
    worker.start()

    app = create_app(store, control, firewall)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Web UI on port {config.WEB_PORT}", flush=True)
    app.run(host="0.0.0.0", port=config.WEB_PORT, threaded=True)


if __name__ == "__main__":
    main()
