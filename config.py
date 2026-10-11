import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
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

# Official hospital departments list (all 52 specialties parsed directly from ADU portal)
ADU_DEPARTMENTS = {
    208: "Aile Hekimliği",
    289: "Algoloji (Ağrı) - Anesteziyoloji",
    365: "Algoloji (Ağrı) - Nöroloji",
    303: "Anestezi ve Reanimasyon",
    282: "Beyin ve Sinir Cerrahisi (Nöroşirürji)",
    278: "Çocuk Cerrahisi",
    272: "Çocuk Endokrinoloji",
    271: "Çocuk Enfeksiyon Hastalıkları",
    270: "Çocuk Gastroenteroloji",
    217: "Çocuk Hematolojisi ve Onkolojisi",
    273: "Çocuk Alerji ve İmmünoloji",
    281: "Çocuk Kalp ve Damar Cerrahisi",
    268: "Çocuk Kardiyoloji",
    267: "Çocuk Metabolizma",
    266: "Çocuk Nefroloji",
    265: "Çocuk Nörolojisi",
    296: "Çocuk Romatoloji",
    264: "Çocuk Yenidoğan (Neonatoloji)",
    216: "Çocuk Sağlığı ve Hastalıkları (Pediatri)",
    390: "Çocuk Ürolojisi",
    274: "Çocuk ve Ergen Ruh Sağlığı (Psikiyatri)",
    275: "Deri ve Zührevi Hastalıkları (Cildiye)",
    259: "Endokrinoloji ve Metabolizma Hastalıkları",
    262: "Enfeksiyon Hastalıkları ve Klinik Mikrobiyoloji",
    -229: "Erişkin Aşılama",
    276: "Fiziksel Tıp ve Rehabilitasyon (FTR)",
    258: "Gastroenteroloji",
    210: "Genel Cerrahi",
    279: "Göğüs Cerrahisi",
    261: "Göğüs Hastalıkları",
    288: "Göz Hastalıkları",
    223: "Hematoloji",
    215: "İç Hastalıkları (Dahiliye)",
    222: "İmmünoloji ve Alerji Hastalıkları",
    304: "İş ve Meslek Hastalıkları / Çalışan Sağlığı",
    207: "Kadın Hastalıkları ve Doğum",
    280: "Kalp ve Damar Cerrahisi",
    260: "Kardiyoloji",
    287: "Kulak Burun Boğaz Hastalıkları (KBB)",
    221: "Nefroloji",
    218: "Nöroloji",
    283: "Ortopedi ve Travmatoloji",
    219: "Plastik, Rekonstrüktif ve Estetik Cerrahi",
    302: "Radyasyon Onkolojisi",
    294: "Radyoloji",
    356: "Romatoloji (FTR)",
    220: "Romatoloji (İç Hastalıkları)",
    263: "Ruh Sağlığı ve Hastalıkları (Psikiyatri)",
    325: "Tıbbi Genetik",
    306: "Tıbbi Onkoloji (Medikal Onkoloji)",
    285: "Üroloji",
    -147: "Yara Bakım Ünitesi",
}

# Alias for backwards compatibility
POPULAR_DEPARTMENTS = ADU_DEPARTMENTS
