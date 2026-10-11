import sys
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
import db
import config
import handlers

# --- Post Initialization Function (Central Scanner Setup) ---

async def post_init(application):
    config.logger.info("Initializing central hospital scan engine...")
    active_users = db.get_active_users()
    
    # Establish single centralized background scanner
    application.job_queue.run_repeating(
        callback=handlers.central_scan_job,
        interval=30,  # Checks every 30 seconds for due users
        first=5,
        name="central_hospital_scanner"
    )
    config.logger.info(f"Central scanner active. Initialized for {len(active_users)} active users.")

# --- Main Run ---

def main():
    if not config.TELEGRAM_TOKEN:
        print("HATA: .env dosyasında TELEGRAM_TOKEN tanımlı değil!")
        print("Lütfen bir .env dosyası oluşturup TELEGRAM_TOKEN=<bot_token> ekleyin.")
        sys.exit(1)

    config.logger.info("Starting Telegram ADU Randevu Bot...")
    
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Command Handlers
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler(["help", "yardim"], handlers.help_command))
    app.add_handler(CommandHandler("stats", handlers.stats_command))
    app.add_handler(CommandHandler("ping", handlers.ping_command))
    
    # Interaction Handlers
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    
    # Global error handler
    app.add_error_handler(handlers.error_handler)
    
    app.run_polling()

if __name__ == "__main__":
    main()
