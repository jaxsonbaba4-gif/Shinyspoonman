import asyncio
import asyncpg
from datetime import datetime
from typing import Optional, List
from config import DATABASE_URL, OWNER_ID

class Database:
    def __init__(self):
        self.pool = None

    async def init(self):
        self.pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=2,
            max_size=10,
            ssl="require"  # required for Neon
        )
        await self._create_tables()

    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    tier TEXT DEFAULT 'free',
                    premium_until TIMESTAMP,
                    banned BOOLEAN DEFAULT FALSE,
                    joined_date TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP,
                    usage_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS model_config (
                    model_name TEXT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT TRUE,
                    locked BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id SERIAL PRIMARY KEY,
                    text TEXT,
                    sent_by BIGINT,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
            """)
            # Make owner an admin automatically
            await conn.execute(
                "INSERT INTO admins (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                OWNER_ID
            )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def get_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            return dict(row) if row else None

    async def add_user(self, user_id: int, username: str, first_name: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, last_active, usage_count) "
                "VALUES ($1, $2, $3, $4, 0) ON CONFLICT (user_id) DO UPDATE SET last_active = $4",
                user_id, username, first_name, datetime.utcnow()
            )

    async def update_last_active(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_active = $1 WHERE user_id = $2",
                datetime.utcnow(), user_id
            )

    async def increment_usage(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET usage_count = usage_count + 1 WHERE user_id = $1",
                user_id
            )

    async def set_tier(self, user_id: int, tier: str, premium_until: Optional[str] = None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET tier = $1, premium_until = $2 WHERE user_id = $3",
                tier, premium_until, user_id
            )

    async def is_premium(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        if user["tier"] == "premium":
            if user["premium_until"] and user["premium_until"] > datetime.utcnow():
                return True
        return False

    async def ban_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET banned = TRUE WHERE user_id = $1", user_id)

    async def unban_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET banned = FALSE WHERE user_id = $1", user_id)

    async def is_banned(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return user["banned"] if user else False

    async def get_all_users(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users")
            return [dict(row) for row in rows]

    async def add_admin(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admins (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )

    async def remove_admin(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM admins WHERE user_id = $1", user_id)

    async def is_admin(self, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM admins WHERE user_id = $1", user_id)
            return row is not None

    async def set_model_enabled(self, model: str, enabled: bool):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO model_config (model_name, enabled, locked) VALUES ($1, $2, FALSE) "
                "ON CONFLICT (model_name) DO UPDATE SET enabled = $2",
                model, enabled
            )

    async def set_model_locked(self, model: str, locked: bool):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO model_config (model_name, enabled, locked) VALUES ($1, TRUE, $2) "
                "ON CONFLICT (model_name) DO UPDATE SET locked = $2",
                model, locked
            )

    async def is_model_enabled(self, model: str) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT enabled FROM model_config WHERE model_name = $1", model
            )
            return row["enabled"] if row else True

    async def is_model_locked(self, model: str) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT locked FROM model_config WHERE model_name = $1", model
            )
            return row["locked"] if row else False

    async def set_setting(self, key: str, value: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) "
                "ON CONFLICT (key) DO UPDATE SET value = $2",
                key, value
            )

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
            if row:
                return row["value"]
            return default

    async def add_message(self, user_id: int, role: str, content: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)",
                user_id, role, content
            )

    async def get_history(self, user_id: int, limit: int = 10) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content FROM chat_history WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
                user_id, limit
            )
            rows.reverse()
            return [dict(row) for row in rows]

    async def clear_history(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_history WHERE user_id = $1", user_id)

    async def log_broadcast(self, text: str, sender_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO broadcasts (text, sent_by) VALUES ($1, $2)",
                text, sender_id
            )

db = Database()
