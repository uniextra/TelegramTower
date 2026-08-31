import threading
import logging
import docker
import time

logger = logging.getLogger(__name__)

class EventMonitor:
    def __init__(self, config_db, telegram_callback):
        self.config_db = config_db
        self.telegram_callback = telegram_callback
        self.client = docker.from_env()
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _should_monitor(self, labels):
        import os
        env_whitelist = os.environ.get("ONLY_WHITELIST", "").lower() == "true"
        whitelist_only = self.config_db.get_events_whitelist_only() or env_whitelist
        
        # Check standard watchtower/telegramtower enable labels first (for strict disable)
        # However, as discussed with the user, we want to separate events from updates.
        # But we definitely check telegram-notifier.monitor and telegramtower.events.
        monitor_val = labels.get("telegram-notifier.monitor", labels.get("telegramtower.events", "")).lower()
        
        if monitor_val == "false":
            return False
            
        if whitelist_only and monitor_val != "true":
            return False
            
        return True

    def _listen(self):
        logger.info("Starting Docker Event Monitor...")
        while not self._stop_event.is_set():
            try:
                # We use filters to reduce the amount of data processed
                filters = {"type": ["container"], "event": ["start", "die", "health_status"]}
                for event in self.client.events(decode=True, filters=filters):
                    if self._stop_event.is_set():
                        break
                    
                    if not self.config_db.get_events_enabled():
                        continue

                    action = event.get("Action", "")
                    actor = event.get("Actor", {})
                    name = actor.get("Attributes", {}).get("name", "Unknown")
                    labels = actor.get("Attributes", {})

                    if not self._should_monitor(labels):
                        continue
                        
                    lang = self.config_db.get_language()

                    if action == "start" and self.config_db.get_events_notify_start():
                        msg_es = f"✅ Contenedor *{name}* ha iniciado."
                        msg_en = f"✅ Container *{name}* has started."
                        self.telegram_callback(name, "start", msg_es if lang == "es" else msg_en)
                        
                    elif action == "die" and self.config_db.get_events_notify_stop():
                        exit_code = actor.get("Attributes", {}).get("exitCode", "unknown")
                        if exit_code == "0":
                            msg_es = f"⏹ Contenedor *{name}* se detuvo (Salida normal 0)."
                            msg_en = f"⏹ Container *{name}* stopped (Exit code 0)."
                        else:
                            msg_es = f"🔴 *¡ALERTA!* Contenedor *{name}* se detuvo inesperadamente (Error {exit_code})."
                            msg_en = f"🔴 *ALERT!* Container *{name}* stopped unexpectedly (Exit code {exit_code})."
                        self.telegram_callback(name, "die", msg_es if lang == "es" else msg_en)

                    elif "health_status" in action and self.config_db.get_events_notify_health():
                        if "health_status: healthy" in action:
                            msg_es = f"❤️ Contenedor *{name}* ahora está Healthy."
                            msg_en = f"❤️ Container *{name}* is now Healthy."
                            self.telegram_callback(name, "healthy", msg_es if lang == "es" else msg_en)
                        elif "health_status: unhealthy" in action:
                            msg_es = f"🤒 *¡ALERTA!* Contenedor *{name}* está Unhealthy."
                            msg_en = f"🤒 *ALERT!* Container *{name}* is Unhealthy."
                            self.telegram_callback(name, "unhealthy", msg_es if lang == "es" else msg_en)

            except Exception as e:
                logger.error(f"Event Monitor Error: {e}")
                time.sleep(5)
