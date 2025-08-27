
import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from docx2pdf import convert
import zipfile

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

app = Flask(__name__)
batch_storage = {}
MAX_FILE_SIZE = 50 * 1024 * 1024

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    batch_storage[update.effective_chat.id] = []
    await update.message.reply_text(
        "Send me DOC/DOCX files. Send /done when finished to get a ZIP."
    )

# Handle files
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in batch_storage:
        batch_storage[chat_id] = []

    file = update.message.document
    if file.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(f"{file.file_name} is too large and was skipped.")
        return

    file_obj = await file.get_file()
    file_path = f"/tmp/{file.file_name}"
    await file_obj.download_to_drive(file_path)
    pdf_path = file_path.replace(".docx", ".pdf").replace(".doc", ".pdf")

    try:
        convert(file_path, pdf_path)
        batch_storage[chat_id].append(pdf_path)
        os.remove(file_path)
        await update.message.reply_text(f"{file.file_name} converted successfully!")
    except Exception as e:
        await update.message.reply_text(f"Error converting {file.file_name}: {e}")

# /done command
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pdf_paths = batch_storage.get(chat_id, [])

    if not pdf_paths:
        await update.message.reply_text("No files to convert.")
        return

    zip_path = f"/tmp/batch_{chat_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for pdf in pdf_paths:
            zipf.write(pdf, os.path.basename(pdf))

    await update.message.reply_document(open(zip_path, "rb"))

    for pdf in pdf_paths:
        if os.path.exists(pdf):
            os.remove(pdf)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    batch_storage[chat_id] = []

# Flask webhook endpoint
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    asyncio.run(app_bot.update_queue.put(update))
    return "OK"

@app.route("/")
def index():
    return "Bot is running!"

# Create Application manually (webhook-only)
app_bot = Application.builder().token(TOKEN).build()
bot = app_bot.bot

# Add handlers
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CommandHandler("done", done))
app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_file))

# Set webhook
asyncio.run(bot.set_webhook(WEBHOOK_URL))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
