import html
from telegram import Update
from telegram.ext import ContextTypes
import db
import config
from scraper import ADUScraper
from handlers.notifications import send_calendar_invite, build_google_calendar_markup

async def handle_booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data

    if not data.startswith("book:"):
        return False

    parts = data.split(":")
    profile_id = int(parts[1])
    slot_key = parts[2]
    
    profile = db.get_profile_by_id(profile_id)
    if not profile:
        await query.answer("Hata: Profil bulunamadı.", show_alert=True)
        return True

    slot_cache = context.bot_data.get('slot_cache', {})
    slot_info = slot_cache.get(slot_key)

    if not slot_info:
        await query.answer("Bu randevu seçeneğinin süresi dolmuş veya slot güncellenmiş. Lütfen yeni bildirimi bekleyin.", show_alert=True)
        return True

    await query.edit_message_text(
        text=query.message.text + f"\n\n⏳ <b>{profile['name']} için {slot_info['time']} randevusu alınıyor... Lütfen bekleyin.</b>",
        parse_mode="HTML"
    )
    
    scraper = ADUScraper()
    success, message = await scraper.book_appointment(
        specialty_id=slot_info['specialty_id'],
        polyclinic_id=slot_info['polyclinic_id'],
        slot_id=slot_info['slot_id'],
        tc_kimlik=profile['tc_kimlik'],
        dogum_tarihi=profile['dogum_tarihi'],
        telefon=profile['telefon'],
        randevu_type=slot_info.get('randevu_type', 1)
    )
    
    if success:
        finished_text = (
            query.message.text + 
            f"\n\n🎉 <b>Randevu Başarıyla Alındı!</b>\n"
            f"✅ Hastane Onay Mesajı: <i>{html.escape(message)}</i>"
        )

        gcal_keyboard = build_google_calendar_markup(
            specialty_name=slot_info.get('specialty_name', 'Uzmanlık'),
            polyclinic_name=slot_info.get('polyclinic_name', 'Poliklinik'),
            patient_name=profile['name'],
            date_str=slot_info['date'],
            time_str=slot_info['time']
        )
        await query.edit_message_text(text=finished_text, parse_mode="HTML", reply_markup=gcal_keyboard)
        await query.answer("Randevunuz başarıyla alınmıştır! 🎉", show_alert=True)

        # Send .ics attachment asynchronously
        await send_calendar_invite(
            context=context,
            chat_id=chat_id,
            patient_name=profile['name'],
            specialty_name=slot_info.get('specialty_name', 'Uzmanlık'),
            polyclinic_name=slot_info.get('polyclinic_name', 'Poliklinik'),
            date_str=slot_info['date'],
            time_str=slot_info['time']
        )
    else:
        failed_text = (
            query.message.text + 
            f"\n\n❌ <b>Randevu Alınamadı!</b>\n"
            f"⚠️ Hata Nedeni: <i>{html.escape(message)}</i>"
        )
        await query.edit_message_text(text=failed_text, parse_mode="HTML")
        await query.answer(f"Randevu alma başarısız: {message}", show_alert=True)

    return True
