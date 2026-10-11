import time
from telegram import Update
from telegram.ext import ContextTypes
import db
import config
import keyboards
from scraper import ADUScraper
from handlers.common import check_auth

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler for all unhandled bot exceptions."""
    config.logger.error("Unhandled exception occurred:", exc_info=context.error)
