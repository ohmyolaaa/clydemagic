"""
database.py — Async SQLite database layer for FontStyleBot
Tables:
    users           — registered users
    saved_nicknames — user's favorite saved nicknames
    font_stats      — per-font usage counters
"""
import random
import string
import aiosqlite
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("FontStyleBot.DB")

DB_PATH = Path("bot_data.db")

def generate_code() -> str:
    digits = ''.join(random.choices(string.digits, k=4))
    return f"CAY{digits}"

# ─────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id     INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    joined_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_nicknames (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(telegram_id),
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
"""

# ─────────────────────────────────────────────
#  Init
# ─────────────────────────────────────────────
async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
    logger.info(f"Database initialised at {DB_PATH}")

# ─────────────────────────────────────────────
#  Users
# ─────────────────────────────────────────────
async def register_user(telegram_id: int, username: str | None, first_name: str | None):
    """Insert user if not already present (ignore on conflict)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (telegram_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
            """,
            (telegram_id, username, first_name, datetime.utcnow().isoformat()),
        )
        await db.commit()

async def get_total_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# ─────────────────────────────────────────────
#  Saved Nicknames
# ─────────────────────────────────────────────
MAX_SAVED_PER_USER = 20

async def save_nickname(
    user_id: int,
    original_text: str,
    converted_text: str,
    font_name: str,
) -> tuple[bool, str]:
    """
    Save a nickname for a user.
    Returns (success: bool, message: str).
    Enforces MAX_SAVED_PER_USER limit.
    Prevents exact duplicate (same converted_text + font_name).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Check for duplicate
        async with db.execute(
            """
            SELECT id FROM saved_nicknames
            WHERE user_id = ? AND converted_text = ? AND font_name = ?
            """,
            (user_id, converted_text, font_name),
        ) as cursor:
            if await cursor.fetchone():
                return False, "already_saved"

        # Check limit
        async with db.execute(
            "SELECT COUNT(*) FROM saved_nicknames WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0

        if count >= MAX_SAVED_PER_USER:
            return False, "limit_reached"

        # Generate a unique code
        code = None
        while True:
            candidate = generate_code()
            async with db.execute(
                "SELECT id FROM saved_nicknames WHERE code = ?", (candidate,)
            ) as cur:
                if not await cur.fetchone():
                    code = candidate
                    break

        await db.execute(
            """
            INSERT INTO saved_nicknames
                (user_id, code, original_text, converted_text, font_name, saved_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                code,
                original_text,
                converted_text,
                font_name,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        return True, code  # return the code so bot.py can show it


async def get_saved_nicknames(user_id: int) -> list[dict]:
    """Return all saved nicknames for a user, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, code, original_text, converted_text, font_name, saved_at
            FROM saved_nicknames
            WHERE user_id = ?
            ORDER BY saved_at DESC
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_saved_nickname_by_code(user_id: int, code: str) -> bool:
    """Delete a specific saved nickname by code. Returns True if deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM saved_nicknames WHERE code = ? AND user_id = ?",
            (code, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_saved_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM saved_nicknames WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# ─────────────────────────────────────────────
#  Font Stats
# ─────────────────────────────────────────────
async def increment_font_stat(font_name: str):
    """Upsert font usage counter."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO font_stats (font_name, use_count, last_used)
            VALUES (?, 1, ?)
            ON CONFLICT(font_name) DO UPDATE SET
                use_count = use_count + 1,
                last_used = excluded.last_used
            """,
            (font_name, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_top_fonts(limit: int = 5) -> list[dict]:
    """Return top fonts by usage count."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT font_name, use_count
            FROM font_stats
            ORDER BY use_count DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_total_font_uses() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT SUM(use_count) FROM font_stats") as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else 0