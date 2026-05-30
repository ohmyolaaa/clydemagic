import json
import asyncio
import logging
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ForceReply

# Add FSM States
class NickStates(StatesGroup):
    waiting_for_nick_text = State()

# Update Dispatcher to use MemoryStorage
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("FontStyleBot")
logger.info("Bot starting up...")

BOT_TOKEN = "8975741273:AAERFWG11zY8_e9q47qZDjRQsD1oTzOPSas"

# Improved Bot Session with timeout
session = AiohttpSession(timeout=30)
default_properties = DefaultBotProperties(parse_mode="HTML")
bot = Bot(token=BOT_TOKEN, session=session, default=default_properties)

async def remove_reply_keyboard(message: types.Message):
    dummy = await message.answer("ㅤ", reply_markup=ReplyKeyboardRemove(), disable_notification=True)
    await dummy.delete()

# Handle "Nick yasash" button
@dp.message(F.text.in_(["✏️ Nick yasash ✏️", "🖌🖌 Create a Nickname 🖌🖌"]))
async def handle_nick_yasash(message: types.Message, state: FSMContext):
    await state.set_state(NickStates.waiting_for_nick_text)
    await message.answer(
        "<b>Enter your nickname (alias)</b>\n<i>Example: Cay</i>",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True, input_field_placeholder="Message")
        
    )

@dp.message(F.text.in_(["📗 About the Bot"]))
async def handle_about_bot(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Updates Channel", url="https://t.me/caysredirect"),
            InlineKeyboardButton(text="⤵️ Back", callback_data="close_about")
        ],
    ])
    
    await remove_reply_keyboard(message)
    await message.answer(START_MSG, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "close_about")
async def process_close_about(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Back to the main menu.",
            reply_markup=get_nickname_menu_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer("⤵️ Back", show_alert=False)
    except Exception as e:
        logger.error(f"Error closing about menu: {e}")
        await callback.answer("❌ Failed to close!", show_alert=True)

@dp.message(NickStates.waiting_for_nick_text)
async def handle_nick_text_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()

    await remove_reply_keyboard(message)

    kb = get_keyboard(0)
    sent_message = await message.answer(
        f"<b>Ready: {text}</b>\n"
        f"---------------------------------------------\n\n"
        f"◼️ Copy: <code>{text}</code> 👉 (select a font ☝️)\n"
        f"◻️ Original: <code>{text}</code>",
        reply_markup=kb
    )

    user_key = f"{message.chat.id}_{sent_message.message_id}"
    user_original_texts[user_key] = text
    user_current_pages[user_key] = 0
    user_current_fonts[user_key] = None

    # Remove the "Choose a font style above!" message and get_nickname_menu_keyboard here
    # The reply keyboard will reappear automatically when user closes the inline menu

FONTS_FILE = Path("fonts.json")
fonts = []
user_original_texts = {}
user_current_pages = {}
user_current_fonts = {}

BotCommands = ["/", ".", "!", "#", "$"]

START_MSG = """👋 <b>Welcome to Cay Magic 🖌 Bot!</b>

<b>In short, in this bot, you can create your nickname using various decorations and fonts, and save it so you can find it whenever you need it!!</b>

🔒 Works in <b>Private, Groups & Supergroups</b>

<i>If there are any errors, shortcomings, suggestions, or criticisms, you can feel free to write to @caydigitals 🤝🙋‍♂️</i>"""

def get_nickname_menu_keyboard():
    """Updated menu with minimize/close button"""
    keyboard = [
        [KeyboardButton(text="🖌🖌 Create a Nickname 🖌🖌")],
        # [KeyboardButton(text="🗃 My Nicknames")],
        [KeyboardButton(text="📗 About the Bot")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )

async def show_nickname_start(message: types.Message):
    """New /start flow you requested"""
    text = "<b>Select an option below to create your unique nickname.</b>"
    
    await message.answer(
        text=text,
        reply_markup=get_nickname_menu_keyboard(),
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} opened the new nickname menu")

def load_fonts():
    global fonts
    if not FONTS_FILE.exists():
        logger.error("fonts.json file not found in the current directory!")
        raise FileNotFoundError("fonts.json missing")
    
    try:
        with open(FONTS_FILE, "r", encoding="utf-8") as f:
            fonts = json.load(f)
        logger.info(f"Successfully loaded {len(fonts)} fonts from fonts.json")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in fonts.json: {e}")
        raise

def convert_text(text: str, font_data: dict) -> str:
    lower = font_data.get("fontLower", "")
    upper = font_data.get("fontUpper", "")
    digits = font_data.get("fontDigits", "")

    lower_map = {}
    upper_map = {}
    digits_map = {}

    if isinstance(lower, list):
        for i in range(min(len(lower), 26)):
            lower_map[chr(97 + i)] = lower[i]
    elif lower:
        for i in range(min(len(lower), 26)):
            lower_map[chr(97 + i)] = lower[i]

    if isinstance(upper, list):
        for i in range(min(len(upper), 26)):
            upper_map[chr(65 + i)] = upper[i]
    elif upper:
        for i in range(min(len(upper), 26)):
            upper_map[chr(65 + i)] = upper[i]

    if isinstance(digits, list):
        for i in range(min(len(digits), 10)):
            digits_map[chr(48 + i)] = digits[i]
    elif digits:
        for i in range(min(len(digits), 10)):
            digits_map[chr(48 + i)] = digits[i]

    result = []
    for char in text:
        if char.islower():
            result.append(lower_map.get(char, char))
        elif char.isupper():
            result.append(upper_map.get(char, char))
        elif char.isdigit():
            result.append(digits_map.get(char, char))
        else:
            result.append(char)
    return "".join(result)

def get_button_text(font_data: dict) -> str:
    font_name = font_data["fontName"]
    return convert_text(font_name, font_data)

def get_keyboard(page: int = 0):
    buttons_per_page = 21
    buttons_per_row = 3
    start = page * buttons_per_page
    end = start + buttons_per_page
    current_fonts = fonts[start:end]

    total_pages = (len(fonts) + buttons_per_page - 1) // buttons_per_page

    keyboard = []
    row = []
    for font in current_fonts:
        font_idx = fonts.index(font)
        btn_text = get_button_text(font)
        if not btn_text.strip():
            btn_text = font["fontName"]
        btn = InlineKeyboardButton(
            text=btn_text,
            callback_data=f"font_{font_idx}"
        )
        row.append(btn)
        if len(row) == buttons_per_row:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    has_previous = page > 0
    has_next = end < len(fonts)

    if page == 0:
        if has_next:
            keyboard.append([
                InlineKeyboardButton(text="Next ⇀", callback_data=f"page_{page+1}"),
                InlineKeyboardButton(text="⤵️ Back", callback_data="close")
            ])
        else:
            keyboard.append([InlineKeyboardButton(text="⤵️ Back", callback_data="close")])
    elif page == total_pages - 1:
        keyboard.append([
            InlineKeyboardButton(text="↼ Previous", callback_data=f"page_{page-1}"),
            InlineKeyboardButton(text="⤵️ Back", callback_data="close")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text="Next ⇀", callback_data=f"page_{page+1}"),
            InlineKeyboardButton(text="↼ Previous", callback_data=f"page_{page-1}")
        ])
        keyboard.append([InlineKeyboardButton(text="⤵️ Back", callback_data="close")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command(commands=["start"], prefix=BotCommands))
async def cmd_start(message: types.Message):
    # await message.answer(START_MSG, reply_markup=get_start_keyboard())
    await show_nickname_start(message)
    logger.info(f"User {message.from_user.id} started the bot")

@dp.callback_query(F.data.startswith("page_"))
async def process_pagination(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split("_")[1])
        user_key = f"{callback.message.chat.id}_{callback.message.message_id}"
        user_current_pages[user_key] = page
        
        kb = get_keyboard(page)
        
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer(f"📄 Navigated To Page {page + 1}", show_alert=False)
        logger.debug(f"User {callback.from_user.id} navigated to page {page}")
    except Exception as e:
        logger.error(f"Error in pagination: {e}")
        await callback.answer("❌ Failed To Navigate!", show_alert=True)

@dp.callback_query(F.data.startswith("font_"))
async def process_font_selection(callback: types.CallbackQuery):
    try:
        font_idx = int(callback.data.split("_")[1])
        
        if font_idx < 0 or font_idx >= len(fonts):
            await callback.answer("❌ Invalid Font Selected!", show_alert=True)
            return
        
        font_data = fonts[font_idx]
        font_name = font_data["fontName"]

        user_key = f"{callback.message.chat.id}_{callback.message.message_id}"
        original_text = user_original_texts.get(user_key)
        current_page = user_current_pages.get(user_key, 0)
        current_font_idx = user_current_fonts.get(user_key)
        
        if current_font_idx == font_idx:
            await callback.answer(f"❌ Already Applied {font_name} Style", show_alert=True)
            logger.info(f"User {callback.from_user.id} tried to reapply font '{font_name}'")
            return
        
        if not original_text:
            current_text = callback.message.text or ""
            lines = current_text.split("\n\n", 1)
            if len(lines) > 1:
                original_text = lines[1].replace("<code>", "").replace("</code>", "")
            else:
                original_text = current_text.replace("<code>", "").replace("</code>", "")

        converted = convert_text(original_text, font_data)

        kb = get_keyboard(current_page)

        new_message_text = (
            f"<b>{font_idx + 1}. Ready: {converted}</b>\n"
            f"---------------------------------------------\n\n"
            f"◼️ <b>Copy:</b> <code>{converted}</code> 👈 ({font_name})\n"
            f"◻️ <b>Original:</b> {original_text}"
        )

        await callback.message.edit_text(
            text=new_message_text,
            reply_markup=kb
        )
        
        user_current_fonts[user_key] = font_idx
        
        await callback.answer(f"✨ {font_name} Style Applied!", show_alert=False)
        logger.info(f"User {callback.from_user.id} switched to font '{font_name}'")
        
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await callback.answer("❌ Sorry Failed to apply style!", show_alert=True)

@dp.callback_query(F.data == "close")
async def process_close(callback: types.CallbackQuery):
    user_key = f"{callback.message.chat.id}_{callback.message.message_id}"
    
    if user_key in user_original_texts:
        del user_original_texts[user_key]
    if user_key in user_current_pages:
        del user_current_pages[user_key]
    if user_key in user_current_fonts:
        del user_current_fonts[user_key]
    
    try:
        await callback.message.delete()
        # Restore bottom menu keyboard here after close
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Back to the main menu.",
            reply_markup=get_nickname_menu_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer("👋 Menu Successfully Closed!", show_alert=False)
        logger.info(f"User {callback.from_user.id} closed the style menu")
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        await callback.answer("❌ Failed to close menu!", show_alert=True)

async def main():
    try:
        load_fonts()
        logger.info("Bot Successfully Started 💥")
        
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=["message", "callback_query"]
        )
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
