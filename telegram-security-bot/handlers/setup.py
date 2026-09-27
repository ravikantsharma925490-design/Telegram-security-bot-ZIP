"""
Setup handler — /start command. Bot ko admin banaya gaya hai ya nahi check karta hai,
owner identify karta hai, aur group ki configuration save karta hai.
Ek baar setup hone ke baad bot automatically active rehta hai, dobara /start
karne ki zaroorat nahi.
"""
 
import os
from datetime import datetime, timedelta
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
 
import database as db
from utils.lang import t
 
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # telegram-security-bot/
_REPO_ROOT = os.path.dirname(_PROJECT_DIR)  # repo ka root (telegram-security-bot ke ek level upar)
 
_WELCOME_IMAGE_CANDIDATES = [
    os.path.join(_PROJECT_DIR, "images", "welcome.jpg"),   # telegram-security-bot/images/welcome.jpg
    os.path.join(_REPO_ROOT, "images", "welcome.jpg"),      # images/welcome.jpg (repo root)
]
 
 
def _find_welcome_image():
    for path in _WELCOME_IMAGE_CANDIDATES:
        if os.path.exists(path):
            return path
    return None
 
 
def _current_greeting() -> str:
    """Abhi ke time (IST) ke hisaab se Good Morning/Afternoon/Evening/Night return karta hai."""
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    hour = ist_now.hour
    if 5 <= hour < 12:
        return "GOOD MORNING"
    elif 12 <= hour < 17:
        return "GOOD AFTERNOON"
    elif 17 <= hour < 21:
        return "GOOD EVENING"
    else:
        return "GOOD NIGHT"
 
 
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
 
    if chat.type == "private":
        lang = db.get_user_language(user.id)
        caption = t(lang, "private_welcome", name=user.full_name, greeting=_current_greeting())
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add me to a group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
        ])
        image_path = _find_welcome_image()
        if image_path:
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=buttons
                )
        else:
            await update.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN, reply_markup=buttons)
        return
 
    group = db.get_group(chat.id)
    lang = group["default_language"]
 
    if group["setup_done"]:
        await update.message.reply_text(t(lang, "already_setup"))
        return
 
    await update.message.reply_text(t(lang, "setup_start"))
 
    # Bot khud ki admin status check kare
    bot_member = await chat.get_member(context.bot.id)
    if bot_member.status != "administrator":
        await update.message.reply_text(t(lang, "setup_need_admin"))
        return
 
    # Jisne /start command chalayi (agar chat admin hai) use owner maan lo,
    # warna group creator ko owner set karna behtar hai.
    member = await chat.get_member(user.id)
    is_owner = member.status == "creator"
 
    db.update_group(chat.id, owner_id=user.id if is_owner else group["owner_id"], setup_done=1)
 
    await update.message.reply_text(
        t(lang, "setup_done", owner=user.mention_markdown_v2() if hasattr(user, "mention_markdown_v2") else user.full_name),
        parse_mode=ParseMode.MARKDOWN,
    )
 
 
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type == "private":
        lang = db.get_user_language(user.id)
    else:
        lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "help"), parse_mode=ParseMode.MARKDOWN)
 
 
async def get_file_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Utility command — kisi photo/video/document par reply karke /getfileid bhejo,
    bot uska Telegram file_id bata dega. Ye file_id repo mein image rakhne ke
    bajaye seedha config/language files mein use kiya ja sakta hai.
    """
    message = update.message
    if not message.reply_to_message:
        await message.reply_text("↩️ Reply to a photo/video/document with /getfileid.")
        return
 
    target = message.reply_to_message
    file_id = None
    if target.photo:
        file_id = target.photo[-1].file_id
    elif target.video:
        file_id = target.video.file_id
    elif target.document:
        file_id = target.document.file_id
    elif target.animation:
        file_id = target.animation.file_id
 
    if not file_id:
        await message.reply_text("❌ Is message mein koi photo/video/document nahi mila.")
        return
 
    await message.reply_text(f"📎 File ID:\n`{file_id}`", parse_mode=ParseMode.MARKDOWN)
 
