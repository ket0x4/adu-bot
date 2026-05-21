import re
import time
import secrets
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import db
import config
import keyboards
from scraper import ADUScraper

def clean_turkish(s):
    """Cleans a string for safe, character-invariant matching"""
    s = s.lower()
    s = s.replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def find_matching_specialty(tracked_name, active_specialties):
    """Matches a user's tracked department name with live active specialties"""
    cleaned_tracked = clean_turkish(tracked_name)
    for spec_id, spec_name in active_specialties:
        cleaned_active = clean_turkish(spec_name)
        if cleaned_tracked in cleaned_active or cleaned_active in cleaned_tracked:
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

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # 1. Intercept unauthorized users
    if not check_auth(chat_id):
        unauth_msg = (
            "⚠️ <b>Erişim Yetkiniz Yok!</b>\n\n"
            "Bu bot kişiye özel olarak yapılandırılmıştır ve sadece yetkili kişilerin kullanmasına izin verilir.\n\n"
            "Lütfen devam etmek için sistem yöneticisi (admin) tarafından size tanımlanan tek kullanımlık <b>Davet Kodunu</b> "
            "(Örn: <code>ADU-XXXX-XXXX</code>) doğrudan bu sohbete mesaj olarak gönderin:"
        )
        await update.message.reply_text(text=unauth_msg, parse_mode="HTML")
        return
        
    db.ensure_user_exists(chat_id)
    
    # Cancel any active profile wizard
    context.user_data.pop('adding_profile', None)
    
    welcome_text = (
        "🏥 <b>ADÜ Hastane Randevu Takip & Onay Botu</b>'na hoş geldiniz!\n\n"
        "Bu bot, Aydın Adnan Menderes Üniversitesi online randevu sisteminde boş slot "
        "bulunduğunda size bildirim atar ve <b>tek tıkla randevu kaydı</b> almanızı sağlar.\n\n"
        "🌟 <b>Özellikler:</b>\n"
        "• Çoklu Profil: Kendiniz, anne, baba veya arkadaşlarınız için profiller ekleyin.\n"
        "• Dinamik Takip: İstediğiniz bölümleri profil bazında takip listenize ekleyin.\n"
        "• Arka Plan Tarama: Belirlediğiniz süre aralığıyla otomatik tarama yapın.\n"
        "• Tek Tuşla Rezervasyon: Bilgilerinizle anında randevu kaydı gerçekleştirin.\n\n"
        "<i>Lütfen aşağıdaki menüden işlem seçin:</i>"
    )
    
    await update.message.reply_text(
        text=welcome_text,
        parse_mode="HTML",
        reply_markup=keyboards.get_main_keyboard(chat_id)
    )

# --- Text Handler (Wizard & Invitation Code Resolver) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # 1. Intercept unauthorized users & check for dynamic token entry
    if not check_auth(chat_id):
        token_upper = text.upper()
        if token_upper.startswith("ADU-") and db.validate_invitation_token(token_upper):
            # Claim token atomically to prevent TOCTOU race conditions
            if db.use_invitation_token(token_upper, chat_id):
                db.set_user_authorized(chat_id, True)
                
                success_auth = (
                    "🎉 <b>Davet Kodunuz Başarıyla Doğrulandı!</b>\n\n"
                    "Bot için tam erişim yetkiniz kalıcı olarak tanımlanmıştır.\n\n"
                    "Lütfen <b>/start</b> yazarak ana kontrol menüsüne gidin ve ilk profilinizi oluşturarak takibi başlatın!"
                )
                await update.message.reply_text(text=success_auth, parse_mode="HTML")
            else:
                await update.message.reply_text(
                    text="⚠️ <b>Bu davet kodu zaten kullanılmış!</b>\n\n"
                         "Lütfen yeni bir davet kodu girmeyi deneyin:",
                    parse_mode="HTML"
                )
            return
        else:
            await update.message.reply_text(
                text="⚠️ <b>Yetkisiz Giriş veya Geçersiz Davet Kodu!</b>\n\n"
                     "Lütfen size gönderilen davet kodunu doğru girdiğinizden emin olun (Örn: <code>ADU-XXXX-XXXX</code>):",
                parse_mode="HTML"
            )
            return

    # If the user is authorized and in the middle of adding a profile
    if 'adding_profile' in context.user_data:
        wizard = context.user_data['adding_profile']
        step = wizard.get('step')
        
        if step == 'name':
            wizard['name'] = text
            wizard['step'] = 'tc'
            await update.message.reply_text(
                text=f"👤 Profil: <b>{text}</b>\n\n"
                     f"Lütfen bu kişi için 11 haneli <b>T.C. Kimlik Numarasını</b> girin:",
                parse_mode="HTML"
            )
            return
            
        elif step == 'tc':
            if not text.isdigit() or len(text) != 11:
                await update.message.reply_text(
                    text="⚠️ <b>Hatalı T.C. Kimlik Numarası!</b>\n"
                         "Lütfen tam olarak 11 haneli bir sayı girin:",
                    parse_mode="HTML"
                )
                return
            wizard['tc'] = text
            wizard['step'] = 'birth'
            await update.message.reply_text(
                text=f"👤 Profil: <b>{wizard['name']}</b>\n"
                     f"🆔 T.C.: <code>{text[:3]}********</code>\n\n"
                     f"Lütfen doğum tarihini <b>GG.AA.YYYY</b> formatında girin (Örn: <code>15.08.1985</code>):",
                parse_mode="HTML"
            )
            return
            
        elif step == 'birth':
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
                await update.message.reply_text(
                    text="⚠️ <b>Hatalı Doğum Tarihi Formatı!</b>\n"
                         "Lütfen tarihi tam olarak GG.AA.YYYY formatında girin (Örn: <code>15.08.1985</code>):",
                    parse_mode="HTML"
                )
                return
            wizard['birth'] = text
            wizard['step'] = 'phone'
            await update.message.reply_text(
                text=f"👤 Profil: <b>{wizard['name']}</b>\n"
                     f"📅 Doğum Tarihi: <code>{text}</code>\n\n"
                     f"Lütfen <b>telefon numarasını</b> 11 haneli ve 0 ile başlayacak şekilde girin (Örn: <code>05051234567</code>):",
                parse_mode="HTML"
            )
            return
            
        elif step == 'phone':
            if not text.isdigit() or len(text) != 11 or not text.startswith("0"):
                await update.message.reply_text(
                    text="⚠️ <b>Hatalı Telefon Numarası!</b>\n"
                         "Telefon numarası `05` ile başlayan 11 haneli bir sayı olmalıdır (Örn: <code>05051234567</code>):",
                    parse_mode="HTML"
                )
                return
            
            # All steps completed! Save profile!
            db.add_profile(
                chat_id=chat_id,
                name=wizard['name'],
                tc_kimlik=wizard['tc'],
                dogum_tarihi=wizard['birth'],
                telefon=text
            )
            
            profile_name = wizard['name']
            context.user_data.pop('adding_profile', None)
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 Profillerime Git", callback_data="menu:profiles")
            ]])
            
            await update.message.reply_text(
                text=f"✅ <b>Profil Başarıyla Oluşturuldu!</b>\n\n"
                     f"👤 <b>İsim/Etiket:</b> {profile_name}\n"
                     f"🆔 <b>T.C. Kimlik:</b> <code>{wizard['tc'][:3]}******</code>\n"
                     f"📅 <b>Doğum Tarihi:</b> {wizard['birth']}\n"
                     f"📞 <b>Telefon:</b> {text}\n\n"
                     f"Artık bu profil için takip listesi oluşturabilirsiniz.",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return
            
    # Default text response if not in wizard
    await update.message.reply_text(
        text="⚠️ Anlaşılmadı. Menüyü açmak için lütfen /start yazın."
    )

# --- Callback Query Handler ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    
    # 1. Intercept unauthorized callback clicks
    if not check_auth(chat_id):
        await query.answer("⚠️ Erişim yetkiniz yok!", show_alert=True)
        return
        
    db.ensure_user_exists(chat_id)
    
    # Cancel add profile wizard on any button click
    context.user_data.pop('adding_profile', None)
    
    await query.answer()
    
    # 2. Main Menu
    if query.data == "menu:main":
        await query.message.edit_text(
            text="🏥 <i>Lütfen aşağıdaki menüden işlem seçin:</i>",
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )
        
    # 3. Profiles List
    elif query.data == "menu:profiles":
        profiles = db.get_profiles(chat_id)
        if not profiles:
            text = "👤 <b>Kayıtlı profiliniz bulunmamaktadır.</b>\n\nLütfen randevu takibi yapabilmek için 'Yeni Profil Ekle' butonuna basarak ilk profilinizi oluşturun."
        else:
            text = "👤 <b>Kayıtlı Profilleriniz:</b>\n\nİstediğiniz profilin detaylarını görmek veya silmek için ilgili isme tıklayın."
        
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profiles_keyboard(chat_id)
        )
        
    # 4. Add Profile Trigger
    elif query.data == "profile:add":
        context.user_data['adding_profile'] = {'step': 'name'}
        await query.message.edit_text(
            text="👤 <b>Yeni Profil Ekleme Sihirbazı</b>\n\n"
                 "Lütfen eklemek istediğiniz kişinin adını veya etiketini yazın (Örn: <code>Kendim</code>, <code>Annem</code>, <code>Babam</code>):",
            parse_mode="HTML"
        )
        
    # 5. View Profile Details
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
        
    # 6. Delete Profile
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
        
    # 7. Tracking Selection Profile List
    elif query.data == "menu:tracking":
        profiles = db.get_profiles(chat_id)
        if not profiles:
            await query.message.edit_text(
                text="⚠️ <b>Profil Bulunamadı!</b>\n\nRandevu bölümlerini takip edebilmek için öncelikle en az bir profil oluşturmalısınız.",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard(chat_id)
            )
            return
            
        await query.message.edit_text(
            text="🏥 <b>Bölüm Takip Listesi</b>\n\nHangi profil için randevu bölümlerini yönetmek istiyorsunuz?",
            parse_mode="HTML",
            reply_markup=keyboards.get_tracking_keyboard(chat_id)
        )
        
    # 8. View Profile's Tracked Specialties
    elif query.data.startswith("track:profile:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return
            
        tracked = db.get_profile_specialties(profile_id)
        if not tracked:
            text = f"🏥 <b>{profile['name']}</b> için takip edilen bölüm yok.\n\nAşağıdaki 'Bölüm Ekle' butonuna basarak takip etmek istediğiniz bölümleri ekleyebilirsiniz."
        else:
            text = f"🏥 <b>{profile['name']} için Takip Edilen Bölümler:</b>\n\n"
            for t in tracked:
                text += f"• {t['specialty_name']}\n"
            text += "\n<i>Bir bölümün takibini durdurmak için aşağıdaki ilgili ismin yanındaki [❌] butonuna basın:</i>"
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )
        
    # 9. Specialty Add Options
    elif query.data.startswith("track:add:"):
        profile_id = int(query.data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return
            
        await query.message.edit_text(
            text=f"🏥 <b>{profile['name']} için Bölüm Ekle</b>\n\nTakip listenize eklemek istediğiniz uzmanlık alanını seçin:",
            parse_mode="HTML",
            reply_markup=keyboards.get_track_add_keyboard(profile_id)
        )
        
    # 10. Perform Specialty Addition
    elif query.data.startswith("track:do_add:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        spec_id = int(parts[3])
        
        profile = db.get_profile_by_id(profile_id)
        spec_name = config.POPULAR_DEPARTMENTS.get(spec_id, "Bilinmeyen Bölüm")
        
        if profile:
            db.add_profile_specialty(profile_id, spec_id, spec_name)
            text = f"✅ <b>{spec_name}</b> bölümü <b>{profile['name']}</b>'in takip listesine eklendi."
        else:
            text = "Hata: Profil bulunamadı."
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )
        
    # 11. Perform Specialty Removal
    elif query.data.startswith("track:remove:"):
        parts = query.data.split(":")
        profile_id = int(parts[2])
        spec_id = int(parts[3])
        
        profile = db.get_profile_by_id(profile_id)
        if profile:
            db.remove_profile_specialty(profile_id, spec_id)
            text = "✅ Bölüm takibi başarıyla kaldırıldı."
        else:
            text = "Hata: Profil bulunamadı."
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )
        
    # 12. Settings (Interval Options)
    elif query.data == "menu:settings":
        await query.message.edit_text(
            text="⚙️ <b>Sorgulama Sıklığı Ayarı</b>\n\n"
                 "Botun arka planda boş randevuları kontrol etme sıklığını seçin (varsayılan 15 dakikadır):\n\n"
                 "⚠️ <i>Sorgulama sıklığının çok kısa olması IP adresinin hastane sunucuları tarafından geçici engellenmesine yol açabilir. 10 veya 15 dakika önerilir.</i>",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )
        
    # 13. Save Interval Setting
    elif query.data.startswith("settings:interval:"):
        interval = int(query.data.split(":")[-1])
        db.set_scan_interval(chat_id, interval)
        
        # If tracking is active, restart job with new interval
        user = db.get_user(chat_id)
        if user and user['is_scanning']:
            # Restart job
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs:
                job.schedule_removal()
            
            context.job_queue.run_repeating(
                callback=scan_job,
                interval=interval * 60,
                first=10,
                chat_id=chat_id,
                name=str(chat_id)
            )
            
        await query.message.edit_text(
            text=f"⚙️ Sorgulama sıklığı başarıyla <b>{interval} dakika</b> olarak ayarlandı.",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )
        
    # 14. Status Info View
    elif query.data == "menu:status":
        user = db.get_user(chat_id)
        profiles = db.get_profiles(chat_id)
        
        status_text = "🔄 <b>Sistem Durumu ve Bilgileri</b>\n\n"
        if not user:
            status_text += "Durum: Başlatılmadı."
        else:
            status_state = "🟢 TARAMA AKTİF" if user['is_scanning'] else "🔴 TARAMA DURDURULDU"
            status_text += f"⚙️ <b>Tarama Durumu:</b> {status_state}\n"
            status_text += f"⏰ <b>Sorgulama Aralığı:</b> {user['scan_interval']} dakika\n\n"
            
            status_text += "👤 <b>Kayıtlı Hastalar ve Takip Listeleri:</b>\n"
            if not profiles:
                status_text += "• Kayıtlı hasta profili yok."
            for p in profiles:
                specs = db.get_profile_specialties(p['id'])
                spec_names = ", ".join([s['specialty_name'] for s in specs]) if specs else "Takip edilen bölüm yok"
                status_text += f"• <b>{p['name']}</b>: <i>{spec_names}</i>\n"
                
        await query.message.edit_text(
            text=status_text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )
        
    # 15. Toggle Active Scan Job
    elif query.data == "menu:toggle_scan":
        user = db.get_user(chat_id)
        profiles = db.get_profiles(chat_id)
        
        if not user:
            return
            
        current_state = user['is_scanning']
        new_state = not current_state
        
        if new_state:
            # Prevent starting if no profiles or tracked specialties exist
            if not profiles:
                await query.message.edit_text(
                    text="⚠️ <b>Tarama Başlatılamadı!</b>\n\nTaramayı başlatabilmek için en az 1 adet profil oluşturmalısınız.",
                    parse_mode="HTML",
                    reply_markup=keyboards.get_main_keyboard(chat_id)
                )
                return
                
            has_specs = False
            for p in profiles:
                if db.get_profile_specialties(p['id']):
                    has_specs = True
                    break
            if not has_specs:
                await query.message.edit_text(
                    text="⚠️ <b>Tarama Başlatılamadı!</b>\n\nTaramayı başlatabilmek için en az 1 tane takip edilecek bölüm eklemelisiniz.",
                    parse_mode="HTML",
                    reply_markup=keyboards.get_main_keyboard(chat_id)
                )
                return
                
            db.set_scanning_state(chat_id, True)
            
            # Start job
            # Remove any duplicate jobs first
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs:
                job.schedule_removal()
                
            context.job_queue.run_repeating(
                callback=scan_job,
                interval=user['scan_interval'] * 60,
                first=3,  # Run first scan in 3 seconds!
                chat_id=chat_id,
                name=str(chat_id)
            )
            scan_details = ""
            for p in profiles:
                specs = db.get_profile_specialties(p['id'])
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
            
            # Stop job
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs:
                job.schedule_removal()
            text = "🔴 <b>Otomatik tarama DURDURULDU.</b>\n\nArka plan sorgulamaları sonlandırıldı. İstediğiniz zaman tekrar başlatabilirsiniz."
            
        await query.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )
        
    # 16. Perform Instant Auto Book on Click
    elif query.data.startswith("book:"):
        parts = query.data.split(":")
        profile_id = int(parts[1])
        spec_id = int(parts[2])
        poly_id = int(parts[3])
        slot_id = int(parts[4])
        
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.answer("Hata: Profil bulunamadı.", show_alert=True)
            return
            
        # Give immediate feedback to prevent double clicking
        await query.edit_message_text(
            text=query.message.text + f"\n\n⏳ <b>{profile['name']} için randevu alma işlemi başlatıldı... Lütfen bekleyin.</b>",
            parse_mode="HTML"
        )
        
        scraper = ADUScraper()
        
        # Trigger the reservation!
        success, message = scraper.book_appointment(
            specialty_id=spec_id,
            polyclinic_id=poly_id,
            slot_id=slot_id,
            tc_kimlik=profile['tc_kimlik'],
            dogum_tarihi=profile['dogum_tarihi'],
            telefon=profile['telefon']
        )
        
        if success:
            finished_text = (
                query.message.text + 
                f"\n\n✅ <b>Randevu Alma İşlemi Başarılı!</b>\n"
                f"🎉 Hastane Mesajı: <i>{message}</i>"
            )
            await query.edit_message_text(text=finished_text, parse_mode="HTML")
            await query.answer("Randevunuz başarıyla alınmıştır! 🎉", show_alert=True)
        else:
            failed_text = (
                query.message.text + 
                f"\n\n❌ <b>Randevu Alınamadı!</b>\n"
                f"⚠️ Hata Nedeni: <i>{message}</i>"
            )
            await query.edit_message_text(text=failed_text, parse_mode="HTML")
            await query.answer(f"Randevu alma başarısız oldu: {message}", show_alert=True)

    # --- Master Admin Panel Handlers ---
    
    # Admin Panel Main View
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
            f"Aşağıdaki butonları kullanarak davet kodları üretebilir, kullanılmamış kodları iptal edebilir veya aktif kullanıcıların yetkilerini (Revoke) silebilirsiniz."
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
        
    # Admin: Generate Invitation Code
    elif query.data == "admin:gen_token":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        token = make_token()
        db.add_invitation_token(token)
        
        token_text = (
            f"✅ <b>Yeni Tek Kullanımlık Davet Kodu Üretildi!</b>\n\n"
            f"🔑 <b>Kod:</b> <code>{token}</code>\n\n"
            f"Bu kodu yetki vermek istediğiniz kişiye iletin. Kullanıcı bota bu kodu mesaj olarak attığı an erişim hakkı kalıcı olarak tanımlanacaktır."
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
        
    # Admin: List Unused Tokens
    elif query.data == "admin:list_tokens":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        tokens = db.get_unused_tokens()
        if not tokens:
            list_display_text = "📜 <b>Kullanılmamış aktif davet kodu bulunmuyor.</b>\n\nYeni kod oluşturmak için 'Davet Kodu Üret' butonuna basın."
            keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
        else:
            list_display_text = "📜 <b>Aktif Davet Kodları (Kullanılmamış):</b>\n\nSilmek/İptal etmek istediğiniz davet kodunun yanındaki [❌] butonuna tıklayın."
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
        
    # Admin: Delete Unused Token
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
            list_display_text = "📜 <b>Aktif Davet Kodları (Kullanılmamış):</b>\n\nSilmek/İptal etmek istediğiniz davet kodunun yanındaki [❌] butonuna tıklayın."
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
        
    # Admin: List Users
    elif query.data == "admin:list_users":
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        users = db.get_authorized_users()
        filtered_users = [u for u in users if str(u['chat_id']) != config.ADMIN_CHAT_ID]
        
        if not filtered_users:
            users_text = "👥 <b>Kayıtlı aktif kullanıcı bulunmamaktadır (Siz hariç).</b>"
            keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
        else:
            users_text = (
                "👥 <b>Yetkilendirilmiş Aktif Kullanıcılar:</b>\n\n"
                "Aşağıdaki listede her kullanıcının Telegram ID'si ve eklediği kişilerin sayısı gösterilmektedir.\n\n"
                "⚠️ <b>İptal (Revoke):</b> Bir kullanıcının yetkisini iptal ettiğinizde, o kullanıcının tüm profilleri, takip listeleri veritabanından kalıcı olarak silinir ve arka plandaki tüm tarama işleri sonlandırılır."
            )
            keyboard = []
            for u in filtered_users:
                profiles = db.get_profiles(u['chat_id'])
                profiles_str = f"({len(profiles)} Profil)" if profiles else "(Profil yok)"
                keyboard.append([
                    InlineKeyboardButton(f"❌ Revoke ID: {u['chat_id']} {profiles_str}", callback_data=f"admin:revoke:{u['chat_id']}")
                ])
            keyboard.append([InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")])
            
        await query.message.edit_text(
            text=users_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    # Admin: Perform User Revocation
    elif query.data.startswith("admin:revoke:"):
        if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
            await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
            return
            
        user_to_revoke = query.data.split(":")[-1]
        
        # Stop background job if active
        jobs = context.job_queue.get_jobs_by_name(str(user_to_revoke))
        for job in jobs:
            job.schedule_removal()
            
        # Inform the user directly
        try:
            await context.bot.send_message(
                chat_id=user_to_revoke,
                text="⚠️ <b>Erişim Yetkiniz İptal Edildi!</b>\n\nAdmin tarafından bu bota erişim yetkiniz kaldırılmıştır. Arka plandaki taramalarınız durdurulmuş ve tüm profilleriniz silinmiştir.",
                parse_mode="HTML"
            )
        except Exception as e:
            config.logger.error(f"Could not notify revoked user {user_to_revoke}: {e}")
            
        # Database purge
        db.revoke_user(user_to_revoke)
        
        await query.answer(f"Kullanıcı yetkisi iptal edildi (Revoked): {user_to_revoke}", show_alert=True)
        
        users = db.get_authorized_users()
        filtered_users = [u for u in users if str(u['chat_id']) != config.ADMIN_CHAT_ID]
        
        if not filtered_users:
            users_text = "👥 <b>Kayıtlı aktif kullanıcı bulunmamaktadır (Siz hariç).</b>"
            keyboard = [[InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")]]
        else:
            users_text = (
                "👥 <b>Yetkilendirilmiş Aktif Kullanıcılar:</b>\n\n"
                "Aşağıdaki listede her kullanıcının Telegram ID'si ve eklediği kişilerin sayısı gösterilmektedir.\n\n"
                "⚠️ <b>İptal (Revoke):</b> Bir kullanıcının yetkisini iptal ettiğinizde, o kullanıcının tüm profilleri, takip listeleri veritabanından kalıcı olarak silinir ve arka plandaki tüm tarama işleri sonlandırılır."
            )
            keyboard = []
            for u in filtered_users:
                profiles = db.get_profiles(u['chat_id'])
                profiles_str = f"({len(profiles)} Profil)" if profiles else "(Profil yok)"
                keyboard.append([
                    InlineKeyboardButton(f"❌ Revoke ID: {u['chat_id']} {profiles_str}", callback_data=f"admin:revoke:{u['chat_id']}")
                ])
            keyboard.append([InlineKeyboardButton("🔙 Yetki Paneli", callback_data="menu:admin")])
            
        await query.message.edit_text(
            text=users_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
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
        
    config.logger.info(f"Background check starting for chat_id: {chat_id}")
    
    # 1. Fetch live specialties from site
    scraper = ADUScraper()
    active_specs = scraper.get_specialties()
    if not active_specs:
        config.logger.info("No active specialties found on randevu.adu.edu.tr (everything is fully booked).")
        return
        
    # 2. Iterate through each profile
    for profile in profiles:
        tracked_specs = db.get_profile_specialties(profile['id'])
        if not tracked_specs:
            continue
            
        for tracked in tracked_specs:
            match = find_matching_specialty(tracked['specialty_name'], active_specs)
            if not match:
                continue
                
            active_id, active_name = match
            config.logger.info(f"Tracked department '{tracked['specialty_name']}' is ACTIVE on site as '{active_name}' (ID: {active_id}).")
            
            # 3. Fetch polyclinics
            time.sleep(1.5)
            polyclinics = scraper.get_polyclinics(active_id)
            if not polyclinics:
                continue
                
            # 4. Check slots
            for poly in polyclinics:
                time.sleep(1.5)
                slots = scraper.check_slots(active_id, poly['id'])
                if not slots:
                    continue
                    
                config.logger.info(f"FOUND slots in {poly['name']}!")
                
                for slot in slots:
                    alert_key = f"{profile['id']}_{slot['slot_id']}"
                    if 'sent_alerts' not in context.bot_data:
                        context.bot_data['sent_alerts'] = {}
                        
                    now = time.time()
                    last_sent = context.bot_data['sent_alerts'].get(alert_key, 0)
                    if now - last_sent < 3600:
                        continue
                        
                    context.bot_data['sent_alerts'][alert_key] = now
                    
                    msg = (
                        f"🚨 <b>ADÜ BOŞ RANDEVU BİLDİRİMİ!</b>\n\n"
                        f"👤 <b>Hasta Profili:</b> {profile['name']} ({profile['tc_kimlik'][:3]}***)\n"
                        f"🏥 <b>Ana Bölüm:</b> {active_name}\n"
                        f"🩺 <b>Poliklinik:</b> {poly['name']}\n"
                        f"📅 <b>Tarih:</b> {slot['date']}\n"
                        f"⏰ <b>Saat:</b> <b>{slot['time']}</b>\n"
                        f"👨‍⚕️ <b>Hekim:</b> {slot['doctor']}\n\n"
                        f"⚡️ <i>Aşağıdaki butona tıklayarak profil bilgileriyle hastaneden randevuyu anında onaylayıp alabilirsiniz!</i>"
                    )
                    
                    callback_data = f"book:{profile['id']}:{active_id}:{poly['id']}:{slot['slot_id']}"
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("⚡️ Randevuyu Benim İçin Anında Al", callback_data=callback_data)]
                    ])
                    
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
