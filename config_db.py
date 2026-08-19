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
            conn.execute('''
                CREATE TABLE IF NOT EXISTS quarantine_tracking (
                    container_name TEXT PRIMARY KEY,
                    detected_digest TEXT,
                    detected_at TIMESTAMP,
                    reset_count INTEGER
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
        
    def get_language(self):
        return self.get_config('language', 'en')
        
    def set_language(self, lang):
        self.set_config('language', lang)

    def get_ignored_update(self, container_name):
        return self.get_config(f'ignore_{container_name}')

    def set_ignored_update(self, container_name, digest):
        if digest:
            self.set_config(f'ignore_{container_name}', digest)

    def get_auto_update(self, container_name):
        return self.get_config(f'autoupdate_{container_name}', '0') == '1'

    def set_auto_update(self, container_name, enable):
        self.set_config(f'autoupdate_{container_name}', '1' if enable else '0')

    # Quarantine methods
    def get_quarantine_days(self):
        return int(self.get_config('quarantine_days', 0))

    def set_quarantine_days(self, days):
        self.set_config('quarantine_days', days)

    def get_quarantine_record(self, container_name):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT detected_digest, detected_at, reset_count FROM quarantine_tracking WHERE container_name = ?',
                (container_name,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'detected_digest': row[0],
                    'detected_at': row[1],
                    'reset_count': row[2]
                }
            return None

    def update_quarantine_record(self, container_name, digest, reset_count):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO quarantine_tracking (container_name, detected_digest, detected_at, reset_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(container_name) DO UPDATE SET 
                    detected_digest=excluded.detected_digest,
                    detected_at=excluded.detected_at,
                    reset_count=excluded.reset_count
            ''', (container_name, digest, now, reset_count))
            conn.commit()

    def delete_quarantine_record(self, container_name):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM quarantine_tracking WHERE container_name = ?', (container_name,))
            conn.commit()
