"""
Database module — MongoDB (pymongo) ka use karke har group ki config, users ki
language, warnings, admins wagairah save karta hai. Har group ki config alag rehti hai.
 
Function names purane (SQLite version) jaise hi rakhe gaye hain, taaki handlers/*.py
mein kuch badalne ki zaroorat na pade.
"""
 
import time
from pymongo import MongoClient
 
from config import MONGO_URI, MONGO_DB_NAME, DEFAULT_WARNING_LIMIT, DEFAULT_MUTE_DURATION, DEFAULT_BLOCK_DURATION, DEFAULT_REQUIRED_CHANNEL, DEFAULT_REQUIRED_GROUP
 
_client = None
_db = None
 
DEFAULT_GROUP = {
    "owner_id": None,
    "default_language": "en",
    "anti_spam": 1,
    "flood_protection": 1,
    "bad_word_filter": 1,
    "media_protection": 1,
    "suspicious_activity": 1,
    "force_join": 1,
    "required_channel": DEFAULT_REQUIRED_CHANNEL,
    "required_group": DEFAULT_REQUIRED_GROUP,
    "warning_limit": DEFAULT_WARNING_LIMIT,
    "mute_duration": DEFAULT_MUTE_DURATION,
    "block_duration": DEFAULT_BLOCK_DURATION,
    "unauthorized_cmd_protection": 1,
    "admin_alerts": 1,
    "log_chat_id": 0,
    "auto_accept_requests": 1,
    "setup_done": 0,
}
 
 
def init_db():
    """MongoDB connect karta hai aur zaroori indexes bana deta hai."""
    global _client, _db
    _client = MongoClient(MONGO_URI)
    _db = _client[MONGO_DB_NAME]
 
    _db.groups.create_index("chat_id", unique=True)
    _db.group_admins.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
    _db.user_prefs.create_index("user_id", unique=True)
    _db.warnings.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
    _db.blocked_users.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
 
 
# ---------- Group config helpers ----------
 
def get_group(chat_id):
    doc = _db.groups.find_one({"chat_id": chat_id})
    if doc is None:
        doc = {"chat_id": chat_id, **DEFAULT_GROUP}
        _db.groups.insert_one(doc)
    return doc
 
 
def update_group(chat_id, **kwargs):
    get_group(chat_id)  # ensure doc exists
    _db.groups.update_one({"chat_id": chat_id}, {"$set": kwargs})
 
 
def toggle_group_setting(chat_id, field):
    group = get_group(chat_id)
    new_val = 0 if group[field] else 1
    update_group(chat_id, **{field: new_val})
    return new_val
 
 
# ---------- Admin helpers ----------
 
def add_group_admin(chat_id, user_id, can_ban=1, can_mute=1, can_warn=1, can_settings=0):
    _db.group_admins.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {
            "can_ban": can_ban, "can_mute": can_mute,
            "can_warn": can_warn, "can_settings": can_settings,
        }},
        upsert=True,
    )
 
 
def remove_group_admin(chat_id, user_id):
    _db.group_admins.delete_one({"chat_id": chat_id, "user_id": user_id})
 
 
def get_group_admin(chat_id, user_id):
    return _db.group_admins.find_one({"chat_id": chat_id, "user_id": user_id})
 
 
# ---------- Language helpers ----------
 
def get_user_language(user_id):
    doc = _db.user_prefs.find_one({"user_id": user_id})
    return doc["language"] if doc else "en"
 
 
def has_user_language(user_id):
    """True agar is user ne khud apni language choose ki hai (welcome button se)."""
    return _db.user_prefs.find_one({"user_id": user_id}) is not None
 
 
def get_effective_language(chat_id, user_id):
    """
    User ne agar khud apni language choose ki hai to wahi return karta hai,
    warna group ki default language.
    """
    if has_user_language(user_id):
        return get_user_language(user_id)
    return get_group(chat_id)["default_language"]
 
 
def set_user_language(user_id, lang_code):
    _db.user_prefs.update_one(
        {"user_id": user_id}, {"$set": {"language": lang_code}}, upsert=True
    )
 
 
# ---------- Warning helpers ----------
 
def add_warning(chat_id, user_id):
    _db.warnings.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
    )
    doc = _db.warnings.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc["count"]
 
 
def reset_warnings(chat_id, user_id):
    _db.warnings.delete_one({"chat_id": chat_id, "user_id": user_id})
 
 
# ---------- Block helpers ----------
 
def block_user(chat_id, user_id, duration_seconds):
    until = int(time.time()) + duration_seconds
    _db.blocked_users.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"until": until}},
        upsert=True,
    )
 
 
def unblock_user(chat_id, user_id):
    _db.blocked_users.delete_one({"chat_id": chat_id, "user_id": user_id})
 
 
def is_blocked(chat_id, user_id):
    doc = _db.blocked_users.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        return False
    if doc["until"] < int(time.time()):
        _db.blocked_users.delete_one({"chat_id": chat_id, "user_id": user_id})
        return False
    return True
