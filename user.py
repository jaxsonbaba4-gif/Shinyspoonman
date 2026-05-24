import asyncio
import json
import logging
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from config import MODELS, DEFAULT_MODEL, FALLBACK_MODELS, PREMIUM_MODEL, API_URL, OWNER_ID
from database import db
from utils import is_rate_limited, safe_edit

logger = logging.getLogger(__name__)

def register_user_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=['start'])
    async def start(message):
        user = message.from_user
        await db.add_user(user.id, user.username, user.first_name)
        if OWNER_ID == 0:
            await bot.send_message(message.chat.id,
                "⚠️ <b>OWNER_ID not set!</b> Use /id to get your ID and set it in env.",
                parse_mode="HTML")
        welcome = await db.get_setting("welcome_message",
            "👾 Welcome to <b>LITHOVEX AI</b> – the ultimate AI experience.\n\n"
            "Use /help to explore, /models to choose a model, and just send a message to begin.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✨ Models", callback_data="menu_models"),
                   types.InlineKeyboardButton("ℹ️ Help", callback_data="menu_help"))
        await bot.send_message(message.chat.id, welcome, parse_mode="HTML", reply_markup=markup)

    @bot.message_handler(commands=['id'])
    async def show_id(message):
        await bot.reply_to(message, f"🆔 Your ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

    @bot.message_handler(commands=['help'])
    async def help_command(message):
        await send_help(message.chat.id, bot)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_help")
    async def help_callback(call):
        await send_help(call.message.chat.id, bot, edit_message=call.message)
        await bot.answer_callback_query(call.id)

    @bot.message_handler(commands=['models'])
    async def models_command(message):
        await show_models_page(message.chat.id, 0, bot)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("models_page_"))
    async def models_page_callback(call):
        page = int(call.data.split("_")[-1])
        await show_models_page(call.message.chat.id, page, bot, edit_message=call.message)
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("select_model_"))
    async def select_model(call):
        user_id = call.from_user.id
        model = call.data.replace("select_model_", "", 1)
        await db.set_setting(f"model_{user_id}", model)
        await bot.answer_callback_query(call.id, f"✅ Model set to {model.split('/')[-1]}")
        await safe_edit(bot, call.message.chat.id, call.message.message_id,
                        f"✅ Model changed to <b>{model}</b>")

    @bot.message_handler(commands=['stats'])
    async def user_stats(message):
        user = await db.get_user(message.from_user.id)
        usage = user["usage_count"] if user else 0
        tier = user["tier"] if user else "free"
        premium = await db.is_premium(message.from_user.id)
        model = await db.get_setting(f"model_{message.from_user.id}", DEFAULT_MODEL)
        stats = (f"📊 <b>Your Stats</b>\n"
                 f"• Requests: {usage}\n"
                 f"• Tier: {tier.capitalize()}{' 🌟' if premium else ''}\n"
                 f"• Selected model: <code>{model}</code>")
        await bot.send_message(message.chat.id, stats, parse_mode="HTML")

    @bot.message_handler(func=lambda m: True, content_types=['text'])
    async def handle_text(message):
        user = message.from_user
        if await db.is_banned(user.id):
            return
        if is_rate_limited(user.id):
            await bot.send_message(message.chat.id, "⚠️ Please wait a few seconds.")
            return

        if message.text.strip().lower() in ["who created you?", "who made you?", "creator"]:
            await bot.send_message(message.chat.id, "I was developed by @normaluser2")
            return

        await db.add_user(user.id, user.username, user.first_name)
        await db.update_last_active(user.id)

        maintenance = await db.get_setting("maintenance", "0")
        if maintenance == "1" and not await db.is_admin(user.id):
            await bot.send_message(message.chat.id, "🔧 LITHOVEX AI is under maintenance.")
            return

        model = await db.get_setting(f"model_{user.id}", DEFAULT_MODEL)

        # Model restrictions
        if not await db.is_model_enabled(model):
            await bot.send_message(message.chat.id, f"🚫 Model <code>{model}</code> is disabled.", parse_mode="HTML")
            return
        if await db.is_model_locked(model) and not await db.is_admin(user.id):
            await bot.send_message(message.chat.id, f"🔒 Model <code>{model}</code> is locked.", parse_mode="HTML")
            return
        if model == PREMIUM_MODEL and not await db.is_premium(user.id) and user.id != OWNER_ID:
            await bot.send_message(message.chat.id, "🌟 This model requires premium.")
            return

        thinking_msg = await bot.send_message(message.chat.id, "💭 <i>LITHOVEX AI is thinking...</i>", parse_mode="HTML")

        history = await db.get_history(user.id, limit=8)
        msgs = [{"role": h["role"], "content": h["content"]} for h in history]
        msgs.append({"role": "user", "content": message.text})
        await db.add_message(user.id, "user", message.text)

        response_text = None
        used_model = model
        try:
            response_text = await stream_api_response(bot, thinking_msg, msgs, model)
        except Exception as e:
            logger.error(f"Model {model} failed: {e}")
            for fb in FALLBACK_MODELS:
                if fb == model:
                    continue
                try:
                    response_text = await stream_api_response(bot, thinking_msg, msgs, fb)
                    used_model = fb
                    break
                except Exception as e2:
                    logger.error(f"Fallback {fb} also failed: {e2}")

        if not response_text:
            await safe_edit(bot, thinking_msg.chat.id, thinking_msg.message_id,
                            "❌ All models failed. Please try later.")
            return

        await db.add_message(user.id, "assistant", response_text)
        await db.increment_usage(user.id)

        final_text = response_text + f"\n\n⚡ <i>Powered by {used_model}</i>\nDev @normaluser2"
        reply_markup = types.InlineKeyboardMarkup(row_width=3)
        reply_markup.add(
            types.InlineKeyboardButton("🔄 Regenerate", callback_data=f"regenerate_{message.message_id}"),
            types.InlineKeyboardButton("📋 Copy", callback_data=f"copy_{message.message_id}"),
            types.InlineKeyboardButton("❌ Close", callback_data="close")
        )
        await safe_edit(bot, thinking_msg.chat.id, thinking_msg.message_id, final_text, reply_markup=reply_markup)

    @bot.callback_query_handler(func=lambda call: call.data == "close")
    async def close_message(call):
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        await bot.answer_callback_query(call.id)

async def send_help(chat_id, bot, edit_message=None):
    help_text = (
        "🤖 <b>LITHOVEX AI – Help</b>\n\n"
        "• Send any message to chat\n"
        "• Use /models to choose a model\n"
        "• Use /stats to see your usage\n"
        "• Premium users get <code>gpt-5.5-xhigh-codex</code>\n\n"
        "<i>Dev @normaluser2</i>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📂 Models", callback_data="menu_models"))
    if edit_message:
        await safe_edit(bot, chat_id, edit_message.message_id, help_text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, help_text, parse_mode="HTML", reply_markup=markup)

async def show_models_page(chat_id, page, bot, edit_message=None):
    all_models = [(prov, model) for prov, models in MODELS.items() for model in models]
    items_per_page = 8
    total_pages = (len(all_models) + items_per_page - 1) // items_per_page
    start = page * items_per_page
    end = start + items_per_page
    page_models = all_models[start:end]

    text = "✨ <b>Choose an AI Model</b>\n\n"
    emojis = {
        "openai": "🔹", "anthropic": "🔸", "google": "🟢", "xai": "⚡",
        "deepseek": "🐋", "qwen": "👾", "meta": "🦙", "moonshot": "🌙",
        "minimax": "🌀", "zhipu": "🔷", "cohere": "🟣", "mistral": "🌪️"
    }
    for prov, model in page_models:
        emoji = emojis.get(prov, "🔸")
        text += f"{emoji} <code>{model}</code>\n"

    markup = types.InlineKeyboardMarkup(row_width=1)
    for _, model in page_models:
        markup.add(types.InlineKeyboardButton(f"✅ Select {model.split('/')[-1]}",
                                              callback_data=f"select_model_{model}"))
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"models_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"models_page_{page+1}"))
        if nav_buttons:
            markup.add(*nav_buttons)

    if edit_message:
        await safe_edit(bot, chat_id, edit_message.message_id, text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

async def stream_api_response(bot, message, messages, model):
    import httpx
    headers = {"Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True}
    accumulated = ""
    last_update = 0
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", API_URL, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            buffer = ""
            async for chunk in resp.aiter_bytes():
                buffer += chunk.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                            delta = obj["choices"][0]["delta"].get("content", "")
                            if delta:
                                accumulated += delta
                                if len(accumulated) - last_update > 5:
                                    await safe_edit(bot, message.chat.id, message.message_id,
                                                    accumulated + "\n\n💭 <i>Generating...</i>")
                                    last_update = len(accumulated)
                        except:
                            continue
    return accumulated.strip()
