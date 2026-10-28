"""
Bio-link check — kisi member ki profile bio mein link ho to group mein usko aur
group owner ko mention karke English mein bata deta hai. Message delete nahi
hota, koi warning/restrict/ban nahi. Owner ko DM mein bhi ek baar batata hai.
 
- Bio har user ki ek group mein 10 minute mein sirf ek baar check hoti hai (speed ke liye).
- Ek user ke liye notice 24 ghante mein sirf ek baar jata hai (bio saaf karke dobara
  link lagaye tab bhi 24 ghante se pehle dobara nahi aata).
- Owner/admin par ye check lagta hi nahi.
"""
 
import html
import logging
import re
import time
 
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
 
import database as db
from handlers.admin import is_authorized_admin
 
logger = logging.getLogger(__name__)
 
# Bio kitni der mein dobara check hogi (seconds)
BIO_CHECK_INTERVAL = 600
 
# Ek user ke liye notice kitne ghante mein sirf ek baar (seconds)
NOTICE_COOLDOWN = 24 * 60 * 60
 
# Owner ko DM bhi bhejna hai? (False kar do to sirf group mein mention jayega)
BIO_LINK_DM_OWNER = True
 
# Telegram ka "Anonymous Admin" user id
_ANONYMOUS_ADMIN_ID = 1087968824
 
_LINK_RE = re.compile(
    r"(https?://|t\.me/|telegram\.me/|telegram\.dog/|www\.)"
    r"|\b[a-z0-9-]+\.(com|in|org|net|me|io|xyz|link|ly|gg|app|co|info|site|online|club|top)\b",
    re.IGNORECASE,
)
 
 
def bio_has_link(bio) -> bool:
    return bool(bio) and _LINK_RE.search(bio) is not None
 
 
def _mention(user) -> str:
    """@username ho to wahi, warna clickable naam (profile khulti hai)."""
    if user.username:
        return f"@{html.escape(user.username)}"
    name = html.escape(user.full_name or "User")
    return f'<a href="tg://user?id={user.id}">{name}</a>'
 
 
async def _find_group_owner(chat_id: int, context):
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
    except Exception:
        return None
    for a in admins:
        if a.status == "creator":
            return a.user
    return None
 
 
async def bio_link_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ye kabhi message ko rokta nahi aur kabhi error bahar nahi phenkta."""
    try:
        await _bio_link_check(update, context)
    except Exception as e:  # bot ka baaki kaam kabhi na ruke
        logger.warning("bio_link_check failed: %s", e)
 
 
async def _bio_link_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user:
        return
    if user.is_bot or user.id == _ANONYMOUS_ADMIN_ID or message.sender_chat:
        return
 
    state = db.get_bio_state(chat.id, user.id)
    now = time.time()
    if state and now - state.get("checked_at", 0) < BIO_CHECK_INTERVAL:
        return  # abhi haal hi mein check ho chuka hai
 
    # Bio Telegram se padho
    try:
        info = await context.bot.get_chat(user.id)
    except Exception:
        return  # bio nahi mili => kuch nahi karna
    has_link = bio_has_link(getattr(info, "bio", None))
 
    # Link nahi hai, ya 24 ghante mein notice pehle hi ja chuka hai => kuch nahi bhejna
    last_notice = (state or {}).get("notified_at", 0)
    if not has_link or now - last_notice < NOTICE_COOLDOWN:
        db.set_bio_state(chat.id, user.id)
        return
 
    # Owner / admin par lagu nahi
    if await is_authorized_admin(chat.id, user.id, context=context):
        db.set_bio_state(chat.id, user.id)
        return
 
    owner = await _find_group_owner(chat.id, context)
 
    text = f"{_mention(user)}, your bio contains a link. Please remove it."
    if owner:
        text += f"\n{_mention(owner)}, this member's bio contains a link."
 
    await context.bot.send_message(chat.id, text, parse_mode=ParseMode.HTML)
    db.set_bio_state(chat.id, user.id, notified_now=True)
 
    # Owner ko DM (sirf tab chalta hai jab owner ne bot ko private mein /start kiya ho)
    if BIO_LINK_DM_OWNER and owner:
        try:
            await context.bot.send_message(
                owner.id,
                f"⚠️ In {html.escape(chat.title or 'your group')}, {_mention(user)} "
                f"has a link in their bio. Please ask them to remove it.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass  # DM band ho ya owner ne /start na kiya ho => group notice kaafi hai
 
