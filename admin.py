import asyncio
import logging
from datetime import datetime, timedelta
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from config import OWNER_ID, MODELS
from database import db
from utils import safe_edit

logger = logging.getLogger(__name__)

def register_admin_handlers(bot: AsyncTeleBot):

    async def is_owner(user_id):
        return user_id == OWNER_ID

    # ── Admin dashboard ─────────────────
    @bot.message_handler(commands=['admin'])
    async def admin_dashboard(message):
        if not await db.is_admin(message.from_user.id):
            await bot.reply_to(message, "⛔ Admin access only.")
            return
        await show_dashboard(message.chat.id, bot, message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "admin_dashboard")
    async def refresh_dashboard(call):
        if not await db.is_admin(call.from_user.id):
            await bot.answer_callback_query(call.id, "Access denied.")
            return
        await show_dashboard(call.message.chat.id, bot, call.message.message_id, edit=True)
        await bot.answer_callback_query(call.id)

    # ── Model manager ──────────────────
    @bot.callback_query_handler(func=lambda call: call.data == "admin_models")
    async def model_management(call):
        if not await db.is_admin(call.from_user.id):
            await bot.answer_callback_query(call.id, "Access denied.")
            return
        await show_model_manager(call.message.chat.id, bot, call.message.message_id)
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_model_"))
    async def toggle_model(call):
        if not await db.is_admin(call.from_user.id):
            await bot.answer_callback_query(call.id, "Access denied.")
            return
        parts = call.data.split("_", 2)
        model = parts[1]
        action = parts[2]
        if action == "lock":
            current = await db.is_model_locked(model)
            await db.set_model_locked(model, not current)
        elif action == "enable":
            current = await db.is_model_enabled(model)
            await db.set_model_enabled(model, not current)
        await show_model_manager(call.message.chat.id, bot, call.message.message_id, edit=True)
        await bot.answer_callback_query(call.id, "✅ Updated")

    # ── Broadcast – skip commands ──────
    @bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
    async def broadcast_prompt(call):
        if not await db.is_admin(call.from_user.id):
            await bot.answer_callback_query(call.id, "Access denied.")
            return
        await db.set_setting(f"broadcast_{call.from_user.id}", "1")
        await bot.answer_callback_query(call.id)
        await bot.send_message(call.message.chat.id,
            "📣 <b>Broadcast mode activated.</b>\n\nSend the message you want to broadcast.\n<i>Type /cancel to abort.</i>",
            parse_mode="HTML"
        )

    @bot.message_handler(commands=['cancel'])
    async def cancel_broadcast(message):
        if await db.is_admin(message.from_user.id):
            await db.set_setting(f"broadcast_{message.from_user.id}", "0")
            await bot.reply_to(message, "❌ Broadcast cancelled.")

    @bot.message_handler(func=lambda m: True, content_types=['text'])
    async def maybe_broadcast(message):
        # Skip commands – they have their own handlers
        if message.text and message.text.startswith('/'):
            return

        if not await db.is_admin(message.from_user.id):
            return  # let user handler take over

        if await db.get_setting(f"broadcast_{message.from_user.id}", "0") == "1":
            await db.set_setting(f"broadcast_{message.from_user.id}", "0")
            users = await db.get_all_users()
            count = 0
            for u in users:
                try:
                    await bot.send_message(u["user_id"], f"📢 <b>Announcement</b>\n\n{message.text}",
                                           parse_mode="HTML")
                    count += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
            await bot.reply_to(message, f"✅ Broadcast sent to {count}/{len(users)} users.")
            return
        # If not broadcast, fall through → next handler will catch

    # ── Maintenance toggle ─────────────
    @bot.callback_query_handler(func=lambda call: call.data == "admin_maintenance_toggle")
    async def toggle_maintenance(call):
        if not await db.is_admin(call.from_user.id):
            await bot.answer_callback_query(call.id, "Access denied.")
            return
        current = await db.get_setting("maintenance", "0")
        new = "1" if current == "0" else "0"
        await db.set_setting("maintenance", new)
        await bot.answer_callback_query(call.id, f"Maintenance {'ON' if new=='1' else 'OFF'}")
        await show_dashboard(call.message.chat.id, bot, call.message.message_id, edit=True)

    # ── Owner-only text commands ───────
    @bot.message_handler(commands=['ban'])
    async def ban_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) != 2:
            await bot.reply_to(message, "Usage: /ban <user_id>")
            return
        uid = int(parts[1])
        await db.ensure_user(uid)   # create user row if missing
        await db.ban_user(uid)
        await bot.reply_to(message, f"🚫 User {uid} banned.")

    @bot.message_handler(commands=['unban'])
    async def unban_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) != 2:
            await bot.reply_to(message, "Usage: /unban <user_id>")
            return
        uid = int(parts[1])
        await db.ensure_user(uid)
        await db.unban_user(uid)
        await bot.reply_to(message, f"✅ User {uid} unbanned.")

    @bot.message_handler(commands=['premium'])
    async def premium_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 2:
            await bot.reply_to(message, "Usage: /premium <user_id> [hours]")
            return
        uid = int(parts[1])
        await db.ensure_user(uid)   # ensure user exists in DB
        until = None
        if len(parts) >= 3:
            until = (datetime.utcnow() + timedelta(hours=int(parts[2]))).isoformat()
        await db.set_tier(uid, "premium", premium_until=until)
        await bot.reply_to(message, f"🌟 User {uid} is now premium {'for ' + parts[2] + ' hours' if until else 'permanently'}.")

    @bot.message_handler(commands=['setwelcome'])
    async def set_welcome_cmd(message):
        if not await is_owner(message.from_user.id):
            return
        text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if not text:
            await bot.reply_to(message, "Usage: /setwelcome <new text>")
            return
        await db.set_setting("welcome_message", text)
        await bot.reply_to(message, "✅ Welcome message updated.")

    # ── Dashboard builders ─────────────
    async def show_dashboard(chat_id, bot, msg_id=None, edit=False):
        users = await db.get_all_users()
        total = len(users)
        banned = sum(1 for u in users if u["banned"])
        premium = sum(1 for u in users if u["tier"] == "premium")
        usage = sum(u["usage_count"] for u in users)
        text = (
            f"🛡️ <b>LITHOVEX AI Admin Dashboard</b>\n\n"
            f"👥 Users: <b>{total}</b>\n"
            f"🚫 Banned: <b>{banned}</b>\n"
            f"🌟 Premium: <b>{premium}</b>\n"
            f"⚡ Total requests: <b>{usage}</b>\n\n"
            "Select an action:"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🧠 Model Manager", callback_data="admin_models"),
            types.InlineKeyboardButton("📣 Broadcast", callback_data="admin_broadcast")
        )
        markup.add(
            types.InlineKeyboardButton("🔄 Refresh", callback_data="admin_dashboard"),
            types.InlineKeyboardButton("🔧 Maintenance", callback_data="admin_maintenance_toggle")
        )
        markup.add(
            types.InlineKeyboardButton("👑 Admins", callback_data="admin_admins"),
            types.InlineKeyboardButton("❌ Close", callback_data="close")
        )
        if edit and msg_id:
            await safe_edit(bot, chat_id, msg_id, text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

    async def show_model_manager(chat_id, bot, msg_id, edit=False):
        text = "🧠 <b>Model Configuration</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        all_models = [m for sub in MODELS.values() for m in sub]
        # Show first 8 models
        for model in all_models[:8]:
            enabled = await db.is_model_enabled(model)
            locked = await db.is_model_locked(model)
            status = "🟢" if enabled else "🔴"
            lock_icon = "🔒" if locked else "🔓"
            text += f"{status}{lock_icon} <code>{model}</code>\n"
            markup.add(
                types.InlineKeyboardButton(
                    f"{'🔓' if locked else '🔒'} {model.split('/')[-1][:10]}",
                    callback_data=f"toggle_model_{model}_lock"
                ),
                types.InlineKeyboardButton(
                    f"{'🟢 Enable' if not enabled else '🔴 Disable'}",
                    callback_data=f"toggle_model_{model}_enable"
                )
            )
        markup.add(types.InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard"))
        if edit:
            await safe_edit(bot, chat_id, msg_id, text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
