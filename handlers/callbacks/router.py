from telegram import Update
from telegram.ext import ContextTypes
import db
from handlers.common import check_auth
from handlers.callbacks.menu import handle_menu_callbacks
from handlers.callbacks.profiles import handle_profile_callbacks
from handlers.callbacks.tracking import handle_tracking_callbacks
from handlers.callbacks.booking import handle_booking_callback
from handlers.callbacks.alerts import handle_alert_callback
from handlers.callbacks.admin import handle_admin_callbacks

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback query router dispatching to domain handlers."""
    query = update.callback_query
    chat_id = query.message.chat.id
    
    if not check_auth(chat_id):
        await query.answer("⚠️ Erişim yetkiniz yok!", show_alert=True)
        return
        
    db.ensure_user_exists(chat_id)
    context.user_data.pop('adding_profile', None)
    context.user_data.pop('editing_profile', None)
    
    if query.data == "noop":
        await query.answer()
        return

    await query.answer()

    # Route query to corresponding domain handler
    data = query.data
    if data.startswith("menu:") or data.startswith("settings:"):
        if await handle_menu_callbacks(update, context):
            return

    if data.startswith("profile:") or data.startswith("pref:"):
        if await handle_profile_callbacks(update, context):
            return

    if data.startswith("track:"):
        if await handle_tracking_callbacks(update, context):
            return

    if data.startswith("book:"):
        if await handle_booking_callback(update, context):
            return

    if data.startswith("alert:p:"):
        if await handle_alert_callback(update, context):
            return

    if data == "menu:admin" or data.startswith("admin:"):
        if await handle_admin_callbacks(update, context):
            return
