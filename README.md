# Terraria Connection Logger

A small Docker container that monitors a Terraria server container's logs and
records connection attempts — and **which player each connection belongs to** —
to a CSV file.

Terraria logs a connection and then the player's join on the next line:

```text
86.24.220.78:45738 is connecting...
Nic has joined.
```

The logger pairs these up and writes one row per event to
`terraria_connection_attempts.log`:

```text
timestamp,event,name,ip,port,raw_line
"2026-06-15 19:35:14","connecting","","86.24.220.78","45738","86.24.220.78:45738 is connecting..."
"2026-06-15 19:35:15","joined","Nic","86.24.220.78","45738","Nic has joined."
"2026-06-15 20:01:02","left","Nic","86.24.220.78","45738","Nic has left."
```

The `event` column is one of:

- **`connecting`** — an IP attempted a connection. Scanners/bots that connect
  but never join show up only as `connecting` rows (no name), which makes them
  easy to spot.
- **`joined`** — a player finished connecting. The `name`, `ip`, and `port` are
  filled in by matching the join to the most recent `connecting` line (within
  `JOIN_WINDOW_SECONDS`).
- **`left`** — a player disconnected. Their IP is recalled from when they joined.

## How it works

The container mounts the host Docker socket (read-only) and follows the logs of
your Terraria container. It does **not** touch or restart the Terraria
container — it only reads its log stream.

Name↔IP matching is a heuristic based on log ordering, so on a busy server where
several people connect in the same second a name could occasionally be paired
with the wrong recent IP. The `raw_line` column is always the unmodified log
line so you can verify any row by hand.

## Configuration

This container has two kinds of settings. In Unraid's **Add Container** screen
each row has a **Type** dropdown that is either *Variable* or *Path*:

- **Variable** — a key/value setting passed to the program as an environment
  variable (Docker `-e KEY=value`). Just text.
- **Path** — a folder/file mapping between your Unraid server (the host) and
  the container (Docker `-v host:container`). This is how files get shared in
  and out of the container.

Both are required for the logger to work. The two Paths in particular are
mandatory — without them the container can't read Docker and won't keep your
log file.

### The only setting you need to change

| Variable             | Default      | Description                                                                              |
| -------------------- | ------------ | ---------------------------------------------------------------------------------------- |
| `TERRARIA_CONTAINER` | `terraria`   | Name (recommended) or ID of your Terraria container, e.g. `terraria` or `8ec2734d585e`.  |

> **Name vs. ID:** A container **name** (like `terraria`) is stable. A short
> **ID** (like `8ec2734d585e`) changes every time the container is recreated —
> which Unraid does on every update or template edit. Prefer the name.

### Advanced settings (optional — defaults baked into the image)

You normally never touch these. They ship with working defaults; override one
only by adding it as an extra `-e` variable.

| Variable             | Default                                      | Description                                                                                   |
| -------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `LOG_FILE`           | `/logs/terraria_connection_attempts.log`     | Path **inside** the container where the CSV is written. Must live under the `/logs` Path below.|
| `PRINT_TO_CONSOLE`   | `true`                                       | Also print matched attempts to this container's Docker logs.                                  |
| `RETRY_SECONDS`      | `15`                                         | Wait time before retrying when the Terraria container is missing or the log stream drops.     |
| `JOIN_WINDOW_SECONDS`| `30`                                         | Max seconds between a `connecting` line and a `has joined` line for them to be paired.         |

### Paths (`-v`) — required

| Container path         | Host path (example)                                        | Mode | Why                                                                                  |
| ---------------------- | ---------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------ |
| `/var/run/docker.sock` | `/var/run/docker.sock`                                     | ro   | Lets this container read the Terraria container's logs. Without it nothing works.    |
| `/logs`                | `/mnt/user/appdata/terraria-connection-logger/logs`        | rw   | Where the CSV is saved on your server so it survives restarts. `LOG_FILE` points here.|

> **How the two relate:** `LOG_FILE` is a *Variable* pointing at a path *inside*
> the container (`/logs/...`). `/logs` is a *Path* that maps that in-container
> folder to a real folder on your Unraid array. Keep `LOG_FILE` under `/logs` so
> the file lands in the host folder you mapped.

## Run with Docker Compose

```bash
docker compose up -d --build
```

Edit `docker-compose.yml` to set `TERRARIA_CONTAINER` and the host log path.

## Docker image

Every push to `main` builds and publishes a multi-tag image to the GitHub
Container Registry via GitHub Actions:

```text
ghcr.io/smart-speaker/terraria-connection-manager:latest
```

Tagged releases (push a `v1.2.3` git tag) also publish `1.2.3` and `1.2`
image tags. No local build is needed to run it.

## Run on Unraid

There are two ways to install this on Unraid. Both pull the prebuilt image
above — no building on the Unraid host.

### Option A — Add Container template (recommended)

1. Copy `unraid-template.xml` to:

   ```text
   /boot/config/plugins/dockerMan/templates-user/my-terraria-connection-manager.xml
   ```

2. In the Unraid web UI: **Docker → Add Container**, pick
   `terraria-connection-logger` from the template dropdown, set the
   **Terraria Container** field to your server's container name, and click
   **Apply**.

### Option B — Manual Add Container

In **Docker → Add Container**, set:

- **Repository:** `ghcr.io/smart-speaker/terraria-connection-manager:latest`
- **Variable** `TERRARIA_CONTAINER` → your Terraria container name
- **Path** `/logs` → `/mnt/user/appdata/terraria-connection-logger/logs` (rw)
- **Path** `/var/run/docker.sock` → `/var/run/docker.sock` (ro)

### Option C — One command from the Unraid terminal

Run this as root from the Unraid console/SSH. Change `TERRARIA_CONTAINER` to
your Terraria container's name first:

```bash
docker run -d \
  --name terraria-connection-logger \
  --restart unless-stopped \
  -e TERRARIA_CONTAINER=terraria \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /mnt/user/appdata/terraria-connection-logger/logs:/logs \
  ghcr.io/smart-speaker/terraria-connection-manager:latest
```

`TERRARIA_CONTAINER` is the only variable you set — everything else uses the
image defaults.

Containers created this way won't show the Unraid template icon/links, but they
run identically. To update later: `docker pull` the image, then
`docker rm -f terraria-connection-logger` and re-run the command.

> **Note:** GHCR packages are private by default. After the first successful
> Actions run, open the package on GitHub
> (**Profile/Org → Packages → terraria-connection-manager → Package settings**)
> and set visibility to **Public** so Unraid can pull it without a login.

## Logs

The CSV is written to your mapped host path, by default:

```text
/mnt/user/appdata/terraria-connection-logger/logs/terraria_connection_attempts.log
```

Matched attempts also appear in this container's own log (when
`PRINT_TO_CONSOLE` is `true`).
