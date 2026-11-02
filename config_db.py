import contextlib
import datetime
import logging
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BOT_TOKEN_REGEX = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")
CHAT_ID_REGEX = re.compile(r"^-?\d+$|^@[A-Za-z0-9_]{5,}$")


class ConfigDB:
    def __init__(self, db_path: str = "data/config.db") -> None:
        self.db_path = db_path
        # Ensure directory exists with secure permissions where supported
        dir_path = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(dir_path, exist_ok=True)
        try:
            if os.name != "nt":
                os.chmod(dir_path, 0o700)
        except Exception:
            pass

        self._init_db()

        try:
            if os.name != "nt" and os.path.exists(self.db_path):
                os.chmod(self.db_path, 0o600)
        except Exception:
            pass

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS container_settings (
                    container_name TEXT,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (container_name, key)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quarantine_tracking (
                    container_name TEXT PRIMARY KEY,
                    detected_digest TEXT,
                    detected_at TIMESTAMP,
                    reset_count INTEGER
                )
            """)

            # Migration: add remote_created_iso if not exists
            try:
                conn.execute(
                    "ALTER TABLE quarantine_tracking ADD COLUMN remote_created_iso TEXT"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Migration: copy legacy container keys to container_settings
            try:
                cursor = conn.execute("SELECT key, value FROM config")
                for k, v in cursor.fetchall():
                    for prefix in ("auto_", "ignored_", "notified_", "snooze_", "last_updated_"):
                        if k.startswith(prefix):
                            c_name = k[len(prefix):]
                            setting_name = prefix.rstrip("_")
                            conn.execute(
                                """
                                INSERT INTO container_settings (container_name, key, value)
                                VALUES (?, ?, ?)
                                ON CONFLICT(container_name, key) DO UPDATE SET value=excluded.value
                                """,
                                (c_name, setting_name, v),
                            )
                            break
            except Exception as e:
                logger.debug(f"Migration from config to container_settings skipped: {e}")

            conn.commit()

    def set_config(self, key: str, value: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
                (key, str(value)),
            )

    def get_config(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return default

    # Container Settings Helper Methods
    def _set_container_setting(self, container_name: str, key: str, value: Any) -> None:
        val_str = str(value)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO container_settings (container_name, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(container_name, key) DO UPDATE SET value=excluded.value
                """,
                (container_name, key, val_str),
            )
            # Also update legacy config table for backwards compatibility
            legacy_key = f"{key}_{container_name}"
            conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (legacy_key, val_str),
            )

    def _get_container_setting(self, container_name: str, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT value FROM container_settings WHERE container_name = ? AND key = ?",
                (container_name, key),
            )
            row = cursor.fetchone()
            if row:
                return row[0]
            # Fallback to legacy config table
            legacy_key = f"{key}_{container_name}"
            cursor2 = conn.execute("SELECT value FROM config WHERE key = ?", (legacy_key,))
            row2 = cursor2.fetchone()
            if row2:
                return row2[0]
            return default

    def _delete_container_setting(self, container_name: str, key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM container_settings WHERE container_name = ? AND key = ?",
                (container_name, key),
            )
            legacy_key = f"{key}_{container_name}"
            conn.execute("DELETE FROM config WHERE key = ?", (legacy_key,))

    # Helpers
    def get_poll_interval_days(self) -> int:
        return int(self.get_config("poll_interval_days", 1))

    def set_poll_interval_days(self, days: int) -> None:
        self.set_config("poll_interval_days", days)

    def get_request_delay_seconds(self) -> int:
        return int(self.get_config("request_delay_seconds", 0))

    def set_request_delay_seconds(self, seconds: int) -> None:
        self.set_config("request_delay_seconds", seconds)

    def get_cleanup_old_image(self) -> bool:
        return self.get_config("cleanup_old_image", "1") == "1"

    def set_cleanup_old_image(self, enabled: bool) -> None:
        self.set_config("cleanup_old_image", "1" if enabled else "0")

    def get_include_stopped(self) -> bool:
        return self.get_config("include_stopped", "0") == "1"

    def set_include_stopped(self, enabled: bool) -> None:
        self.set_config("include_stopped", "1" if enabled else "0")

    def get_language(self) -> str:
        return self.get_config("language", "en")

    def set_language(self, lang: str) -> None:
        self.set_config("language", lang)

    def get_ignored_update(self, container_name: str) -> Optional[str]:
        return self._get_container_setting(container_name, "ignored")

    def set_ignored_update(self, container_name: str, digest: str) -> None:
        if digest:
            self._set_container_setting(container_name, "ignored", digest)

    def get_notified_update(self, container_name: str) -> Optional[str]:
        return self._get_container_setting(container_name, "notified")

    def set_notified_update(self, container_name: str, digest: str) -> None:
        if digest:
            self._set_container_setting(container_name, "notified", digest)

    def clear_notified_update(self, container_name: str) -> None:
        self._delete_container_setting(container_name, "notified")

    def get_auto_update(self, container_name: str) -> bool:
        return self._get_container_setting(container_name, "auto", "0") == "1"

    def set_auto_update(self, container_name: str, enabled: bool) -> None:
        self._set_container_setting(container_name, "auto", "1" if enabled else "0")

    def set_last_updated(self, container_name: str, timestamp: str) -> None:
        self._set_container_setting(container_name, "last_updated", timestamp)

    def get_all_last_updated(self) -> dict:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT container_name, value FROM container_settings WHERE key = 'last_updated'"
            )
            rows = cursor.fetchall()
            result = {row[0]: row[1] for row in rows}
            if not result:
                # Fallback to config table with proper LIKE ESCAPE and prefix slicing
                cursor2 = conn.execute(
                    "SELECT key, value FROM config WHERE key LIKE 'last\\_updated\\_%' ESCAPE '\\'"
                )
                for k, v in cursor2.fetchall():
                    prefix = "last_updated_"
                    if k.startswith(prefix):
                        c_name = k[len(prefix):]
                        result[c_name] = v
            return result

    def set_snooze(self, container_name: str, days: int) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        snoozed_until = (now + datetime.timedelta(days=days)).isoformat()
        self._set_container_setting(container_name, "snooze", snoozed_until)

    def get_snoozed_until(self, container_name: str) -> Optional[str]:
        return self._get_container_setting(container_name, "snooze")

    def is_snoozed(self, container_name: str) -> bool:
        snoozed_until_iso = self.get_snoozed_until(container_name)
        if not snoozed_until_iso:
            return False
        try:
            snoozed_until = datetime.datetime.fromisoformat(snoozed_until_iso)
            now = datetime.datetime.now(datetime.timezone.utc)
            return now < snoozed_until
        except ValueError:
            return False

    def clear_snooze(self, container_name: str) -> None:
        self._delete_container_setting(container_name, "snooze")

    def get_events_enabled(self) -> bool:
        return self.get_config("events_enabled", "1") == "1"

    def set_events_enabled(self, enabled: bool) -> None:
        self.set_config("events_enabled", "1" if enabled else "0")

    def get_events_notify_start(self) -> bool:
        return self.get_config("events_notify_start", "0") == "1"

    def set_events_notify_start(self, enabled: bool) -> None:
        self.set_config("events_notify_start", "1" if enabled else "0")

    def get_events_notify_stop(self) -> bool:
        return self.get_config("events_notify_stop", "1") == "1"

    def set_events_notify_stop(self, enabled: bool) -> None:
        self.set_config("events_notify_stop", "1" if enabled else "0")

    def get_events_notify_health(self) -> bool:
        return self.get_config("events_notify_health", "1") == "1"

    def set_events_notify_health(self, enabled: bool) -> None:
        self.set_config("events_notify_health", "1" if enabled else "0")

    def get_events_whitelist_only(self) -> bool:
        return self.get_config("events_whitelist_only", "0") == "1"

    def set_events_whitelist_only(self, enabled: bool) -> None:
        self.set_config("events_whitelist_only", "1" if enabled else "0")

    def get_bot_token(self) -> Optional[str]:
        return self.get_config("bot_token")

    def set_bot_token(self, token: str) -> None:
        token_str = str(token).strip() if token else ""
        if token_str and not BOT_TOKEN_REGEX.match(token_str):
            raise ValueError(f"Invalid Telegram bot token format: {token_str}")
        self.set_config("bot_token", token_str)

    def get_chat_id(self) -> Optional[str]:
        return self.get_config("chat_id")

    def set_chat_id(self, chat_id: str) -> None:
        chat_str = str(chat_id).strip() if chat_id else ""
        if chat_str and not CHAT_ID_REGEX.match(chat_str):
            raise ValueError(f"Invalid Telegram chat_id format: {chat_str}")
        self.set_config("chat_id", chat_str)

    # --- Container Settings ---
    # Quarantine methods
    def get_quarantine_days(self) -> int:
        return int(self.get_config("quarantine_days", 0))

    def set_quarantine_days(self, days: int) -> None:
        self.set_config("quarantine_days", days)

    def get_quarantine_record(self, container_name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT detected_digest, detected_at, reset_count, remote_created_iso FROM quarantine_tracking WHERE container_name = ?",
                (container_name,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "detected_digest": row[0],
                    "detected_at": row[1],
                    "reset_count": row[2],
                    "remote_created_iso": row[3],
                }
            return None

    def get_all_quarantine_records(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT container_name, detected_digest, detected_at, reset_count, remote_created_iso FROM quarantine_tracking"
            )
            rows = cursor.fetchall()
            return [
                {
                    "container_name": r[0],
                    "detected_digest": r[1],
                    "detected_at": r[2],
                    "reset_count": r[3],
                    "remote_created_iso": r[4],
                }
                for r in rows
            ]

    def update_quarantine_record(
        self,
        container_name: str,
        digest: str,
        reset_count: int,
        remote_created_iso: Optional[str] = None,
    ) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quarantine_tracking (container_name, detected_digest, detected_at, reset_count, remote_created_iso)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(container_name) DO UPDATE SET 
                    detected_digest=excluded.detected_digest,
                    detected_at=excluded.detected_at,
                    reset_count=excluded.reset_count,
                    remote_created_iso=excluded.remote_created_iso
            """,
                (container_name, digest, now, reset_count, remote_created_iso),
            )

    def delete_quarantine_record(self, container_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM quarantine_tracking WHERE container_name = ?",
                (container_name,),
            )

    # --- Active Hours (Horas Activas) ---
    def get_active_hours_enabled(self) -> bool:
        return self.get_config("active_hours_enabled", "0") == "1"

    def set_active_hours_enabled(self, enabled: bool) -> None:
        self.set_config("active_hours_enabled", "1" if enabled else "0")

    def get_active_hours_start(self) -> str:
        return self.get_config("active_hours_start", "08:00")

    def set_active_hours_start(self, time_str: str) -> None:
        self.set_config("active_hours_start", time_str)

    def get_active_hours_end(self) -> str:
        return self.get_config("active_hours_end", "02:00")

    def set_active_hours_end(self, time_str: str) -> None:
        self.set_config("active_hours_end", time_str)

    def is_in_active_hours(self, dt: Optional[datetime.datetime] = None) -> bool:
        """
        Returns True if dt (or datetime.now()) falls within the configured active hours.
        During active hours, automatic updates should not restart services.
        """
        if not self.get_active_hours_enabled():
            return False

        start_str = self.get_active_hours_start()
        end_str = self.get_active_hours_end()
        if not start_str or not end_str:
            return False

        try:
            start_parts = [int(p) for p in start_str.split(":")]
            end_parts = [int(p) for p in end_str.split(":")]
            start_time = datetime.time(start_parts[0], start_parts[1])
            end_time = datetime.time(end_parts[0], end_parts[1])
        except Exception:
            return False

        if dt is None:
            dt = datetime.datetime.now()
        current_time = dt.time()

        if start_time < end_time:
            return start_time <= current_time < end_time
        elif start_time > end_time:
            # Spans across midnight (e.g. 08:00 to 02:00)
            return current_time >= start_time or current_time < end_time
        else:
            # start == end -> covers entire 24h
            return True

    def get_seconds_until_active_hours_end(self, dt: Optional[datetime.datetime] = None) -> int:
        """
        Calculates the seconds remaining until the active hours window ends.
        """
        if dt is None:
            dt = datetime.datetime.now()
        end_str = self.get_active_hours_end()
        try:
            end_parts = [int(p) for p in end_str.split(":")]
            end_h, end_m = end_parts[0], end_parts[1]
        except Exception:
            return 0

        target_dt = dt.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if target_dt <= dt:
            target_dt += datetime.timedelta(days=1)

        diff = int((target_dt - dt).total_seconds())
        return max(0, diff)
