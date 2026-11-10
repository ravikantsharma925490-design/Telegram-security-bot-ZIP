"""
Logger — important events ko log channels mein bhejta hai.

Do alag system:
  1. OWNER ka FIXED channel (config.LOG_CHANNEL_ID, env mein): SIRF 2 alert —
     naya user bot par aaya (+ total users) aur bot naye group mein add hua. -> send_owner_log()
  2. Har GROUP ka apna channel (/setlogchat): us group ke saare logs (join, leave, ban, mute,
     warn, spam, ...) sirf wahin jaate hain. Set nahi to kahin nahi. -> send_log()
     /settings ka "Admin Alerts" toggle isi ko ON/OFF karta hai.
"""

import logging
import time
from datetime import datetime, timezone, timedelta

from telegram.ext import ContextTypes

import database as db
from config import LOG_CHANNEL_ID, OWNER_ID

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
_title_cache = {}
_last_owner_alert = {}      # target -> last time (DM spam rokne ke liye)
_ALERT_COOLDOWN = 60 * 60   # ek hi problem ka DM ghante mein ek baar


def fmt_user(user) -> str:
    """Naam (@username | ID: 123)"""
    if user is None:
        return "Unknown"
    uname = f"@{user.username}" if getattr(user, "username", None) else "no username"
    return f"{user.full_name} ({uname} | ID: {user.id})"


def fmt_name_id(name, user_id) -> str:
    name = str(name or "")
    if not name or name == str(user_id):
        return f"ID: {user_id}"
    return f"{name} (ID: {user_id})"


def _by_line(by) -> str:
    if by is None:
        return ""
    if by == "auto":
        return "\n🤖 By: Bot (automatic)"
    return f"\n👮 By: {fmt_user(by)}"


def _now() -> str:
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p") + " IST"


async def _group_title(context, chat_id):
    if chat_id in _title_cache:
        return _title_cache[chat_id]
    try:
        chat = await context.bot.get_chat(chat_id)
        title = chat.title or str(chat_id)
    except Exception:
        title = str(chat_id)
    _title_cache[chat_id] = title
    return title


async def _alert_owner(context, key, text):
    """Fixed log channel kaam na kare to bot owner ko DM (ghante mein ek baar)."""
    if not OWNER_ID:
        return
    now = time.time()
    if now - _last_owner_alert.get(key, 0) < _ALERT_COOLDOWN:
        return
    _last_owner_alert[key] = now
    try:
        await context.bot.send_message(OWNER_ID, text)
    except Exception:
        pass  # owner ne bot ko private mein /start nahi kiya hoga


async def _send_owner_channel(context, msg):
    if not LOG_CHANNEL_ID:
        return
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=msg)
    except Exception as e:
        log.warning("Owner log channel (%s) par message nahi gaya: %s", LOG_CHANNEL_ID, e)
        await _alert_owner(
            context, "owner_channel",
            f"⚠️ Log channel ({LOG_CHANNEL_ID}) par message nahi ja raha.\n"
            f"Check karo: bot channel mein admin hai? ID sahi hai?\nError: {e}",
        )


async def send_owner_log(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Sirf owner ke fixed channel mein (group ke channel mein nahi)."""
    await _send_owner_channel(context, f"{text}\n\n🕒 {_now()}")


async def send_log(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, by=None):
    """
    Group event ka log — sirf is GROUP ke apne log channel (/setlogchat) mein jaata hai.
    Channel set nahi hai to kahin nahi jaata. Owner ke fixed channel mein group logs NAHI jaate.
      by=None   -> koi 'By' line nahi (join/leave jaise events)
      by="auto" -> bot ne khud action liya
      by=<User> -> is admin ne action liya
    """
    try:
        group = db.get_group(chat_id)
    except Exception:
        return
    own = group.get("log_chat_id") or 0
    if not own or not group.get("admin_alerts", 1):
        return  # channel set nahi, ya group ne Admin Alerts OFF kiya

    title = await _group_title(context, chat_id)
    msg = f"📝 {text}{_by_line(by)}\n\n🏷 Group: {title}\n🕒 {_now()}"
    try:
        await context.bot.send_message(chat_id=own, text=msg)
    except Exception as e:
        log.warning("Group %s ke log chat (%s) par message nahi gaya: %s", chat_id, own, e)
