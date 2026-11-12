"""
Bot Link Cleaner — group mein koi DOOSRA bot (jaise /broadcast se promotion) link wala
message bheje to usse chup-chaap delete kar deta hai. Koi warning, restrict ya notice nahi.

Kya delete hota hai:
  - Doosre bot ka message jisme koi bhi link ho: text ka link (http, https, t.me),
    kisi word ke peeche chhupa link, photo/video caption ka link, ya message ke
    neeche ke BUTTONS ka link.
  - Agar message mein ek bhi link "apna" nahi hai (apna + doosre ka dono = delete).

Kya delete NAHI hota:
  - Bot ka message jisme koi link nahi hai.
  - Message jisme sirf "apne" links hain:
      * is group ka apna link (public username ya group ka main invite link, bot khud dekh leta hai)
      * /setchannel aur /setgroup se set kiye channel/group
      * BOT_LINK_ALLOW wale links (neeche dekho: Join Group link, @CinemaGyan_bot, @EccSecurity_Bot)
  - Aapke apne bots (@EccSecurity_Bot, @CinemaGyan_bot), Telegram ke service accounts
    (Anonymous Admin, Channel post) aur bot ka apna message.
  - Insaano ke messages (unke liye handlers/moderation.py pehle jaisa kaam karta hai).

Settings (Vercel/Render env, sab optional):
  BOT_LINK_CLEANER=0   -> ye feature band
  BOT_LINK_ALLOW=...   -> comma se alag "apne" links/bots. Username (cinemagyan_bot),
                          invite link ka hissa (+xfk1QS-y50RmOTc1) ya website (example.com).
                          Ye list default ki jagah leti hai, isliye purane items bhi likhna.

Zaroori: Telegram ke BotFather mein is bot ka "Bot to Bot Communication Mode" ON ho
aur bot group mein admin ho (Delete messages right ke saath), tabhi doosre bots ke
messages bot tak pahunchte hain.
"""

import logging
import os
import re
import time
from urllib.parse import urlparse, parse_qs

from telegram import Update, MessageEntity
from telegram.ext import ContextTypes

import database as db

log = logging.getLogger(__name__)

ENABLED = os.environ.get("BOT_LINK_CLEANER", "1").strip() != "0"

# Default "apne" links: dono bots + Join Group link
_DEFAULT_ALLOW = "cinemagyan_bot,eccsecurity_bot,+xfk1QS-y50RmOTc1"

# Telegram ke service accounts: Telegram (777000), Anonymous Admin, Channel_Bot
_SERVICE_IDS = {777000, 1087968824, 136817688}

_TG_HOSTS = {"t.me", "telegram.me", "telegram.dog"}
_TG_PREFIX_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/", re.I)
_URL_RE = re.compile(
    r"(?:https?://|tg://)[^\s<>\"']+"
    r"|(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>\"']+",
    re.I,
)
# t.me/<yeh> — ye username nahi, Telegram ke khas links hain (apna nahi maane jayenge)
_TG_RESERVED = {
    "addstickers", "addemoji", "share", "proxy", "socks", "setlanguage", "boost",
    "m", "iv", "addtheme", "login", "invoice", "giftcode", "contact", "bg", "confirmphone",
}


def _add_allow(item, users, hashes, domains):
    """Ek allow entry ko sahi set mein daalta hai (username / invite hash / website)."""
    item = (item or "").strip()
    if not item:
        return
    item = _TG_PREFIX_RE.sub("", item).strip().strip("/")
    if not item:
        return
    if item.startswith("+"):
        hashes.add(item[1:])
    elif item.lower().startswith("joinchat/"):
        hashes.add(item.split("/", 1)[1])
    elif "." in item:
        domains.add(item.lower().lstrip("@"))
    else:
        users.add(item.lstrip("@").lower())


def _parse_allow(raw):
    users, hashes, domains = set(), set(), set()
    for item in (raw or "").split(","):
        _add_allow(item, users, hashes, domains)
    return users, hashes, domains


_ALLOW_USERS, _ALLOW_HASHES, _ALLOW_DOMAINS = _parse_allow(os.environ.get("BOT_LINK_ALLOW", _DEFAULT_ALLOW))

# {chat_id: (time, {"users": set, "hashes": set, "domains": set})} — 5 minute cache
_own_cache = {}
_OWN_CACHE_SECONDS = 300


def _parse_link(url):
    """
    Link ko (kind, value) mein badalta hai:
      ("user", "username")   t.me/username, tg://resolve?domain=username
      ("invite", "hash")     t.me/+hash, t.me/joinchat/hash, tg://join?invite=hash
      ("chatid", "123456")   t.me/c/123456/7  (private group ke message ka link)
      ("domain", "host")     koi bhi website
      ("other", "...")       Telegram ka khas link (apna nahi)
      None                   ignore (jaise tg://user?id=... clickable naam)
    """
    u = (url or "").strip().rstrip(".,;:!?)]}»”’'\"")
    if not u:
        return None
    low = u.lower()

    if low.startswith("tg:"):
        p = urlparse(u)
        q = parse_qs(p.query)
        kind = (p.netloc or p.path.strip("/")).lower()
        if kind == "user":
            return None  # clickable naam (mention), promotion link nahi
        if kind == "resolve":
            d = q.get("domain")
            return ("user", d[0].lower()) if d else ("other", u)
        if kind == "join":
            i = q.get("invite")
            return ("invite", i[0]) if i else ("other", u)
        return ("other", u)

    if not re.match(r"^[a-z][a-z0-9+.\-]*://", low):
        u = "https://" + u
    p = urlparse(u)
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None

    if host in _TG_HOSTS:
        parts = [s for s in p.path.split("/") if s]
        if not parts:
            return ("other", host)
        first = parts[0]
        if first.startswith("+"):
            return ("invite", first[1:])
        fl = first.lower()
        if fl == "joinchat" and len(parts) > 1:
            return ("invite", parts[1])
        if fl == "c" and len(parts) > 1:
            return ("chatid", parts[1])
        if fl in _TG_RESERVED:
            return ("other", u)
        return ("user", fl)

    return ("domain", host)


def _is_own(parsed, own, chat_id):
    kind, val = parsed
    if kind == "user":
        return val in own["users"]
    if kind == "invite":
        return val in own["hashes"]
    if kind == "chatid":
        cid = str(chat_id)
        return cid.startswith("-100") and val == cid[4:]
    if kind == "domain":
        return any(val == d or val.endswith("." + d) for d in own["domains"])
    return False


async def _own_links(context, chat_id):
    """Is group ke 'apne' links: group ka apna link + /setchannel + /setgroup + BOT_LINK_ALLOW."""
    now = time.time()
    hit = _own_cache.get(chat_id)
    if hit and now - hit[0] < _OWN_CACHE_SECONDS:
        return hit[1]

    users, hashes, domains = set(_ALLOW_USERS), set(_ALLOW_HASHES), set(_ALLOW_DOMAINS)
    if context.bot.username:
        users.add(context.bot.username.lower())

    # Group ka apna link. NOTE: bot kabhi naya invite link nahi banata (isse purana link toot jata hai),
    # sirf Telegram se jo link already hai wahi padhta hai.
    try:
        chat = await context.bot.get_chat(chat_id)
        if getattr(chat, "username", None):
            users.add(chat.username.lower())
        for un in (getattr(chat, "active_usernames", None) or []):
            users.add(un.lower())
        link = getattr(chat, "invite_link", None)
        if link:
            parsed = _parse_link(link)
            if parsed and parsed[0] == "invite":
                hashes.add(parsed[1])
    except Exception:
        log.warning("bot_link_cleaner: get_chat failed for %s", chat_id)

    # /setchannel aur /setgroup se set kiye gaye
    try:
        group = db.get_group(chat_id)
        for field in ("required_channel", "required_group"):
            _add_allow(group.get(field), users, hashes, domains)
    except Exception:
        log.warning("bot_link_cleaner: group settings read failed for %s", chat_id)

    own = {"users": users, "hashes": hashes, "domains": domains}
    _own_cache[chat_id] = (now, own)
    return own


def _extract_urls(message):
    """Message ke text, caption, chhupe links aur buttons se sab links nikalta hai."""
    urls = []

    for text, ents, parse in (
        (message.text, message.entities, message.parse_entities),
        (message.caption, message.caption_entities, message.parse_caption_entities),
    ):
        if not text:
            continue
        urls.extend(_URL_RE.findall(text))
        try:
            urls.extend(parse([MessageEntity.URL]).values())  # bina http wale links (example.com)
        except Exception:
            pass
        for ent in ents or []:
            if ent.type == MessageEntity.TEXT_LINK and ent.url:  # word ke peeche chhupa link
                urls.append(ent.url)

    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "inline_keyboard", None) or []:
        for button in row:
            if getattr(button, "url", None):
                urls.append(button.url)
            login_url = getattr(button, "login_url", None)
            if login_url is not None and getattr(login_url, "url", None):
                urls.append(login_url.url)

    return urls


async def bot_link_cleaner_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    True  = aage process hone do.
    False = doosre bot ka link wala message tha, delete ho gaya (kuch aur nahi hota).
    """
    if not ENABLED:
        return True

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or not user.is_bot:
        return True

    # Bot ka apna message, service accounts, channel ke naam se aaya post
    if user.id == context.bot.id or user.id in _SERVICE_IDS:
        return True
    if message.sender_chat or getattr(message, "is_automatic_forward", False):
        return True

    # Aapke apne bots (@CinemaGyan_bot, @EccSecurity_Bot ...) kabhi delete nahi
    if (user.username or "").lower() in _ALLOW_USERS:
        return True

    urls = _extract_urls(message)
    if not urls:
        return True

    own = await _own_links(context, chat.id)
    for url in urls:
        parsed = _parse_link(url)
        if parsed is None:
            continue
        if not _is_own(parsed, own, chat.id):
            try:
                await message.delete()
                log.info("bot_link_cleaner: deleted link message from @%s in %s", user.username, chat.id)
            except Exception:
                log.warning("bot_link_cleaner: delete failed in %s (bot ko Delete messages right chahiye)", chat.id)
            return False

    return True
