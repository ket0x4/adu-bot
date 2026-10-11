import re
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import db
import keyboards
from handlers.common import check_auth

def validate_tc_kimlik(tc: str) -> bool:
    """Validates 11-digit Turkish identification number format."""
    tc_clean = str(tc).strip()
    return tc_clean.isdigit() and len(tc_clean) == 11

def validate_birth_date(date_str: str) -> bool:
    """Validates DD.MM.YYYY birth date format and valid calendar date."""
    m = re.match(r'^(\d{2})\.(\d{2})\.(\d{4})$', str(date_str).strip())
    if not m:
        return False
    d, m_val, y = map(int, m.groups())
    try:
        dt = datetime.date(y, m_val, d)
        today = datetime.date.today()
        # Must be in the past, reasonably after 1900
        return 1900 <= y <= today.year and dt <= today
    except ValueError:
        return False

def clean_phone_number(phone: str) -> str | None:
    """Cleans phone string and normalizes to 11-digit 05XXXXXXXXX format, or None if invalid."""
    clean = re.sub(r'[\s\-\(\)\+]', '', str(phone).strip())
    if clean.startswith("90") and len(clean) == 12:
        clean = clean[2:]
    if len(clean) == 10 and clean.startswith("5"):
        clean = "0" + clean
    if clean.isdigit() and len(clean) == 11 and clean.startswith("05"):
        return clean
    return None

async def handle_unauthorized_user(update: Update, text: str) -> bool:
    """Handles messages from unauthorized users, verifying invitation tokens."""
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

async def handle_profile_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> bool:
    """Step-by-step wizard for creating a new patient profile."""
    if 'adding_profile' not in context.user_data:
        return False

    wizard = context.user_data['adding_profile']
    step = wizard.get('step')

    if step == 'name':
        wizard['name'] = text.strip()
        wizard['step'] = 'tc'
        await update.message.reply_text(
            text=f"👤 Profil: <b>{wizard['name']}</b>\n\nLütfen 11 haneli <b>T.C. Kimlik Numarasını</b> girin:",
            parse_mode="HTML"
        )
        return True

    elif step == 'tc':
        if not validate_tc_kimlik(text):
            await update.message.reply_text(
                text="⚠️ <b>Hatalı T.C. Kimlik!</b>\nLütfen tam olarak 11 haneli sayı girin:",
                parse_mode="HTML"
            )
            return True
        wizard['tc'] = text.strip()
        wizard['step'] = 'birth'
        await update.message.reply_text(
            text=f"👤 Profil: <b>{wizard['name']}</b>\n"
                 f"🆔 T.C.: <code>{text[:3]}********</code>\n\n"
                 f"Lütfen doğum tarihini <b>GG.AA.YYYY</b> formatında girin (Örn: <code>15.08.1985</code>):",
            parse_mode="HTML"
        )
        return True

    elif step == 'birth':
        if not validate_birth_date(text):
            await update.message.reply_text(
                text="⚠️ <b>Hatalı Doğum Tarihi Formatı!</b>\nLütfen tarihi tam olarak geçerli bir GG.AA.YYYY formatında girin (Örn: <code>15.08.1985</code>):",
                parse_mode="HTML"
            )
            return True
        wizard['birth'] = text.strip()
        wizard['step'] = 'phone'
        await update.message.reply_text(
            text=f"👤 Profil: <b>{wizard['name']}</b>\n"
                 f"📅 Doğum Tarihi: <code>{text.strip()}</code>\n\n"
                 f"Lütfen <b>telefon numarasını</b> 11 haneli ve 0 ile başlayacak şekilde girin (Örn: <code>05051234567</code>):",
            parse_mode="HTML"
        )
        return True

    elif step == 'phone':
        clean_p = clean_phone_number(text)
        if not clean_p:
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

async def handle_profile_edit_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> bool:
    """Handles text input for editing an existing profile (name or phone)."""
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
        clean_p = clean_phone_number(text)
        if not clean_p:
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
    """Main message handler dispatching to authorization and wizard steps."""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    if not check_auth(chat_id):
        if await handle_unauthorized_user(update, text):
            return

    if await handle_profile_wizard(update, context, chat_id, text):
        return

    if await handle_profile_edit_wizard(update, context, chat_id, text):
        return

    await update.message.reply_text(
        text="⚠️ Menüyü görüntülemek için lütfen /start yazın."
    )

# Aliases for backwards compatibility
_handle_unauthorized_user = handle_unauthorized_user
_handle_profile_wizard = handle_profile_wizard
_handle_profile_edit_wizard = handle_profile_edit_wizard
