# ============================================================
# Quantum Bet Bot v12 PRO
# Полный код с документацией и комментариями
# Версия: 1.0.0
# Автор: Seva2288
# Лицензия: MIT
# ============================================================

import os
import json
import logging
from flask import Flask, request, jsonify, render_template_string
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import random
import sys
import traceback

# ============================================================
# КОНФИГУРАЦИЯ ПРИЛОЖЕНИЯ
# ============================================================

# Инициализация Flask-приложения
app = Flask(__name__)

# Получение токена бота из переменных окружения
TOKEN = os.environ.get('TELEGRAM_TO')

# Имя файла для хранения данных
DATA_FILE = 'data.json'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# ПРОВЕРКА ТОКЕНА
# ============================================================

def validate_token(token):
    """
    Проверяет валидность токена Telegram бота
    
    Args:
        token (str): Токен для проверки
        
    Returns:
        bool: True если токен валидный, иначе False
    """
    if not token:
        logger.error("❌ ТОКЕН НЕ НАЙДЕН! Добавь переменную TELEGRAM_TO в Railway.")
        return False
    
    # Базовая проверка формата токена
    if not token.startswith('') and ':' not in token:
        logger.error("❌ Неверный формат токена. Ожидается: цифры:буквы")
        return False
    
    if len(token) < 20:
        logger.error("❌ Токен слишком короткий. Проверь правильность.")
        return False
    
    logger.info("✅ Токен прошёл базовую проверку")
    return True

# Проверяем токен при старте
TOKEN_VALID = validate_token(TOKEN)

# ============================================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================================

def init_bot():
    """
    Инициализирует экземпляр Telegram бота
    
    Returns:
        Application: Экземпляр бота или None при ошибке
    """
    try:
        if not TOKEN_VALID:
            logger.warning("⚠️ Токен невалидный, бот не будет инициализирован")
            return None
        
        bot = Application.builder().token(TOKEN).build()
        logger.info("✅ Бот успешно инициализирован")
        return bot
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации бота: {e}")
        logger.error(traceback.format_exc())
        return None

# Создаём экземпляр бота
bot_app = init_bot()

# ============================================================
# РАБОТА С ДАННЫМИ
# ============================================================

def load_data():
    """
    Загружает данные из файла data.json
    
    Returns:
        dict: Словарь с данными {'bank': int, 'history': list}
    """
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ Данные загружены: {len(data.get('history', []))} ставок")
                return data
        else:
            logger.warning("⚠️ Файл данных не найден, создаю новый")
            default_data = {'bank': 1000, 'history': []}
            save_data(default_data)
            return default_data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON: {e}")
        return {'bank': 1000, 'history': []}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        return {'bank': 1000, 'history': []}

def save_data(data):
    """
    Сохраняет данные в файл data.json
    
    Args:
        data (dict): Словарь с данными для сохранения
    """
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("✅ Данные успешно сохранены")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")

def add_bet_to_history(home, away, home_goals, away_goals, stake, bet_type='Ручная ставка', odds=1.85):
    """
    Добавляет новую ставку в историю
    
    Args:
        home (str): Название домашней команды
        away (str): Название гостевой команды
        home_goals (int): Голы хозяев
        away_goals (int): Голы гостей
        stake (float): Сумма ставки
        bet_type (str): Тип ставки
        odds (float): Коэффициент
        
    Returns:
        dict: Созданная запись о ставке
    """
    # Определяем результат
    result = 'pending'
    profit = 0
    
    if home_goals is not None and away_goals is not None:
        if home_goals > away_goals:
            result = 'win'
            profit = round(stake * (odds - 1), 2)
        elif home_goals < away_goals:
            result = 'loss'
            profit = -stake
        else:
            result = 'push'
            profit = 0
    
    bet_record = {
        'home': home,
        'away': away,
        'home_goals': home_goals,
        'away_goals': away_goals,
        'bet': bet_type,
        'odds': odds,
        'stake': round(stake, 2),
        'ev': 0,
        'result': result,
        'profit': profit,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    
    data = load_data()
    data['history'].append(bet_record)
    save_data(data)
    
    logger.info(f"✅ Добавлена ставка: {home} vs {away} → {home_goals}-{away_goals}")
    return bet_record

# ============================================================
# КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start
    
    Показывает приветственное сообщение и список команд
    """
    try:
        await update.message.reply_text(
            "🤖 Привет! Я бот для ставок.\n\n"
            "📌 Команды:\n"
            "/start — показать это меню\n"
            "/help — список команд\n"
            "/bank — показать банк\n"
            "/stats — статистика\n"
            "/result Команда1 Команда2 Счёт Сумма — добавить результат\n"
            "Пример: /result Real Barca 2-1 50"
        )
        logger.info(f"✅ Команда /start от пользователя {update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /help
    
    Показывает подробную справку по командам
    """
    try:
        await update.message.reply_text(
            "📋 Доступные команды:\n\n"
            "🔹 Основные:\n"
            "/start — приветствие\n"
            "/help — эта справка\n"
            "/bank — текущий банк\n"
            "/stats — статистика\n\n"
            "🔹 Добавление ставок:\n"
            "/result Команда1 Команда2 Счёт Сумма\n"
            "Пример: /result Real Barca 2-1 50\n\n"
            "🔹 Управление:\n"
            "/bank — посмотреть банк\n"
            "/stats — посмотреть статистику"
        )
        logger.info(f"✅ Команда /help от пользователя {update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /help: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")

async def bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /bank
    
    Показывает текущий банк пользователя
    """
    try:
        data = load_data()
        bank_value = data.get('bank', 1000)
        await update.message.reply_text(f"💰 Текущий банк: ${bank_value:.2f}")
        logger.info(f"✅ Команда /bank от пользователя {update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /bank: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /stats
    
    Показывает детальную статистику по ставкам
    """
    try:
        data = load_data()
        history = data.get('history', [])
        
        total = len(history)
        wins = sum(1 for b in history if b.get('result') == 'win')
        losses = sum(1 for b in history if b.get('result') == 'loss')
        pushes = sum(1 for b in history if b.get('result') == 'push')
        profit = sum(float(b.get('profit', 0)) for b in history)
        
        # Дополнительные метрики
        total_stake = sum(float(b.get('stake', 0)) for b in history)
        avg_stake = round(total_stake / total, 2) if total > 0 else 0
        winrate = round(wins / total * 100, 1) if total > 0 else 0
        
        message = (
            f"📊 Статистика:\n\n"
            f"📌 Всего ставок: {total}\n"
            f"✅ Выигрыши: {wins}\n"
            f"❌ Проигрыши: {losses}\n"
            f"➖ Возвраты: {pushes}\n"
            f"🎯 Проходимость: {winrate}%\n"
            f"💰 Прибыль: ${profit:.2f}\n"
            f"📊 Средняя ставка: ${avg_stake:.2f}"
        )
        
        await update.message.reply_text(message)
        logger.info(f"✅ Команда /stats от пользователя {update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /stats: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")

async def result_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /result
    
    Добавляет результат матча в историю
    
    Формат: /result Команда1 Команда2 Счёт Сумма
    Пример: /result Real Barca 2-1 50
    """
    try:
        args = context.args
        
        # Проверка количества аргументов
        if len(args) < 4:
            await update.message.reply_text(
                "❌ Неправильный формат.\n"
                "Используй: /result Команда1 Команда2 Счёт Сумма\n"
                "Пример: /result Real Barca 2-1 50"
            )
            return
        
        # Разбор аргументов
        home = args[0]
        away = args[1]
        score = args[2]
        
        # Проверка суммы ставки
        try:
            stake = float(args[3])
        except ValueError:
            await update.message.reply_text("❌ Сумма должна быть числом!")
            return
        
        if stake <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return
        
        # Парсинг счёта
        home_goals = None
        away_goals = None
        
        if '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0])
                away_goals = int(parts[1])
            except ValueError:
                await update.message.reply_text("❌ Неправильный формат счёта. Используй: 2-1")
                return
        else:
            await update.message.reply_text("❌ Неправильный формат счёта. Используй: 2-1")
            return
        
        # Определение результата
        result = 'pending'
        profit = 0
        
        if home_goals > away_goals:
            result = 'win'
            profit = round(stake * 0.85, 2)
        elif home_goals < away_goals:
            result = 'loss'
            profit = -stake
        else:
            result = 'push'
            profit = 0
        
        # Добавление ставки в историю
        bet_record = {
            'home': home,
            'away': away,
            'home_goals': home_goals,
            'away_goals': away_goals,
            'bet': 'Ручная ставка',
            'odds': 1.85,
            'stake': round(stake, 2),
            'ev': 0,
            'result': result,
            'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        data = load_data()
        data['history'].append(bet_record)
        save_data(data)
        
        # Отправка подтверждения
        await update.message.reply_text(
            f"✅ Результат сохранён!\n"
            f"{home} vs {away} → {score}\n"
            f"Результат: {result}\n"
            f"💰 Прибыль: ${profit:.2f}"
        )
        
        logger.info(f"✅ Команда /result от {update.effective_user.id}: {home} vs {away} {score}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /result: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ============================================================
# РЕГИСТРАЦИЯ КОМАНД БОТА
# ============================================================

def register_handlers():
    """
    Регистрирует все обработчики команд бота
    """
    if not bot_app:
        logger.warning("⚠️ Бот не инициализирован, команды не зарегистрированы")
        return
    
    try:
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(CommandHandler("help", help_command))
        bot_app.add_handler(CommandHandler("bank", bank))
        bot_app.add_handler(CommandHandler("stats", stats))
        bot_app.add_handler(CommandHandler("result", result_command))
        logger.info("✅ Все обработчики команд зарегистрированы")
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации обработчиков: {e}")

# Регистрируем обработчики
register_handlers()

# ============================================================
# ВЕБХУК
# ============================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Эндпоинт для приёма вебхуков от Telegram
    
    Returns:
        tuple: (status_message, http_code)
    """
    if not bot_app:
        logger.error("❌ Бот не инициализирован")
        return 'Bot not initialized', 500
    
    try:
        # Получение данных от Telegram
        update_data = request.get_json()
        
        if not update_data:
            logger.warning("⚠️ Пустой запрос от Telegram")
            return 'No data', 400
        
        # Обработка обновления
        update = Update.de_json(update_data, bot_app.bot)
        bot_app.process_update(update)
        
        logger.info("✅ Вебхук успешно обработан")
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"❌ Ошибка в вебхуке: {e}")
        logger.error(traceback.format_exc())
        return 'error', 500

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ВЕБ-ИНТЕРФЕЙСА
# ============================================================

def calculate_stats(history):
    """
    Рассчитывает статистику на основе истории ставок
    
    Args:
        history (list): Список ставок
        
    Returns:
        dict: Статистика в виде словаря
    """
    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    pushes = sum(1 for b in history if b.get('result') == 'push')
    profit = sum(float(b.get('profit', 0)) for b in history)
    total_stake = sum(float(b.get('stake', 0)) for b in history)
    
    return {
        'bank': load_data().get('bank', 1000),
        'total_bets': total,
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'profit': round(profit, 2),
        'winrate': round(wins / total * 100, 1) if total > 0 else 0,
        'roi': round((profit / (total_stake or 1)) * 100, 2) if total > 0 else 0,
        'avg_stake': round(total_stake / total, 2) if total > 0 else 0,
        'max_profit': max([float(b.get('profit', 0)) for b in history]) if history else 0,
        'min_profit': min([float(b.get('profit', 0)) for b in history]) if history else 0
    }

def get_profit_data(history, days=7):
    """
    Генерирует данные для графика прибыли
    
    Args:
        history (list): Список ставок
        days (int): Количество дней для отображения
        
    Returns:
        dict: {'dates': list, 'profits': list}
    """
    profits = []
    
    for i in range(days - 1, -1, -1):
        day_profit = 0
        day = datetime.now() - timedelta(days=i)
        
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bet_date.date() == day.date():
                    stake = float(bet.get('stake', 0))
                    odds = float(bet.get('odds', 1))
                    
                    if bet.get('result') == 'win':
                        day_profit += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= stake
            except (ValueError, IndexError) as e:
                logger.warning(f"⚠️ Ошибка парсинга даты: {e}")
                continue
        
        profits.append(round(day_profit, 2))
    
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}

# ============================================================
# HTML ШАБЛОН
# ============================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
    <title>Quantum Bet Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
    <style>
        :root {
            --bg-primary: #0f0f1a;
            --bg-secondary: #1a1a2e;
            --bg-card: rgba(255,255,255,0.03);
            --text-primary: #e0e0e0;
            --text-secondary: #8888aa;
            --border-color: rgba(255,255,255,0.08);
            --input-bg: #0f0f1a;
            --input-border: #2a2a4a;
            --gradient-start: #667eea;
            --gradient-end: #764ba2;
            --shadow: rgba(102,126,234,0.3);
        }
        [data-theme="light"] {
            --bg-primary: #f0f2f5;
            --bg-secondary: #ffffff;
            --bg-card: rgba(0,0,0,0.02);
            --text-primary: #1a1a2e;
            --text-secondary: #666688;
            --border-color: rgba(0,0,0,0.08);
            --input-bg: #f8f9fa;
            --input-border: #ddd;
            --shadow: rgba(0,0,0,0.1);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            transition: all 0.3s ease;
            overflow-x: hidden;
            padding-bottom: 80px;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 15px; }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 20px;
            padding: 15px 20px;
            background: var(--bg-secondary);
            border-radius: 16px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 30px var(--shadow);
        }
        .header h1 {
            font-size: 24px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header-controls {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .status {
            display: flex;
            align-items: center;
            gap: 6px;
            color: #38ef7d;
            font-size: 12px;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            background: #38ef7d;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.8); }
        }
        .theme-toggle {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 50%;
            width: 36px;
            height: 36px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--text-primary);
        }
        .theme-toggle:hover { transform: scale(1.1); border-color: var(--gradient-start); }
        
        .nav {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        .btn {
            padding: 8px 16px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.3s;
            font-size: 13px;
            white-space: nowrap;
        }
        .btn:hover {
            background: rgba(102,126,234,0.2);
            border-color: var(--gradient-start);
            color: var(--text-primary);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px var(--shadow);
        }
        .btn.active {
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            border-color: var(--gradient-start);
            color: #fff;
            box-shadow: 0 4px 15px var(--shadow);
        }
        .btn-danger { background: #ef473a; color: #fff; border-color: #ef473a; }
        .btn-danger:hover { background: #cb2d3e; border-color: #cb2d3e; }
        .btn-success { background: #38ef7d; color: #000; border-color: #38ef7d; }
        .btn-success:hover { background: #11998e; border-color: #11998e; }
        .btn-primary { background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn-primary:hover { background: #764ba2; transform: scale(1.02); }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .stat-card {
            padding: 15px;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            background: var(--bg-secondary);
            transition: all 0.3s;
            text-align: center;
            box-shadow: 0 2px 10px var(--shadow);
        }
        .stat-card:hover { transform: translateY(-3px); border-color: var(--gradient-start); }
        .stat-card .value {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.green { background: linear-gradient(135deg, #11998e, #38ef7d); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.red { background: linear-gradient(135deg, #cb2d3e, #ef473a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.gold { background: linear-gradient(135deg, #f7971e, #ffd200); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .label { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
        
        .card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 2px 10px var(--shadow);
            overflow: hidden;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 12px;
        }
        .card-header h2 { color: var(--text-secondary); font-size: 16px; font-weight: normal; }
        .card-header .count { color: var(--text-secondary); font-size: 13px; }
        
        .chart-container {
            position: relative;
            height: 200px;
            width: 100%;
        }
        
        .table-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            min-width: 800px;
        }
        th, td {
            padding: 8px 10px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th { 
            color: var(--text-secondary); 
            font-weight: 600; 
            font-size: 11px; 
            text-transform: uppercase; 
            letter-spacing: 0.5px;
            background: var(--bg-card);
            position: sticky;
            top: 0;
        }
        tr:hover td { background: var(--bg-card); }
        
        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        }
        .badge.win { background: rgba(56,239,125,0.15); color: #38ef7d; border: 1px solid rgba(56,239,125,0.2); }
        .badge.loss { background: rgba(239,71,58,0.15); color: #ef473a; border: 1px solid rgba(239,71,58,0.2); }
        .badge.push { background: rgba(255,210,0,0.15); color: #ffd200; border: 1px solid rgba(255,210,0,0.2); }
        .badge.pending { background: rgba(255,255,255,0.05); color: #8888aa; border: 1px solid var(--border-color); }
        
        .profit-positive { color: #38ef7d; font-weight: bold; }
        .profit-negative { color: #ef473a; font-weight: bold; }
        
        .no-data { text-align: center; color: var(--text-secondary); padding: 30px 0; }
        .no-data .emoji { font-size: 48px; margin-bottom: 10px; }
        
        .footer {
            text-align: center;
            color: #444466;
            font-size: 11px;
            margin-top: 20px;
            padding: 15px 0;
            border-top: 1px solid var(--border-color);
        }
        
        .summary-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }
        .summary-item {
            background: var(--bg-card);
            padding: 12px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }
        .summary-item .label { color: var(--text-secondary); font-size: 12px; }
        .summary-item .value { font-size: 18px; font-weight: bold; }
        
        .scrollable-table {
            max-height: 500px;
            overflow-y: auto;
        }
        
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 10px 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
        }
        .bottom-nav .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            color: var(--text-secondary);
            font-size: 10px;
            transition: all 0.3s;
            padding: 4px 12px;
            border-radius: 8px;
            border: none;
            background: transparent;
            cursor: pointer;
            min-width: 60px;
            position: relative;
        }
        .bottom-nav .nav-item .icon { font-size: 22px; line-height: 1.2; }
        .bottom-nav .nav-item .label { font-size: 9px; margin-top: 2px; font-weight: 500; }
        .bottom-nav .nav-item.active { color: var(--gradient-start); }
        .bottom-nav .nav-item.active::after {
            content: '';
            position: absolute;
            top: -1px;
            left: 50%;
            transform: translateX(-50%);
            width: 20px;
            height: 2px;
            background: var(--gradient-start);
            border-radius: 2px;
        }
        
        .setting-group {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
        }
        .setting-group h2 { color: var(--text-secondary); font-size: 14px; font-weight: normal; margin-bottom: 10px; }
        .setting-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid var(--bg-primary);
            flex-wrap: wrap;
            gap: 8px;
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-item .label { color: var(--text-primary); }
        .setting-item .desc { color: var(--text-secondary); font-size: 12px; }
        .input-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .input-group input {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 6px 10px;
            border-radius: 6px;
            width: 120px;
        }
        .input-group button {
            background: var(--gradient-start);
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
        }
        .input-group button:hover { background: var(--gradient-end); }
        .toggle {
            width: 44px;
            height: 24px;
            background: var(--input-border);
            border-radius: 12px;
            cursor: pointer;
            position: relative;
            transition: 0.3s;
        }
        .toggle.active { background: var(--gradient-start); }
        .toggle .dot {
            width: 18px;
            height: 18px;
            background: white;
            border-radius: 50%;
            position: absolute;
            top: 3px;
            left: 3px;
            transition: 0.3s;
        }
        .toggle.active .dot { left: 23px; }
        .file-input-label {
            display: inline-block;
            padding: 6px 14px;
            background: var(--gradient-start);
            color: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        .file-input-label:hover { background: var(--gradient-end); }
        .import-status { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
        
        .match-card {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
        }
        .match-title { font-size: 16px; font-weight: bold; }
        .match-league { color: var(--text-secondary); font-size: 13px; }
        .match-xg { color: var(--gradient-start); font-size: 13px; }
        .match-bets { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }
        .bet-item {
            background: var(--bg-card);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            border: 1px solid var(--border-color);
        }
        
        .sim-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .sim-stat {
            background: var(--bg-card);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid var(--border-color);
        }
        .sim-stat .value { font-size: 28px; font-weight: bold; }
        .sim-stat .value.green { color: #38ef7d; }
        .sim-stat .value.red { color: #ef473a; }
        .sim-stat .value.gold { color: #ffd200; }
        .sim-stat .label { color: var(--text-secondary); font-size: 13px; margin-top: 5px; }
        
        .slider-container { margin: 20px 0; }
        .slider-container input[type="range"] {
            width: 100%;
            height: 8px;
            background: var(--input-border);
            border-radius: 4px;
            outline: none;
            -webkit-appearance: none;
        }
        .slider-container input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--gradient-start);
            cursor: pointer;
        }
        
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
            .bottom-nav .nav-item .icon { font-size: 18px; }
            .bottom-nav .nav-item .label { font-size: 8px; }
            .header h1 { font-size: 20px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
            .stat-card { padding: 10px; }
            .stat-card .value { font-size: 18px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Quantum Bet Bot</h1>
            <div class="header-controls">
                <div class="status">
                    <span class="status-dot"></span>
                    <span>Система активна</span>
                    <span style="color:var(--text-secondary);">|</span>
                    <span style="color:var(--text-secondary);">v12 PRO</span>
                </div>
                <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">🌙</button>
            </div>
        </div>
        
        <div class="nav">
            <button class="btn active" onclick="showPage('dashboard')">📊 Дашборд</button>
            <button class="btn" onclick="showPage('matches')">⚽ Матчи</button>
            <button class="btn" onclick="showPage('stats')">📈 Статистика</button>
            <button class="btn" onclick="showPage('simulator')">🎲 Симулятор</button>
            <button class="btn" onclick="showPage('settings')">⚙️ Настройки</button>
            <button class="btn" onclick="location.reload()">🔄 Обновить</button>
        </div>
        
        <div id="page-dashboard" class="page"><div id="dashboard-content">Загрузка...</div></div>
        <div id="page-matches" class="page" style="display:none;"><div id="matches-content">Загрузка...</div></div>
        <div id="page-stats" class="page" style="display:none;"><div id="stats-content">Загрузка...</div></div>
        <div id="page-simulator" class="page" style="display:none;"><div id="simulator-content">Загрузка...</div></div>
        <div id="page-settings" class="page" style="display:none;"><div id="settings-content">Загрузка...</div></div>
        
        <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
    </div>
    
    <div class="bottom-nav">
        <button class="nav-item active" onclick="showPage('dashboard')"><span class="icon">📊</span><span class="label">Дашборд</span></button>
        <button class="nav-item" onclick="showPage('matches')"><span class="icon">⚽</span><span class="label">Матчи</span></button>
        <button class="nav-item" onclick="showPage('stats')"><span class="icon">📈</span><span class="label">Статистика</span></button>
        <button class="nav-item" onclick="showPage('simulator')"><span class="icon">🎲</span><span class="label">Симулятор</span></button>
        <button class="nav-item" onclick="showPage('settings')"><span class="icon">⚙️</span><span class="label">Настройки</span></button>
    </div>
    
    <script>
        function toggleTheme() {
            const html = document.documentElement;
            const btn = document.getElementById('themeBtn');
            if (html.getAttribute('data-theme') === 'dark') {
                html.setAttribute('data-theme', 'light');
                btn.textContent = '☀️';
                localStorage.setItem('theme', 'light');
            } else {
                html.setAttribute('data-theme', 'dark');
                btn.textContent = '🌙';
                localStorage.setItem('theme', 'dark');
            }
        }
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeBtn').textContent = savedTheme === 'dark' ? '🌙' : '☀️';
        
        function showPage(page) {
            document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
            document.getElementById('page-' + page).style.display = 'block';
            document.querySelectorAll('.nav .btn, .bottom-nav .nav-item').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.nav .btn[onclick*="' + page + '"], .bottom-nav .nav-item[onclick*="' + page + '"]').forEach(b => b.classList.add('active'));
            loadPage(page);
        }
        
        function loadPage(page) {
            const el = document.getElementById(page + '-content');
            fetch('/api/' + page + '_data')
                .then(r => r.json())
                .then(data => {
                    if (page === 'dashboard') renderDashboard(el, data);
                    else if (page === 'matches') renderMatches(el, data);
                    else if (page === 'stats') renderStats(el, data);
                    else if (page === 'simulator') renderSimulator(el, data);
                    else if (page === 'settings') renderSettings(el, data);
                })
                .catch(() => el.innerHTML = '<div class="no-data"><div class="emoji">⚠️</div>Ошибка загрузки</div>');
        }
        
        function renderDashboard(el, data) {
            const s = data.stats;
            const history = data.history || [];
            let html = `
                <div class="stats-grid">
                    <div class="stat-card"><div class="value">$${s.bank}</div><div class="label">💰 Текущий банк</div></div>
                    <div class="stat-card"><div class="value green">${s.wins}</div><div class="label">✅ Выигрыши</div></div>
                    <div class="stat-card"><div class="value red">${s.losses}</div><div class="label">❌ Проигрыши</div></div>
                    <div class="stat-card"><div class="value gold">$${s.profit}</div><div class="label">💰 Прибыль</div></div>
                </div>
                <div class="summary-row">
                    <div class="summary-item"><div class="label">📊 Всего ставок</div><div class="value">${s.total_bets}</div></div>
                    <div class="summary-item"><div class="label">🎯 Проходимость</div><div class="value">${s.winrate}%</div></div>
                    <div class="summary-item"><div class="label">📈 ROI</div><div class="value">${s.roi}%</div></div>
                    <div class="summary-item"><div class="label">📅 Средняя ставка</div><div class="value">$${s.avg_stake}</div></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>📈 График прибыли</h2><span style="font-size:12px;color:var(--text-secondary);">За последние 7 дней</span></div>
                    <div class="chart-container"><canvas id="profitChart"></canvas></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>📋 Все ставки</h2><span class="count">Всего: ${history.length}</span></div>
                    <div class="scrollable-table"><div class="table-wrapper"><table>
                        <thead><tr><th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead><tbody>
            `;
            if (history.length === 0) {
                html += `<tr><td colspan="10" class="no-data"><div class="emoji">📭</div>Нет данных</td></tr>`;
            } else {
                history.slice().reverse().forEach(bet => {
                    const profitClass = bet.profit > 0 ? 'profit-positive' : (bet.profit < 0 ? 'profit-negative' : '');
                    html += `<tr>
                        <td>${history.indexOf(bet) + 1}</td>
                        <td style="font-size:11px;white-space:nowrap;">${bet.date}</td>
                        <td><strong>${bet.home}</strong> vs <strong>${bet.away}</strong></td>
                        <td>${bet.home_goals !== null && bet.away_goals !== null ? bet.home_goals + ' - ' + bet.away_goals : '-'}</td>
                        <td>${bet.bet}</td>
                        <td>${bet.odds}</td>
                        <td>$${bet.stake}</td>
                        <td>${bet.ev}%</td>
                        <td><span class="badge ${bet.result}">${bet.result}</span></td>
                        <td class="${profitClass}">$${bet.profit}</td>
                    </tr>`;
                });
            }
            html += `</tbody></table></div></div></div>`;
            el.innerHTML = html;
            setTimeout(() => {
                const ctx = document.getElementById('profitChart');
                if (!ctx) return;
                const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.profit_data?.dates || ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],
                        datasets: [{
                            label: 'Прибыль ($)',
                            data: data.profit_data?.profits || [0,0,0,0,0,0,0],
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102,126,234,0.1)',
                            fill: true,
                            tension: 0.4,
                            pointBackgroundColor: '#667eea',
                            pointBorderColor: '#fff',
                            pointBorderWidth: 2,
                            pointRadius: 3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { labels: { color: isDark ? '#e0e0e0' : '#1a1a2e', font: { size: 10 } } } },
                        scales: {
                            x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 10 } } },
                            y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: v => '$' + v, font: { size: 10 } } }
                        }
                    }
                });
            }, 50);
        }
        
        function renderMatches(el, data) {
            const matches = data.matches || [];
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">⚽ Матчи на сегодня</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Прогнозы и валуйные ставки</div>`;
            if (matches.length === 0) {
                html += `<div class="no-data"><div class="emoji">📭</div>Матчей не найдено</div>`;
            } else {
                matches.forEach(m => {
                    html += `<div class="match-card">
                        <div class="match-title">${m.home} vs ${m.away}</div>
                        <div class="match-league">🏆 ${m.league} | ⏰ ${m.match_time}</div>
                        <div class="match-xg">📊 xG: ${m.home_xg || '?'} : ${m.away_xg || '?'}</div>
                        <div class="match-bets">${(m.bets || []).slice(0,3).map(b => `<span class="bet-item">${b.label} | КЭФ: ${b.odds} | EV: ${b.ev}%</span>`).join('')}</div>
                    </div>`;
                });
            }
            el.innerHTML = html;
        }
        
        function renderStats(el, data) {
            const s = data.stats;
            const history = data.history || [];
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">📈 Статистика</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Детальный анализ ваших ставок</div>
                <div class="card"><div style="display:flex;gap:15px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:var(--gradient-start);">${s.total_bets}</div><div style="color:var(--text-secondary);font-size:12px;">Всего ставок</div></div>
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:#38ef7d;">${s.wins}</div><div style="color:var(--text-secondary);font-size:12px;">Выигрыши</div></div>
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:#ef473a;">${s.losses}</div><div style="color:var(--text-secondary);font-size:12px;">Проигрыши</div></div>
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:#ffd200;">$${s.profit}</div><div style="color:var(--text-secondary);font-size:12px;">Прибыль</div></div>
                </div></div>
                <div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📋 Все ставки</h2>
                <div class="table-wrapper"><table><thead><tr><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead><tbody>`;
            if (history.length === 0) {
                html += `<tr><td colspan="8" class="no-data">Нет данных</td></tr>`;
            } else {
                history.forEach(bet => {
                    html += `<tr><td style="font-size:11px;">${bet.date}</td><td>${bet.home} vs ${bet.away}</td><td>${bet.home_goals !== null && bet.away_goals !== null ? bet.home_goals + ' - ' + bet.away_goals : '-'}</td><td>${bet.bet}</td><td>${bet.odds}</td><td>${bet.ev}%</td><td><span class="badge ${bet.result}">${bet.result}</span></td><td>$${bet.profit}</td></tr>`;
                });
            }
            html += `</tbody></table></div></div>`;
            el.innerHTML = html;
        }
        
        function renderSimulator(el, data) {
            const history = data.history || [];
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">🎲 Симулятор ставок</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Узнай, сколько ты мог бы заработать!</div>`;
            if (history.length < 5) {
                html += `<div class="card"><div class="no-data"><div class="emoji">📭</div><div>Нет данных для симуляции</div><div style="font-size:13px;color:var(--text-secondary);">Сначала сделайте хотя бы 5 ставок!</div></div></div>`;
            } else {
                html += `<div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📊 Параметры симуляции</h2>
                    <div class="slider-container"><label style="color:var(--text-secondary);font-size:14px;">Количество симуляций: <span id="simCountLabel">1000</span></label>
                    <input type="range" id="simCount" min="100" max="5000" step="100" value="1000" oninput="document.getElementById('simCountLabel').textContent=this.value"></div>
                    <button class="btn-primary" onclick="runSimulation()">🎲 Запустить симуляцию</button>
                    <button class="btn" onclick="document.getElementById('simResults').style.display='none'">🔄 Сбросить</button>
                </div>
                <div id="simResults" style="display:none;">
                    <div class="sim-stats">
                        <div class="sim-stat"><div class="value gold" id="simProfit">$0</div><div class="label">💰 Ожидаемая прибыль</div></div>
                        <div class="sim-stat"><div class="value green" id="simWinrate">0%</div><div class="label">🎯 Проходимость</div></div>
                        <div class="sim-stat"><div class="value" id="simROI">0%</div><div class="label">📈 ROI</div></div>
                        <div class="sim-stat"><div class="value red" id="simRisk">0%</div><div class="label">⚠️ Риск</div></div>
                    </div>
                    <div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📈 График симуляции</h2><div class="chart-container"><canvas id="simChart"></canvas></div></div>
                    <div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📋 Результаты симуляции</h2>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:14px;">
                        <div style="color:var(--text-secondary);">Всего симуляций: <span id="simTotal" style="color:var(--text-primary);">0</span></div>
                        <div style="color:var(--text-secondary);">Выигрышных: <span id="simWins" style="color:#38ef7d;">0</span></div>
                        <div style="color:var(--text-secondary);">Проигрышных: <span id="simLosses" style="color:#ef473a;">0</span></div>
                        <div style="color:var(--text-secondary);">Макс. прибыль: <span id="simMaxProfit" style="color:#ffd200;">$0</span></div>
                        <div style="color:var(--text-secondary);">Мин. прибыль: <span id="simMinProfit" style="color:#ef473a;">$0</span></div>
                        <div style="color:var(--text-secondary);">Средняя ставка: <span id="simAvgStake" style="color:var(--text-primary);">$0</span></div>
                    </div></div>
                    <div class="card" style="background:rgba(102,126,234,0.05);border-color:var(--gradient-start);">
                        <h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">💡 Рекомендация</h2>
                        <div id="simRecommendation" style="font-size:16px;line-height:1.6;">Запустите симуляцию, чтобы получить рекомендацию!</div>
                    </div>
                </div>`;
            }
            el.innerHTML = html;
        }
        
        function renderSettings(el, data) {
            const bank = data.stats?.bank || 1000;
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">⚙️ Настройки</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Управление ботом</div>
                <div class="setting-group"><h2>💰 Банк</h2><div class="setting-item"><div><div class="label">Текущий банк</div><div class="desc">Ваш игровой банк</div></div><div class="input-group"><input type="number" id="bankInput" value="${bank}" step="10"><button onclick="updateBank()">Сохранить</button></div></div></div>
                <div class="setting-group"><h2>🤖 Автоматизация</h2><div class="setting-item"><div><div class="label">Авто-ставки</div><div class="desc">Автоматическое размещение ставок</div></div><div class="toggle active" onclick="this.classList.toggle('active')"><div class="dot"></div></div></div></div>
                <div class="setting-group"><h2>📊 Экспорт / Импорт</h2>
                    <div class="setting-item"><div><div class="label">Экспорт данных</div><div class="desc">Скачать историю в Excel</div></div><button class="btn" onclick="window.location.href='/export'">📥 Скачать</button></div>
                    <div class="setting-item" style="border-bottom:none;"><div><div class="label">Импорт данных</div><div class="desc">Загрузить историю из Excel</div></div><div class="input-group"><label class="file-input-label" for="importFileInput">📤 Выбрать файл</label><input type="file" id="importFileInput" accept=".xlsx,.csv" style="display:none" onchange="importExcel(event)"><span id="fileName" style="color:var(--text-secondary);font-size:12px;">Файл не выбран</span></div></div>
                    <div id="importStatus" class="import-status"></div>
                </div>`;
            el.innerHTML = html;
        }
        
        function runSimulation() {
            const count = parseInt(document.getElementById('simCount').value) || 1000;
            document.getElementById('simResults').style.display = 'block';
            fetch('/api/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: count })
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) { alert('❌ ' + data.error); return; }
                document.getElementById('simProfit').textContent = '$' + data.profit;
                document.getElementById('simWinrate').textContent = data.winrate + '%';
                document.getElementById('simROI').textContent = data.roi + '%';
                document.getElementById('simRisk').textContent = data.risk + '%';
                document.getElementById('simTotal').textContent = data.total;
                document.getElementById('simWins').textContent = data.wins;
                document.getElementById('simLosses').textContent = data.losses;
                document.getElementById('simMaxProfit').textContent = '$' + data.max_profit;
                document.getElementById('simMinProfit').textContent = '$' + data.min_profit;
                document.getElementById('simAvgStake').textContent = '$' + data.avg_stake;
                const rec = document.getElementById('simRecommendation');
                if (data.profit > 0) {
                    rec.innerHTML = '✅ <b style="color:#38ef7d;">Отличный результат!</b> Ваша стратегия принесла бы прибыль!<br>💡 Средняя прибыль на ставку: $' + (data.profit / data.total).toFixed(2) + '<br>🔥 Лучший результат: +$' + data.max_profit;
                } else {
                    rec.innerHTML = '⚠️ <b style="color:#ef473a;">Стратегия требует улучшения</b><br>💡 Попробуйте снизить сумму ставок<br>📊 Работайте над проходимостью (сейчас ' + data.winrate + '%)';
                }
                const ctx = document.getElementById('simChart');
                if (ctx) {
                    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.labels || Array.from({length: data.history?.length || 10}, (_, i) => i + 1),
                            datasets: [{
                                label: 'Прибыль ($)',
                                data: data.history || [],
                                borderColor: data.profit > 0 ? '#38ef7d' : '#ef473a',
                                backgroundColor: data.profit > 0 ? 'rgba(56,239,125,0.1)' : 'rgba(239,71,58,0.1)',
                                fill: true,
                                tension: 0.4,
                                pointRadius: 2
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { labels: { color: isDark ? '#e0e0e0' : '#1a1a2e', font: { size: 10 } } } },
                            scales: {
                                x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 9 } } },
                                y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: v => '$' + v, font: { size: 9 } } }
                            }
                        }
                    });
                }
            });
        }
        
        function updateBank() {
            const value = document.getElementById('bankInput').value;
            fetch('/api/bank', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bank: parseFloat(value) })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) { alert('✅ Банк обновлен: $' + data.bank); location.reload(); }
            });
        }
        
        function importExcel(event) {
            const file = event.target.files[0];
            const statusDiv = document.getElementById('importStatus');
            const fileNameSpan = document.getElementById('fileName');
            if (!file) { statusDiv.textContent = '❌ Файл не выбран'; return; }
            fileNameSpan.textContent = '📄 ' + file.name;
            statusDiv.textContent = '⏳ Загрузка...';
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, {type: 'array'});
                    const sheet = workbook.Sheets[workbook.SheetNames[0]];
                    const json = XLSX.utils.sheet_to_json(sheet);
                    if (json.length === 0) { statusDiv.textContent = '❌ Файл пуст'; return; }
                    statusDiv.textContent = '⏳ Отправка...';
                    fetch('/api/import_excel', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ data: json })
                    })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            statusDiv.textContent = '✅ Импортировано ' + data.count + ' ставок!';
                            setTimeout(() => location.reload(), 1500);
                        } else {
                            statusDiv.textContent = '❌ Ошибка: ' + data.error;
                        }
                    });
                } catch (error) {
                    statusDiv.textContent = '❌ Ошибка: ' + error;
                }
            };
            reader.readAsArrayBuffer(file);
        }
        
        document.getElementById('importFileInput').addEventListener('change', function() {
            if (this.files.length > 0) {
                document.getElementById('fileName').textContent = '📄 ' + this.files[0].name;
            }
        });
        
        document.addEventListener('DOMContentLoaded', function() {
            loadPage('dashboard');
        });
    </script>
</body>
</html>
"""

# ============================================================
# API МАРШРУТЫ
# ============================================================

@app.route('/')
def index():
    """
    Главная страница приложения
    Возвращает HTML-интерфейс
    """
    logger.info("✅ Запрос главной страницы")
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/dashboard_data')
def dashboard_data():
    """
    API для получения данных дашборда
    
    Returns:
        json: Статистика, история ставок и данные для графика
    """
    try:
        data = load_data()
        history = data.get('history', [])
        stats = calculate_stats(history)
        profit_data = get_profit_data(history)
        
        response = {
            'stats': stats,
            'history': history,
            'profit_data': profit_data
        }
        logger.info(f"✅ Дашборд загружен: {len(history)} ставок")
        return jsonify(response)
    except Exception as e:
        logger.error(f"❌ Ошибка в dashboard_data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/matches_data')
def matches_data():
    """
    API для получения данных о матчах
    
    Returns:
        json: Список матчей
    """
    # Здесь можно подключить API-Football
    return jsonify({'matches': []})

@app.route('/api/stats_data')
def stats_data():
    """
    API для получения статистики
    
    Returns:
        json: Статистика и история ставок
    """
    try:
        data = load_data()
        history = data.get('history', [])
        stats = calculate_stats(history)
        return jsonify({'stats': stats, 'history': history})
    except Exception as e:
        logger.error(f"❌ Ошибка в stats_data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulator_data')
def simulator_data():
    """
    API для получения данных для симулятора
    
    Returns:
        json: История ставок
    """
    try:
        data = load_data()
        history = data.get('history', [])
        return jsonify({'history': history})
    except Exception as e:
        logger.error(f"❌ Ошибка в simulator_data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings_data')
def settings_data():
    """
    API для получения настроек
    
    Returns:
        json: Текущий банк
    """
    try:
        data = load_data()
        return jsonify({'stats': {'bank': data.get('bank', 1000)}})
    except Exception as e:
        logger.error(f"❌ Ошибка в settings_data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    """
    API для запуска симуляции
    
    Returns:
        json: Результаты симуляции
    """
    try:
        data = request.json
        count = data.get('count', 1000)
        history = load_data().get('history', [])
        
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок'}), 400
        
        # Расчёт параметров на основе истории
        wins = sum(1 for b in history if b.get('result') == 'win')
        winrate = wins / len(history) if len(history) > 0 else 0
        avg_stake = sum(float(b.get('stake', 0)) for b in history) / len(history) if len(history) > 0 else 10
        
        # Запуск симуляции
        profit_history = []
        total_profit = 0
        
        for _ in range(count):
            if random.random() < winrate:
                profit = avg_stake * random.uniform(0.5, 1.5)
                total_profit += profit
            else:
                profit = -avg_stake
                total_profit += profit
            profit_history.append(round(total_profit, 2))
        
        wins_sim = int(winrate * count)
        
        response = {
            'total': count,
            'wins': wins_sim,
            'losses': count - wins_sim,
            'profit': round(total_profit, 2),
            'winrate': round(winrate * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'risk': round((abs(min(profit_history)) / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'max_profit': round(max(profit_history), 2),
            'min_profit': round(min(profit_history), 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        }
        
        logger.info(f"✅ Симуляция завершена: {count} итераций")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в simulate: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    """
    API для импорта данных из Excel
    
    Returns:
        json: Результат импорта
    """
    try:
        excel_data = request.json.get('data', [])
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        
        data = load_data()
        history = data.get('history', [])
        imported = 0
        
        for row in excel_data:
            # Парсинг названия матча
            match = row.get('Матч', '') or row.get('Match', '')
            home = ''
            away = ''
            
            if ' vs ' in match:
                parts = match.split(' vs ')
                home = parts[0].strip()
                away = parts[1].strip()
            elif ' - ' in match:
                parts = match.split(' - ')
                home = parts[0].strip()
                away = parts[1].strip()
            
            # Парсинг счёта
            score = row.get('Счёт', '') or row.get('Score', '')
            home_goals = None
            away_goals = None
            
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except ValueError:
                    pass
            
            # Парсинг остальных данных
            bet = row.get('Ставка', '') or row.get('Bet', '') or 'Ручная ставка'
            
            try:
                odds = float(row.get('Коэф', 1.85) or row.get('Odds', 1.85) or 1.85)
            except ValueError:
                odds = 1.85
            
            try:
                stake = round(float(row.get('Сумма', 0) or row.get('Stake', 0) or 0), 2)
            except ValueError:
                stake = 0
            
            try:
                ev = float(row.get('EV%', 0) or row.get('Ev', 0) or 0)
            except ValueError:
                ev = 0
            
            result = row.get('Результат', 'pending') or row.get('Result', 'pending')
            result_lower = result.lower()
            
            if result_lower in ['win', 'выигрыш']:
                result = 'win'
            elif result_lower in ['loss', 'проигрыш']:
                result = 'loss'
            elif result_lower in ['push', 'возврат']:
                result = 'push'
            else:
                result = 'pending'
            
            try:
                profit = float(row.get('Прибыль', 0) or row.get('Profit', 0) or 0)
            except ValueError:
                profit = 0
            
            date = row.get('Дата', '') or row.get('Date', '') or datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Добавление ставки в историю
            history.append({
                'home': home or 'Unknown',
                'away': away or 'Unknown',
                'home_goals': home_goals,
                'away_goals': away_goals,
                'bet': bet,
                'odds': odds,
                'stake': stake,
                'ev': ev,
                'result': result,
                'profit': profit,
                'date': date
            })
            imported += 1
        
        data['history'] = history
        save_data(data)
        
        logger.info(f"✅ Импортировано {imported} ставок из Excel")
        return jsonify({'success': True, 'count': imported})
        
    except Exception as e:
        logger.error(f"❌ Ошибка в import_excel: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def update_bank():
    """
    API для обновления банка
    
    Returns:
        json: Результат обновления
    """
    try:
        data = request.json
        if 'bank' in data:
            bank_value = float(data['bank'])
            if bank_value < 0:
                return jsonify({'error': 'Банк не может быть отрицательным'}), 400
            
            d = load_data()
            d['bank'] = bank_value
            save_data(d)
            
            logger.info(f"✅ Банк обновлён: ${bank_value:.2f}")
            return jsonify({'success': True, 'bank': bank_value})
        return jsonify({'error': 'Нет значения банка'}), 400
        
    except Exception as e:
        logger.error(f"❌ Ошибка в update_bank: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/export')
def export_data():
    """
    Экспорт данных в Excel
    
    Returns:
        file: Excel-файл с историей ставок
    """
    try:
        import io
        import xlsxwriter
        
        data = load_data()
        history = data.get('history', [])
        
        if not history:
            return "Нет данных для экспорта", 404
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('История')
        
        # Заголовки
        headers = ['Дата', 'Матч', 'Счёт', 'Ставка', 'Кэф', 'Сумма', 'EV', 'Результат', 'Прибыль']
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)
        
        # Данные
        for row, bet in enumerate(history, 1):
            score = f"{bet.get('home_goals', '')}-{bet.get('away_goals', '')}" if bet.get('home_goals') is not None else '-'
            worksheet.write(row, 0, bet.get('date', ''))
            worksheet.write(row, 1, f"{bet.get('home', '')} vs {bet.get('away', '')}")
            worksheet.write(row, 2, score)
            worksheet.write(row, 3, bet.get('bet', ''))
            worksheet.write(row, 4, bet.get('odds', ''))
            worksheet.write(row, 5, bet.get('stake', ''))
            worksheet.write(row, 6, bet.get('ev', ''))
            worksheet.write(row, 7, bet.get('result', ''))
            worksheet.write(row, 8, bet.get('profit', ''))
        
        workbook.close()
        output.seek(0)
        
        logger.info(f"✅ Экспортировано {len(history)} ставок в Excel")
        return output.getvalue(), 200, {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': 'attachment; filename=history.xlsx'
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка в export_data: {e}")
        logger.error(traceback.format_exc())
        return f"Ошибка экспорта: {e}", 500

# ============================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================================================

def main():
    """
    Главная функция запуска приложения
    """
    try:
        # Создание файла данных при отсутствии
        if not os.path.exists(DATA_FILE):
            save_data({'bank': 1000, 'history': []})
            logger.info("✅ Создан новый файл данных")
        
        # Получение порта из переменных окружения
        port = int(os.environ.get('PORT', 8080))
        
        logger.info(f"🚀 Запуск приложения на порту {port}")
        logger.info(f"📊 Файл данных: {DATA_FILE}")
        logger.info(f"🤖 Токен бота: {'✅ Установлен' if TOKEN_VALID else '❌ НЕ УСТАНОВЛЕН'}")
        
        # Запуск Flask-приложения
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            threaded=True
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске приложения: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

# Запуск приложения
if __name__ == '__main__':
    main()
