"""
maintenance.py
──────────────
Drop-in maintenance mode for FontStyleBot.

Single command: /admin
Everything is handled via interactive buttons — no other commands needed.
"""
import asyncio
import logging
from typing import Callable, Any

from aiogram import Bot, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    get_maintenance_state,
    set_maintenance_state,
    get_total_users,
    get_new_users_today,
    get_total_nicknames_saved
)

logger = logging.getLogger("FontStyleBot.maintenance")
maintenance_router = Router()

# ─────────────────────────────────────────────
#  ⚠️  Your Telegram user ID(s)
# ─────────────────────────────────────────────
ADMIN_IDS: set[int] = {
    7399488750,
}

# ─────────────────────────────────────────────
#  FSM — waiting for custom status message input
# ─────────────────────────────────────────────
class AdminStates(StatesGroup):
    waiting_for_status_message = State()

# ─────────────────────────────────────────────
#  In-process cache
# ─────────────────────────────────────────────
_maintenance_enabled: bool = False
_maintenance_message: str  = (
    "🔧 <b>Bot is under maintenance</b>\n\n"
    "We'll be back shortly! Follow @caysredirect for updates. 🙏"
)

async def init_maintenance() -> None:
    global _maintenance_enabled, _maintenance_message
    enabled, message = await get_maintenance_state()
    _maintenance_enabled = enabled
    if message:
        _maintenance_message = message
    logger.info(f"Maintenance mode loaded → enabled={_maintenance_enabled}")

def is_maintenance() -> bool:
    return _maintenance_enabled

# ─────────────────────────────────────────────
#  Admin panel helpers
# ─────────────────────────────────────────────
def _admin_keyboard() -> InlineKeyboardMarkup:
    toggle_label = "🔴 Maintenance: ON  —  tap to turn OFF" if _maintenance_enabled else "🟢 Maintenance: OFF  —  tap to turn ON"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label,           callback_data="admin_toggle")],
        [InlineKeyboardButton(text="✏️ Set Status Message", callback_data="admin_setstatus")],
        [InlineKeyboardButton(text="🔄 Refresh",            callback_data="admin_refresh")],
    ])

async def _admin_text() -> str:
    total_users = await get_total_users()
    new_today   = await get_new_users_today()
    total_nicks = await get_total_nicknames_saved()

    status = "🔴 ON" if _maintenance_enabled else "🟢 OFF"
    return (
        f"🛠 <b>Admin Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔧 <b>Maintenance:</b> {status}\n\n"
        f"👥 <b>Users see:</b>\n"
        f"<i>{_maintenance_message}</i>\n\n"
        f"📊 <b>Stats</b>\n"
        f"├ 👥 Total Users: <b>{total_users}</b>\n"
        f"├ 🆕 New Today: <b>{new_today}</b>\n"
        f"└ 📜 Nicknames Saved: <b>{total_nicks}</b>"
    )

# ─────────────────────────────────────────────
#  Middleware
# ─────────────────────────────────────────────
class MaintenanceMiddleware:
    async def __call__(self, handler: Callable, event: Any, data: dict) -> Any:
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
            await event.answer("🔧 Bot is under maintenance. Please wait!", show_alert=True)
        return

# ─────────────────────────────────────────────
#  /admin — open the panel
# ─────────────────────────────────────────────
@maintenance_router.message(Command("admin"))
async def cmd_admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await message.answer(
        await _admin_text(),
        reply_markup=_admin_keyboard(), 
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────
#  Broadcast helpers
# ─────────────────────────────────────────────
async def broadcast_maintenance_off(bot: Bot) -> None:
    from database import get_all_user_ids
    user_ids = await get_all_user_ids()
    success, failed = 0, 0
    for user_id in user_ids:
        try:
            await bot.send_message(
                chat_id=user_id,
                text="✅ <b>Bot is back online!</b>\n\nEverything is working again. Enjoy! 🎉",
                parse_mode="HTML",
            )
            success += 1
            await asyncio.sleep(0.05)  # avoid hitting Telegram rate limits
        except Exception:
            failed += 1
    logger.info(f"Broadcast done → sent={success}, failed={failed}")

# ─────────────────────────────────────────────
#  Toggle maintenance (single button, ON↔OFF)
# ─────────────────────────────────────────────
@maintenance_router.callback_query(lambda c: c.data == "admin_toggle")
async def cb_admin_toggle(callback: types.CallbackQuery):
    global _maintenance_enabled
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Not authorised", show_alert=True)
        return

    _maintenance_enabled = not _maintenance_enabled
    await set_maintenance_state(_maintenance_enabled, _maintenance_message)

    toast = "🔴 Maintenance ON" if _maintenance_enabled else "🟢 Maintenance OFF"
    await callback.message.edit_text(
        await _admin_text(), 
        reply_markup=_admin_keyboard(), 
        parse_mode="HTML"
    )
    await callback.answer(toast, show_alert=False)
    logger.info(f"Admin {callback.from_user.id} → maintenance={_maintenance_enabled}")

    # Notify all users when coming back online
    if not _maintenance_enabled:
        asyncio.create_task(broadcast_maintenance_off(callback.bot))

# ─────────────────────────────────────────────
#  Set status message
# ─────────────────────────────────────────────
@maintenance_router.callback_query(lambda c: c.data == "admin_setstatus")
async def cb_admin_setstatus(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Not authorised", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_status_message)
    await callback.message.edit_text(
        "✏️ <b>Type the new maintenance message:</b>\n\n"
        "<i>Send /cancel to go back without changing.</i>",
        parse_mode="HTML",
    )
    await callback.answer()

@maintenance_router.message(AdminStates.waiting_for_status_message)
async def handle_status_input(message: types.Message, state: FSMContext):
    global _maintenance_message
    if message.from_user.id not in ADMIN_IDS:
        return

    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer(
            await _admin_text(), 
            reply_markup=_admin_keyboard(), 
            parse_mode="HTML"
        )
        return

    _maintenance_message = message.text.strip()
    await set_maintenance_state(_maintenance_enabled, _maintenance_message)
    await state.clear()

    # Send a separate confirmation that auto-deletes after 3 seconds
    confirm = await message.answer("✅ Message updated!")
    await message.answer(
        await _admin_text(), 
        reply_markup=_admin_keyboard(), 
        parse_mode="HTML"
    )

    async def _delete_later():
        await asyncio.sleep(3)
        try:
            await confirm.delete()
        except Exception:
            pass

    asyncio.create_task(_delete_later())

# ─────────────────────────────────────────────
#  Refresh panel
# ─────────────────────────────────────────────
@maintenance_router.callback_query(lambda c: c.data == "admin_refresh")
async def cb_admin_refresh(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Not authorised", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            await _admin_text(), 
            reply_markup=_admin_keyboard(), 
            parse_mode="HTML"
        )
        await callback.answer("🔄 Refreshed", show_alert=False)
    except Exception:
        await callback.answer("✅ Already up to date!", show_alert=False)