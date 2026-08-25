import os
import sys
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== ЗАГРУЗКА ТОКЕНА =====
TOKEN = os.environ.get('TELEGRAM_TO')

if not TOKEN:
    logging.error("❌ ТОКЕН НЕ НАЙДЕН! Проверь переменную TELEGRAM_TO в Railway.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logging.info(f"✅ Токен загружен: {TOKEN[:10]}...")

# ===== ПРИЛОЖЕНИЕ =====
app = Flask(__name__)

# ===== БОТ =====
bot_app = Application.builder().token(TOKEN).build()

# ===== КОМАНДЫ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Бот работает! Токен загружен.")

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
    return "🤖 Бот работает! Токен загружен."

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
