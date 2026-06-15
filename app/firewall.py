"""Optional iptables enforcement: actually DROP blacklisted IPs.

Vanilla Terraria cannot ban by IP, so dropping repeat-offender IPs that never
join has to happen at the host firewall. This is opt-in (FIREWALL_ENABLED) and
needs the container to run with --network host --cap-add NET_ADMIN.

All rules live in a dedicated chain (TERRARIA_BL) so we never touch unrelated
rules and can be removed cleanly. When disabled or unavailable, every method is
a no-op and the rest of the app keeps working (detection + listing still run).
"""
import subprocess

import config

CHAIN = "TERRARIA_BL"


class Firewall:
    def __init__(self, store) -> None:
        self.store = store
        self.enabled = config.FIREWALL_ENABLED
        self.ready = False
        if self.enabled:
            self._setup()

    def _run(self, args, check=False):
        result = subprocess.run(
            ["iptables"] + args,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"iptables {' '.join(args)} failed")
        return result

    def _exists(self, args) -> bool:
        return self._run(["-C"] + args).returncode == 0

    def _ensure(self, args) -> None:
        if not self._exists(args):
            self._run(["-A"] + args, check=True)

    def _setup(self) -> None:
        try:
            # Create our chain if it does not exist yet.
            if self._run(["-nL", CHAIN]).returncode != 0:
                self._run(["-N", CHAIN], check=True)
            # Hook it in wherever the chain exists on this host. Docker-published
            # ports traverse DOCKER-USER; host-networked servers traverse INPUT.
            for parent in ("DOCKER-USER", "INPUT"):
                if self._run(["-nL", parent]).returncode == 0:
                    rule = [parent, "-j", CHAIN]
                    if not self._exists(rule):
                        self._run(["-I"] + rule, check=True)
            self.ready = True
            self.store.set_status(firewall="ready")
            self.sync()
        except Exception as error:  # noqa: BLE001 - degrade gracefully
            self.enabled = False
            self.ready = False
            self.store.set_status(
                firewall="error",
                last_error=f"firewall setup failed: {error}",
            )

    def add(self, ip: str) -> None:
        if not (self.enabled and self.ready):
            return
        try:
            rule = [CHAIN, "-s", ip, "-j", "DROP"]
            if not self._exists(rule):
                self._run(["-A"] + rule, check=True)
        except Exception as error:  # noqa: BLE001
            self.store.set_status(last_error=f"firewall add {ip} failed: {error}")

    def remove(self, ip: str) -> None:
        if not (self.enabled and self.ready):
            return
        rule = [CHAIN, "-s", ip, "-j", "DROP"]
        # Delete every copy of the rule, ignoring "not found".
        while self._run(["-D"] + rule).returncode == 0:
            pass

    def sync(self) -> None:
        if not (self.enabled and self.ready):
            return
        for ip in self.store.blacklist_ips():
            self.add(ip)
