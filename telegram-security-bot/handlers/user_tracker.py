"""
User tracker — group ke users ko database mein save karta hai. Sirf save; kisi par koi action nahi.

Save kab hota hai:
  1. User khud message kare            -> track_users (sender)
  2. Koi kisi ko mention kare           -> track_users (mention): bot Telegram se check karke,
                                           user group mein mila to save
  3. User join / add ho                 -> handlers/welcome.py (remember_member)
User group chhode ya ban ho to data hata diya jata hai (handlers/welcome.py).
"""

import logging

import database as db

log = logging.getLogger(__name__)

# Telegram ke service accounts (channel post / anonymous admin) — save nahi karte
_SKIP_IDS = {777000, 1087968824, 136817688}
_MAX_MENTION_LOOKUPS = 5  # ek message mein max itne mention Telegram se check (speed ke liye)


def _is_present(member) -> bool:
    """Kya ye user abhi group ka member hai? (left/kicked = nahi)"""
    if member.status in ("member", "administrator", "creator"):
        return True
    return member.status == "restricted" and bool(getattr(member, "is_member", False))


def save_user(chat_id, user):
    """User object ko save karta hai. Bots aur service accounts skip."""
    if user is None or getattr(user, "is_bot", False) or user.id in _SKIP_IDS:
        return
    db.save_group_user(chat_id, user.id, user.username, user.full_name)


async def _track_mentions(message, context, chat_id):
    lookups = 0

    # ID se mention (clickable naam)
    for ent in (message.entities or []):
        if ent.type != "text_mention" or not ent.user:
            continue
        u = ent.user
        if u.is_bot or u.id in _SKIP_IDS or db.is_saved_user(chat_id, u.id):
            continue
        if lookups >= _MAX_MENTION_LOOKUPS:
            return
        lookups += 1
        try:
            member = await context.bot.get_chat_member(chat_id, u.id)
        except Exception:
            continue
        if _is_present(member):
            save_user(chat_id, u)

    # @username se mention (bots ke @...bot yahan nahi; wo group_bots se handle hote hain)
    try:
        names = list(message.parse_entities(["mention"]).values())
    except Exception:
        names = []
    seen = set()
    for m in names:
        name = m.lstrip("@").lower()
        if name in seen or name.endswith("bot"):
            continue
        seen.add(name)
        if db.get_saved_user_by_username(chat_id, name):
            continue
        if lookups >= _MAX_MENTION_LOOKUPS:
            return
        lookups += 1
        try:
            chat_obj = await context.bot.get_chat("@" + name)
        except Exception:
            continue  # Telegram ne dhundha nahi => kuch save nahi
        if chat_obj.type != "private":
            continue  # channel/group ka username
        try:
            member = await context.bot.get_chat_member(chat_id, chat_obj.id)
        except Exception:
            continue
        if _is_present(member) and not getattr(chat_obj, "is_bot", False):
            db.save_group_user(chat_id, chat_obj.id, chat_obj.username or name, chat_obj.full_name)


async def track_users(update, context):
    """Har group message par: bhejne wala save + message ke mentions check karke save."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    # Anonymous admin / channel ke naam se aaya message => asli user nahi
    if message.sender_chat is None:
        save_user(chat.id, update.effective_user)

    if message.text and ("@" in message.text or message.entities):
        await _track_mentions(message, context, chat.id)
