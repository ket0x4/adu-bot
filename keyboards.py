from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import db
import config

def get_main_keyboard(chat_id):
    user = db.get_user(chat_id)
    is_scanning = user['is_scanning'] if user else False
    
    scan_btn_text = "Taramayı Durdur" if is_scanning else "Taramayı Başlat"
    
    keyboard = [
        [
            InlineKeyboardButton("Profillerim", callback_data="menu:profiles"),
            InlineKeyboardButton("Takip Ettiklerim", callback_data="menu:tracking")
        ],
        [
            InlineKeyboardButton("Ayarlar", callback_data="menu:settings"),
            InlineKeyboardButton("Durum / Bilgi", callback_data="menu:status")
        ],
        [
            InlineKeyboardButton(scan_btn_text, callback_data="menu:toggle_scan")
        ]
    ]
    
    # If this is the Master Admin, append the Authorization Panel button!
    if config.ADMIN_CHAT_ID and str(chat_id) == config.ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("Yetki Paneli (Admin)", callback_data="menu:admin")])
        
    return InlineKeyboardMarkup(keyboard)

def get_profiles_keyboard(chat_id):
    profiles = db.get_profiles(chat_id)
    keyboard = []
    for p in profiles:
        keyboard.append([InlineKeyboardButton(f"{p['name']}", callback_data=f"profile:view:{p['id']}")])
    
    keyboard.append([InlineKeyboardButton("Yeni Profil Ekle", callback_data="profile:add")])
    keyboard.append([InlineKeyboardButton("Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)

def get_profile_view_keyboard(profile_id):
    keyboard = [
        [InlineKeyboardButton("Profili Sil", callback_data=f"profile:delete:{profile_id}")],
        [InlineKeyboardButton("Profillerim", callback_data="menu:profiles")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tracking_keyboard(chat_id):
    profiles = db.get_profiles(chat_id)
    keyboard = []
    for p in profiles:
        keyboard.append([InlineKeyboardButton(f"{p['name']}", callback_data=f"track:profile:{p['id']}")])
    keyboard.append([InlineKeyboardButton("Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)

def get_profile_tracking_keyboard(profile_id):
    tracked = db.get_profile_specialties(profile_id)
    keyboard = []
    for t in tracked:
        keyboard.append([
            InlineKeyboardButton(f"Sil: {t['specialty_name']}", callback_data=f"track:remove:{profile_id}:{t['specialty_id']}")
        ])
    keyboard.append([InlineKeyboardButton("Bölüm Ekle", callback_data=f"track:add:{profile_id}")])
    keyboard.append([InlineKeyboardButton("Geri", callback_data="menu:tracking")])
    return InlineKeyboardMarkup(keyboard)

def get_track_add_keyboard(profile_id, page=0):
    departments = list(config.POPULAR_DEPARTMENTS.items())
    page_size = 10
    total_pages = (len(departments) + page_size - 1) // page_size
    
    # Clamp page between 0 and total_pages - 1
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
        
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_items = departments[start_idx:end_idx]
    
    keyboard = []
    row = []
    for spec_id, name in page_items:
        # Display short names in buttons to fit perfectly on screens
        short_name = name.split(" (")[0] if " (" in name else name
        short_name = short_name[:15] + "..." if len(short_name) > 17 else short_name
        row.append(InlineKeyboardButton(short_name, callback_data=f"track:do_add:{profile_id}:{spec_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("< Geri", callback_data=f"track:add:{profile_id}:{page-1}"))
    else:
        nav_row.append(InlineKeyboardButton("[Geri]", callback_data="noop"))
        
    nav_row.append(InlineKeyboardButton(f"Sayfa {page + 1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("İleri >", callback_data=f"track:add:{profile_id}:{page+1}"))
    else:
        nav_row.append(InlineKeyboardButton("[İleri]", callback_data="noop"))
        
    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("İptal", callback_data=f"track:profile:{profile_id}")])
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard(chat_id):
    user = db.get_user(chat_id)
    current_interval = user['scan_interval'] if user else 15
    
    keyboard = []
    intervals = [5, 10, 15, 30, 60]
    row = []
    for i in intervals:
        indicator = "[Seçili] " if i == current_interval else ""
        row.append(InlineKeyboardButton(f"{indicator}{i} dk", callback_data=f"settings:interval:{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("Ana Menü", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)
