"""
Admin handler — owner protection, admin permission management, block/unblock users,
aur unauthorized ban/kick/mute/command attempts se protection.
"""
 
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t
from handlers.logger import send_log
 
 
async def is_owner(chat_id: int, user_id: int) -> bool:
    group = db.get_group(chat_id)
    return group["owner_id"] == user_id
 
 
async def is_authorized_admin(chat_id: int, user_id: int, permission: str = None, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    """
    Owner ya bot ke through authorized admin check karta hai.
    Agar 'permission' None hai (yaani sirf general exemption chahiye, jaise
    moderation/force-join se bachna), to Telegram ke real admins/owner bhi
    automatically authorized maane jaate hain — chahe unhe /addadmin se add
    kiya ho ya sirf Telegram ke group settings se admin banaya ho.
    Specific permissions (can_ban, can_mute, can_warn, can_settings) ke liye
    sirf owner ya bot ke /addadmin se di gayi permission hi count hoti hai.
    """
    if await is_owner(chat_id, user_id):
        return True
 
    record = db.get_group_admin(chat_id, user_id)
    if record:
        if permission is None:
            return True
        if record.get(permission, 0):
            return True
 
    if context is not None:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ("administrator", "creator"):
                return True
        except Exception:
            pass
 
    return False
 
 
async def guard_or_warn(update: Update, context: ContextTypes.DEFAULT_TYPE, permission: str = None) -> bool:
    """True return karta hai agar user authorized hai. Warna warning bhej kar False return karta hai."""
    chat = update.effective_chat
    user = update.effective_user
    if await is_authorized_admin(chat.id, user.id, permission, context=context):
        return True
 
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "unauthorized_command"))
    await send_log(context, chat.id, t(lang, "log_unauthorized_cmd", name=user.full_name))
    return False
 
 
# ---------- Commands ----------
 
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_settings"):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Kisi user ke message par reply karke ye command bhejein.")
        return
 
    target = update.message.reply_to_message.from_user
    db.add_group_admin(chat.id, target.id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "admin_added", name=target.full_name))
    await send_log(context, chat.id, t(lang, "log_admin_action", name=target.full_name, action="added as admin"))
 
 
async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_settings"):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Kisi user ke message par reply karke ye command bhejein.")
        return
 
    target = update.message.reply_to_message.from_user
    db.remove_group_admin(chat.id, target.id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "admin_removed", name=target.full_name))
    await send_log(context, chat.id, t(lang, "log_admin_action", name=target.full_name, action="removed as admin"))
 
 
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_ban"):
        return
    if not update.message.reply_to_message:
        return
    target = update.message.reply_to_message.from_user
    await chat.ban_member(target.id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "user_blocked", name=target.full_name))
    await send_log(context, chat.id, t(lang, "log_block", name=target.full_name))
 
 
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_ban"):
        return
    if not update.message.reply_to_message:
        return
    target = update.message.reply_to_message.from_user
    await chat.unban_member(target.id)
    db.unblock_user(chat.id, target.id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "user_unblocked", name=target.full_name))
 
 
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_mute"):
        return
    if not update.message.reply_to_message:
        return
    target = update.message.reply_to_message.from_user
    await chat.restrict_member(target.id, ChatPermissions(can_send_messages=False))
    lang = db.get_group(chat.id)["default_language"]
    await send_log(context, chat.id, t(lang, "log_mute", name=target.full_name))
 
 
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_warn"):
        return
    if not update.message.reply_to_message:
        return
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "manual warning"
    await _issue_warning(update, context, target, reason)
 
 
async def _issue_warning(update: Update, context: ContextTypes.DEFAULT_TYPE, target, reason):
    """
    Central warning function — moderation.py bhi ise use karta hai.
    NOTE: update.message.reply_text() use nahi karte, kyunki bad-word/spam
    flow mein message pehle hi delete ho chuka hota hai — usko reply karne
    ki koshish Telegram error deti hai aur function beech mein ruk jata hai
    (isliye restriction wala part kabhi chalta nahi tha). Isliye seedha
    context.bot.send_message() use karte hain.
    """
    chat = update.effective_chat
    group = db.get_group(chat.id)
    lang = db.get_effective_language(chat.id, target.id)  # target user ki apni language
    count = db.add_warning(chat.id, target.id)
    limit = group["warning_limit"]
 
    await context.bot.send_message(
        chat.id, t(lang, "warning_issued", name=target.full_name, count=count, limit=limit, reason=reason)
    )
    await send_log(context, chat.id, t(lang, "log_warning", name=target.full_name, count=count, limit=limit, reason=reason))
 
    if count >= limit:
        try:
            await chat.restrict_member(target.id, ChatPermissions(can_send_messages=False))
        except Exception:
            pass
        db.block_user(chat.id, target.id, group["mute_duration"])
        db.reset_warnings(chat.id, target.id)
        await context.bot.send_message(chat.id, t(lang, "warning_limit_reached", name=target.full_name))
        await send_log(context, chat.id, t(lang, "log_mute", name=target.full_name))
 
