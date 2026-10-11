import html
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import calendar_util
import config

async def send_calendar_invite(
    context,
    chat_id: int | str,
    patient_name: str,
    specialty_name: str,
    polyclinic_name: str,
    date_str: str,
    time_str: str,
    rtype_label: str = "ADÜ Hastane Randevusu",
    silent_mode: bool = False
):
    """Generates and sends an iCalendar (.ics) attachment to the user."""
    try:
        ics_bytes = calendar_util.generate_ics_calendar(
            specialty_name=specialty_name,
            polyclinic_name=polyclinic_name,
            patient_name=patient_name,
            date_str=date_str,
            time_str=time_str,
            rtype_label=rtype_label
        )
        ics_stream = BytesIO(ics_bytes)
        ics_stream.name = f"ADU_Randevu_{patient_name}.ics"
        await context.bot.send_document(
            chat_id=chat_id,
            document=ics_stream,
            filename=ics_stream.name,
            caption="📎 <b>Takvim Daveti:</b> Randevunuzu telefon takviminize eklemek için dosyayı açabilirsiniz.",
            parse_mode="HTML",
            disable_notification=silent_mode
        )
    except Exception as e:
        config.logger.warning(f"Could not send .ics calendar file to {chat_id}: {e}")

def build_google_calendar_markup(
    specialty_name: str,
    polyclinic_name: str,
    patient_name: str,
    date_str: str,
    time_str: str,
    rtype_label: str = "ADÜ Hastane Randevusu"
) -> InlineKeyboardMarkup:
    """Builds inline markup containing the Google Calendar direct URL button."""
    gcal_url = calendar_util.generate_google_calendar_url(
        specialty_name=specialty_name,
        polyclinic_name=polyclinic_name,
        patient_name=patient_name,
        date_str=date_str,
        time_str=time_str,
        rtype_label=rtype_label
    )
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 Google Takvime Ekle", url=gcal_url)
    ]])
