import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request
import requests
from datetime import datetime, timedelta
import json
import random
import time
import logging

# ===== НАСТРОЙКИ БОТА =====
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== КОНФИГ =====
TOKEN = "8884017743:AAHkCNM9BTFHaGo5P9dd3aExq9iHL4Jy8LA"
ADMIN_CHAT_ID = "228801334"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ===== ИНИЦИАЛИЗАЦИЯ БОТА =====
bot_app = Application.builder().token(TOKEN).build()

# ===== КОМАНДЫ БОТА =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Бот работает! Веб-интерфейс доступен.")

async def bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Банк: $1000")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Статистика загружается...")

# Регистрация команд
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("bank", bank))
bot_app.add_handler(CommandHandler("stats", stats))

# ===== ВЕБХУК =====
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return 'No data', 400
        
        update = Update.de_json(data, bot_app.bot)
        bot_app.process_update(update)
        return 'ok', 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return 'error', 500

# ============================================================
# ВЕБ-ИНТЕРФЕЙС (ТВОЙ HTML)
# ============================================================

MAIN_HTML = """
<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
    <title>Quantum Bet Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
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
            padding-bottom: 80px;
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
        .btn-primary { background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn-primary:hover { background: #764ba2; transform: scale(1.02); }
        
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
            text-align: center;
            box-shadow: 0 2px 10px var(--shadow);
        }
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
        .chart-container { height: 200px; width: 100%; }
        
        .table-wrapper { overflow-x: auto; }
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
            background: var(--bg-card);
        }
        
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
        
        .profit-positive { color: #38ef7d; font-weight: bold; }
        .profit-negative { color: #ef473a; font-weight: bold; }
        
        .no-data { text-align: center; color: var(--text-secondary); padding: 30px 0; }
        .no-data .emoji { font-size: 48px; margin-bottom: 10px; }
        
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 10px 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
        }
        .bottom-nav .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            color: var(--text-secondary);
            font-size: 10px;
            transition: all 0.3s;
            padding: 4px 12px;
            border-radius: 8px;
            border: none;
            background: transparent;
            cursor: pointer;
            min-width: 60px;
        }
        .bottom-nav .nav-item .icon { font-size: 22px; }
        .bottom-nav .nav-item .label { font-size: 9px; margin-top: 2px; }
        .bottom-nav .nav-item.active { color: var(--gradient-start); }
        .bottom-nav .nav-item.active::after {
            content: '';
            position: absolute;
            top: -1px;
            left: 50%;
            transform: translateX(-50%);
            width: 20px;
            height: 2px;
            background: var(--gradient-start);
            border-radius: 2px;
        }
        
        .setting-group {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
        }
        .setting-group h2 { color: var(--text-secondary); font-size: 14px; font-weight: normal; margin-bottom: 10px; }
        .setting-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid var(--bg-primary);
            flex-wrap: wrap;
            gap: 8px;
        }
        .setting-item:last-child { border-bottom: none; }
        .input-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .input-group input {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 6px 10px;
            border-radius: 6px;
            width: 120px;
        }
        .input-group button {
            background: var(--gradient-start);
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
        }
        .toggle {
            width: 44px;
            height: 24px;
            background: var(--input-border);
            border-radius: 12px;
            cursor: pointer;
            position: relative;
            transition: 0.3s;
        }
        .toggle.active { background: var(--gradient-start); }
        .toggle .dot {
            width: 18px;
            height: 18px;
            background: white;
            border-radius: 50%;
            position: absolute;
            top: 3px;
            left: 3px;
            transition: 0.3s;
        }
        .toggle.active .dot { left: 23px; }
        .file-input-label {
            display: inline-block;
            padding: 6px 14px;
            background: var(--gradient-start);
            color: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        .file-input-label:hover { background: var(--gradient-end); }
        .import-status { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
        
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
        
        .slider-container { margin: 20px 0; }
        .slider-container input[type="range"] {
            width: 100%;
            height: 8px;
            background: var(--input-border);
            border-radius: 4px;
            outline: none;
        }
        .slider-container input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--gradient-start);
            cursor: pointer;
        }
        
        .sim-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .sim-stat {
            background: var(--bg-card);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid var(--border-color);
        }
        .sim-stat .value { font-size: 28px; font-weight: bold; }
        .sim-stat .value.green { color: #38ef7d; }
        .sim-stat .value.red { color: #ef473a; }
        .sim-stat .value.gold { color: #ffd200; }
        .sim-stat .label { color: var(--text-secondary); font-size: 13px; margin-top: 5px; }
        
        .match-card {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
        }
        .match-title { font-size: 16px; font-weight: bold; }
        .match-league { color: var(--text-secondary); font-size: 13px; }
        .match-xg { color: var(--gradient-start); font-size: 13px; }
        .match-bets { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }
        .bet-item {
            background: var(--bg-card);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            border: 1px solid var(--border-color);
        }
        
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
            .bottom-nav .nav-item .icon { font-size: 18px; }
            .bottom-nav .nav-item .label { font-size: 8px; }
            .header h1 { font-size: 20px; }
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
            <button class="btn active" onclick="showPage('dashboard')">📊 Дашборд</button>
            <button class="btn" onclick="showPage('matches')">⚽ Матчи</button>
            <button class="btn" onclick="showPage('stats')">📈 Статистика</button>
            <button class="btn" onclick="showPage('simulator')">🎲 Симулятор</button>
            <button class="btn" onclick="showPage('settings')">⚙️ Настройки</button>
            <button class="btn" onclick="location.reload()">🔄 Обновить</button>
        </div>
        
        <div id="page-dashboard" class="page"><div id="dashboard-content">Загрузка...</div></div>
        <div id="page-matches" class="page" style="display:none;"><div id="matches-content">Загрузка...</div></div>
        <div id="page-stats" class="page" style="display:none;"><div id="stats-content">Загрузка...</div></div>
        <div id="page-simulator" class="page" style="display:none;"><div id="simulator-content">Загрузка...</div></div>
        <div id="page-settings" class="page" style="display:none;"><div id="settings-content">Загрузка...</div></div>
        
        <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
    </div>
    
    <div class="bottom-nav">
        <button class="nav-item active" onclick="showPage('dashboard')"><span class="icon">📊</span><span class="label">Дашборд</span></button>
        <button class="nav-item" onclick="showPage('matches')"><span class="icon">⚽</span><span class="label">Матчи</span></button>
        <button class="nav-item" onclick="showPage('stats')"><span class="icon">📈</span><span class="label">Статистика</span></button>
        <button class="nav-item" onclick="showPage('simulator')"><span class="icon">🎲</span><span class="label">Симулятор</span></button>
        <button class="nav-item" onclick="showPage('settings')"><span class="icon">⚙️</span><span class="label">Настройки</span></button>
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
        
        function showPage(page) {
            document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
            document.getElementById('page-' + page).style.display = 'block';
            document.querySelectorAll('.nav .btn, .bottom-nav .nav-item').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.nav .btn[onclick*="' + page + '"], .bottom-nav .nav-item[onclick*="' + page + '"]').forEach(b => b.classList.add('active'));
            loadPage(page);
        }
        
        function loadPage(page) {
            const el = document.getElementById(page + '-content');
            fetch('/api/' + page + '_data')
                .then(r => r.json())
                .then(data => {
                    if (page === 'dashboard') renderDashboard(el, data);
                    else if (page === 'matches') renderMatches(el, data);
                    else if (page === 'stats') renderStats(el, data);
                    else if (page === 'simulator') renderSimulator(el, data);
                    else if (page === 'settings') renderSettings(el, data);
                })
                .catch(() => el.innerHTML = '<div class="no-data"><div class="emoji">⚠️</div>Ошибка загрузки</div>');
        }
        
        function renderDashboard(el, data) {
            const s = data.stats;
            const history = data.history || [];
            let html = `
                <div class="stats-grid">
                    <div class="stat-card"><div class="value">$${s.bank}</div><div class="label">💰 Текущий банк</div></div>
                    <div class="stat-card"><div class="value green">${s.wins}</div><div class="label">✅ Выигрыши</div></div>
                    <div class="stat-card"><div class="value red">${s.losses}</div><div class="label">❌ Проигрыши</div></div>
                    <div class="stat-card"><div class="value gold">$${s.profit}</div><div class="label">💰 Прибыль</div></div>
                </div>
                <div class="summary-row">
                    <div class="summary-item"><div class="label">📊 Всего ставок</div><div class="value">${s.total_bets}</div></div>
                    <div class="summary-item"><div class="label">🎯 Проходимость</div><div class="value">${s.winrate}%</div></div>
                    <div class="summary-item"><div class="label">📈 ROI</div><div class="value">${s.roi}%</div></div>
                    <div class="summary-item"><div class="label">📅 Средняя ставка</div><div class="value">$${s.avg_stake}</div></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>📈 График прибыли</h2><span style="font-size:12px;color:var(--text-secondary);">За последние 7 дней</span></div>
                    <div class="chart-container"><canvas id="profitChart"></canvas></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>📋 Все ставки</h2><span class="count">Всего: ${history.length}</span></div>
                    <div class="table-wrapper"><table>
                        <thead><tr><th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead>
                        <tbody>
            `;
            if (history.length === 0) {
                html += `<tr><td colspan="10" class="no-data"><div class="emoji">📭</div>Нет данных</td></tr>`;
            } else {
                history.slice().reverse().forEach(bet => {
                    const profitClass = bet.profit > 0 ? 'profit-positive' : (bet.profit < 0 ? 'profit-negative' : '');
                    html += `<tr>
                        <td>${history.indexOf(bet) + 1}</td>
                        <td style="font-size:11px;white-space:nowrap;">${bet.date}</td>
                        <td><strong>${bet.home}</strong> vs <strong>${bet.away}</strong></td>
                        <td>${bet.home_goals !== null && bet.away_goals !== null ? bet.home_goals + ' - ' + bet.away_goals : '-'}</td>
                        <td>${bet.bet}</td>
                        <td>${bet.odds}</td>
                        <td>$${bet.stake}</td>
                        <td>${bet.ev}%</td>
                        <td><span class="badge ${bet.result}">${bet.result}</span></td>
                        <td class="${profitClass}">$${bet.profit}</td>
                    </tr>`;
                });
            }
            html += `</tbody></table></div></div>`;
            el.innerHTML = html;
            setTimeout(() => {
                const ctx = document.getElementById('profitChart');
                if (!ctx) return;
                const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.profit_data?.dates || ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],
                        datasets: [{
                            label: 'Прибыль ($)',
                            data: data.profit_data?.profits || [0,0,0,0,0,0,0],
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
                        plugins: { legend: { labels: { color: isDark ? '#e0e0e0' : '#1a1a2e', font: { size: 10 } } } },
                        scales: {
                            x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 10 } } },
                            y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: v => '$' + v, font: { size: 10 } } }
                        }
                    }
                });
            }, 50);
        }
        
        function renderMatches(el, data) {
            const matches = data.matches || [];
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">⚽ Матчи на сегодня</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Прогнозы и валуйные ставки</div>`;
            if (matches.length === 0) {
                html += `<div class="no-data"><div class="emoji">📭</div>Матчей не найдено</div>`;
            } else {
                matches.forEach(m => {
                    html += `<div class="match-card">
                        <div class="match-title">${m.home} vs ${m.away}</div>
                        <div class="match-league">🏆 ${m.league} | ⏰ ${m.match_time}</div>
                        <div class="match-xg">📊 xG: ${m.home_xg || '?'} : ${m.away_xg || '?'}</div>
                        <div class="match-bets">${(m.bets || []).slice(0,3).map(b => `<span class="bet-item">${b.label} | КЭФ: ${b.odds} | EV: ${b.ev}%</span>`).join('')}</div>
                    </div>`;
                });
            }
            el.innerHTML = html;
        }
        
        function renderStats(el, data) {
            const s = data.stats;
            const history = data.history || [];
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">📈 Статистика</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Детальный анализ ваших ставок</div>
                <div class="card"><div style="display:flex;gap:15px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:var(--gradient-start);">${s.total_bets}</div><div style="color:var(--text-secondary);font-size:12px;">Всего ставок</div></div>
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:#38ef7d;">${s.wins}</div><div style="color:var(--text-secondary);font-size:12px;">Выигрыши</div></div>
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:#ef473a;">${s.losses}</div><div style="color:var(--text-secondary);font-size:12px;">Проигрыши</div></div>
                    <div style="flex:1;min-width:100px;"><div style="font-size:22px;font-weight:bold;color:#ffd200;">$${s.profit}</div><div style="color:var(--text-secondary);font-size:12px;">Прибыль</div></div>
                </div></div>
                <div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📋 Все ставки</h2>
                <div class="table-wrapper"><table><thead><tr><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead><tbody>`;
            if (history.length === 0) {
                html += `<tr><td colspan="8" class="no-data">Нет данных</td></tr>`;
            } else {
                history.forEach(bet => {
                    html += `<tr><td style="font-size:11px;">${bet.date}</td><td>${bet.home} vs ${bet.away}</td><td>${bet.home_goals !== null && bet.away_goals !== null ? bet.home_goals + ' - ' + bet.away_goals : '-'}</td><td>${bet.bet}</td><td>${bet.odds}</td><td>${bet.ev}%</td><td><span class="badge ${bet.result}">${bet.result}</span></td><td>$${bet.profit}</td></tr>`;
                });
            }
            html += `</tbody></table></div></div>`;
            el.innerHTML = html;
        }
        
        function renderSimulator(el, data) {
            const history = data.history || [];
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">🎲 Симулятор ставок</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Узнай, сколько ты мог бы заработать!</div>`;
            if (history.length < 5) {
                html += `<div class="card"><div class="no-data"><div class="emoji">📭</div><div>Нет данных для симуляции</div><div style="font-size:13px;color:var(--text-secondary);">Сначала сделайте хотя бы 5 ставок!</div></div></div>`;
            } else {
                html += `<div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📊 Параметры симуляции</h2>
                    <div class="slider-container"><label style="color:var(--text-secondary);font-size:14px;">Количество симуляций: <span id="simCountLabel">1000</span></label>
                    <input type="range" id="simCount" min="100" max="5000" step="100" value="1000" oninput="document.getElementById('simCountLabel').textContent=this.value"></div>
                    <button class="btn-primary" onclick="runSimulation()">🎲 Запустить симуляцию</button>
                    <button class="btn" onclick="document.getElementById('simResults').style.display='none'">🔄 Сбросить</button>
                </div>
                <div id="simResults" style="display:none;">
                    <div class="sim-stats">
                        <div class="sim-stat"><div class="value gold" id="simProfit">$0</div><div class="label">💰 Ожидаемая прибыль</div></div>
                        <div class="sim-stat"><div class="value green" id="simWinrate">0%</div><div class="label">🎯 Проходимость</div></div>
                        <div class="sim-stat"><div class="value" id="simROI">0%</div><div class="label">📈 ROI</div></div>
                        <div class="sim-stat"><div class="value red" id="simRisk">0%</div><div class="label">⚠️ Риск</div></div>
                    </div>
                    <div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📈 График симуляции</h2><div class="chart-container"><canvas id="simChart"></canvas></div></div>
                    <div class="card"><h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">📋 Результаты симуляции</h2>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:14px;">
                        <div style="color:var(--text-secondary);">Всего симуляций: <span id="simTotal" style="color:var(--text-primary);">0</span></div>
                        <div style="color:var(--text-secondary);">Выигрышных: <span id="simWins" style="color:#38ef7d;">0</span></div>
                        <div style="color:var(--text-secondary);">Проигрышных: <span id="simLosses" style="color:#ef473a;">0</span></div>
                        <div style="color:var(--text-secondary);">Макс. прибыль: <span id="simMaxProfit" style="color:#ffd200;">$0</span></div>
                        <div style="color:var(--text-secondary);">Мин. прибыль: <span id="simMinProfit" style="color:#ef473a;">$0</span></div>
                        <div style="color:var(--text-secondary);">Средняя ставка: <span id="simAvgStake" style="color:var(--text-primary);">$0</span></div>
                    </div></div>
                    <div class="card" style="background:rgba(102,126,234,0.05);border-color:var(--gradient-start);">
                        <h2 style="color:var(--text-secondary);font-size:14px;font-weight:normal;margin-bottom:10px;">💡 Рекомендация</h2>
                        <div id="simRecommendation" style="font-size:16px;line-height:1.6;">Запустите симуляцию, чтобы получить рекомендацию!</div>
                    </div>
                </div>`;
            }
            el.innerHTML = html;
        }
        
        function renderSettings(el, data) {
            const bank = data.stats?.bank || 1000;
            let html = `<h1 style="font-size:24px;color:var(--gradient-start);">⚙️ Настройки</h1><div style="color:var(--text-secondary);margin-bottom:15px;">Управление ботом</div>
                <div class="setting-group"><h2>💰 Банк</h2><div class="setting-item"><div><div class="label">Текущий банк</div><div class="desc">Ваш игровой банк</div></div><div class="input-group"><input type="number" id="bankInput" value="${bank}" step="10"><button onclick="updateBank()">Сохранить</button></div></div></div>
                <div class="setting-group"><h2>🤖 Автоматизация</h2><div class="setting-item"><div><div class="label">Авто-ставки</div><div class="desc">Автоматическое размещение ставок</div></div><div class="toggle active" onclick="this.classList.toggle('active')"><div class="dot"></div></div></div></div>
                <div class="setting-group"><h2>📊 Экспорт / Импорт</h2>
                    <div class="setting-item"><div><div class="label">Экспорт данных</div><div class="desc">Скачать историю в Excel</div></div><button class="btn" onclick="window.location.href='/export'">📥 Скачать</button></div>
                    <div class="setting-item" style="border-bottom:none;"><div><div class="label">Импорт данных</div><div class="desc">Загрузить историю из Excel</div></div><div class="input-group"><label class="file-input-label" for="importFileInput">📤 Выбрать файл</label><input type="file" id="importFileInput" accept=".xlsx,.csv" style="display:none" onchange="importExcel(event)"><span id="fileName" style="color:var(--text-secondary);font-size:12px;">Файл не выбран</span></div></div>
                    <div id="importStatus" class="import-status"></div>
                </div>`;
            el.innerHTML = html;
        }
        
        function runSimulation() {
            const count = parseInt(document.getElementById('simCount').value) || 1000;
            document.getElementById('simResults').style.display = 'block';
            fetch('/api/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: count })
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) { alert('❌ ' + data.error); return; }
                document.getElementById('simProfit').textContent = '$' + data.profit;
                document.getElementById('simWinrate').textContent = data.winrate + '%';
                document.getElementById('simROI').textContent = data.roi + '%';
                document.getElementById('simRisk').textContent = data.risk + '%';
                document.getElementById('simTotal').textContent = data.total;
                document.getElementById('simWins').textContent = data.wins;
                document.getElementById('simLosses').textContent = data.losses;
                document.getElementById('simMaxProfit').textContent = '$' + data.max_profit;
                document.getElementById('simMinProfit').textContent = '$' + data.min_profit;
                document.getElementById('simAvgStake').textContent = '$' + data.avg_stake;
                const rec = document.getElementById('simRecommendation');
                if (data.profit > 0) {
                    rec.innerHTML = '✅ <b style="color:#38ef7d;">Отличный результат!</b> Ваша стратегия принесла бы прибыль!<br>💡 Средняя прибыль на ставку: $' + (data.profit / data.total).toFixed(2) + '<br>🔥 Лучший результат: +$' + data.max_profit;
                } else {
                    rec.innerHTML = '⚠️ <b style="color:#ef473a;">Стратегия требует улучшения</b><br>💡 Попробуйте снизить сумму ставок<br>📊 Работайте над проходимостью (сейчас ' + data.winrate + '%)';
                }
                const ctx = document.getElementById('simChart');
                if (ctx) {
                    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.labels || Array.from({length: data.history?.length || 10}, (_, i) => i + 1),
                            datasets: [{
                                label: 'Прибыль ($)',
                                data: data.history || [],
                                borderColor: data.profit > 0 ? '#38ef7d' : '#ef473a',
                                backgroundColor: data.profit > 0 ? 'rgba(56,239,125,0.1)' : 'rgba(239,71,58,0.1)',
                                fill: true,
                                tension: 0.4,
                                pointRadius: 2
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { labels: { color: isDark ? '#e0e0e0' : '#1a1a2e', font: { size: 10 } } } },
                            scales: {
                                x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 9 } } },
                                y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: v => '$' + v, font: { size: 9 } } }
                            }
                        }
                    });
                }
            });
        }
        
        function updateBank() {
            const value = document.getElementById('bankInput').value;
            fetch('/api/bank', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bank: parseFloat(value) })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) { alert('✅ Банк обновлен: $' + data.bank); location.reload(); }
            });
        }
        
        function importExcel(event) {
            const file = event.target.files[0];
            const statusDiv = document.getElementById('importStatus');
            const fileNameSpan = document.getElementById('fileName');
            if (!file) { statusDiv.textContent = '❌ Файл не выбран'; return; }
            fileNameSpan.textContent = '📄 ' + file.name;
            statusDiv.textContent = '⏳ Загрузка...';
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, {type: 'array'});
                    const sheet = workbook.Sheets[workbook.SheetNames[0]];
                    const json = XLSX.utils.sheet_to_json(sheet);
                    if (json.length === 0) { statusDiv.textContent = '❌ Файл пуст'; return; }
                    statusDiv.textContent = '⏳ Отправка...';
                    fetch('/api/import_excel', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ data: json })
                    })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            statusDiv.textContent = '✅ Импортировано ' + data.count + ' ставок!';
                            setTimeout(() => location.reload(), 1500);
                        } else {
                            statusDiv.textContent = '❌ Ошибка: ' + data.error;
                        }
                    });
                } catch (error) {
                    statusDiv.textContent = '❌ Ошибка: ' + error;
                }
            };
            reader.readAsArrayBuffer(file);
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            loadPage('dashboard');
        });
    </script>
</body>
</html>
"""

# ============================================================
# API ДЛЯ ВЕБ-ИНТЕРФЕЙСА
# ============================================================

@app.route('/')
def index():
    return render_template_string(MAIN_HTML)

@app.route('/api/dashboard_data')
def dashboard_data():
    data = {'bank': 1000, 'wins': 0, 'losses': 0, 'profit': 0, 'total_bets': 0, 'winrate': 0, 'roi': 0, 'avg_stake': 0}
    history = []
    profit_data = {'dates': ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], 'profits': [0,0,0,0,0,0,0]}
    return jsonify({'stats': data, 'history': history, 'profit_data': profit_data})

@app.route('/api/matches_data')
def matches_data():
    return jsonify({'matches': []})

@app.route('/api/stats_data')
def stats_data():
    data = {'bank': 1000, 'wins': 0, 'losses': 0, 'profit': 0, 'total_bets': 0, 'winrate': 0, 'roi': 0, 'avg_stake': 0}
    return jsonify({'stats': data, 'history': []})

@app.route('/api/simulator_data')
def simulator_data():
    return jsonify({'history': []})

@app.route('/api/settings_data')
def settings_data():
    return jsonify({'stats': {'bank': 1000}})

@app.route('/api/simulate', methods=['POST'])
def simulate():
    return jsonify({'error': 'Симулятор временно отключен'}), 400

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    return jsonify({'error': 'Импорт временно отключен'}), 400

@app.route('/api/bank', methods=['POST'])
def update_bank():
    return jsonify({'success': True, 'bank': 1000})

@app.route('/export')
def export_data():
    return "Нет данных для экспорта", 404

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
