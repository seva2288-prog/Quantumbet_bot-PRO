import os
import json
import logging
import random
import requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, request

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# ⭐ ВСЕ КЛЮЧИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ (RENDER)
# ============================================================

# Telegram Bot Token (обязательно!)
BOT_TOKEN = os.environ.get('8884017743:AAEDsDQEV5NZe2x9-XTlZHrsBJ99UtgLHj8', '')

# Ваш Telegram Chat ID (обязательно!)
CHAT_ID = os.environ.get('228801334', '')

# Секретный ключ для Flask (обязательно!)
SECRET_KEY = os.environ.get('SECRET_KEY', 'default-secret-key-change-me')

# URL веб-интерфейса (обязательно!)
WEB_URL = os.environ.get('WEB_URL', 'https://quantumnet-web.onrender.com')

# API ключ для погоды (опционально)
WEATHER_API_KEY = os.environ.get('7f0cfaed346b0fe364815ab65d627af2', '')

# API ключ для футбольных данных (опционально)
FOOTBALL_API_KEY = os.environ.get('2c34b71a9086c34f9a59f30c814283f5', '')

# API ключ для коэффициентов (опционально)
ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')

# API ключ для новостей (опционально)
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '')

# ============================================================
# ПРОВЕРКА КЛЮЧЕЙ ПРИ ЗАПУСКЕ
# ============================================================

logger.info("=" * 60)
logger.info("🔑 ПРОВЕРКА КЛЮЧЕЙ:")
logger.info(f"  BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'} {BOT_TOKEN[:15] + '...' if BOT_TOKEN else 'НЕ УСТАНОВЛЕН!'}")
logger.info(f"  CHAT_ID: {'✅' if CHAT_ID else '❌'} {CHAT_ID if CHAT_ID else 'НЕ УСТАНОВЛЕН!'}")
logger.info(f"  SECRET_KEY: {'✅' if SECRET_KEY else '❌'}")
logger.info(f"  WEB_URL: {'✅' if WEB_URL else '❌'} {WEB_URL}")
logger.info(f"  WEATHER_API_KEY: {'✅' if WEATHER_API_KEY else '❌'}")
logger.info(f"  FOOTBALL_API_KEY: {'✅' if FOOTBALL_API_KEY else '❌'}")
logger.info(f"  ODDS_API_KEY: {'✅' if ODDS_API_KEY else '❌'}")
logger.info(f"  NEWS_API_KEY: {'✅' if NEWS_API_KEY else '❌'}")
logger.info("=" * 60)

# ============================================================
# ДАННЫЕ
# ============================================================

DATA_FILE = 'data.json'

def load_data():
    """Загружает данные из data.json"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ Загружено {len(data.get('history', []))} ставок")
                return data
        else:
            logger.info("📄 data.json не найден, создаю новый")
            return {"bank": 1000, "history": []}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return {"bank": 1000, "history": []}

def save_data(data):
    """Сохраняет данные в data.json"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Данные сохранены: {len(data.get('history', []))} ставок")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def get_stats(history):
    """Вычисляет статистику из истории"""
    total = len(history)
    if total == 0:
        return {
            'total_bets': 0,
            'wins': 0,
            'losses': 0,
            'pushes': 0,
            'pending': 0,
            'profit': 0,
            'winrate': 0,
            'roi': 0,
            'avg_stake': 0
        }
    
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    pushes = sum(1 for b in history if b.get('result') == 'push')
    pending = sum(1 for b in history if b.get('result') == 'pending')
    profit = sum(float(b.get('profit', 0)) for b in history)
    winrate = round((wins / total * 100), 1) if total > 0 else 0
    
    stakes = [float(b.get('stake', 0)) for b in history if b.get('stake', 0) > 0]
    avg_stake = round(sum(stakes) / len(stakes), 2) if stakes else 0
    total_stake = sum(stakes)
    roi = round((profit / total_stake * 100), 2) if total_stake > 0 else 0
    
    return {
        'total_bets': total,
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'pending': pending,
        'profit': round(profit, 2),
        'winrate': winrate,
        'roi': roi,
        'avg_stake': avg_stake
    }

def get_profit_data(history):
    """Данные для графика прибыли за 7 дней"""
    profits = []
    for i in range(6, -1, -1):
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
            except:
                pass
        profits.append(round(day_profit, 2))
    
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(6, -1, -1)]
    return {'dates': dates, 'profits': profits}

# ============================================================
# ФУНКЦИЯ ОТПРАВКИ СООБЩЕНИЙ В TELEGRAM
# ============================================================

def send_telegram_message(chat_id, text):
    """Отправляет сообщение в Telegram используя BOT_TOKEN"""
    global BOT_TOKEN
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        return None
    
    try:
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Сообщение отправлено в chat_id: {chat_id}")
        else:
            logger.error(f"❌ Ошибка отправки: {response.text}")
        
        return response.json()
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        return None

# ============================================================
# ФУНКЦИЯ ПОГОДЫ (если есть WEATHER_API_KEY)
# ============================================================

def get_weather(city):
    """Получает погоду для города используя WEATHER_API_KEY"""
    global WEATHER_API_KEY
    
    if not WEATHER_API_KEY:
        return "❌ WEATHER_API_KEY не установлен"
    
    try:
        url = f'http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}&lang=ru'
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            temp = data['current']['temp_c']
            condition = data['current']['condition']['text']
            return f"🌤️ Погода в {city}:\nТемпература: {temp}°C\n{condition}"
        else:
            return f"❌ Ошибка получения погоды: {response.status_code}"
    except Exception as e:
        logger.error(f"❌ Ошибка погоды: {e}")
        return f"❌ Ошибка: {e}"

# ============================================================
# API МАРШРУТЫ
# ============================================================

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'service': 'Quantum Bet Bot',
        'version': 'v12 PRO',
        'keys': {
            'bot_token': bool(BOT_TOKEN),
            'chat_id': bool(CHAT_ID),
            'secret_key': bool(SECRET_KEY),
            'weather': bool(WEATHER_API_KEY),
            'football': bool(FOOTBALL_API_KEY),
            'odds': bool(ODDS_API_KEY),
            'news': bool(NEWS_API_KEY)
        }
    })

@app.route('/api/health')
def health():
    data = load_data()
    return jsonify({
        'status': 'ok',
        'bank': data.get('bank', 1000),
        'total_bets': len(data.get('history', [])),
        'keys': {
            'bot_token': bool(BOT_TOKEN),
            'chat_id': bool(CHAT_ID),
            'weather': bool(WEATHER_API_KEY),
            'football': bool(FOOTBALL_API_KEY)
        }
    })

@app.route('/api/stats')
def api_stats():
    data = load_data()
    stats = get_stats(data.get('history', []))
    stats['bank'] = data.get('bank', 1000)
    return jsonify(stats)

@app.route('/api/history')
def api_history():
    return jsonify(load_data().get('history', []))

@app.route('/api/all_data')
def api_all_data():
    data = load_data()
    history = data.get('history', [])
    stats = get_stats(history)
    stats['bank'] = data.get('bank', 1000)
    return jsonify({
        'stats': stats,
        'history': history,
        'profit_data': get_profit_data(history),
        'matches': []
    })

@app.route('/api/bank', methods=['POST'])
def api_bank():
    data = load_data()
    data['bank'] = float(request.json.get('bank', 1000))
    save_data(data)
    return jsonify({'success': True, 'bank': data['bank']})

@app.route('/api/edit_bet', methods=['POST'])
def api_edit_bet():
    try:
        req = request.json
        idx = req.get('index')
        data = load_data()
        history = data.get('history', [])
        
        if idx >= len(history):
            return jsonify({'error': 'Not found'}), 404
        
        bet = history[idx]
        for key in ['home', 'away', 'bet', 'result']:
            if key in req:
                bet[key] = req[key]
        for key in ['odds', 'stake', 'ev']:
            if key in req:
                bet[key] = float(req[key])
        
        stake = float(bet.get('stake', 0))
        odds = float(bet.get('odds', 1))
        if bet.get('result') == 'win':
            bet['profit'] = round(stake * (odds - 1), 2)
        elif bet.get('result') == 'loss':
            bet['profit'] = -stake
        else:
            bet['profit'] = 0
        
        save_data(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def api_delete_bet():
    try:
        idx = request.json.get('index')
        data = load_data()
        history = data.get('history', [])
        if idx < len(history):
            history.pop(idx)
            save_data(data)
            return jsonify({'success': True})
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    try:
        count = request.json.get('count', 1000)
        data = load_data()
        history = data.get('history', [])
        
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок'}), 400
        
        wins = sum(1 for b in history if b.get('result') == 'win')
        winrate = wins / len(history) if history else 0
        
        stakes = [float(b.get('stake', 0)) for b in history if b.get('stake', 0) > 0]
        avg_stake = sum(stakes) / len(stakes) if stakes else 10
        
        profit_history = []
        total_profit = 0
        
        for _ in range(count):
            if random.random() < winrate:
                total_profit += avg_stake * random.uniform(0.5, 2.0)
            else:
                total_profit -= avg_stake
            profit_history.append(round(total_profit, 2))
        
        return jsonify({
            'total': count,
            'wins': int(winrate * count),
            'losses': count - int(winrate * count),
            'profit': round(total_profit, 2),
            'winrate': round(winrate * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2),
            'risk': round((abs(min(profit_history)) / (avg_stake * count)) * 100, 2),
            'max_profit': round(max(profit_history), 2),
            'min_profit': round(min(profit_history), 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export')
def api_export():
    try:
        import pandas as pd
        import io
        
        data = load_data()
        history = data.get('history', [])
        
        if not history:
            return jsonify({'error': 'Нет данных'}), 404
        
        df = pd.DataFrame(history)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='History')
        
        output.seek(0)
        return output.getvalue(), 200, {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': 'attachment; filename=quantum_bet_history.xlsx'
        }
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_manual_match', methods=['POST'])
def api_add_manual_match():
    try:
        req = request.json
        data = load_data()
        history = data.get('history', [])
        
        match = req.get('match', 'Unknown vs Unknown')
        home, away = match.split(' vs ') if ' vs ' in match else ('Unknown', 'Unknown')
        
        score = req.get('score', '-')
        home_goals, away_goals = None, None
        if '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0])
                away_goals = int(parts[1])
            except:
                pass
        
        bet = {
            'home': home,
            'away': away,
            'league': 'Ручной ввод',
            'bet': req.get('bet', 'Ручная ставка'),
            'odds': float(req.get('odds', 1.85)),
            'stake': float(req.get('stake', 0)),
            'ev': 0,
            'result': req.get('result', 'pending'),
            'profit': 0,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': home_goals,
            'away_goals': away_goals
        }
        
        stake = bet['stake']
        odds = bet['odds']
        if bet['result'] == 'win':
            bet['profit'] = round(stake * (odds - 1), 2)
        elif bet['result'] == 'loss':
            bet['profit'] = -stake
        else:
            bet['profit'] = 0
        
        history.append(bet)
        save_data(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def api_import_excel():
    try:
        excel_data = request.json.get('data', [])
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        
        data = load_data()
        history = data.get('history', [])
        
        imported = 0
        for row in excel_data:
            match = row.get('Матч', '') or row.get('Match', '')
            home, away = 'Unknown', 'Unknown'
            if ' vs ' in match:
                parts = match.split(' vs ')
                home, away = parts[0].strip(), parts[1].strip()
            elif ' - ' in match:
                parts = match.split(' - ')
                home, away = parts[0].strip(), parts[1].strip()
            
            score = row.get('Счёт', '') or row.get('Score', '')
            home_goals, away_goals = None, None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
            
            bet = {
                'home': home,
                'away': away,
                'league': 'Импорт из Excel',
                'bet': row.get('Ставка', '') or row.get('Bet', 'Ручная ставка'),
                'odds': float(row.get('Коэф', 1.85) or row.get('Odds', 1.85)),
                'stake': float(row.get('Сумма', 0) or row.get('Stake', 0)),
                'ev': float(row.get('EV%', 0) or row.get('Ev', 0)),
                'result': str(row.get('Результат', 'pending') or row.get('Result', 'pending')).lower(),
                'profit': float(row.get('Прибыль', 0) or row.get('Profit', 0)),
                'date': row.get('Дата', '') or row.get('Date', datetime.now().strftime('%Y-%m-%d %H:%M')),
                'home_goals': home_goals,
                'away_goals': away_goals
            }
            
            if bet['result'] in ['win', 'выигрыш']:
                bet['result'] = 'win'
            elif bet['result'] in ['loss', 'проигрыш']:
                bet['result'] = 'loss'
            elif bet['result'] in ['push', 'возврат']:
                bet['result'] = 'push'
            else:
                bet['result'] = 'pending'
            
            history.append(bet)
            imported += 1
        
        data['history'] = history
        save_data(data)
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def api_import_project():
    try:
        req = request.json
        history = req.get('history', [])
        
        if not history:
            return jsonify({'error': 'Нет данных'}), 400
        
        data = load_data()
        current_history = data.get('history', [])
        
        if 'bank' in req:
            data['bank'] = req['bank']
        
        imported = 0
        for bet in history:
            is_duplicate = False
            for existing in current_history:
                if (existing.get('date') == bet.get('date') and 
                    existing.get('home') == bet.get('home') and 
                    existing.get('away') == bet.get('away')):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                current_history.append(bet)
                imported += 1
        
        data['history'] = current_history
        save_data(data)
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# ⭐ ТЕЛЕГРАМ ВЕБХУК (СО ВСЕМИ КОМАНДАМИ)
# ============================================================

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Обработка вебхука от Telegram"""
    global BOT_TOKEN, CHAT_ID, WEATHER_API_KEY
    
    if request.method == 'GET':
        return jsonify({
            'status': 'ok',
            'message': 'Webhook endpoint is working!',
            'keys': {
                'bot_token': bool(BOT_TOKEN),
                'chat_id': bool(CHAT_ID),
                'weather': bool(WEATHER_API_KEY)
            }
        })
    
    try:
        data = request.get_json()
        logger.info(f"📩 Получен вебхук: {data}")
        
        if not data:
            return jsonify({'error': 'No data'}), 400
        
        if 'message' not in data:
            return jsonify({'status': 'ok', 'message': 'Not a message'})
        
        message = data['message']
        chat_id = message['chat']['id']
        text = message.get('text', '')
        username = message['chat'].get('username', 'Unknown')
        
        logger.info(f"📨 Сообщение от @{username} (chat_id: {chat_id}): {text}")
        
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN не установлен!")
            return jsonify({'error': 'BOT_TOKEN not set'}), 500
        
        # ============================================================
        # ОБРАБОТКА КОМАНД
        # ============================================================
        
        if text == '/start':
            reply = (
                "🤖 <b>Quantum Bet Bot</b>\n\n"
                "Привет! Я помогу тебе управлять ставками.\n\n"
                "<b>📋 Команды:</b>\n"
                "/stats - 📊 Статистика\n"
                "/bank - 💰 Текущий банк\n"
                "/today - 🔥 ТОП-5 из кэша\n"
                "/update - 🔄 Поиск матчей\n"
                "/weather [город] - 🌤️ Погода\n"
                "/help - ℹ️ Помощь"
            )
        
        elif text == '/stats':
            data = load_data()
            history = data.get('history', [])
            stats = get_stats(history)
            stats['bank'] = data.get('bank', 1000)
            reply = (
                f"📊 <b>Статистика</b>\n\n"
                f"💰 Банк: <b>${stats['bank']}</b>\n"
                f"📈 Всего: <b>{stats['total_bets']}</b>\n"
                f"✅ Выигрыши: <b>{stats['wins']}</b>\n"
                f"❌ Проигрыши: <b>{stats['losses']}</b>\n"
                f"🔄 Возвраты: <b>{stats['pushes']}</b>\n"
                f"🎯 Проходимость: <b>{stats['winrate']}%</b>\n"
                f"📈 Прибыль: <b>${stats['profit']}</b>\n"
                f"📊 ROI: <b>{stats['roi']}%</b>"
            )
        
        elif text == '/bank':
            data = load_data()
            reply = f"💰 <b>Текущий банк:</b> ${data.get('bank', 1000)}"
        
        elif text == '/today':
            data = load_data()
            history = data.get('history', [])
            if history:
                last_bets = history[-5:][::-1]
                reply = "🔥 <b>ТОП-5 последних ставок</b>\n\n"
                for bet in last_bets:
                    status = "✅ WIN" if bet.get('result') == 'win' else "❌ LOSS" if bet.get('result') == 'loss' else "🔄 PUSH"
                    reply += f"• {bet.get('home', '?')} vs {bet.get('away', '?')} - {status} (${bet.get('profit', 0)})\n"
            else:
                reply = "📭 Нет данных о ставках"
        
        elif text == '/update':
            reply = (
                "🔄 <b>Поиск матчей на сегодня...</b>\n\n"
                "Функция в разработке.\n"
                "Скоро здесь будут матчи с коэффициентами!"
            )
        
        elif text == '/help':
            reply = (
                "ℹ️ <b>Помощь</b>\n\n"
                "<b>📋 Команды:</b>\n"
                "/start - Приветствие\n"
                "/stats - 📊 Статистика\n"
                "/bank - 💰 Текущий банк\n"
                "/today - 🔥 ТОП-5 из кэша\n"
                "/update - 🔄 Поиск матчей\n"
                "/weather [город] - 🌤️ Погода\n\n"
                "📱 <b>Веб-интерфейс:</b>\n"
                f"{WEB_URL}"
            )
        
        elif text.startswith('/weather'):
            city = text.replace('/weather', '').strip()
            if city:
                reply = get_weather(city)
            else:
                reply = "❌ Укажите город: /weather Москва"
        
        else:
            reply = (
                f"❓ Неизвестная команда: {text}\n\n"
                "Используйте /start для списка команд"
            )
        
        # Отправляем ответ
        send_telegram_message(chat_id, reply)
        
        return jsonify({'status': 'ok', 'message': 'Processed'})
        
    except Exception as e:
        logger.error(f"❌ Ошибка вебхука: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Запуск бота на порту {port}")
    
    # Создаем data.json если нет
    if not os.path.exists(DATA_FILE):
        logger.info("📄 Создаю новый data.json")
        save_data({"bank": 1000, "history": []})
    
    # Вывод статуса ключей при запуске
    logger.info("=" * 60)
    logger.info("🚀 БОТ ЗАПУЩЕН СО ВСЕМИ КЛЮЧАМИ:")
    logger.info(f"  BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
    logger.info(f"  CHAT_ID: {'✅' if CHAT_ID else '❌'}")
    logger.info(f"  SECRET_KEY: {'✅' if SECRET_KEY else '❌'}")
    logger.info(f"  WEB_URL: {'✅' if WEB_URL else '❌'}")
    logger.info(f"  WEATHER_API_KEY: {'✅' if WEATHER_API_KEY else '❌'}")
    logger.info(f"  FOOTBALL_API_KEY: {'✅' if FOOTBALL_API_KEY else '❌'}")
    logger.info(f"  ODDS_API_KEY: {'✅' if ODDS_API_KEY else '❌'}")
    logger.info(f"  NEWS_API_KEY: {'✅' if NEWS_API_KEY else '❌'}")
    logger.info("=" * 60)
    
    logger.info("✅ Маршрут /webhook зарегистрирован")
    
    app.run(host='0.0.0.0', port=port, debug=False)
