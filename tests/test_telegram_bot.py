import pytest
from unittest.mock import MagicMock, AsyncMock
from telegram_bot import TelegramBot

@pytest.fixture
def mock_docker_manager():
    return MagicMock()

@pytest.fixture
def mock_config_db():
    return MagicMock()

def test_telegram_bot_init(mock_docker_manager, mock_config_db, mocker):
    mocker.patch('telegram.ext.ApplicationBuilder.build', return_value=MagicMock())
    
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)
    assert bot.token == "fake_token"
    assert bot.chat_id == "fake_chat_id"
    assert bot.docker_manager == mock_docker_manager

@pytest.mark.asyncio
async def test_button_handler_ignore(mock_docker_manager, mock_config_db, mocker):
    mocker.patch('telegram.ext.ApplicationBuilder.build', return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)
    
    mock_update = MagicMock()
    mock_update.callback_query.data = "ignore_mycontainer"
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    
    mock_context = MagicMock()
    
    await bot.button_handler(mock_update, mock_context)
    
    mock_update.callback_query.answer.assert_called_once()
    mock_update.callback_query.edit_message_text.assert_called_once()

@pytest.mark.asyncio
async def test_button_handler_update(mock_docker_manager, mock_config_db, mocker):
    mocker.patch('telegram.ext.ApplicationBuilder.build', return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)
    
    # Mock container
    mock_container = MagicMock()
    mock_container.name = "mycontainer"
    mock_container.id = "12345"
    mock_docker_manager.get_containers.return_value = [mock_container]
    mock_docker_manager.update_container.return_value = (True, "update_success_running", {"name": "mycontainer", "cleanup": " Old image removed."})
    mock_config_db.get_cleanup_old_image.return_value = True
    mock_config_db.get_language.return_value = 'en'
    
    mock_update = MagicMock()
    mock_update.callback_query.data = "update_mycontainer"
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    
    mock_context = MagicMock()
    
    await bot.button_handler(mock_update, mock_context)
    
    mock_docker_manager.update_container.assert_called_once_with("12345", True)
    mock_update.callback_query.edit_message_text.assert_called_with(text="✅ Success: Updated mycontainer and started successfully. Old image removed.")
