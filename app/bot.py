import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== ТОКЕН =====
TOKEN = "8884017743:AAHkCNM9BTFHaGo5P9dd3aExq9iHL4Jy8LA"

# ===== НАСТРОЙКИ =====
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ===== БОТ =====
bot_app = Application.builder().token(TOKEN).build()

# ===== КОМАНДА /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Бот на Railway работает!")

bot_app.add_handler(CommandHandler("start", start))

# ===== ВЕБХУК =====
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(), bot_app.bot)
        bot_app.process_update(update)
        return 'ok', 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return 'error', 500

@app.route('/')
def index():
    return "🤖 Бот работает!"

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
