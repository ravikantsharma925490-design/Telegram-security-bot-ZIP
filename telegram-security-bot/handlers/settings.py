"""
Settings handler — /settings command. Sirf owner/authorized admin use kar sakta hai.
Inline buttons se features ON/OFF kar sakte hain.
"""
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
 
import database as db
from utils.lang import t
from handlers.admin import guard_or_warn, owner_guard_or_warn
from utils.lang import LANGUAGE_NAMES
from config import OWNER_ID
 
TOGGLE_FIELDS = [
    ("anti_spam", "🛡️ Anti-Spam"),
    ("flood_protection", "🌊 Flood Protection"),
    ("bad_word_filter", "🤬 Bad-Word Filter"),
    ("media_protection", "🔞 18+ Media Protection"),
    ("suspicious_activity", "🔍 Suspicious Activity"),
    ("force_join", "📢 Force Join"),
    ("unauthorized_cmd_protection", "⚠️ Unauthorized Cmd Protection"),
    ("admin_alerts", "🚨 Admin Alerts (log chat)"),
    ("auto_accept_requests", "🤖 Auto Accept Requests"),
    ("block_bot_add", "🔒 Block Bot Adding"),
    ("daily_tag", "🌅 Morning Tag"),
    ("daily_tag_afternoon", "☀️ Afternoon Tag"),
    ("daily_tag_evening", "🌆 Evening Tag"),
    ("daily_tag_night", "🌙 Night Tag"),
    ("daily_tag_midnight", "🌌 Midnight Tag"),
]
 
 
def _settings_keyboard(group):
    from handlers.daily_tag import SLOTS, format_12h
    # ON/OFF field -> slot (Daily Tag ke 5 buttons ke naam ke aage unka time dikhane ke liye)
    slot_by_field = {s["on"]: key for key, s in SLOTS.items()}
 
    buttons = []
    for field, label in TOGGLE_FIELDS:
        state = "✅" if group.get(field, db.DEFAULT_GROUP.get(field, 0)) else "❌"
        if field in slot_by_field:
            slot = SLOTS[slot_by_field[field]]
            label = f"{label} ({format_12h(group.get(slot['time']) or slot['default'])})"
        buttons.append([InlineKeyboardButton(f"{state} {label}", callback_data=f"toggle_{field}")])
    buttons.append([InlineKeyboardButton("🗑 Close", callback_data="close_settings")])
    return InlineKeyboardMarkup(buttons)
 
 
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context):
        return
    group = db.get_group(chat.id)
    lang = group["default_language"]
    await context.bot.send_message(
        chat.id,
        t(lang, "settings_title"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_settings_keyboard(group),
    )
    # Menu bhejne ke baad aapka /settings command message delete (bot ko 'Delete messages' permission chahiye)
    try:
        await update.message.delete()
    except Exception:
        pass
 
 
async def settings_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user
 
    from handlers.admin import is_authorized_admin
    if not await is_authorized_admin(chat.id, user.id, context=context):
        await query.answer("🚫 Only the group owner or admins can change settings.", show_alert=True)
        return
 
    field = query.data.replace("toggle_", "")
    db.toggle_group_setting(chat.id, field)
    group = db.get_group(chat.id)
    await query.edit_message_reply_markup(reply_markup=_settings_keyboard(group))
    await query.answer("✅ Updated")
 
 
async def settings_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🗑 Close button: sirf owner/admin settings menu delete kar sakta hai. Normal user ke liye kuch nahi hota."""
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user
 
    from handlers.admin import is_authorized_admin
    if not await is_authorized_admin(chat.id, user.id, context=context):
        await query.answer()
        return
 
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
 
 
def _group_language_keyboard(current):
    """Group ki language chunne ke buttons (2 per row). Abhi chuni hui language par ✅."""
    buttons, row = [], []
    for code, label in LANGUAGE_NAMES.items():
        text = f"✅ {label}" if code == current else label
        row.append(InlineKeyboardButton(text, callback_data=f"grplang_{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)
 
 
async def setlanguage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setlanguage ke buttons: sirf owner/admin group ki language badal sakta hai."""
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user
 
    from handlers.admin import is_authorized_admin
    if not await is_authorized_admin(chat.id, user.id, context=context):
        await query.answer("🚫 Only the group owner or admins can change the language.", show_alert=True)
        return
 
    code = query.data.replace("grplang_", "")
    if code not in LANGUAGE_NAMES:
        await query.answer()
        return
    db.update_group(chat.id, default_language=code)
    await query.answer(t(code, "language_set"))
    try:
        await query.edit_message_text(t(code, "language_set"), reply_markup=_group_language_keyboard(code))
    except Exception:
        pass
 
 
async def setlanguage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setlanguage <code> — group ki DEFAULT language set karta hai (sirf owner/admin).
    Ye us language mein hoti hai jisme bot group ke andar warnings, settings,
    force-join messages wagairah bolega. Example: /setlanguage hi
    """
    chat = update.effective_chat
    if not await guard_or_warn(update, context):
        return
 
    if not context.args:
        current = db.get_group(chat.id).get("default_language", "en")
        await update.message.reply_text(
            t(current, "choose_language"),
            reply_markup=_group_language_keyboard(current),
        )
        return
 
    code = context.args[0].lower()
    if code not in LANGUAGE_NAMES:
        await update.message.reply_text("❌ Invalid language code. Use /setlanguage to see the list.")
        return
 
    db.update_group(chat.id, default_language=code)
    await update.message.reply_text(f"✅ Group's default language set to {LANGUAGE_NAMES[code]}.")
 
 
async def setlogchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setlogchat — is group ka APNA log channel set karta hai. Is group ke saare logs sirf wahin jaate hain.
    Bot owner ka fixed channel (env LOG_CHANNEL_ID) alag hai aur isse kabhi nahi badalta.
 
      1) Log channel se koi message forward karo, us par reply karke /setlogchat
      2) /setlogchat -100123456789
      3) /setlogchat off      (apna log channel hata do)
 
    Chala sakta hai: group owner, authorized admin, ya bot owner (kisi bhi group mein).
    """
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("ℹ️ Use this command inside a group.")
        return
 
    is_bot_owner = bool(OWNER_ID) and user.id == OWNER_ID
    if not is_bot_owner and not await guard_or_warn(update, context):
        return
 
    args = [a.strip() for a in (context.args or [])]
    if args and args[0].lower() in ("off", "remove", "none", "0"):
        db.update_group(chat.id, log_chat_id=0)
        await update.message.reply_text("✅ Log chat removed. This group's logs will not be sent anywhere now.")
        return
 
    log_chat_id = None
    replied = update.message.reply_to_message
    if replied:
        origin = getattr(replied, "forward_origin", None)
        origin_chat = None
        if origin is not None:
            origin_chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if origin_chat is None and origin is None:
            origin_chat = getattr(replied, "forward_from_chat", None)  # purane PTB versions
        if origin_chat is not None:
            log_chat_id = origin_chat.id
    if log_chat_id is None and args:
        try:
            log_chat_id = int(args[0])
        except ValueError:
            log_chat_id = None
 
    if log_chat_id is None:
        current = db.get_group(chat.id).get("log_chat_id") or 0
        status = f"Current log chat: {current}" if current else "No log chat set for this group."
        await update.message.reply_text(
            f"ℹ️ {status}\n\n"
            "To set one:\n"
            "• Forward a message from your log channel here, reply to it with /setlogchat\n"
            "• or use /setlogchat <chat_id>\n"
            "• /setlogchat off — remove it\n\n"
            "The bot must be an admin in that log channel (Post Messages)."
        )
        return
 
    try:
        await context.bot.send_message(
            log_chat_id, f"✅ This chat will now receive security logs of: {chat.title or chat.id}"
        )
    except Exception:
        await update.message.reply_text(
            "⚠️ I couldn't send a message to that chat. Add me there as an admin "
            "(with permission to post messages) and try again."
        )
        return
 
    db.update_group(chat.id, log_chat_id=log_chat_id)
    await update.message.reply_text("✅ Log chat set. All logs of this group will now go there.")
 
async def setchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setchannel <@username> — Force Join ke liye required CHANNEL set karta hai.
    Example: /setchannel @cinemagyanupdates
    """
    chat = update.effective_chat
    if not await owner_guard_or_warn(update, context):
        return
 
    if not context.args:
        await update.message.reply_text("📺 Use: `/setchannel @channelusername`", parse_mode="Markdown")
        return
 
    username = context.args[0].lstrip("@")
    db.update_group(chat.id, required_channel=username, force_join=1)
    await update.message.reply_text(
        f"✅ Required channel set to @{username}.\n📢 Force Join is now ON.\n"
        f"⚠️ Make sure I'm an admin in @{username}, otherwise I can't verify members."
    )
 
 
async def setgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setgroup <@username> — Force Join ke liye required GROUP set karta hai.
    Example: /setgroup @english_chatting_USA18
    """
    chat = update.effective_chat
    if not await owner_guard_or_warn(update, context):
        return
 
    if not context.args:
        await update.message.reply_text("👥 Use: `/setgroup @groupusername`", parse_mode="Markdown")
        return
 
    username = context.args[0].lstrip("@")
    db.update_group(chat.id, required_group=username, force_join=1)
    await update.message.reply_text(
        f"✅ Required group set to @{username}.\n📢 Force Join is now ON.\n"
        f"⚠️ Make sure I'm an admin in @{username}, otherwise I can't verify members."
    )
 
 
 
 
 
