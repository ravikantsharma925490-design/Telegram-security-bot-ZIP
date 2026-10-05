"""
Moderation handler — anti-spam, flood protection aur bad-word filter.
Har violation par warning system (handlers/admin.py ki _issue_warning) call hota hai.
"""
 
import os
import time
from collections import defaultdict
 
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t
from handlers.logger import send_log
from handlers.admin import _issue_warning
from config import FLOOD_MESSAGE_LIMIT, FLOOD_TIME_WINDOW, LINK_SPAM_RESTRICT_DAYS, RESTRICTED_IMAGE
 
_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "images")
 
 
async def _send_restricted_message(context, chat_id, text):
    """Restrict message photo ke saath bhejta hai. URL fail ho to local file, phir text."""
    if RESTRICTED_IMAGE:
        try:
            await context.bot.send_photo(chat_id, photo=RESTRICTED_IMAGE, caption=text)
            return
        except Exception:
            pass
        local = os.path.join(_IMAGES_DIR, os.path.basename(RESTRICTED_IMAGE.split("?")[0]))
        if os.path.exists(local):
            try:
                with open(local, "rb") as f:
                    await context.bot.send_photo(chat_id, photo=f, caption=text)
                return
            except Exception:
                pass
    await context.bot.send_message(chat_id, text)
 
 
# In-memory flood tracker: {(chat_id, user_id): [timestamps]}
_message_times = defaultdict(list)
 
# Bad-word list — file se load hoti hai (badwords.txt), taaki aap khud
# words add/remove kar sako bina code chhede. Agar file nahi milti to yahan
# di hui default list use hoti hai.
_DEFAULT_BAD_WORDS = {
    "madarchod", "madharchod", "mc", "behenchod", "bhenchod", "bc",
    "chutiya", "chutia", "chuthiya", "randi", "randy", "gandu", "gaandu",
    "harami", "haraami", "kutta", "kutte", "kamina", "kamine", "saala",
    "saali", "chodu", "lund", "loda", "lauda", "laude", "gaand", "gand",
    "jhant", "jhaant", "raand", "bhosdi", "bhosdike", "bhosda",
    "fuck", "fucking", "fucker", "fck", "f*ck", "bitch", "asshole",
    "bastard", "slut", "whore", "dick", "pussy", "motherfucker",
}
 
import os as _os
 
 
def _load_bad_words():
    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "badwords.txt")
    if _os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            words = {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}
        if words:
            return words
    return _DEFAULT_BAD_WORDS
 
 
BAD_WORDS = _load_bad_words()
 
 
def _contains_bad_word(text: str) -> bool:
    words = text.lower().split()
    return any(w.strip(".,!?") in BAD_WORDS for w in words)
 
 
def _is_flooding(chat_id: int, user_id: int) -> bool:
    now = time.time()
    key = (chat_id, user_id)
    _message_times[key] = [ts for ts in _message_times[key] if now - ts < FLOOD_TIME_WINDOW]
    _message_times[key].append(now)
    return len(_message_times[key]) > FLOOD_MESSAGE_LIMIT
 
 
async def moderation_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Return True agar message ko aage process hone dena hai (allowed),
    False agar already handle (delete) ho chuka hai.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not message.text or user.is_bot:
        return True
 
    # Koi bhi command (/rules, /ban@BotName, etc.) kabhi spam nahi maana
    # jaata — Telegram kabhi command ke saath "@BotName" bhi jod deta hai,
    # jisme "@" hota hai, aur neeche ka anti-spam check use username
    # samajh ke galti se restrict kar deta tha.
    if message.text.startswith("/"):
        return True
 
    group = db.get_group(chat.id)
    lang = db.get_effective_language(chat.id, user.id)  # jis user ko message ja raha hai, uski apni language
 
    # Owner/admins par moderation apply nahi karte
    from handlers.admin import is_authorized_admin
    if await is_authorized_admin(chat.id, user.id, context=context):
        return True
 
    # 1) Bad word filter
    if group["bad_word_filter"] and _contains_bad_word(message.text):
        try:
            await message.delete()
        except Exception:
            pass
        db.incr_stat("spam_deleted")
        await context.bot.send_message(chat.id, t(lang, "bad_word_deleted"))
        await send_log(context, chat.id, t(lang, "log_bad_word", name=user.full_name))
        await _issue_warning(update, context, user, "bad language")
        return False
 
    # 2) Flood protection
    if group["flood_protection"] and _is_flooding(chat.id, user.id):
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id,
                permissions=None,  # library default restricts sending; explicit below
            )
        except Exception:
            pass
        await context.bot.send_message(chat.id, t(lang, "flood_muted", name=user.full_name))
        await send_log(context, chat.id, t(lang, "log_flood", name=user.full_name))
        return False
 
    # 3) Basic anti-spam: links/usernames bhejne par message delete + 3-din restriction
    if group["anti_spam"]:
        link_count = message.text.count("http://") + message.text.count("https://") + message.text.count("t.me/") + message.text.count("@")
        if link_count >= 1:
            try:
                await message.delete()
            except Exception:
                pass
 
            restrict_seconds = LINK_SPAM_RESTRICT_DAYS * 24 * 60 * 60
            until = int(time.time()) + restrict_seconds
            try:
                await chat.restrict_member(
                    user.id,
                    ChatPermissions(can_send_messages=False),
                    until_date=until,
                )
            except Exception:
                pass
            db.block_user(chat.id, user.id, restrict_seconds)
            db.incr_stat("spam_deleted")
 
            await _send_restricted_message(
                context,
                chat.id,
                f"{t(lang, 'spam_deleted')}\n🚫 {user.full_name} has been restricted for {LINK_SPAM_RESTRICT_DAYS} days for sending a link/username.",
            )
            await send_log(context, chat.id, t(lang, "log_spam", name=user.full_name))
            return False
 
    return True
 
 
 
 
