import asyncio
import time
from typing import Dict
from telebot import types
from html import escape as html_escape

# Simple in‑memory rate limiter
user_last_request: Dict[int, float] = {}
RATE_LIMIT = 3  # seconds

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    if user_id in user_last_request:
        if now - user_last_request[user_id] < RATE_LIMIT:
            return True
    user_last_request[user_id] = now
    return False

def chunk_text(text: str, chunk_size: int = 4096) -> list:
    """Split text into Telegram‑safe chunks."""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def create_inline_keyboard(buttons: list, row_width: int = 2) -> types.InlineKeyboardMarkup:
    """Create an inline keyboard from a list of (text, callback_data) tuples."""
    markup = types.InlineKeyboardMarkup(row_width=row_width)
    for text, data in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=data))
    return markup

def build_pagination_keyboard(page: int, total_pages: int, prefix: str) -> types.InlineKeyboardMarkup:
    """Generic pagination buttons."""
    markup = types.InlineKeyboardMarkup(row_width=5)
    buttons = []
    if page > 0:
        buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"{prefix}_page_{page-1}"))
    buttons.append(types.InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="none"))
    if page < total_pages - 1:
        buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"{prefix}_page_{page+1}"))
    markup.add(*buttons)
    return markup

def generate_progress_bar(percent: float, length: int = 10) -> str:
    filled = int(length * percent)
    bar = "▓" * filled + "░" * (length - filled)
    return f"`{bar}` {percent*100:.0f}%"