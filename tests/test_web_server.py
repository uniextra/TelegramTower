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
