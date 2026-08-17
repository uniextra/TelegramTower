import sqlite3
import os

class ConfigDB:
    def __init__(self, db_path="data/config.db"):
        self.db_path = db_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            conn.commit()

    def set_config(self, key, value):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            ''', (key, str(value)))
            conn.commit()

    def get_config(self, key, default=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT value FROM config WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return default

    # Helpers
    def get_poll_interval_days(self):
        return int(self.get_config('poll_interval_days', 1))

    def set_poll_interval_days(self, days):
        self.set_config('poll_interval_days', days)

    def get_request_delay_seconds(self):
        return int(self.get_config('request_delay_seconds', 0))

    def set_request_delay_seconds(self, seconds):
        self.set_config('request_delay_seconds', seconds)

    def get_cleanup_old_image(self):
        return self.get_config('cleanup_old_image', '1') == '1'

    def set_cleanup_old_image(self, enable):
        self.set_config('cleanup_old_image', '1' if enable else '0')

    def get_include_stopped(self):
        return self.get_config('include_stopped', '0') == '1'

    def set_include_stopped(self, enable):
        self.set_config('include_stopped', '1' if enable else '0')
