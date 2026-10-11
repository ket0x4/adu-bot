import re
import time
import asyncio
import secrets
import string
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import db
import config
import keyboards
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
    # 1. Match by exact department ID
    for spec_id, spec_name in active_specialties:
        if spec_id == tracked_id:
            return spec_id, spec_name

    # 2. Match by clean name fallback
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

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # 1. Intercept unauthorized users
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
    
    welcome_text = (
        "🏥 <b>ADÜ Hastane Randevu Takip & Otomatik Rezervasyon Botu</b>'na hoş geldiniz!\n\n"
        "Aydın Adnan Menderes Üniversitesi (ADÜ) randevu sisteminde takip ettiğiniz bölümlerde boş slot açıldığında bot anında sizi bilgilendirir "
        "ve <b>tek tuşla onaylayarak randevu almanızı</b> sağlar.\n\n"
        "🌟 <b>Neler Yapabilirsiniz?</b>\n"
        "• <b>Profillerim:</b> Kendiniz veya yakınlarınız için hasta profilleri tanımlayın.\n"
        "• <b>Takip Ettiklerim:</b> ADÜ bünyesindeki 52 uzmanlık alanından istediklerinizi profil bazında takibe alın.\n"
        "• <b>Otomatik Tarama:</b> Belirlediğiniz sıklıkta (5-60 dk) arka planda kesintisiz sorgulama yapın.\n"
        "• <b>Hızlı Rezervasyon:</b> Boş randevu bildirimindeki butona tıklayarak bilgilerinizi hastaneye iletin.\n\n"
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
        "3️⃣ <b>Taramayı Başlatma:</b>\n"
        "Ana menüden <b>▶️ Taramayı Başlat</b> butonuna tıklayın. Bot periyodik olarak hastane sunucularını taramaya başlar.\n\n"
        "4️⃣ <b>Randevu Bildirimi & Alma:</b>\n"
        "Boş slot açıldığında bildirim mesajı ve randevu saati butonu gelir. Butona tek tıkla basarak kaydınızı anında tamamlayabilirsiniz!"
    )
    await update.message.reply_text(text=help_text, parse_mode="HTML")

# --- Text Handler (Wizard & Invitation Code Resolver) ---

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

        # Save profile to database
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
                 f"🆔 <b>T.C. Kimlik:</b> <code>{wizard['tc'][:3]}********</code>\n"
                 f"📅 <b>Doğum Tarihi:</b> {wizard['birth']}\n"
                 f"📞 <b>Telefon:</b> {clean_p}\n\n"
                 f"Artık bu profil için takip listesi oluşturabilirsiniz.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return True

    return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # 1. Intercept unauthorized users
    if not check_auth(chat_id):
        if await _handle_unauthorized_user(update, text):
            return

    # 2. Wizard handling
    if await _handle_profile_wizard(update, context, chat_id, text):
        return

    # Default message response
    await update.message.reply_text(
        text="⚠️ Menüyü görüntülemek için lütfen /start yazın."
    )

# --- Callback Query Handler ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    
    # Intercept unauthorized callback clicks
    if not check_auth(chat_id):
        await query.answer("⚠️ Erişim yetkiniz yok!", show_alert=True)
        return
        
    db.ensure_user_exists(chat_id)
    context.user_data.pop('adding_profile', None)
    
    # Noop button (e.g. page info)
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
            text = "👤 <b>Kayıtlı Profilleriniz:</b>\n\nİstediğiniz profilin detaylarını görmek veya silmek için ilgili isme tıklayın."
        
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
            
        details = (
            f"👤 <b>Profil Detayları:</b>\n\n"
            f"🏷️ <b>İsim/Etiket:</b> {profile['name']}\n"
            f"🆔 <b>T.C. Kimlik:</b> <code>{profile['tc_kimlik'][:3]}******{profile['tc_kimlik'][-2:]}</code>\n"
            f"📅 <b>Doğum Tarihi:</b> {profile['dogum_tarihi']}\n"
            f"📞 <b>Telefon:</b> {profile['telefon']}\n"
        )
        await query.message.edit_text(
            text=details,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_view_keyboard(profile_id)
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

    # 10. Legacy Direct Add (Compatibility)
    elif query.data.startswith("track:do_add:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        spec_id = int(parts[3])
        profile = db.get_profile_by_id(profile_id)
        spec_name = config.ADU_DEPARTMENTS.get(spec_id, f"Bölüm ({spec_id})")
        if profile:
            db.add_profile_specialty(profile_id, spec_id, spec_name)
            await query.answer(f"✅ {spec_name} takibe eklendi!")
        await query.message.edit_text(
            text=f"✅ <b>{spec_name}</b> bölümü takip listenize eklendi.",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
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

    # 13. Settings (Interval & Appointment Type Options)
    elif query.data == "menu:settings":
        user = db.get_user(chat_id)
        rtype = user.get('randevu_type', 0) if user else 0
        rtype_desc = config.RANDEVU_TYPES.get(rtype, "Tümü")
        await query.message.edit_text(
            text=f"⚙️ <b>Sorgulama ve Randevu Ayarları</b>\n\n"
                 f"⏰ <b>Sorgulama Sıklığı:</b> Boş randevuları kontrol etme periyodu.\n"
                 f"🏥 <b>Randevu Türü Tercihi:</b> <b>{rtype_desc}</b>\n\n"
                 f"💡 <i>Özel Öğretim Üyesi seçeneği profesör, doçent ve öğretim üyelerinin saat 15:00 randevularını kapsar.</i>",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )

    # 14. Save Interval Setting
    elif query.data.startswith("settings:interval:"):
        interval = int(query.data.split(":")[-1])
        db.set_scan_interval(chat_id, interval)
        
        user = db.get_user(chat_id)
        if user and user['is_scanning']:
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs:
                job.schedule_removal()
            
            context.job_queue.run_repeating(
                callback=scan_job,
                interval=interval * 60,
                first=5,
                chat_id=chat_id,
                name=str(chat_id)
            )
            
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

    # 15. Status Info View
    elif query.data == "menu:status":
        user = db.get_user(chat_id)
        profiles = db.get_profiles(chat_id)
        
        status_text = "🔄 <b>Sistem Durumu ve Bilgileri</b>\n\n"
        if not user:
            status_text += "Durum: Başlatılmadı."
        else:
            status_state = "🟢 TARAMA AKTİF" if user['is_scanning'] else "🔴 TARAMA DURDURULDU"
            rtype = user.get('randevu_type', 0)
            rtype_desc = config.RANDEVU_TYPES.get(rtype, "Tümü (Normal + Özel Öğretim Üyesi)")
            status_text += f"⚙️ <b>Tarama Durumu:</b> {status_state}\n"
            status_text += f"⏰ <b>Sorgulama Aralığı:</b> {user['scan_interval']} dakika\n"
            status_text += f"🏷️ <b>Randevu Türü:</b> {rtype_desc}\n\n"
            
            status_text += f"👤 <b>Kayıtlı Hastalar ({len(profiles)} kişi):</b>\n"
            if not profiles:
                status_text += "• Kayıtlı hasta profili yok.\n"
            else:
                all_specs = db.get_profiles_specialties([p['id'] for p in profiles])
                for p in profiles:
                    specs = all_specs.get(p['id'], [])
                    if specs:
                        spec_names = ", ".join([s['specialty_name'] for s in specs[:3]])
                        if len(specs) > 3:
                            spec_names += f" ve {len(specs)-3} diğer"
                    else:
                        spec_names = "Takip edilen bölüm yok"
                    status_text += f"• <b>{p['name']}</b>: <i>{spec_names}</i>\n"
                
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
            
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs:
                job.schedule_removal()
                
            context.job_queue.run_repeating(
                callback=scan_job,
                interval=user['scan_interval'] * 60,
                first=3,
                chat_id=chat_id,
                name=str(chat_id)
            )
            
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
                "Bot arka planda sürekli olarak hastane sistemini sorgulayacak ve boş randevu yakaladığında sizi anında uyaracaktır."
            )
        else:
            db.set_scanning_state(chat_id, False)
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs:
                job.schedule_removal()
            text = "🔴 <b>Otomatik tarama DURDURULDU.</b>\n\nArka plan sorgulamaları sonlandırıldı. İstediğiniz zaman tekrar başlatabilirsiniz."
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )

    # 17. Perform Instant Auto Book on Click (using cached short slot token)
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

        # Immediate feedback to prevent duplicate taps
        await query.edit_message_text(
            text=query.message.text + f"\n\n⏳ <b>{profile['name']} için {slot_info['time']} randevusu alınıyor... Lütfen bekleyin.</b>",
            parse_mode="HTML"
        )
        
        scraper = ADUScraper()
        success, message = await asyncio.to_thread(
            scraper.book_appointment,
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
            await query.edit_message_text(text=finished_text, parse_mode="HTML")
            await query.answer("Randevunuz başarıyla alınmıştır! 🎉", show_alert=True)
        else:
            failed_text = (
                query.message.text + 
                f"\n\n❌ <b>Randevu Alınamadı!</b>\n"
                f"⚠️ Hata Nedeni: <i>{html.escape(message)}</i>"
            )
            await query.edit_message_text(text=failed_text, parse_mode="HTML")
            await query.answer(f"Randevu alma başarısız: {message}", show_alert=True)

    # --- Master Admin Panel Handlers ---
    
    elif query.data == "menu:admin":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        unused_tokens = db.get_unused_tokens()
        auth_users = db.get_authorized_users()
        auth_users_count = len([u for u in auth_users if str(u['chat_id']) != config.ADMIN_CHAT_ID])
        
        admin_text = (
            f"🔑 <b>ADÜ Bot Yetki Yönetim Paneli</b>\n\n"
            f"👥 <b>Yetkili Aktif Kullanıcılar:</b> {auth_users_count} kişi (Siz hariç)\n"
            f"📜 <b>Kullanılmamış Davet Kodları:</b> {len(unused_tokens)} adet\n\n"
            f"Aşağıdaki butonları kullanarak davet kodları üretebilir veya kullanıcı yetkilerini silebilirsiniz."
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ Davet Kodu Üret", callback_data="admin:gen_token"),
                InlineKeyboardButton("📜 Aktif Kodları Gör", callback_data="admin:list_tokens")
            ],
            [
                InlineKeyboardButton("👥 Kullanıcıları Listele", callback_data="admin:list_users")
            ],
            [
                InlineKeyboardButton("🔙 Ana Menü", callback_data="menu:main")
            ]
        ]
        await query.message.edit_text(
            text=admin_text,
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
        jobs = context.job_queue.get_jobs_by_name(str(user_to_revoke))
        for job in jobs:
            job.schedule_removal()
            
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

# --- Background Scanning Job Callback ---

async def scan_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    user = db.get_user(chat_id)
    
    if not user or not user['is_scanning'] or not user.get('is_authorized', 0):
        context.job.schedule_removal()
        return
        
    profiles = db.get_profiles(chat_id)
    if not profiles:
        return
        
    config.logger.info(f"Background hospital scan starting for chat_id: {chat_id}")
    
    preferred_rtype = user.get('randevu_type', 0)
    if preferred_rtype == 1:
        types_to_scan = [1]
    elif preferred_rtype == 2:
        types_to_scan = [2]
    else:
        types_to_scan = [1, 2]  # Scans both Normal and Özel Öğretim Üyesi!

    scraper = ADUScraper()
    all_tracked_specs = db.get_profiles_specialties([p['id'] for p in profiles])

    # Per-cycle cache to avoid duplicate network calls for shared departments
    polyclinic_cache = {}  # (spec_id, rtype) -> list of polyclinic dicts
    slots_cache = {}       # (spec_id, poly_id, rtype) -> list of slots

    for rtype in types_to_scan:
        rtype_label = "🌟 Özel Öğretim Üyesi (15:00)" if rtype == 2 else "🩺 Normal Randevu"
        active_specs = await asyncio.to_thread(scraper.get_specialties, randevu_type=rtype)
        if not active_specs:
            continue

        for profile in profiles:
            tracked_specs = all_tracked_specs.get(profile['id'], [])
            if not tracked_specs:
                continue

            for tracked in tracked_specs:
                match = find_matching_specialty(tracked['specialty_id'], tracked['specialty_name'], active_specs)
                if not match:
                    continue

                active_id, active_name = match
                config.logger.info(f"Tracked department '{tracked['specialty_name']}' is ACTIVE on site for {rtype_label} (ID: {active_id}).")

                # Fetch polyclinics
                cache_key_poly = (active_id, rtype)
                if cache_key_poly not in polyclinic_cache:
                    await asyncio.sleep(0.8)
                    polyclinic_cache[cache_key_poly] = await asyncio.to_thread(scraper.get_polyclinics, active_id, randevu_type=rtype)

                polyclinics = polyclinic_cache[cache_key_poly]
                if not polyclinics:
                    continue

                # Check slots for each polyclinic
                for poly in polyclinics:
                    poly_id = poly['id']
                    cache_key_slots = (active_id, poly_id, rtype)
                    if cache_key_slots not in slots_cache:
                        await asyncio.sleep(0.8)
                        slots_cache[cache_key_slots] = await asyncio.to_thread(scraper.check_slots, active_id, poly_id, randevu_type=rtype)

                    slots = slots_cache[cache_key_slots]
                    if not slots:
                        continue

                    config.logger.info(f"FOUND {len(slots)} free slots in {poly['name']} ({rtype_label})!")

                    # Group slots by date
                    slots_by_date = {}
                    for slot in slots:
                        d = slot['date']
                        slots_by_date.setdefault(d, []).append(slot)

                    now = time.time()
                    if 'sent_alerts' not in context.bot_data:
                        context.bot_data['sent_alerts'] = {}

                    for date_val, day_slots in slots_by_date.items():
                        alert_key = f"{profile['id']}_{poly_id}_{date_val}_{rtype}"
                        last_sent = context.bot_data['sent_alerts'].get(alert_key, 0)
                        # Don't repeat the exact same date alert within 45 minutes
                        if now - last_sent < 2700:
                            continue

                        context.bot_data['sent_alerts'][alert_key] = now

                        # Take top 3 earliest slots to show direct booking buttons
                        earliest_slots = day_slots[:3]
                        keyboard_rows = []

                        for s in earliest_slots:
                            slot_key = secrets.token_hex(4)
                            context.bot_data.setdefault('slot_cache', {})[slot_key] = {
                                'specialty_id': active_id,
                                'polyclinic_id': poly_id,
                                'slot_id': s['slot_id'],
                                'date': s['date'],
                                'time': s['time'],
                                'doctor': s['doctor'],
                                'randevu_type': rtype,
                                'timestamp': now
                            }
                            cb_data = f"book:{profile['id']}:{slot_key}"
                            keyboard_rows.append([
                                InlineKeyboardButton(f"⚡️ {s['time']} Randevusunu Al", callback_data=cb_data)
                            ])

                        times_summary = ", ".join([s['time'] for s in day_slots[:8]])
                        if len(day_slots) > 8:
                            times_summary += f" ... (+{len(day_slots)-8} slot)"

                        msg = (
                            f"🚨 <b>ADÜ BOŞ RANDEVU BULUNDU!</b>\n\n"
                            f"👤 <b>Hasta Profili:</b> {profile['name']} ({profile['tc_kimlik'][:3]}***)\n"
                            f"🏷️ <b>Randevu Türü:</b> <b>{rtype_label}</b>\n"
                            f"🏥 <b>Ana Bölüm:</b> {active_name}\n"
                            f"🩺 <b>Poliklinik/Hekim:</b> {poly['name']}\n"
                            f"📅 <b>Tarih:</b> {date_val}\n"
                            f"⏰ <b>Uygun Saatler:</b> {times_summary}\n"
                            f"📊 <b>Toplam Boş Slot:</b> {len(day_slots)} adet\n\n"
                            f"⚡️ <i>Aşağıdaki butona basarak doğrudan bu hekimden randevunuzu onaylayabilirsiniz:</i>"
                        )

                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(keyboard_rows)
                        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler for all unhandled bot exceptions"""
    config.logger.error("Unhandled exception occurred:", exc_info=context.error)
