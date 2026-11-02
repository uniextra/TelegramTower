# Changelog

All notable changes to **TelegramTower** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-11-02

### Added
- **Telegram Bot Authorization:** Handlers and callback buttons now strictly authenticate users against `TELEGRAM_CHAT_ID` and optional `TELEGRAM_ALLOWED_USER_IDS` with masked audit logging.
- **Web Dashboard Security:**
  - Fail-closed authentication (panel will not start without credentials unless `WEB_AUTH_DISABLED=true` is set).
  - Anti-brute force rate limiting (maximum 5 failed login attempts per minute per IP returning HTTP 429).
  - CSRF protection on all form submissions with `Origin` and `Referer` verification.
  - Security headers (`Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`).
  - Secret token masking in HTML (`1234••••••••abcd`) preventing plaintext leaks in browser views.
  - Production WSGI server (`waitress`) replacing Werkzeug in production threads.
  - Unauthenticated `/health` endpoint for Docker and orchestrator health checks.
- **Docker Container Updates:**
  - Full attribute preservation during container updates: `healthcheck`, `security_opt`, `read_only`, `tmpfs`, `cap_drop`, `ulimits`, `sysctls`, `user`, `working_dir`, resource limits, and named volumes.
  - Immediate post-startup health check with automatic rollback to backup container if startup fails.
  - Self-update and Docker socket-proxy protection preventing TelegramTower from interrupting its own execution.
  - Thread-safe updates lock preventing concurrency races.
- **Registry & SSRF Defense:**
  - Strict HTTPS realm validation and trusted registry allowlist rejecting private/internal IPs and cloud metadata (`169.254.169.254`).
  - Validation of all image manifest digests against `^sha256:[a-f0-9]{64}$`.
  - HTTP retry and backoff adapter using `requests.Session`.
- **Event Monitor Hardening:**
  - Anti-flood notification rate limiting (maximum 3 alerts per 60 seconds per container) to prevent alert storms during crash loops.
  - Exponential backoff on Docker daemon disconnections.
- **Database & Persistence:**
  - Automatic migration from legacy key-value prefixes to normalized `container_settings` table to prevent container name collisions.
  - Explicit connection closing via `contextlib` to eliminate file descriptor leaks.
  - Restrictive database directory and file permissions (`0700`/`0600`).
- **Container & CI/CD:**
  - Dedicated non-root `appuser` in `Dockerfile`.
  - Added `docker-compose.socket-proxy.yml` for zero-root Docker deployments.
  - Hardened `docker-compose.yml` with `127.0.0.1` binding and `no-new-privileges:true`.
  - Separated CI into `.github/workflows/ci.yml` (tests & linting on PRs without push) and `docker-publish.yml` (pushes only on release tags/main).
  - Added `SECURITY.md` and `.dockerignore`.

### Changed
- Separated dependencies into `requirements.txt` (production) and `requirements-dev.txt` (testing/linting).
- Empty token submission in web dashboard no longer deletes the existing token.
- Enhanced legacy Markdown escaping across all dynamic fields to avoid broken message syntax.

### Breaking Changes
- **Telegram Bot Authorization:** All Telegram commands and buttons now strictly verify incoming user IDs against `TELEGRAM_CHAT_ID` and `TELEGRAM_ALLOWED_USER_IDS`. Unauthorized users will be denied access.
- **Docker Container Non-Root (`appuser`):** The Docker container now runs as an unprivileged user (`appuser`, UID 1000). If mounting `/var/run/docker.sock` directly, ensure the host socket is accessible to the docker group / UID 1000, use `user: "0:0"` as an override if needed, or adopt the recommended `docker-compose.socket-proxy.yml`.
- **Database Schema Migration:** Container-specific configuration keys (`auto_*`, `last_updated_*`, `snooze_*`) are automatically migrated into the relational `container_settings` table.
- **Web Dashboard CSRF & Fail-Closed Auth:** Web forms require valid CSRF tokens. Insecure passwords (<8 characters or trivial) are rejected unless `ALLOW_INSECURE_PASSWORD=true` is set.
- **Telegram Callback Protocol (64-byte limit):** Long container names now use a deterministic 16-hex hash mapping (`h:<hash>`) to ensure callback data never exceeds Telegram's 64-byte API limit.
