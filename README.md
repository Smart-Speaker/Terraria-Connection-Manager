# Terraria Connection Logger

A small Docker container that monitors a Terraria server container's logs and
records connection attempts to a CSV file.

It watches for lines like:

```text
194.163.172.10:33746 is connecting...
```

and appends a row to `terraria_connection_attempts.log`:

```text
timestamp,ip,port,raw_line
"2026-06-15 12:34:56","194.163.172.10","33746","194.163.172.10:33746 is connecting..."
```

## How it works

The container mounts the host Docker socket (read-only) and follows the logs of
your Terraria container. It does **not** touch or restart the Terraria
container — it only reads its log stream.

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

### Variables (`-e`)

| Variable             | Default                                      | Description                                                                                   |
| -------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `TERRARIA_CONTAINER` | `terraria`                                   | Name (recommended) or ID of your Terraria container, e.g. `terraria` or `8ec2734d585e`.       |
| `LOG_FILE`           | `/logs/terraria_connection_attempts.log`     | Path **inside** the container where the CSV is written. Must live under the `/logs` Path below.|
| `PRINT_TO_CONSOLE`   | `true`                                       | Also print matched attempts to this container's Docker logs.                                  |
| `RETRY_SECONDS`      | `15`                                         | Wait time before retrying when the Terraria container is missing or the log stream drops.     |

> **Name vs. ID:** A container **name** (like `terraria`) is stable. A short
> **ID** (like `8ec2734d585e`) changes every time the container is recreated —
> which Unraid does on every update or template edit. Prefer the name.

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
