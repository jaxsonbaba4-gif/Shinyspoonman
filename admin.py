import asyncio
import logging
from datetime import datetime, timedelta
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from config import OWNER_ID, MODELS
from database import db
from utils import safe_edit, safe_answer

logger = logging.getLogger(__name__)

def register_admin_handlers(bot: AsyncTeleBot):

    async def is_owner(uid):
        return uid == OWNER_ID

    @bot.message_handler(commands=['admin'])
    async def dashboard(message):
        if not await db.is_admin(message.from_user.id):
            await bot.reply_to(message, "⛔ Admin only")
            return
        await show_dash(message.chat.id, bot)

    @bot.callback_query_handler(func=lambda c: c.data == "admin_dash")
    async def cb_dash(call):
        if not await db.is_admin(call.from_user.id):
            return
        await show_dash(call.message.chat.id, bot, msg_id=call.message.message_id)
        await safe_answer(bot, call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "admin_models")
    async def cb_models(call):
        if not await db.is_admin(call.from_user.id):
            return
        await show_model_mgr(call.message.chat.id, bot, msg_id=call.message.message_id)
        await safe_answer(bot, call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("tog_"))
    async def cb_toggle(call):
        if not await db.is_admin(call.from_user.id):
            return
        _, model, action = call.data.split("_", 2)
        if action == "lock":
            cur = await db.is_model_locked(model)
            await db.set_model_locked(model, not cur)
        elif action == "enable":
            cur = await db.is_model_enabled(model)
            await db.set_model_enabled(model, not cur)
        await show_model_mgr(call.message.chat.id, bot, msg_id=call.message.message_id)
        await safe_answer(bot, call.id, "✅ Updated")

    @bot.callback_query_handler(func=lambda c: c.data == "admin_maint")
    async def cb_maint(call):
        if not await db.is_admin(call.from_user.id):
            return
        cur = await db.get_setting("maintenance", "0")
        new = "1" if cur == "0" else "0"
        await db.set_setting("maintenance", new)
        await safe_answer(bot, call.id, f"Maintenance {'ON' if new=='1' else 'OFF'}")
        await show_dash(call.message.chat.id, bot, msg_id=call.message.message_id)

    @bot.message_handler(commands=['premium'])
    async def premium_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 2:
            await bot.reply_to(message, "Usage: /premium <user_id> [hours]")
            return
        uid = int(parts[1])
        await db.ensure_user(uid)
        until = None
        if len(parts) >= 3:
            until = (datetime.utcnow() + timedelta(hours=int(parts[2]))).isoformat()
        await db.set_tier(uid, "premium", premium_until=until)
        await bot.reply_to(message, f"🌟 User {uid} is premium {'for '+parts[2]+'h' if until else 'permanently'}")

    @bot.message_handler(commands=['ban'])
    async def ban_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) != 2:
            await bot.reply_to(message, "/ban <user_id>")
            return
        uid = int(parts[1])
        await db.ensure_user(uid)
        await db.ban_user(uid)
        await bot.reply_to(message, f"🚫 {uid} banned")

    @bot.message_handler(commands=['unban'])
    async def unban_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) != 2:
            await bot.reply_to(message, "/unban <user_id>")
            return
        uid = int(parts[1])
        await db.unban_user(uid)
        await bot.reply_to(message, f"✅ {uid} unbanned")

    @bot.message_handler(commands=['setwelcome'])
    async def welcome_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        txt = message.text.split(maxsplit=1)
        if len(txt) < 2:
            await bot.reply_to(message, "/setwelcome <text>")
            return
        await db.set_setting("welcome_message", txt[1])
        await bot.reply_to(message, "✅ Updated")

    @bot.message_handler(commands=['broadcast'])
    async def broadcast_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        txt = message.text.split(maxsplit=1)
        if len(txt) < 2:
            await bot.reply_to(message, "/broadcast <message>")
            return
        users = await db.get_all_users()
        c = 0
        for u in users:
            try:
                await bot.send_message(u["user_id"], f"📢 <b>Announcement</b>\n\n{txt[1]}", parse_mode="HTML")
                c += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await bot.reply_to(message, f"✅ Sent to {c}/{len(users)}")

    # ── UI builders ────────────────────────────────
    async def show_dash(chat_id, bot, msg_id=None):
        users = await db.get_all_users()
        total = len(users)
        banned = sum(1 for u in users if u.get("banned"))
        prem = sum(1 for u in users if u.get("tier") == "premium")
        usage = sum(u.get("usage_count", 0) for u in users)
        text = (f"🛡️ <b>Admin Dashboard</b>\n\n"
                f"👥 {total} | 🚫 {banned} | 🌟 {prem} | ⚡ {usage}\n\n"
                "Select action:")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🧠 Models", callback_data="admin_models"),
            types.InlineKeyboardButton("🔄 Refresh", callback_data="admin_dash"),
            types.InlineKeyboardButton("🔧 Maintenance", callback_data="admin_maint"),
            types.InlineKeyboardButton("❌ Close", callback_data="close")
        )
        if msg_id:
            await safe_edit(bot, chat_id, msg_id, text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

    async def show_model_mgr(chat_id, bot, msg_id=None):
        text = "🧠 <b>Model Manager</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        all_models = [m for v in MODELS.values() for m in v][:6]
        for m in all_models:
            en = await db.is_model_enabled(m)
            lo = await db.is_model_locked(m)
            text += f"{'🟢' if en else '🔴'}{'🔒' if lo else '🔓'} <code>{m}</code>\n"
            markup.add(
                types.InlineKeyboardButton(f"{'🔓' if lo else '🔒'}", callback_data=f"tog_{m}_lock"),
                types.InlineKeyboardButton(f"{'🔴' if en else '🟢'}", callback_data=f"tog_{m}_enable")
            )
        markup.add(
            types.InlineKeyboardButton("🔙 Back", callback_data="admin_dash"),
            types.InlineKeyboardButton("❌ Close", callback_data="close")
        )
        if msg_id:
            await safe_edit(bot, chat_id, msg_id, text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
