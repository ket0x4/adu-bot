import time
import asyncio
import secrets
import html
from telegram.ext import ContextTypes
import db
import config
from scraper import ADUScraper
from handlers.common import (
    find_matching_specialty,
    is_in_dnd,
    filter_slots_for_profile,
    build_slot_alert_view
)
from handlers.notifications import send_calendar_invite, build_google_calendar_markup

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
    all_needed_specs = set()  # (spec_id, spec_name, rtype)
    
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
                                kb = build_google_calendar_markup(
                                    specialty_name=active_name,
                                    polyclinic_name=poly['name'],
                                    patient_name=profile['name'],
                                    date_str=target_slot['date'],
                                    time_str=target_slot['time'],
                                    rtype_label=rtype_label
                                )
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
                                await send_calendar_invite(
                                    context=context,
                                    chat_id=chat_id,
                                    patient_name=profile['name'],
                                    specialty_name=active_name,
                                    polyclinic_name=poly['name'],
                                    date_str=target_slot['date'],
                                    time_str=target_slot['time'],
                                    rtype_label=rtype_label,
                                    silent_mode=silent_mode
                                )
                                continue

                        # --- MANUAL NOTIFICATION MODE ---
                        alert_key = f"{profile['id']}_{poly_id}_{rtype}"
                        # Fixed bug: using context.bot_data instead of context.bot.data
                        last_sent = context.bot_data['sent_alerts'].get(alert_key, 0)
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
