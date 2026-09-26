"""
Logger — har important event (join, leave, warning, mute, block, delete, etc.)
ko group ke configured log channel mein bhejta hai (agar admin_alerts ON hai).
"""
 
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
 
import database as db
 
 
async def send_log(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    group = db.get_group(chat_id)
    if not group["admin_alerts"]:
        return
    log_chat = group["log_chat_id"]
    if not log_chat:
        return
    try:
        await context.bot.send_message(chat_id=log_chat, text=f"📝 {text}", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        # Log channel set nahi hai ya bot wahan admin nahi hai — chup-chaap ignore
        pass
 
