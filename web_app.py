import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== ТОКЕН =====
TOKEN = "8884017743:AAHkCNM9BTFHaGo5P9dd3aExq9iHL4Jy8LA"

# ===== НАСТРОЙКИ =====
web_app = Flask(__name__)  # ← ИЗМЕНИЛ ИМЯ!
logging.basicConfig(level=logging.INFO)

# ===== БОТ =====
bot_app = Application.builder().token(TOKEN).build()

# ===== КОМАНДА /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Бот работает!")

bot_app.add_handler(CommandHandler("start", start))

# ===== ВЕБХУК =====
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return 'No data', 400
        
        update = Update.de_json(data, bot_app.bot)
        # ПРАВИЛЬНЫЙ АСИНХРОННЫЙ ВЫЗОВ
        import asyncio
        asyncio.create_task(bot_app.process_update(update))
        return 'ok', 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return 'error', 500

@web_app.route('/')
def index():
    return "🤖 Бот работает!"

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port)
