import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request
import requests
from datetime import datetime, timedelta
import json
import logging
from collections import defaultdict
import re
import time

# Импорт анализатора матчей
from match_analyzer import MatchAnalyzer

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_URL = os.environ.get('BOT_URL', 'https://quantumbet-bot-pro.onrender.com')
print(f"🔗 Бот URL: {BOT_URL}")

# ============================================================
# ПРОВЕРКА БОТА
# ============================================================

def check_bot_health():
    try:
        response = requests.get(f'{BOT_URL}/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Бот доступен: {data}")
            return True, data
        else:
            logger.warning(f"⚠️ Бот вернул код {response.status_code}")
            return False, None
    except Exception as e:
        logger.error(f"❌ Бот недоступен: {e}")
        return False, None

def get_bot_status():
    try:
        response = requests.get(f'{BOT_URL}/health', timeout=5)
        if response.status_code == 200:
            return response.json()
        return {'status': 'error', 'code': response.status_code}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def safe_parse_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_parse_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# ============================================================
# ГЛАВНАЯ СТРАНИЦА
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

# ============================================================
# API МАРШРУТЫ
# ============================================================

@app.route('/api/all_data')
def api_all_data():
    try:
        response = requests.get(f'{BOT_URL}/api/all_data', timeout=15)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': f'Бот вернул ошибку {response.status_code}'}), 500
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/matches')
def api_matches():
    try:
        response = requests.get(f'{BOT_URL}/api/matches', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify([])
    except Exception as e:
        logger.error(f"Ошибка получения матчей: {e}")
        return jsonify([])

@app.route('/api/stats')
def api_stats():
    try:
        response = requests.get(f'{BOT_URL}/api/stats', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({'bank': 1000, 'total_bets': 0, 'wins': 0, 'losses': 0, 'profit': 0})
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return jsonify({'bank': 1000, 'total_bets': 0, 'wins': 0, 'losses': 0, 'profit': 0})

@app.route('/api/history')
def api_history():
    try:
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify([])
    except Exception as e:
        logger.error(f"Ошибка получения истории: {e}")
        return jsonify([])

@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/bank', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка обновления банка: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/simulate', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка симуляции: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/import_excel', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка импорта Excel: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/import_project', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка импорта проекта: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/edit_bet', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка редактирования ставки: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/delete_bet', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка удаления ставки: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/add_manual_match', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Ошибка добавления матча: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/send_command', methods=['POST'])
def send_command():
    try:
        data = request.json
        command = data.get('command', '')
        
        if not command:
            return jsonify({'success': False, 'error': 'Команда не указана'}), 400
        
        telegram_token = os.environ.get('TELEGRAM_TOKEN', '')
        admin_chat_id = os.environ.get('ADMIN_CHAT_ID', '')
        
        if not telegram_token or not admin_chat_id:
            response = requests.post(f'{BOT_URL}/api/command', json={'command': command}, timeout=10)
            if response.status_code == 200:
                return jsonify({'success': True, 'message': f'Команда {command} отправлена боту'})
            else:
                return jsonify({'success': False, 'error': f'Ошибка бота: {response.status_code}'}), 500
        
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            'chat_id': admin_chat_id,
            'text': command,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': f'Команда {command} отправлена в Telegram'})
        else:
            return jsonify({'success': False, 'error': f'Ошибка Telegram: {response.status_code}'}), 500
            
    except Exception as e:
        logger.error(f"Ошибка отправки команды: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/save_settings', methods=['POST'])
def save_settings():
    try:
        data = request.json
        
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_settings.json')
        with open(settings_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        try:
            response = requests.post(f'{BOT_URL}/api/update_settings', json=data, timeout=5)
            if response.status_code != 200:
                logger.warning(f"Не удалось обновить настройки в боте: {response.status_code}")
        except Exception as e:
            logger.warning(f"Ошибка отправки настроек в бот: {e}")
        
        return jsonify({'success': True, 'message': 'Настройки сохранены'})
        
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_settings', methods=['GET'])
def get_settings():
    try:
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_settings.json')
        
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
            return jsonify({'success': True, 'settings': settings})
        else:
            default_settings = {
                'ev_min_70': 20,
                'prob_min_70': 60,
                'xg_min_70': 1.8,
                'xg_max_70': 3.0,
                'position_max_70': 15,
                'premium_ev': 30,
                'standard_ev': 15,
                'xg_min_tm25': 1.0,
                'xg_max_tm25': 3.0,
                'max_tm25_bets': 5,
                'top_league_ev': 35
            }
            return jsonify({'success': True, 'settings': default_settings})
            
    except Exception as e:
        logger.error(f"Ошибка загрузки настроек: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# API ДЛЯ АНАЛИЗА МАТЧЕЙ
# ============================================================

@app.route('/api/analyze_matches', methods=['POST'])
def analyze_matches():
    try:
        data = request.json
        log_text = data.get('log', '')
        
        if not log_text:
            return jsonify({
                'success': False,
                'error': 'Лог не предоставлен'
            }), 400
        
        stats = MatchAnalyzer.analyze_logs(log_text)
        recommendations = MatchAnalyzer.get_recommendations(stats)
        
        stats['analysis_time'] = datetime.now().isoformat()
        stats['log_length'] = len(log_text)
        stats['lines_analyzed'] = len([line for line in log_text.split('\n') if 'Пропускаем' in line])
        
        return jsonify({
            'success': True,
            'stats': stats,
            'recommendations': recommendations
        })
        
    except Exception as e:
        logger.error(f"Ошибка анализа матчей: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/matches_log')
def get_matches_log():
    try:
        # Пробуем получить лог от бота
        try:
            response = requests.get(f'{BOT_URL}/api/log', timeout=5)
            if response.status_code == 200:
                data = response.json()
                log_text = data.get('log', '')
                if log_text and len(log_text) > 100:
                    return jsonify({
                        'log': log_text,
                        'source': 'bot_api',
                        'timestamp': datetime.now().isoformat()
                    })
        except Exception as e:
            logger.warning(f"Не удалось получить лог через API: {e}")
        
        # Пробуем получить лог из локального файла
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'matches_log.txt')
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_text = f.read()
            if log_text and len(log_text) > 100:
                return jsonify({
                    'log': log_text,
                    'source': 'local_file',
                    'timestamp': datetime.fromtimestamp(os.path.getmtime(log_file)).isoformat()
                })
        
        # Пробуем создать лог из матчей
        try:
            matches_response = requests.get(f'{BOT_URL}/api/matches', timeout=5)
            if matches_response.status_code == 200:
                matches = matches_response.json()
                if matches and len(matches) > 0:
                    log_lines = []
                    for match in matches:
                        xg = match.get('total_xg', 0)
                        home = match.get('home', 'Unknown')
                        away = match.get('away', 'Unknown')
                        skip_reason = match.get('skip_reason', '')
                        
                        if skip_reason:
                            if 'xg' in skip_reason.lower() or 'XG' in skip_reason:
                                log_lines.append(f"⏭️ Пропускаем (XG вне диапазона 1.8-3.0): {home} vs {away} | XG: {xg}")
                            elif 'позици' in skip_reason.lower():
                                log_lines.append(f"⏭️ Пропускаем (низкая позиция): {home} vs {away}")
                            elif 'мотиваци' in skip_reason.lower():
                                log_lines.append(f"⏭️ Пропускаем (нет мотивации): {home} vs {away}")
                    
                    if log_lines:
                        log_text = '\n'.join(log_lines)
                        try:
                            with open(log_file, 'w', encoding='utf-8') as f:
                                f.write(log_text)
                        except:
                            pass
                        return jsonify({
                            'log': log_text,
                            'source': 'generated_from_matches',
                            'timestamp': datetime.now().isoformat(),
                            'match_count': len(matches)
                        })
        except:
            pass
        
        # Тестовый лог
        test_log = """2026-09-08T04:38:19.377 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): Utrecht vs GO Ahead Eagles | XG: 3.33
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): Cowdenbeath vs Kilmarnock II | XG: 4.39
2026-09-08T04:38:19.667 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): Gala Fairydean Rovers vs Hearts U21 | XG: 4.75
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (низкая позиция): Watford vs Preston | H: #17, A: #23
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (нет мотивации): Blackburn vs Sheffield Utd"""
        
        return jsonify({
            'log': test_log,
            'source': 'test_data',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения лога: {e}")
        return jsonify({'log': '', 'source': 'error', 'error': str(e)})

@app.route('/api/test_analysis')
def test_analysis():
    test_log = """2026-09-08T04:38:19.377 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): Utrecht vs GO Ahead Eagles | XG: 3.33
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): Cowdenbeath vs Kilmarnock II | XG: 4.39
2026-09-08T04:38:19.667 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): Gala Fairydean Rovers vs Hearts U21 | XG: 4.75
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (XG вне диапазона 1.8-3.0): AEK Athens FC vs Lask Linz | XG: 3.66
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (низкая позиция): Watford vs Preston | H: #17, A: #23
2026-09-08T04:38:19.666 - betting_bot.__main__ - INFO - ⏭️ Пропускаем (нет мотивации): Blackburn vs Sheffield Utd"""
    
    stats = MatchAnalyzer.analyze_logs(test_log)
    recommendations = MatchAnalyzer.get_recommendations(stats)
    
    return jsonify({
        'success': True,
        'stats': stats,
        'recommendations': recommendations,
        'test_mode': True
    })

@app.route('/api/save_bot_log', methods=['POST'])
def save_bot_log():
    try:
        data = request.json
        log_text = data.get('log', '')
        
        if not log_text:
            return jsonify({'success': False, 'error': 'Лог пуст'}), 400
        
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'matches_log.txt')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(log_text)
        
        return jsonify({
            'success': True,
            'message': 'Лог сохранен',
            'file': log_file,
            'size': len(log_text)
        })
        
    except Exception as e:
        logger.error(f"Ошибка сохранения лога: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health')
def health():
    bot_ok, bot_data = check_bot_health()
    return jsonify({
        'status': 'ok',
        'web': 'running',
        'bot': 'ok' if bot_ok else 'error',
        'bot_data': bot_data,
        'bot_url': BOT_URL,
        'timestamp': datetime.now().isoformat()
    })

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"🌐 Запуск веб-интерфейса на порту {port}")
    logger.info(f"📡 Подключение к боту: {BOT_URL}")
    
    bot_ok, bot_data = check_bot_health()
    if bot_ok:
        logger.info("✅ Бот доступен")
    else:
        logger.warning("⚠️ Бот недоступен! Убедитесь, что бот запущен на Render")
    
    app.run(host='0.0.0.0', port=port, debug=False)
