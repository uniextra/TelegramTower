import logging
import os
import threading
import time

from config_db import ConfigDB
from docker_manager import DockerManager
from event_monitor import EventMonitor
from telegram_bot import TelegramBot
from web_server import start_web_server

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def _get_bot_credentials(config_db: ConfigDB):
    bot_token = config_db.get_bot_token() or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = config_db.get_chat_id() or os.environ.get("TELEGRAM_CHAT_ID")
    if bot_token:
        bot_token = bot_token.strip()
    if chat_id:
        chat_id = chat_id.strip()
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

    if not bot_token or not chat_id:
        logger.info(
            "TelegramTower Web Dashboard is running in setup mode on port 8080 waiting for bot credentials..."
        )
        try:
            while not bot_token or not chat_id:
                time.sleep(2)
                bot_token, chat_id = _get_bot_credentials(config_db)
        except KeyboardInterrupt:
            logger.info("Stopping TelegramTower...")
            return

    logger.info("Initializing Telegram Bot...")
    bot = TelegramBot(bot_token, chat_id, docker_manager, config_db)

    logger.info("Initializing Docker Event Monitor...")
    event_monitor = EventMonitor(config_db, bot.handle_event_sync)
    event_monitor.start()

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Stopping TelegramTower...")
    finally:
        event_monitor.stop()


if __name__ == "__main__":
    main()
