import math
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import db
import config

def get_main_keyboard(chat_id):
    user = db.get_user(chat_id)
    is_scanning = user['is_scanning'] if user else False
    
    scan_btn_text = "⏸️ Taramayı Durdur" if is_scanning else "▶️ Taramayı Başlat"
    
    keyboard = [
        [
            InlineKeyboardButton("👤 Profillerim", callback_data="menu:profiles"),
            InlineKeyboardButton("🏥 Takip Ettiklerim", callback_data="menu:tracking")
        ],
        [
            InlineKeyboardButton("⚙️ Ayarlar", callback_data="menu:settings"),
            InlineKeyboardButton("🔄 Durum / Bilgi", callback_data="menu:status")
        ],
        [
            InlineKeyboardButton(scan_btn_text, callback_data="menu:toggle_scan")
        ]
    ]
    
    if config.ADMIN_CHAT_ID and str(chat_id) == config.ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("🔑 Yetki Paneli & Metrikler (Admin)", callback_data="menu:admin")])
        
    return InlineKeyboardMarkup(keyboard)

def get_profiles_keyboard(chat_id):
    profiles = db.get_profiles(chat_id)
    keyboard = []
    for p in profiles:
        keyboard.append([InlineKeyboardButton(f"👤 {p['name']}", callback_data=f"profile:view:{p['id']}")])
    
    keyboard.append([InlineKeyboardButton("➕ Yeni Profil Ekle", callback_data="profile:add")])
    keyboard.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)

def get_profile_view_keyboard(profile_id):
    keyboard = [
        [InlineKeyboardButton("🏥 Takip Listesini Yönet", callback_data=f"track:profile:{profile_id}")],
        [InlineKeyboardButton("⚡️ Filtreler & Sniper Modu", callback_data=f"pref:view:{profile_id}")],
        [InlineKeyboardButton("✏️ Profili Düzenle", callback_data=f"profile:edit:{profile_id}")],
        [InlineKeyboardButton("❌ Profili Sil", callback_data=f"profile:delete:{profile_id}")],
        [InlineKeyboardButton("🔙 Profillerim", callback_data="menu:profiles")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_profile_prefs_keyboard(profile_id):
    profile = db.get_profile_by_id(profile_id)
    if not profile:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="menu:profiles")]])

    auto_book = profile.get('auto_book', 0)
    cur_days = profile.get('filter_date_days', 0)
    cur_time = profile.get('filter_time_pref', 0)

    # 1. Sniper Mode Toggle Button
    auto_label = "⚡️ Sniper (Otomatik Al): ✅ AÇIK" if auto_book else "⚡️ Sniper (Otomatik Al): 🔘 KAPALI"
    keyboard = [
        [InlineKeyboardButton(auto_label, callback_data=f"pref:toggle_auto:{profile_id}")],
        [InlineKeyboardButton("─── 📅 Tarih Aralığı Filtresi ───", callback_data="noop")]
    ]

    # 2. Date Filter buttons (0: All, 7, 15, 30 days)
    date_options = [(0, "Tümü"), (7, "7 Gün"), (15, "15 Gün"), (30, "30 Gün")]
    date_row = []
    for days_val, lbl in date_options:
        prefix = "✅ " if days_val == cur_days else ""
        date_row.append(InlineKeyboardButton(f"{prefix}{lbl}", callback_data=f"pref:date:{profile_id}:{days_val}"))
    keyboard.append(date_row)

    # 3. Time Preference buttons (0: All day, 1: Morning, 2: Afternoon)
    keyboard.append([InlineKeyboardButton("─── ⏰ Saat Tercihi ───", callback_data="noop")])
    time_options = [
        (0, "🌟 Tüm Gün"),
        (1, "🌅 Sabah (08-12)"),
        (2, "🌇 Öğle (13-17)")
    ]
    time_row = []
    for t_val, lbl in time_options:
        prefix = "✅ " if t_val == cur_time else ""
        time_row.append(InlineKeyboardButton(f"{prefix}{lbl}", callback_data=f"pref:time:{profile_id}:{t_val}"))
        if len(time_row) == 2:
            keyboard.append(time_row)
            time_row = []
    if time_row:
        keyboard.append(time_row)

    keyboard.append([InlineKeyboardButton("🔙 Profile Dön", callback_data=f"profile:view:{profile_id}")])
    return InlineKeyboardMarkup(keyboard)

def get_profile_edit_keyboard(profile_id):
    keyboard = [
        [InlineKeyboardButton("✏️ İsmi / Etiketi Değiştir", callback_data=f"profile:edit_name:{profile_id}")],
        [InlineKeyboardButton("📞 Telefon Numarasını Değiştir", callback_data=f"profile:edit_phone:{profile_id}")],
        [InlineKeyboardButton("🔙 Profile Dön", callback_data=f"profile:view:{profile_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tracking_keyboard(chat_id):
    profiles = db.get_profiles(chat_id)
    keyboard = []
    for p in profiles:
        keyboard.append([InlineKeyboardButton(f"👤 {p['name']}", callback_data=f"track:profile:{p['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)

def get_profile_tracking_keyboard(profile_id):
    tracked = db.get_profile_specialties(profile_id)
    keyboard = []
    
    for t in tracked:
        keyboard.append([
            InlineKeyboardButton(f"❌ {t['specialty_name']}", callback_data=f"track:remove:{profile_id}:{t['specialty_id']}")
        ])
    
    actions = [InlineKeyboardButton("➕ Bölüm Ekle / Listele", callback_data=f"track:add:{profile_id}:0")]
    if len(tracked) > 1:
        actions.append(InlineKeyboardButton("🗑️ Tümünü Temizle", callback_data=f"track:clear:{profile_id}"))
    keyboard.append(actions)
    
    keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="menu:tracking")])
    return InlineKeyboardMarkup(keyboard)

def get_track_add_keyboard(profile_id, page=0, page_size=8):
    """Paginated keyboard showing ALL 52 departments with toggle indicators"""
    turkish_sort_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    sorted_deps = sorted(
        config.ADU_DEPARTMENTS.items(),
        key=lambda item: item[1].translate(turkish_sort_map).lower()
    )
    
    total_items = len(sorted_deps)
    total_pages = max(1, math.ceil(total_items / page_size))
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = sorted_deps[start_idx:end_idx]
    
    tracked_list = db.get_profile_specialties(profile_id)
    tracked_ids = {t['specialty_id'] for t in tracked_list}
    
    keyboard = []
    row = []
    for spec_id, name in page_items:
        is_tracked = spec_id in tracked_ids
        prefix = "✅ " if is_tracked else "➕ "
        
        short_name = name.split(" (")[0] if " (" in name else name
        short_name = short_name[:14] + ".." if len(short_name) > 16 else short_name
        
        btn_text = f"{prefix}{short_name}"
        cb_data = f"track:toggle:{profile_id}:{spec_id}:{page}"
        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    nav_row = []
    if total_pages > 1:
        prev_page = page - 1 if page > 0 else total_pages - 1
        next_page = page + 1 if page < total_pages - 1 else 0
        nav_row.append(InlineKeyboardButton("◀️ Önceki", callback_data=f"track:add:{profile_id}:{prev_page}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
        nav_row.append(InlineKeyboardButton("Sonraki ▶️", callback_data=f"track:add:{profile_id}:{next_page}"))
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton("🔙 Bitti / Geri Dön", callback_data=f"track:profile:{profile_id}")])
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard(chat_id):
    user = db.get_user(chat_id)
    current_interval = user['scan_interval'] if user else 15
    current_rtype = user.get('randevu_type', 0) if user else 0
    dnd_enabled = user.get('dnd_enabled', 0) if user else 0
    
    keyboard = []
    
    # 1. Interval options row
    intervals = [5, 10, 15, 30, 60]
    row = []
    for i in intervals:
        indicator = "✅ " if i == current_interval else ""
        row.append(InlineKeyboardButton(f"{indicator}{i} dk", callback_data=f"settings:interval:{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # 2. Randevu Type section
    keyboard.append([InlineKeyboardButton("─── Randevu Türü Tercihi ───", callback_data="noop")])
    
    types = [
        (0, "🌟 Tümü (Normal + Özel Öğretim)"),
        (1, "🩺 Sadece Normal Randevu"),
        (2, "👨‍🏫 Sadece Özel Öğretim Üyesi")
    ]
    for r_val, label in types:
        prefix = "✅ " if r_val == current_rtype else "🔘 "
        keyboard.append([
            InlineKeyboardButton(f"{prefix}{label}", callback_data=f"settings:rtype:{r_val}")
        ])

    # 3. DND Silent hours section
    keyboard.append([InlineKeyboardButton("─── 🌙 Bildirim Tercihi ───", callback_data="noop")])
    dnd_indicator = "✅ AÇIK" if dnd_enabled else "🔘 KAPALI"
    keyboard.append([
        InlineKeyboardButton(f"🌙 Gece Modu (23:00-08:00 Sessiz): {dnd_indicator}", callback_data="settings:toggle_dnd")
    ])
        
    keyboard.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ Davet Kodu Üret", callback_data="admin:gen_token"),
            InlineKeyboardButton("📜 Aktif Kodları Gör", callback_data="admin:list_tokens")
        ],
        [
            InlineKeyboardButton("👥 Kullanıcıları Listele", callback_data="admin:list_users"),
            InlineKeyboardButton("📊 Sistem Metrikleri", callback_data="admin:metrics")
        ],
        [
            InlineKeyboardButton("🔙 Ana Menü", callback_data="menu:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
