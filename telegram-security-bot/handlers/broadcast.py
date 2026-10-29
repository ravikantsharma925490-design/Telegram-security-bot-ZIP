"""
/broadcast — sirf bot owner (OWNER_ID), private chat mein.

  /broadcast aapka text           -> text sabko jayega
  (kisi message par reply) /broadcast -> wo message (photo/video/formatting ke saath) sabko jayega

Target: bot ke saare groups + saare users jinhone bot ko private mein /start / message kiya.
Pehle preview + "Send" confirm aata hai. Serverless (Vercel) ke time limit ke liye kaam chhote
hisso (BROADCAST_BATCH_SECONDS) mein hota hai; baaki bacha ho to "Continue" button aata hai.
"""

import asyncio
import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, Forbidden, TelegramError
from telegram.ext import ContextTypes

import database as db
from config import BROADCAST_BATCH_SECONDS
from handlers.owner import _is_bot_owner

log = logging.getLogger(__name__)

_SEND_GAP = 0.05      # do messages ke beech gap (Telegram flood limit se bachne ke liye)
_SAVE_EVERY = 20      # itne messages ke baad progress DB mein save


def _buttons(*pairs):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in pairs]])


def _report(job, done):
    total = len(job["targets"])
    head = "✅ Broadcast complete" if done else f"⏳ Broadcast: {job['pos']}/{total} bheja gaya"
    return (
        f"{head}\n\n"
        f"👥 Groups: {job['sent_g']} gaya, {job['fail_g']} fail\n"
        f"🙋 Users: {job['sent_u']} gaya, {job['fail_u']} fail, "
        f"{job['removed_u']} ne bot block kiya (list se hata diye)"
    )


async def _send_one(context, job, chat_id):
    """'ok' / 'forbidden' (blocked/kicked) / 'fail'."""
    for _ in range(2):
        try:
            if job.get("src_message_id"):
                await context.bot.copy_message(chat_id, job["src_chat_id"], job["src_message_id"])
            else:
                await context.bot.send_message(chat_id, job["text"])
            return "ok"
        except RetryAfter as e:
            wait = e.retry_after
            wait = wait.total_seconds() if hasattr(wait, "total_seconds") else wait
            await asyncio.sleep(min(float(wait), 5) + 0.5)
        except Forbidden:
            return "forbidden"
        except TelegramError:
            return "fail"
        except Exception:
            log.exception("broadcast send failed for %s", chat_id)
            return "fail"
    return "fail"


async def _run_batch(context, job):
    """Time budget tak bhejta hai. True = sab ho gaya."""
    start = time.monotonic()
    targets = job["targets"]
    pos = job["pos"]
    since_save = 0

    def _stats():
        return {k: job[k] for k in ("sent_g", "fail_g", "sent_u", "fail_u", "removed_u")}

    while pos < len(targets):
        if time.monotonic() - start >= BROADCAST_BATCH_SECONDS:
            break
        kind, cid = targets[pos]
        result = await _send_one(context, job, cid)
        if kind == "g":
            job["sent_g" if result == "ok" else "fail_g"] += 1
        else:
            if result == "ok":
                job["sent_u"] += 1
            elif result == "forbidden":
                job["removed_u"] += 1
                db.remove_bot_user(cid)
            else:
                job["fail_u"] += 1
        pos += 1
        since_save += 1
        if since_save >= _SAVE_EVERY:
            db.update_broadcast_job(pos=pos, **_stats())
            since_save = 0
        await asyncio.sleep(_SEND_GAP)

    job["pos"] = pos
    done = pos >= len(targets)
    db.update_broadcast_job(
        pos=pos, status="done" if done else "running", locked_until=0, **_stats()
    )
    return done


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not _is_bot_owner(user.id):
        return  # baaki logon ko koi reply nahi

    job = {
        "_id": "current", "status": "pending", "pos": 0,
        "sent_g": 0, "fail_g": 0, "sent_u": 0, "fail_u": 0, "removed_u": 0,
    }
    if msg.reply_to_message:
        job["src_chat_id"] = msg.chat_id
        job["src_message_id"] = msg.reply_to_message.message_id
        preview = "(jis message par reply kiya, wahi jayega)"
    else:
        parts = (msg.text or "").split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            await msg.reply_text(
                "📢 Broadcast\n\n"
                "• /broadcast aapka text\n"
                "• ya kisi message (text/photo/video) par reply karke /broadcast"
            )
            return
        job["text"] = parts[1].strip()
        preview = job["text"][:300]

    groups = db.list_group_ids()
    users = [u for u in db.list_bot_user_ids() if u != user.id]
    job["targets"] = [["g", g] for g in groups] + [["u", u] for u in users]
    if not job["targets"]:
        await msg.reply_text("Abhi koi group ya user nahi mila jise bheja ja sake.")
        return

    db.save_broadcast_job(job)
    await msg.reply_text(
        f"📢 Broadcast ready\n\n{preview}\n\n"
        f"👥 Groups: {len(groups)}\n🙋 Users: {len(users)}\n\nBhejna hai?",
        reply_markup=_buttons(("✅ Send", "bc_send"), ("❌ Cancel", "bc_cancel")),
    )


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_bot_owner(query.from_user.id):
        await query.answer()
        return

    if query.data == "bc_cancel":
        db.delete_broadcast_job()
        await query.answer("Cancel")
        try:
            await query.edit_message_text("❌ Broadcast cancel kar diya.")
        except Exception:
            pass
        return

    statuses = ["pending"] if query.data == "bc_send" else ["running"]
    job = db.claim_broadcast_job(statuses, lock_seconds=BROADCAST_BATCH_SECONDS + 15)
    if not job:
        await query.answer("Ye pehle se chal raha hai ya mila nahi.", show_alert=True)
        return

    await query.answer("Bhej raha hu…")
    done = await _run_batch(context, job)
    try:
        await query.edit_message_text(
            _report(job, done),
            reply_markup=None if done else _buttons(("▶️ Continue", "bc_continue"), ("❌ Cancel", "bc_cancel")),
        )
    except Exception:
        pass
