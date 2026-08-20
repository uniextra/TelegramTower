import os
import logging
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logger = logging.getLogger(__name__)

STRINGS = {
    'en': {
        'startup': "🤖 *TelegramTower has started!*\n\nI am ready to monitor your Docker containers.",
        'settings_main': "⚙️ *Settings Menu*\n\n• *Check Interval:* How often I check for container updates.\n• *Request Delay:* Wait time between checks to avoid rate limits.\n• *Cleanup Old Image:* Automatically delete old images after successful updates.\n• *Check Stopped:* Include stopped containers in the update checks.",
        'settings_btn': "⚙️ Settings",
        'btn_interval': "⏱ Check Interval",
        'btn_delay': "⏳ Request Delay",
        'btn_cleanup': "🧹 Cleanup Old Image",
        'btn_stopped': "🛑 Check Stopped",
        'interval_ui': "⏱ *Check Interval*\n\nCurrently checking every *{days} day(s)*.\n\nSelect a new interval:",
        'delay_ui': "⏳ *Request Delay*\n\nCurrently pausing for *{delay}s* between checks.\n\nSelect a new delay:",
        'cleanup_ui': "🧹 *Cleanup Old Image*\n\nCurrent state: *{state}*.\n\nIf enabled, I will delete the old image after a successful update.",
        'stopped_ui': "🛑 *Check Stopped Containers*\n\nCurrent state: *{state}*.\n\nIf enabled, I will check for updates on stopped containers. They will remain stopped after updating.",
        'btn_back': "🔙 Back to Settings",
        'enabled': "Enabled",
        'disabled': "Disabled",
        'day_1': "1 Day",
        'days_7': "7 Days",
        'days_30': "30 Days",
        'update_btn': "Update",
        'ignore_btn': "Ignore",
        'auto_update_btn': "🔄 Auto-Update",
        'update_msg': "🚀 Update available for container *{container}*{state}\nNew image: `{image}`",
        'state_stopped': " *(Stopped)*",
        'ignored_msg': "Ignored update for {container}. I will not notify you again until a newer version is released.",
        'updating_msg': "Updating {container}... please wait.",
        'auto_updating_msg': "Updating {container}... and setting to auto-update in the future.",
        'auto_updated_notification': "🚀 Automatically updated container *{container}* to new image:\n`{image}`",
        'btn_quarantine': "🛡️ Quarantine Delay",
        'quarantine_ui': "🛡️ *Quarantine Delay*\n\nCurrently delaying updates for *{days} day(s)*.\n\nSelect a new delay (0 to disable):",
        'quarantine_warning': "⚠️ *Warning:* Container `{container}` has skipped the quarantine period 3 times due to rapid updates.\n\nPlease check it manually to ensure it's stable.",
        'day_0': "0 Days (Off)",
        'days_3': "3 Days",
        'days_5': "5 Days",
        'update_success_running': "Updated {name} and started successfully.{cleanup}",
        'update_success_stopped': "Updated {name} and recreated successfully (kept stopped).{cleanup}",
        'cleanup_removed': " Old image removed.",
        'already_up_to_date': "Container {name} is already up to date.",
        'err_recreate': "Failed to recreate container: {error}",
        'generic_error': "Error: {error}",
        'not_found_msg': "Container {container} not found.",
        'success': "✅ Success",
        'failed': "❌ Failed"
    },
    'es': {
        'startup': "🤖 *¡TelegramTower ha iniciado!*\n\nEstoy listo para monitorizar tus contenedores Docker.",
        'settings_main': "⚙️ *Menú de Ajustes*\n\n• *Check Interval:* Cada cuánto tiempo verificaré actualizaciones.\n• *Request Delay:* Espera entre comprobaciones para evitar bloqueos por límite de peticiones.\n• *Cleanup Old Image:* Eliminar automáticamente la imagen antigua tras una actualización.\n• *Check Stopped:* Incluir contenedores detenidos en las comprobaciones.\n• *Quarantine:* Esperar X días antes de avisar/actualizar para evitar bugs de Día 0.",
        'settings_btn': "⚙️ Ajustes",
        'btn_interval': "⏱ Intervalo",
        'btn_delay': "⏳ Retraso",
        'btn_cleanup': "🧹 Limpiar Imagen",
        'btn_stopped': "🛑 Detenidos",
        'btn_quarantine': "🛡️ Cuarentena",
        'interval_ui': "⏱ *Intervalo de Comprobación*\n\nActualmente comprobando cada *{days} día(s)*.\n\nSelecciona el nuevo intervalo:",
        'delay_ui': "⏳ *Retraso de Peticiones*\n\nActualmente esperando *{delay}s* entre contenedores.\n\nSelecciona el nuevo retraso:",
        'cleanup_ui': "🧹 *Limpiar Imagen Antigua*\n\nEstado actual: *{state}*.\n\nSi está activado, borraré la imagen antigua tras actualizar con éxito.",
        'stopped_ui': "🛑 *Comprobar Contenedores Detenidos*\n\nEstado actual: *{state}*.\n\nSi está activado, buscaré actualizaciones en contenedores detenidos. Se mantendrán detenidos tras actualizarse.",
        'quarantine_ui': "🛡️ *Cuarentena de Actualizaciones*\n\nActualmente retrasando avisos *{days} día(s)*.\n\nSelecciona el nuevo retraso (0 para desactivar):",
        'quarantine_warning': "⚠️ *Aviso:* El contenedor `{container}` se ha saltado la cuarentena 3 veces por actualizaciones rápidas.\n\nPor favor, revísalo manualmente para asegurar su estabilidad.",
        'btn_back': "🔙 Volver a Ajustes",
        'enabled': "Activado",
        'disabled': "Desactivado",
        'day_0': "0 Días (Off)",
        'day_1': "1 Día",
        'days_3': "3 Días",
        'days_5': "5 Días",
        'days_7': "7 Días",
        'days_30': "30 Días",
        'update_btn': "Actualizar",
        'ignore_btn': "Ignorar",
        'auto_update_btn': "🔄 Auto-Actualizar",
        'update_msg': "🚀 Actualización disponible para *{container}*{state}\nNueva imagen: `{image}`",
        'state_stopped': " *(Detenido)*",
        'ignored_msg': "Actualización ignorada para {container}. No volveré a avisarte de esta versión específica.",
        'updating_msg': "Actualizando {container}... por favor espera.",
        'auto_updating_msg': "Actualizando {container}... y configurado para actualizarse automáticamente en el futuro.",
        'auto_updated_notification': "🚀 Contenedor *{container}* actualizado automáticamente a la nueva imagen:\n`{image}`",
        'update_success_running': "Contenedor {name} actualizado e iniciado con éxito.{cleanup}",
        'update_success_stopped': "Contenedor {name} actualizado y recreado con éxito (mantenido detenido).{cleanup}",
        'cleanup_removed': " Imagen antigua eliminada.",
        'already_up_to_date': "El contenedor {name} ya está en la última versión.",
        'err_recreate': "Error al recrear el contenedor: {error}",
        'generic_error': "Error: {error}",
        'not_found_msg': "Contenedor {container} no encontrado.",
        'success': "✅ Éxito",
        'failed': "❌ Error"
    }
}

class TelegramBot:
    def __init__(self, token, chat_id, docker_manager, config_db):
        self.token = token
        self.chat_id = chat_id
        self.docker_manager = docker_manager
        self.config_db = config_db
        self.application = Application.builder().token(self.token).build()
        self._check_job = None
        self.pending_updates = {}
        self._setup_handlers()

    def _setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("config", self.settings_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        self.application.add_error_handler(self._error_handler)

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(f"Exception while handling an update: {context.error}")

    def t(self, key, **kwargs):
        lang = self.config_db.get_language()
        text = STRINGS.get(lang, STRINGS['en']).get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text

    def format_update_result(self, result):
        if isinstance(result, tuple) and len(result) == 3:
            success, key, params = result
            if key == "update_success":
                cleanup_str = self.t('cleanup_removed') if params.get('cleaned_up') else ""
                template_key = 'update_success_running' if params.get('was_running') else 'update_success_stopped'
                return self.t(template_key, name=params.get('name', ''), cleanup=cleanup_str)
            return self.t(key, **params)
        elif isinstance(result, tuple) and len(result) == 2:
            return result[1]
        return str(result)

    def _update_language(self, update: Update):
        if update.effective_user and update.effective_user.language_code:
            lang_code = update.effective_user.language_code.lower()
            lang = 'es' if lang_code.startswith('es') else 'en'
            self.config_db.set_language(lang)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._update_language(update)
        msg, reply_markup = self._get_startup_ui()
        await update.message.reply_text(text=msg, reply_markup=reply_markup, parse_mode="Markdown")

    # --- UI Generators ---

    def _get_startup_ui(self):
        msg = self.t('startup')
        keyboard = [[InlineKeyboardButton(self.t('settings_btn'), callback_data="menu_main_settings")]]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_settings_main_ui(self):
        msg = self.t('settings_main')
        keyboard = [
            [InlineKeyboardButton(self.t('btn_interval'), callback_data="menu_set_interval")],
            [InlineKeyboardButton(self.t('btn_delay'), callback_data="menu_set_delay")],
            [InlineKeyboardButton(self.t('btn_cleanup'), callback_data="menu_set_cleanup")],
            [InlineKeyboardButton(self.t('btn_stopped'), callback_data="menu_set_stopped")],
            [InlineKeyboardButton(self.t('btn_quarantine'), callback_data="menu_set_quarantine")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_quarantine_ui(self):
        days = self.config_db.get_quarantine_days()
        msg = self.t('quarantine_ui', days=days)
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if days == 0 else ''}{self.t('day_0')}", callback_data="set_quarantine_0"),
                InlineKeyboardButton(f"{'✅ ' if days == 1 else ''}{self.t('day_1')}", callback_data="set_quarantine_1"),
                InlineKeyboardButton(f"{'✅ ' if days == 3 else ''}{self.t('days_3')}", callback_data="set_quarantine_3")
            ],
            [
                InlineKeyboardButton(f"{'✅ ' if days == 5 else ''}{self.t('days_5')}", callback_data="set_quarantine_5"),
                InlineKeyboardButton(f"{'✅ ' if days == 7 else ''}{self.t('days_7')}", callback_data="set_quarantine_7")
            ],
            [InlineKeyboardButton(self.t('btn_back'), callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_interval_ui(self):
        days = self.config_db.get_poll_interval_days()
        msg = self.t('interval_ui', days=days)
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if days == 1 else ''}{self.t('day_1')}", callback_data="set_interval_1"),
                InlineKeyboardButton(f"{'✅ ' if days == 7 else ''}{self.t('days_7')}", callback_data="set_interval_7"),
                InlineKeyboardButton(f"{'✅ ' if days == 30 else ''}{self.t('days_30')}", callback_data="set_interval_30"),
            ],
            [InlineKeyboardButton(self.t('btn_back'), callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_delay_ui(self):
        delay = self.config_db.get_request_delay_seconds()
        msg = self.t('delay_ui', delay=delay)
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if delay == 0 else ''}0s", callback_data="set_delay_0"),
                InlineKeyboardButton(f"{'✅ ' if delay == 2 else ''}2s", callback_data="set_delay_2"),
                InlineKeyboardButton(f"{'✅ ' if delay == 5 else ''}5s", callback_data="set_delay_5"),
            ],
            [InlineKeyboardButton(self.t('btn_back'), callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_cleanup_ui(self):
        enabled = self.config_db.get_cleanup_old_image()
        state = self.t('enabled') if enabled else self.t('disabled')
        msg = self.t('cleanup_ui', state=state)
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if enabled else ''}{self.t('enabled')}", callback_data="set_cleanup_1"),
                InlineKeyboardButton(f"{'✅ ' if not enabled else ''}{self.t('disabled')}", callback_data="set_cleanup_0"),
            ],
            [InlineKeyboardButton(self.t('btn_back'), callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    def _get_stopped_ui(self):
        enabled = self.config_db.get_include_stopped()
        state = self.t('enabled') if enabled else self.t('disabled')
        msg = self.t('stopped_ui', state=state)
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ ' if enabled else ''}{self.t('enabled')}", callback_data="set_stopped_1"),
                InlineKeyboardButton(f"{'✅ ' if not enabled else ''}{self.t('disabled')}", callback_data="set_stopped_0"),
            ],
            [InlineKeyboardButton(self.t('btn_back'), callback_data="menu_main_settings")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    # --- Handlers ---

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._update_language(update)
        msg, reply_markup = self._get_settings_main_ui()
        await update.message.reply_text(text=msg, reply_markup=reply_markup, parse_mode="Markdown")

    async def send_update_notification(self, container_name, new_image, is_stopped=False, remote_info=None):
        """Sends a notification with Inline Keyboard to update or ignore."""
        state_str = self.t('state_stopped') if is_stopped else ""
        msg = self.t('update_msg', container=container_name, state=state_str, image=new_image)
        
        if remote_info:
            version = remote_info.get('version')
            source = remote_info.get('source')
            lang = self.config_db.get_language()
            
            if version:
                msg += f"\n📦 Version: `{version}`" if lang == 'en' else f"\n📦 Versión: `{version}`"
            if source:
                link_text = "Changelog / Source" if lang == 'en' else "Ver código/changelog"
                msg += f"\n🔗 [{link_text}]({source})"
                
        keyboard = [
            [
                InlineKeyboardButton(self.t('update_btn'), callback_data=f"update_{container_name}"),
                InlineKeyboardButton(self.t('ignore_btn'), callback_data=f"ignore_{container_name}"),
            ],
            [
                InlineKeyboardButton(self.t('auto_update_btn'), callback_data=f"auto_{container_name}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id, text=msg, reply_markup=reply_markup, parse_mode="Markdown", disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._update_language(update)
        query = update.callback_query
        try:
            await query.answer()
        except Exception:
            pass
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
        elif data == "menu_set_quarantine":
            msg, markup = self._get_quarantine_ui()
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
            
        if data.startswith("set_quarantine_"):
            days = int(data.split("_")[-1])
            self.config_db.set_quarantine_days(days)
            msg, markup = self._get_quarantine_ui()
            await query.edit_message_text(text=msg, reply_markup=markup, parse_mode="Markdown")
            return
        
        # Update Container Handlers
        try:
            action, container_name = data.split("_", 1)
        except ValueError:
            return
            
        if action == "ignore":
            remote_digest = self.pending_updates.get(container_name)
            if not remote_digest:
                # Re-fetch it just in case memory was cleared
                include_stopped = self.config_db.get_include_stopped()
                containers = await asyncio.to_thread(self.docker_manager.get_containers, include_stopped)
                target = next((c for c in containers if c.name == container_name), None)
                if target:
                    _, remote_digest = await asyncio.to_thread(self.docker_manager.check_for_updates, target)
            
            if remote_digest:
                self.config_db.set_ignored_update(container_name, remote_digest)
                
            await query.edit_message_text(text=self.t('ignored_msg', container=container_name))
            return
            
        if action in ["update", "auto"]:
            if action == "auto":
                self.config_db.set_auto_update(container_name, True)
                await query.edit_message_text(text=self.t('auto_updating_msg', container=container_name))
            else:
                await query.edit_message_text(text=self.t('updating_msg', container=container_name))
            
            include_stopped = self.config_db.get_include_stopped()
            containers = await asyncio.to_thread(self.docker_manager.get_containers, include_stopped)
            target = next((c for c in containers if c.name == container_name), None)
            
            if not target:
                await query.edit_message_text(text=self.t('not_found_msg', container=container_name))
                return
                
            cleanup = self.config_db.get_cleanup_old_image()
            
            # Execute the heavy update process in a separate thread so it doesn't block the UI
            result = await asyncio.to_thread(self.docker_manager.update_container, target.id, cleanup)
            success = result[0]
            msg_str = self.format_update_result(result)
            
            status = self.t('success') if success else self.t('failed')
            
            if success:
                self.pending_updates.pop(container_name, None)
                
            await query.edit_message_text(text=f"{status}: {msg_str}")

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
        
        containers = await asyncio.to_thread(self.docker_manager.get_containers, include_stopped)
        for i, container in enumerate(containers):
            if i > 0 and delay > 0:
                await asyncio.sleep(delay)
                
            logger.info(f"Inspecting container {container.name} (status: {container.status})")
            new_image, remote_digest, remote_info = await asyncio.to_thread(self.docker_manager.check_for_updates, container)
            
            if new_image and remote_digest:
                ignored_digest = self.config_db.get_ignored_update(container.name)
                if ignored_digest == remote_digest:
                    logger.info(f"Update for {container.name} was previously ignored. Skipping.")
                    continue

                labels = getattr(container, 'labels', {})

                # Quarantine Check
                q_label = labels.get('telegramtower.quarantine')
                q_days = int(q_label) if q_label and q_label.isdigit() else self.config_db.get_quarantine_days()
                
                if q_days > 0:
                    q_record = self.config_db.get_quarantine_record(container.name)
                    import datetime
                    
                    now = datetime.datetime.now(datetime.timezone.utc)
                    remote_created_at = None
                    remote_created_iso = remote_info.get('created') if remote_info else None
                    if remote_created_iso:
                        try:
                            # Replace 'Z' with '+00:00' to parse isoformat correctly in older Pythons
                            clean_iso = remote_created_iso.replace('Z', '+00:00')
                            remote_created_at = datetime.datetime.fromisoformat(clean_iso)
                        except Exception as e:
                            logger.error(f"Failed to parse remote creation date {remote_created_iso}: {e}")
                    
                    if not remote_created_at:
                        # Fallback to local 'now' if we couldn't fetch remote date
                        remote_created_at = now
                        
                    age_days = (now - remote_created_at).days
                    is_in_quarantine = age_days < q_days
                    
                    if not q_record:
                        # First time seeing this update
                        if is_in_quarantine:
                            logger.info(f"Quarantine tracking started for {container.name} (age: {age_days}d, digest: {remote_digest})")
                            self.config_db.update_quarantine_record(container.name, remote_digest, 0)
                            continue
                        else:
                            # Image is already old enough! No need to quarantine.
                            logger.info(f"Container {container.name} update is {age_days}d old, bypassing {q_days}d quarantine.")
                    else:
                        if q_record['detected_digest'] == remote_digest:
                            # We are already tracking this exact update
                            if is_in_quarantine:
                                logger.info(f"Container {container.name} is in quarantine for {(q_days - age_days)} more days. Skipping.")
                                continue
                            else:
                                logger.info(f"Container {container.name} passed {q_days} days quarantine.")
                                self.config_db.delete_quarantine_record(container.name)
                        else:
                            # Digest changed during quarantine! New push detected.
                            new_count = q_record['reset_count'] + 1
                            logger.info(f"Container {container.name} digest changed during quarantine. Reset count: {new_count}")
                            
                            if new_count >= 3:
                                logger.warning(f"Container {container.name} skipped quarantine 3 times!")
                                try:
                                    await self.application.bot.send_message(
                                        chat_id=self.chat_id,
                                        text=self.t('quarantine_warning', container=container.name),
                                        parse_mode="Markdown"
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to send quarantine warning: {e}")
                                new_count = 0  # Reset after warning
                            
                            # Update DB tracking to new digest
                            self.config_db.update_quarantine_record(container.name, remote_digest, new_count)
                            
                            if is_in_quarantine:
                                continue
                            else:
                                # New digest is somehow already old enough (unlikely, but handled)
                                self.config_db.delete_quarantine_record(container.name)

                # Check Auto-update settings
                label_auto = str(labels.get('telegramtower.autoupdate', '')).lower() == 'true'
                db_auto = self.config_db.get_auto_update(container.name)
                
                if label_auto or db_auto:
                    logger.info(f"Auto-updating {container.name}...")
                    cleanup = self.config_db.get_cleanup_old_image()
                    result = await asyncio.to_thread(self.docker_manager.update_container, container.id, cleanup)
                    success = result[0]
                    msg_str = self.format_update_result(result)
                    status = self.t('success') if success else self.t('failed')
                    
                    if success:
                        msg = self.t('auto_updated_notification', container=container.name, image=new_image)
                    else:
                        msg = self.t('auto_updating_msg', container=container.name)  # fallback
                    
                    await self.application.bot.send_message(
                        chat_id=self.chat_id,
                        text=f"{msg}\n{status}: {msg_str}",
                        parse_mode="Markdown"
                    )
                    continue
                    
                # Store pending update and notify user manually
                self.pending_updates[container.name] = remote_digest
                logger.info(f"Update found for {container.name}: {new_image}. Sending notification...")
                is_stopped = container.status != 'running'
                await self.send_update_notification(container.name, new_image, is_stopped, remote_info)
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
