import os
import logging
from docker_manager import DockerManager
from telegram_bot import TelegramBot
from config_db import ConfigDB

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        return

    logger.info("Initializing Database...")
    config_db = ConfigDB()

    logger.info("Initializing Docker Manager...")
    docker_manager = DockerManager()

    logger.info("Initializing Telegram Bot...")
    bot = TelegramBot(bot_token, chat_id, docker_manager, config_db)

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Stopping TelegramTower...")

if __name__ == "__main__":
    main()
