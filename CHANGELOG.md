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
- Bound default Web Dashboard host to `127.0.0.1` (configurable via `WEB_HOST`).
- Empty token submission in web dashboard no longer deletes the existing token.
- Enhanced legacy Markdown escaping across all dynamic fields to avoid broken message syntax.

### Breaking Changes
- Web Dashboard no longer allows default `admin/admin` credentials or empty passwords without setting `ALLOW_INSECURE_PASSWORD=true` or `WEB_AUTH_DISABLED=true`.
- Web Dashboard binds to `127.0.0.1` by default instead of `0.0.0.0`.
