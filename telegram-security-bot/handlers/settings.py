"""
Settings handler — /settings command. Sirf owner/authorized admin use kar sakta hai.
Inline buttons se features ON/OFF kar sakte hain.
"""
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
 
import database as db
from utils.lang import t
from handlers.admin import guard_or_warn
from utils.lang import LANGUAGE_NAMES
 
TOGGLE_FIELDS = [
    ("anti_spam", "🛡️ Anti-Spam"),
    ("flood_protection", "🌊 Flood Protection"),
    ("bad_word_filter", "🤬 Bad-Word Filter"),
    ("media_protection", "🔞 18+ Media Protection"),
    ("suspicious_activity", "🔍 Suspicious Activity"),
    ("force_join", "📢 Force Join"),
    ("unauthorized_cmd_protection", "⚠️ Unauthorized Cmd Protection"),
    ("admin_alerts", "🚨 Admin Alerts"),
    ("auto_accept_requests", "🤖 Auto Accept Requests"),
]
 
 
def _settings_keyboard(group):
    buttons = []
    for field, label in TOGGLE_FIELDS:
        state = "✅" if group[field] else "❌"
        buttons.append([InlineKeyboardButton(f"{state} {label}", callback_data=f"toggle_{field}")])
    return InlineKeyboardMarkup(buttons)
 
 
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_settings"):
        return
    group = db.get_group(chat.id)
    lang = group["default_language"]
    await update.message.reply_text(
        t(lang, "settings_title"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_settings_keyboard(group),
    )
 
 
async def settings_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user
 
    from handlers.admin import is_authorized_admin
    if not await is_authorized_admin(chat.id, user.id, "can_settings"):
        await query.answer("🚫 Not authorized.", show_alert=True)
        return
 
    field = query.data.replace("toggle_", "")
    db.toggle_group_setting(chat.id, field)
    group = db.get_group(chat.id)
    await query.edit_message_reply_markup(reply_markup=_settings_keyboard(group))
    await query.answer("✅ Updated")
 
 
async def setlanguage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setlanguage <code> — group ki DEFAULT language set karta hai (sirf owner/admin).
    Ye us language mein hoti hai jisme bot group ke andar warnings, settings,
    force-join messages wagairah bolega. Example: /setlanguage hi
    """
    chat = update.effective_chat
    if not await guard_or_warn(update, context, "can_settings"):
        return
 
    if not context.args:
        available = ", ".join(f"`{code}`" for code in LANGUAGE_NAMES)
        await update.message.reply_text(
            f"🌐 Use: `/setlanguage <code>`\nAvailable codes: {available}",
            parse_mode="Markdown",
        )
        return
 
    code = context.args[0].lower()
    if code not in LANGUAGE_NAMES:
        await update.message.reply_text("❌ Invalid language code. Use /setlanguage to see the list.")
        return
 
    db.update_group(chat.id, default_language=code)
    await update.message.reply_text(f"✅ Group's default language set to {LANGUAGE_NAMES[code]}.")
 
