"""
maintenance.py
──────────────
Drop-in maintenance mode for FontStyleBot.

Admin commands:
  /maintenance      → toggle ON / OFF
  /setstatus <msg>  → update the message users see
  /endmaintenance   → turn off + broadcast "we're back" to all users
  /adminstatus      → check current state without changing it
"""

import logging
from typing import Callable, Any

from aiogram import Bot, Router, types
from aiogram.filters import Command

from database import (
    get_maintenance_state,
    set_maintenance_state,
    get_all_user_ids,
)

logger = logging.getLogger("FontStyleBot.maintenance")
maintenance_router = Router()

# ─────────────────────────────────────────────
#  ⚠️  Set your Telegram user ID(s) here
# ─────────────────────────────────────────────
ADMIN_IDS: set[int] = {
    7399488750,   # ← replace with your real Telegram ID
}

# ─────────────────────────────────────────────
#  In-process cache  (avoids a DB hit per update)
# ─────────────────────────────────────────────
_maintenance_enabled: bool = False
_maintenance_message: str  = (
    "🔧 <b>Bot is under maintenance</b>\n\n"
    "We'll be back shortly! Follow @caysredirect for updates. 🙏"
)

async def init_maintenance() -> None:
    """Load persisted state from DB into the in-process cache."""
    global _maintenance_enabled, _maintenance_message
    enabled, message = await get_maintenance_state()
    _maintenance_enabled = enabled
    if message:
        _maintenance_message = message
    logger.info(f"Maintenance mode loaded → enabled={_maintenance_enabled}")

def is_maintenance() -> bool:
    return _maintenance_enabled

# ─────────────────────────────────────────────
#  Middleware
# ─────────────────────────────────────────────
class MaintenanceMiddleware:
    """Blocks all updates from non-admins while maintenance is active."""

    async def __call__(
        self,
        handler: Callable,
        event: Any,
        data: dict,
    ) -> Any:
        if not _maintenance_enabled:
            return await handler(event, data)

        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        if user.id in ADMIN_IDS:
            return await handler(event, data)

        if isinstance(event, types.Message):
            await event.answer(_maintenance_message, parse_mode="HTML")
        elif isinstance(event, types.CallbackQuery):
            await event.answer(
                "🔧 Bot is under maintenance. Please wait!",
                show_alert=True,
            )
        return

# ─────────────────────────────────────────────
#  Admin commands
# ─────────────────────────────────────────────
def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@maintenance_router.message(Command("maintenance"))
async def cmd_toggle_maintenance(message: types.Message):
    global _maintenance_enabled
    if not _is_admin(message.from_user.id):
        return

    _maintenance_enabled = not _maintenance_enabled
    await set_maintenance_state(_maintenance_enabled, _maintenance_message)

    status = "🔴 <b>ON</b>" if _maintenance_enabled else "🟢 <b>OFF</b>"
    await message.answer(
        f"🔧 Maintenance mode: {status}\n\n"
        f"<i>Message users will see:</i>\n{_maintenance_message}",
        parse_mode="HTML",
    )
    logger.info(f"Admin {message.from_user.id} → maintenance={_maintenance_enabled}")


@maintenance_router.message(Command("setstatus"))
async def cmd_set_status(message: types.Message):
    """Usage: /setstatus Upgrading the database. Back in ~10 mins!"""
    global _maintenance_message
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: <code>/setstatus Your message here</code>",
            parse_mode="HTML",
        )
        return

    _maintenance_message = parts[1].strip()
    await set_maintenance_state(_maintenance_enabled, _maintenance_message)
    await message.answer(
        f"✅ Maintenance message updated:\n\n{_maintenance_message}",
        parse_mode="HTML",
    )


@maintenance_router.message(Command("endmaintenance"))
async def cmd_end_maintenance(message: types.Message, bot: Bot):
    """Usage: /endmaintenance [optional custom message]"""
    global _maintenance_enabled
    if not _is_admin(message.from_user.id):
        return

    _maintenance_enabled = False
    await set_maintenance_state(False, _maintenance_message)

    parts = message.text.split(maxsplit=1)
    broadcast_text = (
        parts[1].strip()
        if len(parts) > 1
        else "✅ <b>We're back online!</b>\n\nSorry for the wait. Everything is up and running. Enjoy! 🎉"
    )

    status_msg = await message.answer("🟢 Maintenance ended. Broadcasting to all users…")

    user_ids = await get_all_user_ids()
    sent = failed = 0

    for uid in user_ids:
        try:
            await bot.send_message(uid, broadcast_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"📢 <b>Broadcast complete!</b>\n\n"
        f"✅ Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
    )
    logger.info(f"End-maintenance broadcast: sent={sent} failed={failed}")


@maintenance_router.message(Command("adminstatus"))
async def cmd_admin_status(message: types.Message):
    if not _is_admin(message.from_user.id):
        return

    status = "🔴 ON" if _maintenance_enabled else "🟢 OFF"
    await message.answer(
        f"🔧 <b>Maintenance:</b> {status}\n\n"
        f"<b>Current message:</b>\n{_maintenance_message}",
        parse_mode="HTML",
    )