import os
import sqlite3
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

TOKEN = "8711612037:AAFSOm_3NZBniSEqzhVuv-ngFYZpItl0W-Q"

# ===== PATH TO DATABASE =====
BASE_DIR = os.path.expanduser("~/Desktop")
db_path = os.path.join(BASE_DIR, "streetbikes.db")

# ===== DATABASE =====
conn = sqlite3.connect(db_path, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bikes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo_id TEXT,
    likes INTEGER DEFAULT 0,
    dislikes INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS votes(
    user_id INTEGER,
    bike_id INTEGER,
    PRIMARY KEY(user_id, bike_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reputation(
    user_id INTEGER PRIMARY KEY,
    rep INTEGER DEFAULT 0
)
""")
conn.commit()

# ===== АНТИ-СПАМ =====
last_action_time = {}
ANTI_SPAM_DELAY = 5  # теперь 5 секунд

def check_spam(user_id):
    now = time.time()
    last = last_action_time.get(user_id, 0)
    if now - last < ANTI_SPAM_DELAY:
        return True
    last_action_time[user_id] = now
    return False

# ===== HELPERS =====
def build_keyboard(bike_id, likes, dislikes):
    keyboard = [[
        InlineKeyboardButton(f"👍 {likes}", callback_data=f"like_{bike_id}"),
        InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike_{bike_id}")
    ]]
    return InlineKeyboardMarkup(keyboard)

def add_rep(user_id, amount=40):
    cursor.execute("SELECT rep FROM reputation WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row:
        new_rep = row[0] + amount
        cursor.execute("UPDATE reputation SET rep=? WHERE user_id=?", (new_rep, user_id))
    else:
        cursor.execute("INSERT INTO reputation(user_id, rep) VALUES(?, ?)", (user_id, amount))
    conn.commit()
    return amount

# ===== COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_spam(update.message.from_user.id):
        return
    await update.message.reply_text(
        "🚲 StreetBikes бот\n"
        "/addbike — добавить байк (только ЛС)\n"
        "/mybike — показать свой байк\n"
        "/deletebike — удалить байк\n"
        "/top — топ 5 байков\n"
        "/random — случайный байк\n"
        "/stats — общая статистика\n"
        "/race — фармить репутацию +40"
    )

async def addbike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    if update.message.chat.type != "private":
        await update.message.reply_text("🚫 Добавлять байк можно только в ЛС!")
        return
    await update.message.reply_text("📷 Отправь фото своего байка")

async def add_bike_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    if update.message.chat.type != "private":
        return

    photo = update.message.photo[-1].file_id
    target_user_id = update.message.reply_to_message.from_user.id if update.message.reply_to_message else user_id

    cursor.execute("SELECT id FROM bikes WHERE user_id=?", (target_user_id,))
    if cursor.fetchone():
        await update.message.reply_text("🚫 У этого пользователя уже есть байк")
        return

    cursor.execute("INSERT INTO bikes(user_id, photo_id) VALUES(?, ?)", (target_user_id, photo))
    conn.commit()
    bike_id = cursor.lastrowid
    keyboard = build_keyboard(bike_id, 0, 0)
    await update.message.reply_photo(photo, caption="✅ Байк добавлен!", reply_markup=keyboard)

async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if check_spam(user_id):
        await query.answer("⏱ Подожди немного", show_alert=True)
        return
    await query.answer()

    if query.data == "ignore":
        return

    action, bike_id = query.data.split("_")
    bike_id = int(bike_id)

    cursor.execute("SELECT user_id, likes, dislikes FROM bikes WHERE id=?", (bike_id,))
    res = cursor.fetchone()
    if not res:
        await query.answer("Байк не найден", show_alert=True)
        return
    owner_id, likes, dislikes = res

    if user_id == owner_id:
        await query.answer("❌ Нельзя голосовать за свой байк", show_alert=True)
        return

    cursor.execute("SELECT 1 FROM votes WHERE user_id=? AND bike_id=?", (user_id, bike_id))
    if cursor.fetchone():
        await query.answer("Ты уже голосовал", show_alert=True)
        return

    if action == "like":
        likes += 1
        cursor.execute("UPDATE bikes SET likes=? WHERE id=?", (likes, bike_id))
    elif action == "dislike":
        dislikes += 1
        cursor.execute("UPDATE bikes SET dislikes=? WHERE id=?", (dislikes, bike_id))

    cursor.execute("INSERT INTO votes(user_id, bike_id) VALUES(?, ?)", (user_id, bike_id))
    conn.commit()

    keyboard = build_keyboard(bike_id, likes, dislikes)
    await query.edit_message_reply_markup(reply_markup=keyboard)

async def mybike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    cursor.execute("SELECT id, photo_id, likes, dislikes FROM bikes WHERE user_id=?", (user_id,))
    bike = cursor.fetchone()
    if not bike:
        await update.message.reply_text("🚫 У тебя нет байка")
        return
    bike_id, photo, likes, dislikes = bike
    keyboard = build_keyboard(bike_id, likes, dislikes)
    await update.message.reply_photo(photo, caption=f"👍 {likes}   👎 {dislikes}", reply_markup=keyboard)

async def deletebike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    cursor.execute("DELETE FROM bikes WHERE user_id=?", (user_id,))
    cursor.execute("DELETE FROM votes WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text("🗑 Твой байк удалён")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    cursor.execute("SELECT photo_id, likes FROM bikes ORDER BY likes DESC LIMIT 5")
    bikes = cursor.fetchall()
    if not bikes:
        await update.message.reply_text("Нет байков")
        return
    await update.message.reply_text("🏆 Топ 5 байков")
    for photo, likes in bikes:
        await update.message.reply_photo(photo, caption=f"👍 {likes}")

async def random_bike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    cursor.execute("SELECT id, photo_id, likes, dislikes FROM bikes")
    bikes = cursor.fetchall()
    if not bikes:
        await update.message.reply_text("Нет байков")
        return
    bike = random.choice(bikes)
    bike_id, photo, likes, dislikes = bike
    keyboard = build_keyboard(bike_id, likes, dislikes)
    await update.message.reply_photo(photo, caption="🎲 Случайный байк", reply_markup=keyboard)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        return
    cursor.execute("SELECT COUNT(*) FROM bikes")
    total_bikes = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(likes) FROM bikes")
    total_likes = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(dislikes) FROM bikes")
    total_dislikes = cursor.fetchone()[0] or 0
    text = f"📊 Статистика\n\n🚲 Байков: {total_bikes}\n👍 Лайков: {total_likes}\n👎 Дизлайков: {total_dislikes}"
    await update.message.reply_text(text)

async def farm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if check_spam(user_id):
        await update.message.reply_text("⏱ Подожди 5 секунд прежде чем фармить снова!", quote=True)
        return
    amount = add_rep(user_id)
    await update.message.reply_text(f"💰 Ты покатал байк и получил +{amount} репутации!", quote=True)

# ===== MAIN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addbike", addbike))
app.add_handler(CommandHandler("mybike", mybike))
app.add_handler(CommandHandler("deletebike", deletebike))
app.add_handler(CommandHandler("top", top))
app.add_handler(CommandHandler("random", random_bike))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("race", farm))

app.add_handler(MessageHandler(filters.PHOTO, add_bike_photo))
app.add_handler(CallbackQueryHandler(vote, pattern="^(like|dislike)_"))

print("StreetBikes IMBA bot started")
app.run_polling()