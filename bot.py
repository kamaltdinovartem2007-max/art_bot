import os
import random
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)

# ───────────────────────────── CONFIG ─────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8527530306:AAFAlkJXt0OR0bJrxuj1Rhu4I5MkTDwkGFA")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN", "390540012:LIVE:98268")

FREE_USERS = {1470728379, 1125997394}

PAID_USERS_FILE = "paid_users.json"

# ─────────────────────── PAID USERS ───────────────────────────────
def load_paid_users() -> set:
    if os.path.isfile(PAID_USERS_FILE):
        with open(PAID_USERS_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_paid_users(users: set):
    with open(PAID_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f)

def is_paid(user_id: int) -> bool:
    return user_id in FREE_USERS or user_id in load_paid_users()

def mark_paid(user_id: int):
    users = load_paid_users()
    users.add(user_id)
    save_paid_users(users)

# ─────────────────────── LOAD ARTWORKS ────────────────────────────
def load_artworks() -> list[dict]:
    with open("artworks.json", encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────── NORMALISE INPUT ──────────────────────────
def normalise(text: str) -> str:
    return text.strip().lower()

# ──────────────────────── KEYBOARDS ───────────────────────────────
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Викторина (5 вопросов)", callback_data="quiz")],
        [InlineKeyboardButton("🏃 Марафон (все картины)", callback_data="marathon")],
    ])

def pay_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Оплатить подписку — 100 ₽", callback_data="pay")],
    ])

# ──────────────────────── MENU ────────────────────────────────────
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
    msg = text or "🖼 *Выбери режим:*"
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(msg, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# ──────────────────────── HELPERS ─────────────────────────────────
def build_question_caption(artwork: dict) -> str:
    no_author = artwork.get("no_author", False)
    if no_author:
        return (
            "🎨 *Что это за произведение?*\n\n"
            "Напиши только название:\n"
            "`Название`\n\n"
            "_Например: Звёздная ночь_"
        )
    return (
        "🎨 *Что это за произведение и кто его автор?*\n\n"
        "Напиши в формате:\n"
        "`Название — Автор`\n\n"
        "_Например: Звёздная ночь — Ван Гог_"
    )

async def send_artwork(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    artwork = data["queue"][data["current_index"]]
    num = data["current_index"] + 1
    total = len(data["queue"])

    mode_label = "🏃 *Марафон*" if data.get("mode") == "marathon" else "🎨 *Викторина*"
    caption = f"{mode_label} | Вопрос {num}/{total}\n\n" + build_question_caption(artwork)

    image_path = artwork.get("image")
    target = update.callback_query.message if update.callback_query else update.effective_message

    if image_path and os.path.isfile(image_path):
        with open(image_path, "rb") as img:
            await target.reply_photo(photo=img, caption=caption, parse_mode="Markdown")
    else:
        await target.reply_text(
            f"[изображение не найдено: {image_path}]\n\n{caption}",
            parse_mode="Markdown",
        )

# ──────────────────────── COMMANDS ────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id

    if is_paid(user_id):
        await show_main_menu(update, context, text="🖼 *Добро пожаловать!*\n\nВыбери режим:")
    else:
        await update.message.reply_text(
            "👋 *Добро пожаловать в викторину по искусству!*\n\n"
            "Для доступа ко всем режимам необходима подписка — *100 рублей/месяц*.\n\n"
            "Нажми кнопку ниже чтобы оплатить:",
            parse_mode="Markdown",
            reply_markup=pay_keyboard(),
        )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_main_menu(update, context, text="Викторина остановлена. Выбери режим:")

# ──────────────────────── PAYMENT ─────────────────────────────────
async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title="Подписка на викторину по искусству",
        description="Доступ к викторине и марафону на 1 месяц",
        payload="subscription_1month",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[LabeledPrice("Подписка на 1 месяц", 10000)],  # 10000 = 100 рублей (в копейках)
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mark_paid(user_id)
    await update.message.reply_text(
        "✅ *Оплата прошла успешно!*\n\n"
        "Теперь тебе доступны все режимы викторины.",
        parse_mode="Markdown",
    )
    await show_main_menu(update, context, text="🖼 Выбери режим:")

# ──────────────────────── CALLBACKS ───────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data
    user_id = update.effective_user.id

    if query.data == "pay":
        await send_invoice(update, context)
        return

    # Проверка оплаты перед запуском режима
    if not is_paid(user_id):
        await query.message.reply_text(
            "🔒 Для доступа к викторине необходима подписка.\n\n"
            "Нажми кнопку ниже чтобы оплатить:",
            reply_markup=pay_keyboard(),
        )
        return

    if query.data == "quiz":
        artworks = load_artworks()
        random.shuffle(artworks)
        queue = artworks[:min(5, len(artworks))]

        data.update({
            "queue": queue,
            "current_index": 0,
            "score": 0,
            "waiting_answer": True,
            "mode": "quiz",
        })

        await query.message.reply_text(
            "🎨 *Викторина начинается!*\n\n"
            f"Тебе покажут *{len(queue)}* произведений.\n"
            "Угадай название и автора каждого.\n\n"
            "Отвечай в формате: `Название — Автор`\n"
            "Если автор неизвестен — пиши только название.\n\n"
            "Напиши /stop чтобы выйти в меню.",
            parse_mode="Markdown",
        )
        await send_artwork(update, context)

    elif query.data == "marathon":
        artworks = load_artworks()
        random.shuffle(artworks)

        data.update({
            "queue": artworks,
            "current_index": 0,
            "score": 0,
            "waiting_answer": True,
            "mode": "marathon",
        })

        await query.message.reply_text(
            "🏃 *Марафон начинается!*\n\n"
            f"Всего произведений: *{len(artworks)}*\n"
            "Они будут идти в случайном порядке — одно за другим.\n\n"
            "Отвечай в формате: `Название — Автор`\n"
            "Если автор неизвестен — пиши только название.\n\n"
            "Напиши /stop чтобы выйти в меню.",
            parse_mode="Markdown",
        )
        await send_artwork(update, context)

# ──────────────────────── ANSWER HANDLER ──────────────────────────
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data

    if not data.get("waiting_answer"):
        await show_main_menu(update, context, text="Нет активной викторины. Выбери режим:")
        return

    artwork = data["queue"][data["current_index"]]
    user_text = normalise(update.message.text)
    no_author = artwork.get("no_author", False)

    correct_titles = [normalise(t) for t in artwork.get("title_aliases", [artwork["title"]])]

    if no_author:
        separator = "—" if "—" in user_text else "-"
        parts = [p.strip() for p in user_text.split(separator, 1)]
        title_ok = parts[0] in correct_titles
        correct_answer = f"*{artwork['title']}*"

        if title_ok:
            data["score"] += 1
            await update.message.reply_text(
                "✅ *Верно!* Молодец!\n\n"
                f"Правильный ответ: {correct_answer}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "❌ Неверно.\n\n"
                f"Правильный ответ: {correct_answer}",
                parse_mode="Markdown",
            )
    else:
        correct_authors = [normalise(a) for a in artwork.get("author_aliases", [artwork["author"]])]
        separator = "—" if "—" in user_text else "-"
        parts = [p.strip() for p in user_text.split(separator, 1)]

        title_ok  = len(parts) >= 1 and parts[0] in correct_titles
        author_ok = len(parts) >= 2 and parts[1] in correct_authors
        correct_answer = f"*{artwork['title']}* — *{artwork['author']}*"

        if title_ok and author_ok:
            data["score"] += 1
            await update.message.reply_text(
                "✅ *Верно!* Молодец!\n\n"
                f"Правильный ответ: {correct_answer}",
                parse_mode="Markdown",
            )
        elif title_ok:
            await update.message.reply_text(
                "🟡 Название правильное, но автор неверный.\n\n"
                f"Правильный ответ: {correct_answer}",
                parse_mode="Markdown",
            )
        elif author_ok:
            await update.message.reply_text(
                "🟡 Автор правильный, но название неверное.\n\n"
                f"Правильный ответ: {correct_answer}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "❌ Неверно.\n\n"
                f"Правильный ответ: {correct_answer}",
                parse_mode="Markdown",
            )

    data["current_index"] += 1

    if data["current_index"] < len(data["queue"]):
        await send_artwork(update, context)
    else:
        score = data["score"]
        total = len(data["queue"])
        data["waiting_answer"] = False

        emoji = "🏆" if score == total else ("👍" if score >= total // 2 else "😅")
        mode_label = "Марафон" if data.get("mode") == "marathon" else "Викторина"

        await update.message.reply_text(
            f"{emoji} *{mode_label} завершён!*\n\n"
            f"Твой результат: *{score}/{total}*\n",
            parse_mode="Markdown",
        )
        await show_main_menu(update, context, text="Выбери следующий режим:")

# ────────────────────────── MAIN ──────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    print("Бот запущен...")
    app.run_polling(stop_signals=None)


if __name__ == "__main__":
    main()
