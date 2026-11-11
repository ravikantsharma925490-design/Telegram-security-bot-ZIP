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
    """Language file padhta hai. File na mile ya kharab (toot-phoot) ho to khaali dict deta hai (crash nahi)."""
    if lang_code in _cache:
        return _cache[lang_code]
    path = os.path.join(_LANG_DIR, f"{lang_code}.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    _cache[lang_code] = data
    return data
 
 
def t(lang_code, key, **kwargs):
    """
    Text nikalta hai, group ki chuni hui language mein. Us language mein key ya poori file
    na ho (ya file kharab ho) to us key ke liye English (en) text deta hai.
    """
    text = _load(lang_code or "en").get(key)
    if text is None:
        text = _load("en").get(key, key)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text
