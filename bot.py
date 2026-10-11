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

# --- Post Initialization Function (Reload Jobs) ---

async def post_init(application):
    config.logger.info("Initializing bot database scan jobs reload...")
    active_users = db.get_active_users()
    for user in active_users:
        try:
            chat_id = int(str(user['chat_id']).strip())
            interval = int(user['scan_interval'])
            
            application.job_queue.run_repeating(
                callback=handlers.scan_job,
                interval=interval * 60,
                first=10,
                chat_id=chat_id,
                name=str(chat_id)
            )
            config.logger.info(f"Job re-established for user {chat_id} with {interval} min interval.")
        except Exception as e:
            config.logger.error(f"Error restoring job for user {user.get('chat_id')}: {e}")
            
    config.logger.info(f"Database jobs reload complete. Total active jobs restored: {len(active_users)}")

# --- Main Run ---

def main():
    if not config.TELEGRAM_TOKEN:
        print("HATA: .env dosyasında TELEGRAM_TOKEN tanımlı değil!")
        print("Lütfen bir .env dosyası oluşturup TELEGRAM_TOKEN=<bot_token> ekleyin.")
        sys.exit(1)

    config.logger.info("Starting Telegram ADU Randevu Bot...")
    
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler(["help", "yardim"], handlers.help_command))
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    
    # Global error handler
    app.add_error_handler(handlers.error_handler)
    
    app.run_polling()

if __name__ == "__main__":
    main()
