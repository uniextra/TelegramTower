import os
import sqlite3
import pytest
from unittest.mock import patch

from config_db import ConfigDB


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_config.db"
    return str(db_file)


def test_init_db_pragmas(temp_db):
    db = ConfigDB(temp_db)
    with sqlite3.connect(temp_db) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        # In SQLite, WAL mode is persisted on file
        assert journal_mode.lower() == "wal"


def test_sqlite_connect_timeout(temp_db):
    with patch("sqlite3.connect", wraps=sqlite3.connect) as mock_connect:
        db = ConfigDB(temp_db)
        # Verify that connect was called with timeout=15
        assert any(
            call.kwargs.get("timeout") == 15 or (len(call.args) > 1 and call.args[1] == 15)
            for call in mock_connect.call_args_list
        )


def test_config_db_get_set(temp_db):
    db = ConfigDB(temp_db)
    db.set_config("test_key", "test_val")
    assert db.get_config("test_key") == "test_val"
    assert db.get_config("nonexistent", "default") == "default"


def test_bot_credentials_get_set(temp_db):
    db = ConfigDB(temp_db)
    assert db.get_bot_token() is None
    assert db.get_chat_id() is None
    db.set_bot_token("123:ABC")
    db.set_chat_id("999888")
    assert db.get_bot_token() == "123:ABC"
    assert db.get_chat_id() == "999888"
