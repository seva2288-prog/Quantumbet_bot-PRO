import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request
from app.database.storage import storage
from app.bot import get_matches_with_factors, find_top_matches
from app.api.football import football_api
from app.analytics.arbitrage import arbitrage_analyzer
from app.analytics.anomalies import anomaly_detector
from app.ml.predictor import ml_predictor

app = Flask(__name__)

# ============================================================
# КРАСИВЫЙ HTML ШАБЛОН
# ============================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Quantum Bet Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a0f2e 50%, #0f1a2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        /* Шапка */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .header h1 {
            font-size: 32px;
            background: linear-gradient(135deg, #667eea, #764ba2, #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header .status {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #38ef7d;
            font-size: 14px;
        }
        .status-dot {
            display: inline-block;
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
        
        /* Навигация */
        .nav {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 25px;
        }
        .nav a { text-decoration: none; }
        .btn {
            padding: 10px 22px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.1);
            background: rgba(255,255,255,0.05);
            color: #a0a0c0;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
            backdrop-filter: blur(10px);
        }
        .btn:hover {
            background: rgba(102, 126, 234, 0.2);
            border-color: #667eea;
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.2);
        }
        .btn.active {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-color: #667eea;
            color: #fff;
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
        }
        .btn.refresh-btn {
            background: rgba(255,255,255,0.05);
        }
        .btn.refresh-btn:hover {
            background: rgba(102, 126, 234, 0.2);
            border-color: #667eea;
            color: #fff;
        }
        
        /* Карточки статистики */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .stat-card {
            padding: 24px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03);
            backdrop-filter: blur(10px);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg, transparent 60%, rgba(102, 126, 234, 0.05));
            pointer-events: none;
        }
        .stat-card:hover { transform: translateY(-4px); border-color: rgba(102, 126, 234, 0.3); }
        .stat-card .icon { font-size: 24px; margin-bottom: 8px; }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            background: linear-gradient(135deg, #667eea, #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.green { background: linear-gradient(135deg, #11998e, #38ef7d); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.red { background: linear-gradient(135deg, #cb2d3e, #ef473a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.gold { background: linear-gradient(135deg, #f7971e, #ffd200); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .label { color: #8888aa; font-size: 13px; margin-top: 4px; }
        
        /* Таблица */
        .card {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 15px;
        }
        .card-header h2 { color: #a0a0c0; font-size: 16px; font-weight: normal; }
        .card-header .count { color: #667eea; font-size: 14px; }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        th, td {
            padding: 12px 10px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        th { color: #666688; font-weight: normal; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
        tr:hover td { background: rgba(255,255,255,0.03); }
        
        .badge {
            display: inline-block;
            padding: 3px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
        }
        .badge.win { background: rgba(56, 239, 125, 0.15); color: #38ef7d; border: 1px solid rgba(56, 239, 125, 0.2); }
        .badge.loss { background: rgba(239, 71, 58, 0.15); color: #ef473a; border: 1px solid rgba(239, 71, 58, 0.2); }
        .badge.pending { background: rgba(255, 210, 0, 0.15); color: #ffd200; border: 1px solid rgba(255, 210, 0, 0.2); }
        
        .profit-positive { color: #38ef7d; }
        .profit-negative { color: #ef473a; }
        
        .no-data {
            text-align: center;
            color: #555577;
            padding: 40px 0;
        }
        .no-data .emoji { font-size: 48px; margin-bottom: 15px; }
        
        .footer {
            text-align: center;
            color: #333355;
            font-size: 12px;
            margin-top: 30px;
            padding: 20px 0;
            border-top: 1px solid rgba(255,255,255,0.05);
        }
        
        @media (max-width: 600px) {
            .header h1 { font-size: 24px; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .stat-card .value { font-size: 24px; }
            .nav { gap: 6px; }
            .btn { padding: 8px 14px; font-size: 12px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Шапка -->
        <div class="header">
            <h1>🤖 Quantum Bet Bot</h1>
            <div class="status">
                <span class="status-dot"></span>
                <span>Система активна</span>
                <span style="color:#555577;">|</span>
                <span style="color:#666688;">v12 PRO</span>
            </div>
        </div>
        
        <!-- Навигация -->
        <div class="nav">
            <a href="/"><button class="btn active">📊 Дашборд</button></a>
            <a href="/matches"><button class="btn">⚽ Матчи</button></a>
            <a href="/stats"><button class="btn">📈 Статистика</button></a>
            <a href="/arbitrage"><button class="btn">🔍 Вилки</button></a>
            <a href="/settings"><button class="btn">⚙️ Настройки</button></a>
            <button class="btn refresh-btn" onclick="location.reload()">🔄 Обновить</button>
        </div>
        
        <!-- Статистика -->
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
        
        <!-- Последние ставки -->
        <div class="card">
            <div class="card-header">
                <h2>📋 Последние ставки</h2>
                <span class="count">{{ history|length }} записей</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Матч</th>
                        <th>Ставка</th>
                        <th>Кэф</th>
                        <th>EV</th>
                        <th>Результат</th>
                        <th>Прибыль</th>
                    </tr>
                </thead>
                <tbody>
                    {% for bet in history[:10] %}
                    <tr>
                        <td>{{ bet.home }} vs {{ bet.away }}</td>
                        <td>{{ bet.bet }}</td>
                        <td>{{ bet.odds }}</td>
                        <td>{{ bet.ev }}%</td>
                        <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                        <td class="{% if bet.profit|replace('$','')|float > 0 %}profit-positive{% else %}profit-negative{% endif %}">{{ bet.profit }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6">
                            <div class="no-data">
                                <div class="emoji">📭</div>
                                <div>Нет данных</div>
                                <div style="font-size:13px;color:#444466;">Начните делать ставки!</div>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            Quantum Bet Bot v12 PRO © 2026
        </div>
    </div>
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
    
    return render_template_string(DASHBOARD_HTML, stats=stats, bank=bank, history=history)

@app.route('/matches')
def matches_page():
    try:
        matches = get_matches_with_factors()
        top_matches = find_top_matches(matches) if matches else []
        return render_template_string(MATCHES_HTML, matches=top_matches)
    except Exception as e:
        return render_template_string(MATCHES_HTML, matches=[])

# Остальные маршруты остаются без изменений...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
