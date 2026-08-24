import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request, send_file
from app.database.storage import storage
from app.bot import get_matches_with_factors, find_top_matches
from app.api.football import football_api
from app.analytics.arbitrage import arbitrage_analyzer
from app.analytics.anomalies import anomaly_detector
from app.ml.predictor import ml_predictor
import io
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================================
# HTML ШАБЛОН С ВСЕМИ УЛУЧШЕНИЯМИ
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
        /* ===== ОСНОВНЫЕ ПЕРЕМЕННЫЕ ===== */
        :root {
            --bg-primary: #0f0f1a;
            --bg-secondary: #1a1a2e;
            --bg-card: rgba(255,255,255,0.03);
            --text-primary: #e0e0e0;
            --text-secondary: #8888aa;
            --border-color: rgba(255,255,255,0.08);
            --shadow-color: rgba(102,126,234,0.3);
            --gradient-start: #667eea;
            --gradient-end: #764ba2;
        }
        
        [data-theme="light"] {
            --bg-primary: #f0f2f5;
            --bg-secondary: #ffffff;
            --bg-card: rgba(0,0,0,0.02);
            --text-primary: #1a1a2e;
            --text-secondary: #666688;
            --border-color: rgba(0,0,0,0.08);
            --shadow-color: rgba(0,0,0,0.1);
        }
        
        /* ===== ОБЩИЕ СТИЛИ ===== */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            transition: all 0.3s ease;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        /* ===== ШАПКА ===== */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 25px;
            padding: 20px 24px;
            background: var(--bg-secondary);
            border-radius: 16px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
        }
        .header h1 {
            font-size: 28px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header-controls {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        /* ===== КНОПКА ТЕМЫ ===== */
        .theme-toggle {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .theme-toggle:hover {
            transform: scale(1.1);
            border-color: var(--gradient-start);
        }
        
        /* ===== СТАТУС ===== */
        .status {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #38ef7d;
            font-size: 13px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            background: #38ef7d;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.8); }
            100% { opacity: 1; transform: scale(1); }
        }
        
        /* ===== НАВИГАЦИЯ ===== */
        .nav {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 25px;
        }
        .nav a { text-decoration: none; }
        .btn {
            padding: 10px 20px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
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
            box-shadow: 0 8px 25px var(--shadow-color);
        }
        
        /* ===== СТАТИСТИКА ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .stat-card {
            padding: 20px;
            border-radius: 16px;
            border: 1px solid var(--border-color);
            background: var(--bg-secondary);
            transition: all 0.3s;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        }
        .stat-card:hover { transform: translateY(-4px); border-color: var(--gradient-start); }
        .stat-card .icon { font-size: 24px; margin-bottom: 6px; }
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
        
        /* ===== КАРТОЧКИ ===== */
        .card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 15px;
        }
        .card-header h2 { color: var(--text-secondary); font-size: 16px; font-weight: normal; }
        
        /* ===== ГРАФИК ===== */
        .chart-container {
            position: relative;
            height: 250px;
            margin: 10px 0;
        }
        .chart-container canvas { width: 100% !important; height: 100% !important; }
        
        /* ===== ТАБЛИЦЫ ===== */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        th, td {
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th { color: var(--text-secondary); font-weight: normal; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
        tr:hover td { background: var(--bg-card); }
        
        .badge {
            display: inline-block;
            padding: 3px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
        }
        .badge.win { background: rgba(56,239,125,0.15); color: #38ef7d; border: 1px solid rgba(56,239,125,0.2); }
        .badge.loss { background: rgba(239,71,58,0.15); color: #ef473a; border: 1px solid rgba(239,71,58,0.2); }
        .badge.pending { background: rgba(255,210,0,0.15); color: #ffd200; border: 1px solid rgba(255,210,0,0.2); }
        
        .profit-positive { color: #38ef7d; }
        .profit-negative { color: #ef473a; }
        
        /* ===== ТОП ЛИГ ===== */
        .league-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
        }
        .league-item:last-child { border-bottom: none; }
        .league-name { display: flex; align-items: center; gap: 8px; }
        .league-bar {
            height: 6px;
            border-radius: 3px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            transition: width 1s ease;
        }
        
        /* ===== НЕТ ДАННЫХ ===== */
        .no-data { text-align: center; color: var(--text-secondary); padding: 30px 0; }
        .no-data .emoji { font-size: 48px; margin-bottom: 10px; }
        
        /* ===== ФУТЕР ===== */
        .footer { text-align: center; color: #444466; font-size: 12px; margin-top: 30px; padding: 20px 0; border-top: 1px solid var(--border-color); }
        
        /* ===== АДАПТИВНОСТЬ ===== */
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: stretch; gap: 15px; }
            .header h1 { font-size: 22px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .stat-card .value { font-size: 22px; }
            .nav { justify-content: center; }
            .btn { padding: 8px 14px; font-size: 12px; }
            .card { padding: 16px; }
            table { font-size: 12px; }
            th, td { padding: 6px 8px; }
            .chart-container { height: 180px; }
        }
        
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
            .stat-card { padding: 14px; }
            .stat-card .value { font-size: 18px; }
            .header h1 { font-size: 18px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- ШАПКА -->
        <div class="header">
            <h1>🤖 Quantum Bet Bot</h1>
            <div class="header-controls">
                <div class="status">
                    <span class="status-dot"></span>
                    <span>Система активна</span>
                    <span style="color:var(--text-secondary);">|</span>
                    <span style="color:var(--text-secondary);">v12 PRO</span>
                </div>
                <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn" title="Сменить тему">🌙</button>
            </div>
        </div>
        
        <!-- НАВИГАЦИЯ -->
        <div class="nav">
            <a href="/"><button class="btn active">📊 Дашборд</button></a>
            <a href="/matches"><button class="btn">⚽ Матчи</button></a>
            <a href="/stats"><button class="btn">📈 Статистика</button></a>
            <a href="/arbitrage"><button class="btn">🔍 Вилки</button></a>
            <a href="/settings"><button class="btn">⚙️ Настройки</button></a>
            <button class="btn" onclick="location.reload()">🔄 Обновить</button>
            <button class="btn" onclick="exportPDF()">📄 PDF</button>
        </div>
        
        <!-- СТАТИСТИКА -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="icon">💰</div>
                <div class="value">${{ bank }}</div>
                <div class="label">Текущий банк</div>
            </div>
            <div class="stat-card">
                <div class="icon">✅</div>
                <div class="value green">{{ stats.wins }}</div>
                <div class="label">Выигрыши</div>
            </div>
            <div class="stat-card">
                <div class="icon">❌</div>
                <div class="value red">{{ stats.losses }}</div>
                <div class="label">Проигрыши</div>
            </div>
            <div class="stat-card">
                <div class="icon">📈</div>
                <div class="value gold">${{ stats.total_profit }}</div>
                <div class="label">Прибыль</div>
            </div>
        </div>
        
        <!-- ГРАФИК ПРИБЫЛИ -->
        <div class="card">
            <div class="card-header">
                <h2>📈 График прибыли</h2>
                <span style="font-size:13px;color:var(--text-secondary);">За последние 7 дней</span>
            </div>
            <div class="chart-container">
                <canvas id="profitChart"></canvas>
            </div>
        </div>
        
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
            <!-- ТОП ЛИГ -->
            <div class="card">
                <div class="card-header">
                    <h2>🏆 Топ лиг</h2>
                </div>
                <div id="leagueList">
                    {% if top_leagues %}
                        {% for league in top_leagues %}
                        <div class="league-item">
                            <div class="league-name">
                                <span>{{ loop.index }}.</span>
                                <span>{{ league.name }}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:10px;flex:1;max-width:200px;">
                                <div class="league-bar" style="width:{{ league.winrate }}%;"></div>
                                <span style="font-size:13px;color:var(--text-secondary);">{{ league.winrate }}%</span>
                            </div>
                            <span style="color:#38ef7d;">+${{ league.profit }}</span>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="no-data"><div class="emoji">🏆</div>Нет данных</div>
                    {% endif %}
                </div>
            </div>
            
            <!-- ПОСЛЕДНИЕ СТАВКИ -->
            <div class="card">
                <div class="card-header">
                    <h2>📋 Последние ставки</h2>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Матч</th>
                            <th>Ставка</th>
                            <th>Результат</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for bet in history[:5] %}
                        <tr>
                            <td style="font-size:12px;">{{ bet.home }} vs {{ bet.away }}</td>
                            <td>{{ bet.bet }}</td>
                            <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                        </tr>
                        {% else %}
                        <tr><td colspan="3" class="no-data">Нет данных</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
    </div>
    
    <script>
        // ===== ТЁМНАЯ/СВЕТЛАЯ ТЕМА =====
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
        
        // Восстановление темы
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeBtn').textContent = savedTheme === 'dark' ? '🌙' : '☀️';
        
        // ===== ГРАФИК ПРИБЫЛИ =====
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
                                pointRadius: 4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    labels: {
                                        color: isDark ? '#e0e0e0' : '#1a1a2e',
                                        font: { size: 12 }
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    ticks: { color: isDark ? '#8888aa' : '#666688' }
                                },
                                y: {
                                    ticks: { 
                                        color: isDark ? '#8888aa' : '#666688',
                                        callback: function(value) { return '$' + value; }
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
        
        // ===== ЭКСПОРТ В PDF =====
        function exportPDF() {
            window.open('/export_pdf', '_blank');
        }
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
    
    for bet in history:
        if bet.get('result') == 'win':
            profit = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
            bet['profit'] = f"${profit}"
        elif bet.get('result') == 'loss':
            profit = -round(bet.get('stake', 0), 2)
            bet['profit'] = f"${profit}"
        else:
            bet['profit'] = "$0.00"
    
    # Топ лиги
    league_stats = {}
    for bet in history:
        league = bet.get('league', 'Unknown')
        if league not in league_stats:
            league_stats[league] = {'wins': 0, 'total': 0, 'profit': 0}
        league_stats[league]['total'] += 1
        if bet.get('result') == 'win':
            league_stats[league]['wins'] += 1
            league_stats[league]['profit'] += bet.get('stake', 0) * (bet.get('odds', 1) - 1)
        elif bet.get('result') == 'loss':
            league_stats[league]['profit'] -= bet.get('stake', 0)
    
    top_leagues = []
    for league, data in league_stats.items():
        if data['total'] >= 3:
            winrate = round(data['wins'] / data['total'] * 100, 1)
            top_leagues.append({
                'name': league,
                'winrate': winrate,
                'profit': round(data['profit'], 2)
            })
    top_leagues.sort(key=lambda x: x['winrate'], reverse=True)
    top_leagues = top_leagues[:5]
    
    return render_template_string(DASHBOARD_HTML, 
                                   stats=stats, 
                                   bank=bank, 
                                   history=history,
                                   top_leagues=top_leagues)

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

@app.route('/export_pdf')
def export_pdf():
    # Простой PDF через HTML
    from flask import render_template_string
    html = """
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Отчёт</title></head>
    <body style="font-family:Arial;padding:40px;">
        <h1>📊 Отчёт Quantum Bet Bot</h1>
        <p>Дата: {{ now }}</p>
        <hr>
        <h2>Статистика</h2>
        <ul>
            <li>Банк: ${{ bank }}</li>
            <li>Выигрыши: {{ stats.wins }}</li>
            <li>Проигрыши: {{ stats.losses }}</li>
            <li>Прибыль: ${{ stats.total_profit }}</li>
        </ul>
        <hr>
        <p style="color:#888;font-size:12px;">Сгенерировано автоматически</p>
    </body>
    </html>
    """
    stats = storage.load_stats()
    bank = storage.load_bank()
    html_rendered = render_template_string(html, stats=stats, bank=bank, now=datetime.now().strftime('%d.%m.%Y %H:%M'))
    
    from weasyprint import HTML as WeasyHTML
    pdf = WeasyHTML(string=html_rendered).write_pdf()
    
    return send_file(io.BytesIO(pdf), as_attachment=True, download_name='report.pdf', mimetype='application/pdf')

# ============================================================
# ОСТАЛЬНЫЕ МАРШРУТЫ
# ============================================================

@app.route('/matches')
def matches_page():
    try:
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
        matches = get_matches_with_factors()
        arbs = []
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
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
