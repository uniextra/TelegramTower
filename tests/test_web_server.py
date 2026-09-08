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
