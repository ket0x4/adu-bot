from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import db
import config
from handlers.common import make_token, get_admin_users_view

async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data

    if not (data == "menu:admin" or data.startswith("admin:")):
        return False

    if not config.ADMIN_CHAT_ID or str(chat_id) != config.ADMIN_CHAT_ID:
        await query.answer("⚠️ Yetkiniz yok!", show_alert=True)
        return True

    # Main Admin Panel View
    if data == "menu:admin":
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
            reply_markup=keyboards.get_admin_keyboard() if hasattr(keyboards, 'get_admin_keyboard') else None
        )
        return True

    elif data == "admin:metrics":
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
        return True

    elif data == "admin:gen_token":
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
        return True

    elif data == "admin:list_tokens":
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
        return True

    elif data.startswith("admin:del_token:"):
        token_to_del = data.split(":")[-1]
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
        return True

    elif data == "admin:list_users":
        users_text, users_markup = get_admin_users_view()
        await query.message.edit_text(
            text=users_text,
            parse_mode="HTML",
            reply_markup=users_markup
        )
        return True

    elif data.startswith("admin:revoke:"):
        user_to_revoke = data.split(":")[-1]
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
        return True

    return False
