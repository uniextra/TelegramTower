import logging
import os

from config_db import ConfigDB
from docker_manager import DockerManager
from telegram_bot import TelegramBot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


import threading

from web_server import start_web_server


def main():
    logger.info("Initializing Database...")
    config_db = ConfigDB()

    env_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    db_bot_token = config_db.get_bot_token()
    
    bot_token = db_bot_token or env_bot_token
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        return

    logger.info("Initializing Docker Manager...")
    docker_manager = DockerManager()

    logger.info("Initializing Web Dashboard Thread...")
    web_thread = threading.Thread(
        target=start_web_server, args=(docker_manager, config_db), daemon=True
    )
    web_thread.start()

    logger.info("Initializing Telegram Bot...")
    bot = TelegramBot(bot_token, chat_id, docker_manager, config_db)

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Stopping TelegramTower...")


if __name__ == "__main__":
    main()
