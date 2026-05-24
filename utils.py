import time
from typing import Dict
from telebot import types

user_last_request: Dict[int, float] = {}
RATE_LIMIT = 3  # seconds

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    if user_id in user_last_request:
        if now - user_last_request[user_id] < RATE_LIMIT:
            return True
    user_last_request[user_id] = now
    return False

def create_inline_keyboard(buttons: list, row_width: int = 2) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=row_width)
    for text, data in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=data))
    return markup

def build_pagination_keyboard(page: int, total_pages: int, prefix: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=5)
    if page > 0:
        markup.add(types.InlineKeyboardButton("⬅️", callback_data=f"{prefix}_page_{page-1}"))
    markup.add(types.InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="none"))
    if page < total_pages - 1:
        markup.add(types.InlineKeyboardButton("➡️", callback_data=f"{prefix}_page_{page+1}"))
    return markup
