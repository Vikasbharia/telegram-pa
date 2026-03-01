import os
import sqlite3
from datetime import datetime, timezone
import dateparser
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_PATH = "pa.db"

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        username TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        remind_at TEXT,
        text TEXT,
        chat_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        key TEXT PRIMARY KEY,
        file_id TEXT,
        file_type TEXT
    )
    """)

    conn.commit()
    conn.close()

# ---------------- USER REGISTER ----------------
def register_user(update: Update):
    u = update.effective_user
    chat = update.effective_chat
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO users(user_id, chat_id, username) VALUES (?, ?, ?)",
        (u.id, chat.id, u.username)
    )
    conn.commit()
    conn.close()

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text(
            "✅ Personal Assistant Active.\n\n"
            "/remind me tomorrow 9am | Standup\n"
            "/remember Buy milk\n"
            "/notes\n"
            "Reply to file → /save_doc agreement\n"
            "/send_doc agreement me"
        )
    else:
        await update.message.reply_text("Connected. You may receive reminders.")

# ---------------- MEMORY ----------------
async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    text = " ".join(context.args)
    conn = db()
    conn.execute(
        "INSERT INTO notes(text, created_at) VALUES (?, ?)",
        (text, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("🧠 Saved.")

async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    conn = db()
    rows = conn.execute(
        "SELECT id, text FROM notes ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    msg = "\n".join([f"{r[0]}: {r[1]}" for r in rows])
    await update.message.reply_text(msg if msg else "No notes.")

# ---------------- REMINDERS ----------------
async def reminder_fire(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.data["chat_id"],
        text=f"⏰ Reminder: {job.data['text']}"
    )

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    raw = " ".join(context.args)
    if "|" not in raw:
        await update.message.reply_text("Use: /remind me tomorrow 9am | Meeting")
        return

    left, text = raw.split("|", 1)
    dt = dateparser.parse(left.replace("me", "").strip())

    context.job_queue.run_once(
        reminder_fire,
        when=dt,
        data={"chat_id": update.effective_chat.id, "text": text.strip()}
    )

    await update.message.reply_text("Reminder set.")

# ---------------- DOCUMENT VAULT ----------------
async def save_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to file first.")
        return

    key = context.args[0]
    msg = update.message.reply_to_message

    if msg.document:
        file_id = msg.document.file_id
        file_type = "document"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    else:
        await update.message.reply_text("Unsupported file.")
        return

    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO documents(key, file_id, file_type) VALUES (?, ?, ?)",
        (key, file_id, file_type)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("Document saved.")

async def send_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    key = context.args[0]

    conn = db()
    row = conn.execute(
        "SELECT file_id, file_type FROM documents WHERE key=?",
        (key,)
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("No such key.")
        return

    file_id, file_type = row

    if file_type == "document":
        await update.message.reply_document(file_id)
    else:
        await update.message.reply_photo(file_id)

# ---------------- MAIN ----------------
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remember", remember))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("save_doc", save_doc))
    app.add_handler(CommandHandler("send_doc", send_doc))

    app.run_polling()

if __name__ == "__main__":
    main()
