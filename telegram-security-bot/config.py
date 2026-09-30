"""
Config file — sab basic settings yaha se load hoti hain.
BOT_TOKEN environment variable se lo (safe rehta hai), ya seedha yaha likh do.
"""
 
import os
 
# BotFather se mila token yaha daalo (ya environment variable BOT_TOKEN set karo)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
 
# MongoDB connection — local ke liye default, ya MongoDB Atlas ka connection string yaha/env mein daalo
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "telegram_security_bot")
 
# Default language jab tak user apni language na choose kare
DEFAULT_LANGUAGE = "en"
 
# Default warning limit (kitni warnings ke baad auto-mute/ban)
DEFAULT_WARNING_LIMIT = 3
 
# Default temporary mute/block duration (seconds mein)
DEFAULT_MUTE_DURATION = 60 * 60          # 1 ghanta
DEFAULT_BLOCK_DURATION = 60 * 60 * 24    # 1 din
 
# Flood control: itne seconds ke andar itne messages = flood
FLOOD_MESSAGE_LIMIT = 5
FLOOD_TIME_WINDOW = 10  # seconds
 
# Force Join ke liye default required channel/group (owner ne diya)
DEFAULT_REQUIRED_CHANNEL = ""
DEFAULT_REQUIRED_GROUP = ""
 
# Link/username spam bhejne par kitne din ke liye restrict karna hai
LINK_SPAM_RESTRICT_DAYS = 3
 
# Bot ki personal/DM chat me /start karne par ye welcome image bheji jaati hai.
# Yaha koi bhi public image URL, ya Telegram file_id (jo ek baar bot ko photo
# bhejkar update.message.photo[-1].file_id se milta hai), daal sakte ho.
WELCOME_IMAGE = os.environ.get(
    "WELCOME_IMAGE",
    "https://raw.githubusercontent.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/main/images/welcome.jpg",
)
 
 
# Bot ke malik (tumhara) numeric Telegram user ID — /stats aur /groups sirf isse chalenge.
# Render env mein OWNER_ID naam se daalo (ID @userinfobot se milti hai).
OWNER_ID = int(os.environ.get("OWNER_ID", "0") or 0)
 
 
# Group welcome ke liye photos — naya member aane par inme se koi ek random
# photo lagti hai. Render env mein GROUP_WELCOME_IMAGES daal kar (comma se
# alag URLs) is list ko override bhi kar sakte ho.
_RAW_WELCOME_IMAGES = [
    u.strip() for u in os.environ.get(
        "GROUP_WELCOME_IMAGES",
        "https://raw.githubusercontent.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/main/images/imagesgroup_welcome1.jpg,"
        "https://raw.githubusercontent.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/main/images/imagesgroup_welcome2.jpg,"
        "https://raw.githubusercontent.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/main/images/imagesgroup_welcome3.jpg,"
        "https://raw.githubusercontent.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/main/images/imagesgroup_welcome4.jpg,"
        "https://raw.githubusercontent.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/main/images/imagesgroup_welcome5.jpg",
    ).split(",") if u.strip()
]
 
 
def _to_raw(url):
    """github.com/.../blob/... (web page) ko raw.githubusercontent.com (direct image) me badalta hai."""
    if "github.com" in url and "/blob/" in url:
        url = url.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/", 1)
    return url
 
 
GROUP_WELCOME_IMAGES = [_to_raw(u) for u in _RAW_WELCOME_IMAGES]
 
 
# Restrict hone par jo photo message ke saath jayegi (GitHub par images/restricted.jpg)
RESTRICTED_IMAGE = _to_raw(os.environ.get(
    "RESTRICTED_IMAGE",
    "https://github.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/blob/main/images/restricted.jpg",
).strip())
 
 
# Ban hone par jo photo message ke saath jayegi (GitHub par images/banned.jpg)
BANNED_IMAGE = _to_raw(os.environ.get(
    "BANNED_IMAGE",
    "https://github.com/ravikantsharma925490-design/Telegram-security-bot-ZIP/blob/main/images/banned.jpg",
).strip())
 
