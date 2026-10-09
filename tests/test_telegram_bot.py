from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot import TelegramBot


@pytest.fixture
def mock_docker_manager():
    return MagicMock()


@pytest.fixture
def mock_config_db():
    return MagicMock()


def test_telegram_bot_init(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())

    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)
    assert bot.token == "fake_token"
    assert bot.chat_id == "fake_chat_id"
    assert bot.docker_manager == mock_docker_manager


@pytest.mark.asyncio
async def test_button_handler_ignore(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
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
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)

    # Mock container
    mock_container = MagicMock()
    mock_container.name = "mycontainer"
    mock_container.id = "12345"
    mock_docker_manager.get_containers.return_value = [mock_container]
    mock_docker_manager.update_container.return_value = (
        True,
        "update_success_running",
        {"name": "mycontainer", "cleanup": " Old image removed."},
    )
    mock_config_db.get_cleanup_old_image.return_value = True
    mock_config_db.get_language.return_value = "en"

    mock_update = MagicMock()
    mock_update.callback_query.data = "update_mycontainer"
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()

    mock_context = MagicMock()

    await bot.button_handler(mock_update, mock_context)

    mock_docker_manager.update_container.assert_called_once_with("12345", True)
    mock_update.callback_query.edit_message_text.assert_called_with(
        text="✅ Success: Updated mycontainer and started successfully. Old image removed."
    )


@pytest.mark.asyncio
async def test_button_handler_update_with_dependents(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)

    mock_container = MagicMock()
    mock_container.name = "gluetun"
    mock_container.id = "vpn123"
    mock_docker_manager.get_containers.return_value = [mock_container]
    mock_docker_manager.update_container.return_value = (
        True,
        "update_success",
        {
            "name": "gluetun",
            "was_running": True,
            "cleaned_up": True,
            "dependents": ["radarr", "qbittorrent"],
        },
    )
    mock_config_db.get_cleanup_old_image.return_value = True
    mock_config_db.get_language.return_value = "es"

    mock_update = MagicMock()
    mock_update.callback_query.data = "update_gluetun"
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()

    mock_context = MagicMock()
    await bot.button_handler(mock_update, mock_context)

    expected_text = (
        "✅ Éxito: Contenedor gluetun actualizado e iniciado con éxito. Imagen antigua eliminada.\n"
        "🔗 Servicios dependientes del stack recreados: radarr, qbittorrent."
    )
    mock_update.callback_query.edit_message_text.assert_called_with(text=expected_text)


@pytest.mark.asyncio
async def test_active_hours_command(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)
    mock_config_db.get_language.return_value = "es"
    mock_config_db.get_active_hours_enabled.return_value = False
    mock_config_db.get_active_hours_start.return_value = "08:00"
    mock_config_db.get_active_hours_end.return_value = "02:00"

    # Test /activehours with no args
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    await bot.active_hours_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "Configuración de Horas Activas" in update.message.reply_text.call_args[0][0]

    # Test /activehours on
    update.message.reply_text.reset_mock()
    context.args = ["on"]
    await bot.active_hours_command(update, context)
    mock_config_db.set_active_hours_enabled.assert_called_with(True)
    update.message.reply_text.assert_called_once()

    # Test /activehours 09:00 01:00
    update.message.reply_text.reset_mock()
    context.args = ["09:00", "01:00"]
    await bot.active_hours_command(update, context)
    mock_config_db.set_active_hours_start.assert_called_with("09:00")
    mock_config_db.set_active_hours_end.assert_called_with("01:00")
    mock_config_db.set_active_hours_enabled.assert_called_with(True)
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_button_handler_active_hours(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)
    mock_config_db.get_language.return_value = "es"
    mock_config_db.get_active_hours_enabled.return_value = False
    mock_config_db.get_active_hours_start.return_value = "08:00"
    mock_config_db.get_active_hours_end.return_value = "02:00"
    mock_config_db.is_in_active_hours.return_value = False

    # Open active hours menu
    update = MagicMock()
    update.callback_query.data = "menu_set_active_hours"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    context = MagicMock()

    await bot.button_handler(update, context)
    update.callback_query.edit_message_text.assert_called_once()
    assert "Horas Activas" in update.callback_query.edit_message_text.call_args[1]["text"]

    # Toggle enable
    update.callback_query.data = "set_active_hours_1"
    await bot.button_handler(update, context)
    mock_config_db.set_active_hours_enabled.assert_called_with(True)

    # Preset 08:00 - 02:00
    update.callback_query.data = "set_active_hours_p_0800_0200"
    await bot.button_handler(update, context)
    mock_config_db.set_active_hours_start.assert_called_with("08:00")
    mock_config_db.set_active_hours_end.assert_called_with("02:00")
    mock_config_db.set_active_hours_enabled.assert_called_with(True)


@pytest.mark.asyncio
async def test_check_containers_job_defers_during_active_hours(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)

    # Setup container with auto-update
    mock_container = MagicMock()
    mock_container.name = "plex"
    mock_container.id = "plex123"
    mock_container.status = "running"
    mock_container.labels = {}
    mock_docker_manager.get_containers.return_value = [mock_container]
    mock_docker_manager.check_for_updates.return_value = ("plex:latest", "sha256:abc", {}, False)

    mock_config_db.is_snoozed.return_value = False
    mock_config_db.get_ignored_update.return_value = None
    mock_config_db.get_quarantine_days.return_value = 0
    mock_config_db.get_quarantine_record.return_value = None
    mock_config_db.get_auto_update.return_value = True
    # Active hours is IN EFFECT
    mock_config_db.is_in_active_hours.return_value = True
    mock_config_db.get_active_hours_start.return_value = "08:00"
    mock_config_db.get_active_hours_end.return_value = "02:00"
    mock_config_db.get_seconds_until_active_hours_end.return_value = 3600

    bot._schedule_deferred_active_hours_check = MagicMock()

    context = MagicMock()
    await bot._check_containers_job(context)

    # Must NOT call update_container during active hours
    mock_docker_manager.update_container.assert_not_called()
    # Must have called schedule deferred check
    bot._schedule_deferred_active_hours_check.assert_called_once()


@pytest.mark.asyncio
async def test_language_command(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)

    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()

    # /language es
    context.args = ["es"]
    await bot.language_command(update, context)
    mock_config_db.set_language.assert_called_with("es")
    update.message.reply_text.assert_called()

    # /language en
    context.args = ["en"]
    await bot.language_command(update, context)
    mock_config_db.set_language.assert_called_with("en")

    # /language without args shows menu
    context.args = []
    await bot.language_command(update, context)
    assert update.message.reply_text.call_count >= 3


@pytest.mark.asyncio
async def test_button_handler_language(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)

    update = MagicMock()
    update.callback_query = AsyncMock()
    context = MagicMock()

    # Open language menu
    update.callback_query.data = "menu_set_language"
    await bot.button_handler(update, context)
    update.callback_query.edit_message_text.assert_called()

    # Set Spanish
    update.callback_query.data = "set_lang_es"
    await bot.button_handler(update, context)
    mock_config_db.set_language.assert_called_with("es")

    # Set English
    update.callback_query.data = "set_lang_en"
    await bot.button_handler(update, context)
    mock_config_db.set_language.assert_called_with("en")


def test_update_language_respects_manual_config(mock_docker_manager, mock_config_db, mocker):
    mocker.patch("telegram.ext.ApplicationBuilder.build", return_value=MagicMock())
    bot = TelegramBot("fake_token", "fake_chat_id", mock_docker_manager, mock_config_db)

    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.language_code = "en"

    # If language is already explicitly set in DB, do not overwrite
    mock_config_db.get_config.return_value = "es"
    bot._update_language(update)
    mock_config_db.set_language.assert_not_called()

    # If language is not set in DB, auto-detect
    mock_config_db.get_config.return_value = None
    bot._update_language(update)
    mock_config_db.set_language.assert_called_with("en")



