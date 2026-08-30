import json
import os
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import random

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# РАБОТА С ДАННЫМИ
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
            return create_default_data()
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        return create_default_data()

def create_default_data():
    """Создает структуру данных по умолчанию"""
    return {
        "bank": 1000,
        "history": [],
        "created_at": datetime.now().isoformat()
    }

def save_data(data):
    """Сохраняет данные в data.json с бэкапом"""
    try:
        # Создаем бэкап
        if os.path.exists(DATA_FILE):
            backup_file = f"{DATA_FILE}.backup"
            with open(backup_file, 'w', encoding='utf-8') as f:
                with open(DATA_FILE, 'r', encoding='utf-8') as src:
                    f.write(src.read())
            logger.info(f"💾 Создан бэкап: {backup_file}")
        
        # Сохраняем новые данные
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
    days = 7
    
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
            except:
                pass
        profits.append(round(day_profit, 2))
    
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}

# ============================================================
# API МАРШРУТЫ
# ============================================================

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'service': 'Quantum Bet Bot API',
        'version': 'v12 PRO',
        'endpoints': [
            '/api/stats',
            '/api/history',
            '/api/update_history',
            '/api/bank',
            '/api/edit_bet',
            '/api/delete_bet',
            '/api/simulate',
            '/api/export'
        ]
    })

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Возвращает статистику"""
    data = load_data()
    history = data.get('history', [])
    stats = get_stats(history)
    stats['bank'] = data.get('bank', 1000)
    return jsonify(stats)

@app.route('/api/history', methods=['GET'])
def api_history():
    """Возвращает историю ставок"""
    data = load_data()
    return jsonify(data.get('history', []))

@app.route('/api/all_data', methods=['GET'])
def api_all_data():
    """Возвращает все данные"""
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

@app.route('/api/update_history', methods=['POST'])
def api_update_history():
    """Обновляет историю ставок"""
    try:
        request_data = request.json
        new_history = request_data.get('history', [])
        
        if not new_history:
            return jsonify({'error': 'Нет данных'}), 400
        
        data = load_data()
        data['history'] = new_history
        
        if save_data(data):
            return jsonify({
                'success': True,
                'count': len(new_history),
                'message': f'Обновлено {len(new_history)} ставок'
            })
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        logger.error(f"Ошибка update_history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def api_update_bank():
    """Обновляет банк"""
    try:
        request_data = request.json
        new_bank = request_data.get('bank')
        
        if new_bank is None:
            return jsonify({'error': 'Bank value required'}), 400
        
        data = load_data()
        data['bank'] = float(new_bank)
        
        if save_data(data):
            return jsonify({
                'success': True,
                'bank': data['bank']
            })
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def api_edit_bet():
    """Редактирует ставку по индексу"""
    try:
        request_data = request.json
        index = request_data.get('index')
        
        if index is None:
            return jsonify({'error': 'Index required'}), 400
        
        data = load_data()
        history = data.get('history', [])
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        # Обновляем поля
        for key in ['home', 'away', 'bet', 'result']:
            if key in request_data:
                history[index][key] = request_data[key]
        
        for key in ['odds', 'stake', 'ev']:
            if key in request_data:
                history[index][key] = float(request_data[key])
        
        if 'home_goals' in request_data:
            history[index]['home_goals'] = request_data['home_goals']
        if 'away_goals' in request_data:
            history[index]['away_goals'] = request_data['away_goals']
        
        # Пересчитываем прибыль
        result = history[index].get('result')
        stake = float(history[index].get('stake', 0))
        odds = float(history[index].get('odds', 1))
        
        if result == 'win':
            history[index]['profit'] = round(stake * (odds - 1), 2)
        elif result == 'loss':
            history[index]['profit'] = -stake
        else:
            history[index]['profit'] = 0
        
        data['history'] = history
        
        if save_data(data):
            return jsonify({'success': True, 'message': 'Ставка обновлена'})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def api_delete_bet():
    """Удаляет ставку по индексу"""
    try:
        request_data = request.json
        index = request_data.get('index')
        
        if index is None:
            return jsonify({'error': 'Index required'}), 400
        
        data = load_data()
        history = data.get('history', [])
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        deleted = history.pop(index)
        data['history'] = history
        
        if save_data(data):
            return jsonify({
                'success': True,
                'deleted': deleted,
                'message': 'Ставка удалена'
            })
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    """Симулятор ставок"""
    try:
        request_data = request.json
        count = request_data.get('count', 1000)
        
        data = load_data()
        history = data.get('history', [])
        
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок'}), 400
        
        # Вычисляем проходимость
        wins = sum(1 for b in history if b.get('result') == 'win')
        total = len(history)
        winrate = wins / total if total > 0 else 0
        
        # Средняя ставка
        stakes = [float(b.get('stake', 0)) for b in history if b.get('stake', 0) > 0]
        avg_stake = sum(stakes) / len(stakes) if stakes else 10
        
        # Симуляция
        profit_history = []
        total_profit = 0
        
        for i in range(count):
            if random.random() < winrate:
                profit = avg_stake * random.uniform(0.5, 2.0)
                total_profit += profit
            else:
                profit = -avg_stake
                total_profit += profit
            
            profit_history.append(round(total_profit, 2))
        
        max_profit = max(profit_history) if profit_history else 0
        min_profit = min(profit_history) if profit_history else 0
        
        wins_sim = int(winrate * count)
        losses_sim = count - wins_sim
        
        return jsonify({
            'total': count,
            'wins': wins_sim,
            'losses': losses_sim,
            'profit': round(total_profit, 2),
            'winrate': round(winrate * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2),
            'risk': round((abs(min_profit) / (avg_stake * count)) * 100, 2),
            'max_profit': round(max_profit, 2),
            'min_profit': round(min_profit, 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def api_import_excel():
    """Импорт данных из Excel"""
    try:
        request_data = request.json
        excel_data = request_data.get('data', [])
        
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        
        data = load_data()
        history = data.get('history', [])
        
        imported = 0
        for row in excel_data:
            # Парсим матч
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
            
            # Парсим счет
            score = row.get('Счёт', '') or row.get('Scht', '') or row.get('Score', '')
            home_goals = None
            away_goals = None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
            
            # Ставка
            bet = row.get('Ставка', '') or row.get('Stanka', '') or 'Ручная ставка'
            
            # Коэффициент
            odds = 1.85
            try:
                odds = float(row.get('Коэф', 1.85) or row.get('Kofy', 1.85) or 1.85)
            except:
                odds = 1.85
            
            # Сумма
            stake = 0
            try:
                stake = float(row.get('Сумма', 0) or row.get('Stake', 0) or 0)
            except:
                stake = 0
            
            # EV
            ev = 0
            try:
                ev = float(row.get('EV%', 0) or row.get('Ev', 0) or 0)
            except:
                ev = 0
            
            # Результат
            result = row.get('Результат', 'pending') or row.get('Result', 'pending')
            result = str(result).lower()
            if result in ['win', 'выигрыш']:
                result = 'win'
            elif result in ['loss', 'проигрыш']:
                result = 'loss'
            elif result in ['push', 'возврат']:
                result = 'push'
            else:
                result = 'pending'
            
            # Прибыль
            profit = 0
            try:
                profit = float(row.get('Прибыль', 0) or row.get('Profit', 0) or 0)
            except:
                profit = 0
            
            # Дата
            date = row.get('Дата', '') or row.get('Data', '') or datetime.now().strftime('%Y-%m-%d %H:%M')
            if not date:
                date = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Проверяем дубликат
            is_duplicate = False
            for existing in history:
                if (existing.get('date') == date and 
                    existing.get('home') == home and 
                    existing.get('away') == away):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                bet_record = {
                    'home': home or 'Unknown',
                    'away': away or 'Unknown',
                    'league': 'Импорт из Excel',
                    'bet': bet,
                    'odds': odds,
                    'stake': stake,
                    'ev': ev,
                    'result': result,
                    'profit': profit,
                    'date': date,
                    'home_goals': home_goals,
                    'away_goals': away_goals
                }
                history.append(bet_record)
                imported += 1
        
        data['history'] = history
        
        if save_data(data):
            return jsonify({'success': True, 'count': imported})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def api_import_project():
    """Импорт проекта"""
    try:
        request_data = request.json
        history = request_data.get('history', [])
        stats = request_data.get('stats', {})
        
        if not history:
            return jsonify({'error': 'Нет данных'}), 400
        
        data = load_data()
        current_history = data.get('history', [])
        
        # Обновляем банк
        if stats and 'bank' in stats:
            data['bank'] = stats['bank']
        
        # Добавляем новые ставки
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
        
        if save_data(data):
            return jsonify({'success': True, 'count': imported})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['GET'])
def api_export():
    """Экспорт данных в Excel (через веб)"""
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

@app.route('/api/health', methods=['GET'])
def api_health():
    """Проверка здоровья бота"""
    data = load_data()
    return jsonify({
        'status': 'ok',
        'bank': data.get('bank', 1000),
        'total_bets': len(data.get('history', [])),
        'data_file': DATA_FILE,
        'data_file_exists': os.path.exists(DATA_FILE)
    })

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Запуск бота на порту {port}")
    logger.info(f"📄 Файл данных: {DATA_FILE}")
    
    # Проверяем наличие data.json
    if not os.path.exists(DATA_FILE):
        logger.info("📄 Создаю новый data.json")
        save_data(create_default_data())
    
    app.run(host='0.0.0.0', port=port, debug=False)
