<div align="center">
<img src="static/logo.jpg" alt="TelegramTower Logo" width="150"/>
</div>

# TelegramTower 🗼

TelegramTower is a lightweight, security-hardened Docker container update manager inspired by Watchtower. Instead of updating containers automatically and silently in the background, TelegramTower notifies you via Telegram and lets you approve updates with a single tap, with full auto-update and quarantine options.

> For security policies, zero-root socket-proxy setup, and hardening details, see [SECURITY.md](SECURITY.md).

---

## Features

* **Approval & Auto-Update:** Receive interactive Telegram messages when an update is available to manually approve them, or enable **Auto-Update** per-container to apply them automatically.
* **Compose & Network Aware:** Preserves Docker Compose labels and multiple network attachments when recreating containers. Automatically detects and recreates dependent network containers (e.g. `network_mode: service:vpn`) when their parent container is updated.
* **Dynamic Configuration:** Adjust settings like polling intervals and delays directly from an interactive Telegram menu without restarting the bot.
* **Quarantine Delay:** Delay update notifications for a specified number of days (1, 3, 5, 7 days) to ensure stability and protect against "day 0" bugs or compromised tags.
* **Active Hours (Horas Activas):** Set custom active hours (inspired by Windows Update) where automatic updates and restarts are paused (e.g. `08:00 - 02:00`) so services like Plex are never interrupted while in use. Pending updates are automatically deferred and applied during the maintenance window.
* **Release Version & Changelog Links:** Notifications parse release versions (OCI labels, version schemas, LinuxServer.io `build_version`) and display clickable links to release notes or source code when available.
* **Multi-Language Support (EN / ES):** Full internationalization in both Web Dashboard and Telegram. Switch dynamically between English and Spanish via `/language` / `/idioma` or dashboard toggle.
* **Event Notifications with Anti-Flood:** Real-time alerts when containers start (✅), stop/crash (🔴), or change health status (💚/🤒), with rate-limiting during crash loops to prevent spam.

---

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Bot token provided by [@BotFather](https://t.me/botfather). | *Required (or configure via Web)* |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID authorized to operate the bot. | *Required (or configure via Web)* |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated list of Telegram User IDs allowed to execute actions (useful in group chats). | Authorized `TELEGRAM_CHAT_ID` |
| `WEB_USER` | Username for Web Dashboard Basic Auth. | `admin` |
| `WEB_PASSWORD` | Password for Web Dashboard (min 8 chars, non-trivial). | `admin` (Configure a secure password) |
| `WEB_AUTH_DISABLED` | Set to `true` to disable Web Dashboard authentication (use with caution). | `false` |
| `ALLOW_INSECURE_PASSWORD`| Set to `true` to allow passwords < 8 chars or trivial passwords. | `false` |
| `WEB_HOST` | Host address the Web Dashboard binds to. | `0.0.0.0` |
| `WEB_PORT` | Port for the Web Dashboard. | `8080` |
| `DOCKER_HOST` | Docker daemon URL (e.g. `tcp://socket-proxy:2375`). | Unix socket (`/var/run/docker.sock`) |
| `LOG_LEVEL` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |

---

## Quick Start

### Option A: Recommended Secure Deployment (Socket-Proxy)

Using a Docker socket proxy isolates Docker API access and runs TelegramTower completely unprivileged without exposing the raw Docker socket:

```bash
docker compose -f docker-compose.socket-proxy.yml up -d
```

### Option B: Standard Deployment

Create `docker-compose.yml`:

```yaml
services:
  telegramtower:
    image: uniextra/telegramtower:latest
    container_name: telegramtower
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    ports:
      - "8080:8080" # Use "127.0.0.1:8080:8080" if behind a local reverse proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/app/data
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - WEB_HOST=0.0.0.0
      - WEB_USER=admin
      - WEB_PASSWORD=${WEB_PASSWORD:-admin}
```

```bash
docker compose up -d
```

---

## Migration & Breaking Changes (v2.0.0)

1. **Telegram Authorization:** The bot strictly allows only `TELEGRAM_CHAT_ID` and IDs listed in `TELEGRAM_ALLOWED_USER_IDS`. Unauthorized users are rejected.
2. **Non-Root Execution:** The container runs as unprivileged user `appuser` (UID 1000). Ensure `/var/run/docker.sock` has appropriate host permissions, or use `docker-compose.socket-proxy.yml` (or `user: "0:0"` if required by host).
3. **Database Migration:** Legacy `config` table keys (`auto_*`, `last_updated_*`) are automatically migrated to the normalized `container_settings` table on first run without manual intervention.
4. **Web Security:** Web dashboard includes CSRF protection, rate limiting against brute-force attacks, and masked secret tokens.

---

## License

This project is open source and available under the [MIT License](LICENSE).
