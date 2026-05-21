import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("HATA: .env dosyasında TELEGRAM_TOKEN tanımlı değil!")
    sys.exit(1)

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if ADMIN_CHAT_ID:
    ADMIN_CHAT_ID = str(ADMIN_CHAT_ID).strip()

# Setup logging
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

# Formatter
log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Log file path
log_file = os.getenv("LOG_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "adu_bot.log"))

# File Handler (5MB max size, keeping 3 backups, UTF-8 encoded)
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
file_handler.setFormatter(log_formatter)
file_handler.setLevel(LOG_LEVEL)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(LOG_LEVEL)

# Root Logger configuration
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger("adu_bot")
logger.info(f"Logging initialized. Level: {LOG_LEVEL_STR}. File: {log_file}")

# Standard hospital departments list (fallback/static list for user to track)
POPULAR_DEPARTMENTS = {
    101: "Deri ve Zührevi Hastalıkları (Cildiye)",
    102: "Göz Hastalıkları",
    103: "Kulak Burun Boğaz Hastalıkları (KBB)",
    104: "İç Hastalıkları (Dahiliye)",
    105: "Ortopedi ve Travmatoloji",
    106: "Kardiyoloji",
    107: "Nöroloji",
    108: "Fiziksel Tıp ve Rehabilitasyon",
    109: "Genel Cerrahi",
    110: "Üroloji",
    111: "Kadın Hastalıkları ve Doğum",
    112: "Çocuk Sağlığı ve Hastalıkları",
    113: "Göğüs Hastalıkları",
    114: "Ruh Sağlığı ve Hastalıkları (Psikiyatri)",
    115: "Enfeksiyon Hastalıkları",
    116: "Nefroloji",
    117: "Gastroenteroloji",
    118: "Endokrinoloji ve Metabolizma"
}
