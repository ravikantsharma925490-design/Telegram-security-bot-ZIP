"""
Main entry point — bot yahan se start hota hai. Sab handlers yaha register hote hain.
 
Chalane ke liye:
    pip install -r requirements.txt
    export BOT_TOKEN="your-bot-token-here"     (ya config.py mein seedha likh do)
    python main.py
"""
 
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
 
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatJoinRequestHandler, ContextTypes, filters,
)
 
import database as db
from config import BOT_TOKEN
 
from handlers.setup import start_command, help_command
from handlers.settings import settings_command, settings_toggle_callback, setlanguage_command
from handlers.admin import add_admin_command, remove_admin_command, ban_command, unban_command, mute_command, warn_command
from handlers.welcome import auto_accept_join_request, welcome_new_member, member_left, language_callback, language_command
from handlers.force_join import force_join_check, verify_callback
from handlers.moderation import moderation_check
from handlers.media_filter import media_moderation_check
 
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
 
 
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har normal group message yaha se guzarta hai: force join -> moderation -> media check."""
    if not update.effective_message or update.effective_chat.type not in ("group", "supergroup"):
        return
 
    allowed = await force_join_check(update, context)
    if not allowed:
        return
 
    allowed = await moderation_check(update, context)
    if not allowed:
        return
 
    await media_moderation_check(update, context)
 
 
class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running.")
 
    def log_message(self, format, *args):
        pass  # HTTP request logs spam na kare
 
 
def _run_dummy_web_server():
    """
    Render (Web Service) ko ek open port chahiye hota hai, warna port-scan
    timeout warning deta rehta hai. Ye bas ek chhota HTTP server hai jo
    'Bot is running.' bolta hai — bot ke asli kaam (polling) se iska koi
    lena dena nahi, ye sirf background thread mein chalta hai.
    """
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    server.serve_forever()
 
 
def main():
    threading.Thread(target=_run_dummy_web_server, daemon=True).start()
 
    db.init_db()
 
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .build()
    )
 
    # Core commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("setlanguage", setlanguage_command))
 
    # Admin commands
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("removeadmin", remove_admin_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("warn", warn_command))
 
    # Join requests (auto accept)
    app.add_handler(ChatJoinRequestHandler(auto_accept_join_request))
 
    # New member / left member
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, member_left))
 
    # Normal group messages -> force join + moderation + media checks
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
        handle_group_message,
    ))
 
    # Callback buttons
    app.add_handler(CallbackQueryHandler(settings_toggle_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(language_callback, pattern="^setlang_"))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^force_join_verify$"))
 
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
 
 
if __name__ == "__main__":
    main()
 
