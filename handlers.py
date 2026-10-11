import re
import time
import asyncio
import secrets
import string
import html
import math
import datetime
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import db
import config
import keyboards
import calendar_util
from scraper import ADUScraper

CLEAN_RE = re.compile(r'[^a-z0-9]')

def clean_turkish(s):
    """Cleans a string for safe, character-invariant matching"""
    if not s:
        return ""
    s = s.lower()
    s = s.replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
    s = CLEAN_RE.sub('', s)
    return s

def find_matching_specialty(tracked_id, tracked_name, active_specialties):
    """Matches a user's tracked department with live active specialties by ID or name"""
    for spec_id, spec_name in active_specialties:
        if spec_id == tracked_id:
            return spec_id, spec_name

    cleaned_tracked = clean_turkish(tracked_name)
    for spec_id, spec_name in active_specialties:
        cleaned_active = clean_turkish(spec_name)
        if cleaned_tracked and (cleaned_tracked in cleaned_active or cleaned_active in cleaned_tracked):
            return spec_id, spec_name
    return None

def check_auth(chat_id):
    """Checks if a user is authorized. If they are the Master Admin, automatically authorizes them."""
    chat_id_str = str(chat_id)
    if config.ADMIN_CHAT_ID and chat_id_str == config.ADMIN_CHAT_ID:
        db.ensure_user_exists(chat_id_str)
        db.set_user_authorized(chat_id_str, True)
        return True
    
    user = db.get_user(chat_id_str)
    return user is not None and user.get('is_authorized', 0) == 1

def make_token():
    """Generates a secure random 8-character uppercase invitation token"""
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
    """Helper to generate the text and keyboard for the authorized users list in Admin Panel"""
    users = db.get_authorized_users()
    filtered_users = [u for u in users if str(u['chat_id']) != config.ADMIN_CHAT_ID]

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
        profile_counts = db.get_profiles_counts()
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
    """Builds an interactive paginated view for appointment alerts across dates and hours"""
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

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not check_auth(chat_id):
        unauth_msg = (
            "⚠️ <b>Erişim Yetkiniz Yok!</b>\n\n"
            "Bu bot yetkili kullanım için yapılandırılmıştır.\n\n"
            "Lütfen devam etmek için sistem yöneticisi (admin) tarafından size tanımlanan tek kullanımlık <b>Davet Kodunu</b> "
            "(Örn: <code>ADU-XXXX-XXXX</code>) doğrudan bu sohbete mesaj olarak gönderin:"
        )
        await update.message.reply_text(text=unauth_msg, parse_mode="HTML")
        return
        
    db.ensure_user_exists(chat_id)
    context.user_data.pop('adding_profile', None)
    context.user_data.pop('editing_profile', None)
    
    welcome_text = (
        "🏥 <b>ADÜ Hastane Randevu Takip & Otomatik Rezervasyon Botu</b>'na hoş geldiniz!\n\n"
        "Aydın Adnan Menderes Üniversitesi (ADÜ) randevu sisteminde takip ettiğiniz bölümlerde boş slot açıldığında bot anında sizi bilgilendirir "
        "ve <b>tek tuşla veya Sniper moduyla otomatik olarak randevu almanızı</b> sağlar.\n\n"
        "🌟 <b>Temel Özellikler:</b>\n"
        "• <b>Çoklu Profil:</b> Kendiniz ve yakınlarınız için hasta profilleri tanımlayın.\n"
        "• <b>Merkezi Hızlı Tarama:</b> Sunucuyu yormadan, tek havuzdan yüksek frekanslı tarama.\n"
        "• <b>Sniper (Otomatik Al):</b> Boş yer çıktığında beklemeden saniyeler içinde randevu oluşturma.\n"
        "• <b>Tarih & Saat Filtreleri:</b> Sabah/Öğle ve gün aralığına göre akıllı slot eşleştirme.\n"
        "• <b>Takvim Entegrasyonu:</b> Randevu alındığında doğrudan Google Calendar ve Apple .ics dosyası gönderimi.\n"
        "• <b>Veri Güvenliği:</b> T.C. Kimlik ve telefon numaraları veritabanında şifrelenerek saklanır (At-Rest Encrypted).\n\n"
        "<i>Lütfen aşağıdaki menüden işlem seçin:</i>"
    )
    
    await update.message.reply_text(
        text=welcome_text,
        parse_mode="HTML",
        reply_markup=keyboards.get_main_keyboard(chat_id)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not check_auth(chat_id):
        return
        
    help_text = (
        "📖 <b>ADÜ Randevu Botu Kullanım Kılavuzu:</b>\n\n"
        "1️⃣ <b>Profil Oluşturma:</b>\n"
        "Menüden <i>Profillerim -> Yeni Profil Ekle</i> butonuna basıp hastanın Adını, T.C. Kimlik numarasını, doğum tarihini ve telefonunu girin.\n\n"
        "2️⃣ <b>Bölüm Ekleme:</b>\n"
        "<i>Takip Ettiklerim</i> menüsünden hastanızı seçin. <i>Bölüm Ekle</i> butonuna basarak 52 bölüm arasından istediğinizi işaretleyin (✅).\n\n"
        "3️⃣ <b>Sniper & Filtreler:</b>\n"
        "<i>Profillerim -> Profil Detayı -> Filtreler & Sniper Modu</i> adımıyla 'Otomatik Al' seçeneğini ve tarih/saat tercihlerinizi belirleyin.\n\n"
        "4️⃣ <b>Taramayı Başlatma:</b>\n"
        "Ana menüden <b>▶️ Taramayı Başlat</b> butonuna tıklayın. Merkezi tarayıcı sistemi boş randevuları düzenli sorgulamaya başlar.\n\n"
        "5️⃣ <b>Komutlar:</b>\n"
        "• <b>/stats:</b> Sistem çalışma metrikleri ve istatistikleri\n"
        "• <b>/ping:</b> Bot ve hastane portalı bağlantı hız testi"
    )
    await update.message.reply_text(text=help_text, parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not check_auth(chat_id):
        return

    stats = db.get_system_stats()
    stats_text = (
        "📊 <b>Sistem ve Bot İstatistikleri</b>\n\n"
        f"🏥 <b>Hastane Durumu:</b> {stats['hospital_status']}\n"
        f"⚡️ <b>Son Yanıt Süresi:</b> {stats['last_latency_ms']} ms\n"
        f"🔄 <b>Toplam Yapılan Tarama:</b> {stats['total_scans']:,}\n"
        f"🚨 <b>Tespit Edilen Boş Slot:</b> {stats['slots_found']:,}\n"
        f"🎉 <b>Başarılı Randevu Kaydı:</b> {stats['bookings_count']:,}\n\n"
        f"👥 <b>Yetkili Kullanıcılar:</b> {stats['total_users']}\n"
        f"🟢 <b>Aktif Tarayan Kullanıcı:</b> {stats['active_scanners']}\n"
        f"👤 <b>Tanımlı Hasta Profilleri:</b> {stats['total_profiles']}\n"
        f"💾 <b>Veritabanı Boyutu:</b> {stats['db_size_kb']} KB (WAL Modu)\n"
        f"🔐 <b>Kişisel Veri Şifreleme:</b> Aktif (PBKDF2-CTR-HMAC)"
    )
    await update.message.reply_text(text=stats_text, parse_mode="HTML")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not check_auth(chat_id):
        return

    msg = await update.message.reply_text("🏓 <i>Hastane sunucusu ve bot gecikmesi test ediliyor...</i>", parse_mode="HTML")
    t0 = time.perf_counter()
    scraper = ADUScraper()
    specs = await scraper.get_specialties(randevu_type=1)
    lat_ms = int((time.perf_counter() - t0) * 1000)

    if specs:
        status_txt = f"🟢 <b>Çevrimiçi</b> ({len(specs)} aktif uzmanlık)"
    else:
        status_txt = "🔴 <b>Bağlantı Başarısız / Yanıt Yok</b>"

    await msg.edit_text(
        text=f"🏓 <b>Pong!</b>\n\n"
             f"🏥 <b>Hastane Portalı:</b> {status_txt}\n"
             f"⏱️ <b>Gecikme (Latency):</b> <code>{lat_ms} ms</code>\n"
             f"🤖 <b>Bot Motoru:</b> Aktif ve Hazır",
        parse_mode="HTML"
    )

# --- Text Handlers (Wizards & Token Input) ---

async def _handle_unauthorized_user(update: Update, text: str) -> bool:
    """Handles messages from unauthorized users, verifying invitation tokens"""
    chat_id = update.effective_chat.id
    token_upper = text.upper()

    if token_upper.startswith("ADU-") and db.validate_invitation_token(token_upper):
        if db.use_invitation_token(token_upper, chat_id):
            db.set_user_authorized(chat_id, True)

            success_auth = (
                "🎉 <b>Davet Kodunuz Başarıyla Doğrulandı!</b>\n\n"
                "Bot için tam erişim yetkiniz tanımlanmıştır.\n\n"
                "Lütfen <b>/start</b> yazarak ana kontrol menüsüne gidin ve profilinizi oluşturun!"
            )
            await update.message.reply_text(text=success_auth, parse_mode="HTML")
        else:
            await update.message.reply_text(
                text="⚠️ <b>Bu davet kodu zaten kullanılmış!</b>\nLütfen yeni bir davet kodu girin:",
                parse_mode="HTML"
            )
        return True
    else:
        await update.message.reply_text(
            text="⚠️ <b>Yetkisiz Giriş veya Geçersiz Davet Kodu!</b>\n"
                 "Lütfen size gönderilen davet kodunu doğru girdiğinizden emin olun (Örn: <code>ADU-XXXX-XXXX</code>):",
            parse_mode="HTML"
        )
        return True

async def _handle_profile_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> bool:
    """Step-by-step wizard for creating a new patient profile"""
    if 'adding_profile' not in context.user_data:
        return False

    wizard = context.user_data['adding_profile']
    step = wizard.get('step')

    if step == 'name':
        wizard['name'] = text
        wizard['step'] = 'tc'
        await update.message.reply_text(
            text=f"👤 Profil: <b>{text}</b>\n\nLütfen 11 haneli <b>T.C. Kimlik Numarasını</b> girin:",
            parse_mode="HTML"
        )
        return True

    elif step == 'tc':
        if not text.isdigit() or len(text) != 11:
            await update.message.reply_text(
                text="⚠️ <b>Hatalı T.C. Kimlik!</b>\nLütfen tam olarak 11 haneli sayı girin:",
                parse_mode="HTML"
            )
            return True
        wizard['tc'] = text
        wizard['step'] = 'birth'
        await update.message.reply_text(
            text=f"👤 Profil: <b>{wizard['name']}</b>\n"
                 f"🆔 T.C.: <code>{text[:3]}********</code>\n\n"
                 f"Lütfen doğum tarihini <b>GG.AA.YYYY</b> formatında girin (Örn: <code>15.08.1985</code>):",
            parse_mode="HTML"
        )
        return True

    elif step == 'birth':
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
            await update.message.reply_text(
                text="⚠️ <b>Hatalı Doğum Tarihi Formatı!</b>\nLütfen tarihi tam olarak GG.AA.YYYY formatında girin (Örn: <code>15.08.1985</code>):",
                parse_mode="HTML"
            )
            return True
        wizard['birth'] = text
        wizard['step'] = 'phone'
        await update.message.reply_text(
            text=f"👤 Profil: <b>{wizard['name']}</b>\n"
                 f"📅 Doğum Tarihi: <code>{text}</code>\n\n"
                 f"Lütfen <b>telefon numarasını</b> 11 haneli ve 0 ile başlayacak şekilde girin (Örn: <code>05051234567</code>):",
            parse_mode="HTML"
        )
        return True

    elif step == 'phone':
        clean_p = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not clean_p.isdigit() or len(clean_p) != 11 or not clean_p.startswith("0"):
            await update.message.reply_text(
                text="⚠️ <b>Hatalı Telefon Numarası!</b>\n0 ile başlayan 11 haneli numara girin (Örn: <code>05051234567</code>):",
                parse_mode="HTML"
            )
            return True

        db.add_profile(
            chat_id=chat_id,
            name=wizard['name'],
            tc_kimlik=wizard['tc'],
            dogum_tarihi=wizard['birth'],
            telefon=clean_p
        )

        profile_name = wizard['name']
        context.user_data.pop('adding_profile', None)

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👤 Profillerime Git", callback_data="menu:profiles")
        ]])

        await update.message.reply_text(
            text=f"✅ <b>Profil Başarıyla Oluşturuldu!</b>\n\n"
                 f"👤 <b>İsim/Etiket:</b> {profile_name}\n"
                 f"🆔 <b>T.C. Kimlik:</b> <code>{wizard['tc'][:3]}********</code> (Şifrelendi 🔐)\n"
                 f"📅 <b>Doğum Tarihi:</b> {wizard['birth']}\n"
                 f"📞 <b>Telefon:</b> {clean_p}\n\n"
                 f"Artık bu profil için takip listesi oluşturabilir ve Sniper/Otomatik Al ayarlarını yapabilirsiniz.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return True

    return False

async def _handle_profile_edit_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> bool:
    """Handles text input for editing an existing profile (name or phone)"""
    if 'editing_profile' not in context.user_data:
        return False

    edit_data = context.user_data['editing_profile']
    profile_id = edit_data['profile_id']
    edit_type = edit_data['type']

    profile = db.get_profile_by_id(profile_id)
    if not profile:
        context.user_data.pop('editing_profile', None)
        await update.message.reply_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
        return True

    if edit_type == 'name':
        new_name = text.strip()
        db.update_profile(profile_id, name=new_name)
        context.user_data.pop('editing_profile', None)
        await update.message.reply_text(
            text=f"✅ Profil ismi başarıyla <b>{new_name}</b> olarak güncellendi.",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_view_keyboard(profile_id)
        )
        return True

    elif edit_type == 'phone':
        clean_p = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not clean_p.isdigit() or len(clean_p) != 11 or not clean_p.startswith("0"):
            await update.message.reply_text(
                text="⚠️ <b>Hatalı Telefon Numarası!</b>\n0 ile başlayan 11 haneli numara girin (Örn: <code>05051234567</code>):",
                parse_mode="HTML"
            )
            return True

        db.update_profile(profile_id, telefon=clean_p)
        context.user_data.pop('editing_profile', None)
        await update.message.reply_text(
            text=f"✅ <b>{profile['name']}</b> için telefon numarası başarıyla <code>{clean_p}</code> olarak güncellendi.",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_view_keyboard(profile_id)
        )
        return True

    return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    if not check_auth(chat_id):
        if await _handle_unauthorized_user(update, text):
            return

    if await _handle_profile_wizard(update, context, chat_id, text):
        return

    if await _handle_profile_edit_wizard(update, context, chat_id, text):
        return

    await update.message.reply_text(
        text="⚠️ Menüyü görüntülemek için lütfen /start yazın."
    )

# --- Callback Query Handlers ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # 1. Main Menu
    if query.data == "menu:main":
        await query.message.edit_text(
            text="🏥 <i>Lütfen aşağıdaki menüden işlem seçin:</i>",
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )

    # 2. Profiles List
    elif query.data == "menu:profiles":
        profiles = db.get_profiles(chat_id)
        if not profiles:
            text = "👤 <b>Kayıtlı profiliniz bulunmamaktadır.</b>\n\nRandevu takibi yapabilmek için 'Yeni Profil Ekle' butonuna basarak ilk profilinizi oluşturun."
        else:
            text = "👤 <b>Kayıtlı Profilleriniz:</b>\n\nİstediğiniz profilin detaylarını görmek, filtrelerini ayarlamak veya silmek için ilgili isme tıklayın."
        
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profiles_keyboard(chat_id)
        )

    # 3. Add Profile Trigger
    elif query.data == "profile:add":
        context.user_data['adding_profile'] = {'step': 'name'}
        await query.message.edit_text(
            text="👤 <b>Yeni Profil Ekleme Sihirbazı</b>\n\n"
                 "Lütfen eklemek istediğiniz kişinin adını veya etiketini yazın (Örn: <code>Kendim</code>, <code>Annem</code>, <code>Babam</code>):",
            parse_mode="HTML"
        )

    # 4. View Profile Details
    elif query.data.startswith("profile:view:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return
            
        auto_str = "🟢 AKTİF (Sniper)" if profile.get('auto_book') else "⚪️ Pasif (Yalnızca Bildirim)"
        date_filter_str = f"Önümüzdeki {profile['filter_date_days']} Gün" if profile.get('filter_date_days') else "Tüm Tarihler"
        time_pref = profile.get('filter_time_pref', 0)
        time_str = "Tüm Gün" if time_pref == 0 else ("🌅 Sabah (08-12)" if time_pref == 1 else "🌇 Öğle (13-17)")

        details = (
            f"👤 <b>Profil Detayları:</b>\n\n"
            f"🏷️ <b>İsim/Etiket:</b> {profile['name']}\n"
            f"🆔 <b>T.C. Kimlik:</b> <code>{profile['tc_kimlik'][:3]}******{profile['tc_kimlik'][-2:]}</code> (Şifrelendi 🔐)\n"
            f"📅 <b>Doğum Tarihi:</b> {profile['dogum_tarihi']}\n"
            f"📞 <b>Telefon:</b> {profile['telefon']}\n\n"
            f"⚡️ <b>Sniper Modu (Otomatik Al):</b> {auto_str}\n"
            f"📅 <b>Tarih Tercihi:</b> {date_filter_str}\n"
            f"⏰ <b>Saat Tercihi:</b> {time_str}\n"
        )
        await query.message.edit_text(
            text=details,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_view_keyboard(profile_id)
        )

    # 4b. Profile Preferences / Sniper View
    elif query.data.startswith("pref:view:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            return
        
        pref_text = (
            f"⚡️ <b>{profile['name']} için Sniper & Filtre Ayarları</b>\n\n"
            f"🎯 <b>Sniper (Otomatik Al):</b> Açık olduğunda bot boş randevu yakaladığı an onay beklemeden doğrudan sizin adınıza randevuyu onaylar!\n\n"
            f"📅 <b>Tarih Filtresi:</b> Sadece belirlediğiniz gün aralığındaki slotlar kabul edilir.\n"
            f"⏰ <b>Saat Tercihi:</b> Sadece tercih ettiğiniz sabah/öğle saatleri taranır."
        )
        await query.message.edit_text(
            text=pref_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_prefs_keyboard(profile_id)
        )

    # 4c. Toggle Auto-Book Sniper
    elif query.data.startswith("pref:toggle_auto:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            new_val = 0 if profile.get('auto_book', 0) else 1
            db.set_profile_auto_book(profile_id, new_val)
            stat_lbl = "AÇILDI 🎯" if new_val else "KAPATILDI ⚪️"
            await query.answer(f"Sniper Modu {stat_lbl}")
            await query.message.edit_reply_markup(reply_markup=keyboards.get_profile_prefs_keyboard(profile_id))

    # 4d. Set Date Filter
    elif query.data.startswith("pref:date:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        days = int(parts[3])
        db.set_profile_filter_date(profile_id, days)
        await query.answer(f"Tarih filtresi: {'Tümü' if days == 0 else f'{days} Gün'}")
        await query.message.edit_reply_markup(reply_markup=keyboards.get_profile_prefs_keyboard(profile_id))

    # 4e. Set Time Filter
    elif query.data.startswith("pref:time:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        time_pref = int(parts[3])
        db.set_profile_filter_time(profile_id, time_pref)
        t_lbl = "Tüm Gün" if time_pref == 0 else ("Sabah" if time_pref == 1 else "Öğle")
        await query.answer(f"Saat tercihi: {t_lbl}")
        await query.message.edit_reply_markup(reply_markup=keyboards.get_profile_prefs_keyboard(profile_id))

    # 4f. Edit Profile Menu
    elif query.data.startswith("profile:edit:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            return
        await query.message.edit_text(
            text=f"✏️ <b>{profile['name']} Profilini Düzenle</b>\n\nGüncellemek istediğiniz alanı seçin:",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_edit_keyboard(profile_id)
        )

    # 4g. Edit Profile Name Prompt
    elif query.data.startswith("profile:edit_name:"):
        profile_id = int(query.data.split(":")[-1])
        context.user_data['editing_profile'] = {'profile_id': profile_id, 'type': 'name'}
        await query.message.edit_text(
            text="✏️ <b>İsim / Etiket Güncelleme:</b>\n\nLütfen bu profil için yeni ismi yazıp gönderin:",
            parse_mode="HTML"
        )

    # 4h. Edit Profile Phone Prompt
    elif query.data.startswith("profile:edit_phone:"):
        profile_id = int(query.data.split(":")[-1])
        context.user_data['editing_profile'] = {'profile_id': profile_id, 'type': 'phone'}
        await query.message.edit_text(
            text="📞 <b>Telefon Numarası Güncelleme:</b>\n\nLütfen 0 ile başlayan yeni 11 haneli telefon numarasını yazıp gönderin (Örn: <code>05051234567</code>):",
            parse_mode="HTML"
        )

    # 5. Delete Profile
    elif query.data.startswith("profile:delete:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            db.delete_profile(chat_id, profile['name'])
            text = f"✅ <b>{profile['name']}</b> isimli profil başarıyla silindi."
        else:
            text = "Hata: Profil bulunamadı."
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profiles_keyboard(chat_id)
        )

    # 6. Tracking Selection Profile List
    elif query.data == "menu:tracking":
        profiles = db.get_profiles(chat_id)
        if not profiles:
            await query.message.edit_text(
                text="⚠️ <b>Profil Bulunamadı!</b>\n\nRandevu takibi yapabilmek için öncelikle en az bir profil oluşturmalısınız.",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard(chat_id)
            )
            return
            
        await query.message.edit_text(
            text="🏥 <b>Bölüm Takip Listesi</b>\n\nHangi hasta için randevu bölümlerini yönetmek istiyorsunuz?",
            parse_mode="HTML",
            reply_markup=keyboards.get_tracking_keyboard(chat_id)
        )

    # 7. View Profile's Tracked Specialties
    elif query.data.startswith("track:profile:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return
            
        tracked = db.get_profile_specialties(profile_id)
        if not tracked:
            text = f"🏥 <b>{profile['name']}</b> için takip edilen bölüm yok.\n\nAşağıdaki 'Bölüm Ekle' butonuna basarak takip etmek istediğiniz hastane bölümlerini seçebilirsiniz."
        else:
            text = f"🏥 <b>{profile['name']} için Takip Edilen Bölümler ({len(tracked)} adet):</b>\n\n"
            for t in tracked:
                text += f"• {t['specialty_name']}\n"
            text += "\n<i>Bir bölümü takipten çıkarmak için aşağıdaki ismin yanındaki [❌] butonuna tıklayın:</i>"
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )

    # 8. Specialty Add / Paginated Browser
    elif query.data.startswith("track:add:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0

        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return

        text = (
            f"🏥 <b>{profile['name']} için Bölüm Listesi (Toplam 52 Uzmanlık)</b>\n\n"
            f"Takip etmek istediğiniz bölümlere dokunarak aktif (✅) veya pasif (➕) hale getirebilirsiniz.\n\n"
            f"<i>Sayfalar arasında geçiş yapmak için [◀️ Önceki] ve [Sonraki ▶️] butonlarını kullanın:</i>"
        )
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_track_add_keyboard(profile_id, page=page)
        )

    # 9. Toggle Specialty on/off
    elif query.data.startswith("track:toggle:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        spec_id = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 0

        profile = db.get_profile_by_id(profile_id)
        spec_name = config.ADU_DEPARTMENTS.get(spec_id, f"Bölüm ({spec_id})")

        if profile:
            tracked = db.get_profile_specialties(profile_id)
            tracked_ids = {t['specialty_id'] for t in tracked}

            if spec_id in tracked_ids:
                db.remove_profile_specialty(profile_id, spec_id)
                await query.answer(f"❌ {spec_name} takipten çıkarıldı.")
            else:
                db.add_profile_specialty(profile_id, spec_id, spec_name)
                await query.answer(f"✅ {spec_name} takibe eklendi!")

        await query.message.edit_reply_markup(
            reply_markup=keyboards.get_track_add_keyboard(profile_id, page=page)
        )

    # 11. Clear All Specialties for Profile
    elif query.data.startswith("track:clear:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            db.clear_profile_specialties(profile_id)
            await query.answer("Tüm takip listesi temizlendi.")
        await query.message.edit_text(
            text=f"🏥 <b>{profile['name']}</b> için tüm takip listesi temizlendi.",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )

    # 12. Remove Single Specialty
    elif query.data.startswith("track:remove:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        spec_id = int(parts[3])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            db.remove_profile_specialty(profile_id, spec_id)
            await query.answer("Bölüm takibi kaldırıldı.")
        
        tracked = db.get_profile_specialties(profile_id)
        text = f"🏥 <b>{profile['name']} için Takip Edilen Bölümler ({len(tracked)} adet):</b>\n\n"
        if not tracked:
            text = f"🏥 <b>{profile['name']}</b> için takip edilen bölüm yok."
        else:
            for t in tracked:
                text += f"• {t['specialty_name']}\n"
            text += "\n<i>Bir bölümü takipten çıkarmak için aşağıdaki [❌] butonuna basın:</i>"

        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )

    # 13. Settings View
    elif query.data == "menu:settings":
        user = db.get_user(chat_id)
        rtype = user.get('randevu_type', 0) if user else 0
        rtype_desc = config.RANDEVU_TYPES.get(rtype, "Tümü")
        dnd_state = "AÇIK (23:00 - 08:00)" if user.get('dnd_enabled') else "KAPALI"
        await query.message.edit_text(
            text=f"⚙️ <b>Sorgulama ve Bildirim Ayarları</b>\n\n"
                 f"⏰ <b>Sorgulama Sıklığı:</b> Boş randevuları kontrol etme periyodu.\n"
                 f"🏥 <b>Randevu Türü Tercihi:</b> <b>{rtype_desc}</b>\n"
                 f"🌙 <b>Gece Sessiz Modu:</b> <b>{dnd_state}</b>\n\n"
                 f"💡 <i>Özel Öğretim Üyesi seçeneği profesör ve doçentlerin saat 15:00 randevularını kapsar.</i>",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )

    # 14. Save Interval Setting
    elif query.data.startswith("settings:interval:"):
        interval = int(query.data.split(":")[-1])
        db.set_scan_interval(chat_id, interval)
        await query.message.edit_text(
            text=f"⚙️ Sorgulama sıklığı <b>{interval} dakika</b> olarak ayarlandı.",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )

    # 14b. Save Randevu Type Setting
    elif query.data.startswith("settings:rtype:"):
        rtype = int(query.data.split(":")[-1])
        db.set_randevu_type(chat_id, rtype)
        rtype_desc = config.RANDEVU_TYPES.get(rtype, "Tümü")
        await query.answer(f"Randevu türü: {rtype_desc}")
        await query.message.edit_text(
            text=f"⚙️ <b>Ayarlar Güncellendi</b>\n\n"
                 f"Tercih edilen randevu türü: <b>{rtype_desc}</b> olarak ayarlandı.",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )

    # 14c. Toggle DND Setting
    elif query.data == "settings:toggle_dnd":
        user = db.get_user(chat_id)
        cur_dnd = user.get('dnd_enabled', 0) if user else 0
        new_dnd = 0 if cur_dnd else 1
        db.set_user_dnd(chat_id, new_dnd)
        dnd_lbl = "AÇILDI 🌙" if new_dnd else "KAPATILDI 🔔"
        await query.answer(f"Gece Modu {dnd_lbl}")
        await query.message.edit_reply_markup(reply_markup=keyboards.get_settings_keyboard(chat_id))

    # 15. Status Info View
    elif query.data == "menu:status":
        user = db.get_user(chat_id)
        profiles = db.get_profiles(chat_id)
        
        status_text = "🔄 <b>Sistem ve Tarama Durumu</b>\n\n"
        if not user:
            status_text += "Durum: Başlatılmadı."
        else:
            status_state = "🟢 TARAMA AKTİF" if user['is_scanning'] else "🔴 TARAMA DURDURULDU"
            rtype = user.get('randevu_type', 0)
            rtype_desc = config.RANDEVU_TYPES.get(rtype, "Tümü (Normal + Özel Öğretim Üyesi)")
            dnd_str = "Açık (Sessiz)" if user.get('dnd_enabled') else "Kapalı (Sesli)"
            status_text += f"⚙️ <b>Tarama Durumu:</b> {status_state}\n"
            status_text += f"⏰ <b>Sorgulama Aralığı:</b> {user['scan_interval']} dakika\n"
            status_text += f"🏷️ <b>Randevu Türü:</b> {rtype_desc}\n"
            status_text += f"🌙 <b>Gece Sessiz Modu:</b> {dnd_str}\n\n"
            
            status_text += f"👤 <b>Kayıtlı Hastalar ({len(profiles)} kişi):</b>\n"
            if not profiles:
                status_text += "• Kayıtlı hasta profili yok.\n"
            else:
                all_specs = db.get_profiles_specialties([p['id'] for p in profiles])
                for p in profiles:
                    specs = all_specs.get(p['id'], [])
                    auto_badge = " [🎯 Sniper]" if p.get('auto_book') else ""
                    if specs:
                        spec_names = ", ".join([s['specialty_name'] for s in specs[:3]])
                        if len(specs) > 3:
                            spec_names += f" ve {len(specs)-3} diğer"
                    else:
                        spec_names = "Takip edilen bölüm yok"
                    status_text += f"• <b>{p['name']}</b>{auto_badge}: <i>{spec_names}</i>\n"
                
        await query.message.edit_text(
            text=status_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )

    # 16. Toggle Active Scan Job
    elif query.data == "menu:toggle_scan":
        user = db.get_user(chat_id)
        profiles = db.get_profiles(chat_id)
        if not user:
            return
            
        current_state = user['is_scanning']
        new_state = not current_state
        
        if new_state:
            if not profiles:
                await query.message.edit_text(
                    text="⚠️ <b>Tarama Başlatılamadı!</b>\n\nTaramayı başlatabilmek için en az 1 adet profil oluşturmalısınız.",
                    parse_mode="HTML",
                    reply_markup=keyboards.get_main_keyboard(chat_id)
                )
                return
                
            all_specs = db.get_profiles_specialties([p['id'] for p in profiles])
            if not all_specs:
                await query.message.edit_text(
                    text="⚠️ <b>Tarama Başlatılamadı!</b>\n\nTaramayı başlatabilmek için en az 1 tane takip edilecek bölüm eklemelisiniz.",
                    parse_mode="HTML",
                    reply_markup=keyboards.get_main_keyboard(chat_id)
                )
                return
                
            db.set_scanning_state(chat_id, True)
            db.update_user_last_scan(chat_id, 0)
            
            scan_details = ""
            for p in profiles:
                specs = all_specs.get(p['id'], [])
                if specs:
                    spec_names = ", ".join([s['specialty_name'] for s in specs])
                    scan_details += f"• <b>{p['name']}</b>: <i>{spec_names}</i>\n"

            text = (
                "🟢 <b>Otomatik tarama başarıyla BAŞLATILDI.</b>\n\n"
                "🔍 <b>Aktif Takip Listesi:</b>\n"
                f"{scan_details}\n"
                "Merkezi tarayıcı arka planda hastane sistemini sorgulayacak ve boş randevu yakaladığında sizi anında uyaracaktır."
            )
        else:
            db.set_scanning_state(chat_id, False)
            text = "🔴 <b>Otomatik tarama DURDURULDU.</b>\n\nArka plan sorgulamaları sonlandırıldı. İstediğiniz zaman tekrar başlatabilirsiniz."
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )

    # 17. Perform Instant Auto Book on Click
    elif query.data.startswith("book:"):
        parts = query.data.split(":")
        profile_id = int(parts[1])
        slot_key = parts[2]
        
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.answer("Hata: Profil bulunamadı.", show_alert=True)
            return

        slot_cache = context.bot_data.get('slot_cache', {})
        slot_info = slot_cache.get(slot_key)

        if not slot_info:
            await query.answer("Bu randevu seçeneğinin süresi dolmuş veya slot güncellenmiş. Lütfen yeni bildirimi bekleyin.", show_alert=True)
            return

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

            # Generate Google Calendar Link and .ics file
            gcal_url = calendar_util.generate_google_calendar_url(
                specialty_name=slot_info.get('specialty_name', 'Uzmanlık'),
                polyclinic_name=slot_info.get('polyclinic_name', 'Poliklinik'),
                patient_name=profile['name'],
                date_str=slot_info['date'],
                time_str=slot_info['time']
            )
            gcal_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📅 Google Takvime Ekle", url=gcal_url)
            ]])
            await query.edit_message_text(text=finished_text, parse_mode="HTML", reply_markup=gcal_keyboard)
            await query.answer("Randevunuz başarıyla alınmıştır! 🎉", show_alert=True)

            # Send .ics attachment
            try:
                ics_bytes = calendar_util.generate_ics_calendar(
                    specialty_name=slot_info.get('specialty_name', 'Uzmanlık'),
                    polyclinic_name=slot_info.get('polyclinic_name', 'Poliklinik'),
                    patient_name=profile['name'],
                    date_str=slot_info['date'],
                    time_str=slot_info['time']
                )
                ics_stream = BytesIO(ics_bytes)
                ics_stream.name = f"ADU_Randevu_{profile['name']}.ics"
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=ics_stream,
                    filename=ics_stream.name,
                    caption="📎 <b>Takvim Dosyası:</b> Randevunuzu telefonunuzun yerel takvimine eklemek için dosyayı açabilirsiniz.",
                    parse_mode="HTML"
                )
            except Exception as e:
                config.logger.warning(f"Could not send .ics file: {e}")

        else:
            failed_text = (
                query.message.text + 
                f"\n\n❌ <b>Randevu Alınamadı!</b>\n"
                f"⚠️ Hata Nedeni: <i>{html.escape(message)}</i>"
            )
            await query.edit_message_text(text=failed_text, parse_mode="HTML")
            await query.answer(f"Randevu alma başarısız: {message}", show_alert=True)

    # 18. Paginated Slot Alerts Navigation
    elif query.data.startswith("alert:p:"):
        parts = query.data.split(":")
        alert_id = parts[2]
        date_idx = int(parts[3])
        slot_page = int(parts[4])
        
        alert_data = context.bot_data.get('slot_alerts', {}).get(alert_id)
        if not alert_data:
            await query.answer("Bu bildirim güncellenmiş veya süresi dolmuş.", show_alert=True)
            return
            
        text, reply_markup = build_slot_alert_view(alert_data, alert_id, date_idx=date_idx, slot_page=slot_page)
        try:
            await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            pass
        await query.answer()

    # --- Master Admin Panel Handlers ---

    elif query.data == "menu:admin":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        unused_tokens = db.get_unused_tokens()
        auth_users = db.get_authorized_users()
        auth_users_count = len([u for u in auth_users if str(u['chat_id']) != config.ADMIN_CHAT_ID])
        
        admin_text = (
            f"🔑 <b>ADÜ Bot Yetki & Sistem Yönetim Paneli</b>\n\n"
            f"👥 <b>Yetkili Aktif Kullanıcılar:</b> {auth_users_count} kişi (Siz hariç)\n"
            f"📜 <b>Kullanılmamış Davet Kodları:</b> {len(unused_tokens)} adet\n\n"
            f"Aşağıdaki butonları kullanarak davet kodları üretebilir, kullanıcıları yönetebilir veya sistem metriklerini izleyebilirsiniz."
        )
        await query.message.edit_text(
            text=admin_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_admin_keyboard()
        )

    elif query.data == "admin:metrics":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return

        stats = db.get_system_stats()
        metrics_text = (
            "📊 <b>Canlı Sistem Metrikleri & Teşhis Paneli</b>\n\n"
            f"🏥 <b>Hastane Bağlantı Durumu:</b> {stats['hospital_status']}\n"
            f"⚡️ <b>Son Yanıt Süresi (Latency):</b> {stats['last_latency_ms']} ms\n\n"
            f"📈 <b>Toplam Tarama Döngüsü:</b> {stats['total_scans']:,}\n"
            f"🚨 <b>Yakalana Boş Slot Sayısı:</b> {stats['slots_found']:,}\n"
            f"🎯 <b>Başarıyla Alınan Randevular:</b> {stats['bookings_count']:,}\n\n"
            f"👥 <b>Kayıtlı Kullanıcı Sayısı:</b> {stats['total_users']}\n"
            f"🟢 <b>Şu An Tarama Yapanlar:</b> {stats['active_scanners']}\n"
            f"👤 <b>Toplam Hasta Profilleri:</b> {stats['total_profiles']}\n\n"
            f"💾 <b>SQLite Boyutu:</b> {stats['db_size_kb']} KB\n"
            f"⚡️ <b>WAL Günlük Modu:</b> Aktif\n"
            f"🔐 <b>Veri Şifreleme:</b> PBKDF2 + CTR + HMAC-SHA256"
        )
        keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
        await query.message.edit_text(
            text=metrics_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "admin:gen_token":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        token = make_token()
        db.add_invitation_token(token)
        
        token_text = (
            f"✅ <b>Yeni Tek Kullanımlık Davet Kodu Üretildi!</b>\n\n"
            f"🔑 <b>Kod:</b> <code>{token}</code>\n\n"
            f"Bu kodu kullanıcıya iletin. Bota mesaj attığında yetkilendirilecektir."
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ Bir Tane Daha Üret", callback_data="admin:gen_token"),
                InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")
            ]
        ]
        await query.message.edit_text(
            text=token_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "admin:list_tokens":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        tokens = db.get_unused_tokens()
        if not tokens:
            list_display_text = "📜 <b>Kullanılmamış aktif davet kodu bulunmuyor.</b>"
            keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
        else:
            list_display_text = "📜 <b>Aktif Davet Kodları (Kullanılmamış):</b>\n\nSilmek istediğiniz kodun yanındaki [❌] butonuna tıklayın."
            keyboard = []
            for t in tokens:
                keyboard.append([
                    InlineKeyboardButton(f"❌ {t['token']}", callback_data=f"admin:del_token:{t['token']}")
                ])
            keyboard.append([InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")])
            
        await query.message.edit_text(
            text=list_display_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("admin:del_token:"):
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        token_to_del = query.data.split(":")[-1]
        db.delete_invitation_token(token_to_del)
        await query.answer(f"Davet kodu silindi: {token_to_del}", show_alert=True)
        
        tokens = db.get_unused_tokens()
        if not tokens:
            list_display_text = "📜 <b>Kullanılmamış aktif davet kodu bulunmuyor.</b>"
            keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
        else:
            list_display_text = "📜 <b>Aktif Davet Kodları (Kullanılmamış):</b>"
            keyboard = []
            for t in tokens:
                keyboard.append([
                    InlineKeyboardButton(f"❌ {t['token']}", callback_data=f"admin:del_token:{t['token']}")
                ])
            keyboard.append([InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")])
            
        await query.message.edit_text(
            text=list_display_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "admin:list_users":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        users_text, users_markup = get_admin_users_view()
        await query.message.edit_text(
            text=users_text,
            parse_mode="HTML",
            reply_markup=users_markup
        )

    elif query.data.startswith("admin:revoke:"):
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        user_to_revoke = query.data.split(":")[-1]
        try:
            await context.bot.send_message(
                chat_id=user_to_revoke,
                text="⚠️ <b>Erişim Yetkiniz İptal Edildi!</b>\n\nAdmin tarafından bu bota erişim yetkiniz kaldırılmıştır.",
                parse_mode="HTML"
            )
        except Exception as e:
            config.logger.error(f"Could not notify revoked user {user_to_revoke}: {e}")
            
        db.revoke_user(user_to_revoke)
        await query.answer(f"Kullanıcı yetkisi iptal edildi: {user_to_revoke}", show_alert=True)
        
        users_text, users_markup = get_admin_users_view()
        await query.message.edit_text(
            text=users_text,
            parse_mode="HTML",
            reply_markup=users_markup
        )

# --- Centralized Background Scanning Worker ---

async def central_scan_job(context: ContextTypes.DEFAULT_TYPE):
    """Centralized high-performance background scanner (Fan-Out Pub-Sub).
    Collects all unique departments tracked across due users, scrapes each once,
    and broadcasts/auto-books to individual users without duplicate requests.
    """
    active_users = db.get_active_users()
    if not active_users:
        return

    now = time.time()
    due_users = []
    for u in active_users:
        last = u.get('last_scan_time', 0)
        interval_secs = max(60, int(u.get('scan_interval', 15)) * 60)
        if now - last >= interval_secs or last == 0:
            due_users.append(u)

    if not due_users:
        return

    config.logger.info(f"Central scan cycle started for {len(due_users)} due users.")
    db.increment_metric("total_scans")
    db.set_metric("last_scan_time", str(now))

    # Collect all profiles and tracked specialties for due users
    user_profiles_map = {}
    all_needed_specs = set() # (spec_id, spec_name, rtype)
    
    for u in due_users:
        chat_id = u['chat_id']
        db.update_user_last_scan(chat_id, now)
        profiles = db.get_profiles(chat_id)
        if not profiles:
            continue
        user_profiles_map[chat_id] = profiles

        p_ids = [p['id'] for p in profiles]
        profile_specs = db.get_profiles_specialties(p_ids)

        preferred_rtype = u.get('randevu_type', 0)
        rtypes = [1, 2] if preferred_rtype == 0 else [preferred_rtype]

        for p in profiles:
            specs = profile_specs.get(p['id'], [])
            for s in specs:
                for rt in rtypes:
                    all_needed_specs.add((s['specialty_id'], s['specialty_name'], rt))

    if not all_needed_specs:
        return

    scraper = ADUScraper()
    active_specs_cache = {}  # rtype -> active_specs list
    polyclinic_cache = {}    # (spec_id, rtype) -> polyclinics list
    slots_cache = {}         # (spec_id, poly_id, rtype) -> slots list

    # Ensure memory structures exist on bot_data
    if 'sent_alerts' not in context.bot_data:
        context.bot_data['sent_alerts'] = {}
    if 'slot_cache' not in context.bot_data:
        context.bot_data['slot_cache'] = {}
    if 'slot_alerts' not in context.bot_data:
        context.bot_data['slot_alerts'] = {}

    # Prune memory structures if large
    if len(context.bot_data['slot_alerts']) > 100:
        context.bot_data['slot_alerts'] = {
            k: v for k, v in context.bot_data['slot_alerts'].items()
            if now - v.get('timestamp', 0) < 7200
        }
    if len(context.bot_data['slot_cache']) > 500:
        context.bot_data['slot_cache'] = {
            k: v for k, v in context.bot_data['slot_cache'].items()
            if now - v.get('timestamp', 0) < 7200
        }

    # Execute central queries for needed departments
    for spec_id, spec_name, rtype in all_needed_specs:
        if rtype not in active_specs_cache:
            active_specs_cache[rtype] = await scraper.get_specialties(randevu_type=rtype)

        active_specs = active_specs_cache[rtype]
        match = find_matching_specialty(spec_id, spec_name, active_specs)
        if not match:
            continue

        active_id, active_name = match
        poly_key = (active_id, rtype)
        if poly_key not in polyclinic_cache:
            await asyncio.sleep(0.5)
            polyclinic_cache[poly_key] = await scraper.get_polyclinics(active_id, randevu_type=rtype)

        polys = polyclinic_cache[poly_key]
        for poly in polys:
            poly_id = poly['id']
            slots_key = (active_id, poly_id, rtype)
            if slots_key not in slots_cache:
                await asyncio.sleep(0.5)
                slots_cache[slots_key] = await scraper.check_slots(active_id, poly_id, randevu_type=rtype)

    # Fan-out: match results to each due user's profiles
    for u in due_users:
        chat_id = u['chat_id']
        silent_mode = is_in_dnd(u)
        profiles = user_profiles_map.get(chat_id, [])
        if not profiles:
            continue

        p_ids = [p['id'] for p in profiles]
        profile_specs = db.get_profiles_specialties(p_ids)

        preferred_rtype = u.get('randevu_type', 0)
        rtypes = [1, 2] if preferred_rtype == 0 else [preferred_rtype]

        for profile in profiles:
            specs = profile_specs.get(profile['id'], [])
            for s in specs:
                spec_id = s['specialty_id']
                spec_name = s['specialty_name']

                for rtype in rtypes:
                    rtype_label = "🌟 Özel Öğretim Üyesi (15:00)" if rtype == 2 else "🩺 Normal Randevu"
                    active_specs = active_specs_cache.get(rtype, [])
                    match = find_matching_specialty(spec_id, spec_name, active_specs)
                    if not match:
                        continue

                    active_id, active_name = match
                    polys = polyclinic_cache.get((active_id, rtype), [])
                    for poly in polys:
                        poly_id = poly['id']
                        raw_slots = slots_cache.get((active_id, poly_id, rtype), [])
                        if not raw_slots:
                            continue

                        # Apply profile filters (date range and time preference)
                        matched_slots = filter_slots_for_profile(
                            raw_slots,
                            filter_date_days=profile.get('filter_date_days', 0),
                            filter_time_pref=profile.get('filter_time_pref', 0)
                        )
                        if not matched_slots:
                            continue

                        db.increment_metric("slots_found", len(matched_slots))

                        # --- AUTO-BOOK SNIPER MODE ---
                        if profile.get('auto_book') == 1:
                            target_slot = matched_slots[0]
                            config.logger.info(f"SNIPER TRIGGERED for {profile['name']} at {target_slot['time']}!")

                            success, book_msg = await scraper.book_appointment(
                                specialty_id=active_id,
                                polyclinic_id=poly_id,
                                slot_id=target_slot['slot_id'],
                                tc_kimlik=profile['tc_kimlik'],
                                dogum_tarihi=profile['dogum_tarihi'],
                                telefon=profile['telefon'],
                                randevu_type=rtype
                            )

                            if success:
                                gcal_url = calendar_util.generate_google_calendar_url(
                                    specialty_name=active_name,
                                    polyclinic_name=poly['name'],
                                    patient_name=profile['name'],
                                    date_str=target_slot['date'],
                                    time_str=target_slot['time'],
                                    rtype_label=rtype_label
                                )
                                kb = InlineKeyboardMarkup([[
                                    InlineKeyboardButton("📅 Google Takvime Ekle", url=gcal_url)
                                ]])
                                sniper_success_text = (
                                    f"🎯 <b>OTOMATİK RANDEVU ALINDI! (SNIPER MODU)</b>\n\n"
                                    f"👤 <b>Hasta:</b> {profile['name']} (<code>{profile['tc_kimlik'][:3]}***</code>)\n"
                                    f"🏷️ <b>Tür:</b> {rtype_label}\n"
                                    f"🏥 <b>Bölüm:</b> {active_name}\n"
                                    f"🩺 <b>Hekim/Poliklinik:</b> {poly['name']}\n"
                                    f"📅 <b>Tarih & Saat:</b> <b>{target_slot['date']} {target_slot['time']}</b>\n\n"
                                    f"✅ <i>Hastane Onay Mesajı: {html.escape(book_msg)}</i>"
                                )
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=sniper_success_text,
                                    parse_mode="HTML",
                                    reply_markup=kb,
                                    disable_notification=silent_mode
                                )

                                # Send .ics calendar attachment
                                try:
                                    ics_bytes = calendar_util.generate_ics_calendar(
                                        specialty_name=active_name,
                                        polyclinic_name=poly['name'],
                                        patient_name=profile['name'],
                                        date_str=target_slot['date'],
                                        time_str=target_slot['time'],
                                        rtype_label=rtype_label
                                    )
                                    ics_stream = BytesIO(ics_bytes)
                                    ics_stream.name = f"ADU_Randevu_{profile['name']}.ics"
                                    await context.bot.send_document(
                                        chat_id=chat_id,
                                        document=ics_stream,
                                        filename=ics_stream.name,
                                        caption="📎 <b>Takvim Daveti:</b> Randevunuzu telefon takviminize ekleyebilirsiniz.",
                                        disable_notification=silent_mode
                                    )
                                except Exception as e:
                                    config.logger.warning(f"Failed sending .ics in sniper mode: {e}")
                                continue

                        # --- MANUAL NOTIFICATION MODE ---
                        alert_key = f"{profile['id']}_{poly_id}_{rtype}"
                        last_sent = context.bot.data['sent_alerts'].get(alert_key, 0)
                        if now - last_sent < 2700:
                            continue

                        context.bot_data['sent_alerts'][alert_key] = now

                        slots_by_date = {}
                        for slot in matched_slots:
                            d = slot.get('date', 'Bilinmeyen Tarih')
                            slots_by_date.setdefault(d, []).append(slot)

                        dates = list(slots_by_date.keys())
                        if not dates:
                            continue

                        for d, d_slots in slots_by_date.items():
                            for s in d_slots:
                                slot_key = secrets.token_hex(4)
                                s['key'] = slot_key
                                context.bot_data['slot_cache'][slot_key] = {
                                    'specialty_id': active_id,
                                    'specialty_name': active_name,
                                    'polyclinic_id': poly_id,
                                    'polyclinic_name': poly['name'],
                                    'slot_id': s['slot_id'],
                                    'date': s.get('date', d),
                                    'time': s['time'],
                                    'doctor': s.get('doctor', ''),
                                    'randevu_type': rtype,
                                    'timestamp': now
                                }

                        alert_id = secrets.token_hex(4)
                        alert_data = {
                            'profile_id': profile['id'],
                            'profile_name': profile['name'],
                            'tc_masked': f"{profile['tc_kimlik'][:3]}***",
                            'rtype_label': rtype_label,
                            'specialty_name': active_name,
                            'polyclinic_name': poly['name'],
                            'dates': dates,
                            'slots_by_date': slots_by_date,
                            'all_slots': matched_slots,
                            'timestamp': now
                        }
                        context.bot_data['slot_alerts'][alert_id] = alert_data

                        msg_text, reply_markup = build_slot_alert_view(alert_data, alert_id, date_idx=0, slot_page=0)

                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=msg_text,
                                parse_mode="HTML",
                                reply_markup=reply_markup,
                                disable_notification=silent_mode
                            )
                        except Exception as e:
                            config.logger.error(f"Error sending slot alert to {chat_id}: {e}")

# Compatibility alias for central_scan_job
scan_job = central_scan_job

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler for all unhandled bot exceptions"""
    config.logger.error("Unhandled exception occurred:", exc_info=context.error)
