import json
import asyncio
import logging
import time
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ForceReply
from maintenance import ADMIN_IDS
from datetime import datetime, timezone
from database import (
    init_db, register_user,
    get_total_users, get_total_font_uses, get_top_fonts,
    save_nickname, get_saved_nicknames, delete_saved_nickname_by_code,
    get_saved_count, increment_font_stat,
    get_new_users_today, get_total_nicknames_saved,
)
from maintenance import (
    maintenance_router,
    MaintenanceMiddleware,
    init_maintenance,
)

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("FontStyleBot")
logger.info("Bot starting up...")

# ─────────────────────────────────────────────
#  In-memory session state (per message)
# ─────────────────────────────────────────────
user_original_texts: dict[str, str] = {}
user_current_pages:  dict[str, int] = {}
user_current_fonts:  dict[str, int | None] = {}
user_session_times:  dict[str, float] = {}
saved_list_message_ids: dict[int, int] = {}

SESSION_TTL = 60 * 30  # 30 minutes

def touch_session(user_key: str):
    user_session_times[user_key] = time.time()

def cleanup_sessions():
    now = time.time()
    expired = [k for k, t in user_session_times.items() if now - t > SESSION_TTL]
    for k in expired:
        user_original_texts.pop(k, None)
        user_current_pages.pop(k, None)
        user_current_fonts.pop(k, None)
        user_session_times.pop(k, None)
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired sessions")


# ─────────────────────────────────────────────
#  Bot setup
# ─────────────────────────────────────────────
BOT_TOKEN = "8885186472:AAGNjhlEWjosQTpNBYbqP9YLlxlBZM4cO6U"

session = AiohttpSession(timeout=30)
default_properties = DefaultBotProperties(parse_mode="HTML")
bot = Bot(token=BOT_TOKEN, session=session, default=default_properties)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ─────────────────────────────────────────────
#  Maintenance middleware + router  ← NEW
# ─────────────────────────────────────────────
dp.message.middleware(MaintenanceMiddleware())
dp.callback_query.middleware(MaintenanceMiddleware())
dp.include_router(maintenance_router)

BotCommands = ["/", ".", "!", "#", "$"]

# ─────────────────────────────────────────────
#  FSM States
# ─────────────────────────────────────────────
class NickStates(StatesGroup):
    waiting_for_nick_text = State()

# ─────────────────────────────────────────────
#  Fonts
# ─────────────────────────────────────────────
FONTS_FILE = Path("fonts.json")
fonts: list[dict] = []

def load_fonts():
    global fonts
    if not FONTS_FILE.exists():
        raise FileNotFoundError("fonts.json missing")
    with open(FONTS_FILE, "r", encoding="utf-8") as f:
        fonts = json.load(f)
    logger.info(f"Loaded {len(fonts)} fonts")

# ─────────────────────────────────────────────
#  Text conversion
# ─────────────────────────────────────────────
LEET_MAP = {
    'a': '4', 'b': 'b', 'c': 'c', 'd': 'd', 'e': '3', 'f': 'f',
    'g': '9', 'h': 'h', 'i': '1', 'j': 'j', 'k': 'k', 'l': '1',
    'm': 'm', 'n': 'n', 'o': '0', 'p': 'p', 'q': 'q', 'r': 'r',
    's': '5', 't': '7', 'u': 'u', 'v': 'v', 'w': 'w', 'x': 'x',
    'y': 'y', 'z': '2',
    'A': '4', 'B': 'B', 'C': 'C', 'D': 'D', 'E': '3', 'F': 'F',
    'G': '9', 'H': 'H', 'I': '1', 'J': 'J', 'K': 'K', 'L': '1',
    'M': 'M', 'N': 'N', 'O': '0', 'P': 'P', 'Q': 'Q', 'R': 'R',
    'S': '5', 'T': '7', 'U': 'U', 'V': 'V', 'W': 'W', 'X': 'X',
    'Y': 'Y', 'Z': '2',
}

def convert_text(text: str, font_data: dict) -> str:
    combiner = font_data.get("combiner")
    if combiner:
        return "".join(ch + combiner if ch.strip() else ch for ch in text)

    if font_data.get("leet"):
        return "".join(LEET_MAP.get(ch, ch) for ch in text)
    lower_raw  = font_data.get("fontLower", "")
    upper_raw  = font_data.get("fontUpper", "")
    digits_raw = font_data.get("fontDigits", "")
    lower_map  = {chr(97 + i): lower_raw[i]  for i in range(min(len(lower_raw),  26))} if lower_raw  else {}
    upper_map  = {chr(65 + i): upper_raw[i]  for i in range(min(len(upper_raw),  26))} if upper_raw  else {}
    digits_map = {chr(48 + i): digits_raw[i] for i in range(min(len(digits_raw), 10))} if digits_raw else {}

    result = []
    for char in text:
        if char.islower():   result.append(lower_map.get(char, char))
        elif char.isupper(): result.append(upper_map.get(char, char))
        elif char.isdigit(): result.append(digits_map.get(char, char))
        else:                result.append(char)
    return "".join(result)

def get_button_text(font_data: dict) -> str:
    if font_data.get("combiner") or font_data.get("leet"):
        return font_data["fontName"]
    return convert_text(font_data["fontName"], font_data)

# ─────────────────────────────────────────────
#  Keyboards
# ─────────────────────────────────────────────
def get_nickname_menu_keyboard(user_id: int = None):
    keyboard = [
        [KeyboardButton(text="🖌🖌 Create a Nickname 🖌🖌")],
        [KeyboardButton(text="🗃 My Nicknames")],
        [KeyboardButton(text="📗 About the Bot")],
    ]
    
    # Only show Admin Panel button to admins
    if user_id and user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="⚙️ Admin Panel")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_keyboard(page: int = 0, active_font_idx: int = None):
    buttons_per_page = 21
    buttons_per_row  = 3
    start = page * buttons_per_page
    end   = start + buttons_per_page
    current_fonts = fonts[start:end]
    total_pages   = (len(fonts) + buttons_per_page - 1) // buttons_per_page

    keyboard = []
    row = []
    for font_idx in range(start, end):
        if font_idx >= len(fonts):
            break
        font = fonts[font_idx]
        btn_text = get_button_text(font)
        if not btn_text.strip():
            btn_text = font["fontName"]
        if font_idx == active_font_idx:
            btn_text = f"✅ {font['fontName']}"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"font_{font_idx}"))
        if len(row) == buttons_per_row:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    has_next = end < len(fonts)

    if active_font_idx is not None:
        keyboard.append([InlineKeyboardButton(text="⭐ Save Nickname", callback_data="save_nick")])

    if page == 0:
        nav = []
        if has_next:
            nav.append(InlineKeyboardButton(text="Next ⇀", callback_data=f"page_{page+1}"))
        nav.append(InlineKeyboardButton(text="⤵️ Back", callback_data="close"))
        keyboard.append(nav)
    elif page == total_pages - 1:
        keyboard.append([
            InlineKeyboardButton(text="↼ Previous", callback_data=f"page_{page-1}"),
            InlineKeyboardButton(text="⤵️ Back", callback_data="close"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text="↼ Previous", callback_data=f"page_{page-1}"),
            InlineKeyboardButton(text="Next ⇀", callback_data=f"page_{page+1}"),
        ])
        keyboard.append([InlineKeyboardButton(text="⤵️ Back", callback_data="close")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def time_ago(saved_at: str) -> str:
    try:
        saved = datetime.fromisoformat(saved_at).replace(tzinfo=timezone.utc)
        diff  = datetime.now(timezone.utc) - saved
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        elif seconds < 604800:
            return f"{seconds // 86400}d ago"
        else:
            return f"{seconds // 604800}w ago"
    except Exception:
        return ""

async def build_saved_nicknames_message(nicknames: list[dict], page: int = 0):
    per_page    = 8
    start       = page * per_page
    chunk       = nicknames[start:start + per_page]
    total_pages = (len(nicknames) + per_page - 1) // per_page

    lines = []
    for nick in chunk:
        ago = time_ago(nick["saved_at"])
        lines.append(
            f"▪️ <code>{nick['converted_text']}</code>  ← tap to copy\n"
            f"   <i>Style: {nick['font_name']} • {ago}</i>  ❌ /del{nick['code']}\n"
        )

    text = (
        f"🗃 <b>My Saved Nicknames</b> ({len(nicknames)})\n\n"
        + "\n".join(lines)
        + "\n<i>Tap /delCAYXXXX to delete</i>"
    )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="↼ Prev", callback_data=f"savedpage_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ⇀", callback_data=f"savedpage_{page+1}"))

    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="⤵️ Back", callback_data="close_saved")])

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
async def remove_reply_keyboard(message: types.Message):
    dummy = await message.answer("ㅤ", reply_markup=ReplyKeyboardRemove(), disable_notification=True)
    await dummy.delete()

START_MSG = """
<b>In short, in this bot, you can create your nickname using various decorations and fonts, and save it so you can find it whenever you need it!!</b>

<i>If there are any errors, shortcomings, suggestions, or criticisms, you can feel free to write to @caydigitals 🤝🙋‍♂️</i>"""

# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────
@dp.message(Command(commands=["start"], prefix=BotCommands))
async def cmd_start(message: types.Message):
    user = message.from_user
    is_new = await register_user(user.id, user.username, user.first_name)
    
    await message.answer(
        "<b>Select an option below to create your unique nickname.</b>",
        reply_markup=get_nickname_menu_keyboard(user.id),
        parse_mode="HTML",
    )

    # ── Notify admins if brand new user ──
    if is_new:
        username_display = f"@{user.username}" if user.username else "No username"
        notif_text = (
            f"👤 <b>New User Joined!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🙍 <b>Name:</b> {user.first_name}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📛 <b>Username:</b> {username_display}\n"
            f"🕒 <b>Time:</b> {datetime.now(timezone.utc).strftime('%B %d, %Y %I:%M %p')} UTC"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(chat_id=admin_id, text=notif_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")

    logger.info(f"User {user.id} started the bot")

# ─────────────────────────────────────────────
#  /admin
# ─────────────────────────────────────────────
async def _auto_delete_toast(msg: types.Message, delay: int = 2):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

@dp.message(F.text == "⚙️ Admin Panel")
async def handle_admin_panel_button(message: types.Message, state: FSMContext):
    from maintenance import ADMIN_IDS, _admin_text, _admin_keyboard
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await remove_reply_keyboard(message)
    await message.answer(
        await _admin_text(), 
        reply_markup=_admin_keyboard(),
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────
#  /delCAYXXXX — delete saved nickname by code
# ─────────────────────────────────────────────
@dp.message(F.text.regexp(r"^/delCAY\d{4}$"))
async def handle_del_command(message: types.Message):
    code = message.text.strip().lstrip("/del")

    try:
        await message.delete()
    except Exception:
        pass

    deleted = await delete_saved_nickname_by_code(message.from_user.id, code)
    nicknames = await get_saved_nicknames(message.from_user.id)
    list_msg_id = saved_list_message_ids.get(message.from_user.id)

    if deleted:
        # ── Show a brief toast then auto-delete it ──
        toast = await message.answer("✅ <b>Nickname deleted!</b>", parse_mode="HTML")
        asyncio.create_task(_auto_delete_toast(toast, delay=2))

        if nicknames:
            text, kb = await build_saved_nicknames_message(nicknames, page=0)
            if list_msg_id:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=list_msg_id,
                        text=text,
                        reply_markup=kb,
                        parse_mode="HTML",
                    )
                except Exception:
                    sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
                    saved_list_message_ids[message.from_user.id] = sent.message_id
            else:
                sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
                saved_list_message_ids[message.from_user.id] = sent.message_id
        else:
            saved_list_message_ids.pop(message.from_user.id, None)
            if list_msg_id:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=list_msg_id,
                        text="🗃 <b>My Saved Nicknames</b>\n\nNo saved nicknames left.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="⤵️ Back", callback_data="close_saved")]
                        ]),
                        parse_mode="HTML",
                    )
                except Exception:
                    await message.answer(
                        "🗃 <b>My Saved Nicknames</b>\n\nNo saved nicknames left.",
                        parse_mode="HTML",
                        reply_markup=get_nickname_menu_keyboard(message.from_user.id),
                    )
            else:
                await message.answer(
                    "🗃 <b>My Saved Nicknames</b>\n\nNo saved nicknames left.",
                    parse_mode="HTML",
                    reply_markup=get_nickname_menu_keyboard(message.from_user.id),
                )
    else:
        toast = await message.answer("❌ <b>Couldn't delete — code not found or doesn't belong to you.</b>", parse_mode="HTML")
        asyncio.create_task(_auto_delete_toast(toast, delay=3))

# ─────────────────────────────────────────────
#  Create Nickname flow
# ─────────────────────────────────────────────
@dp.message(F.text.in_(["✏️ Nick yasash ✏️", "🖌🖌 Create a Nickname 🖌🖌"]))
async def handle_nick_yasash(message: types.Message, state: FSMContext):
    await register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await state.set_state(NickStates.waiting_for_nick_text)
    await message.answer(
        "<b>Enter your nickname (alias)</b>\n<i>Example: Cay</i>",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True, input_field_placeholder="Message"),
    )

@dp.message(NickStates.waiting_for_nick_text)
async def handle_nick_text_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()
    await remove_reply_keyboard(message)

    kb   = get_keyboard(0)
    sent = await message.answer(
        f"<b>Ready: {text}</b>\n"
        f"---------------------------------------------\n\n"
        f"◼️ Copy: <code>{text}</code> 👉 (select a font ☝️)\n"
        f"◻️ Original: <code>{text}</code>",
        reply_markup=kb,
    )

    user_key = f"{message.chat.id}_{sent.message_id}"
    user_original_texts[user_key] = text
    user_current_pages[user_key]  = 0
    user_current_fonts[user_key]  = None
    touch_session(user_key)

# ─────────────────────────────────────────────
#  Font selection
# ─────────────────────────────────────────────
@dp.callback_query(F.data.startswith("font_"))
async def process_font_selection(callback: types.CallbackQuery):
    try:
        font_idx = int(callback.data.split("_")[1])
        if font_idx < 0 or font_idx >= len(fonts):
            await callback.answer("❌ Invalid Font Selected!", show_alert=True)
            return

        font_data  = fonts[font_idx]
        font_name  = font_data["fontName"]
        user_key   = f"{callback.message.chat.id}_{callback.message.message_id}"
        orig_text  = user_original_texts.get(user_key, "")
        cur_page   = user_current_pages.get(user_key, 0)
        cur_font   = user_current_fonts.get(user_key)

        if cur_font == font_idx:
            await callback.answer(f"❌ Already Applied {font_name} Style", show_alert=True)
            return

        if not orig_text:
            lines     = (callback.message.text or "").split("\n\n", 1)
            orig_text = lines[1] if len(lines) > 1 else callback.message.text or ""

        converted = convert_text(orig_text, font_data)
        kb        = get_keyboard(cur_page, active_font_idx=font_idx)

        await callback.message.edit_text(
            f"<b>{font_idx + 1}. Ready: {converted}</b>\n"
            f"---------------------------------------------\n\n"
            f"◼️ <b>Copy:</b> <code>{converted}</code> 👈 ({font_name})\n"
            f"◻️ <b>Original:</b> {orig_text}",
            reply_markup=kb,
        )

        user_current_fonts[user_key] = font_idx
        touch_session(user_key)
        await increment_font_stat(font_name)
        await callback.answer(f"✨ {font_name} Style Applied!", show_alert=False)
        logger.info(f"User {callback.from_user.id} applied font '{font_name}'")

    except Exception as e:
        logger.error(f"Error in font selection: {e}")
        await callback.answer("❌ Sorry, failed to apply style!", show_alert=True)

# ─────────────────────────────────────────────
#  Save Nickname
# ─────────────────────────────────────────────
@dp.callback_query(F.data == "save_nick")
async def process_save_nick(callback: types.CallbackQuery):
    user_key  = f"{callback.message.chat.id}_{callback.message.message_id}"
    font_idx  = user_current_fonts.get(user_key)
    orig_text = user_original_texts.get(user_key, "")

    if font_idx is None or not orig_text:
        await callback.answer("❌ No font selected yet!", show_alert=True)
        return

    font_data = fonts[font_idx]
    font_name = font_data["fontName"]
    converted = convert_text(orig_text, font_data)

    await register_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)

    success, result = await save_nickname(
        user_id=callback.from_user.id,
        original_text=orig_text,
        converted_text=converted,
        font_name=font_name,
    )

    if success:
        saved_count = await get_saved_count(callback.from_user.id)
        await callback.answer(
            f"✅ Nickname saved!\n"
            f"Code: {result}\n"
            f"You have {saved_count} nicknames saved.",
            show_alert=True,
        )
    elif result == "already_saved":
        await callback.answer("📋 Already in your saved list!", show_alert=True)

# ─────────────────────────────────────────────
#  My Nicknames
# ─────────────────────────────────────────────
@dp.message(F.text == "🗃 My Nicknames")
async def handle_my_nicknames(message: types.Message):
    await register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await remove_reply_keyboard(message)

    nicknames = await get_saved_nicknames(message.from_user.id)
    if not nicknames:
        await message.answer(
            "🗃 <b>My Saved Nicknames</b>\n\nYou haven't saved any nicknames yet.\n"
            "Create one and tap <b>⭐ Save Nickname</b>!",
            parse_mode="HTML",
            reply_markup=get_nickname_menu_keyboard(message.from_user.id),
        )
        return

    text, kb = await build_saved_nicknames_message(nicknames, page=0)
    sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    # ── Store the message ID so /del can edit it later ──
    saved_list_message_ids[message.from_user.id] = sent.message_id

@dp.callback_query(F.data.startswith("savedpage_"))
async def process_saved_page(callback: types.CallbackQuery):
    page      = int(callback.data.split("_")[1])
    nicknames = await get_saved_nicknames(callback.from_user.id)
    text, kb  = await build_saved_nicknames_message(nicknames, page=page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "close_saved")
async def process_close_saved(callback: types.CallbackQuery):
    try:
        # ── Clean up stored message ID ──
        saved_list_message_ids.pop(callback.from_user.id, None)
        
        await callback.message.delete()
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Back to the main menu.",
            reply_markup=get_nickname_menu_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error closing saved menu: {e}")

# ─────────────────────────────────────────────
#  About
# ─────────────────────────────────────────────
@dp.message(F.text == "📗 About the Bot")
async def handle_about_bot(message: types.Message):
    total_users      = await get_total_users()
    total_fonts_used = await get_total_font_uses()

    stats_header = (
        f"👥 <b>Active Users:</b> {total_users}\n"
        f"🎨 <b>Total Font Styles:</b> {len(fonts)}\n"
        f"📜 <b>Total Font Applications:</b> {total_fonts_used}\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📢 Updates Channel", url="https://t.me/caysredirect"),
        InlineKeyboardButton(text="⤵️ Back", callback_data="close_about"),
    ]])
    await remove_reply_keyboard(message)
    await message.answer(stats_header + START_MSG, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "close_about")
async def process_close_about(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Back to the main menu.",
            reply_markup=get_nickname_menu_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )
        await callback.answer("⤵️ Back", show_alert=False)
    except Exception as e:
        logger.error(f"Error closing about menu: {e}")
        await callback.answer("❌ Failed to close!", show_alert=True)

# ─────────────────────────────────────────────
#  Pagination
# ─────────────────────────────────────────────
@dp.callback_query(F.data.startswith("page_"))
async def process_pagination(callback: types.CallbackQuery):
    try:
        page     = int(callback.data.split("_")[1])
        user_key = f"{callback.message.chat.id}_{callback.message.message_id}"
        user_current_pages[user_key] = page
        active   = user_current_fonts.get(user_key)
        kb       = get_keyboard(page, active_font_idx=active)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer(f"📄 Page {page + 1}", show_alert=False)
    except Exception as e:
        logger.error(f"Error in pagination: {e}")
        await callback.answer("❌ Failed to navigate!", show_alert=True)

# ─────────────────────────────────────────────
#  Close font picker
# ─────────────────────────────────────────────
@dp.callback_query(F.data == "close")
async def process_close(callback: types.CallbackQuery):
    user_key = f"{callback.message.chat.id}_{callback.message.message_id}"
    user_original_texts.pop(user_key, None)
    user_current_pages.pop(user_key, None)
    user_current_fonts.pop(user_key, None)
    user_session_times.pop(user_key, None)

    try:
        await callback.message.delete()
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Back to the main menu.",
            reply_markup=get_nickname_menu_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )
        await callback.answer("👋 Menu Closed!", show_alert=False)
    except Exception as e:
        logger.error(f"Error closing menu: {e}")
        await callback.answer("❌ Failed to close menu!", show_alert=True)


async def session_cleanup_loop():
    while True:
        await asyncio.sleep(60 * 10)  # run every 10 minutes
        cleanup_sessions()
# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
async def main():
    try:
        load_fonts()
        await init_db()
        await init_maintenance()
        asyncio.create_task(session_cleanup_loop())  # ← add this
        logger.info("Bot Successfully Started 💥")
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=["message", "callback_query"],
        )
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
