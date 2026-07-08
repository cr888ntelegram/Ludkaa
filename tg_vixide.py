import asyncio
import logging
import os
import random
import sqlite3
from contextlib import closing

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from telethon import TelegramClient, functions
from telethon.tl import types

# ===== ПЕРЕМЕННЫЕ ДЛЯ RAILWAY =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8257020137:AAFng7pgAacxilMkxGYH8CVO6-yHlQmt3K0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8424002876"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "nihers")
TELETHON_API_ID = int(os.environ.get("TELETHON_API_ID", "32199693"))
TELETHON_API_HASH = os.environ.get("TELETHON_API_HASH", "0f27e89d40cd2a025f98b24bc676c943")
SESSION_PATH = os.environ.get("SESSION_PATH", "gift_session.session")
# ====================================

ROSE_GIFT_ID = 5168103777563050263
GIFT_COMMENT = "Приз за участие - @ludkanihers!"

DB_PATH = os.path.join(os.path.dirname(__file__), "slotbot.db")
SLOT_EMOJI = "🎰"
SYMBOLS = ["bar", "grapes", "lemon", "seven"]

ALLOWED_GROUP = "@ludkanihers"

telethon_client: TelegramClient = None

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("slotbot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

frog_positions = {}


def db_init():
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                spins INTEGER DEFAULT 0,
                jackpots INTEGER DEFAULT 0,
                near_miss INTEGER DEFAULT 0,
                roses_won INTEGER DEFAULT 0
            )
        """)
        con.commit()
    log.info("📊 База данных инициализирована")


def db_bump(user_id: int, username: str, field: str, amount: int = 1):
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("""
            INSERT INTO stats (user_id, username, spins, jackpots, near_miss, roses_won)
            VALUES (?, ?, 0, 0, 0, 0)
            ON CONFLICT(user_id) DO UPDATE SET 
                username=excluded.username
        """, (user_id, username))
        con.execute(f"UPDATE stats SET {field} = {field} + ? WHERE user_id = ?", (amount, user_id))
        con.commit()


def db_get_total_stats():
    with closing(sqlite3.connect(DB_PATH)) as con:
        cur = con.execute("""
            SELECT 
                SUM(spins) as total_spins,
                SUM(roses_won) as total_roses
            FROM stats
        """)
        return cur.fetchone()


def db_get_top(limit: int = 10):
    with closing(sqlite3.connect(DB_PATH)) as con:
        cur = con.execute(
            "SELECT username, jackpots, near_miss, spins FROM stats ORDER BY jackpots DESC, near_miss DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()


def decode_slot(value: int) -> tuple[str, str, str]:
    idx = value - 1
    r1 = idx % 4
    r2 = (idx // 4) % 4
    r3 = (idx // 16) % 4
    return SYMBOLS[r1], SYMBOLS[r2], SYMBOLS[r3]


def build_prize_grid_hidden(winner_user_id: int, message_id: int) -> InlineKeyboardMarkup:
    frog_index = random.randint(0, 24)
    frog_positions[f"{winner_user_id}_{message_id}"] = frog_index
    
    buttons = []
    row = []
    for i in range(25):
        cb_data = f"prize:select:{winner_user_id}:{message_id}:{i}"
        row.append(InlineKeyboardButton(text="❓", callback_data=cb_data))
        if len(row) == 5:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_prize_grid_revealed(winner_user_id: int, message_id: int, selected_index: int) -> InlineKeyboardMarkup:
    frog_index = frog_positions.get(f"{winner_user_id}_{message_id}", 0)
    
    buttons = []
    row = []
    for i in range(25):
        if i == frog_index:
            button_text = f"🐸"
            cb_data = f"prize:revealed:nft:{winner_user_id}"
        else:
            if i == selected_index:
                button_text = f"✅🌹"
            else:
                button_text = f"🌹"
            cb_data = f"prize:revealed:rose:{winner_user_id}"
        
        row.append(InlineKeyboardButton(text=button_text, callback_data=cb_data))
        if len(row) == 5:
            buttons.append(row)
            row = []
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_rose(username: str) -> bool:
    try:
        peer = await telethon_client.get_input_entity(username)
        invoice = types.InputInvoiceStarGift(
            peer=peer,
            gift_id=ROSE_GIFT_ID,
            hide_name=False,
            message=types.TextWithEntities(text=GIFT_COMMENT, entities=[]) if GIFT_COMMENT else None
        )
        form = await telethon_client(functions.payments.GetPaymentFormRequest(invoice=invoice))
        await telethon_client(functions.payments.SendStarsFormRequest(
            form_id=form.form_id,
            invoice=invoice
        ))
        return True
    except Exception as e:
        log.error(f"ошибка отправки розы: {e}")
        return False


@dp.message(F.dice, F.dice.emoji == SLOT_EMOJI)
async def handle_slot(message: Message):
    if message.forward_origin:
        return

    if not message.chat or not message.chat.username:
        return
    
    if f"@{message.chat.username.lower()}" != ALLOWED_GROUP.lower():
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    
    db_bump(user.id, username, "spins")

    value = message.dice.value
    r1, r2, r3 = decode_slot(value)
    
    sevens = [r1, r2, r3].count("seven")

    if sevens == 3:
        db_bump(user.id, username, "jackpots")
        
        await message.reply(
            f"🎰 <b>ДЖЕКПОТ!</b>\n\n"
            f"🎉 {username} сорвал банк!\n\n"
            f"👇 <b>Выбери слот:</b>\n"
            f"За одним из них спрятана 🐸 NFT\n"
            f"Остальные — 🌹 розы!",
            reply_markup=build_prize_grid_hidden(user.id, message.message_id)
        )

    elif sevens == 2:
        db_bump(user.id, username, "near_miss")
        await message.reply(
            f"⭐ <b>Почти джекпот!</b>\n\n"
            f"{username}, тебе не хватило одной семерки!\n"
            f"Повезет в следующий раз! 🍀"
        )


@dp.callback_query(F.data.startswith("prize:select:"))
async def handle_prize_select(callback: CallbackQuery):
    _, _, winner_id_str, message_id_str, index_str = callback.data.split(":")
    winner_id = int(winner_id_str)
    message_id = int(message_id_str)
    selected_index = int(index_str)
    user = callback.from_user

    if user.id != winner_id:
        await callback.answer("❌ Это не твой приз!", show_alert=True)
        return

    frog_index = frog_positions.get(f"{winner_id}_{message_id}", 0)
    username = f"@{user.username}" if user.username else user.full_name
    
    if selected_index == frog_index:
        await callback.message.edit_text(
            f"🐸 <b>NFT НАЙДЕН!</b>\n\n"
            f"{username} нашел 🐸 NFT!\n\n"
            f"🎉 Поздравляем! Это эксклюзивный приз!\n"
            f"@{ADMIN_USERNAME} выдаст NFT вручную",
            reply_markup=build_prize_grid_revealed(winner_id, message_id, selected_index)
        )
        await callback.answer("🐸 Вы нашли NFT!", show_alert=True)
        
        await bot.send_message(
            ADMIN_ID,
            f"🎉 Игрок нашел NFT!\n"
            f"Пользователь: {username} (id <code>{user.id}</code>)\n"
            f"Выдай NFT вручную!"
        )
    else:
        db_bump(user.id, username, "roses_won")
        
        await callback.message.edit_text(
            f"🌹 <b>РОЗА!</b>\n\n"
            f"{username} нашел 🌹 розу!\n\n"
            f"⏳ Отправляем подарок...",
            reply_markup=build_prize_grid_revealed(winner_id, message_id, selected_index)
        )

        sent = await send_rose(user.username)

        if sent:
            await callback.message.edit_text(
                f"🌹 <b>Подарок отправлен!</b>\n\n"
                f"{username}, ты нашел розу!\n"
                f"Проверь свои подарки в Telegram! 🎁",
                reply_markup=build_prize_grid_revealed(winner_id, message_id, selected_index)
            )
        else:
            await callback.message.edit_text(
                f"🌹 <b>Роза найдена!</b>\n\n"
                f"{username} нашел розу!\n\n"
                f"❌ Не удалось отправить автоматически\n"
                f"@{ADMIN_USERNAME} выдаст подарок вручную",
                reply_markup=build_prize_grid_revealed(winner_id, message_id, selected_index)
            )
            await bot.send_message(
                ADMIN_ID,
                f"❌ Не смог отправить розу автоматически\n"
                f"Пользователь: {username} (id <code>{user.id}</code>)\n"
                f"Выдай вручную!"
            )

        await callback.answer("🌹 Вы нашли розу!", show_alert=True)


@dp.message(Command("top"))
async def cmd_top(message: Message):
    """Топ игроков - только для админа"""
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Эта команда только для администратора!")
        return
    
    rows = db_get_top()
    if not rows:
        await message.reply("🏆 Пока никто не крутил слот")
        return

    lines = ["🏆 <b>ТОП ИГРОКОВ</b>\n"]
    for i, (username, jackpots, near_miss, spins) in enumerate(rows, start=1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        lines.append(f"{medal} {username} — 🎰 {jackpots} джекпотов, ⭐️ {near_miss} почти, 🔄 {spins} спинов")

    await message.reply("\n".join(lines))


@dp.message(Command("adminstats"))
async def cmd_admin_stats(message: Message):
    """Статистика - только для админа"""
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Эта команда только для администратора!")
        return
    
    total = db_get_total_stats()
    if not total or total[0] == 0:
        await message.reply("📊 Пока нет статистики")
        return
    
    total_spins = total[0] or 0
    total_roses = total[1] or 0
    
    await message.reply(
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"🎰 Всего спинов: {total_spins}\n"
        f"🌹 Всего роз выдано: {total_roses}"
    )


async def main():
    global telethon_client
    
    log.info("🚀 Запуск бота на Railway...")
    
    # Инициализация базы данных
    db_init()
    
    # Подключение Telethon
    telethon_client = TelegramClient(SESSION_PATH, TELETHON_API_ID, TELETHON_API_HASH)
    await telethon_client.start()
    log.info("✅ Telethon подключен")
    
    # Запуск бота
    log.info("🤖 Бот запущен и работает в группе @ludkanihers")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())