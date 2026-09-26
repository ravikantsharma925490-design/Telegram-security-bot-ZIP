"""
Welcome handler — naye member ka welcome, language selection button,
aur join requests ko automatically accept karna (Force Join System se pehle).
"""
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t, LANGUAGE_NAMES
from handlers.logger import send_log
 
 
async def auto_accept_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naye 'join request' (approval-required groups/channels) ko turant accept karta hai."""
    request = update.chat_join_request
    chat = request.chat
    user = request.from_user
 
    group = db.get_group(chat.id)
    if not group["auto_accept_requests"]:
        return
 
    try:
        await context.bot.approve_chat_join_request(chat.id, user.id)
    except Exception:
        return
 
    lang = group["default_language"]
    await send_log(context, chat.id, t(lang, "log_auto_request_approved", name=user.full_name))
 
 
def _language_keyboard():
    buttons, row = [], []
    for code, label in LANGUAGE_NAMES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"setlang_{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)
 
 
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab naya member group mein aaye (join request flow ke bina bhi) — welcome + language button."""
    chat = update.effective_chat
    group = db.get_group(chat.id)
    lang = group["default_language"]
 
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        text = t(lang, "welcome", name=member.full_name)
        await update.message.reply_text(text)
        await send_log(context, chat.id, t(lang, "log_user_joined", name=member.full_name))
 
 
async def member_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    group = db.get_group(chat.id)
    lang = group["default_language"]
    left_member = update.message.left_chat_member
    if left_member and not left_member.is_bot:
        await send_log(context, chat.id, t(lang, "log_user_left", name=left_member.full_name))
 
 
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Koi bhi user kabhi bhi /language bhej kar apni pasand ki language choose kar sakta hai."""
    await update.message.reply_text(
        t(db.get_user_language(update.effective_user.id), "choose_language"),
        reply_markup=_language_keyboard(),
    )
 
 
async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    code = query.data.replace("setlang_", "")
    db.set_user_language(user.id, code)
    await query.answer(t(code, "language_set"))
 
    # Message ka text turant chuni gayi language ke confirmation se badal do,
    # taaki user ko visibly confirm ho ki language change ho gayi hai.
    try:
        await query.edit_message_text(t(code, "language_set"), reply_markup=_language_keyboard())
    except Exception:
        pass
