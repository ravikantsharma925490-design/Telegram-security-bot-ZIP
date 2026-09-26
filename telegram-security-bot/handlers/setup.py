"""
Setup handler — /start command. Bot ko admin banaya gaya hai ya nahi check karta hai,
owner identify karta hai, aur group ki configuration save karta hai.
Ek baar setup hone ke baad bot automatically active rehta hai, dobara /start
karne ki zaroorat nahi.
"""
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import html
 
import database as db
from utils.lang import t, bold_name, time_greeting
from config import WELCOME_IMAGE
 
 
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
 
    if chat.type == "private":
        lang = db.get_user_language(user.id)
        styled_name = html.escape(bold_name(user.first_name or "Friend"))
        caption = (
            "🚩 <u><b>JAI SHRI RAM</b></u> 🚩\n\n"
            f"HEY {styled_name}, {time_greeting()}\n\n"
            f"{html.escape(t(lang, 'private_welcome'))}"
        )
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
        )
        try:
            await update.message.reply_photo(
                photo=WELCOME_IMAGE,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception:
            # Agar WELCOME_IMAGE abhi tak placeholder/invalid hai, to sirf
            # text hi bhej do taaki bot crash na ho.
            await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
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
        t(lang, "setup_done", owner=user.mention_markdown()),
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
 
