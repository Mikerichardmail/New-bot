
import os
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters
from docx2pdf import convert
import zipfile

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, None, workers=0, use_context=True)
app = Flask(__name__)

batch_storage = {}
MAX_FILE_SIZE = 50 * 1024 * 1024

def start(update: Update, context):
    update.message.reply_text(
        "Send me DOC/DOCX files. You can send multiple messages. "
        "When done, send /done to get a single ZIP with all PDFs! "
        f"Files larger than {MAX_FILE_SIZE // (1024*1024)} MB will be skipped."
    )
    batch_storage[update.message.chat_id] = []

def handle_file(update: Update, context):
    chat_id = update.message.chat_id
    if chat_id not in batch_storage:
        batch_storage[chat_id] = []

    file = update.message.document

    if file.file_size > MAX_FILE_SIZE:
        update.message.reply_text(f"File {file.file_name} is too large ({file.file_size // (1024*1024)} MB) and was skipped.")
        return

    file_obj = file.get_file()
    file_name = file.file_name
    file_path = f"/tmp/{file_name}"
    file_obj.download(file_path)

    pdf_path = file_path.replace(".docx", ".pdf").replace(".doc", ".pdf")
    try:
        msg = update.message.reply_text(f"Converting {file_name}...")
        convert(file_path, pdf_path)
        batch_storage[chat_id].append(pdf_path)
        os.remove(file_path)
        msg.edit_text(f"{file_name} converted successfully! Total files in batch: {len(batch_storage[chat_id])}")
    except Exception as e:
        update.message.reply_text(f"Error converting {file_name}: {e}")

def done(update: Update, context):
    chat_id = update.message.chat_id
    pdf_paths = batch_storage.get(chat_id, [])

    if not pdf_paths:
        update.message.reply_text("No files in batch. Send DOC/DOCX first!")
        return

    zip_path = f"/tmp/batch_{chat_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for pdf in pdf_paths:
            zipf.write(pdf, os.path.basename(pdf))

    update.message.reply_document(document=open(zip_path, "rb"))

    for pdf in pdf_paths:
        if os.path.exists(pdf):
            os.remove(pdf)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    batch_storage[chat_id] = []

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("done", done))
dp.add_handler(MessageHandler(filters.Document.ALL, handle_file))

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dp.process_update(update)
    return "OK"

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    bot.set_webhook(WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
