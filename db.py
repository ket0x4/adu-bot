import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "adu_bot.db"))

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")  # Enable foreign keys for CASCADE DELETE
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users table (stores general Telegram user configuration and authorization status)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id TEXT PRIMARY KEY,
                scan_interval INTEGER DEFAULT 15,
                is_scanning INTEGER DEFAULT 0,
                is_authorized INTEGER DEFAULT 0
            )
        """)
        
        # Migration-safe: Try adding is_authorized column in case database was already created
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_authorized INTEGER DEFAULT 0;")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists, safe to ignore
            pass
        
        # 2. Profiles table (multiple patients under one user)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                name TEXT,
                tc_kimlik TEXT,
                dogum_tarihi TEXT,
                telefon TEXT,
                UNIQUE(chat_id, name),
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            )
        """)
        
        # 3. Profile specialties table (specialties tracked per profile)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile_specialties (
                profile_id INTEGER,
                specialty_id INTEGER,
                specialty_name TEXT,
                PRIMARY KEY (profile_id, specialty_id),
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            )
        """)
        
        # 4. Invitation Tokens table (dynamically generated access codes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invitation_tokens (
                token TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_used INTEGER DEFAULT 0,
                used_by_chat_id TEXT UNIQUE
            )
        """)
        
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

def set_scanning_state(chat_id, is_scanning):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_scanning = ? WHERE chat_id = ?
        """, (1 if is_scanning else 0, str(chat_id)))
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
        
        # 1. Delete user row completely. Foreign Key CASCADE will delete profiles and profile_specialties automatically!
        cursor.execute("DELETE FROM users WHERE chat_id = ?", (str(chat_id),))
        
        # 2. Delete any invitation token associated with this user
        cursor.execute("DELETE FROM invitation_tokens WHERE used_by_chat_id = ?", (str(chat_id),))
        
        conn.commit()

# --- Profile Functions ---

def add_profile(chat_id, name, tc_kimlik, dogum_tarihi, telefon):
    ensure_user_exists(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO profiles (chat_id, name, tc_kimlik, dogum_tarihi, telefon)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, name) DO UPDATE SET
                tc_kimlik = excluded.tc_kimlik,
                dogum_tarihi = excluded.dogum_tarihi,
                telefon = excluded.telefon
        """, (str(chat_id), name.strip(), tc_kimlik.strip(), dogum_tarihi.strip(), telefon.strip()))
        conn.commit()

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
        return [dict(row) for row in rows]

def get_profile_by_id(profile_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE id = ?", (int(profile_id),))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_profile_by_name(chat_id, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE chat_id = ? AND name = ?", (str(chat_id), name.strip()))
        row = cursor.fetchone()
        return dict(row) if row else None

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

# Initialize DB on import
init_db()
