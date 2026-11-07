"""
Daily Tag — roz fixed time par group ke saare (saved) members ko 5-5 ke message mein tag karta hai.
 
- Default: ON, subah 6:00 baje (India time, IST). /settagtime se group ka time badal sakte hain.
- /settings mein "Daily Tag" ON/OFF button (sirf owner / admins).
- Bot khud time nahi dekhta — bahar se cron (cron-job.org) har minute ye URL bulata hai:
      https://<tumhara-vercel-domain>/api/daily-tag?key=<WEBHOOK_SECRET>
- Bot apni taraf se koi delay nahi rakhta, jitni tezi se ho sake messages bhejta hai.
  Telegram "ruko" (429) bole to utna ruk kar (ya agli cron call mein) wahin se aage chalta hai.
- Progress (kitne members tag ho chuke) MongoDB mein save hota hai, to Vercel beech mein ruk jaye
  tab bhi agli call wahin se chalegi, kisi ko do baar tag nahi hoga.
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
DEFAULT_TAG_TIME = "06:00"
PER_MESSAGE = 5            # ek message mein itne members
WINDOW_MINUTES = 180       # tag time ke itne minute baad tak naya tag shuru ho sakta hai (late ON karne par achanak raat ko tag na ho)
MAX_PARALLEL_GROUPS = 8    # ek saath itne groups
 
 
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
 
async def settagtime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/settagtime <time> — Daily Tag ka time (IST). Sirf owner / admins."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("ℹ️ Ye command group mein use karo.")
        return
    if not await guard_or_warn(update, context):
        return
 
    group = db.get_group(chat.id)
    current = group.get("tag_time") or DEFAULT_TAG_TIME
 
    if not context.args:
        state = "ON ✅" if group.get("daily_tag", 1) else "OFF ❌ (/settings se ON karo)"
        await update.message.reply_text(
            f"🌅 Daily Tag: {state}\n"
            f"⏰ Abhi ka time: {format_12h(current)} (IST)\n\n"
            "Time badalne ke liye:\n"
            "`/settagtime 6:30`  ya  `/settagtime 6:30 PM`  ya  `/settagtime 18:30`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
 
    new_time = parse_time(" ".join(context.args))
    if not new_time:
        await update.message.reply_text(
            "❌ Time samajh nahi aaya. Aise likho:\n"
            "`/settagtime 6:30`  ya  `/settagtime 6:30 PM`  ya  `/settagtime 18:30`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
 
    db.update_group(chat.id, tag_time=new_time)
    extra = "" if group.get("daily_tag", 1) else "\n⚠️ Daily Tag abhi OFF hai, /settings se ON karo."
    await update.message.reply_text(
        f"✅ Daily Tag ka time set: {format_12h(new_time)} (IST). Ab roz isi time par sabko tag hoga.{extra}"
    )
 
 
# ---------- tag message banana ----------
 
def _mention(user_doc) -> str:
    name = (user_doc.get("name") or "").strip() or "member"
    name = html.escape(name[:25])
    return f'<a href="tg://user?id={user_doc["user_id"]}">{name}</a>'
 
 
# Pehle message ke upar aane wala text (baaki messages mein sirf 5 naam). Yahin se badal sakte ho.
TAG_HEADER = (
    "꧁𓊈𒆜🦚ཞ།ધે ཞ།ધે🦚𒆜𓊉꧂\n\n"
    "♡᭄ꦿGOOD MORNING ♡\n\n"
    "ONLINE AAO, KAHAN HO SAB LOG?"
)
 
 
def _build_text(users, first: bool) -> str:
    body = " ".join(_mention(u) for u in users)
    if first:
        return f"{html.escape(TAG_HEADER)}\n\n{body}"
    return body
 
 
# ---------- ek group ka kaam ----------
 
async def _process_group(bot, chat_id, today, deadline, summary):
    """Ek group ke 5-5 members tag karta hai (eligibility run_daily_tag pehle hi check kar chuka hota hai)."""
    # Lock (do cron calls ek saath ek hi group par na chalein) + RetryAfter wait
    lock_for = max(deadline - time.time(), 1) + 5
    st = db.claim_tag_state(chat_id, today, lock_for)
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
                _build_text(users, first=(sent_msgs == 0)),
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
            log.warning("daily tag: chat %s par send nahi ho paya (%s) - aaj ke liye band", chat_id, e)
            finished = True
            break
        except TelegramError as e:
            log.warning("daily tag: chat %s TelegramError %s", chat_id, e)
            next_try = time.time() + 20
            break
 
        last_id = users[-1]["user_id"]
        sent_msgs += 1
        tagged += len(users)
        # Har message ke baad progress save: crash / timeout par bhi dobara tag nahi hoga
        db.save_tag_progress(chat_id, last_id=last_id, sent_msgs=sent_msgs, tagged=tagged)
 
    db.finish_tag_run(chat_id, today, last_id, sent_msgs, tagged, finished, next_try)
    summary["messages"] += sent_msgs - st.get("sent_msgs", 0)
    summary["tagged"] += tagged - st.get("tagged", 0)
    if finished:
        summary["finished_groups"] += 1
        log.info("daily tag done: chat=%s tagged=%s messages=%s", chat_id, tagged, sent_msgs)
        if tagged == 0:
            log.warning("daily tag: chat %s mein saved member nahi mila (ya send fail hua) - aaj ke liye done maana gaya", chat_id)
 
 
# ---------- cron entry point ----------
 
async def run_daily_tag(bot):
    """Cron har minute isko bulata hai (app.py ka /api/daily-tag). Kitna kaam hua uska chhota summary deta hai."""
    started = time.time()
    deadline = started + BROADCAST_BATCH_SECONDS
    now = _now_ist()
    today = now.strftime("%Y-%m-%d")
    now_min = now.hour * 60 + now.minute
 
    # Sirf 2 DB queries: Daily Tag ON wale groups + unki aaj ki state. Baaki groups par kuch nahi chalta.
    groups = db.list_daily_tag_groups()
    states = db.get_tag_states([g["chat_id"] for g in groups])
 
    due = []
    done_today = 0
    for g in groups:
        chat_id = g["chat_id"]
        st = states.get(chat_id)
        same_day = bool(st) and st.get("date") == today
        if same_day and st.get("status") == "done":
            done_today += 1
            continue
        if same_day and st.get("status") == "running":
            due.append(chat_id)  # shuru ho chuka hai, poora hone tak chalao
            continue
        try:
            start_min = _to_minutes(g.get("tag_time") or DEFAULT_TAG_TIME)
        except Exception:
            start_min = _to_minutes(DEFAULT_TAG_TIME)
        if start_min <= now_min < start_min + WINDOW_MINUTES:
            due.append(chat_id)
 
    summary = {"messages": 0, "tagged": 0, "finished_groups": 0}
    sem = asyncio.Semaphore(MAX_PARALLEL_GROUPS)
 
    async def _one(chat_id):
        async with sem:
            try:
                await _process_group(bot, chat_id, today, deadline, summary)
            except Exception:
                log.exception("daily tag failed for chat %s", chat_id)
 
    if due:
        await asyncio.gather(*[_one(cid) for cid in due])
    return {
        "ist": now.strftime("%H:%M"), "date": today,
        "groups_with_tag_on": len(groups), "done_today": done_today, "due_groups": len(due),
        **summary, "seconds": round(time.time() - started, 1),
    }
 
