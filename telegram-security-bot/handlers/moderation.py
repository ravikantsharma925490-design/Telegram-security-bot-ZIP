"""
Moderation handler — anti-spam, flood protection aur bad-word filter.
Har violation par warning system (handlers/admin.py ki _issue_warning) call hota hai.
"""
 
import time
from collections import defaultdict
 
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t
from handlers.logger import send_log
from handlers.admin import _issue_warning
from config import FLOOD_MESSAGE_LIMIT, FLOOD_TIME_WINDOW, LINK_SPAM_RESTRICT_DAYS
 
# In-memory flood tracker: {(chat_id, user_id): [timestamps]}
_message_times = defaultdict(list)
 
# Bad-word list — common Hindi/Urdu aur English gaaliyan + unke common spelling
# variations (taaki log thoda spelling badal kar bhi bypass na kar sakein).
# Zaroorat ke hisaab se aage aur words add/remove kar sakte hain.
BAD_WORDS = {
    # Hindi/Urdu — madarchod
    "madarchod", "madarchodd", "mc", "mderchod", "madrchod", "matarchod",
    # behenchod / bhenchod
    "behenchod", "bhenchod", "bc", "bhenchodd", "bahenchod", "bhosdike",
    "bhosdiwala", "bhosda", "bhosdi",
    # chutiya / chutiyapa
    "chutiya", "chutiye", "chutiyapa", "chutya", "chutmarike",
    # randi / raand
    "randi", "randy", "raand", "randwa", "randibaaz",
    # gandu / gaand
    "gandu", "gaand", "gand", "gandmasti", "gaandu",
    # lund / lauda
    "lund", "lauda", "laude", "lawda", "loda", "lodu",
    # chodu / chod
    "chod", "chodu", "chodna", "chudai", "chuda",
    # harami / kutta / saala etc.
    "harami", "haraami", "kutta", "kutti", "saala", "saali", "kamina",
    "kaminey", "kamine",
    # English profanity
    "fuck", "fucking", "fucker", "fuk", "fck", "fuckin", "motherfucker",
    "bitch", "bitches", "asshole", "ass", "bastard", "bastards", "slut",
    "whore", "dick", "dickhead", "pussy", "cunt", "shit", "shitty",
    "damn", "piss", "nigger", "nigga",
}
 
 
 
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
        await context.bot.send_message(chat.id, t(lang, "bad_word_deleted"))
        await send_log(context, chat.id, t(lang, "log_bad_word", name=user.full_name))
        await _issue_warning(update, context, user, "bad language")
        return False
 
    # 2) Flood protection
    if group["flood_protection"] and _is_flooding(chat.id, user.id):
        until = int(time.time()) + group["mute_duration"]
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            db.block_user(chat.id, user.id, group["mute_duration"])
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
 
            spam_text = (
                t(lang, "spam_deleted")
                + "\n"
                + t(lang, "spam_restricted", name=user.full_name, days=LINK_SPAM_RESTRICT_DAYS)
            )
            await context.bot.send_message(chat.id, spam_text)
            await send_log(context, chat.id, t(lang, "log_spam", name=user.full_name))
            return False
 
    return True
 
 
