from telegram import Update
from telegram.ext import ContextTypes
import db
import config
import keyboards

async def handle_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data

    if data == "menu:main":
        await query.message.edit_text(
            text="🏥 <i>Lütfen aşağıdaki menüden işlem seçin:</i>",
            parse_mode="HTML",
            reply_markup=keyboards.get_main_keyboard(chat_id)
        )
        return True

    elif data == "menu:profiles":
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
        return True

    elif data == "menu:tracking":
        profiles = db.get_profiles(chat_id)
        if not profiles:
            await query.message.edit_text(
                text="⚠️ <b>Profil Bulunamadı!</b>\n\nRandevu takibi yapabilmek için öncelikle en az bir profil oluşturmalısınız.",
                parse_mode="HTML",
                reply_markup=keyboards.get_main_keyboard(chat_id)
            )
            return True
            
        await query.message.edit_text(
            text="🏥 <b>Bölüm Takip Listesi</b>\n\nHangi hasta için randevu bölümlerini yönetmek istiyorsunuz?",
            parse_mode="HTML",
            reply_markup=keyboards.get_tracking_keyboard(chat_id)
        )
        return True

    elif data == "menu:settings":
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
        return True

    elif data.startswith("settings:interval:"):
        interval = int(data.split(":")[-1])
        db.set_scan_interval(chat_id, interval)
        await query.message.edit_text(
            text=f"⚙️ Sorgulama sıklığı <b>{interval} dakika</b> olarak ayarlandı.",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )
        return True

    elif data.startswith("settings:rtype:"):
        rtype = int(data.split(":")[-1])
        db.set_randevu_type(chat_id, rtype)
        rtype_desc = config.RANDEVU_TYPES.get(rtype, "Tümü")
        await query.answer(f"Randevu türü: {rtype_desc}")
        await query.message.edit_text(
            text=f"⚙️ <b>Ayarlar Güncellendi</b>\n\n"
                 f"Tercih edilen randevu türü: <b>{rtype_desc}</b> olarak ayarlandı.",
            parse_mode="HTML",
            reply_markup=keyboards.get_settings_keyboard(chat_id)
        )
        return True

    elif data == "settings:toggle_dnd":
        user = db.get_user(chat_id)
        cur_dnd = user.get('dnd_enabled', 0) if user else 0
        new_dnd = 0 if cur_dnd else 1
        db.set_user_dnd(chat_id, new_dnd)
        dnd_lbl = "AÇILDI 🌙" if new_dnd else "KAPATILDI 🔔"
        await query.answer(f"Gece Modu {dnd_lbl}")
        await query.message.edit_reply_markup(reply_markup=keyboards.get_settings_keyboard(chat_id))
        return True

    elif data == "menu:status":
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
        return True

    elif data == "menu:toggle_scan":
        user = db.get_user(chat_id)
        profiles = db.get_profiles(chat_id)
        if not user:
            return True
            
        current_state = user['is_scanning']
        new_state = not current_state
        
        if new_state:
            if not profiles:
                await query.message.edit_text(
                    text="⚠️ <b>Tarama Başlatılamadı!</b>\n\nTaramayı başlatabilmek için en az 1 adet profil oluşturmalısınız.",
                    parse_mode="HTML",
                    reply_markup=keyboards.get_main_keyboard(chat_id)
                )
                return True
                
            all_specs = db.get_profiles_specialties([p['id'] for p in profiles])
            if not all_specs:
                await query.message.edit_text(
                    text="⚠️ <b>Tarama Başlatılamadı!</b>\n\nTaramayı başlatabilmek için en az 1 tane takip edilecek bölüm eklemelisiniz.",
                    parse_mode="HTML",
                    reply_markup=keyboards.get_main_keyboard(chat_id)
                )
                return True
                
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
        return True

    return False
