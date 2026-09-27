"""
Force Join handler — user ko message bhejne se pehle required channel aur
required group dono join karna zaroori hai. Owner/authorized admins exempt hain.
"""
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t
from handlers.logger import send_log
 
 
async def _is_member(context: ContextTypes.DEFAULT_TYPE, channel_username: str, user_id: int) -> bool:
    if not channel_username:
        return True
    username = channel_username if channel_username.startswith("@") else f"@{channel_username}"
    try:
        member = await context.bot.get_chat_member(username, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        # Bot us channel/group mein admin nahi hai ya username galat hai
        return True  # fail-open, taaki bot ki galti se sab block na ho jaaye
 
 
async def force_join_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True = allowed, False = message delete karke join prompt bheja gaya."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
 
    if not message or user.is_bot:
        return True
 
    group = db.get_group(chat.id)
    if not group["force_join"]:
        return True
 
    from handlers.admin import is_authorized_admin
    if await is_authorized_admin(chat.id, user.id, context=context):
        return True
 
    channel = group["required_channel"]
    req_group = group["required_group"]
 
    in_channel = await _is_member(context, channel, user.id)
    in_group = await _is_member(context, req_group, user.id)
 
    if in_channel and in_group:
        return True
 
    lang = db.get_effective_language(chat.id, user.id)
    try:
        await message.delete()
    except Exception:
        pass
 
    buttons = []
    if channel:
        buttons.append([InlineKeyboardButton(t(lang, "join_channel"), url=f"https://t.me/{channel.lstrip('@')}")])
    if req_group:
        buttons.append([InlineKeyboardButton(t(lang, "join_group"), url=f"https://t.me/{req_group.lstrip('@')}")])
    buttons.append([InlineKeyboardButton(t(lang, "verify"), callback_data="force_join_verify")])
 
    await context.bot.send_message(
        chat.id, t(lang, "force_join_prompt"),
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return False
 
 
async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user
    group = db.get_group(chat.id)
    lang = db.get_effective_language(chat.id, user.id)
 
    in_channel = await _is_member(context, group["required_channel"], user.id)
    in_group = await _is_member(context, group["required_group"], user.id)
 
    if in_channel and in_group:
        await query.answer(t(lang, "verify_success"))
        await query.message.delete()
        await send_log(context, chat.id, t(lang, "log_force_join_verified", name=user.full_name))
    else:
        await query.answer(t(lang, "verify_fail"), show_alert=True)
 
