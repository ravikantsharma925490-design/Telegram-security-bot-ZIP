"""
Join DM — naya member group mein aaye to usko private mein ek welcome DM bhejta hai.

Do raaste:
  1. Join request (approval wale group): bot request approve karta hai aur turant DM bhejta hai.
     (Telegram join request ke saath DM ki permission deta hai, user ne bot /start kiya ho ya na kiya ho.)
  2. Seedha add / open join: DM tabhi jaata hai jab user ne bot pehle start kiya ho.
     Nahi to Telegram "Forbidden" deta hai — bot chup-chaap skip karta hai (koi error / spam nahi).

Ek user ko ek group ke liye ek hi baar DM jaata hai (MongoDB dedupe).
Band karne ke liye env mein JOIN_DM_ENABLED=0 daalo.
"""

import html
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, TelegramError

import database as db

log = logging.getLogger(__name__)

JOIN_DM_ENABLED = os.environ.get("JOIN_DM_ENABLED", "1").strip() != "0"

# Buttons / links (env se badal sakte ho)
MOVIE_BOT_URL = os.environ.get("JOIN_DM_MOVIE_BOT_URL", "https://t.me/CinemaGyan_bot").strip()
JOIN_GROUP_URL = os.environ.get("JOIN_DM_GROUP_URL", "https://t.me/+xfk1QS-y50RmOTc1").strip()
START_BOT_URL = os.environ.get("JOIN_DM_START_BOT_URL", "https://t.me/EccSecurity_Bot").strip()


def _build_text(user, chat) -> str:
    name = html.escape(user.first_name or user.full_name or "friend")
    group_name = html.escape(chat.title or "the group")
    return (
        f"👋 Hey {name}!\n\n"
        f"Your request to join <b>{group_name}</b> has been approved! ✅ Welcome aboard! 🎉\n"
        f"Why not have some fun while you’re here?\n\n"
        f"🚀 <b>Meet New People Instantly!</b>\n"
        f"Connect with strangers, make new friends, or even find your soulmate using @CinemaGyan_bot!\n"
        f"No phone numbers needed. 100% Safe, Secure, &amp; Anonymous! 🛡\n\n"
        f'💖 <a href="{html.escape(MOVIE_BOT_URL, quote=True)}">Click here to start chatting now!</a>\n\n'
        f"👇 Or use the buttons below!"
    )


def _build_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Movie Bot", url=MOVIE_BOT_URL)],
        [InlineKeyboardButton("🎉 Join Group", url=JOIN_GROUP_URL)],
        [InlineKeyboardButton("▶️ Start Bot", url=START_BOT_URL)],
    ])


async def send_join_dm(context, chat, user, dm_chat_id=None):
    """Naye member ko welcome DM. Kabhi exception bahar nahi phenkta, group ke kaam ko nahi rokta.

    dm_chat_id: join request mein request.user_chat_id (bina /start ke bhi chalta hai).
    """
    if not JOIN_DM_ENABLED or user is None or getattr(user, "is_bot", False):
        return False

    try:
        if not db.claim_join_dm(chat.id, user.id):
            return False  # is user ko is group ke liye DM pehle ja chuka hai
    except Exception:
        log.exception("join DM claim failed")
        return False

    try:
        await context.bot.send_message(
            chat_id=dm_chat_id or user.id,
            text=_build_text(user, chat),
            parse_mode="HTML",
            reply_markup=_build_keyboard(),
            disable_web_page_preview=True,
        )
        return True
    except Forbidden:
        # User ne bot start nahi kiya / block kiya hai — chup-chaap skip, baad mein dobara try ho sakta hai
        db.release_join_dm(chat.id, user.id)
    except TelegramError as e:
        log.warning("join DM failed for user %s: %s", user.id, e)
        db.release_join_dm(chat.id, user.id)
    except Exception:
        log.exception("join DM crashed for user %s", user.id)
        db.release_join_dm(chat.id, user.id)
    return False
