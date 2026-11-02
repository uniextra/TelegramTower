import logging
import os
import re
import signal
import sys
import threading
import time

from config_db import ConfigDB
from docker_manager import DockerManager
from event_monitor import EventMonitor
from telegram_bot import TelegramBot
from web_server import start_web_server

log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=log_level
)
logger = logging.getLogger(__name__)

# Prevent token leaks in HTTP client logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BOT_TOKEN_REGEX = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")
CHAT_ID_REGEX = re.compile(r"^-?\d+$|^@[A-Za-z0-9_]{5,}$")


def _get_bot_credentials(config_db: ConfigDB):
    # Prefer env vars over DB to avoid persisting tokens on disk when provided via environment
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or config_db.get_bot_token()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config_db.get_chat_id()

    if bot_token:
        bot_token = bot_token.strip()
        if not BOT_TOKEN_REGEX.match(bot_token):
            logger.warning("TELEGRAM_BOT_TOKEN format is invalid.")
            bot_token = None

    if chat_id:
        chat_id = chat_id.strip()
        if not CHAT_ID_REGEX.match(chat_id):
            logger.warning("TELEGRAM_CHAT_ID format is invalid.")
            chat_id = None

    return bot_token or None, chat_id or None


def main():
    logger.info("Initializing Database...")
    config_db = ConfigDB()

    logger.info("Initializing Docker Manager...")
    docker_manager = DockerManager()

    logger.info("Initializing Web Dashboard Thread...")
    web_thread = threading.Thread(
        target=start_web_server, args=(docker_manager, config_db), daemon=True
    )
    web_thread.start()

    bot_token, chat_id = _get_bot_credentials(config_db)

    stop_event = threading.Event()

    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, stopping TelegramTower...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    if not bot_token or not chat_id:
        logger.info(
            "TelegramTower Web Dashboard is running in setup mode waiting for bot credentials..."
        )
        while not stop_event.is_set() and (not bot_token or not chat_id):
            stop_event.wait(2)
            bot_token, chat_id = _get_bot_credentials(config_db)

        if stop_event.is_set():
            logger.info("Exiting setup mode...")
            return

    logger.info("Initializing Telegram Bot...")
    bot = TelegramBot(bot_token, chat_id, docker_manager, config_db)

    logger.info("Initializing Docker Event Monitor...")
    event_monitor = EventMonitor(config_db, bot.handle_event_sync)
    event_monitor.start()

    try:
        bot.run()
    except Exception as e:
        logger.error(f"Error running Telegram bot: {e}")
    finally:
        event_monitor.stop()
        logger.info("TelegramTower stopped.")


if __name__ == "__main__":
    main()
