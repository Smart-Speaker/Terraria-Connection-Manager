# Terraria Connection Manager

A lightweight **web control panel** for a Terraria server running in Docker
(built for Unraid, works great with the `ich777/terrariaserver` image).

It reads the Terraria container's console over the Docker socket and lets you:

- **Live console** — watch server output and type any command (`help`,
  `playing`, `say ...`, `time`, etc.); output appears in the panel.
- **Player list with IPs** — see who's online and the IP each player connected
  from, matched automatically from the join logs.
- **Kick / ban** — one-click `kick <player>` / `ban <player>`.
- **Connection logging** — every attempt/join/leave is written to a CSV.
- **Auto-blacklist** — IPs that repeatedly try to connect but never join get
  flagged automatically. With the optional firewall mode enabled, they're
  **dropped** so they can't reach the server.
- **Whitelist** — IPs you mark as trusted are never auto-blacklisted.

Everything except the firewall-drop feature works with just the Docker socket
mounted and a web port — no special privileges.

## How it talks to the server

The `ich777/terrariaserver` image runs the Terraria server inside a `screen`
session (that's what its built-in web console attaches to). This panel sends
commands by injecting keystrokes into that screen session through the Docker
socket — the same as typing into the console. The session name and user are
auto-detected; override with `SCREEN_SESSION` / `SCREEN_USER` only if needed.

Because the server's console output also shows up in `docker logs`, the panel
captures command responses (like the `playing` player list) from the same
stream it already watches.

## Quick start (Unraid)

### Option A — Community Applications template (recommended)

1. Copy `unraid-template.xml` to
   `/boot/config/plugins/dockerMan/templates-user/my-terraria-connection-manager.xml`.
2. **Docker → Add Container**, pick `terraria-connection-manager`, set
   **Terraria Container** to your server's name (e.g. `Terraria`), **Apply**.
3. Click the container's **WebUI** to open the panel.

### Option B — One command from the Unraid terminal

```bash
docker run -d \
  --name terraria-connection-manager \
  --restart unless-stopped \
  -p 8780:8780 \
  -e TERRARIA_CONTAINER=Terraria \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /mnt/user/appdata/terraria-connection-manager:/data \
  ghcr.io/smart-speaker/terraria-connection-manager:latest
```

Then browse to `http://<unraid-ip>:8780`.

## Configuration

`TERRARIA_CONTAINER` is the only setting you normally change. Everything else
has a working default baked into the image.

### Common

| Variable             | Default     | Description                                                                       |
| -------------------- | ----------- | --------------------------------------------------------------------------------- |
| `TERRARIA_CONTAINER` | `terraria`  | Name (recommended) or ID of your Terraria container, e.g. `Terraria`.             |
| `WEB_PORT`           | `8780`      | Port the control panel listens on.                                                |
| `WEB_PASSWORD`       | *(empty)*   | Set to require login (username `WEB_USER`, default `admin`). Blank = no auth.      |

> The panel can kick/ban and edit firewall rules. If it's reachable beyond your
> LAN, set `WEB_PASSWORD`.

### Auto-blacklist

| Variable            | Default | Description                                                                 |
| ------------------- | ------- | --------------------------------------------------------------------------- |
| `AUTO_BLACKLIST`    | `true`  | Flag IPs that connect repeatedly without joining.                           |
| `ATTEMPT_THRESHOLD` | `6`     | Attempts (without joining) within the window before blacklisting.           |
| `ATTEMPT_WINDOW`    | `600`   | Seconds the attempts are counted over.                                      |

### Firewall drop (optional, privileged)

Vanilla Terraria has no IP ban — its `ban` command only bans a *connected
player by name*. To actually **drop** a blacklisted IP's packets, this image
can manage an `iptables` chain on the host. That requires extra privileges:

```bash
docker run -d \
  --name terraria-connection-manager \
  --restart unless-stopped \
  --network host \
  --cap-add NET_ADMIN \
  -e TERRARIA_CONTAINER=Terraria \
  -e FIREWALL_ENABLED=true \
  -e TERRARIA_PORT=7777 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /mnt/user/appdata/terraria-connection-manager:/data \
  ghcr.io/smart-speaker/terraria-connection-manager:latest
```

| Variable           | Default | Description                                                                 |
| ------------------ | ------- | --------------------------------------------------------------------------- |
| `FIREWALL_ENABLED` | `false` | Manage iptables DROP rules for blacklisted IPs. Needs host net + NET_ADMIN. |
| `TERRARIA_PORT`    | `7777`  | Your Terraria game port (informational; rules drop the IP entirely).        |

With host networking the `-p 8780:8780` mapping is ignored — the panel is
reachable directly on `WEB_PORT`. Rules live in a dedicated `TERRARIA_BL`
chain, so removing the container/rules never touches your other firewall rules.
**If firewall mode is off, blacklisting still records and lists the IP** — it
just doesn't drop packets.

### Advanced

| Variable              | Default                       | Description                                         |
| --------------------- | ----------------------------- | --------------------------------------------------- |
| `LOG_FILE`            | `/data/connection_log.csv`    | Where the connection CSV is written.                |
| `JOIN_WINDOW_SECONDS` | `30`                          | Max gap to pair a `connecting` line with a join.    |
| `SCREEN_SESSION`      | *(auto)*                      | Override the screen session name.                   |
| `SCREEN_USER`         | *(auto)*                      | Override the screen session user.                   |
| `CMD_NEWLINE`         | `cr`                          | Console Enter key: `cr`, `lf`, or `crlf`. Switch to `lf` if commands don't register. |

## Data files

Everything persists under the `/data` mount:

| File                  | Contents                                                  |
| --------------------- | --------------------------------------------------------- |
| `connection_log.csv`  | Every `connecting` / `joined` / `left` event.             |
| `blacklist.json`      | Blacklisted IPs with reason, timestamp, and auto flag.    |
| `whitelist.json`      | Trusted IPs that are never auto-blacklisted.              |

CSV columns: `timestamp,event,name,ip,port,raw_line`. `connecting` rows with no
name are connection attempts that never joined (scanners/bots).

## Updating

```bash
docker pull ghcr.io/smart-speaker/terraria-connection-manager:latest
docker rm -f terraria-connection-manager
# re-run your docker run command (or just hit "Apply" in the Unraid UI)
```

The image is built and published to GHCR automatically by GitHub Actions on
every push to `main` (and on `v*` tags).

## Run with Docker Compose

```bash
docker compose up -d --build
```

Edit `docker-compose.yml` to set `TERRARIA_CONTAINER`; uncomment the firewall
lines if you want IP dropping.

## Notes & caveats

- **Name vs. ID:** a container **name** (`Terraria`) is stable; a short **ID**
  (`8ec2734d585e`) changes every time the container is recreated. Prefer the name.
- **Name↔IP matching** is a heuristic based on log ordering; on a busy server a
  name could occasionally pair with the wrong recent IP. The `raw_line` column
  preserves the original line so you can verify.
- The panel only **reads** the Terraria container's logs and **sends console
  commands**; it never restarts or modifies the container itself.
