import json
import logging
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from config import MODELS, DEFAULT_MODEL, FALLBACK_MODELS, PREMIUM_MODEL, API_URL, OWNER_ID
from database import db
from utils import is_rate_limited, safe_edit, safe_answer

logger = logging.getLogger(__name__)

def register_user_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=['start'])
    async def start(message):
        user = message.from_user
        await db.add_user(user.id, user.username, user.first_name)
        welcome = await db.get_setting("welcome_message",
            "👾 Welcome to <b>LITHOVEX AI</b>\n\nUse /help for commands, /models to choose AI.")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✨ Models", callback_data="show_models"),
            types.InlineKeyboardButton("ℹ️ Help", callback_data="show_help")
        )
        await bot.send_message(message.chat.id, welcome, parse_mode="HTML", reply_markup=markup)

    @bot.message_handler(commands=['id'])
    async def show_id(message):
        await bot.reply_to(message, f"🆔 <code>{message.from_user.id}</code>", parse_mode="HTML")

    @bot.message_handler(commands=['help'])
    async def help_cmd(message):
        await show_help(message.chat.id, bot)

    @bot.message_handler(commands=['stats'])
    async def stats_cmd(message):
        user = await db.get_user(message.from_user.id)
        if not user:
            await bot.reply_to(message, "❌ Start bot first: /start")
            return
        usage = user["usage_count"]
        tier = user["tier"]
        premium = await db.is_premium(message.from_user.id)
        model = await db.get_setting(f"model_{message.from_user.id}", DEFAULT_MODEL)
        text = (f"📊 <b>Stats</b>\n"
                f"• Requests: {usage}\n"
                f"• Tier: {tier}{' 🌟' if premium else ''}\n"
                f"• Model: <code>{model}</code>")
        await bot.send_message(message.chat.id, text, parse_mode="HTML")

    @bot.message_handler(commands=['models'])
    async def models_cmd(message):
        await show_models_page(message.chat.id, 0, bot)

    # ── Callback Handlers ──────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == "show_help")
    async def cb_help(call):
        await show_help(call.message.chat.id, bot, msg_id=call.message.message_id)
        await safe_answer(bot, call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "show_models")
    async def cb_models(call):
        await show_models_page(call.message.chat.id, 0, bot, msg_id=call.message.message_id)
        await safe_answer(bot, call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("models_page_"))
    async def cb_models_page(call):
        page = int(call.data.split("_")[2])
        await show_models_page(call.message.chat.id, page, bot, msg_id=call.message.message_id)
        await safe_answer(bot, call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("select_model_"))
    async def cb_select_model(call):
        user_id = call.from_user.id
        model = call.data.replace("select_model_", "", 1)
        await db.set_setting(f"model_{user_id}", model)
        await safe_answer(bot, call.id, f"✅ {model.split('/')[-1]}")
        await safe_edit(bot, call.message.chat.id, call.message.message_id,
                       f"✅ Model: <b>{model}</b>")

    @bot.callback_query_handler(func=lambda c: c.data == "close")
    async def cb_close(call):
        try:
            await bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

    # ── Main text handler ──────────────────────────
    @bot.message_handler(func=lambda m: True, content_types=['text'])
    async def chat_handler(message):
        user = message.from_user

        # Skip commands (they have own handlers)
        if message.text.startswith('/'):
            return

        if await db.is_banned(user.id):
            return
        if is_rate_limited(user.id):
            await bot.reply_to(message, "⏳ Slow down!")
            return

        # Special replies
        txt = message.text.strip().lower()
        if txt in ["who created you?", "who made you?", "creator", "dev"]:
            await bot.reply_to(message, "I was developed by @normaluser2")
            return

        await db.add_user(user.id, user.username, user.first_name)

        # Maintenance check
        if await db.get_setting("maintenance", "0") == "1" and not await db.is_admin(user.id):
            await bot.reply_to(message, "🔧 Maintenance mode.")
            return

        # Model check
        model = await db.get_setting(f"model_{user.id}", DEFAULT_MODEL)
        if not await db.is_model_enabled(model):
            await bot.reply_to(message, f"🚫 {model} disabled. Use /models")
            return
        if await db.is_model_locked(model) and not await db.is_admin(user.id):
            await bot.reply_to(message, f"🔒 {model} locked.")
            return
        if model == PREMIUM_MODEL and not await db.is_premium(user.id) and user.id != OWNER_ID:
            await bot.reply_to(message, "🌟 Premium model only.")
            return

        # Thinking message
        think = await bot.send_message(message.chat.id, "💭 <i>Thinking...</i>", parse_mode="HTML")

        # Build history
        hist = await db.get_history(user.id, 8)
        msgs = [{"role": h["role"], "content": h["content"]} for h in hist]
        msgs.append({"role": "user", "content": message.text})
        await db.add_message(user.id, "user", message.text)

        # Call API with fallback
        final_text = None
        used = model
        for attempt in [model] + [fb for fb in FALLBACK_MODELS if fb != model]:
            try:
                final_text = await stream_api(bot, think, msgs, attempt)
                used = attempt
                break
            except Exception as e:
                logger.error(f"Model {attempt} error: {e}")

        if not final_text:
            await safe_edit(bot, think.chat.id, think.message_id, "❌ All models failed.")
            return

        await db.add_message(user.id, "assistant", final_text)
        await db.increment_usage(user.id)

        reply = final_text + f"\n\n⚡ <i>{used}</i>\nDev @normaluser2"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_{message.message_id}"),
            types.InlineKeyboardButton("❌ Close", callback_data="close")
        )
        await safe_edit(bot, think.chat.id, think.message_id, reply, reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("regen_"))
    async def cb_regenerate(call):
        await safe_answer(bot, call.id, "Send the message again to regenerate.")
        # Simple approach – ask user to resend

# ── Helper functions ──────────────────────────────
async def show_help(chat_id, bot, msg_id=None):
    text = ("🤖 <b>LITHOVEX AI</b>\n\n"
            "/start – Welcome\n"
            "/help – This menu\n"
            "/models – Choose model\n"
            "/stats – Your usage\n"
            "/id – Your Telegram ID\n\n"
            "<i>Dev @normaluser2</i>")
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✨ Models", callback_data="show_models"),
        types.InlineKeyboardButton("❌ Close", callback_data="close")
    )
    if msg_id:
        await safe_edit(bot, chat_id, msg_id, text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

async def show_models_page(chat_id, page, bot, msg_id=None):
    all_models = [(p, m) for p, mods in MODELS.items() for m in mods]
    per_page = 8
    total_pages = max(1, (len(all_models) + per_page - 1) // per_page)
    start = page * per_page
    chunk = all_models[start:start+per_page]

    emojis = {"openai":"🔹","anthropic":"🔸","google":"🟢","xai":"⚡",
              "deepseek":"🐋","qwen":"👾","meta":"🦙","moonshot":"🌙",
              "minimax":"🌀","zhipu":"🔷","cohere":"🟣","mistral":"🌪️"}

    text = f"✨ <b>Models</b> (page {page+1}/{total_pages})\n\n"
    for prov, model in chunk:
        text += f"{emojis.get(prov,'🔸')} <code>{model}</code>\n"

    markup = types.InlineKeyboardMarkup(row_width=1)
    for _, model in chunk:
        short = model.split('/')[-1][:20]
        markup.add(types.InlineKeyboardButton(f"✅ {short}", callback_data=f"select_model_{model}"))

    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"models_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("➡️", callback_data=f"models_page_{page+1}"))
    if nav:
        markup.row(*nav)

    markup.add(types.InlineKeyboardButton("❌ Close", callback_data="close"))

    if msg_id:
        await safe_edit(bot, chat_id, msg_id, text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

async def stream_api(bot, msg, messages, model):
    import httpx
    headers = {"Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True}
    accumulated = ""
    last = 0

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", API_URL, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            buf = ""
            async for chunk in resp.aiter_bytes():
                buf += chunk.decode()
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                            delta = obj["choices"][0]["delta"].get("content", "")
                            if delta:
                                accumulated += delta
                                if len(accumulated) - last > 10:
                                    await safe_edit(bot, msg.chat.id, msg.message_id,
                                                   accumulated + "\n\n💭 <i>...</i>")
                                    last = len(accumulated)
                        except:
                            continue
    return accumulated.strip()
