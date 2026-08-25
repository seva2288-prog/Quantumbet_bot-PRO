import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request
import requests
from datetime import datetime, timedelta
import json
import random

app = Flask(__name__)

# URL бота
BOT_URL = 'https://quantumbet-bot-pro.onrender.com'

# ============================================================
# HTML ШАБЛОН ДАШБОРДА (С НИЖНЕЙ НАВИГАЦИЕЙ)
# ============================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
    <title>Quantum Bet Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
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
            --nav-bg: #1a1a2e;
            --nav-active: #667eea;
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
            --nav-bg: #ffffff;
            --nav-active: #667eea;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            transition: all 0.3s ease;
            overflow-x: hidden;
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
            font-size: 20px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header-controls {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        .status {
            display: flex;
            align-items: center;
            gap: 6px;
            color: #38ef7d;
            font-size: 11px;
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
            width: 32px;
            height: 32px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--text-primary);
        }
        .theme-toggle:hover { transform: scale(1.1); border-color: var(--gradient-start); }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 16px;
        }
        .stat-card {
            padding: 12px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            background: var(--bg-secondary);
            transition: all 0.3s;
            text-align: center;
            box-shadow: 0 2px 10px var(--shadow);
        }
        .stat-card:hover { transform: translateY(-2px); border-color: var(--gradient-start); }
        .stat-card .value {
            font-size: 20px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.green { background: linear-gradient(135deg, #11998e, #38ef7d); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.red { background: linear-gradient(135deg, #cb2d3e, #ef473a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.gold { background: linear-gradient(135deg, #f7971e, #ffd200); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .label { color: var(--text-secondary); font-size: 11px; margin-top: 3px; }
        
        .card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 14px;
            box-shadow: 0 2px 10px var(--shadow);
            overflow: hidden;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 10px;
        }
        .card-header h2 { color: var(--text-secondary); font-size: 14px; font-weight: normal; }
        .card-header .count { color: var(--text-secondary); font-size: 12px; }
        
        .chart-container {
            position: relative;
            height: 160px;
            width: 100%;
        }
        
        .table-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            min-width: 700px;
        }
        th, td {
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th { 
            color: var(--text-secondary); 
            font-weight: 600; 
            font-size: 10px; 
            text-transform: uppercase; 
            letter-spacing: 0.5px;
            background: var(--bg-card);
            position: sticky;
            top: 0;
        }
        tr:hover td { background: var(--bg-card); }
        
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
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
            padding: 8px;
            border-radius: 6px;
            display: none;
            margin-top: 4px;
        }
        .edit-row.active { display: table-row; }
        .edit-row input, .edit-row select {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 3px 6px;
            border-radius: 4px;
            font-size: 11px;
            margin-right: 3px;
        }
        .edit-row .btn { padding: 3px 10px; font-size: 11px; }
        .edit-btn { cursor: pointer; color: var(--text-secondary); font-size: 12px; }
        .edit-btn:hover { color: var(--gradient-start); }
        
        .no-data { text-align: center; color: var(--text-secondary); padding: 20px 0; }
        .no-data .emoji { font-size: 36px; margin-bottom: 6px; }
        
        .summary-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }
        .summary-item {
            background: var(--bg-card);
            padding: 10px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }
        .summary-item .label { color: var(--text-secondary); font-size: 11px; }
        .summary-item .value { font-size: 16px; font-weight: bold; }
        
        .scrollable-table {
            max-height: 400px;
            overflow-y: auto;
        }
        
        .footer {
            text-align: center;
            color: #444466;
            font-size: 10px;
            margin-top: 16px;
            padding: 12px 0;
            border-top: 1px solid var(--border-color);
        }
        
        /* ===== НИЖНЯЯ НАВИГАЦИЯ ===== */
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--nav-bg);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 8px 0;
            z-index: 1000;
            box-shadow: 0 -4px 20px rgba(0,0,0,0.3);
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
            position: relative;
        }
        .bottom-nav .nav-item .icon {
            font-size: 22px;
            line-height: 1.2;
            transition: all 0.3s;
        }
        .bottom-nav .nav-item .label {
            font-size: 9px;
            margin-top: 2px;
            font-weight: 500;
        }
        .bottom-nav .nav-item.active {
            color: var(--nav-active);
        }
        .bottom-nav .nav-item.active .icon {
            transform: scale(1.1);
        }
        .bottom-nav .nav-item.active::after {
            content: '';
            position: absolute;
            top: -1px;
            left: 50%;
            transform: translateX(-50%);
            width: 20px;
            height: 2px;
            background: var(--nav-active);
            border-radius: 2px;
        }
        .bottom-nav .nav-item:hover {
            color: var(--text-primary);
        }
        
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: stretch; gap: 8px; padding: 12px 16px; }
            .header h1 { font-size: 18px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
            .summary-row { grid-template-columns: 1fr; }
            .card { padding: 10px; }
            table { font-size: 10px; min-width: 500px; }
            th, td { padding: 4px 5px; }
            .chart-container { height: 120px; }
            .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
            .bottom-nav .nav-item .icon { font-size: 18px; }
            .bottom-nav .nav-item .label { font-size: 8px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .stat-card { padding: 8px; }
            .stat-card .value { font-size: 16px; }
            .bottom-nav .nav-item { min-width: 44px; padding: 2px 6px; }
            .bottom-nav .nav-item .icon { font-size: 16px; }
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
                <span style="font-size:10px;color:var(--text-secondary);">За последние 7 дней</span>
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
                                <td style="font-size:10px;white-space:nowrap;">{{ bet.date }}</td>
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
                                    <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">
                                        <input type="text" id="edit_home_{{ loop.index0 }}" value="{{ bet.home }}" placeholder="Хозяева" style="width:80px;">
                                        <input type="text" id="edit_away_{{ loop.index0 }}" value="{{ bet.away }}" placeholder="Гости" style="width:80px;">
                                        <input type="text" id="edit_score_{{ loop.index0 }}" value="{% if bet.home_goals is not none and bet.away_goals is not none %}{{ bet.home_goals }}-{{ bet.away_goals }}{% endif %}" placeholder="Счёт" style="width:60px;">
                                        <input type="text" id="edit_bet_{{ loop.index0 }}" value="{{ bet.bet }}" placeholder="Ставка" style="width:80px;">
                                        <input type="number" id="edit_odds_{{ loop.index0 }}" value="{{ bet.odds }}" placeholder="Кэф" step="0.01" style="width:60px;">
                                        <input type="number" id="edit_stake_{{ loop.index0 }}" value="{{ bet.stake }}" placeholder="Сумма" step="0.5" style="width:70px;">
                                        <input type="number" id="edit_ev_{{ loop.index0 }}" value="{{ bet.ev }}" placeholder="EV" step="0.1" style="width:60px;">
                                        <select id="edit_result_{{ loop.index0 }}" style="padding:3px 6px;border-radius:4px;border:1px solid var(--input-border);background:var(--input-bg);color:var(--text-primary);font-size:11px;">
                                            <option value="win" {% if bet.result == 'win' %}selected{% endif %}>win</option>
                                            <option value="loss" {% if bet.result == 'loss' %}selected{% endif %}>loss</option>
                                            <option value="push" {% if bet.result == 'push' %}selected{% endif %}>push</option>
                                            <option value="pending" {% if bet.result == 'pending' %}selected{% endif %}>pending</option>
                                        </select>
                                        <button class="btn btn-success" onclick="saveEdit('{{ loop.index0 }}')" style="padding:3px 8px;font-size:10px;">💾</button>
                                        <button class="btn btn-danger" onclick="deleteBet('{{ loop.index0 }}')" style="padding:3px 8px;font-size:10px;">🗑️</button>
                                        <button class="btn" onclick="toggleEdit('{{ loop.index0 }}')" style="padding:3px 8px;font-size:10px;">✖</button>
                                    </div>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="11" class="no-data">
                                    <div class="emoji">📭</div>
                                    <div>Нет данных</div>
                                    <div style="font-size:11px;color:#444466;">Начните делать ставки!</div>
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
    
    <!-- ===== НИЖНЯЯ НАВИГАЦИЯ ===== -->
    <div class="bottom-nav">
        <a href="/" class="nav-item active">
            <span class="icon">📊</span>
            <span class="label">Дашборд</span>
        </a>
        <a href="/matches" class="nav-item">
            <span class="icon">⚽</span>
            <span class="label">Матчи</span>
        </a>
        <a href="/stats" class="nav-item">
            <span class="icon">📈</span>
            <span class="label">Статистика</span>
        </a>
        <a href="/simulator" class="nav-item">
            <span class="icon">🎲</span>
            <span class="label">Симулятор</span>
        </a>
        <a href="/settings" class="nav-item">
            <span class="icon">⚙️</span>
            <span class="label">Настройки</span>
        </a>
    </div>
    
    <script>
        // Подсветка активного пункта в нижней навигации
        document.querySelectorAll('.bottom-nav .nav-item').forEach(item => {
            if (item.getAttribute('href') === window.location.pathname) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
        
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
                                        font: { size: 9 }
                                    }
                                }
                            },
                            scales: {
                                x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 9 } } },
                                y: {
                                    ticks: { 
                                        color: isDark ? '#8888aa' : '#666688',
                                        callback: function(value) { return '$' + value; },
                                        font: { size: 9 }
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
# ШАБЛОН МАТЧЕЙ (С НИЖНЕЙ НАВИГАЦИЕЙ)
# ============================================================

MATCHES_HTML = """
<!DOCTYPE html>
<html>
<head><title>Матчи</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; padding-bottom: 80px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 22px; margin-bottom: 4px; }
.subtitle { color: #8888aa; margin-bottom: 12px; font-size: 13px; }
.match-card { background: #1a1a2e; padding: 12px; border-radius: 10px; border: 1px solid #2a2a4a; margin-bottom: 10px; overflow: hidden; }
.match-title { font-size: 15px; font-weight: bold; color: #e0e0e0; }
.match-league { color: #8888aa; font-size: 12px; }
.match-xg { color: #667eea; font-size: 12px; }
.match-bets { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.bet-item { background: #0f0f1a; padding: 3px 8px; border-radius: 5px; font-size: 11px; border: 1px solid #2a2a4a; }
.no-matches { text-align: center; color: #8888aa; padding: 30px 0; }

.bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #1a1a2e;
    border-top: 1px solid #2a2a4a;
    display: flex;
    justify-content: space-around;
    align-items: center;
    padding: 8px 0;
    z-index: 1000;
    backdrop-filter: blur(10px);
}
.bottom-nav .nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    color: #8888aa;
    font-size: 10px;
    transition: all 0.3s;
    padding: 4px 12px;
    border-radius: 8px;
    border: none;
    background: transparent;
    cursor: pointer;
    min-width: 60px;
    position: relative;
}
.bottom-nav .nav-item .icon { font-size: 22px; line-height: 1.2; }
.bottom-nav .nav-item .label { font-size: 9px; margin-top: 2px; font-weight: 500; }
.bottom-nav .nav-item.active { color: #667eea; }
.bottom-nav .nav-item.active::after {
    content: '';
    position: absolute;
    top: -1px;
    left: 50%;
    transform: translateX(-50%);
    width: 20px;
    height: 2px;
    background: #667eea;
    border-radius: 2px;
}
@media (max-width: 768px) {
    .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
    .bottom-nav .nav-item .icon { font-size: 18px; }
    .bottom-nav .nav-item .label { font-size: 8px; }
}
</style>
</head>
<body>
<div class="container">
    <h1>⚽ Матчи</h1>
    <div class="subtitle">Прогнозы и валуйные ставки</div>
    
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
        <span style="padding:4px 12px;background:#667eea;border-radius:16px;font-size:12px;color:#fff;">Все игры</span>
        <span style="padding:4px 12px;background:#1a1a2e;border:1px solid #2a2a4a;border-radius:16px;font-size:12px;color:#8888aa;">LIVE</span>
        <span style="padding:4px 12px;background:#1a1a2e;border:1px solid #2a2a4a;border-radius:16px;font-size:12px;color:#8888aa;">⭐ Избранное</span>
        <span style="padding:4px 12px;background:#1a1a2e;border:1px solid #2a2a4a;border-radius:16px;font-size:12px;color:#8888aa;">🏆 Турниры</span>
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

<div class="bottom-nav">
    <a href="/" class="nav-item"><span class="icon">📊</span><span class="label">Дашборд</span></a>
    <a href="/matches" class="nav-item active"><span class="icon">⚽</span><span class="label">Матчи</span></a>
    <a href="/stats" class="nav-item"><span class="icon">📈</span><span class="label">Статистика</span></a>
    <a href="/simulator" class="nav-item"><span class="icon">🎲</span><span class="label">Симулятор</span></a>
    <a href="/settings" class="nav-item"><span class="icon">⚙️</span><span class="label">Настройки</span></a>
</div>
</body>
</html>
"""

# ============================================================
# ШАБЛОН СТАТИСТИКИ (С НИЖНЕЙ НАВИГАЦИЕЙ)
# ============================================================

STATS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Статистика</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; padding-bottom: 80px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 22px; margin-bottom: 4px; }
.subtitle { color: #8888aa; margin-bottom: 12px; font-size: 13px; }
.card { background: #1a1a2e; padding: 12px; border-radius: 10px; border: 1px solid #2a2a4a; margin-bottom: 10px; overflow: hidden; }
.card h2 { color: #8888aa; font-size: 13px; font-weight: normal; margin-bottom: 8px; }
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; }
.stat-item { flex: 1; min-width: 80px; }
.stat-item .value { font-size: 20px; font-weight: bold; color: #667eea; }
.stat-item .label { color: #8888aa; font-size: 11px; }
.table-wrapper { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 500px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #2a2a4a; white-space: nowrap; }
th { color: #8888aa; font-weight: normal; font-size: 10px; text-transform: uppercase; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; }
.badge.win { background: rgba(56,239,125,0.15); color: #38ef7d; border: 1px solid rgba(56,239,125,0.2); }
.badge.loss { background: rgba(239,71,58,0.15); color: #ef473a; border: 1px solid rgba(239,71,58,0.2); }
.badge.push { background: rgba(255,210,0,0.15); color: #ffd200; border: 1px solid rgba(255,210,0,0.2); }
.no-data { text-align: center; color: #8888aa; padding: 20px 0; }

.bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #1a1a2e;
    border-top: 1px solid #2a2a4a;
    display: flex;
    justify-content: space-around;
    align-items: center;
    padding: 8px 0;
    z-index: 1000;
    backdrop-filter: blur(10px);
}
.bottom-nav .nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    color: #8888aa;
    font-size: 10px;
    transition: all 0.3s;
    padding: 4px 12px;
    border-radius: 8px;
    border: none;
    background: transparent;
    cursor: pointer;
    min-width: 60px;
    position: relative;
}
.bottom-nav .nav-item .icon { font-size: 22px; line-height: 1.2; }
.bottom-nav .nav-item .label { font-size: 9px; margin-top: 2px; font-weight: 500; }
.bottom-nav .nav-item.active { color: #667eea; }
.bottom-nav .nav-item.active::after {
    content: '';
    position: absolute;
    top: -1px;
    left: 50%;
    transform: translateX(-50%);
    width: 20px;
    height: 2px;
    background: #667eea;
    border-radius: 2px;
}
@media (max-width: 768px) {
    .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
    .bottom-nav .nav-item .icon { font-size: 18px; }
    .bottom-nav .nav-item .label { font-size: 8px; }
}
</style>
</head>
<body>
<div class="container">
    <h1>📈 Статистика</h1>
    <div class="subtitle">Детальный анализ ваших ставок</div>
    
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
                        <td style="font-size:10px;">{{ bet.date }}</td>
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

<div class="bottom-nav">
    <a href="/" class="nav-item"><span class="icon">📊</span><span class="label">Дашборд</span></a>
    <a href="/matches" class="nav-item"><span class="icon">⚽</span><span class="label">Матчи</span></a>
    <a href="/stats" class="nav-item active"><span class="icon">📈</span><span class="label">Статистика</span></a>
    <a href="/simulator" class="nav-item"><span class="icon">🎲</span><span class="label">Симулятор</span></a>
    <a href="/settings" class="nav-item"><span class="icon">⚙️</span><span class="label">Настройки</span></a>
</div>
</body>
</html>
"""

# ============================================================
# ШАБЛОН СИМУЛЯТОРА (С НИЖНЕЙ НАВИГАЦИЕЙ)
# ============================================================

SIMULATOR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Симулятор - Quantum Bet Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; padding-bottom: 80px; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #667eea; font-size: 22px; margin-bottom: 4px; }
        .subtitle { color: #8888aa; margin-bottom: 12px; font-size: 13px; }
        
        .card { background: #1a1a2e; padding: 14px; border-radius: 10px; border: 1px solid #2a2a4a; margin-bottom: 12px; }
        .card h2 { color: #8888aa; font-size: 13px; font-weight: normal; margin-bottom: 8px; }
        
        .sim-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
        .sim-stat { background: #0f0f1a; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #2a2a4a; }
        .sim-stat .value { font-size: 22px; font-weight: bold; }
        .sim-stat .value.green { color: #38ef7d; }
        .sim-stat .value.red { color: #ef473a; }
        .sim-stat .value.gold { color: #ffd200; }
        .sim-stat .label { color: #8888aa; font-size: 11px; margin-top: 4px; }
        
        .slider-container { margin: 14px 0; }
        .slider-container input[type="range"] { width: 100%; height: 6px; background: #2a2a4a; border-radius: 4px; outline: none; }
        .slider-container input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 18px; height: 18px; border-radius: 50%; background: #667eea; cursor: pointer; }
        .slider-labels { display: flex; justify-content: space-between; color: #8888aa; font-size: 11px; margin-top: 4px; }
        
        .chart-container { height: 160px; width: 100%; }
        .no-data { text-align: center; color: #8888aa; padding: 30px 0; }
        .no-data .emoji { font-size: 36px; margin-bottom: 6px; }
        
        .btn-primary { background: #667eea; color: white; border: none; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-size: 13px; }
        .btn-primary:hover { background: #764ba2; transform: scale(1.02); }
        .btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #2a2a4a; background: transparent; color: #8888aa; cursor: pointer; font-size: 12px; transition: all 0.3s; }
        .btn:hover { background: rgba(102,126,234,0.2); border-color: #667eea; color: #fff; }
        
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #1a1a2e;
            border-top: 1px solid #2a2a4a;
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 8px 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
        }
        .bottom-nav .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            color: #8888aa;
            font-size: 10px;
            transition: all 0.3s;
            padding: 4px 12px;
            border-radius: 8px;
            border: none;
            background: transparent;
            cursor: pointer;
            min-width: 60px;
            position: relative;
        }
        .bottom-nav .nav-item .icon { font-size: 22px; line-height: 1.2; }
        .bottom-nav .nav-item .label { font-size: 9px; margin-top: 2px; font-weight: 500; }
        .bottom-nav .nav-item.active { color: #667eea; }
        .bottom-nav .nav-item.active::after {
            content: '';
            position: absolute;
            top: -1px;
            left: 50%;
            transform: translateX(-50%);
            width: 20px;
            height: 2px;
            background: #667eea;
            border-radius: 2px;
        }
        @media (max-width: 768px) {
            .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
            .bottom-nav .nav-item .icon { font-size: 18px; }
            .bottom-nav .nav-item .label { font-size: 8px; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>🎲 Симулятор</h1>
    <div class="subtitle">Узнай, сколько ты мог бы заработать!</div>
    
    {% if history %}
    <div class="card">
        <h2>📊 Параметры симуляции</h2>
        
        <div class="slider-container">
            <label style="color:#8888aa;font-size:13px;">Количество симуляций: <span id="simCountLabel">{{ sim_count }}</span></label>
            <input type="range" id="simCount" min="100" max="5000" step="100" value="{{ sim_count }}" oninput="document.getElementById('simCountLabel').textContent=this.value">
        </div>
        
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn-primary" onclick="runSimulation()">🎲 Запустить</button>
            <button class="btn" onclick="location.reload()">🔄 Сбросить</button>
        </div>
    </div>
    
    <div id="simResults" style="display:none;">
        <div class="sim-stats" id="simStats">
            <div class="sim-stat">
                <div class="value gold" id="simProfit">$0</div>
                <div class="label">💰 Ожидаемая прибыль</div>
            </div>
            <div class="sim-stat">
                <div class="value green" id="simWinrate">0%</div>
                <div class="label">🎯 Проходимость</div>
            </div>
            <div class="sim-stat">
                <div class="value" id="simROI">0%</div>
                <div class="label">📈 ROI</div>
            </div>
            <div class="sim-stat">
                <div class="value red" id="simRisk">0%</div>
                <div class="label">⚠️ Риск</div>
            </div>
        </div>
        
        <div class="card">
            <h2>📈 График симуляции</h2>
            <div class="chart-container">
                <canvas id="simChart"></canvas>
            </div>
        </div>
        
        <div class="card">
            <h2>📋 Результаты</h2>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;" id="simDetails">
                <div style="color:#8888aa;">Всего: <span id="simTotal" style="color:#e0e0e0;">0</span></div>
                <div style="color:#8888aa;">Выигрышей: <span id="simWins" style="color:#38ef7d;">0</span></div>
                <div style="color:#8888aa;">Проигрышей: <span id="simLosses" style="color:#ef473a;">0</span></div>
                <div style="color:#8888aa;">Макс. прибыль: <span id="simMaxProfit" style="color:#ffd200;">$0</span></div>
                <div style="color:#8888aa;">Мин. прибыль: <span id="simMinProfit" style="color:#ef473a;">$0</span></div>
                <div style="color:#8888aa;">Средняя ставка: <span id="simAvgStake" style="color:#e0e0e0;">$0</span></div>
            </div>
        </div>
        
        <div class="card" style="background:rgba(102,126,234,0.05);border-color:#667eea;">
            <h2>💡 Рекомендация</h2>
            <div id="simRecommendation" style="font-size:14px;line-height:1.6;">
                Запустите симуляцию, чтобы получить рекомендацию!
            </div>
        </div>
    </div>
    {% else %}
    <div class="card">
        <div class="no-data">
            <div class="emoji">📭</div>
            <div>Нет данных для симуляции</div>
            <div style="font-size:12px;color:#444466;">Сначала сделайте хотя бы 5 ставок!</div>
        </div>
    </div>
    {% endif %}
    
    <div style="text-align:center;color:#444466;font-size:10px;margin-top:16px;">
        Quantum Bet Bot v12 PRO © 2026
    </div>
</div>

<div class="bottom-nav">
    <a href="/" class="nav-item"><span class="icon">📊</span><span class="label">Дашборд</span></a>
    <a href="/matches" class="nav-item"><span class="icon">⚽</span><span class="label">Матчи</span></a>
    <a href="/stats" class="nav-item"><span class="icon">📈</span><span class="label">Статистика</span></a>
    <a href="/simulator" class="nav-item active"><span class="icon">🎲</span><span class="label">Симулятор</span></a>
    <a href="/settings" class="nav-item"><span class="icon">⚙️</span><span class="label">Настройки</span></a>
</div>

<script>
function runSimulation() {
    const count = document.getElementById('simCount').value;
    
    fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: parseInt(count) })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('❌ Ошибка: ' + data.error);
            return;
        }
        
        document.getElementById('simResults').style.display = 'block';
        
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
            rec.innerHTML = '✅ <b style="color:#38ef7d;">Отличный результат!</b> Ваша стратегия принесла бы прибыль!<br>' +
                '💡 Средняя прибыль на ставку: $' + (data.profit / data.total).toFixed(2) + '<br>' +
                '🔥 Лучший результат: +$' + data.max_profit;
        } else {
            rec.innerHTML = '⚠️ <b style="color:#ef473a;">Стратегия требует улучшения</b><br>' +
                '💡 Попробуйте снизить сумму ставок<br>' +
                '📊 Работайте над проходимостью (сейчас ' + data.winrate + '%)';
        }
        
        const ctx = document.getElementById('simChart').getContext('2d');
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels || Array.from({length: data.history.length}, (_, i) => i + 1),
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
                plugins: {
                    legend: {
                        labels: {
                            color: isDark ? '#e0e0e0' : '#1a1a2e',
                            font: { size: 9 }
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 8 } } },
                    y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: function(value) { return '$' + value; }, font: { size: 8 } } }
                }
            }
        });
        
        document.getElementById('simResults').scrollIntoView({ behavior: 'smooth' });
    })
    .catch(error => alert('❌ Ошибка: ' + error));
}
</script>
</body>
</html>
"""

# ============================================================
# ШАБЛОН НАСТРОЕК (С НИЖНЕЙ НАВИГАЦИЕЙ И ИМПОРТОМ)
# ============================================================

SETTINGS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Настройки</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 15px; padding-bottom: 80px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #667eea; font-size: 22px; margin-bottom: 4px; }
.subtitle { color: #8888aa; margin-bottom: 12px; font-size: 13px; }
.setting-group { background: #1a1a2e; padding: 12px; border-radius: 10px; border: 1px solid #2a2a4a; margin-bottom: 10px; }
.setting-group h2 { color: #8888aa; font-size: 13px; font-weight: normal; margin-bottom: 8px; }
.setting-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #0f0f1a; flex-wrap: wrap; gap: 6px; }
.setting-item:last-child { border-bottom: none; }
.setting-item .label { color: #e0e0e0; font-size: 13px; }
.setting-item .desc { color: #666688; font-size: 11px; }
.input-group { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.input-group input { background: #0f0f1a; border: 1px solid #2a2a4a; color: #e0e0e0; padding: 5px 8px; border-radius: 4px; width: 100px; font-size: 12px; }
.input-group button { background: #667eea; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.input-group button:hover { background: #764ba2; }
.btn { padding: 5px 12px; border-radius: 4px; border: 1px solid #2a2a4a; background: transparent; color: #8888aa; cursor: pointer; font-size: 12px; transition: all 0.3s; }
.btn:hover { background: rgba(102,126,234,0.2); border-color: #667eea; color: #fff; }
.toggle { width: 40px; height: 22px; background: #2a2a4a; border-radius: 12px; cursor: pointer; position: relative; transition: 0.3s; }
.toggle.active { background: #667eea; }
.toggle .dot { width: 16px; height: 16px; background: white; border-radius: 50%; position: absolute; top: 3px; left: 3px; transition: 0.3s; }
.toggle.active .dot { left: 21px; }
.file-input-label { display: inline-block; padding: 5px 12px; background: #667eea; color: white; border-radius: 4px; cursor: pointer; font-size: 12px; }
.file-input-label:hover { background: #764ba2; }
.import-status { color: #8888aa; font-size: 11px; margin-top: 4px; }

.bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #1a1a2e;
    border-top: 1px solid #2a2a4a;
    display: flex;
    justify-content: space-around;
    align-items: center;
    padding: 8px 0;
    z-index: 1000;
    backdrop-filter: blur(10px);
}
.bottom-nav .nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    color: #8888aa;
    font-size: 10px;
    transition: all 0.3s;
    padding: 4px 12px;
    border-radius: 8px;
    border: none;
    background: transparent;
    cursor: pointer;
    min-width: 60px;
    position: relative;
}
.bottom-nav .nav-item .icon { font-size: 22px; line-height: 1.2; }
.bottom-nav .nav-item .label { font-size: 9px; margin-top: 2px; font-weight: 500; }
.bottom-nav .nav-item.active { color: #667eea; }
.bottom-nav .nav-item.active::after {
    content: '';
    position: absolute;
    top: -1px;
    left: 50%;
    transform: translateX(-50%);
    width: 20px;
    height: 2px;
    background: #667eea;
    border-radius: 2px;
}
@media (max-width: 768px) {
    .bottom-nav .nav-item { padding: 2px 8px; min-width: 50px; }
    .bottom-nav .nav-item .icon { font-size: 18px; }
    .bottom-nav .nav-item .label { font-size: 8px; }
}
</style>
</head>
<body>
<div class="container">
    <h1>⚙️ Настройки</h1>
    <div class="subtitle">Управление ботом</div>
    
    <!-- Банк -->
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
    
    <!-- Автоматизация -->
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
    
    <!-- Экспорт / Импорт -->
    <div class="setting-group">
        <h2>📊 Экспорт / Импорт</h2>
        
        <!-- Экспорт -->
        <div class="setting-item">
            <div>
                <div class="label">Экспорт данных</div>
                <div class="desc">Скачать историю в Excel</div>
            </div>
            <button class="btn" onclick="window.location.href='/export'">📥 Скачать</button>
        </div>
        
        <!-- Импорт -->
        <div class="setting-item" style="border-bottom: none;">
            <div>
                <div class="label">Импорт данных</div>
                <div class="desc">Загрузить историю из Excel</div>
            </div>
            <div class="input-group">
                <label class="file-input-label" for="importFileInput">📤 Выбрать файл</label>
                <input type="file" id="importFileInput" accept=".xlsx,.csv" style="display:none" onchange="importExcel(event)">
                <span id="fileName" style="color:#666688;font-size:11px;">Файл не выбран</span>
            </div>
        </div>
        <div id="importStatus" class="import-status"></div>
    </div>
</div>

<div class="bottom-nav">
    <a href="/" class="nav-item"><span class="icon">📊</span><span class="label">Дашборд</span></a>
    <a href="/matches" class="nav-item"><span class="icon">⚽</span><span class="label">Матчи</span></a>
    <a href="/stats" class="nav-item"><span class="icon">📈</span><span class="label">Статистика</span></a>
    <a href="/simulator" class="nav-item"><span class="icon">🎲</span><span class="label">Симулятор</span></a>
    <a href="/settings" class="nav-item active"><span class="icon">⚙️</span><span class="label">Настройки</span></a>
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

function importExcel(event) {
    const file = event.target.files[0];
    const statusDiv = document.getElementById('importStatus');
    const fileNameSpan = document.getElementById('fileName');
    
    if (!file) {
        statusDiv.textContent = '❌ Файл не выбран';
        return;
    }
    
    fileNameSpan.textContent = '📄 ' + file.name;
    statusDiv.textContent = '⏳ Загрузка файла...';
    
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, {type: 'array'});
            const sheet = workbook.Sheets[workbook.SheetNames[0]];
            const json = XLSX.utils.sheet_to_json(sheet);
            
            if (json.length === 0) {
                statusDiv.textContent = '❌ Файл пуст или неправильный формат';
                return;
            }
            
            statusDiv.textContent = '⏳ Отправка данных на сервер...';
            
            fetch('/api/import_excel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: json })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    statusDiv.textContent = '✅ Импортировано ' + data.count + ' ставок! Страница обновится...';
                    setTimeout(() => location.reload(), 1500);
                } else {
                    statusDiv.textContent = '❌ Ошибка: ' + data.error;
                }
            })
            .catch(error => {
                statusDiv.textContent = '❌ Ошибка: ' + error;
            });
        } catch (error) {
            statusDiv.textContent = '❌ Ошибка чтения файла: ' + error;
        }
    };
    reader.readAsArrayBuffer(file);
}

document.getElementById('importFileInput').addEventListener('change', function() {
    if (this.files.length > 0) {
        document.getElementById('fileName').textContent = '📄 ' + this.files[0].name;
    }
});
</script>
</body>
</html>
"""

# ============================================================
# ОСТАЛЬНОЙ КОД (ФУНКЦИИ И МАРШРУТЫ) - БЕЗ ИЗМЕНЕНИЙ
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

@app.route('/simulator')
def simulator_page():
    stats_data, history = get_data_from_bot()
    sim_count = 1000
    return render_template_string(SIMULATOR_HTML, history=history, sim_count=sim_count)

@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        count = data.get('count', 1000)
        
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = response.json() if response.status_code == 200 else []
        
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок для симуляции'}), 400
        
        wins = sum(1 for b in history if b.get('result') == 'win')
        losses = sum(1 for b in history if b.get('result') == 'loss')
        total = len(history)
        winrate = wins / total if total > 0 else 0
        
        avg_stake = sum(float(b.get('stake', 0)) for b in history) / total if total > 0 else 10
        
        results = []
        profit_history = []
        total_profit = 0
        
        for i in range(count):
            if random.random() < winrate:
                profit = avg_stake * random.uniform(0.5, 1.5)
                total_profit += profit
                results.append('win')
            else:
                profit = -avg_stake
                total_profit += profit
                results.append('loss')
            
            profit_history.append(round(total_profit, 2))
        
        wins_sim = results.count('win')
        losses_sim = results.count('loss')
        max_profit = max(profit_history) if profit_history else 0
        min_profit = min(profit_history) if profit_history else 0
        
        return jsonify({
            'total': count,
            'wins': wins_sim,
            'losses': losses_sim,
            'profit': round(total_profit, 2),
            'winrate': round(wins_sim / count * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'risk': round((abs(min_profit) / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'max_profit': round(max_profit, 2),
            'min_profit': round(min_profit, 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
                    stake = bet.get('stake', 0)
                    if isinstance(stake, str):
                        try:
                            stake = float(stake)
                        except:
                            stake = 0
                    odds = bet.get('odds', 1)
                    if isinstance(odds, str):
                        try:
                            odds = float(odds)
                        except:
                            odds = 1
                    
                    if bet.get('result') == 'win':
                        day_profit += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= stake
            except:
                pass
        profits.append(round(day_profit, 2))
    
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    
    return jsonify({'dates': dates, 'profits': profits})

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        excel_data = data.get('data', [])
        
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = response.json() if response.status_code == 200 else []
        
        imported = 0
        for row in excel_data:
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
            
            bet = row.get('Ставка', '') or row.get('Stanka', '') or 'Ручная ставка'
            
            odds = 1.85
            try:
                odds = float(row.get('Коэф', 1.85) or row.get('Kofy', 1.85) or 1.85)
            except:
                odds = 1.85
            
            stake = 0
            try:
                stake = float(row.get('Сумма', 0) or row.get('Stake', 0) or 0)
            except:
                stake = 0
            
            ev = 0
            try:
                ev = float(row.get('EV%', 0) or row.get('Ev', 0) or 0)
            except:
                ev = 0
            
            result = row.get('Результат', 'pending') or row.get('Result', 'pending')
            if result.lower() in ['win', 'выигрыш']:
                result = 'win'
            elif result.lower() in ['loss', 'проигрыш']:
                result = 'loss'
            elif result.lower() in ['push', 'возврат']:
                result = 'push'
            else:
                result = 'pending'
            
            profit = 0
            try:
                profit = float(row.get('Прибыль', 0) or row.get('Profit', 0) or 0)
            except:
                profit = 0
            
            date = row.get('Дата', '') or row.get('Data', '') or datetime.now().strftime('%Y-%m-%d %H:%M')
            if not date or date == '':
                date = datetime.now().strftime('%Y-%m-%d %H:%M')
            
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
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'count': imported})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
