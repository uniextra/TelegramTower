import os
from unittest.mock import MagicMock, patch
import pytest

from web_server import app, check_auth, is_password_secure, _login_attempts


@pytest.fixture(autouse=True)
def reset_web_state():
    _login_attempts.clear()
    app.config["TESTING"] = True
    app.config["CSRF_ENABLED"] = False
    yield
    _login_attempts.clear()


def test_check_auth_fail_closed_no_env():
    with patch.dict(os.environ, {}, clear=True):
        # Fail-closed: missing credentials return False
        assert check_auth("any_user", "any_pw") is False


def test_check_auth_explicitly_disabled():
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        assert check_auth("any_user", "any_pw") is True


def test_check_auth_with_env(monkeypatch):
    monkeypatch.setenv("WEB_USER", "admin")
    monkeypatch.setenv("WEB_PASSWORD", "secret123")

    assert check_auth("admin", "secret123") is True
    assert check_auth("admin", "wrong_pw") is False
    assert check_auth("wrong_user", "secret123") is False
    assert check_auth("", "") is False
    assert check_auth(None, "secret123") is False
    assert check_auth("admin", None) is False


def test_is_password_secure():
    assert is_password_secure("admin") is False
    assert is_password_secure("password") is False
    assert is_password_secure("short") is False
    assert is_password_secure("12345678") is False
    assert is_password_secure("super_secure_pass_123") is True


def test_dashboard_save_active_hours(monkeypatch):
    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        resp = client.post(
            "/",
            data={
                "action": "save_global_settings",
                "active_hours_enabled": "on",
                "active_hours_start": "09:00",
                "active_hours_end": "01:00",
            },
        )
        assert resp.status_code == 302
        mock_config.set_active_hours_enabled.assert_called_with(True)
        mock_config.set_active_hours_start.assert_called_with("09:00")
        mock_config.set_active_hours_end.assert_called_with("01:00")


def test_dashboard_set_language_form():
    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        resp = client.post(
            "/",
            data={
                "action": "set_language",
                "language": "es",
            },
        )
        assert resp.status_code == 302
        mock_config.set_language.assert_called_with("es")


def test_dashboard_set_language_ajax():
    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        resp = client.post(
            "/",
            data={
                "action": "set_language",
                "language": "en",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "language": "en"}
        mock_config.set_language.assert_called_with("en")


def test_csrf_protection_blocks_post():
    app.config["CSRF_ENABLED"] = True
    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        # POST without CSRF token must fail with 403 Forbidden
        resp = client.post(
            "/",
            data={"action": "save_global_settings"},
        )
        assert resp.status_code == 403


def test_csrf_protection_accepts_valid_token():
    app.config["CSRF_ENABLED"] = True
    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()
    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "valid_test_token"

        resp = client.post(
            "/",
            data={
                "action": "save_global_settings",
                "csrf_token": "valid_test_token",
            },
        )
        assert resp.status_code == 302


def test_rate_limiting_brute_force():
    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()
    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    env = {"WEB_USER": "admin", "WEB_PASSWORD": "ValidPassword123"}
    with patch.dict(os.environ, env, clear=True):
        # 5 failed attempts
        import base64
        bad_auth = base64.b64encode(b"admin:wrong").decode("utf-8")
        headers = {"Authorization": f"Basic {bad_auth}"}

        for _ in range(5):
            r = client.get("/", headers=headers)
            assert r.status_code == 401

        # 6th attempt -> 429 Too Many Requests
        r6 = client.get("/", headers=headers)
        assert r6.status_code == 429


def test_empty_bot_token_does_not_clear_existing():
    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()
    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        resp = client.post(
            "/",
            data={
                "action": "save_bot_credentials",
                "bot_token": "",  # Empty
                "chat_id": "",
            },
        )
        assert resp.status_code == 302
        mock_config.set_bot_token.assert_not_called()
        mock_config.set_chat_id.assert_not_called()


def test_security_headers_and_health_endpoint():
    client = app.test_client()
    # Health endpoint without auth
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in resp.headers


def test_dashboard_renders_container_logs():
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "test_app"
    mock_container.status = "running"
    mock_container.attrs = {"Config": {"Image": "test/app:latest"}}
    mock_docker.get_containers.return_value = [mock_container]

    mock_config = MagicMock()
    mock_config.get_quarantine_days.return_value = 0
    mock_config.get_all_quarantine_records.return_value = []
    mock_config.get_bot_token.return_value = None
    mock_config.get_chat_id.return_value = None
    mock_config.get_poll_interval_days.return_value = 1
    mock_config.get_request_delay_seconds.return_value = 0
    mock_config.get_cleanup_old_image.return_value = False
    mock_config.get_include_stopped.return_value = False
    mock_config.get_events_enabled.return_value = False
    mock_config.get_events_notify_start.return_value = False
    mock_config.get_events_notify_stop.return_value = False
    mock_config.get_events_notify_health.return_value = False
    mock_config.get_events_whitelist_only.return_value = False
    mock_config.get_active_hours_enabled.return_value = False
    mock_config.get_active_hours_start.return_value = "08:00"
    mock_config.get_active_hours_end.return_value = "02:00"
    mock_config.is_in_active_hours.return_value = False
    mock_config.get_language.return_value = "en"
    mock_config.get_all_last_updated.return_value = {"test_app": "2026-11-10T08:00:00Z"}
    mock_config.get_auto_update.return_value = False
    mock_config.is_snoozed.return_value = False
    mock_config.get_all_container_logs.return_value = {
        "test_app": [
            {
                "id": 1,
                "container_name": "test_app",
                "timestamp": "2026-11-10T08:00:00Z",
                "event_type": "update_detected",
                "details": "test/app:v2.0",
            }
        ]
    }

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "test_app" in html
        assert "update_detected" in html
        assert "test/app:v2.0" in html


def test_toggle_auto_update_logs_event():
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "web_app"
    mock_docker.get_containers.return_value = [mock_container]

    mock_config = MagicMock()
    mock_config.get_auto_update.return_value = False

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {"WEB_AUTH_DISABLED": "true"}, clear=True):
        resp = client.post(
            "/",
            data={
                "action": "toggle_auto_update",
                "container_name": "web_app",
            },
        )
        assert resp.status_code == 302
        mock_config.set_auto_update.assert_called_once_with("web_app", True)
        mock_config.add_container_log.assert_called_once_with(
            "web_app", "auto_update_enabled", "Dashboard"
        )

