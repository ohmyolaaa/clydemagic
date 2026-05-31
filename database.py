import random
import string
import asyncpg
import logging
import os
from datetime import datetime

logger = logging.getLogger("FontStyleBot.DB")

DATABASE_URL = os.environ["DATABASE_URL"]

# ─────────────────────────────────────────────
#  Connection Pool  (replaces per-call connect)
# ─────────────────────────────────────────────
_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def generate_code() -> str:
    digits = ''.join(random.choices(string.digits, k=4))
    return f"CAY{digits}"

# ─────────────────────────────────────────────
#  Init
# ─────────────────────────────────────────────
async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id     BIGINT PRIMARY KEY,
                username        TEXT,
                first_name      TEXT,
                joined_at       TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_nicknames (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT NOT NULL REFERENCES users(telegram_id),
                code            TEXT NOT NULL UNIQUE,
                original_text   TEXT NOT NULL,
                converted_text  TEXT NOT NULL,
                font_name       TEXT NOT NULL,
                saved_at        TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS font_stats (
                font_name       TEXT PRIMARY KEY,
                use_count       INTEGER NOT NULL DEFAULT 0,
                last_used       TEXT
            );
            CREATE TABLE IF NOT EXISTS bot_settings (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            );
        """)
        # Seed default maintenance rows
        await conn.execute("""
            INSERT INTO bot_settings (key, value)
            VALUES
                ('maintenance_enabled', 'false'),
                ('maintenance_message', '🔧 Bot is under maintenance. Back shortly!')
            ON CONFLICT (key) DO NOTHING;
        """)
    logger.info("PostgreSQL database initialised")

# ─────────────────────────────────────────────
#  Users
# ─────────────────────────────────────────────
async def register_user(telegram_id: int, username: str | None, first_name: str | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, first_name, joined_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO NOTHING
        """, telegram_id, username, first_name, datetime.utcnow().isoformat())

async def get_total_users() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) FROM users")
        return row[0] if row else 0

async def get_all_user_ids() -> list[int]:
    """Return every registered user ID (used for broadcasts)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM users")
        return [row["telegram_id"] for row in rows]

# ─────────────────────────────────────────────
#  Saved Nicknames
# ─────────────────────────────────────────────
async def save_nickname(user_id, original_text, converted_text, font_name):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("""
            SELECT id FROM saved_nicknames
            WHERE user_id = $1 AND converted_text = $2 AND font_name = $3
        """, user_id, converted_text, font_name)
        if existing:
            return False, "already_saved"

        while True:
            code = generate_code()
            exists = await conn.fetchrow(
                "SELECT id FROM saved_nicknames WHERE code = $1", code
            )
            if not exists:
                break

        await conn.execute("""
            INSERT INTO saved_nicknames
                (user_id, code, original_text, converted_text, font_name, saved_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, user_id, code, original_text, converted_text, font_name, datetime.utcnow().isoformat())
        return True, code

async def get_saved_nicknames(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, code, original_text, converted_text, font_name, saved_at
            FROM saved_nicknames
            WHERE user_id = $1
            ORDER BY saved_at DESC
        """, user_id)
        return [dict(r) for r in rows]

async def delete_saved_nickname_by_code(user_id: int, code: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM saved_nicknames WHERE code = $1 AND user_id = $2", code, user_id
        )
        return result == "DELETE 1"

async def get_saved_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM saved_nicknames WHERE user_id = $1", user_id
        )
        return count or 0

# ─────────────────────────────────────────────
#  Font Stats
# ─────────────────────────────────────────────
async def increment_font_stat(font_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO font_stats (font_name, use_count, last_used)
            VALUES ($1, 1, $2)
            ON CONFLICT (font_name) DO UPDATE SET
                use_count = font_stats.use_count + 1,
                last_used = EXCLUDED.last_used
        """, font_name, datetime.utcnow().isoformat())

async def get_top_fonts(limit: int = 5) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT font_name, use_count FROM font_stats
            ORDER BY use_count DESC LIMIT $1
        """, limit)
        return [dict(r) for r in rows]

async def get_total_font_uses() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT SUM(use_count) FROM font_stats")
        return val or 0

# ─────────────────────────────────────────────
#  Maintenance
# ─────────────────────────────────────────────
async def get_maintenance_state() -> tuple[bool, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value FROM bot_settings WHERE key IN ('maintenance_enabled', 'maintenance_message')"
        )
        settings = {row["key"]: row["value"] for row in rows}
        enabled  = settings.get("maintenance_enabled", "false").lower() == "true"
        message  = settings.get("maintenance_message", "")
        return enabled, message

async def set_maintenance_state(enabled: bool, message: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO bot_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            [
                ("maintenance_enabled", str(enabled).lower()),
                ("maintenance_message", message),
            ],
        )