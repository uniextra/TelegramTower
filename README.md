# TelegramTower 🗼

TelegramTower is a lightweight, Watchtower-inspired Docker container update manager that puts you in control. Instead of updating containers automatically and silently in the background, TelegramTower notifies you via Telegram and lets you approve updates with a single tap.

## Features

* **Manual Approval:** Receive interactive Telegram messages when an update is available. Choose to Update or Ignore directly from the chat.
* **Compose & Network Aware:** Preserves Docker Compose labels and multiple network attachments when recreating containers, preventing broken stacks.
* **Dynamic Configuration:** Adjust settings like polling intervals and delays directly from an interactive Telegram menu without restarting the bot.
* **GHCR Support:** Seamlessly works with GitHub Container Registry, Docker Hub, and private registries.
* **Exclude Containers:** Easily exclude specific containers from updates using standard labels.

## Previews

| Startup & Main Menu | Settings Details | Check Interval Selection |
|:---:|:---:|:---:|
| ![Startup](images/startup.png) | ![Settings](images/settings.png) | ![Interval](images/interval.png) |

## Quick Start

### 1. Prerequisites
1. Talk to [@BotFather](https://t.me/botfather) on Telegram to create a bot and get your `TELEGRAM_BOT_TOKEN`.
2. Get your Chat ID (you can use a bot like @userinfobot) for `TELEGRAM_CHAT_ID`.

### 2. Run with Docker Compose

Create a `docker-compose.yml` file:

```yaml
services:
  telegramtower:
    image: uniextra/telegramtower:latest
    container_name: telegramtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./telegramtower_data:/app/data
    environment:
      - TELEGRAM_BOT_TOKEN=your_bot_token_here
      - TELEGRAM_CHAT_ID=your_chat_id_here
```

Then run:
```bash
docker-compose up -d
```

### 3. Exclude Containers
To prevent TelegramTower from monitoring specific containers, add one of the following labels to your container's compose file or run command:
* `telegramtower.enable=false`
* `com.centurylinklabs.watchtower.enable=false` (Supported for easy migration from Watchtower)

Example in `docker-compose.yml`:
```yaml
services:
  my_app:
    image: nginx:latest
    labels:
      - "telegramtower.enable=false"
```

## Settings Configuration
Once the container starts, it will send a greeting message to your Telegram chat. 
Click **⚙️ Settings** to open the interactive configuration panel. Alternatively, you can send the `/settings` command to the bot at any time to adjust:
- **Check Interval:** How often to check for updates (1, 7, or 30 days). *(Note: TelegramTower performs its first check 10 seconds after startup, and then waits the configured interval before the next one).*
- **Request Delay:** Wait time between checks (0s, 2s, 5s) to avoid Docker Hub rate limits.
- **Cleanup Old Image:** Automatically delete old images after a successful update.
- **Check Stopped:** Include stopped containers in the update checks.
