import pytest
from unittest.mock import MagicMock

from event_monitor import EventMonitor, escape_markdown


def test_escape_markdown():
    assert escape_markdown("my_nginx_app") == r"my\_nginx\_app"
    assert escape_markdown("app*name") == r"app\*name"
    assert escape_markdown("bracket[test]") == r"bracket\[test]"
    assert escape_markdown("code`block`") == r"code\`block\`"
    assert escape_markdown("all_*[`test") == r"all\_\*\[\`test"
    assert escape_markdown("") == ""
    assert escape_markdown(None) == ""


def test_should_monitor_none_labels():
    mock_config = MagicMock()
    mock_config.get_events_whitelist_only.return_value = False
    monitor = EventMonitor.__new__(EventMonitor)
    monitor.config_db = mock_config

    assert monitor._should_monitor(None) is True
    assert monitor._should_monitor({}) is True


def test_should_monitor_none_label_values():
    mock_config = MagicMock()
    mock_config.get_events_whitelist_only.return_value = False
    monitor = EventMonitor.__new__(EventMonitor)
    monitor.config_db = mock_config

    labels = {"telegram-notifier.monitor": None, "telegramtower.events": None}
    assert monitor._should_monitor(labels) is True


def test_should_monitor_disabled():
    mock_config = MagicMock()
    mock_config.get_events_whitelist_only.return_value = False
    monitor = EventMonitor.__new__(EventMonitor)
    monitor.config_db = mock_config

    assert monitor._should_monitor({"telegram-notifier.monitor": "false"}) is False
    assert monitor._should_monitor({"telegramtower.events": "false"}) is False


def test_should_monitor_whitelist_only():
    mock_config = MagicMock()
    mock_config.get_events_whitelist_only.return_value = True
    monitor = EventMonitor.__new__(EventMonitor)
    monitor.config_db = mock_config

    assert monitor._should_monitor({}) is False
    assert monitor._should_monitor({"telegramtower.events": "true"}) is True
    assert monitor._should_monitor({"telegram-notifier.monitor": "true"}) is True
