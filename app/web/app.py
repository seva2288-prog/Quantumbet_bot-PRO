from flask import Flask, render_template, jsonify, request
import requests
import os
import sys
import json

# Добавляем путь к корневой папке
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)

# URL вашего бота
BOT_URL = "https://quantumbet-bot-pro.onrender.com"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/all_data')
def all_data():
    try:
        r = requests.get(f'{BOT_URL}/api/all_data', timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def stats():
    try:
        r = requests.get(f'{BOT_URL}/api/stats', timeout=5)
        return jsonify(r.json())
    except:
        return jsonify({'bank': 1000, 'wins': 0, 'losses': 0, 'profit': 0})

@app.route('/api/history')
def history():
    try:
        r = requests.get(f'{BOT_URL}/api/history', timeout=5)
        return jsonify(r.json())
    except:
        return jsonify([])

@app.route('/api/matches')
def matches():
    try:
        r = requests.get(f'{BOT_URL}/api/matches', timeout=5)
        return jsonify(r.json())
    except:
        return jsonify([])

@app.route('/api/bank', methods=['POST'])
def bank():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/bank', json=data, timeout=5)
        return jsonify(r.json())
    except:
        return jsonify({'error': 'Ошибка'})

@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        r = requests.post(f'{BOT_URL}/api/simulate', json=data, timeout=10)
        return jsonify(r.json())
    except:
        return jsonify({'error': 'Ошибка'})

@app.route('/api/update_matches')
def update_matches():
    try:
        r = requests.get(f'{BOT_URL}/api/update_matches', timeout=10)
        return jsonify(r.json())
    except:
        return jsonify({'success': False, 'error': 'Ошибка'})

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'bot': BOT_URL})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
