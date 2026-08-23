from flask import Flask, render_template_string, jsonify
from app.database.storage import storage

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Betting Bot Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: #0f0f1a; 
            padding: 20px; 
            color: #e0e0e0;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        
        h1 { 
            color: #fff; 
            margin-bottom: 20px; 
            font-size: 28px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        h1 span { background: linear-gradient(135deg, #667eea, #764ba2); padding: 5px 15px; border-radius: 8px; font-size: 14px; }
        
        .card { 
            background: #1a1a2e; 
            padding: 20px; 
            border-radius: 12px; 
            margin-bottom: 20px; 
            border: 1px solid #2a2a4a;
        }
        .card h2 { color: #a0a0c0; font-size: 16px; margin-bottom: 15px; font-weight: normal; letter-spacing: 1px; }
        
        .grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); 
            gap: 15px; 
        }
        .stat { 
            background: linear-gradient(135deg, #1a1a3e 0%, #2a1a4e 100%); 
            padding: 20px; 
            border-radius: 10px; 
            border: 1px solid #333366;
        }
        .stat .value { 
            font-size: 28px; 
            font-weight: bold; 
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stat .label { font-size: 13px; color: #8888aa; margin-top: 5px; }
        
        .stat.green .value { background: linear-gradient(135deg, #11998e, #38ef7d); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat.red .value { background: linear-gradient(135deg, #cb2d3e, #ef473a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat.gold .value { background: linear-gradient(135deg, #f7971e, #ffd200); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 12px 10px; text-align: left; border-bottom: 1px solid #2a2a4a; }
        th { color: #8888aa; font-weight: normal; text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }
        tr:hover { background: #1a1a3e; }
        
        .badge { 
            display: inline-block; 
            padding: 3px 12px; 
            border-radius: 20px; 
            font-size: 11px; 
            font-weight: bold; 
            text-transform: uppercase;
        }
        .badge.win { background: #1a4a2a; color: #38ef7d; }
        .badge.loss { background: #4a1a1a; color: #ef473a; }
        .badge.pending { background: #4a3a1a; color: #ffd200; }
        
        .refresh-btn { 
            background: linear-gradient(135deg, #667eea, #764ba2); 
            color: white; 
            border: none; 
            padding: 8px 20px; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 13px;
            transition: all 0.3s;
        }
        .refresh-btn:hover { opacity: 0.8; transform: scale(1.02); }
        
        .header-actions { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        
        .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
        .status-dot.online { background: #38ef7d; }
        .status-dot.offline { background: #ef473a; }
        
        @media (max-width: 600px) {
            .grid { grid-template-columns: 1fr 1fr; }
            table { font-size: 12px; }
            th, td { padding: 8px 6px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>
            🤖 Betting Bot Dashboard
            <span>v12 PRO</span>
        </h1>
        
        <div class="card">
            <div class="header-actions">
                <h2>📊 Общая статистика</h2>
                <button class="refresh-btn" onclick="location.reload()">🔄 Обновить</button>
            </div>
            <div class="grid">
                <div class="stat">
                    <div class="value">{{ stats.total_bets }}</div>
                    <div class="label">Всего ставок</div>
                </div>
                <div class="stat green">
                    <div class="value">{{ stats.wins }}</div>
                    <div class="label">✅ Выигрышей</div>
                </div>
                <div class="stat red">
                    <div class="value">{{ stats.losses }}</div>
                    <div class="label">❌ Проигрышей</div>
                </div>
                <div class="stat gold">
                    <div class="value">${{ "%.2f"|format(stats.total_profit) }}</div>
                    <div class="label">💰 Прибыль</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>📋 Последние ставки</h2>
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
                    {% for bet in bets %}
                    <tr>
                        <td>{{ bet.match|truncate(30) }}</td>
                        <td>{{ bet.bet_type }}</td>
                        <td>{{ bet.odds }}</td>
                        <td>{{ bet.ev }}%</td>
                        <td><span class="badge {{ bet.result }}">{{ bet.result }}</span></td>
                        <td>${{ "%.2f"|format(bet.profit) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    stats = storage.load_stats()
    bets = storage.load_history()
    
    for bet in bets:
        if bet.get('result') == 'win':
            bet['profit'] = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
        elif bet.get('result') == 'loss':
            bet['profit'] = -round(bet.get('stake', 0), 2)
        else:
            bet['profit'] = 0
        bet['match'] = f"{bet.get('home', '')} vs {bet.get('away', '')}"
        bet['bet_type'] = bet.get('bet', '')
        bet['odds'] = bet.get('odds', 0)
        bet['ev'] = bet.get('ev', 0)
        bet['result'] = bet.get('result', 'pending')
    
    return render_template_string(HTML, stats=stats, bets=bets[-20:])

@app.route('/api/stats')
def api_stats():
    return jsonify(storage.load_stats())

@app.route('/api/matches')
def api_matches():
    cache = storage.load_cache()
    return jsonify(cache.get('top_matches', []))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
