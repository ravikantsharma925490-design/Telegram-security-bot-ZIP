"""
Anti-forward — group mein owner/admin ke alawa koi bhi forward kare to message
turant delete. Koi warning, koi restrict, koi message nahi — sirf delete.
"""

from telegram import Update
from telegram.ext import ContextTypes

from handlers.admin import is_authorized_admin

# Telegram ka "Anonymous Admin" (group ke naam se bhejne wala admin) ka user id
_ANONYMOUS_ADMIN_ID = 1087968824


def _is_forwarded(message) -> bool:
    return (
        getattr(message, "forward_origin", None) is not None
        or getattr(message, "forward_date", None) is not None
    )


async def anti_forward_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    True  = aage process hone do (forward nahi hai, ya bhejne wala owner/admin hai).
    False = forward tha aur delete ho gaya.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user:
        return True

    if not _is_forwarded(message):
        return True

    # Linked channel ka post jo group mein apne-aap forward hota hai -> chhodo
    if getattr(message, "is_automatic_forward", False):
        return True

    # Bots, anonymous admin, ya channel ke naam se bheja gaya message -> chhodo
    if user.is_bot or user.id == _ANONYMOUS_ADMIN_ID or message.sender_chat:
        return True

    # Owner / admin (Telegram ke admin ya /addadmin wale) -> chhodo
    if await is_authorized_admin(chat.id, user.id, context=context):
        return True

    # Normal member ka forward -> sirf delete
    try:
        await message.delete()
    except Exception:
        pass
    return False
