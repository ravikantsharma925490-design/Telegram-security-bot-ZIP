"""
Welcome handler — naye member ka welcome, goodbye, language selection button,
aur join requests ko automatically accept karna (Force Join System se pehle).
 
Welcome/Goodbye ab DO raaston se chalte hain:
  1. Service message ("X joined/left")      -> welcome_new_member / member_left
  2. chat_member update (Telegram ka status) -> chat_member_update
Jin groups mein Telegram service message nahi bhejta, wahan raasta 2 kaam karta hai.
Jahan dono aate hain wahan MongoDB dedupe se welcome sirf EK baar jata hai.
"""
 
import logging
import os
import random
import time
 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t, LANGUAGE_NAMES
from config import GROUP_WELCOME_IMAGES, GOODBYE_IMAGE
from handlers.admin import send_photo_or_text
from handlers.logger import send_log
 
log = logging.getLogger(__name__)
 
_DEDUPE_SECONDS = 60
 
 
async def auto_accept_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naye 'join request' (approval-required groups/channels) ko turant accept karta hai."""
    request = update.chat_join_request
    chat = request.chat
    user = request.from_user
 
    group = db.get_group(chat.id)
    if not group.get("auto_accept_requests", 1):
        return
 
    try:
        await context.bot.approve_chat_join_request(chat.id, user.id)
    except Exception as e:
        log.warning("approve_chat_join_request failed in chat %s: %s", chat.id, e)
        return
 
    lang = group.get("default_language", "en")
    await send_log(context, chat.id, t(lang, "log_auto_request_approved", name=user.full_name))
 
 
# ---- Dedupe: service message + chat_member dono aayein to bhi welcome/goodbye ek hi baar ----
def _first_time(kind, chat_id, user_id):
    """True agar ye event pichle 60 sec mein pehle handle nahi hua.
    MongoDB use hota hai kyunki Vercel (serverless) mein memory har request pe reset ho sakti hai.
    DB fail ho to True (fail-open): double welcome ho sakta hai, par welcome miss nahi hoga."""
    now = time.time()
    try:
        old = db._db.welcome_events.find_one_and_update(
            {"_id": f"{kind}:{chat_id}:{user_id}"},
            {"$set": {"ts": now}},
            upsert=True,
        )  # default: update se PEHLE ka document lautata hai (ya None)
    except Exception:
        log.exception("dedupe check failed, proceeding anyway")
        return True
    return old is None or (now - old.get("ts", 0)) > _DEDUPE_SECONDS
 
 
# ---- Welcome/Goodbye photos: har baar agli photo (5 me se, repeat tab tak nahi jab tak sab na aa jayein)
_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "images")
_photo_bags = {}  # chat_id -> bachi hui photos ki list
 
 
def _next_photo(chat_id):
    bag = _photo_bags.get(chat_id)
    if not bag:
        bag = list(GROUP_WELCOME_IMAGES)
        random.shuffle(bag)
        # naya round pichli aakhri photo se shuru na ho
        last = _photo_bags.get(("last", chat_id))
        if last and len(bag) > 1 and bag[-1] == last:
            bag[0], bag[-1] = bag[-1], bag[0]
    photo = bag.pop()
    _photo_bags[chat_id] = bag
    _photo_bags[("last", chat_id)] = photo
    return photo
 
 
async def _send_photo_message(context, chat_id, text, reply_to=None):
    """Welcome photo (rotation se) + text. Reply wala message delete ho gaya ho to bina reply ke dobara try."""
    url = _next_photo(chat_id) if GROUP_WELCOME_IMAGES else None
    try:
        await send_photo_or_text(context, chat_id, url, text, reply_to=reply_to)
        return
    except Exception as e:
        log.warning("welcome send failed (reply_to=%s): %s", reply_to, e)
 
    if reply_to is not None:
        try:
            await send_photo_or_text(context, chat_id, url, text, reply_to=None)
        except Exception as e:
            log.warning("welcome send failed again without reply: %s", e)
 
 
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
 
 
async def _welcome_member(context, chat, member, reply_to=None):
    if member.is_bot or not _first_time("join", chat.id, member.id):
        return
    group = db.get_group(chat.id)
    lang = group.get("default_language", "en")
    text = t(lang, "welcome", name=member.full_name)
    await _send_photo_message(context, chat.id, text, reply_to=reply_to)
    try:
        await send_log(context, chat.id, t(lang, "log_user_joined", name=member.full_name))
    except Exception:
        log.exception("send_log (join) failed in chat %s", chat.id)
 
 
async def _goodbye_member(context, chat, member, left_by_self):
    if member.is_bot or not _first_time("leave", chat.id, member.id):
        return
    group = db.get_group(chat.id)
    lang = group.get("default_language", "en")
    # Goodbye sirf tab jab member ne khud group chhoda ho (ban/kick par nahi).
    if left_by_self:
        try:
            await send_photo_or_text(
                context, chat.id, GOODBYE_IMAGE,
                t(lang, "goodbye", name=member.full_name),
            )
        except Exception as e:
            log.warning("goodbye send failed in chat %s: %s", chat.id, e)
    try:
        await send_log(context, chat.id, t(lang, "log_user_left", name=member.full_name))
    except Exception:
        log.exception("send_log (left) failed in chat %s", chat.id)
 
 
# ---- Raasta 1: service messages ----
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab naya member group mein aaye ("X joined" service message aaye) — welcome."""
    chat = update.effective_chat
    try:
        for member in update.message.new_chat_members:
            await _welcome_member(context, chat, member, reply_to=update.message.message_id)
    except Exception:
        log.exception("welcome_new_member failed in chat %s", chat.id)
 
 
async def member_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    try:
        left_member = update.message.left_chat_member
        if left_member:
            sender = update.message.from_user
            left_by_self = sender is None or sender.id == left_member.id
            await _goodbye_member(context, chat, left_member, left_by_self)
    except Exception:
        log.exception("member_left failed in chat %s", chat.id)
 
 
# ---- Raasta 2: chat_member updates (jahan service message nahi aata) ----
def _is_in(member):
    """Kya ye user abhi group ka member hai?"""
    if member.status in ("member", "administrator", "creator"):
        return True
    return member.status == "restricted" and bool(getattr(member, "is_member", False))
 
 
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.chat_member
    if cmu is None:
        return
    chat = cmu.chat
    if chat.type not in ("group", "supergroup"):
        return
 
    old, new = cmu.old_chat_member, cmu.new_chat_member
    user = new.user
    was_in, is_in = _is_in(old), _is_in(new)
 
    try:
        if not was_in and is_in:
            await _welcome_member(context, chat, user)
        elif was_in and not is_in and new.status == "left":
            actor = cmu.from_user
            left_by_self = actor is None or actor.id == user.id
            await _goodbye_member(context, chat, user, left_by_self)
    except Exception:
        log.exception("chat_member_update failed in chat %s", chat.id)
 
 
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
 
