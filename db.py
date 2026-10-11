import sqlite3
import os
import time
import crypto

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "adu_bot.db"))

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
    except sqlite3.OperationalError:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id TEXT PRIMARY KEY,
                scan_interval INTEGER DEFAULT 15,
                is_scanning INTEGER DEFAULT 0,
                is_authorized INTEGER DEFAULT 0,
                randevu_type INTEGER DEFAULT 0,
                dnd_enabled INTEGER DEFAULT 0,
                dnd_start INTEGER DEFAULT 23,
                dnd_end INTEGER DEFAULT 8,
                last_scan_time REAL DEFAULT 0
            )
        """)
        
        # Migrations for users table
        cols_users = [
            ("is_authorized", "INTEGER DEFAULT 0"),
            ("randevu_type", "INTEGER DEFAULT 0"),
            ("dnd_enabled", "INTEGER DEFAULT 0"),
            ("dnd_start", "INTEGER DEFAULT 23"),
            ("dnd_end", "INTEGER DEFAULT 8"),
            ("last_scan_time", "REAL DEFAULT 0")
        ]
        for col_name, col_def in cols_users:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        
        # 2. Profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                name TEXT,
                tc_kimlik TEXT,
                dogum_tarihi TEXT,
                telefon TEXT,
                auto_book INTEGER DEFAULT 0,
                filter_date_days INTEGER DEFAULT 0,
                filter_time_pref INTEGER DEFAULT 0,
                UNIQUE(chat_id, name),
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            )
        """)
        
        # Migrations for profiles table
        cols_profiles = [
            ("auto_book", "INTEGER DEFAULT 0"),
            ("filter_date_days", "INTEGER DEFAULT 0"),
            ("filter_time_pref", "INTEGER DEFAULT 0")
        ]
        for col_name, col_def in cols_profiles:
            try:
                cursor.execute(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_def};")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        
        # 3. Profile specialties table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile_specialties (
                profile_id INTEGER,
                specialty_id INTEGER,
                specialty_name TEXT,
                PRIMARY KEY (profile_id, specialty_id),
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            )
        """)
        
        # 4. Invitation Tokens table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invitation_tokens (
                token TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_used INTEGER DEFAULT 0,
                used_by_chat_id TEXT UNIQUE
            )
        """)

        # 5. Metrics table (key-value storage for bot operations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                val TEXT
            )
        """)
        
        conn.commit()

        # Migrate unencrypted profiles to encrypted tokens
        cursor.execute("SELECT id, tc_kimlik, dogum_tarihi, telefon FROM profiles")
        rows = cursor.fetchall()
        for r in rows:
            tc = r['tc_kimlik'] or ""
            dt = r['dogum_tarihi'] or ""
            tel = r['telefon'] or ""
            if tc and not tc.startswith("enc:v1:"):
                enc_tc = crypto.encrypt_text(tc)
                enc_dt = crypto.encrypt_text(dt)
                enc_tel = crypto.encrypt_text(tel)
                cursor.execute("""
                    UPDATE profiles 
                    SET tc_kimlik = ?, dogum_tarihi = ?, telefon = ?
                    WHERE id = ?
                """, (enc_tc, enc_dt, enc_tel, r['id']))
        conn.commit()

# --- User & Authorization Functions ---

def ensure_user_exists(chat_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO users (chat_id) VALUES (?)
        """, (str(chat_id),))
        conn.commit()

def get_user(chat_id):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE chat_id = ?", (str(chat_id),))
        row = cursor.fetchone()
        return dict(row) if row else None

def set_scan_interval(chat_id, interval):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET scan_interval = ? WHERE chat_id = ?
        """, (int(interval), str(chat_id)))
        conn.commit()

def set_randevu_type(chat_id, randevu_type):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET randevu_type = ? WHERE chat_id = ?
        """, (int(randevu_type), str(chat_id)))
        conn.commit()

def set_scanning_state(chat_id, is_scanning):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_scanning = ? WHERE chat_id = ?
        """, (1 if is_scanning else 0, str(chat_id)))
        conn.commit()

def set_user_dnd(chat_id, dnd_enabled, start_hour=23, end_hour=8):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET dnd_enabled = ?, dnd_start = ?, dnd_end = ? 
            WHERE chat_id = ?
        """, (1 if dnd_enabled else 0, int(start_hour), int(end_hour), str(chat_id)))
        conn.commit()

def update_user_last_scan(chat_id, timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_scan_time = ? WHERE chat_id = ?
        """, (float(timestamp), str(chat_id)))
        conn.commit()

def get_active_users():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE is_scanning = 1 AND is_authorized = 1")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def set_user_authorized(chat_id, is_authorized):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_authorized = ? WHERE chat_id = ?
        """, (1 if is_authorized else 0, str(chat_id)))
        conn.commit()

def get_authorized_users():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE is_authorized = 1")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def revoke_user(chat_id):
    """Revokes user authorization, deletes their row completely (triggering CASCADE DELETE on profiles/specialties)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE chat_id = ?", (str(chat_id),))
        cursor.execute("DELETE FROM invitation_tokens WHERE used_by_chat_id = ?", (str(chat_id),))
        conn.commit()

# --- Profile Functions ---

def _decrypt_profile_dict(row_dict):
    """Decrypts sensitive fields in a profile dictionary."""
    if not row_dict:
        return row_dict
    d = dict(row_dict)
    if 'tc_kimlik' in d and d['tc_kimlik']:
        d['tc_kimlik'] = crypto.decrypt_text(d['tc_kimlik'])
    if 'dogum_tarihi' in d and d['dogum_tarihi']:
        d['dogum_tarihi'] = crypto.decrypt_text(d['dogum_tarihi'])
    if 'telefon' in d and d['telefon']:
        d['telefon'] = crypto.decrypt_text(d['telefon'])
    return d

def add_profile(chat_id, name, tc_kimlik, dogum_tarihi, telefon):
    ensure_user_exists(chat_id)
    enc_tc = crypto.encrypt_text(tc_kimlik.strip())
    enc_dt = crypto.encrypt_text(dogum_tarihi.strip())
    enc_tel = crypto.encrypt_text(telefon.strip())
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO profiles (chat_id, name, tc_kimlik, dogum_tarihi, telefon)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, name) DO UPDATE SET
                tc_kimlik = excluded.tc_kimlik,
                dogum_tarihi = excluded.dogum_tarihi,
                telefon = excluded.telefon
        """, (str(chat_id), name.strip(), enc_tc, enc_dt, enc_tel))
        conn.commit()

def update_profile(profile_id, name=None, telefon=None, auto_book=None, filter_date_days=None, filter_time_pref=None):
    """Updates one or more fields of an existing profile."""
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(str(name).strip())
    if telefon is not None:
        updates.append("telefon = ?")
        params.append(crypto.encrypt_text(str(telefon).strip()))
    if auto_book is not None:
        updates.append("auto_book = ?")
        params.append(1 if auto_book else 0)
    if filter_date_days is not None:
        updates.append("filter_date_days = ?")
        params.append(int(filter_date_days))
    if filter_time_pref is not None:
        updates.append("filter_time_pref = ?")
        params.append(int(filter_time_pref))

    if not updates:
        return

    params.append(int(profile_id))
    query = f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def set_profile_auto_book(profile_id, auto_book):
    update_profile(profile_id, auto_book=(1 if auto_book else 0))

def set_profile_filter_date(profile_id, days):
    update_profile(profile_id, filter_date_days=int(days))

def set_profile_filter_time(profile_id, time_pref):
    update_profile(profile_id, filter_time_pref=int(time_pref))

def delete_profile(chat_id, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM profiles WHERE chat_id = ? AND name = ?
        """, (str(chat_id), name.strip()))
        conn.commit()

def get_profiles(chat_id):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE chat_id = ?", (str(chat_id),))
        rows = cursor.fetchall()
        return [_decrypt_profile_dict(dict(row)) for row in rows]

def get_profiles_counts():
    """Returns a dictionary mapping chat_id to the number of profiles they have."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, COUNT(*) as count FROM profiles GROUP BY chat_id")
        rows = cursor.fetchall()
        return {str(row['chat_id']): row['count'] for row in rows}

def get_profile_by_id(profile_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE id = ?", (int(profile_id),))
        row = cursor.fetchone()
        return _decrypt_profile_dict(dict(row)) if row else None

def get_profile_by_name(chat_id, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE chat_id = ? AND name = ?", (str(chat_id), name.strip()))
        row = cursor.fetchone()
        return _decrypt_profile_dict(dict(row)) if row else None

# --- Specialty Functions per Profile ---

def add_profile_specialty(profile_id, specialty_id, specialty_name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO profile_specialties (profile_id, specialty_id, specialty_name)
            VALUES (?, ?, ?)
        """, (int(profile_id), int(specialty_id), specialty_name.strip()))
        conn.commit()

def remove_profile_specialty(profile_id, specialty_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM profile_specialties WHERE profile_id = ? AND specialty_id = ?
        """, (int(profile_id), int(specialty_id)))
        conn.commit()

def get_profile_specialties(profile_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profile_specialties WHERE profile_id = ?", (int(profile_id),))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_profiles_specialties(profile_ids):
    if not profile_ids:
        return {}

    placeholders = ", ".join(["?"] * len(profile_ids))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM profile_specialties WHERE profile_id IN ({placeholders})", [int(pid) for pid in profile_ids])
        rows = cursor.fetchall()

        result = {}
        for row in rows:
            p_id = row['profile_id']
            if p_id not in result:
                result[p_id] = []
            result[p_id].append(dict(row))
        return result

def clear_profile_specialties(profile_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM profile_specialties WHERE profile_id = ?
        """, (int(profile_id),))
        conn.commit()

# --- Invitation Token Functions ---

def add_invitation_token(token):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO invitation_tokens (token) VALUES (?)
        """, (token.strip().upper(),))
        conn.commit()

def validate_invitation_token(token):
    """Returns True if the token exists and is not used"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM invitation_tokens WHERE token = ? AND is_used = 0
        """, (token.strip().upper(),))
        return cursor.fetchone() is not None

def use_invitation_token(token, chat_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE invitation_tokens 
            SET is_used = 1, used_by_chat_id = ? 
            WHERE token = ? AND is_used = 0
        """, (str(chat_id), token.strip().upper()))
        conn.commit()
        return cursor.rowcount > 0

def get_unused_tokens():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invitation_tokens WHERE is_used = 0 ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_invitation_token(token):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM invitation_tokens WHERE token = ?", (token.strip().upper(),))
        conn.commit()

# --- Metrics & System Stats Functions ---

def set_metric(key, value):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO metrics (key, val) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET val = excluded.val
        """, (str(key), str(value)))
        conn.commit()

def get_metric(key, default="0"):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT val FROM metrics WHERE key = ?", (str(key),))
        row = cursor.fetchone()
        return row['val'] if row else default

def increment_metric(key, amount=1):
    current = int(get_metric(key, "0"))
    set_metric(key, str(current + amount))

def get_system_stats():
    """Compiles complete diagnostic and usage metrics for the Admin Dashboard."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_users = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_scanning = 1 AND is_authorized = 1")
        active_scanners = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM profiles")
        total_profiles = cursor.fetchone()['count']

    db_size_kb = 0
    if os.path.exists(DB_PATH):
        db_size_kb = round(os.path.getsize(DB_PATH) / 1024, 1)

    return {
        "total_users": total_users,
        "active_scanners": active_scanners,
        "total_profiles": total_profiles,
        "total_scans": int(get_metric("total_scans", "0")),
        "slots_found": int(get_metric("slots_found", "0")),
        "bookings_count": int(get_metric("bookings_count", "0")),
        "last_scan_time": float(get_metric("last_scan_time", "0")),
        "last_latency_ms": int(get_metric("last_latency_ms", "0")),
        "hospital_status": get_metric("hospital_status", "Bilinmiyor"),
        "db_size_kb": db_size_kb,
        "encryption_active": True,
        "wal_mode_active": True
    }

# Initialize DB on import
init_db()
