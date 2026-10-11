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
    
    # If this is the Master Admin, append the Authorization Panel button
    if config.ADMIN_CHAT_ID and str(chat_id) == config.ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("🔑 Yetki Paneli (Admin)", callback_data="menu:admin")])
        
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
        [InlineKeyboardButton("❌ Profili Sil", callback_data=f"profile:delete:{profile_id}")],
        [InlineKeyboardButton("🔙 Profillerim", callback_data="menu:profiles")]
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
    
    # List tracked specialties with remove button
    for t in tracked:
        keyboard.append([
            InlineKeyboardButton(f"❌ {t['specialty_name']}", callback_data=f"track:remove:{profile_id}:{t['specialty_id']}")
        ])
    
    # Action buttons
    actions = [InlineKeyboardButton("➕ Bölüm Ekle / Listele", callback_data=f"track:add:{profile_id}:0")]
    if len(tracked) > 1:
        actions.append(InlineKeyboardButton("🗑️ Tümünü Temizle", callback_data=f"track:clear:{profile_id}"))
    keyboard.append(actions)
    
    keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="menu:tracking")])
    return InlineKeyboardMarkup(keyboard)

def get_track_add_keyboard(profile_id, page=0, page_size=8):
    """Paginated keyboard showing ALL 52 departments with toggle indicators"""
    # Alphabetically sorted list of all departments
    turkish_sort_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    sorted_deps = sorted(
        config.ADU_DEPARTMENTS.items(),
        key=lambda item: item[1].translate(turkish_sort_map).lower()
    )
    
    total_items = len(sorted_deps)
    total_pages = max(1, math.ceil(total_items / page_size))
    
    # Clamp page index
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = sorted_deps[start_idx:end_idx]
    
    # Get currently tracked specialties for this profile
    tracked_list = db.get_profile_specialties(profile_id)
    tracked_ids = {t['specialty_id'] for t in tracked_list}
    
    keyboard = []
    row = []
    for spec_id, name in page_items:
        is_tracked = spec_id in tracked_ids
        prefix = "✅ " if is_tracked else "➕ "
        
        # Format name to fit nicely on Telegram buttons
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
        
    # Navigation row
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
        
    keyboard.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)
