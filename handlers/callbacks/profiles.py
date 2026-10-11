from telegram import Update
from telegram.ext import ContextTypes
import db
import keyboards

async def handle_profile_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data

    # Add Profile Trigger
    if data == "profile:add":
        context.user_data['adding_profile'] = {'step': 'name'}
        await query.message.edit_text(
            text="👤 <b>Yeni Profil Ekleme Sihirbazı</b>\n\n"
                 "Lütfen eklemek istediğiniz kişinin adını veya etiketini yazın (Örn: <code>Kendim</code>, <code>Annem</code>, <code>Babam</code>):",
            parse_mode="HTML"
        )
        return True

    # View Profile Details
    elif data.startswith("profile:view:"):
        profile_id = int(data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return True
            
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
        return True

    # Profile Preferences / Sniper View
    elif data.startswith("pref:view:"):
        profile_id = int(data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            return True
        
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
        return True

    # Toggle Auto-Book Sniper
    elif data.startswith("pref:toggle_auto:"):
        profile_id = int(data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            new_val = 0 if profile.get('auto_book', 0) else 1
            db.set_profile_auto_book(profile_id, new_val)
            stat_lbl = "AÇILDI 🎯" if new_val else "KAPATILDI ⚪️"
            await query.answer(f"Sniper Modu {stat_lbl}")
            await query.message.edit_reply_markup(reply_markup=keyboards.get_profile_prefs_keyboard(profile_id))
        return True

    # Set Date Filter
    elif data.startswith("pref:date:"):
        parts = data.split(":")
        profile_id = int(parts[2])
        days = int(parts[3])
        db.set_profile_filter_date(profile_id, days)
        await query.answer(f"Tarih filtresi: {'Tümü' if days == 0 else f'{days} Gün'}")
        await query.message.edit_reply_markup(reply_markup=keyboards.get_profile_prefs_keyboard(profile_id))
        return True

    # Set Time Filter
    elif data.startswith("pref:time:"):
        parts = data.split(":")
        profile_id = int(parts[2])
        time_pref = int(parts[3])
        db.set_profile_filter_time(profile_id, time_pref)
        t_lbl = "Tüm Gün" if time_pref == 0 else ("Sabah" if time_pref == 1 else "Öğle")
        await query.answer(f"Saat tercihi: {t_lbl}")
        await query.message.edit_reply_markup(reply_markup=keyboards.get_profile_prefs_keyboard(profile_id))
        return True

    # Edit Profile Menu
    elif data.startswith("profile:edit:"):
        profile_id = int(data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            return True
        await query.message.edit_text(
            text=f"✏️ <b>{profile['name']} Profilini Düzenle</b>\n\nGüncellemek istediğiniz alanı seçin:",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_edit_keyboard(profile_id)
        )
        return True

    # Edit Profile Name Prompt
    elif data.startswith("profile:edit_name:"):
        profile_id = int(data.split(":")[-1])
        context.user_data['editing_profile'] = {'profile_id': profile_id, 'type': 'name'}
        await query.message.edit_text(
            text="✏️ <b>İsim / Etiket Güncelleme:</b>\n\nLütfen bu profil için yeni ismi yazıp gönderin:",
            parse_mode="HTML"
        )
        return True

    # Edit Profile Phone Prompt
    elif data.startswith("profile:edit_phone:"):
        profile_id = int(data.split(":")[-1])
        context.user_data['editing_profile'] = {'profile_id': profile_id, 'type': 'phone'}
        await query.message.edit_text(
            text="📞 <b>Telefon Numarası Güncelleme:</b>\n\nLütfen 0 ile başlayan yeni 11 haneli telefon numarasını yazıp gönderin (Örn: <code>05051234567</code>):",
            parse_mode="HTML"
        )
        return True

    # Delete Profile
    elif data.startswith("profile:delete:"):
        profile_id = int(data.split(":")[-1])
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
        return True

    return False
