import os
from unittest.mock import MagicMock, patch
import pytest

from main import _get_bot_credentials, main

VALID_TOKEN = "123456:abcdefABCDEF1234567890abcdef12345"
VALID_CHAT = "999888"


def test_get_bot_credentials_from_db():
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = VALID_TOKEN
    mock_db.get_chat_id.return_value = VALID_CHAT

    with patch.dict(os.environ, {}, clear=True):
        token, chat_id = _get_bot_credentials(mock_db)
        assert token == VALID_TOKEN
        assert chat_id == VALID_CHAT


def test_get_bot_credentials_from_env(monkeypatch):
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = None
    mock_db.get_chat_id.return_value = None

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", VALID_CHAT)

    token, chat_id = _get_bot_credentials(mock_db)
    assert token == VALID_TOKEN
    assert chat_id == VALID_CHAT


def test_get_bot_credentials_invalid_format():
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = "invalid_token_123"
    mock_db.get_chat_id.return_value = "invalid!chat"

    with patch.dict(os.environ, {}, clear=True):
        token, chat_id = _get_bot_credentials(mock_db)
        assert token is None
        assert chat_id is None


def test_get_bot_credentials_empty():
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = "   "
    mock_db.get_chat_id.return_value = ""

    with patch.dict(os.environ, {}, clear=True):
        token, chat_id = _get_bot_credentials(mock_db)
        assert token is None
        assert chat_id is None


def test_main_runs_web_server_when_credentials_missing(monkeypatch):
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = None
    mock_db.get_chat_id.return_value = None

    with patch.dict(os.environ, {}, clear=True), \
         patch("main.ConfigDB", return_value=mock_db), \
         patch("main.DockerManager") as mock_dm, \
         patch("main.threading.Thread") as mock_thread, \
         patch("threading.Event.wait", side_effect=KeyboardInterrupt):

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Web server thread should be started even though credentials are missing
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
