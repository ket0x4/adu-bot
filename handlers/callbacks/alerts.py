from telegram import Update
from telegram.ext import ContextTypes
from handlers.common import build_slot_alert_view

async def handle_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if not data.startswith("alert:p:"):
        return False

    parts = data.split(":")
    alert_id = parts[2]
    date_idx = int(parts[3])
    slot_page = int(parts[4])
    
    alert_data = context.bot_data.get('slot_alerts', {}).get(alert_id)
    if not alert_data:
        await query.answer("Bu bildirim güncellenmiş veya süresi dolmuş.", show_alert=True)
        return True
        
    text, reply_markup = build_slot_alert_view(alert_data, alert_id, date_idx=date_idx, slot_page=slot_page)
    try:
        await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        pass
    await query.answer()
    return True
