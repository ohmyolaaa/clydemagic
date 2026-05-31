import random
import string
import asyncpg
import logging
import os
from datetime import datetime

logger = logging.getLogger("FontStyleBot.DB")

MAX_SAVED_PER_USER = 20

DATABASE_URL = os.environ["DATABASE_URL"]

def generate_code() -> str:
    digits = ''.join(random.choices(string.digits, k=4))
    return f"CAY{digits}"

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
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
    """)
    await conn.close()
    logger.info("PostgreSQL database initialised")

async def register_user(telegram_id: int, username: str | None, first_name: str | None):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO users (telegram_id, username, first_name, joined_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (telegram_id) DO NOTHING
    """, telegram_id, username, first_name, datetime.utcnow().isoformat())
    await conn.close()

async def get_total_users() -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT COUNT(*) FROM users")
    await conn.close()
    return row[0] if row else 0

async def save_nickname(user_id, original_text, converted_text, font_name):
    conn = await asyncpg.connect(DATABASE_URL)
    # Check duplicate
    existing = await conn.fetchrow("""
        SELECT id FROM saved_nicknames
        WHERE user_id = $1 AND converted_text = $2 AND font_name = $3
    """, user_id, converted_text, font_name)
    if existing:
        await conn.close()
        return False, "already_saved"

    # Check limit
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM saved_nicknames WHERE user_id = $1", user_id
    )
    if count >= MAX_SAVED_PER_USER:
        await conn.close()
        return False, "limit_reached"

    # Generate unique code
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
    await conn.close()
    return True, code

async def get_saved_nicknames(user_id: int) -> list[dict]:
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT id, code, original_text, converted_text, font_name, saved_at
        FROM saved_nicknames
        WHERE user_id = $1
        ORDER BY saved_at DESC
    """, user_id)
    await conn.close()
    return [dict(r) for r in rows]

async def delete_saved_nickname_by_code(user_id: int, code: str) -> bool:
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute(
        "DELETE FROM saved_nicknames WHERE code = $1 AND user_id = $2", code, user_id
    )
    await conn.close()
    return result == "DELETE 1"

async def get_saved_count(user_id: int) -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM saved_nicknames WHERE user_id = $1", user_id
    )
    await conn.close()
    return count or 0

async def increment_font_stat(font_name: str):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO font_stats (font_name, use_count, last_used)
        VALUES ($1, 1, $2)
        ON CONFLICT (font_name) DO UPDATE SET
            use_count = font_stats.use_count + 1,
            last_used = EXCLUDED.last_used
    """, font_name, datetime.utcnow().isoformat())
    await conn.close()

async def get_top_fonts(limit: int = 5) -> list[dict]:
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT font_name, use_count FROM font_stats
        ORDER BY use_count DESC LIMIT $1
    """, limit)
    await conn.close()
    return [dict(r) for r in rows]

async def get_total_font_uses() -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    val = await conn.fetchval("SELECT SUM(use_count) FROM font_stats")
    await conn.close()
    return val or 0