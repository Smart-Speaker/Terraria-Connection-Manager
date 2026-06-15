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

All options are environment variables:

| Variable             | Default                                      | Description                                                                                   |
| -------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `TERRARIA_CONTAINER` | `terraria`                                   | Name (recommended) or ID of your Terraria container, e.g. `terraria` or `8ec2734d585e`.       |
| `LOG_FILE`           | `/logs/terraria_connection_attempts.log`     | Path inside the container where the CSV is written. Keep it under the `/logs` mount.           |
| `PRINT_TO_CONSOLE`   | `true`                                       | Also print matched attempts to this container's Docker logs.                                  |
| `RETRY_SECONDS`      | `15`                                         | Wait time before retrying when the Terraria container is missing or the log stream drops.     |

> **Name vs. ID:** A container **name** (like `terraria`) is stable. A short
> **ID** (like `8ec2734d585e`) changes every time the container is recreated —
> which Unraid does on every update or template edit. Prefer the name.

## Run with Docker Compose

```bash
docker compose up -d --build
```

Edit `docker-compose.yml` to set `TERRARIA_CONTAINER` and the host log path.

## Run on Unraid

There are two ways to install this on Unraid.

### Option A — Add Container template (recommended)

1. Build the image on the Unraid host so it's available locally:

   ```bash
   cd /path/to/terraria-connection-logger
   docker build -t terraria-connection-logger:latest .
   ```

   (Or push it to a registry and set that as the repository.)

2. Copy `unraid-template.xml` to:

   ```text
   /boot/config/plugins/dockerMan/templates-user/my-terraria-connection-logger.xml
   ```

3. In the Unraid web UI: **Docker → Add Container**, pick
   `terraria-connection-logger` from the template dropdown, set the
   **Terraria Container** field to your server's container name, and click
   **Apply**.

### Option B — Manual Add Container

In **Docker → Add Container**, set:

- **Repository:** `terraria-connection-logger:latest` (after building it on the host)
- **Variable** `TERRARIA_CONTAINER` → your Terraria container name
- **Path** `/logs` → `/mnt/user/appdata/terraria-connection-logger/logs` (rw)
- **Path** `/var/run/docker.sock` → `/var/run/docker.sock` (ro)

## Logs

The CSV is written to your mapped host path, by default:

```text
/mnt/user/appdata/terraria-connection-logger/logs/terraria_connection_attempts.log
```

Matched attempts also appear in this container's own log (when
`PRINT_TO_CONSOLE` is `true`).
