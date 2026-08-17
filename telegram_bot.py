import os
import logging
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token, chat_id, docker_manager, config_db):
        self.token = token
        self.chat_id = chat_id
        self.docker_manager = docker_manager
        self.config_db = config_db
        self.application = Application.builder().token(self.token).build()
        self._check_job = None
        self._setup_handlers()

    def _setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("config", self.settings_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg, reply_markup = self._get_startup_ui()
        await update.message.reply_text(text=msg, reply_markup=reply_markup, parse_mode="Markdown")

    # --- UI Generators ---

    def _get_startup_ui(self):
        msg = "🤖 *TelegramTower has started!*\n\nI am ready to monitor your Docker containers."
        keyboard = [[InlineKeyboardButton("⚙️ Settings", callback_data="menu_main_settings")]]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_settings_main_ui(self):
        msg = (
            "⚙️ *Settings Menu*\n\n"
            "• *Check Interval:* Configura cada cuánto tiempo verificaré si hay nuevas versiones de tus contenedores.\n"
            "• *Request Delay:* Configura el tiempo de espera entre cada consulta a Docker Hub para evitar bloqueos por límite de peticiones (Rate Limit).\n"
            "• *Cleanup Old Image:* Elimina automáticamente la imagen antigua después de actualizar con éxito.\n"
            "• *Check Stopped:* Si está habilitado, también actualiza contenedores detenidos (sin iniciarlos)."
        )
        keyboard = [
            [InlineKeyboardButton("⏱ Check Interval", callback_data="menu_set_interval")],
            [InlineKeyboardButton("⏳ Request Delay", callback_data="menu_set_delay")],
            [InlineKeyboardButton("🧹 Cleanup Old Image", callback_data="menu_set_cleanup")],
            [InlineKeyboardButton("🛑 Check Stopped", callback_data="menu_set_stopped")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_interval_ui(self):
        days = self.config_db.get_poll_interval_days()
        msg = f"⏱ *Check Interval*\n\nActualmente comprobando cada *{days} día(s)*.\n\nSelecciona el nuevo intervalo:"
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if days == 1 else ''}1 Day", callback_data="set_interval_1"),
                InlineKeyboardButton(f"{'✅ ' if days == 7 else ''}7 Days", callback_data="set_interval_7"),
                InlineKeyboardButton(f"{'✅ ' if days == 30 else ''}30 Days", callback_data="set_interval_30"),
            ],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_delay_ui(self):
        delay = self.config_db.get_request_delay_seconds()
        msg = f"⏳ *Request Delay*\n\nActualmente esperando *{delay}s* entre contenedores.\n\nSelecciona el nuevo tiempo de espera:"
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if delay == 0 else ''}0s", callback_data="set_delay_0"),
                InlineKeyboardButton(f"{'✅ ' if delay == 2 else ''}2s", callback_data="set_delay_2"),
                InlineKeyboardButton(f"{'✅ ' if delay == 5 else ''}5s", callback_data="set_delay_5"),
            ],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_cleanup_ui(self):
        enabled = self.config_db.get_cleanup_old_image()
        msg = f"🧹 *Cleanup Old Image*\n\nEstado actual: *{'Activado' if enabled else 'Desactivado'}*.\n\nSi está activado, borraré la imagen antigua una vez que el contenedor se haya actualizado correctamente."
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if enabled else ''}Enabled", callback_data="set_cleanup_1"),
                InlineKeyboardButton(f"{'✅ ' if not enabled else ''}Disabled", callback_data="set_cleanup_0"),
            ],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_stopped_ui(self):
        enabled = self.config_db.get_include_stopped()
        msg = f"🛑 *Check Stopped Containers*\n\nEstado actual: *{'Activado' if enabled else 'Desactivado'}*.\n\nSi está activado, buscaré actualizaciones también para contenedores que estén detenidos. Si apruebas la actualización de un contenedor detenido, se actualizará pero **se mantendrá detenido**."
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if enabled else ''}Enabled", callback_data="set_stopped_1"),
                InlineKeyboardButton(f"{'✅ ' if not enabled else ''}Disabled", callback_data="set_stopped_0"),
            ],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    # --- Handlers ---

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg, reply_markup = self._get_settings_main_ui()
        await update.message.reply_text(text=msg, reply_markup=reply_markup, parse_mode="Markdown")

    async def send_update_notification(self, container_name, new_image, is_stopped=False):
        """Sends a notification with Inline Keyboard to update or ignore."""
        keyboard = [
            [
                InlineKeyboardButton("Update", callback_data=f"update_{container_name}"),
                InlineKeyboardButton("Ignore", callback_data=f"ignore_{container_name}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        state_info = " *(Stopped)*" if is_stopped else ""
        message = f"🚀 Update available for container *{container_name}*{state_info}\nNew image: `{new_image}`"
        
        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id, text=message, reply_markup=reply_markup, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        # UI Navigation
        if data == "menu_main_settings":
            msg, markup = self._get_settings_main_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
        elif data == "menu_set_interval":
            msg, markup = self._get_interval_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
        elif data == "menu_set_delay":
            msg, markup = self._get_delay_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
        elif data == "menu_set_cleanup":
            msg, markup = self._get_cleanup_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
        elif data == "menu_set_stopped":
            msg, markup = self._get_stopped_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
            
        # Setting values
        if data.startswith("set_interval_"):
            days = int(data.split("_")[-1])
            self.config_db.set_poll_interval_days(days)
            self._reschedule_check_job(days)
            msg, markup = self._get_interval_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
            
        if data.startswith("set_delay_"):
            delay = int(data.split("_")[-1])
            self.config_db.set_request_delay_seconds(delay)
            msg, markup = self._get_delay_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
            
        if data.startswith("set_cleanup_"):
            enable = data.endswith("_1")
            self.config_db.set_cleanup_old_image(enable)
            msg, markup = self._get_cleanup_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
            
        if data.startswith("set_stopped_"):
            enable = data.endswith("_1")
            self.config_db.set_include_stopped(enable)
            msg, markup = self._get_stopped_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
        
        # Update Container Handlers
        try:
            action, container_name = data.split("_", 1)
        except ValueError:
            return
            
        if action == "ignore":
            await query.edit_message_text(text=f"Ignored update for {container_name}.")
            return
            
        if action == "update":
            await query.edit_message_text(text=f"Updating {container_name}... please wait.")
            
            include_stopped = self.config_db.get_include_stopped()
            containers = self.docker_manager.get_containers(include_stopped=include_stopped)
            target = next((c for c in containers if c.name == container_name), None)
            
            if not target:
                await query.edit_message_text(text=f"Container {container_name} not found.")
                return
                
            cleanup = self.config_db.get_cleanup_old_image()
            success, msg = self.docker_manager.update_container(target.id, cleanup_old_image=cleanup)
            status = "✅ Success" if success else "❌ Failed"
            await query.edit_message_text(text=f"{status}: {msg}")

    # --- Core Logic ---

    def _reschedule_check_job(self, days):
        if self._check_job:
            self._check_job.schedule_removal()
        
        interval_seconds = days * 24 * 60 * 60
        job_queue = self.application.job_queue
        self._check_job = job_queue.run_repeating(
            self._check_containers_job, 
            interval=interval_seconds, 
            first=interval_seconds  # don't run immediately on setting change
        )
        logger.info(f"Rescheduled check job to every {days} days.")

    async def _check_containers_job(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Checking for container updates...")
        delay = self.config_db.get_request_delay_seconds()
        include_stopped = self.config_db.get_include_stopped()
        
        containers = self.docker_manager.get_containers(include_stopped=include_stopped)
        for i, container in enumerate(containers):
            if i > 0 and delay > 0:
                await asyncio.sleep(delay)
                
            logger.info(f"Inspecting container {container.name} (status: {container.status})")
            new_image = self.docker_manager.check_for_updates(container)
            if new_image:
                logger.info(f"Update found for {container.name}: {new_image}. Sending notification...")
                is_stopped = container.status != 'running'
                await self.send_update_notification(container.name, new_image, is_stopped)
            else:
                logger.info(f"No update for {container.name}")

    async def _send_startup_message(self, context: ContextTypes.DEFAULT_TYPE):
        msg, reply_markup = self._get_startup_ui()
        try:
            await context.bot.send_message(
                chat_id=self.chat_id, text=msg, reply_markup=reply_markup, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")

    def run(self):
        """Starts the Telegram bot polling and schedules periodic checks."""
        days = self.config_db.get_poll_interval_days()
        interval_seconds = days * 24 * 60 * 60
        
        logger.info(f"Starting Telegram Bot. Checking every {days} day(s).")
        job_queue = self.application.job_queue
        
        # Schedule the startup message to run almost immediately
        job_queue.run_once(self._send_startup_message, when=1)
        
        self._check_job = job_queue.run_repeating(
            self._check_containers_job, 
            interval=interval_seconds, 
            first=10
        )
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
