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


def test_active_hours_logic(temp_db):
    import datetime
    db = ConfigDB(temp_db)

    # Defaults: disabled, 08:00 to 02:00
    assert db.get_active_hours_enabled() is False
    assert db.get_active_hours_start() == "08:00"
    assert db.get_active_hours_end() == "02:00"

    # When disabled, is_in_active_hours is always False
    now_day = datetime.datetime(2026, 10, 9, 14, 0)
    assert db.is_in_active_hours(now_day) is False

    # Enable
    db.set_active_hours_enabled(True)
    assert db.get_active_hours_enabled() is True

    # Test crossing midnight: 08:00 to 02:00
    # 14:00 -> within active hours
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 9, 14, 0)) is True
    # 23:59 -> within active hours
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 9, 23, 59)) is True
    # 01:30 -> within active hours
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 10, 1, 30)) is True
    # 02:00 -> outside active hours (update window!)
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 10, 2, 0)) is False
    # 04:00 -> outside active hours
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 10, 4, 0)) is False
    # 07:59 -> outside active hours
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 10, 7, 59)) is False

    # Test seconds until end: at 14:00, target 02:00 tomorrow (12 hours = 43200s)
    secs = db.get_seconds_until_active_hours_end(datetime.datetime(2026, 10, 9, 14, 0))
    assert secs == 12 * 3600

    # At 01:00 on the same night, target 02:00 (1 hour = 3600s)
    secs_night = db.get_seconds_until_active_hours_end(datetime.datetime(2026, 10, 10, 1, 0))
    assert secs_night == 3600

    # Test non-crossing midnight: 09:00 to 18:00
    db.set_active_hours_start("09:00")
    db.set_active_hours_end("18:00")
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 9, 8, 59)) is False
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 9, 9, 0)) is True
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 9, 17, 59)) is True
    assert db.is_in_active_hours(datetime.datetime(2026, 10, 9, 18, 0)) is False

