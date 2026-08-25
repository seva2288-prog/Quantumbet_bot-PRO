import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request
from app.database.storage import storage
from app.api.football import football_api
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================================
# HTML ШАБЛОН С ПОЛНОЙ СТАТИСТИКОЙ
# ============================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
    <title>Quantum Bet Bot - Полная статистика</title>
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
            --gradient-start: #667eea;
            --gradient-end: #764ba2;
        }
        [data-theme="light"] {
            --bg-primary: #f0f2f5;
            --bg-secondary: #ffffff;
            --text-primary: #1a1a2e;
            --text-secondary: #666688;
            --border-color: rgba(0,0,0,0.08);
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
        }
        .btn.active {
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            border-color: var(--gradient-start);
            color: #fff;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
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
        }
        .stat-card:hover { transform: translateY(-3px); border-color: var(--gradient-start); }
        .stat-card .value {
            font-size: 28px;
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
            min-width: 700px;
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
        
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: stretch; gap: 10px; }
            .header h1 { font-size: 20px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .summary-row { grid-template-columns: 1fr; }
            .nav { justify-content: center; }
            .btn { padding: 6px 12px; font-size: 12px; }
            .card { padding: 12px; }
            table { font-size: 11px; min-width: 500px; }
            th, td { padding: 5px 6px; }
            .chart-container { height: 150px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
            .stat-card { padding: 10px; }
            .stat-card .value { font-size: 20px; }
        }
        
        .scrollable-table {
            max-height: 500px;
            overflow-y: auto;
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
        
        <!-- ===== ОБЩАЯ СТАТИСТИКА ===== -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">${{ bank }}</div>
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
                <div class="value gold">${{ stats.total_profit }}</div>
                <div class="label">💰 Прибыль</div>
            </div>
        </div>
        
        <!-- ===== ПОДРОБНАЯ СТАТИСТИКА ===== -->
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
        
        <!-- ===== ГРАФИК ПРИБЫЛИ ===== -->
        <div class="card">
            <div class="card-header">
                <h2>📈 График прибыли</h2>
                <span style="font-size:12px;color:var(--text-secondary);">За последние 7 дней</span>
            </div>
            <div class="chart-container">
                <canvas id="profitChart"></canvas>
            </div>
        </div>
        
        <!-- ===== ТАБЛИЦА ВСЕХ СТАВОК ===== -->
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
                                <th>Ставка</th>
                                <th>Кэф</th>
                                <th>Сумма</th>
                                <th>EV</th>
                                <th>Результат</th>
                                <th>Прибыль</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for bet in history|reverse %}
                            <tr>
                                <td>{{ loop.index }}</td>
                                <td style="font-size:11px;white-space:nowrap;">{{ bet.date }}</td>
                                <td><strong>{{ bet.home }}</strong> vs <strong>{{ bet.away }}</strong></td>
                                <td>{{ bet.bet }}</td>
                                <td>{{ bet.odds }}</td>
                                <td>${{ bet.stake }}</td>
                                <td>{{ bet.ev }}%</td>
                                <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                                <td class="{% if bet.profit > 0 %}profit-positive{% elif bet.profit < 0 %}profit-negative{% endif %}">
                                    ${{ bet.profit }}
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="9" class="no-data">
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
# МАРШРУТЫ
# ============================================================

@app.route('/')
def dashboard():
    stats = storage.load_stats()
    bank = storage.load_bank()
    history = storage.load_history()
    
    total_bets = len(history)
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    pushes = stats.get('pushes', 0)
    total_profit = stats.get('total_profit', 0)
    
    winrate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
    
    # Расчёт ROI
    total_stake = sum(bet.get('stake', 0) for bet in history)
    roi = round((total_profit / total_stake) * 100, 1) if total_stake > 0 else 0
    
    avg_stake = round(total_stake / total_bets, 2) if total_bets > 0 else 0
    
    for bet in history:
        if bet.get('result') == 'win':
            profit = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
            bet['profit'] = profit
        elif bet.get('result') == 'loss':
            profit = -round(bet.get('stake', 0), 2)
            bet['profit'] = profit
        else:
            bet['profit'] = 0
    
    stats_data = {
        'total_bets': total_bets,
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'total_profit': round(total_profit, 2),
        'winrate': winrate,
        'roi': roi,
        'avg_stake': avg_stake
    }
    
    return render_template_string(DASHBOARD_HTML, 
                                   stats=stats_data, 
                                   bank=bank, 
                                   history=history)

@app.route('/api/profit_data')
def profit_data():
    history = storage.load_history()
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

@app.route('/matches')
def matches_page():
    try:
        from app.bot import get_matches_with_factors, find_top_matches
        matches = get_matches_with_factors()
        top_matches = find_top_matches(matches) if matches else []
        return render_template_string(MATCHES_HTML, matches=top_matches)
    except Exception as e:
        return render_template_string(MATCHES_HTML, matches=[])

@app.route('/stats')
def stats_page():
    stats = storage.load_stats()
    history = storage.load_history()
    
    for bet in history:
        if bet.get('result') == 'win':
            profit = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
            bet['profit'] = f"${profit}"
        elif bet.get('result') == 'loss':
            profit = -round(bet.get('stake', 0), 2)
            bet['profit'] = f"${profit}"
        else:
            bet['profit'] = "$0.00"
    
    return render_template_string(STATS_HTML, stats=stats, history=history)

@app.route('/arbitrage')
def arbitrage_page():
    try:
        from app.bot import get_matches_with_factors
        from app.api.football import football_api
        from app.analytics.arbitrage import arbitrage_analyzer
        
        matches = get_matches_with_factors()
        arbs = []
        if matches:
            for match in matches:
                odds = football_api.get_match_odds(match['fixture']['id'])
                if odds:
                    arb_opps = arbitrage_analyzer.find_arbitrage(odds)
                    if arb_opps:
                        arbs.append({
                            'home': match['teams']['home']['name'],
                            'away': match['teams']['away']['name'],
                            'league': match['league']['name'],
                            'arbitrage': arb_opps
                        })
        return render_template_string(ARBITRAGE_HTML, arbs=arbs)
    except Exception as e:
        return render_template_string(ARBITRAGE_HTML, arbs=[])

@app.route('/settings')
def settings_page():
    bank = storage.load_bank()
    return render_template_string(SETTINGS_HTML, bank=bank)

@app.route('/api/bank', methods=['POST'])
def update_bank():
    data = request.json
    if 'bank' in data:
        storage.save_bank(data['bank'])
        return jsonify({'success': True, 'bank': data['bank']})
    return jsonify({'error': 'No bank value'}), 400

@app.route('/api/stats')
def api_stats():
    stats = storage.load_stats()
    bank = storage.load_bank()
    return jsonify({
        'bank': bank,
        'total_bets': stats.get('total', 0),
        'wins': stats.get('wins', 0),
        'losses': stats.get('losses', 0),
        'profit': stats.get('total_profit', 0),
    })

@app.route('/export')
def export_data():
    from app.bot import export_to_excel
    file, message = export_to_excel()
    if file:
        return file
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
@media (max-width: 600px) { .match-title { font-size: 14px; } .match-card { padding: 12px; } }
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
@media (max-width: 600px) { .stat-item .value { font-size: 18px; } table { font-size: 12px; min-width: 400px; } }
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
                <div class="value" style="color:#ffd200;">{{ stats.total_profit or 0 }}$</div>
                <div class="label">Прибыль</div>
            </div>
        </div>
    </div>
    <div class="card">
        <h2>📋 Все ставки</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr><th>Дата</th><th>Матч</th><th>Ставка</th><th>Кэф</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr>
                </thead>
                <tbody>
                    {% for bet in history %}
                    <tr>
                        <td>{{ bet.date }}</td>
                        <td>{{ bet.home }} vs {{ bet.away }}</td>
                        <td>{{ bet.bet }}</td>
                        <td>{{ bet.odds }}</td>
                        <td>{{ bet.ev }}%</td>
                        <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                        <td>${{ bet.profit }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="7" class="no-data">Нет данных</td></tr>
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
@media (max-width: 600px) { .setting-item { flex-direction: column; align-items: stretch; } }
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
