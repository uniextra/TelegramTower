import datetime
import os
import sqlite3
from typing import Any, Dict, List, Optional


class ConfigDB:
    def __init__(self, db_path: str = "data/config.db") -> None:
        self.db_path = db_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
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

            conn.commit()

    def set_config(self, key: str, value: Any) -> None:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
                (key, str(value)),
            )
            conn.commit()

    def get_config(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return default

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
        return self.get_config(f"ignored_{container_name}")

    def set_ignored_update(self, container_name: str, digest: str) -> None:
        if digest:
            self.set_config(f"ignored_{container_name}", digest)

    def get_auto_update(self, container_name: str) -> bool:
        return self.get_config(f"auto_{container_name}", "0") == "1"

    def set_auto_update(self, container_name: str, enabled: bool) -> None:
        self.set_config(f"auto_{container_name}", "1" if enabled else "0")

    def set_last_updated(self, container_name: str, timestamp: str) -> None:
        self.set_config(f"last_updated_{container_name}", timestamp)
        
    def get_all_last_updated(self) -> dict:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            cursor = conn.execute("SELECT key, value FROM config WHERE key LIKE 'last_updated_%'")
            rows = cursor.fetchall()
            return {row[0].replace("last_updated_", ""): row[1] for row in rows}

    def set_snooze(self, container_name: str, days: int) -> None:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        snoozed_until = (now + datetime.timedelta(days=days)).isoformat()
        self.set_config(f"snooze_{container_name}", snoozed_until)

    def get_snoozed_until(self, container_name: str) -> Optional[str]:
        return self.get_config(f"snooze_{container_name}")

    def is_snoozed(self, container_name: str) -> bool:
        snoozed_until_iso = self.get_snoozed_until(container_name)
        if not snoozed_until_iso:
            return False
        import datetime
        try:
            snoozed_until = datetime.datetime.fromisoformat(snoozed_until_iso)
            now = datetime.datetime.now(datetime.timezone.utc)
            return now < snoozed_until
        except ValueError:
            return False

    def clear_snooze(self, container_name: str) -> None:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            conn.execute("DELETE FROM config WHERE key = ?", (f"snooze_{container_name}",))
            conn.commit()

    def get_events_enabled(self) -> bool: return self.get_config("events_enabled", "1") == "1"
    def set_events_enabled(self, enabled: bool) -> None: self.set_config("events_enabled", "1" if enabled else "0")

    def get_events_notify_start(self) -> bool: return self.get_config("events_notify_start", "0") == "1"
    def set_events_notify_start(self, enabled: bool) -> None: self.set_config("events_notify_start", "1" if enabled else "0")

    def get_events_notify_stop(self) -> bool: return self.get_config("events_notify_stop", "1") == "1"
    def set_events_notify_stop(self, enabled: bool) -> None: self.set_config("events_notify_stop", "1" if enabled else "0")

    def get_events_notify_health(self) -> bool: return self.get_config("events_notify_health", "1") == "1"
    def set_events_notify_health(self, enabled: bool) -> None: self.set_config("events_notify_health", "1" if enabled else "0")
    
    def get_events_whitelist_only(self) -> bool: return self.get_config("events_whitelist_only", "0") == "1"
    def set_events_whitelist_only(self, enabled: bool) -> None: self.set_config("events_whitelist_only", "1" if enabled else "0")

    def get_bot_token(self) -> Optional[str]:
        return self.get_config("bot_token")

    def set_bot_token(self, token: str) -> None:
        self.set_config("bot_token", token)

    def get_chat_id(self) -> Optional[str]:
        return self.get_config("chat_id")

    def set_chat_id(self, chat_id: str) -> None:
        self.set_config("chat_id", chat_id)

    # --- Container Settings ---
    # Quarantine methods
    def get_quarantine_days(self) -> int:
        return int(self.get_config("quarantine_days", 0))

    def set_quarantine_days(self, days: int) -> None:
        self.set_config("quarantine_days", days)

    def get_quarantine_record(self, container_name: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
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
        with sqlite3.connect(self.db_path, timeout=15) as conn:
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
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path, timeout=15) as conn:
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
            conn.commit()

    def delete_quarantine_record(self, container_name: str) -> None:
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            conn.execute(
                "DELETE FROM quarantine_tracking WHERE container_name = ?",
                (container_name,),
            )
            conn.commit()

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
