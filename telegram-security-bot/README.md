# 🤖 Telegram Security Bot

Aapke group ke liye stylish, feature-rich security & moderation bot.

## 🚀 Setup (steps)

1. **Python install** karein (3.10+ recommended).
2. Ye project folder kisi bhi server/PC par rakhein (VPS best rahega taaki bot 24x7 chale).
3. Terminal mein:
   ```
   pip install -r requirements.txt
   ```
4. [@BotFather](https://t.me/BotFather) se bot bana kar **token** le lein.
5. Token set karein:
   - Linux/Mac: `export BOT_TOKEN="yaha_apna_token"`
   - Windows (PowerShell): `$env:BOT_TOKEN="yaha_apna_token"`
   - Ya seedha `config.py` mein `BOT_TOKEN` variable mein paste kar dein.
6. **MongoDB** ready rakhein — do options hain:
   - **Local**: MongoDB install karke chala dein (default `mongodb://localhost:27017` already config mein set hai).
   - **MongoDB Atlas (free cloud)**: [mongodb.com/atlas](https://www.mongodb.com/atlas) par free cluster bana kar connection string le lein, phir set karein:
     - `export MONGO_URI="mongodb+srv://user:pass@cluster.mongodb.net"`
     - Ya `config.py` mein `MONGO_URI` variable mein paste kar dein.
7. Bot chalayein:
   ```
   python main.py
   ```
7. Bot ko apne group mein **admin** banayein — permissions: delete messages, ban users, restrict/mute users, invite users (join requests ke liye).
8. Group mein `/start` bhejein — setup automatic ho jayega.
9. `/settings` se sab features ON/OFF kar sakte hain (sirf owner/admin).

## ⚙️ Force Join set karna

`/settings` mein "Force Join" ON karein, phir database mein (ya ek chhota admin command bana kar) `required_channel` aur `required_group` set karein apne channel/group ke `@username` ke saath. (Chaahein to bata dein, main iske liye ek seedha `/setchannel` aur `/setgroup` command bhi add kar dunga.)

## 🔞 18+ Media Detection

`handlers/media_filter.py` mein ek **hook** diya gaya hai (`check_media_safety`). Abhi ye function hamesha "safe" return karta hai kyunki real NSFW-detection ke liye ek third-party API/model (jaise Sightengine, Google Cloud Vision SafeSearch, ya koi open-source classifier) chahiye hoti hai jiski apni API key hoti hai. Jab aapke paas wo ho, bas us function mein API call daal dein.

## 📁 Project Structure

```
main.py                  → bot start point, sab handlers register
config.py                → token & default settings
database.py               → MongoDB (per-group config, warnings, admins, language)
handlers/
  setup.py                → /start, /help
  settings.py              → /settings menu
  admin.py                  → owner/admin control, ban/mute/warn, unauthorized protection
  moderation.py             → anti-spam, flood protection, bad-word filter
  media_filter.py           → 18+ media detection hook
  force_join.py             → required channel/group verification
  welcome.py                → welcome message, language button, auto-accept join requests
  logger.py                  → events ko log channel mein bhejta hai
languages/                → en, hi (full) + 13 aur languages (English text placeholder, translate kar lein)
utils/lang.py              → language text lookup helper
```

## 📝 Logging

Group ke `log_chat_id` ko ek private channel/group ke ID par set kar dein (database mein ya ek `/setlogchannel` command add karke) — bot sab important events (join/leave/warning/mute/block/delete/etc.) wahan bhejega.

## ➕ Aage kya add kiya ja sakta hai

- `/setchannel`, `/setgroup`, `/setlogchannel` jaise seedhe commands (abhi DB directly edit karni padegi)
- Real 18+ media detection API
- Baaki 13 languages ka actual translation (abhi English text hai placeholder ke taur par)
