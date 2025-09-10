import os
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from tinydb import TinyDB, Query

# --- Настройки из переменных окружения ---
TOKEN = os.environ.get("TOKEN")  # обязательно задать на Render
CHAT_IDS_RAW = os.environ.get("CHAT_IDS", "")  # "427656853,5383245847"
CHAT_IDS = [int(x.strip()) for x in CHAT_IDS_RAW.split(",") if x.strip()]

# --- Логирование ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# --- Путь к БД (в рабочей папке сервиса) ---
DB_PATH = os.path.join(os.getcwd(), "wishlist.json")
db = TinyDB(DB_PATH)
Wishlist = Query()

# Состояние ConversationHandler
ADD_GIFT = 1

# --- Хэндлеры ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [["/add", "/list", "/reset"]]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "Любовь моя! Это наш помощник - общий вишлист. Используй команды или кнопки:",
        reply_markup=reply_markup
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши название подарка или комментарий:")
    return ADD_GIFT

async def save_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name or str(update.message.from_user.id)
    gift_text = update.message.text.strip()
    if not gift_text:
        await update.message.reply_text("Пустое сообщение — напиши название подарка.")
        return ConversationHandler.END

    doc_id = db.insert({"user": user_name, "gift": gift_text, "taken": False})
    buttons = [
        [
            InlineKeyboardButton("Забрал ✅", callback_data=f"take:{doc_id}"),
            InlineKeyboardButton("Не забрал ❌", callback_data=f"untake:{doc_id}")
        ]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    for chat_id in CHAT_IDS:
        await context.bot.send_message(chat_id=chat_id, text=f"{user_name} добавил(а) подарок: {gift_text}", reply_markup=keyboard)
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if ":" not in data:
        await query.edit_message_text("Неправильный callback.")
        return
    action, sid = data.split(":", 1)
    try:
        doc_id = int(sid)
    except:
        await query.edit_message_text("Ошибка идентификатора подарка.")
        return
    item = db.get(doc_id=doc_id)
    if not item:
        await query.edit_message_text("Подарок не найден.")
        return

    if action == "take":
        db.update({"taken": True}, doc_ids=[doc_id])
        status_text = "забрал(а)"
    else:
        db.update({"taken": False}, doc_ids=[doc_id])
        status_text = "пометил(а) как не забран"

    for chat_id in CHAT_IDS:
        await context.bot.send_message(chat_id=chat_id, text=f"{query.from_user.first_name} {status_text} подарок: {item['gift']}")

async def list_gifts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        all_gifts = db.all()
    except Exception as e:
        logging.exception("Ошибка чтения БД")
        await update.message.reply_text("Ошибка при чтении базы данных.")
        return
    if not all_gifts:
        await update.message.reply_text("Список пока пустой.")
        return
    lines = []
    for i, item in enumerate(all_gifts, start=1):
        user = item.get("user", "anon")
        gift = item.get("gift", "<без названия>")
        taken = item.get("taken", False)
        status = "Забрал ✅" if taken else "Не забрал ❌"
        lines.append(f"{i}. {user}: {gift} — {status}")
    text = "🎁 Вишлист:\n\n" + "\n".join(lines)
    MAX = 3800
    if len(text) <= MAX:
        await update.message.reply_text(text)
    else:
        for start in range(0, len(text), MAX):
            await update.message.reply_text(text[start:start+MAX])

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.truncate()
    for chat_id in CHAT_IDS:
        await context.bot.send_message(chat_id=chat_id, text="Список подарков очищен!")

async def relay_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text and not text.startswith("/"):
        sender = update.message.from_user.first_name or str(update.message.from_user.id)
        for chat_id in CHAT_IDS:
            if chat_id != update.message.chat_id:
                await context.bot.send_message(chat_id=chat_id, text=f"{sender}: {text}")

# --- Application ---
app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add", add)],
    states={ADD_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_gift)]},
    fallbacks=[]
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_gifts))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_all))

if __name__ == "__main__":
    asyncio.run(app.run_polling())
