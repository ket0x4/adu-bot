import re
import math
import string
import secrets
import datetime
import sys
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

CLEAN_RE = re.compile(r'[^a-zA-Z0-9]')

def _get_db():
    handlers = sys.modules.get('handlers')
    if handlers and hasattr(handlers, 'db'):
        return handlers.db
    import db
    return db

def _get_config():
    handlers = sys.modules.get('handlers')
    if handlers and hasattr(handlers, 'config'):
        return handlers.config
    import config
    return config

def clean_turkish(s: str) -> str:
    """Cleans a string for safe, character-invariant matching."""
    if not s:
        return ""
    s = s.lower()
    s = s.replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
    s = CLEAN_RE.sub('', s)
    return s

def find_matching_specialty(tracked_id, tracked_name, active_specialties):
    """Matches a user's tracked department with live active specialties by ID or name."""
    for spec_id, spec_name in active_specialties:
        if spec_id == tracked_id:
            return spec_id, spec_name

    cleaned_tracked = clean_turkish(tracked_name)
    for spec_id, spec_name in active_specialties:
        cleaned_active = clean_turkish(spec_name)
        if cleaned_tracked and (cleaned_tracked in cleaned_active or cleaned_active in cleaned_tracked):
            return spec_id, spec_name
    return None

def check_auth(chat_id) -> bool:
    """Checks if a user is authorized. If they are the Master Admin, automatically authorizes them."""
    chat_id_str = str(chat_id)
    cfg = _get_config()
    db_mod = _get_db()
    if cfg.ADMIN_CHAT_ID and chat_id_str == cfg.ADMIN_CHAT_ID:
        db_mod.ensure_user_exists(chat_id_str)
        db_mod.set_user_authorized(chat_id_str, True)
        return True
    
    user = db_mod.get_user(chat_id_str)
    return user is not None and user.get('is_authorized', 0) == 1

def make_token() -> str:
    """Generates a secure random 8-character uppercase invitation token."""
    chars = string.ascii_uppercase + string.digits
    return f"ADU-{''.join(secrets.SystemRandom().choices(chars, k=4))}-{''.join(secrets.SystemRandom().choices(chars, k=4))}"

def is_in_dnd(user) -> bool:
    """Returns True if user has enabled DND (silent hours) and current Turkey time falls within DND window."""
    if not user or not user.get('dnd_enabled'):
        return False
    tz_tr = datetime.timezone(datetime.timedelta(hours=3))
    now_hour = datetime.datetime.now(tz_tr).hour
    start_h = user.get('dnd_start', 23)
    end_h = user.get('dnd_end', 8)
    if start_h > end_h:
        return now_hour >= start_h or now_hour < end_h
    else:
        return start_h <= now_hour < end_h

def filter_slots_for_profile(slots, filter_date_days=0, filter_time_pref=0):
    """Filters slots based on profile's date range and time of day preferences."""
    if not filter_date_days and not filter_time_pref:
        return slots

    filtered = []
    today = datetime.date.today()

    for s in slots:
        # 1. Time Preference (1: Morning 08:00-11:59, 2: Afternoon 12:00-17:00)
        if filter_time_pref:
            m_time = re.search(r'(\d{2}):(\d{2})', s.get('time', ''))
            if m_time:
                hour = int(m_time.group(1))
                if filter_time_pref == 1 and hour >= 12:
                    continue
                if filter_time_pref == 2 and hour < 12:
                    continue

        # 2. Date Filter (within N days from today)
        if filter_date_days > 0:
            m_date = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', s.get('date', ''))
            if m_date:
                d, m, y = map(int, m_date.groups())
                try:
                    slot_date = datetime.date(y, m, d)
                    diff = (slot_date - today).days
                    if diff < 0 or diff > filter_date_days:
                        continue
                except Exception:
                    pass

        filtered.append(s)

    return filtered

def get_admin_users_view():
    """Helper to generate the text and keyboard for the authorized users list in Admin Panel."""
    cfg = _get_config()
    db_mod = _get_db()
    users = db_mod.get_authorized_users()
    filtered_users = [u for u in users if str(u['chat_id']) != cfg.ADMIN_CHAT_ID]

    if not filtered_users:
        text = "👥 <b>Kayıtlı aktif kullanıcı bulunmamaktadır (Siz hariç).</b>"
        keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
    else:
        text = (
            "👥 <b>Yetkilendirilmiş Aktif Kullanıcılar:</b>\n\n"
            "Aşağıdaki listede her kullanıcının Telegram ID'si ve eklediği profiller gösterilmektedir.\n\n"
            "⚠️ <b>İptal (Revoke):</b> Bir kullanıcının yetkisini iptal ettiğinizde, o kullanıcının tüm verileri silinir ve arka plan taramaları durdurulur."
        )
        keyboard = []
        profile_counts = db_mod.get_profiles_counts()
        for u in filtered_users:
            chat_id_str = str(u['chat_id'])
            count = profile_counts.get(chat_id_str, 0)
            profiles_str = f"({count} Profil)" if count > 0 else "(Profil yok)"
            keyboard.append([
                InlineKeyboardButton(f"❌ Revoke ID: {chat_id_str} {profiles_str}", callback_data=f"admin:revoke:{chat_id_str}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")])

    return text, InlineKeyboardMarkup(keyboard)

def build_slot_alert_view(alert_data, alert_id, date_idx=0, slot_page=0, page_size=6):
    """Builds an interactive paginated view for appointment alerts across dates and hours."""
    dates = alert_data.get('dates', [])
    if not dates:
        return "Randevu bulunamadı.", InlineKeyboardMarkup([])

    date_idx = max(0, min(date_idx, len(dates) - 1))
    current_date = dates[date_idx]
    day_slots = alert_data['slots_by_date'].get(current_date, [])

    total_slot_pages = max(1, math.ceil(len(day_slots) / page_size))
    slot_page = max(0, min(slot_page, total_slot_pages - 1))

    start_s = slot_page * page_size
    current_page_slots = day_slots[start_s : start_s + page_size]

    text = (
        f"🚨 <b>ADÜ BOŞ RANDEVU BİLDİRİMİ!</b>\n\n"
        f"👤 <b>Hasta Profili:</b> {alert_data['profile_name']} ({alert_data['tc_masked']})\n"
        f"🏷️ <b>Randevu Türü:</b> <b>{alert_data['rtype_label']}</b>\n"
        f"🏥 <b>Ana Bölüm:</b> {alert_data['specialty_name']}\n"
        f"🩺 <b>Poliklinik/Hekim:</b> {alert_data['polyclinic_name']}\n"
        f"📅 <b>Seçili Tarih:</b> <b>{current_date}</b> ({len(day_slots)} slot)\n"
        f"📊 <b>Toplam Boş Randevu:</b> {len(alert_data['all_slots'])} slot ({len(dates)} farklı gün)\n\n"
        f"⚡️ <i>Randevu almak istediğiniz saatin butonuna basarak kaydınızı anında tamamlayabilirsiniz:</i>"
    )

    keyboard = []
    row = []
    for s in current_page_slots:
        slot_key = s.get('key')
        row.append(InlineKeyboardButton(f"⚡️ {s['time']} Al", callback_data=f"book:{alert_data['profile_id']}:{slot_key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if total_slot_pages > 1:
        prev_sp = slot_page - 1 if slot_page > 0 else total_slot_pages - 1
        next_sp = slot_page + 1 if slot_page < total_slot_pages - 1 else 0
        keyboard.append([
            InlineKeyboardButton("◀️ Önceki Saat", callback_data=f"alert:p:{alert_id}:{date_idx}:{prev_sp}"),
            InlineKeyboardButton(f"📄 Saat {slot_page + 1}/{total_slot_pages}", callback_data="noop"),
            InlineKeyboardButton("Sonraki Saat ▶️", callback_data=f"alert:p:{alert_id}:{date_idx}:{next_sp}"),
        ])

    if len(dates) > 1:
        prev_dp = date_idx - 1 if date_idx > 0 else len(dates) - 1
        next_dp = date_idx + 1 if date_idx < len(dates) - 1 else 0
        keyboard.append([
            InlineKeyboardButton("⏮️ Önceki Gün", callback_data=f"alert:p:{alert_id}:{prev_dp}:0"),
            InlineKeyboardButton(f"📅 Gün {date_idx + 1}/{len(dates)}", callback_data="noop"),
            InlineKeyboardButton("Sonraki Gün ⏭️", callback_data=f"alert:p:{alert_id}:{next_dp}:0"),
        ])

    return text, InlineKeyboardMarkup(keyboard)
