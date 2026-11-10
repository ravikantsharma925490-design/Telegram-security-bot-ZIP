"""
Daily Tag — roz fixed time par group ke saare (saved) members ko 5-5 ke message mein tag karta hai.
 
5 slots (sab default ON, time India time / IST mein):
    🌅 Morning   6:00 AM     ☀️ Afternoon 12:00 PM     🌆 Evening 6:00 PM
    🌙 Night    10:00 PM     🌌 Midnight  12:00 AM
 
- /settings mein har slot ka alag ON/OFF button (sirf owner / admins).
- Time badalne ke liye:  /settagtime night 11:00 PM   (slot ka naam na likho to Morning ka time badlega)
- Bot khud time nahi dekhta — bahar se cron (cron-job.org) har minute ye URL bulata hai:
      https://<tumhara-vercel-domain>/api/daily-tag?key=<WEBHOOK_SECRET>
- Bot apni taraf se koi delay nahi rakhta, jitni tezi se ho sake messages bhejta hai.
  Telegram "ruko" (429) bole to utna ruk kar (ya agli cron call mein) wahin se aage chalta hai.
- Progress (kitne members tag ho chuke) har (group, slot) ke liye MongoDB mein save hota hai, to Vercel beech mein
  ruk jaye tab bhi agli call wahin se chalegi, kisi ko do baar tag nahi hoga.
"""
 
import asyncio
import html
import logging
import re
import time
from datetime import datetime, timedelta, timezone
 
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes
 
import database as db
from config import BROADCAST_BATCH_SECONDS
from handlers.admin import guard_or_warn
 
log = logging.getLogger(__name__)
 
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_TAG_TIME = "06:00"  # Morning ka default (settings.py isko import karta hai)
PER_MESSAGE = 5            # ek message mein itne members
WINDOW_MINUTES = 180       # slot time ke itne minute baad tak naya tag shuru ho sakta hai (late ON karne par achanak tag na ho)
MAX_PARALLEL_GROUPS = 8    # ek saath itne (group, slot) kaam
 
# ---------- slots ----------
# on  = DB mein ON/OFF ka field (Morning ke purane field naam wahi rakhe hain, to purani setting bani rahegi)
# time = DB mein time ka field
DESIGN_LINE = "꧁𓊈𒆜🦚ཞ།ધે ཞ།ધે🦚𒆜𓊉꧂"
SLOTS = {
    "morning": {
        "label": "🌅 Morning", "on": "daily_tag", "time": "tag_time", "default": "06:00",
        "title": "♡᭄ꦿGOOD MORNING ♡", "line": "ONLINE AAO, KAHAN HO SAB LOG?",
    },
    "afternoon": {
        "label": "☀️ Afternoon", "on": "daily_tag_afternoon", "time": "tag_time_afternoon", "default": "12:00",
        "title": "GOOD AFTERNOON ☀️", "line": "ONLINE AAO, KAHAN HO SAB LOG?",
    },
    "evening": {
        "label": "🌆 Evening", "on": "daily_tag_evening", "time": "tag_time_evening", "default": "18:00",
        "title": "GOOD EVENING 🌆", "line": "ONLINE AAO, KAHAN HO SAB LOG?",
    },
    "night": {
        "label": "🌙 Night", "on": "daily_tag_night", "time": "tag_time_night", "default": "22:00",
        "title": "GOOD NIGHT 🌙", "line": "SO JAO SAB LOG, KAL MILTE HAIN!",
    },
    "midnight": {
        "label": "🌌 Midnight", "on": "daily_tag_midnight", "time": "tag_time_midnight", "default": "00:00",
        "title": "MIDNIGHT 🌌", "line": "ABHI TAK JAAG RAHE HO? ONLINE AAO!",
    },
}
SLOT_ORDER = ["morning", "afternoon", "evening", "night", "midnight"]
SLOT_ALIASES = {"mid": "midnight"}
 
 
def slot_header(slot: str) -> str:
    s = SLOTS[slot]
    return f"{DESIGN_LINE}\n\n{s['title']}\n\n{s['line']}"
 
 
def slot_is_on(group: dict, slot: str) -> bool:
    return bool(group.get(SLOTS[slot]["on"], 1))  # field na ho to default ON
 
 
def slot_time(group: dict, slot: str) -> str:
    return group.get(SLOTS[slot]["time"]) or SLOTS[slot]["default"]
 
 
# ---------- time helpers ----------
 
def _now_ist():
    return datetime.now(timezone.utc).astimezone(IST)
 
 
def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)
 
 
def format_12h(hhmm: str) -> str:
    h, m = hhmm.split(":")
    h, m = int(h), int(m)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"
 
 
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.IGNORECASE)
 
 
def parse_time(text: str):
    """'6:30', '6:30 PM', '6pm', '18:30', '6' -> 'HH:MM' (24h). Galat ho to None."""
    m = _TIME_RE.match((text or "").strip())
    if not m:
        return None
    h = int(m.group(1))
    minute = int(m.group(2) or 0)
    suffix = (m.group(3) or "").lower()
    if minute > 59:
        return None
    if suffix:
        if not 1 <= h <= 12:
            return None
        h = h % 12
        if suffix == "pm":
            h += 12
    elif h > 23:
        return None
    return f"{h:02d}:{minute:02d}"
 
 
# ---------- /settagtime ----------
 
_USAGE = (
    "`/settagtime morning 6:30 AM`\n"
    "`/settagtime afternoon 12:30 PM`\n"
    "`/settagtime evening 6 PM`\n"
    "`/settagtime night 10:30 PM`\n"
    "`/settagtime midnight 12:00 AM`\n"
    "(Slot ka naam na likho to Morning ka time badlega, jaise `/settagtime 6:30`)"
)
 
 
def _slots_overview(group: dict) -> str:
    lines = []
    for slot in SLOT_ORDER:
        state = "ON ✅" if slot_is_on(group, slot) else "OFF ❌"
        lines.append(f"{SLOTS[slot]['label']}: {format_12h(slot_time(group, slot))} (IST) — {state}")
    return "\n".join(lines)
 
 
async def settagtime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/settagtime [slot] <time> — Daily Tag slot ka time (IST). Sirf owner / admins."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("ℹ️ Ye command group mein use karo.")
        return
    if not await guard_or_warn(update, context):
        return
 
    group = db.get_group(chat.id)
 
    if not context.args:
        await update.message.reply_text(
            "🌅 Daily Tag ke slots:\n" + _slots_overview(group) +
            "\n\nON/OFF karne ke liye /settings kholo. Time badalne ke liye:\n" + _USAGE,
            parse_mode=ParseMode.MARKDOWN,
        )
        return
 
    args = list(context.args)
    first = args[0].lower()
    first = SLOT_ALIASES.get(first, first)
    if first in SLOTS:
        slot = first
        time_text = " ".join(args[1:])
    else:
        slot = "morning"
        time_text = " ".join(args)
 
    new_time = parse_time(time_text)
    if not new_time:
        await update.message.reply_text(
            "❌ Time samajh nahi aaya. Aise likho:\n" + _USAGE,
            parse_mode=ParseMode.MARKDOWN,
        )
        return
 
    db.update_group(chat.id, **{SLOTS[slot]["time"]: new_time})
    extra = "" if slot_is_on(group, slot) else f"\n⚠️ {SLOTS[slot]['label']} abhi OFF hai, /settings se ON karo."
    await update.message.reply_text(
        f"✅ {SLOTS[slot]['label']} Tag ka time set: {format_12h(new_time)} (IST). "
        f"Ab roz isi time par sabko tag hoga.{extra}"
    )
 
 
# ---------- tag message banana ----------
 
def _mention(user_doc) -> str:
    name = (user_doc.get("name") or "").strip() or "member"
    name = html.escape(name[:25])
    return f'<a href="tg://user?id={user_doc["user_id"]}">{name}</a>'
 
 
def _build_text(users, slot: str) -> str:
    """Har 5-member message ke upar slot ka design + text, neeche 5 naam."""
    body = " ".join(_mention(u) for u in users)
    return f"{html.escape(slot_header(slot))}\n\n{body}"
 
 
# ---------- ek group ke ek slot ka kaam ----------
 
async def _process_slot(bot, chat_id, slot, slot_date, deadline, summary):
    """Ek group ke ek slot ke 5-5 members tag karta hai (eligibility run_daily_tag pehle hi check kar chuka hota hai)."""
    state_id = f"{chat_id}:{slot}"
 
    # Lock (do cron calls ek saath ek hi slot par na chalein) + RetryAfter wait
    lock_for = max(deadline - time.time(), 1) + 5
    st = db.claim_tag_state(state_id, slot_date, lock_for)
    if st is None:
        return
 
    last_id = st.get("last_id", 0)
    sent_msgs = st.get("sent_msgs", 0)
    tagged = st.get("tagged", 0)
    finished = False
    next_try = 0.0
 
    while time.time() < deadline - 1.0:
        users = db.list_group_users_after(chat_id, last_id, PER_MESSAGE)
        if not users:
            finished = True
            break
        try:
            await bot.send_message(
                chat_id,
                _build_text(users, slot),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except RetryAfter as e:
            wait = e.retry_after
            wait = wait.total_seconds() if hasattr(wait, "total_seconds") else float(wait)
            if time.time() + wait < deadline - 1.0:
                await asyncio.sleep(wait + 0.2)
                continue  # isi batch ko dobara bhejo
            next_try = time.time() + wait + 0.5
            break
        except (Forbidden, BadRequest) as e:
            # Bot group se hata diya gaya / message bhejne ki permission nahi
            log.warning("daily tag: chat %s (%s) par send nahi ho paya (%s) - is slot ke liye band", chat_id, slot, e)
            finished = True
            break
        except TelegramError as e:
            log.warning("daily tag: chat %s (%s) TelegramError %s", chat_id, slot, e)
            next_try = time.time() + 20
            break
 
        last_id = users[-1]["user_id"]
        sent_msgs += 1
        tagged += len(users)
        # Har message ke baad progress save: crash / timeout par bhi dobara tag nahi hoga
        db.save_tag_progress(state_id, last_id=last_id, sent_msgs=sent_msgs, tagged=tagged)
 
    db.finish_tag_run(state_id, slot_date, last_id, sent_msgs, tagged, finished, next_try)
    summary["messages"] += sent_msgs - st.get("sent_msgs", 0)
    summary["tagged"] += tagged - st.get("tagged", 0)
    if finished:
        summary["finished"] += 1
        log.info("daily tag done: chat=%s slot=%s tagged=%s messages=%s", chat_id, slot, tagged, sent_msgs)
        if tagged == 0:
            log.warning("daily tag: chat %s (%s) mein saved member nahi mila (ya send fail hua) - done maana gaya", chat_id, slot)
 
 
# ---------- cron entry point ----------
 
async def run_daily_tag(bot):
    """Cron har minute isko bulata hai (app.py ka /api/daily-tag). Kitna kaam hua uska chhota summary deta hai."""
    started = time.time()
    deadline = started + BROADCAST_BATCH_SECONDS
    now = _now_ist()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    now_min = now.hour * 60 + now.minute
 
    # Sirf 2 DB queries: saare groups + unki states. Jis slot ka time nahi aaya uspar kuch nahi chalta.
    groups = db.list_daily_tag_groups()
    ids = []
    for g in groups:
        for slot in SLOT_ORDER:
            ids.append(f"{g['chat_id']}:{slot}")
        ids.append(g["chat_id"])  # purani (sirf Morning wali) state, double tag se bachne ke liye
    states = db.get_tag_states(ids)
 
    due = []
    done = 0
    slots_on = 0
    for g in groups:
        chat_id = g["chat_id"]
        for slot in SLOT_ORDER:
            if not slot_is_on(g, slot):
                continue
            slots_on += 1
            try:
                start_min = _to_minutes(slot_time(g, slot))
            except Exception:
                start_min = _to_minutes(SLOTS[slot]["default"])
 
            # Slot ki "date": raat ke slot ka tag aadhi raat ke baad bhi usi slot ka maana jata hai
            slot_date = today if now_min >= start_min else yesterday
            elapsed = (now_min - start_min) % 1440
 
            st = states.get(f"{chat_id}:{slot}")
            same_day = bool(st) and st.get("date") == slot_date
            if not st and slot == "morning":
                legacy = states.get(chat_id)
                if legacy and legacy.get("date") == slot_date:
                    done += 1
                    continue
            if same_day and st.get("status") == "done":
                done += 1
                continue
            if same_day and st.get("status") == "running":
                due.append((chat_id, slot, slot_date))  # shuru ho chuka hai, poora hone tak chalao
                continue
            if elapsed < WINDOW_MINUTES:
                due.append((chat_id, slot, slot_date))
 
    summary = {"messages": 0, "tagged": 0, "finished": 0}
    sem = asyncio.Semaphore(MAX_PARALLEL_GROUPS)
 
    async def _one(chat_id, slot, slot_date):
        async with sem:
            try:
                await _process_slot(bot, chat_id, slot, slot_date, deadline, summary)
            except Exception:
                log.exception("daily tag failed for chat %s (%s)", chat_id, slot)
 
    if due:
        await asyncio.gather(*[_one(c, s, d) for c, s, d in due])
    return {
        "ist": now.strftime("%H:%M"), "date": today,
        "groups": len(groups), "slots_on": slots_on, "done_today": done, "due": len(due),
        **summary, "seconds": round(time.time() - started, 1),
    }
 
