"""
Admin handler — owner protection, admin permission management, block/unblock users,
aur unauthorized ban/kick/mute/command attempts se protection.
"""
 
import time
 
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t
from handlers.logger import send_log
from utils.media import send_photo_or_text
from config import BANNED_IMAGE
 
 
async def is_owner(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    group = db.get_group(chat_id)
    if group["owner_id"] == user_id:
        return True
 
    # FIX: DB mein owner_id set nahi (ya galat) hai to Telegram se asli
    # group creator verify karo, aur sahi hone par DB mein save kar lo.
    if context is not None:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status == "creator":
                db.update_group(chat_id, owner_id=user_id)
                return True
        except Exception:
            pass
    return False
 
 
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
    if await is_owner(chat_id, user_id, context):
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
 
 
async def _require_mention(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Group mein kai bots ho sakte hain jinke paas same-naam commands (/ban, /mute wagairah)
    hote hain. Bina @mention ke Telegram sab bots ko trigger kar deta hai, isliye
    admin commands ke liye bot ka @username mention karna zaroori hai.
    True = mention sahi hai (ya private chat hai). False = mention missing, already reply bhej diya.
    """
    chat = update.effective_chat
    if chat.type == "private":
        return True
    bot_username = (context.bot.username or "").lower()
    text = (update.message.text or "") if update.message else ""
    if bot_username and f"@{bot_username}" not in text.lower():
        await update.message.reply_text(
            f"ℹ️ Please mention me to use this command — e.g. `/ban@{context.bot.username}`.",
            parse_mode="Markdown",
        )
        return False
    return True
 
 
async def guard_or_warn(update: Update, context: ContextTypes.DEFAULT_TYPE, permission: str = None) -> bool:
    """True return karta hai agar user authorized hai. Warna warning bhej kar False return karta hai."""
    chat = update.effective_chat
    user = update.effective_user
 
    if not await _require_mention(update, context):
        return False
 
    if await is_authorized_admin(chat.id, user.id, permission, context=context):
        return True
 
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "unauthorized_command"))
    await send_log(context, chat.id, t(lang, "log_unauthorized_cmd", name=user.full_name))
    return False
 
 
async def owner_guard_or_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    guard_or_warn jaisa hi, lekin ADMINS ko bhi allow nahi karta — sirf group
    ka OWNER hi True paata hai. /setchannel, /setgroup jaise sensitive
    commands ke liye use hota hai.
    """
    chat = update.effective_chat
    user = update.effective_user
 
    if not await _require_mention(update, context):
        return False
 
    if await is_owner(chat.id, user.id, context):
        return True
 
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text("🚫 Only the group owner can use this command.")
    await send_log(context, chat.id, t(lang, "log_unauthorized_cmd", name=user.full_name))
    return False
 
 
# ---------- Commands ----------
 
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await owner_guard_or_warn(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a user's message to use this command.")
        return
 
    target = update.message.reply_to_message.from_user
    db.add_group_admin(chat.id, target.id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "admin_added", name=target.full_name))
    await send_log(context, chat.id, t(lang, "log_admin_action", name=target.full_name, action="added as admin"))
 
 
async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await owner_guard_or_warn(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a user's message to use this command.")
        return
 
    target = update.message.reply_to_message.from_user
    db.remove_group_admin(chat.id, target.id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "admin_removed", name=target.full_name))
    await send_log(context, chat.id, t(lang, "log_admin_action", name=target.full_name, action="removed as admin"))
 
 
async def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE, usage: str):
    """
    Target user nikalta hai: kisi message par reply karke, ya seedha user ID likhkar.
    Return: (user_id, name, baaki_args). Target na mile to usage hint bhejta hai
    aur (None, None, []) return karta hai.
    """
    msg = update.message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, u.full_name, list(context.args)
    if context.args and context.args[0].lstrip("-").isdigit():
        uid = int(context.args[0])
        return uid, str(uid), list(context.args[1:])
    await msg.reply_text(usage)
    return None, None, []
 
 
async def _is_protected(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int) -> bool:
    """Bot khud, owner ya admins par ban/mute nahi chalta. True = roko."""
    chat = update.effective_chat
    if target_id == context.bot.id:
        await update.message.reply_text("⚠️ I can't do that to myself.")
        return True
    if target_id == update.effective_user.id:
        await update.message.reply_text("⚠️ You can't do that to yourself.")
        return True
    if await is_authorized_admin(chat.id, target_id, context=context):
        await update.message.reply_text("⚠️ I can't ban/mute the group owner or an admin.")
        return True
    return False
 
 
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_ban"):
        return
    target_id, target_name, _ = await _resolve_target(
        update, context, "↩️ Reply to a user's message with /ban, or use /ban <user_id>."
    )
    if target_id is None or await _is_protected(update, context, target_id):
        return
 
    try:
        await chat.ban_member(target_id)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ban failed: {e}\nMake sure I'm an admin with the 'Ban users' right.")
        return
 
    db.incr_stat("bans")
    lang = db.get_group(chat.id)["default_language"]
    await send_photo_or_text(
        context, chat.id, BANNED_IMAGE,
        t(lang, "user_blocked", name=target_name),
        reply_to=update.message.message_id,
    )
    await send_log(context, chat.id, t(lang, "log_block", name=target_name))
 
 
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_ban"):
        return
    target_id, target_name, _ = await _resolve_target(
        update, context, "↩️ Reply to the banned user's message with /unban, or use /unban <user_id>."
    )
    if target_id is None:
        return
 
    try:
        await chat.unban_member(target_id, only_if_banned=True)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Unban failed: {e}\nMake sure I'm an admin with the 'Ban users' right.")
        return
 
    db.unblock_user(chat.id, target_id)
    lang = db.get_group(chat.id)["default_language"]
    await update.message.reply_text(t(lang, "user_unblocked", name=target_name))
    await send_log(context, chat.id, t(lang, "log_admin_action", name=target_name, action="unbanned"))
 
 
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mute [minutes] — reply karke ya /mute <user_id> [minutes]. Minutes na do to group ki default mute duration."""
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_mute"):
        return
    target_id, target_name, rest = await _resolve_target(
        update, context, "↩️ Reply to a user's message with /mute [minutes], or use /mute <user_id> [minutes]."
    )
    if target_id is None or await _is_protected(update, context, target_id):
        return
 
    group = db.get_group(chat.id)
    seconds = group["mute_duration"]
    if rest and rest[0].isdigit() and int(rest[0]) > 0:
        seconds = int(rest[0]) * 60
    until = int(time.time()) + seconds
 
    try:
        await chat.restrict_member(target_id, ChatPermissions(can_send_messages=False), until_date=until)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Mute failed: {e}\nMake sure I'm an admin with the 'Restrict members' right.")
        return
 
    minutes = max(1, seconds // 60)
    await update.message.reply_text(f"🔇 {target_name} has been muted for {minutes} minute(s). Use /unmute to undo.")
    lang = group["default_language"]
    await send_log(context, chat.id, t(lang, "log_mute", name=target_name))
 
 
async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_mute"):
        return
    target_id, target_name, _ = await _resolve_target(
        update, context, "↩️ Reply to a muted user's message with /unmute, or use /unmute <user_id>."
    )
    if target_id is None:
        return
 
    try:
        group_chat = await context.bot.get_chat(chat.id)
        await chat.restrict_member(target_id, group_chat.permissions)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Unmute failed: {e}\nMake sure I'm an admin with the 'Restrict members' right.")
        return
 
    db.unblock_user(chat.id, target_id)
    await update.message.reply_text(f"🔊 {target_name} has been unmuted.")
 
 
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_warn"):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a user's message with /warn [reason].")
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
    db.incr_stat("warnings")
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
 
 
 
 
 
