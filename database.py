import aiosqlite
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple

DB_PATH = "lithovex.db"

class Database:
    def __init__(self):
        self.conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self.conn = await aiosqlite.connect(DB_PATH)
        self.conn.row_factory = aiosqlite.Row
        await self._create_tables()

    async def _create_tables(self):
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                tier TEXT DEFAULT 'free',
                premium_until TIMESTAMP,
                banned INTEGER DEFAULT 0,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                usage_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS model_config (
                model_name TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                locked INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                sent_by INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self.conn.commit()
        # Ensure owner is admin
        from config import OWNER_ID
        await self.conn.execute("INSERT OR IGNORE INTO admins VALUES (?)", (OWNER_ID,))
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    # User methods
    async def get_user(self, user_id: int):
        async with self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

    async def add_user(self, user_id: int, username: str, first_name: str):
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, last_active, usage_count) VALUES (?, ?, ?, ?, 0)",
            (user_id, username, first_name, datetime.utcnow().isoformat())
        )
        await self.conn.commit()

    async def update_last_active(self, user_id: int):
        await self.conn.execute(
            "UPDATE users SET last_active = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat(), user_id)
        )
        await self.conn.commit()

    async def increment_usage(self, user_id: int):
        await self.conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def set_tier(self, user_id: int, tier: str, premium_until: Optional[str] = None):
        await self.conn.execute(
            "UPDATE users SET tier = ?, premium_until = ? WHERE user_id = ?",
            (tier, premium_until, user_id)
        )
        await self.conn.commit()

    async def is_premium(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        if user["tier"] == "premium":
            if user["premium_until"] and datetime.fromisoformat(user["premium_until"]) > datetime.utcnow():
                return True
        return False

    async def ban_user(self, user_id: int):
        await self.conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def unban_user(self, user_id: int):
        await self.conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def is_banned(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if user:
            return bool(user["banned"])
        return False

    async def get_all_users(self) -> List[dict]:
        async with self.conn.execute("SELECT * FROM users") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Admin methods
    async def add_admin(self, user_id: int):
        await self.conn.execute("INSERT OR IGNORE INTO admins VALUES (?)", (user_id,))
        await self.conn.commit()

    async def remove_admin(self, user_id: int):
        await self.conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def is_admin(self, user_id: int) -> bool:
        from config import OWNER_ID
        if user_id == OWNER_ID:
            return True
        async with self.conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None

    # Model config
    async def set_model_enabled(self, model: str, enabled: bool):
        await self.conn.execute(
            "INSERT OR REPLACE INTO model_config (model_name, enabled, locked) VALUES (?, ?, ?)",
            (model, int(enabled), 0)
        )
        await self.conn.commit()

    async def set_model_locked(self, model: str, locked: bool):
        await self.conn.execute(
            "INSERT OR REPLACE INTO model_config (model_name, enabled, locked) VALUES (?, 1, ?)",
            (model, int(locked))
        )
        await self.conn.commit()

    async def is_model_enabled(self, model: str) -> bool:
        async with self.conn.execute("SELECT enabled FROM model_config WHERE model_name = ?", (model,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return True  # by default all enabled
            return bool(row[0])

    async def is_model_locked(self, model: str) -> bool:
        async with self.conn.execute("SELECT locked FROM model_config WHERE model_name = ?", (model,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return False
            return bool(row[0])

    # Settings
    async def set_setting(self, key: str, value: str):
        await self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await self.conn.commit()

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return default

    # Chat history
    async def add_message(self, user_id: int, role: str, content: str):
        await self.conn.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        await self.conn.commit()

    async def get_history(self, user_id: int, limit: int = 10) -> List[dict]:
        async with self.conn.execute(
            "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            rows.reverse()
            return [dict(row) for row in rows]

    async def clear_history(self, user_id: int):
        await self.conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    # Broadcast
    async def log_broadcast(self, text: str, sender_id: int):
        await self.conn.execute("INSERT INTO broadcasts (text, sent_by) VALUES (?, ?)", (text, sender_id))
        await self.conn.commit()

db = Database()