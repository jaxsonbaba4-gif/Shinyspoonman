from telebot.async_telebot import AsyncTeleBot
from telebot import types
from config import OWNER_ID
from database import db
import asyncio
import logging

logger = logging.getLogger(__name__)

def register_admin_handlers(bot: AsyncTeleBot):
    async def admin_only(func):
        async def wrapper(message):
            if not await db.is_admin(message.from_user.id):
                await bot.reply_to(message, "⛔ Admin only.")
                return
            await func(message)
        return wrapper

    @bot.message_handler(commands=['broadcast'])
    @admin_only
    async def broadcast_cmd(message):
        # Expect format: /broadcast text
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await bot.reply_to(message, "Usage: /broadcast <text>")
            return
        text = parts[1]
        await db.log_broadcast(text, message.from_user.id)
        users = await db.get_all_users()
        count = 0
        for user in users:
            try:
                await bot.send_message(user["user_id"], f"📢 <b>Announcement</b>\n\n{text}", parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)  # avoid flood
            except:
                pass
        await bot.reply_to(message, f"✅ Broadcast sent to {count}/{len(users)} users.")

    @bot.message_handler(commands=['ban'])
    @admin_only
    async def ban_cmd(message):
        if len(message.text.split()) != 2:
            await bot.reply_to(message, "Usage: /ban <user_id>")
            return
        target = int(message.text.split()[1])
        await db.ban_user(target)
        await bot.reply_to(message, f"🚫 User {target} banned.")

    @bot.message_handler(commands=['unban'])
    @admin_only
    async def unban_cmd(message):
        if len(message.text.split()) != 2:
            await bot.reply_to(message, "Usage: /unban <user_id>")
            return
        target = int(message.text.split()[1])
        await db.unban_user(target)
        await bot.reply_to(message, f"✅ User {target} unbanned.")

    @bot.message_handler(commands=['admin'])
    @admin_only
    async def admin_manage(message):
        parts = message.text.split()
        if len(parts) < 2:
            await bot.reply_to(message, "Usage:\n/admin add <id>\n/admin remove <id>\n/admin list")
            return
        action = parts[1]
        if action == "add" and len(parts) == 3:
            target = int(parts[2])
            await db.add_admin(target)
            await bot.reply_to(message, f"👑 Admin added: {target}")
        elif action == "remove" and len(parts) == 3:
            target = int(parts[2])
            if target == OWNER_ID:
                await bot.reply_to(message, "Cannot remove the owner.")
                return
            await db.remove_admin(target)
            await bot.reply_to(message, f"Admin removed: {target}")
        elif action == "list":
            admins = await db.conn.execute_fetchall("SELECT user_id FROM admins")
            ids = [str(row[0]) for row in admins]
            await bot.reply_to(message, "Admins: " + ", ".join(ids))
        else:
            await bot.reply_to(message, "Invalid format.")

    @bot.message_handler(commands=['maintenance'])
    @admin_only
    async def maintenance_cmd(message):
        current = await db.get_setting("maintenance", "0")
        new = "1" if current == "0" else "0"
        await db.set_setting("maintenance", new)
        state = "🟢 OFF" if new == "0" else "🔴 ON"
        await bot.reply_to(message, f"Maintenance mode: {state}")

    @bot.message_handler(commands=['setwelcome'])
    @admin_only
    async def set_welcome_cmd(message):
        text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if not text:
            await bot.reply_to(message, "Usage: /setwelcome <new welcome text>")
            return
        await db.set_setting("welcome_message", text)
        await bot.reply_to(message, "✅ Welcome message updated.")

    @bot.message_handler(commands=['lockmodel', 'unlockmodel'])
    @admin_only
    async def lock_model(message):
        cmd = message.text.split()
        if len(cmd) != 2:
            await bot.reply_to(message, "Usage: /lockmodel <model_name> or /unlockmodel <model_name>")
            return
        model = cmd[1]
        lock = message.text.startswith('/lockmodel')
        await db.set_model_locked(model, lock)
        status = "locked" if lock else "unlocked"
        await bot.reply_to(message, f"🔒 Model <code>{model}</code> {status}.", parse_mode="HTML")

    @bot.message_handler(commands=['enablemodel', 'disablemodel'])
    @admin_only
    async def enable_model(message):
        cmd = message.text.split()
        if len(cmd) != 2:
            await bot.reply_to(message, "Usage: /enablemodel <model_name> or /disablemodel <model_name>")
            return
        model = cmd[1]
        enable = message.text.startswith('/enablemodel')
        await db.set_model_enabled(model, enable)
        status = "enabled" if enable else "disabled"
        await bot.reply_to(message, f"⚙️ Model <code>{model}</code> {status}.", parse_mode="HTML")

    @bot.message_handler(commands=['premium'])
    @admin_only
    async def set_premium(message):
        parts = message.text.split()
        if len(parts) < 2:
            await bot.reply_to(message, "Usage: /premium <user_id> [duration_hours] (default permanent)")
            return
        user_id = int(parts[1])
        duration = None
        if len(parts) >= 3:
            hours = int(parts[2])
            from datetime import datetime, timedelta
            until = datetime.utcnow() + timedelta(hours=hours)
            duration = until.isoformat()
        await db.set_tier(user_id, "premium", premium_until=duration)
        await bot.reply_to(message, f"🌟 User {user_id} set to premium.")

    @bot.message_handler(commands=['statsadmin'])
    @admin_only
    async def admin_stats(message):
        users = await db.get_all_users()
        total = len(users)
        banned = sum(1 for u in users if u["banned"])
        premium = sum(1 for u in users if u["tier"] == "premium")
        total_usage = sum(u["usage_count"] for u in users)
        text = (
            f"📊 <b>Admin Stats</b>\n"
            f"• Total users: {total}\n"
            f"• Banned: {banned}\n"
            f"• Premium: {premium}\n"
            f"• Total requests: {total_usage}\n"
        )
        await bot.reply_to(message, text, parse_mode="HTML")