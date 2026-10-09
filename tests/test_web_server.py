import os
import pytest
from unittest.mock import patch

from web_server import check_auth


def test_check_auth_no_env():
    with patch.dict(os.environ, {}, clear=True):
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


def test_dashboard_save_active_hours(monkeypatch):
    from unittest.mock import MagicMock
    from web_server import app

    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {}, clear=True):
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
    from unittest.mock import MagicMock
    from web_server import app

    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {}, clear=True):
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
    from unittest.mock import MagicMock
    from web_server import app

    mock_docker = MagicMock()
    mock_docker.get_containers.return_value = []
    mock_config = MagicMock()

    app.config["DOCKER_MANAGER"] = mock_docker
    app.config["CONFIG_DB"] = mock_config

    client = app.test_client()
    with patch.dict(os.environ, {}, clear=True):
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


