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
    """Text nikalta hai given language mein, placeholders {name} wagairah fill karke."""
    data = _load(lang_code)
    text = data.get(key) or _load("en").get(key, key)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text
