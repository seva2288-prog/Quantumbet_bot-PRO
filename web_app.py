import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request, send_from_directory
import requests
from datetime import datetime
import json
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_URL = os.environ.get('BOT_URL', 'https://quantumbet-bot-pro.onrender.com')
print(f"🔗 Бот URL: {BOT_URL}")


def check_bot_health():
    try:
        r = requests.get(f'{BOT_URL}/health', timeout=5)
        if r.status_code == 200:
            return True, r.json()
    except Exception as e:
        logger.error(f"❌ Бот недоступен: {e}")
    return False, None


# ============================================================
# ГЛАВНАЯ
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')


# ============================================================
# PWA
# ============================================================
@app.route('/sw.js')
def serve_sw():
    try:
        return send_from_directory('.', 'sw.js', mimetype='application/javascript')
    except:
        return """
self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => e.respondWith(fetch(e.request).catch(() => caches.match(e.request))));
""", 200, {'Content-Type': 'application/javascript'}


@app.route('/manifest.json')
def serve_manifest():
    try:
        return send_from_directory('.', 'manifest.json', mimetype='application/json')
    except:
        return {
            "name": "Quantum Bet Tracker",
            "short_name": "Bet Tracker",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#050510",
            "theme_color": "#7c3aed",
            "icons": [{"src": "/static/IMG_2820.jpeg", "sizes": "192x192", "type": "image/jpeg"}]
        }, 200, {'Content-Type': 'application/json'}


# ============================================================
# X2 МАТЧИ (ГЛАВНОЕ!)
# ============================================================
@app.route('/api/x2_matches')
def api_x2_matches():
    """
    Проксирует запрос на бот. Бот читает matches_log.txt и парсит X2_MATCH строки.
    """
    try:
        logger.info(f"📡 Проксируем на {BOT_URL}/api/x2_matches")
        response = requests.get(f'{BOT_URL}/api/x2_matches', timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Получено {data.get('count', 0)} X2 матчей")
            return jsonify(data)
        else:
            logger.warning(f"⚠️ Бот вернул {response.status_code}")
            return jsonify({'success': False, 'x2_matches': [], 'count': 0}), response.status_code
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return jsonify({'success': False, 'x2_matches': [], 'count': 0, 'error': str(e)}), 500


# ============================================================
# ОСТАЛЬНЫЕ API (проксирование)
# ============================================================
@app.route('/api/all_data')
def api_all_data():
    try:
        r = requests.get(f'{BOT_URL}/api/all_data', timeout=15)
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({'error': f'Bot error {r.status_code}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/matches')
def api_matches():
    try:
        r = requests.get(f'{BOT_URL}/api/matches', timeout=10)
        return jsonify(r.json()) if r.status_code == 200 else jsonify([])
    except:
        return jsonify([])


@app.route('/api/stats')
def api_stats():
    try:
        r = requests.get(f'{BOT_URL}/api/stats', timeout=10)
        return jsonify(r.json()) if r.status_code == 200 else jsonify({'bank': 1000})
    except:
        return jsonify({'bank': 1000})


@app.route('/api/history')
def api_history():
    try:
        r = requests.get(f'{BOT_URL}/api/history', timeout=10)
        return jsonify(r.json()) if r.status_code == 200 else jsonify([])
    except:
        return jsonify([])


@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/bank', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/edit_bet', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/delete_bet', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/add_manual_match', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/simulate', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/import_excel', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/import_project', json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def health():
    ok, data = check_bot_health()
    return jsonify({
        'status': 'ok', 'web': 'running',
        'bot': 'ok' if ok else 'error',
        'bot_data': data, 'bot_url': BOT_URL,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/health')
def health_simple():
    return jsonify({'status': 'ok', 'web': 'running', 'timestamp': datetime.now().isoformat()})


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"🌐 Запуск на порту {port}")
    logger.info(f"📡 Бот: {BOT_URL}")
    ok, _ = check_bot_health()
    logger.info("✅ Бот доступен" if ok else "⚠️ Бот недоступен")
    app.run(host='0.0.0.0', port=port, debug=False)
