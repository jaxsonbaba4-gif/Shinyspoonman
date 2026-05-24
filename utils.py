import time
import logging
from typing import Dict
from telebot import types
from telebot.apihelper import ApiTelegramException

logger = logging.getLogger(__name__)

user_last_request: Dict[int, float] = {}
RATE_LIMIT = 3

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    if user_id in user_last_request:
        if now - user_last_request[user_id] < RATE_LIMIT:
            return True
    user_last_request[user_id] = now
    return False

async def safe_edit(bot, chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    """Edit message silently ignoring 'not modified' errors"""
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            pass  # ignore silently
        else:
            logger.error(f"Edit failed: {e}")

async def safe_answer(bot, callback_id, text=None, show_alert=False):
    """Answer callback query safely"""
    try:
        await bot.answer_callback_query(callback_id, text=text, show_alert=show_alert)
    except ApiTelegramException as e:
        if "query is too old" in str(e):
            pass
        else:
            logger.error(f"Answer callback failed: {e}")
