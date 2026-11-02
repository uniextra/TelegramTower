import datetime
import logging
import os
import re
import secrets
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from flask import Flask, Response, redirect, render_template, request, session, url_for

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
)

TRIVIAL_PASSWORDS = {"admin", "password", "123456", "12345678", "root", "toor"}

_login_attempts: Dict[str, List[float]] = {}
_login_lock = threading.Lock()


def is_password_secure(password: Optional[str]) -> bool:
    if not password:
        return False
    if password.lower() in TRIVIAL_PASSWORDS or len(password) < 8:
        return False
    return True


def _check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if IP exceeded 5 failed attempts in 60s."""
    now = time.time()
    with _login_lock:
        timestamps = [t for t in _login_attempts.get(ip, []) if now - t < 60]
        _login_attempts[ip] = timestamps
        return len(timestamps) < 5


def _record_failed_login(ip: str) -> None:
    now = time.time()
    with _login_lock:
        if ip not in _login_attempts:
            _login_attempts[ip] = []
        _login_attempts[ip].append(now)


def _record_successful_login(ip: str) -> None:
    with _login_lock:
        _login_attempts.pop(ip, None)


def check_auth(username: Optional[str], password: Optional[str]) -> bool:
    auth_disabled = os.environ.get("WEB_AUTH_DISABLED", "").strip().lower() == "true"
    if auth_disabled:
        return True

    user = os.environ.get("WEB_USER")
    pw = os.environ.get("WEB_PASSWORD")
    if not user or not pw:
        # Fail-closed: do not allow access if credentials are not configured
        return False

    if username is None or password is None:
        return False

    return secrets.compare_digest(username, user) and secrets.compare_digest(password, pw)


def authenticate() -> Response:
    return Response(
        "Could not verify your access level for that URL.\n"
        "You have to login with proper credentials",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f: Callable) -> Callable:
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        auth_disabled = os.environ.get("WEB_AUTH_DISABLED", "").strip().lower() == "true"
        if auth_disabled:
            return f(*args, **kwargs)

        ip = request.remote_addr or "127.0.0.1"
        if not _check_rate_limit(ip):
            logger.warning(f"Rate limit exceeded for IP {ip}")
            return Response("Too Many Requests: Rate limit exceeded. Try again later.", 429)

        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            _record_failed_login(ip)
            return authenticate()

        _record_successful_login(ip)
        return f(*args, **kwargs)

    return decorated


def get_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def csrf_protect() -> Optional[Response]:
    # Allow tests to disable CSRF validation when testing without forms
    if app.config.get("TESTING") and not app.config.get("CSRF_ENABLED", False):
        return None

    if request.path == "/health":
        return None

    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("Origin")
        if origin:
            origin_host = urlparse(origin).netloc
            if origin_host and origin_host != request.host:
                logger.warning(f"CSRF Origin mismatch: {origin_host} != {request.host}")
                return Response("Forbidden: Cross-site request rejected.", 403)

        token = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRFToken")
            or request.headers.get("X-CSRF-Token")
        )
        if not token and request.is_json and isinstance(request.json, dict):
            token = request.json.get("csrf_token")

        expected_token = session.get("_csrf_token")
        if not expected_token or not token or not secrets.compare_digest(str(token), str(expected_token)):
            logger.warning("CSRF token validation failed")
            return Response("Forbidden: Invalid or missing CSRF token.", 403)

    return None


@app.after_request
def add_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:;"
    )
    return response


@app.route("/health", methods=["GET"])
def health() -> Any:
    return {"status": "ok"}, 200


@app.route("/", methods=["GET", "POST"])
@requires_auth
def dashboard() -> Any:
    try:
        docker_manager = app.config["DOCKER_MANAGER"]
        config_db = app.config["CONFIG_DB"]

        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_bot_credentials":
                new_token = request.form.get("bot_token", "").strip()
                # If non-empty and not masked placeholder, validate and update
                if new_token and not all(c in "•*" for c in new_token):
                    if re.match(r"^\d{6,}:[A-Za-z0-9_-]{30,}$", new_token):
                        config_db.set_bot_token(new_token)
                    else:
                        logger.warning("Rejected invalid bot_token format.")

                new_chat_id = request.form.get("chat_id", "").strip()
                if new_chat_id:
                    if re.match(r"^-?\d+$|^@[A-Za-z0-9_]{5,}$", new_chat_id):
                        config_db.set_chat_id(new_chat_id)
                    else:
                        logger.warning(f"Rejected invalid chat_id format: {new_chat_id}")

            elif action == "save_global_settings":
                poll_val = request.form.get("poll_interval_days")
                if poll_val is not None:
                    try:
                        val = int(poll_val)
                        if 1 <= val <= 365:
                            config_db.set_poll_interval_days(val)
                    except ValueError:
                        pass

                delay_val = request.form.get("request_delay_seconds")
                if delay_val is not None:
                    try:
                        val = int(delay_val)
                        if 0 <= val <= 60:
                            config_db.set_request_delay_seconds(val)
                    except ValueError:
                        pass

                quarantine_val = request.form.get("quarantine_days")
                if quarantine_val is not None:
                    try:
                        val = int(quarantine_val)
                        if 0 <= val <= 365:
                            config_db.set_quarantine_days(val)
                    except ValueError:
                        pass

                config_db.set_cleanup_old_image(request.form.get("cleanup_old_image") == "on")
                config_db.set_include_stopped(request.form.get("include_stopped") == "on")

                config_db.set_events_enabled(request.form.get("events_enabled") == "on")
                config_db.set_events_notify_start(request.form.get("events_notify_start") == "on")
                config_db.set_events_notify_stop(request.form.get("events_notify_stop") == "on")
                config_db.set_events_notify_health(request.form.get("events_notify_health") == "on")
                config_db.set_events_whitelist_only(request.form.get("events_whitelist_only") == "on")

                config_db.set_active_hours_enabled(request.form.get("active_hours_enabled") == "on")
                start_time = request.form.get("active_hours_start", "").strip()
                if start_time and re.match(r"^([01]\d|2[0-3]):[0-5]\d$", start_time):
                    config_db.set_active_hours_start(start_time)
                end_time = request.form.get("active_hours_end", "").strip()
                if end_time and re.match(r"^([01]\d|2[0-3]):[0-5]\d$", end_time):
                    config_db.set_active_hours_end(end_time)

            elif action in ("toggle_auto_update", "clear_snooze"):
                container_name = request.form.get("container_name")
                if container_name and re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", container_name):
                    try:
                        existing_containers = {c.name for c in docker_manager.get_containers(include_stopped=True)}
                    except Exception:
                        existing_containers = set()

                    if not existing_containers or container_name in existing_containers:
                        if action == "toggle_auto_update":
                            current_val = config_db.get_auto_update(container_name)
                            config_db.set_auto_update(container_name, not current_val)
                        elif action == "clear_snooze":
                            config_db.clear_snooze(container_name)
                else:
                    logger.warning(f"Rejected invalid container_name: {container_name}")

            elif action == "set_language":
                new_lang = request.form.get("language", "").strip()
                if new_lang in ("en", "es"):
                    config_db.set_language(new_lang)
                if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                    return {"status": "ok", "language": new_lang}
                return redirect(url_for("dashboard"))

            return redirect(url_for("dashboard"))

        include_stopped = config_db.get_include_stopped()
        containers = docker_manager.get_containers(include_stopped=include_stopped)

        records = config_db.get_all_quarantine_records()
        q_dict = {r["container_name"]: r for r in records}

        q_days_global = config_db.get_quarantine_days()
        now = datetime.datetime.now(datetime.timezone.utc)

        env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        db_token = config_db.get_bot_token() or ""
        env_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        db_chat_id = config_db.get_chat_id() or ""

        effective_token = db_token or env_token
        masked_token = ""
        if effective_token:
            if len(effective_token) > 8:
                masked_token = f"{effective_token[:4]}••••••••{effective_token[-4:]}"
            else:
                masked_token = "••••••••"

        env_only_whitelist = os.environ.get("ONLY_WHITELIST", "").lower() == "true"

        settings = {
            "poll_interval_days": config_db.get_poll_interval_days(),
            "request_delay_seconds": config_db.get_request_delay_seconds(),
            "cleanup_old_image": config_db.get_cleanup_old_image(),
            "include_stopped": config_db.get_include_stopped(),
            "quarantine_days": q_days_global,
            "events_enabled": config_db.get_events_enabled(),
            "events_notify_start": config_db.get_events_notify_start(),
            "events_notify_stop": config_db.get_events_notify_stop(),
            "events_notify_health": config_db.get_events_notify_health(),
            "events_whitelist_only": config_db.get_events_whitelist_only() or env_only_whitelist,
            "env_only_whitelist": env_only_whitelist,
            "active_hours_enabled": config_db.get_active_hours_enabled(),
            "active_hours_start": config_db.get_active_hours_start(),
            "active_hours_end": config_db.get_active_hours_end(),
            "is_in_active_hours": config_db.is_in_active_hours(),
            "server_time": datetime.datetime.now().strftime("%H:%M"),
            "language": config_db.get_language(),
        }

        last_updated_dict = config_db.get_all_last_updated()

        data = []
        for c in containers:
            c_name = c.name
            auto_update = config_db.get_auto_update(c_name)
            snoozed = config_db.is_snoozed(c_name)

            last_updated_str = "Never"
            if c_name in last_updated_dict:
                try:
                    iso_str = last_updated_dict[c_name].replace("Z", "+00:00")
                    dt = datetime.datetime.fromisoformat(iso_str)
                    last_updated_str = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    last_updated_str = last_updated_dict[c_name]

            q_info = None
            if c_name in q_dict:
                r = q_dict[c_name]
                created_iso = r.get("remote_created_iso") or r.get("detected_at")
                try:
                    if created_iso:
                        clean_iso = created_iso.replace("Z", "+00:00")
                        created_at = datetime.datetime.fromisoformat(clean_iso)
                        age_days = (now - created_at).days
                        remaining = max(0, q_days_global - age_days)
                        has_warning = r.get("reset_count", 0) > 0
                        q_info = {"remaining": remaining, "has_warning": has_warning}
                    else:
                        q_info = {"remaining": "?", "has_warning": False}
                except Exception:
                    q_info = {"remaining": "?", "has_warning": False}

            data.append(
                {
                    "name": c_name,
                    "status": c.status,
                    "image": c.attrs.get("Config", {}).get("Image", "Unknown"),
                    "auto_update": auto_update,
                    "quarantine": q_info,
                    "snoozed": snoozed,
                    "last_updated": last_updated_str,
                }
            )

        data.sort(key=lambda x: x["name"])

        return render_template(
            "dashboard.html",
            containers=data,
            q_days_global=q_days_global,
            env_token=env_token,
            db_token=db_token,
            masked_token=masked_token,
            env_chat_id=env_chat_id,
            db_chat_id=db_chat_id,
            settings=settings,
        )
    except Exception:
        logger.exception("Error serving dashboard")
        return Response("Internal Server Error", 500)


def start_web_server(docker_manager: Any, config_db: Any) -> None:
    app.config["DOCKER_MANAGER"] = docker_manager
    app.config["CONFIG_DB"] = config_db

    auth_disabled = os.environ.get("WEB_AUTH_DISABLED", "").strip().lower() == "true"
    user = os.environ.get("WEB_USER")
    pw = os.environ.get("WEB_PASSWORD")
    allow_insecure_pw = os.environ.get("ALLOW_INSECURE_PASSWORD", "").strip().lower() == "true"

    if auth_disabled:
        logger.warning(
            "WEB_AUTH_DISABLED is set to true. Web Dashboard is running WITHOUT authentication!"
        )
    else:
        if not user or not pw:
            logger.error(
                "Web Dashboard failed to start: WEB_USER and WEB_PASSWORD must be configured (or set WEB_AUTH_DISABLED=true)."
            )
            return
        if not is_password_secure(pw) and not allow_insecure_pw:
            logger.error(
                "Web Dashboard failed to start: WEB_PASSWORD is too weak (<8 characters or trivial). "
                "Use a stronger password or ALLOW_INSECURE_PASSWORD=true."
            )
            return

    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "8080"))
    logger.info(f"Starting Web Dashboard on {host}:{port}")

    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=4, _quiet=True)
    except Exception as e:
        logger.warning(f"Waitress failed to start ({e}), falling back to app.run")
        app.run(host=host, port=port, debug=False, use_reloader=False)
