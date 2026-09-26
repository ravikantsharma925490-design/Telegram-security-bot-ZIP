"""
Language helper — JSON files se text uthata hai, agar key ya language
missing ho to automatically English (en) par fallback karta hai.
"""
 
import json
import os
 
_LANG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "languages")
_cache = {}
 
LANGUAGE_NAMES = {
    "en": "🇬🇧 English", "hi": "🇮🇳 Hindi", "es": "🇪🇸 Spanish", "ar": "🇸🇦 Arabic",
    "fr": "🇫🇷 French", "de": "🇩🇪 German", "ru": "🇷🇺 Russian", "bn": "🇧🇩 Bengali",
    "ur": "🇵🇰 Urdu", "id": "🇮🇩 Indonesian", "tr": "🇹🇷 Turkish", "pt": "🇵🇹 Portuguese",
    "ja": "🇯🇵 Japanese", "ko": "🇰🇷 Korean", "zh": "🇨🇳 Chinese",
}
 
 
def _load(lang_code):
    if lang_code in _cache:
        return _cache[lang_code]
    path = os.path.join(_LANG_DIR, f"{lang_code}.json")
    if not os.path.exists(path):
        lang_code = "en"
        path = os.path.join(_LANG_DIR, "en.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _cache[lang_code] = data
    return data
 
 
def t(lang_code, key, **kwargs):
    """Text nikalta hai us language mein jo di gayi hai; missing key/language par English fallback."""
    data = _load(lang_code or "en")
    text = data.get(key)
    if text is None:
        text = _load("en").get(key, key)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text
 
 
_BOLD_MAP = {}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _BOLD_MAP[_c] = chr(0x1D400 + _i)          # 𝐀-𝐙
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _BOLD_MAP[_c] = chr(0x1D41A + _i)          # 𝐚-𝐳
for _i, _c in enumerate("0123456789"):
    _BOLD_MAP[_c] = chr(0x1D7CE + _i)          # 𝟎-𝟗
 
 
def bold_name(name: str) -> str:
    """Naam ko Unicode Mathematical Bold style mein convert karta hai (jaise 𝐑𝐚𝐯𝐢).
    Jo characters is style mein available nahi hain (emoji, special symbols,
    non-Latin scripts) unhe waisa hi rehne deta hai."""
    return "".join(_BOLD_MAP.get(ch, ch) for ch in name)
 
 
def time_greeting() -> str:
    """Server ke current time ke hisaab se 'Good Morning/Afternoon/Evening/Night' return karta hai."""
    import datetime
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "GOOD MORNING"
    if 12 <= hour < 17:
        return "GOOD AFTERNOON"
    if 17 <= hour < 21:
        return "GOOD EVENING"
    return "GOOD NIGHT"
 
 
