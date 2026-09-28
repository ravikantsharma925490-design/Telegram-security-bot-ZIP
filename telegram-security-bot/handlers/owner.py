"""
Owner-only commands — sirf OWNER_ID wala (bot ka malik) use kar sakta hai.
/stats  — kitne groups, users, spam delete, ban, warn
/groups — bot kin groups mein hai
"""
 
from telegram import Update
from telegram.ext import ContextTypes
 
import database as db
from config import OWNER_ID
 
 
def _is_bot_owner(user_id: int) -> bool:
    return bool(OWNER_ID) and user_id == OWNER_ID
 
 
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_bot_owner(update.effective_user.id):
        return  # baaki logon ko koi reply nahi
 
    s = db.get_stats()
    text = (
        "📊 Bot Stats\n\n"
        f"👥 Groups: {s['groups']} (setup done: {s['groups_setup']})\n"
        f"🙋 Users (language chosen): {s['users']}\n\n"
        f"🗑️ Spam/bad-word messages deleted: {s['spam_deleted']}\n"
        f"🔨 Bans (/ban): {s['bans']}\n"
        f"⚠️ Warnings issued: {s['warnings']}\n\n"
        "Note: deleted/ban/warn counts is version ke deploy hone ke baad se ginti shuru hui hain."
    )
    await update.message.reply_text(text)
 
 
async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_bot_owner(update.effective_user.id):
        return
 
    chat_ids = db.list_group_ids()
    if not chat_ids:
        await update.message.reply_text("Abhi koi group nahi mila.")
        return
 
    lines = []
    for i, chat_id in enumerate(chat_ids, start=1):
        try:
            chat = await context.bot.get_chat(chat_id)
            title = chat.title or "(no title)"
        except Exception:
            title = "(bot ab is group me nahi hai / access nahi)"
        lines.append(f"{i}. {title}\n   ID: {chat_id}")
 
    # Telegram message limit ~4096 chars — chunks me bhejo
    chunk, size = [], 0
    for line in lines:
        if size + len(line) > 3800:
            await update.message.reply_text("\n".join(chunk))
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        header = f"👥 Total groups: {len(chat_ids)}\n\n" if len(lines) == len(chunk) else ""
        await update.message.reply_text(header + "\n".join(chunk))
 
