from telegram import Update
from telegram.ext import ContextTypes
import db
import config
import keyboards

async def handle_tracking_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data

    # View Profile's Tracked Specialties
    if data.startswith("track:profile:"):
        profile_id = int(data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return True
            
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
        return True

    # Specialty Add / Paginated Browser
    elif data.startswith("track:add:"):
        parts = data.split(":")
        profile_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0

        profile = db.get_profile_by_id(profile_id)
        if not profile:
            await query.message.edit_text("Hata: Profil bulunamadı.", reply_markup=keyboards.get_main_keyboard(chat_id))
            return True

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
        return True

    # Toggle Specialty on/off
    elif data.startswith("track:toggle:"):
        parts = data.split(":")
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
        return True

    # Clear All Specialties for Profile
    elif data.startswith("track:clear:"):
        profile_id = int(data.split(":")[-1])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            db.clear_profile_specialties(profile_id)
            await query.answer("Tüm takip listesi temizlendi.")
        await query.message.edit_text(
            text=f"🏥 <b>{profile['name']}</b> için tüm takip listesi temizlendi.",
            parse_mode="HTML",
            reply_markup=keyboards.get_profile_tracking_keyboard(profile_id)
        )
        return True

    # Remove Single Specialty
    elif data.startswith("track:remove:"):
        parts = data.split(":")
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
        return True

    return False
