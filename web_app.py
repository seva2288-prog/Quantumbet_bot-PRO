import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request
import requests
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# URL бота
BOT_URL = 'https://quantumbet-bot-pro.onrender.com'

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
        .nav a { text-decoration: none; }
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
        .btn-warning { background: #ffd200; color: #000; border-color: #ffd200; }
        .btn-warning:hover { background: #f7971e; border-color: #f7971e; }
        
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
        
        .edit-row {
            background: var(--bg-card);
            padding: 10px;
            border-radius: 8px;
            display: none;
            margin-top: 5px;
        }
        .edit-row.active { display: table-row; }
        .edit-row input, .edit-row select {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-right: 3px;
        }
        .edit-row .btn { padding: 4px 12px; font-size: 12px; }
        .edit-btn { cursor: pointer; color: var(--text-secondary); }
        .edit-btn:hover { color: var(--gradient-start); }
        
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
        
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: stretch; gap: 10px; }
            .header h1 { font-size: 20px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .summary-row { grid-template-columns: 1fr; }
            .nav { justify-content: center; }
            .btn { padding: 6px 12px; font-size: 12px; }
            .card { padding: 12px; }
            table { font-size: 11px; min-width: 600px; }
            th, td { padding: 5px 6px; }
            .chart-container { height: 150px; }
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
            <a href="/"><button class="btn active">📊 Дашборд</button></a>
            <a href="/matches"><button class="btn">⚽ Матчи</button></a>
            <a href="/stats"><button class="btn">📈 Статистика</button></a>
            <a href="/arbitrage"><button class="btn">🔍 Вилки</button></a>
            <a href="/settings"><button class="btn">⚙️ Настройки</button></a>
            <button class="btn" onclick="location.reload()">🔄 Обновить</button>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">${{ stats.bank }}</div>
                <div class="label">💰 Текущий банк</div>
            </div>
            <div class="stat-card">
                <div class="value green">{{ stats.wins }}</div>
                <div class="label">✅ Выигрыши</div>
            </div>
            <div class="stat-card">
                <div class="value red">{{ stats.losses }}</div>
                <div class="label">❌ Проигрыши</div>
            </div>
            <div class="stat-card">
                <div class="value gold">${{ stats.profit }}</div>
                <div class="label">💰 Прибыль</div>
            </div>
        </div>
        
        <div class="summary-row">
            <div class="summary-item">
                <div class="label">📊 Всего ставок</div>
                <div class="value">{{ stats.total_bets }}</div>
            </div>
            <div class="summary-item">
                <div class="label">🎯 Проходимость</div>
                <div class="value">{{ stats.winrate }}%</div>
            </div>
            <div class="summary-item">
                <div class="label">📈 ROI</div>
                <div class="value">{{ stats.roi }}%</div>
            </div>
            <div class="summary-item">
                <div class="label">📅 Средняя ставка</div>
                <div class="value">${{ stats.avg_stake }}</div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h2>📈 График прибыли</h2>
                <span style="font-size:12px;color:var(--text-secondary);">За последние 7 дней</span>
            </div>
            <div class="chart-container">
                <canvas id="profitChart"></canvas>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h2>📋 Все ставки</h2>
                <span class="count">Всего: {{ history|length }}</span>
            </div>
            <div class="scrollable-table">
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Дата</th>
                                <th>Матч</th>
                                <th>Счёт</th>
                                <th>Ставка</th>
                                <th>Кэф</th>
                                <th>Сумма</th>
                                <th>EV</th>
                                <th>Результат</th>
                                <th>Прибыль</th>
                                <th>✏️</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for bet in history|reverse %}
                            <tr>
                                <td>{{ loop.index }}</td>
                                <td style="font-size:11px;white-space:nowrap;">{{ bet.date }}</td>
                                <td><strong>{{ bet.home }}</strong> vs <strong>{{ bet.away }}</strong></td>
                                <td>
                                    {% if bet.home_goals is not none and bet.away_goals is not none %}
                                        {{ bet.home_goals }} - {{ bet.away_goals }}
                                    {% else %}
                                        -
                                    {% endif %}
                                </td>
                                <td>{{ bet.bet }}</td>
                                <td>{{ bet.odds }}</td>
                                <td>${{ bet.stake }}</td>
                                <td>{{ bet.ev }}%</td>
                                <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                                <td class="{% if bet.profit > 0 %}profit-positive{% elif bet.profit < 0 %}profit-negative{% endif %}">
                                    ${{ bet.profit }}
                                </td>
                                <td>
                                    <span class="edit-btn" onclick="toggleEdit('{{ loop.index0 }}')">✏️</span>
                                </td>
                            </tr>
                            <tr id="edit-row-{{ loop.index0 }}" class="edit-row">
                                <td colspan="11">
                                    <div style="display:flex;flex-wrap:wrap;gap:5px;align-items:center;">
                                        <input type="text" id="edit_home_{{ loop.index0 }}" value="{{ bet.home }}" placeholder="Хозяева" style="width:100px;">
                                        <input type="text" id="edit_away_{{ loop.index0 }}" value="{{ bet.away }}" placeholder="Гости" style="width:100px;">
                                        <input type="text" id="edit_score_{{ loop.index0 }}" value="{% if bet.home_goals is not none and bet.away_goals is not none %}{{ bet.home_goals }}-{{ bet.away_goals }}{% endif %}" placeholder="Счёт (2-1)" style="width:70px;">
                                        <input type="text" id="edit_bet_{{ loop.index0 }}" value="{{ bet.bet }}" placeholder="Ставка" style="width:100px;">
                                        <input type="number" id="edit_odds_{{ loop.index0 }}" value="{{ bet.odds }}" placeholder="Кэф" step="0.01" style="width:70px;">
                                        <input type="number" id="edit_stake_{{ loop.index0 }}" value="{{ bet.stake }}" placeholder="Сумма" step="0.5" style="width:80px;">
                                        <input type="number" id="edit_ev_{{ loop.index0 }}" value="{{ bet.ev }}" placeholder="EV" step="0.1" style="width:70px;">
                                        <select id="edit_result_{{ loop.index0 }}" style="padding:4px 8px;border-radius:4px;border:1px solid var(--input-border);background:var(--input-bg);color:var(--text-primary);">
                                            <option value="win" {% if bet.result == 'win' %}selected{% endif %}>win</option>
                                            <option value="loss" {% if bet.result == 'loss' %}selected{% endif %}>loss</option>
                                            <option value="push" {% if bet.result == 'push' %}selected{% endif %}>push</option>
                                            <option value="pending" {% if bet.result == 'pending' %}selected{% endif %}>pending</option>
                                        </select>
                                        <button class="btn btn-success" onclick="saveEdit('{{ loop.index0 }}')">💾 Сохранить</button>
                                        <button class="btn btn-danger" onclick="deleteBet('{{ loop.index0 }}')">🗑️ Удалить</button>
                                        <button class="btn" onclick="toggleEdit('{{ loop.index0 }}')">❌ Отмена</button>
                                    </div>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="11" class="no-data">
                                    <div class="emoji">📭</div>
                                    <div>Нет данных</div>
                                    <div style="font-size:13px;color:#444466;">Начните делать ставки!</div>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
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
        
        function toggleEdit(index) {
            const row = document.getElementById('edit-row-' + index);
            row.classList.toggle('active');
        }
        
        function saveEdit(index) {
            const score = document.getElementById('edit_score_' + index).value;
            let home_goals = null;
            let away_goals = null;
            
            if (score && score.includes('-')) {
                const parts = score.split('-');
                home_goals = parseInt(parts[0]);
                away_goals = parseInt(parts[1]);
            }
            
            const data = {
                home: document.getElementById('edit_home_' + index).value,
                away: document.getElementById('edit_away_' + index).value,
                home_goals: home_goals,
                away_goals: away_goals,
                score: score,
                bet: document.getElementById('edit_bet_' + index).value,
                odds: parseFloat(document.getElementById('edit_odds_' + index).value) || 0,
                stake: parseFloat(document.getElementById('edit_stake_' + index).value) || 0,
                ev: parseFloat(document.getElementById('edit_ev_' + index).value) || 0,
                result: document.getElementById('edit_result_' + index).value,
                index: index
            };
            
            fetch('/api/edit_bet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('✅ Ставка обновлена!');
                    location.reload();
                } else {
                    alert('❌ Ошибка: ' + data.error);
                }
            });
        }
        
        function deleteBet(index) {
            if (!confirm('Удалить эту ставку?')) return;
            
            fetch('/api/delete_bet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ index: index })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('✅ Ставка удалена!');
                    location.reload();
                } else {
                    alert('❌ Ошибка: ' + data.error);
                }
            });
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            fetch('/api/profit_data')
                .then(response => response.json())
                .then(data => {
                    const ctx = document.getElementById('profitChart').getContext('2d');
                    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.dates || ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
                            datasets: [{
                                label: 'Прибыль ($)',
                                data: data.profits || [0, 0, 0, 0, 0, 0, 0],
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
                            plugins: {
                                legend: {
                                    labels: {
                                        color: isDark ? '#e0e0e0' : '#1a1a2e',
                                        font: { size: 10 }
                                    }
                                }
                            },
                            scales: {
                                x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 10 } } },
                                y: {
                                    ticks: { 
                                        color: isDark ? '#8888aa' : '#666688',
                                        callback: function(value) { return '$' + value; },
                                        font: { size: 10 }
                                    }
                                }
                            }
                        }
                    });
                })
                .catch(() => {
                    document.getElementById('profitChart').parentElement.innerHTML = 
                        '<div class="no-data"><div class="emoji">📊</div>Нет данных для графика</div>';
                });
        });
    </script>
</body>
</html>
"""

# ============================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С API
# ============================================================

def get_data_from_bot():
    """Получение данных из бота через API"""
    try:
        stats_response = requests.get(f'{BOT_URL}/api/stats', timeout=10)
        stats_data = stats_response.json() if stats_response.status_code == 200 else {}
        
        history_response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = history_response.json() if history_response.status_code == 200 else []
        
        return stats_data, history
    except Exception as e:
        print(f"Ошибка получения данных: {e}")
        return {'bank': 1000, 'total_bets': 0, 'wins': 0, 'losses': 0, 'profit': 0, 'winrate': 0, 'roi': 0, 'avg_stake': 0}, []

# ============================================================
# МАРШРУТЫ
# ============================================================

@app.route('/')
def dashboard():
    stats_data, history = get_data_from_bot()
    
    bank = stats_data.get('bank', 1000)
    total_bets = stats_data.get('total_bets', 0)
    wins = stats_data.get('wins', 0)
    losses = stats_data.get('losses', 0)
    total_profit = stats_data.get('profit', 0)
    winrate = stats_data.get('winrate', 0)
    roi = stats_data.get('roi', 0)
    avg_stake = stats_data.get('avg_stake', 0)
    
    stats = {
        'bank': bank,
        'total_bets': total_bets,
        'wins': wins,
        'losses': losses,
        'profit': round(total_profit, 2),
        'winrate': winrate,
        'roi': roi,
        'avg_stake': avg_stake
    }
    
    return render_template_string(DASHBOARD_HTML, stats=stats, history=history)

@app.route('/api/profit_data')
def profit_data():
    try:
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = response.json() if response.status_code == 200 else []
    except:
        history = []
    
    profits = []
    days = 7
    
    for i in range(days - 1, -1, -1):
        day_profit = 0
        day = datetime.now() - timedelta(days=i)
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bet_date.date() == day.date():
                    if bet.get('result') == 'win':
                        day_profit += bet.get('stake', 0) * (bet.get('odds', 1) - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= bet.get('stake', 0)
            except:
                pass
        profits.append(round(day_profit, 2))
    
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    
    return jsonify({'dates': dates, 'profits': profits})

@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    """Редактирование ставки"""
    try:
        data = request.json
        index = data.get('index')
        
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = response.json() if response.status_code == 200 else []
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        history[index]['home'] = data.get('home', history[index]['home'])
        history[index]['away'] = data.get('away', history[index]['away'])
        history[index]['home_goals'] = data.get('home_goals')
        history[index]['away_goals'] = data.get('away_goals')
        history[index]['bet'] = data.get('bet', history[index]['bet'])
        history[index]['odds'] = data.get('odds', history[index]['odds'])
        history[index]['stake'] = data.get('stake', history[index]['stake'])
        history[index]['ev'] = data.get('ev', history[index]['ev'])
        history[index]['result'] = data.get('result', history[index]['result'])
        
        if history[index]['result'] == 'win':
            history[index]['profit'] = round(history[index]['stake'] * (history[index]['odds'] - 1), 2)
        elif history[index]['result'] == 'loss':
            history[index]['profit'] = -history[index]['stake']
        else:
            history[index]['profit'] = 0
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    """Удаление ставки"""
    try:
        data = request.json
        index = data.get('index')
        
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = response.json() if response.status_code == 200 else []
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        deleted = history.pop(index)
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'deleted': deleted})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/matches')
def matches_page():
    try:
        response = requests.get(f'{BOT_URL}/matches', timeout=10)
        matches = response.json() if response.status_code == 200 else []
        return render_template_string(MATCHES_HTML, matches=matches)
    except:
        return render_template_string(MATCHES_HTML, matches=[])

@app.route('/stats')
def stats_page():
    stats_data, history = get_data_from_bot()
    return render_template_string(STATS_HTML, stats=stats_data, history=history)

@app.route('/arbitrage')
def arbitrage_page():
    try:
        response = requests.get(f'{BOT_URL}/api/arbitrage', timeout=10)
        arbs = response.json() if response.status_code == 200 else []
        return render_template_string(ARBITRAGE_HTML, arbs=arbs)
    except:
        return render_template_string(ARBITRAGE_HTML, arbs=[])

@app.route('/settings')
def settings_page():
    stats_data, _ = get_data_from_bot()
    bank = stats_data.get('bank', 1000)
    return render_template_string(SETTINGS_HTML, bank=bank)

@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        if 'bank' in data:
            response = requests.post(f'{BOT_URL}/api/bank', json={'bank': data['bank']}, timeout=10)
            return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'No bank value'}), 400

@app.route('/api/stats')
def api_stats():
    stats_data, _ = get_data_from_bot()
    return jsonify(stats_data)

@app.route('/api/history')
def api_history():
    _, history = get_data_from_bot()
    return jsonify(history)

@app.route('/export')
def export_data():
    try:
        response = requests.get(f'{BOT_URL}/export', timeout=30)
        if response.status_code == 200:
            return response.content, 200, {'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
    except:
        pass
    return "Нет данных для экспорта", 404

# ============================================================
# ДОПОЛНИТЕЛЬНЫЕ ШАБЛОНЫ
# ============================================================

MATCHES_HTML = """
<!DOCTYPE html>
<html>
<head><title>Матчи</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 24px; margin-bottom: 5px; }
.subtitle { color: #8888aa; margin-bottom: 15px; font-size: 14px; }
.nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 15px; }
.nav a { text-decoration: none; }
.btn { padding: 8px 16px; border-radius: 10px; border: 1px solid #2a2a4a; background: transparent; color: #8888aa; cursor: pointer; font-size: 13px; transition: all 0.3s; }
.btn:hover { background: rgba(102,126,234,0.2); border-color: #667eea; color: #fff; }
.btn.active { background: #667eea; border-color: #667eea; color: #fff; }
.match-card { background: #1a1a2e; padding: 15px; border-radius: 12px; border: 1px solid #2a2a4a; margin-bottom: 12px; overflow: hidden; }
.match-title { font-size: 16px; font-weight: bold; color: #e0e0e0; }
.match-league { color: #8888aa; font-size: 13px; }
.match-xg { color: #667eea; font-size: 13px; }
.match-bets { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }
.bet-item { background: #0f0f1a; padding: 4px 10px; border-radius: 6px; font-size: 12px; border: 1px solid #2a2a4a; }
.no-matches { text-align: center; color: #8888aa; padding: 30px 0; }
</style>
</head>
<body>
<div class="container">
    <h1>⚽ Матчи на сегодня</h1>
    <div class="subtitle">Прогнозы и валуйные ставки</div>
    <div class="nav">
        <a href="/"><button class="btn">📊 Дашборд</button></a>
        <a href="/matches"><button class="btn active">⚽ Матчи</button></a>
        <a href="/stats"><button class="btn">📈 Статистика</button></a>
        <a href="/arbitrage"><button class="btn">🔍 Вилки</button></a>
        <a href="/settings"><button class="btn">⚙️ Настройки</button></a>
        <button class="btn" onclick="location.reload()">🔄 Обновить</button>
    </div>
    {% if matches %}
        {% for match in matches %}
        <div class="match-card">
            <div class="match-title">{{ match.home }} vs {{ match.away }}</div>
            <div class="match-league">🏆 {{ match.league }} | ⏰ {{ match.match_time }}</div>
            <div class="match-xg">📊 xG: {{ match.home_xg }} : {{ match.away_xg }}</div>
            <div class="match-bets">
                {% for bet in match.bets[:3] %}
                <span class="bet-item">{{ bet.label }} | КЭФ: {{ bet.odds }} | EV: {{ bet.ev }}%</span>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    {% else %}
        <div class="no-matches">📭 Матчей не найдено</div>
    {% endif %}
</div>
</body>
</html>
"""

STATS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Статистика</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 24px; margin-bottom: 5px; }
.subtitle { color: #8888aa; margin-bottom: 15px; font-size: 14px; }
.nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 15px; }
.nav a { text-decoration: none; }
.btn { padding: 8px 16px; border-radius: 10px; border: 1px solid #2a2a4a; background: transparent; color: #8888aa; cursor: pointer; font-size: 13px; }
.btn:hover { background: rgba(102,126,234,0.2); border-color: #667eea; color: #fff; }
.btn.active { background: #667eea; border-color: #667eea; color: #fff; }
.card { background: #1a1a2e; padding: 15px; border-radius: 12px; border: 1px solid #2a2a4a; margin-bottom: 12px; overflow: hidden; }
.card h2 { color: #8888aa; font-size: 14px; font-weight: normal; margin-bottom: 10px; }
.stat-row { display: flex; gap: 15px; flex-wrap: wrap; }
.stat-item { flex: 1; min-width: 100px; }
.stat-item .value { font-size: 22px; font-weight: bold; color: #667eea; }
.stat-item .label { color: #8888aa; font-size: 12px; }
.table-wrapper { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 500px; }
th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #2a2a4a; white-space: nowrap; }
th { color: #8888aa; font-weight: normal; font-size: 11px; text-transform: uppercase; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; }
.badge.win { background: rgba(56,239,125,0.15); color: #38ef7d; border: 1px solid rgba(56,239,125,0.2); }
.badge.loss { background: rgba(239,71,58,0.15); color: #ef473a; border: 1px solid rgba(239,71,58,0.2); }
.badge.push { background: rgba(255,210,0,0.15); color: #ffd200; border: 1px solid rgba(255,210,0,0.2); }
.no-data { text-align: center; color: #8888aa; padding: 20px 0; }
</style>
</head>
<body>
<div class="container">
    <h1>📈 Статистика</h1>
    <div class="subtitle">Детальный анализ ваших ставок</div>
    <div class="nav">
        <a href="/"><button class="btn">📊 Дашборд</button></a>
        <a href="/matches"><button class="btn">⚽ Матчи</button></a>
        <a href="/stats"><button class="btn active">📈 Статистика</button></a>
        <a href="/arbitrage"><button class="btn">🔍 Вилки</button></a>
        <a href="/settings"><button class="btn">⚙️ Настройки</button></a>
        <button class="btn" onclick="location.reload()">🔄 Обновить</button>
    </div>
    <div class="card">
        <h2>📊 Общая статистика</h2>
        <div class="stat-row">
            <div class="stat-item">
                <div class="value">{{ stats.total_bets or 0 }}</div>
                <div class="label">Всего ставок</div>
            </div>
            <div class="stat-item">
                <div class="value" style="color:#38ef7d;">{{ stats.wins or 0 }}</div>
                <div class="label">Выигрыши</div>
            </div>
            <div class="stat-item">
                <div class="value" style="color:#ef473a;">{{ stats.losses or 0 }}</div>
                <div class="label">Проигрыши</div>
            </div>
            <div class="stat-item">
                <div class="value" style="color:#ffd200;">{{ stats.profit or 0 }}$</div>
                <div class="label">Прибыль</div>
            </div>
        </div>
    </div>
    <div class="card">
        <h2>📋 Все ставки</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr>
                </thead>
                <tbody>
                    {% for bet in history %}
                    <tr>
                        <td>{{ bet.date }}</td>
                        <td>{{ bet.home }} vs {{ bet.away }}</td>
                        <td>
                            {% if bet.home_goals is not none and bet.away_goals is not none %}
                                {{ bet.home_goals }} - {{ bet.away_goals }}
                            {% else %}
                                -
                            {% endif %}
                        </td>
                        <td>{{ bet.bet }}</td>
                        <td>{{ bet.odds }}</td>
                        <td>{{ bet.ev }}%</td>
                        <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                        <td>${{ bet.profit }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="8" class="no-data">Нет данных</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
</body>
</html>
"""

ARBITRAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Вилки</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 24px; margin-bottom: 5px; }
.subtitle { color: #8888aa; margin-bottom: 15px; font-size: 14px; }
.nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 15px; }
.nav a { text-decoration: none; }
.btn { padding: 8px 16px; border-radius: 10px; border: 1px solid #2a2a4a; background: transparent; color: #8888aa; cursor: pointer; font-size: 13px; }
.btn:hover { background: rgba(102,126,234,0.2); border-color: #667eea; color: #fff; }
.btn.active { background: #667eea; border-color: #667eea; color: #fff; }
.arb-card { background: #1a1a2e; padding: 15px; border-radius: 12px; border: 1px solid #2a2a4a; margin-bottom: 12px; overflow: hidden; }
.arb-card h3 { font-size: 16px; margin-bottom: 5px; }
.arb-card .profit { color: #38ef7d; font-size: 18px; font-weight: bold; }
.no-data { text-align: center; color: #8888aa; padding: 30px 0; }
</style>
</head>
<body>
<div class="container">
    <h1>🔍 Букмекерские вилки</h1>
    <div class="subtitle">Гарантированная прибыль</div>
    <div class="nav">
        <a href="/"><button class="btn">📊 Дашборд</button></a>
        <a href="/matches"><button class="btn">⚽ Матчи</button></a>
        <a href="/stats"><button class="btn">📈 Статистика</button></a>
        <a href="/arbitrage"><button class="btn active">🔍 Вилки</button></a>
        <a href="/settings"><button class="btn">⚙️ Настройки</button></a>
        <button class="btn" onclick="location.reload()">🔄 Обновить</button>
    </div>
    {% if arbs %}
        {% for arb in arbs %}
        <div class="arb-card">
            <h3>⚽ {{ arb.home }} vs {{ arb.away }}</h3>
            <div style="color:#8888aa;font-size:13px;">🏆 {{ arb.league }}</div>
            {% for opp in arb.arbitrage[:3] %}
            <div style="margin:8px 0;padding:10px;background:#0f0f1a;border-radius:8px;">
                <div style="color:#ffd200;font-weight:bold;">{{ opp.markets|join(' vs ') }}</div>
                <div>Кэфы: {{ opp.odds|join(' : ') }}</div>
                <div>Ставки: ${{ opp.stake_home }} : ${{ opp.stake_away }}</div>
                <div class="profit">💰 Прибыль: {{ opp.profit }}%</div>
            </div>
            {% endfor %}
        </div>
        {% endfor %}
    {% else %}
        <div class="no-data">🔍 Вилок не найдено</div>
    {% endif %}
</div>
</body>
</html>
"""

SETTINGS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Настройки</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 24px; margin-bottom: 5px; }
.subtitle { color: #8888aa; margin-bottom: 15px; font-size: 14px; }
.nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 15px; }
.nav a { text-decoration: none; }
.btn { padding: 8px 16px; border-radius: 10px; border: 1px solid #2a2a4a; background: transparent; color: #8888aa; cursor: pointer; font-size: 13px; }
.btn:hover { background: rgba(102,126,234,0.2); border-color: #667eea; color: #fff; }
.btn.active { background: #667eea; border-color: #667eea; color: #fff; }
.setting-group { background: #1a1a2e; padding: 15px; border-radius: 12px; border: 1px solid #2a2a4a; margin-bottom: 12px; }
.setting-group h2 { color: #8888aa; font-size: 14px; font-weight: normal; margin-bottom: 10px; }
.setting-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #0f0f1a; flex-wrap: wrap; gap: 8px; }
.setting-item:last-child { border-bottom: none; }
.setting-item .label { color: #e0e0e0; }
.setting-item .desc { color: #666688; font-size: 12px; }
.input-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.input-group input { background: #0f0f1a; border: 1px solid #2a2a4a; color: #e0e0e0; padding: 6px 10px; border-radius: 6px; width: 120px; }
.input-group button { background: #667eea; color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; }
.input-group button:hover { background: #764ba2; }
.toggle { width: 44px; height: 24px; background: #2a2a4a; border-radius: 12px; cursor: pointer; position: relative; transition: 0.3s; }
.toggle.active { background: #667eea; }
.toggle .dot { width: 18px; height: 18px; background: white; border-radius: 50%; position: absolute; top: 3px; left: 3px; transition: 0.3s; }
.toggle.active .dot { left: 23px; }
</style>
</head>
<body>
<div class="container">
    <h1>⚙️ Настройки</h1>
    <div class="subtitle">Управление ботом</div>
    <div class="nav">
        <a href="/"><button class="btn">📊 Дашборд</button></a>
        <a href="/matches"><button class="btn">⚽ Матчи</button></a>
        <a href="/stats"><button class="btn">📈 Статистика</button></a>
        <a href="/arbitrage"><button class="btn">🔍 Вилки</button></a>
        <a href="/settings"><button class="btn active">⚙️ Настройки</button></a>
    </div>
    <div class="setting-group">
        <h2>💰 Банк</h2>
        <div class="setting-item">
            <div>
                <div class="label">Текущий банк</div>
                <div class="desc">Ваш игровой банк</div>
            </div>
            <div class="input-group">
                <input type="number" id="bankInput" value="{{ bank }}" step="10">
                <button onclick="updateBank()">Сохранить</button>
            </div>
        </div>
    </div>
    <div class="setting-group">
        <h2>🤖 Автоматизация</h2>
        <div class="setting-item">
            <div>
                <div class="label">Авто-ставки</div>
                <div class="desc">Автоматическое размещение ставок</div>
            </div>
            <div class="toggle active" onclick="this.classList.toggle('active')">
                <div class="dot"></div>
            </div>
        </div>
    </div>
    <div class="setting-group">
        <h2>📊 Экспорт</h2>
        <div class="setting-item">
            <div>
                <div class="label">Экспорт данных</div>
                <div class="desc">Скачать историю в Excel</div>
            </div>
            <button class="btn" onclick="window.location.href='/export'">📥 Скачать</button>
        </div>
    </div>
</div>
<script>
function updateBank() {
    const value = document.getElementById('bankInput').value;
    fetch('/api/bank', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bank: parseFloat(value) })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('✅ Банк обновлен: $' + data.bank);
            location.reload();
        }
    });
}
</script>
</body>
</html>
"""

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
