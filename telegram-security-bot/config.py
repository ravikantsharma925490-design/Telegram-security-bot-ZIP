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
DEFAULT_REQUIRED_CHANNEL = "cinemagyanupdates"
DEFAULT_REQUIRED_GROUP = "english_chatting_USA18"
 
# Link/username spam bhejne par kitne din ke liye restrict karna hai
LINK_SPAM_RESTRICT_DAYS = 3
