import datetime
import logging
import os
from functools import wraps
from typing import Any, Callable

from flask import Flask, Response, redirect, render_template, request, url_for

logger = logging.getLogger(__name__)

app = Flask(__name__)


def check_auth(username: str, password: str) -> bool:
    user = os.environ.get("WEB_USER")
    pw = os.environ.get("WEB_PASSWORD")
    if not user or not pw:
        return True  # Auth disabled if not set
    return username == user and password == pw


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
        auth = request.authorization
        if (os.environ.get("WEB_USER") and os.environ.get("WEB_PASSWORD")) and (
            not auth or not check_auth(auth.username, auth.password)
        ):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


@app.route("/", methods=["GET", "POST"])
@requires_auth
def dashboard() -> Any:
    try:
        docker_manager = app.config["DOCKER_MANAGER"]
        config_db = app.config["CONFIG_DB"]

        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_bot_token":
                new_token = request.form.get("bot_token", "").strip()
                if new_token:
                    config_db.set_bot_token(new_token)
                else:
                    config_db.set_bot_token("")
            elif action == "save_global_settings":
                try:
                    config_db.set_poll_interval_days(int(request.form.get("poll_interval_days") or 1))
                    config_db.set_request_delay_seconds(int(request.form.get("request_delay_seconds") or 0))
                    config_db.set_quarantine_days(int(request.form.get("quarantine_days") or 0))
                except ValueError:
                    pass
                
                config_db.set_cleanup_old_image(request.form.get("cleanup_old_image") == "on")
                config_db.set_include_stopped(request.form.get("include_stopped") == "on")
                
                config_db.set_events_enabled(request.form.get("events_enabled") == "on")
                config_db.set_events_notify_start(request.form.get("events_notify_start") == "on")
                config_db.set_events_notify_stop(request.form.get("events_notify_stop") == "on")
                config_db.set_events_notify_health(request.form.get("events_notify_health") == "on")
                config_db.set_events_whitelist_only(request.form.get("events_whitelist_only") == "on")
            elif action == "toggle_auto_update":
                container_name = request.form.get("container_name")
                if container_name:
                    current_val = config_db.get_auto_update(container_name)
                    config_db.set_auto_update(container_name, not current_val)
            elif action == "clear_snooze":
                container_name = request.form.get("container_name")
                if container_name:
                    config_db.clear_snooze(container_name)

            return redirect(url_for("dashboard"))

        include_stopped = config_db.get_include_stopped()
        containers = docker_manager.get_containers(include_stopped=include_stopped)

        records = config_db.get_all_quarantine_records()
        q_dict = {r["container_name"]: r for r in records}

        q_days_global = config_db.get_quarantine_days()
        now = datetime.datetime.now(datetime.timezone.utc)
        
        env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        db_token = config_db.get_bot_token() or ""
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
        }

        data = []
        for c in containers:
            c_name = c.name
            auto_update = config_db.get_auto_update(c_name)
            snoozed = config_db.is_snoozed(c_name)

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
                }
            )

        data.sort(key=lambda x: x["name"])

        return render_template(
            "dashboard.html", 
            containers=data, 
            q_days_global=q_days_global,
            env_token=env_token,
            db_token=db_token,
            settings=settings
        )
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return f"Error serving dashboard: {e}", 500


def start_web_server(docker_manager: Any, config_db: Any) -> None:
    app.config["DOCKER_MANAGER"] = docker_manager
    app.config["CONFIG_DB"] = config_db
    logger.info("Starting Web Dashboard on port 8080")
    # use_reloader=False is required when running in a background thread
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
