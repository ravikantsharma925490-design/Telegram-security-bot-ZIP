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
    # Count MongoDB mein rakha jata hai (Vercel par memory reset ho jati hai)
    return db.add_flood_hit(chat_id, user_id, FLOOD_TIME_WINDOW) > FLOOD_MESSAGE_LIMIT
 
 
def _is_present(member) -> bool:
    """Kya ye user/bot abhi group ka member hai? (left/kicked = nahi)"""
    if member.status in ("member", "administrator", "creator"):
        return True
    return member.status == "restricted" and bool(getattr(member, "is_member", False))
 
 
async def _bot_missing_from_group(context, chat_id, name) -> bool:
    """
    name = "@xyzbot". True = ye bot is group mein NAHI hai (spam/warning).
    False = bot group mein hai, ya verify nahi ho paya (tab kuch nahi karte).
    Pehle database (group mein add hue bots), warna Telegram se khud check.
    """
    uname = name.lstrip("@").lower()
    my_name = (context.bot.username or (await context.bot.get_me()).username or "").lower()
    if uname == my_name:
        return False
    if db.is_group_bot(chat_id, uname):
        return False
    try:
        chat_obj = await context.bot.get_chat("@" + uname)
    except Exception:
        return False  # resolve nahi hua => verify nahi kar sakte, kuch nahi
    if chat_obj.type in ("channel", "group", "supergroup"):
        return True  # "...bot" naam ka channel/group => spam
    try:
        member = await context.bot.get_chat_member(chat_id, chat_obj.id)
    except Exception:
        return False
    if _is_present(member):
        db.add_group_bot(chat_id, chat_obj.id, uname)  # aage se database se hi pata chal jayega
        return False
    return True
 
 
async def _id_mention_missing_from_group(context, chat_id, message) -> bool:
    """
    ID se mention (clickable naam / text_mention) ke liye: mention kiya gaya user
    group mein nahi hai to True. Group mein hai ya check fail ho to False.
    """
    seen = set()
    for ent in (message.entities or []):
        if ent.type != "text_mention" or not ent.user:
            continue
        uid = ent.user.id
        if uid == context.bot.id or uid in seen:
            continue
        seen.add(uid)
        if len(seen) > 5:  # speed ke liye max 5
            break
        try:
            member = await context.bot.get_chat_member(chat_id, uid)
        except Exception:
            continue  # verify nahi hua => kuch nahi
        if not _is_present(member):
            return True
    return False
 
 
async def _has_bad_mention(message, context, chat_id) -> bool:
    """
    True = message spam maana jayega:
      - @channel / @group username
      - @xyzbot jo is group mein NAHI hai (group wala bot allowed)
      - ID se mention kiya user jo group mein NAHI hai (group wala user allowed)
    User ka sirf @username allowed (Telegram se member status verify nahi hota).
    """
    try:
        mentions = list(message.parse_entities(["mention"]).values())
    except Exception:
        mentions = []
    seen = set()
    for m in mentions[:5]:  # max 5 mentions check karte hain (speed ke liye)
        name = m.lower()
        if name in seen:
            continue
        seen.add(name)
        if name.endswith("bot"):
            if await _bot_missing_from_group(context, chat_id, name):
                return True
            continue
        try:
            chat_obj = await context.bot.get_chat(name)
        except Exception:
            continue  # resolve nahi hua => user maana, kuch nahi karna
        if chat_obj.type in ("channel", "group", "supergroup"):
            return True
    return await _id_mention_missing_from_group(context, chat_id, message)
 
 
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
        # Links (http, https, t.me) sabke liye spam hain.
        link_count = message.text.count("http://") + message.text.count("https://") + message.text.count("t.me/")
        # @name: sirf channel/group ka username spam hai. User ka @name allowed.
        bad_mention = False
        has_id_mention = any(e.type == "text_mention" for e in (message.entities or []))
        if link_count == 0 and ("@" in message.text or has_id_mention):
            bad_mention = await _has_bad_mention(message, context, chat.id)
        if link_count >= 1 or bad_mention:
            try:
                await message.delete()
            except Exception:
                pass
 
            # Seedha restrict nahi: warning system (limit 5) handle karta hai
            db.incr_stat("spam_deleted")
            await send_log(context, chat.id, t(lang, "log_spam", name=user.full_name))
            await _issue_warning(update, context, user, "link/channel username")
            return False
 
    return True
 
 
 
 
 
 
 
 
