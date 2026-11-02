# Security Policy

## Reporting Security Vulnerabilities

If you discover a security issue or vulnerability in **TelegramTower**, please report it responsibly.

Do **NOT** create public GitHub issues for security vulnerabilities. Instead, please report security concerns via GitHub Private Vulnerability Reporting or contact the maintainer directly.

When reporting, please include:
- A description of the issue.
- Steps to reproduce or proof of concept.
- Affected components and versions.
- Potential impact.

---

## Security Architecture & Best Practices

TelegramTower interacts directly with Docker to monitor and update running containers. Because access to the Docker daemon (`/var/run/docker.sock`) grants root-equivalent control over the host, security hardening is critical.

### 1. Docker Socket Proxy (Recommended)
Rather than mounting `/var/run/docker.sock` directly into the TelegramTower container, we strongly recommend deploying with a socket proxy (such as `tecnativa/docker-socket-proxy` via `docker-compose.socket-proxy.yml`).
This limits the exposed API surface exclusively to read/recreation actions and blocks access to sensitive endpoints like `exec`, `secrets`, or `volumes`.

### 2. Network Isolation
- By default, the Web Dashboard binds to `127.0.0.1:8080` to prevent exposure to external networks.
- Always configure a strong `WEB_PASSWORD` (minimum 8 characters, non-trivial).
- Brute-force protection automatically rate-limits failed authentication attempts (maximum 5 attempts per minute per IP).

### 3. Telegram Bot Authorization
- All commands (`/start`, `/settings`, `/activehours`, `/language`) and callback buttons are strictly restricted to the authorized chat (`TELEGRAM_CHAT_ID`).
- If deploying in a group chat, configure `TELEGRAM_ALLOWED_USER_IDS` to restrict control only to authorized administrative user IDs.
