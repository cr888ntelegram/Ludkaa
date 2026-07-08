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
from telethon.sessions import StringSession

# ===== ПЕРЕМЕННЫЕ =====
BOT_TOKEN = "8257020137:AAFng7pgAacxilMkxGYH8CVO6-yHlQmt3K0"
ADMIN_ID = 8424002876
ADMIN_USERNAME = "nihers"

TELETHON_API_ID = 32199693
TELETHON_API_HASH = "0f27e89d40cd2a025f98b24bc676c943"

# Берем STRING_SESSION из переменных Railway
STRING_SESSION = os.environ.get("STRING_SESSION", "1ApWapzMBu408VIrAysGQCE56NXr_KOX2HvjoTUy-hgJbWMDvjGWUT_wSfzzyVV-ofd_8Gw_LgEW3CXPBCw4g9FxPT9pA22Kez6F6e3yY1HXEniw-uBQ-Ga4PddpYcNLrlsIiTt6kV9sajIg3sm2fqtfx4uUjj0b2W_OzX76jRB8bSA2g1TbHoQoLvK5kYMYja0EUZ9MLm58MdMHjis04GWHXLiaHI9ncmKnTPwco77nszDc8uvH6AQKXRADPO30HOXlsd-dHF6x108KmKNgqVZaUJFdiLIwTcjQrthkP1Esm56hly1uGPQI185qTjSBC1-9gPWKjmp98iiKjuEW6zHQUfM_bOvM=")
# ======================

ROSE_GIFT_ID = 5168103777563050263
GIFT_COMMENT = "Приз за участие - @ludkanihers!"

DB_PATH = "slotbot.db"
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
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username
        """, (user_id, username))
        con.execute(f"UPDATE stats SET {field} = {field} + ? WHERE user_id = ?", (amount, user_id))
        con.commit()


def db_get_total_stats():
    with closing(sqlite3.connect(DB_PATH)) as con:
        cur = con.execute("SELECT SUM(spins), SUM(roses_won) FROM stats")
        return cur.fetchone()


def db_get_top(limit: int = 10):
    with closing(sqlite3.connect(DB_PATH)) as con:
        cur = con.execute(
            "SELECT username, jackpots, near_miss, spins FROM stats ORDER BY jackpots DESC, near_miss DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()


def decode_slot(value: int):
    idx = value - 1
    r1 = idx % 4
    r2 = (idx // 4) % 4
    r3 = (idx // 16) % 4
    return SYMBOLS[r1], SYMBOLS[r2], SYMBOLS[r3]


def build_prize_grid_hidden(winner_user_id: int, message_id: int):
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


def build_prize_grid_revealed(winner_user_id: int, message_id: int, selected_index: int):
    frog_index = frog_positions.get(f"{winner_user_id}_{message_id}", 0)
    
    buttons = []
    row = []
    for i in range(25):
        if i == frog_index:
            button_text = "🐸"
            cb_data = f"prize:revealed:nft:{winner_user_id}"
        else:
            if i == selected_index:
                button_text = "✅🌹"
            else:
                button_text = "🌹"
            cb_data = f"prize:revealed:rose:{winner_user_id}"
        
        row.append(InlineKeyboardButton(text=button_text, callback_data=cb_data))
        if len(row) == 5:
            buttons.append(row)
            row = []
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_rose(username: str) -> bool:
    try:
        peer = await telethon_client.get_input_entity(username)
        
        # Способ 1: Через messages.SendGiftRequest
        result = await telethon_client(functions.messages.SendGiftRequest(
            peer=peer,
            gift_id=ROSE_GIFT_ID,
            message=GIFT_COMMENT if GIFT_COMMENT else None,
            hide_name=False
        ))
        log.info(f"✅ Роза отправлена {username}")
        return True
    except Exception as e:
        log.error(f"Способ 1 ошибка: {e}")
        
        # Способ 2: Через payments
        try:
            from telethon.tl.functions.payments import SendStarsFormRequest, GetPaymentFormRequest
            from telethon.tl.types import InputInvoiceStarGift
            
            invoice = InputInvoiceStarGift(
                peer=peer,
                gift_id=ROSE_GIFT_ID,
                hide_name=False,
                message=GIFT_COMMENT if GIFT_COMMENT else None
            )
            form = await telethon_client(GetPaymentFormRequest(invoice=invoice))
            await telethon_client(SendStarsFormRequest(form_id=form.form_id, invoice=invoice))
            log.info(f"✅ Роза отправлена {username} (способ 2)")
            return True
        except Exception as e2:
            log.error(f"Способ 2 ошибка: {e2}")
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
            f"🎰 ДЖЕКПОТ!\n\n🎉 {username} сорвал банк!\n\n👇 Выбери слот:",
            reply_markup=build_prize_grid_hidden(user.id, message.message_id)
        )
    elif sevens == 2:
        db_bump(user.id, username, "near_miss")
        await message.reply(f"⭐ Почти джекпот! {username}, не хватило одной семерки!")


@dp.callback_query(F.data.startswith("prize:select:"))
async def handle_prize_select(callback: CallbackQuery):
    _, _, winner_id_str, message_id_str, index_str = callback.data.split(":")
    winner_id = int(winner_id_str)
    message_id = int(message_id_str)
    selected_index = int(index_str)
    user = callback.from_user

    if user.id != winner_id:
        await callback.answer("❌ Не твой приз!", show_alert=True)
        return

    frog_index = frog_positions.get(f"{winner_id}_{message_id}", 0)
    username = f"@{user.username}" if user.username else user.full_name
    
    if selected_index == frog_index:
        await callback.message.edit_text(
            f"🐸 NFT НАЙДЕН!\n\n{username} нашел NFT!\n@{ADMIN_USERNAME} выдаст вручную",
            reply_markup=build_prize_grid_revealed(winner_id, message_id, selected_index)
        )
        await callback.answer("🐸 NFT!", show_alert=True)
        await bot.send_message(ADMIN_ID, f"🎉 Игрок {username} нашел NFT!")
    else:
        db_bump(user.id, username, "roses_won")
        await callback.message.edit_text(
            f"🌹 РОЗА!\n\n{username} нашел розу!\n⏳ Отправляем...",
            reply_markup=build_prize_grid_revealed(winner_id, message_id, selected_index)
        )

        sent = await send_rose(user.username)
        if sent:
            await callback.message.edit_text(f"🌹 Подарок отправлен! {username}, проверь подарки! 🎁")
        else:
            await callback.message.edit_text(f"🌹 Роза найдена!\n\n{username}, не удалось отправить автоматически\n@{ADMIN_USERNAME} выдаст вручную")
            await bot.send_message(ADMIN_ID, f"❌ Не смог отправить розу\nПользователь: {username} (id {user.id})")

        await callback.answer("🌹 Роза!", show_alert=True)


@dp.message(Command("top"))
async def cmd_top(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Только для админа!")
        return
    
    rows = db_get_top()
    if not rows:
        await message.reply("🏆 Пока никто не крутил")
        return

    lines = ["🏆 ТОП ИГРОКОВ\n"]
    for i, (username, jackpots, near_miss, spins) in enumerate(rows, start=1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        lines.append(f"{medal} {username} — 🎰 {jackpots} джекпотов, ⭐️ {near_miss} почти, 🔄 {spins} спинов")
    await message.reply("\n".join(lines))


@dp.message(Command("adminstats"))
async def cmd_admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Только для админа!")
        return
    
    total = db_get_total_stats()
    if not total or total[0] == 0:
        await message.reply("📊 Пока нет статистики")
        return
    
    await message.reply(
        f"📊 СТАТИСТИКА БОТА\n\n"
        f"🎰 Всего спинов: {total[0] or 0}\n"
        f"🌹 Всего роз: {total[1] or 0}"
    )


async def main():
    global telethon_client
    db_init()
    
    if not STRING_SESSION:
        log.error("❌ STRING_SESSION не найдена! Добавь переменную на Railway")
        return
    
    log.info("📱 Подключаем Telethon через StringSession...")
    telethon_client = TelegramClient(StringSession(STRING_SESSION), TELETHON_API_ID, TELETHON_API_HASH)
    await telethon_client.start()
    log.info("✅ Telethon подключен!")
    
    log.info("🤖 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
