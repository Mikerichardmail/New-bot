import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
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
        "Send me DOC/DOCX files. You can send multiple messages. "
        "When done, send /done to get a single ZIP with all PDFs! "
        f"Files larger than {MAX_FILE_SIZE // (1024*1024)} MB will be skipped."
    )

# Handle files
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in batch_storage:
        batch_storage[chat_id] = []

    file = update.message.document

    if file.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(f"File {file.file_name} is too large ({file.file_size // (1024*1024)} MB) and was skipped.")
        return

    file_obj = await file.get_file()
    file_name = file.file_name
    file_path = f"/tmp/{file_name}"
    await file_obj.download_to_drive(file_path)

    pdf_path = file_path.replace(".docx", ".pdf").replace(".doc", ".pdf")
    try:
        msg = await update.message.reply_text(f"Converting {file_name}...")
        convert(file_path, pdf_path)
        batch_storage[chat_id].append(pdf_path)
        os.remove(file_path)
        await msg.edit_text(f"{file_name} converted successfully! Total files in batch: {len(batch_storage[chat_id])}")
    except Exception as e:
        await update.message.reply_text(f"Error converting {file_name}: {e}")

# /done command
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pdf_paths = batch_storage.get(chat_id, [])

    if not pdf_paths:
        await update.message.reply_text("No files in batch. Send DOC/DOCX first!")
        return

    zip_path = f"/tmp/batch_{chat_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for pdf in pdf_paths:
            zipf.write(pdf, os.path.basename(pdf))

    await update.message.reply_document(document=open(zip_path, "rb"))

    for pdf in pdf_paths:
        if os.path.exists(pdf):
            os.remove(pdf)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    batch_storage[chat_id] = []

# Flask webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    from telegram import Update
    from telegram.ext import ApplicationBuilder

    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    application.update_queue.put(update)
    return "OK"

@app.route("/")
def index():
    return "Bot is running!"

# Build the Telegram application
application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("done", done))
application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
application.bot.set_webhook(WEBHOOK_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
