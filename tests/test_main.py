import os
import threading
import pytest
from unittest.mock import MagicMock, patch

from main import _get_bot_credentials, main


def test_get_bot_credentials_from_db():
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = "db_token_123"
    mock_db.get_chat_id.return_value = "db_chat_456"

    with patch.dict(os.environ, {}, clear=True):
        token, chat_id = _get_bot_credentials(mock_db)
        assert token == "db_token_123"
        assert chat_id == "db_chat_456"


def test_get_bot_credentials_from_env(monkeypatch):
    mock_db = MagicMock()
    mock_db.get_bot_token.return_value = None
    mock_db.get_chat_id.return_value = None

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "env_chat")

    token, chat_id = _get_bot_credentials(mock_db)
    assert token == "env_token"
    assert chat_id == "env_chat"


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
         patch("main.time.sleep", side_effect=KeyboardInterrupt):
        
        main()

        # Web server thread should be started even though credentials are missing
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
