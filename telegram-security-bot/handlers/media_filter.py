"""
Media filter — photos/videos/GIFs ko 18+/unsafe content ke liye check karta hai.
 
NOTE: Real NSFW detection ke liye ek AI/ML model ya API (jaise Google Cloud
Vision SafeSearch, Sightengine, ya koi open-source NSFW classifier) connect
karna padega — us provider ka apna API key hoga. Yaha ek clean "hook"
(check_media function) diya gaya hai jaha aap apni pasand ki service jod
sakte hain. Abhi ye function hamesha "safe" return karta hai jab tak aap
apna detection logic ya API call nahi daalte.
"""
 
from telegram import Update
from telegram.ext import ContextTypes
 
import database as db
from utils.lang import t
from handlers.logger import send_log
 
 
async def check_media_safety(file_bytes: bytes) -> bool:
    """
    True = safe, False = unsafe (18+/explicit).
    Yaha apni NSFW-detection API ya model call karein, jaise:
 
        import requests
        resp = requests.post("https://api.sightengine.com/1.0/check.json", ...)
        return resp.json()["nudity"]["raw"] < 0.5
 
    Abhi ke liye placeholder — hamesha True (safe) return karta hai.
    """
    return True
 
 
async def media_moderation_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True = message allowed rahega, False = already delete ho chuka hai."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
 
    if not message or user.is_bot:
        return True
 
    group = db.get_group(chat.id)
    if not group["media_protection"]:
        return True
 
    has_media = message.photo or message.video or message.animation or message.document
    if not has_media:
        return True
 
    from handlers.admin import is_authorized_admin
    if await is_authorized_admin(chat.id, user.id, context=context):
        return True
 
    lang = db.get_effective_language(chat.id, user.id)
 
    # File download karke check_media_safety() ko diya ja sakta hai:
    # file = await context.bot.get_file(message.photo[-1].file_id)
    # file_bytes = await file.download_as_bytearray()
    # safe = await check_media_safety(file_bytes)
    safe = True  # placeholder jab tak real detection API connect na ho
 
    if not safe:
        try:
            await message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat.id, t(lang, "media_deleted"))
        await send_log(context, chat.id, t(lang, "log_media_detected", name=user.full_name))
        db.block_user(chat.id, user.id, group["block_duration"])
        return False
 
    return True
