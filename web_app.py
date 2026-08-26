import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request, send_file
import requests
from datetime import datetime, timedelta
import json
import random
import io
import xlsxwriter

app = Flask(__name__)

# URL бота
BOT_URL = 'https://quantumbet-bot-pro.onrender.com'
DIARY_FILE = 'diary.json'

# ============================================================
# РАБОТА С ДНЕВНИКОМ
# ============================================================

def load_diary():
    if os.path.exists(DIARY_FILE):
        try:
            with open(DIARY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_diary(entries):
    with open(DIARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

# ============================================================
# ЕДИНЫЙ HTML ШАБЛОН
# ============================================================

MAIN_HTML = """
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
            padding-bottom: 75px;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 12px; }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 14px;
            padding: 12px 16px;
            background: var(--bg-secondary);
            border-radius: 14px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 20px var(--shadow);
        }
        .header h1 {
            font-size: 18px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header-controls {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }
        .status {
            display: flex;
            align-items: center;
            gap: 5px;
            color: #38ef7d;
            font-size: 10px;
        }
        .status-dot {
            width: 7px;
            height: 7px;
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
            width: 30px;
            height: 30px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--text-primary);
        }
        .theme-toggle:hover { transform: scale(1.1); border-color: var(--gradient-start); }
        
        /* ===== СТРАНИЦЫ ===== */
        .page {
            display: none;
            animation: fadeIn 0.15s ease;
        }
        .page.active {
            display: block;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* ===== СТАТИСТИКА ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 8px;
            margin-bottom: 12px;
        }
        .stat-card {
            padding: 10px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--bg-secondary);
            text-align: center;
            box-shadow: 0 2px 8px var(--shadow);
        }
        .stat-card .value {
            font-size: 18px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.green { background: linear-gradient(135deg, #11998e, #38ef7d); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.red { background: linear-gradient(135deg, #cb2d3e, #ef473a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.gold { background: linear-gradient(135deg, #f7971e, #ffd200); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .label { color: var(--text-secondary); font-size: 10px; margin-top: 2px; }
        
        /* НОВЫЙ БЛОК МЕТРИК — 2 СТРОКИ ПО 2 */
        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 12px;
        }
        .metrics-grid .metric-item {
            background: var(--bg-secondary);
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 8px var(--shadow);
        }
        .metrics-grid .metric-item .label {
            color: var(--text-secondary);
            font-size: 12px;
        }
        .metrics-grid .metric-item .value {
            font-size: 18px;
            font-weight: bold;
            color: var(--text-primary);
        }
        .metrics-grid .metric-item .value.green { color: #38ef7d; }
        .metrics-grid .metric-item .value.gold { color: #ffd200; }
        
        .card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
            box-shadow: 0 2px 8px var(--shadow);
            overflow: hidden;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 8px;
        }
        .card-header h2 { color: var(--text-secondary); font-size: 13px; font-weight: normal; }
        .card-header .count { color: var(--text-secondary); font-size: 11px; }
        
        .chart-container {
            position: relative;
            height: 140px;
            width: 100%;
        }
        .chart-container-half {
            position: relative;
            height: 140px;
            width: 100%;
        }
        
        .table-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11px;
            min-width: 600px;
        }
        th, td {
            padding: 5px 6px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th { 
            color: var(--text-secondary); 
            font-weight: 600; 
            font-size: 9px; 
            text-transform: uppercase; 
            letter-spacing: 0.3px;
            background: var(--bg-card);
            position: sticky;
            top: 0;
        }
        tr:hover td { background: var(--bg-card); }
        
        .badge {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 8px;
            font-size: 9px;
            font-weight: bold;
        }
        .badge.win { background: rgba(56,239,125,0.15); color: #38ef7d; border: 1px solid rgba(56,239,125,0.2); }
        .badge.loss { background: rgba(239,71,58,0.15); color: #ef473a; border: 1px solid rgba(239,71,58,0.2); }
        .badge.push { background: rgba(255,210,0,0.15); color: #ffd200; border: 1px solid rgba(255,210,0,0.2); }
        .badge.pending { background: rgba(255,255,255,0.05); color: #8888aa; border: 1px solid var(--border-color); }
        
        .profit-positive { color: #38ef7d; font-weight: bold; }
        .profit-negative { color: #ef473a; font-weight: bold; }
        
        .no-data { text-align: center; color: var(--text-secondary); padding: 16px 0; }
        .no-data .emoji { font-size: 30px; margin-bottom: 4px; }
        
        .summary-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 8px;
            margin-bottom: 10px;
        }
        .summary-item {
            background: var(--bg-card);
            padding: 8px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
        }
        .summary-item .label { color: var(--text-secondary); font-size: 10px; }
        .summary-item .value { font-size: 14px; font-weight: bold; }
        
        .scrollable-table {
            max-height: 350px;
            overflow-y: auto;
        }
        
        .footer {
            text-align: center;
            color: #444466;
            font-size: 9px;
            margin-top: 12px;
            padding: 8px 0;
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
            padding: 6px 0;
            z-index: 1000;
            box-shadow: 0 -4px 20px rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }
        .bottom-nav .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            color: var(--text-secondary);
            font-size: 9px;
            transition: all 0.15s;
            padding: 4px 10px;
            border-radius: 6px;
            border: none;
            background: transparent;
            cursor: pointer;
            min-width: 50px;
            position: relative;
            -webkit-tap-highlight-color: transparent;
            user-select: none;
        }
        .bottom-nav .nav-item .icon {
            font-size: 20px;
            line-height: 1.1;
            transition: all 0.15s;
        }
        .bottom-nav .nav-item .label {
            font-size: 8px;
            margin-top: 1px;
            font-weight: 500;
        }
        .bottom-nav .nav-item.active {
            color: var(--nav-active);
        }
        .bottom-nav .nav-item.active .icon {
            transform: scale(1.05);
        }
        .bottom-nav .nav-item.active::after {
            content: '';
            position: absolute;
            top: -1px;
            left: 50%;
            transform: translateX(-50%);
            width: 16px;
            height: 2px;
            background: var(--nav-active);
            border-radius: 2px;
        }
        .bottom-nav .nav-item:active {
            transform: scale(0.92);
        }
        
        /* ===== МАТЧИ ===== */
        .match-tabs {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }
        .match-tab {
            padding: 4px 12px;
            border-radius: 14px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.15s;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-secondary);
        }
        .match-tab.active {
            background: var(--gradient-start);
            color: #fff;
            border-color: var(--gradient-start);
        }
        .match-tab:active { transform: scale(0.95); }
        
        .match-card {
            background: var(--bg-secondary);
            padding: 10px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            margin-bottom: 8px;
            overflow: hidden;
        }
        .match-title { font-size: 13px; font-weight: bold; }
        .match-league { color: var(--text-secondary); font-size: 11px; }
        .match-xg { color: var(--gradient-start); font-size: 11px; }
        .match-bets { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 3px; }
        .bet-item {
            background: var(--bg-card);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            border: 1px solid var(--border-color);
        }
        
        /* ===== НАСТРОЙКИ ===== */
        .setting-group {
            background: var(--bg-secondary);
            padding: 10px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            margin-bottom: 8px;
        }
        .setting-group h2 {
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: normal;
            margin-bottom: 6px;
        }
        .setting-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px 0;
            border-bottom: 1px solid var(--bg-primary);
            flex-wrap: wrap;
            gap: 4px;
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-item .label { font-size: 12px; }
        .setting-item .desc { color: var(--text-secondary); font-size: 10px; }
        .input-group { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
        .input-group input {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 4px 6px;
            border-radius: 4px;
            width: 80px;
            font-size: 11px;
        }
        .input-group button {
            background: var(--gradient-start);
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
        }
        .input-group button:active { transform: scale(0.95); }
        .btn {
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 11px;
            transition: all 0.15s;
        }
        .btn:active { transform: scale(0.95); }
        .btn:hover { background: rgba(102,126,234,0.15); border-color: var(--gradient-start); color: var(--text-primary); }
        .btn-success {
            background: #38ef7d;
            color: #000;
            border-color: #38ef7d;
        }
        .btn-success:hover {
            background: #11998e;
            border-color: #11998e;
            color: #fff;
        }
        .btn-danger {
            background: #ef473a;
            color: #fff;
            border-color: #ef473a;
        }
        .btn-danger:hover {
            background: #cb2d3e;
            border-color: #cb2d3e;
        }
        .toggle {
            width: 36px;
            height: 20px;
            background: var(--input-border);
            border-radius: 10px;
            cursor: pointer;
            position: relative;
            transition: 0.2s;
        }
        .toggle.active { background: var(--gradient-start); }
        .toggle .dot {
            width: 14px;
            height: 14px;
            background: white;
            border-radius: 50%;
            position: absolute;
            top: 3px;
            left: 3px;
            transition: 0.2s;
        }
        .toggle.active .dot { left: 19px; }
        .file-input-label {
            display: inline-block;
            padding: 4px 10px;
            background: var(--gradient-start);
            color: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
        }
        .file-input-label:active { transform: scale(0.95); }
        .import-status { color: var(--text-secondary); font-size: 10px; margin-top: 3px; }
        
        /* ===== СИМУЛЯТОР ===== */
        .sim-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
            margin-bottom: 10px;
        }
        .sim-stat {
            background: var(--bg-card);
            padding: 10px;
            border-radius: 6px;
            text-align: center;
            border: 1px solid var(--border-color);
        }
        .sim-stat .value { font-size: 18px; font-weight: bold; }
        .sim-stat .value.green { color: #38ef7d; }
        .sim-stat .value.red { color: #ef473a; }
        .sim-stat .value.gold { color: #ffd200; }
        .sim-stat .label { color: var(--text-secondary); font-size: 10px; margin-top: 2px; }
        
        .slider-container { margin: 10px 0; }
        .slider-container input[type="range"] {
            width: 100%;
            height: 4px;
            background: var(--input-border);
            border-radius: 2px;
            outline: none;
            -webkit-appearance: none;
        }
        .slider-container input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--gradient-start);
            cursor: pointer;
        }
        .slider-container input[type="range"]::-moz-range-thumb {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--gradient-start);
            cursor: pointer;
            border: none;
        }
        .btn-primary {
            background: var(--gradient-start);
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .btn-primary:active { transform: scale(0.95); }
        
        /* ===== ДНЕВНИК ===== */
        .diary-entry {
            background: var(--bg-card);
            padding: 10px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            margin-bottom: 6px;
        }
        .diary-entry .date {
            color: var(--text-secondary);
            font-size: 10px;
        }
        .diary-entry .text {
            font-size: 13px;
            margin-top: 4px;
        }
        .diary-entry .delete-btn {
            float: right;
            background: none;
            border: none;
            color: #ef473a;
            cursor: pointer;
            font-size: 14px;
        }
        .diary-entry .delete-btn:hover { color: #cb2d3e; }
        .diary-textarea {
            width: 100%;
            padding: 8px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-primary);
            resize: vertical;
            min-height: 80px;
            font-family: inherit;
            font-size: 13px;
        }
        .diary-textarea:focus {
            outline: none;
            border-color: var(--gradient-start);
        }
        
        /* ===== LOADER ===== */
        .loader {
            display: none;
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
        }
        .loader.active { display: block; }
        .loader .spinner {
            width: 30px;
            height: 30px;
            border: 3px solid var(--border-color);
            border-top: 3px solid var(--gradient-start);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 8px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .charts-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: stretch; gap: 6px; padding: 10px 14px; }
            .header h1 { font-size: 16px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .metrics-grid { grid-template-columns: 1fr 1fr; gap: 4px; }
            .metrics-grid .metric-item { padding: 6px 10px; }
            .metrics-grid .metric-item .value { font-size: 14px; }
            .summary-row { grid-template-columns: 1fr; }
            .card { padding: 8px; }
            table { font-size: 9px; min-width: 450px; }
            th, td { padding: 3px 4px; }
            .chart-container { height: 100px; }
            .bottom-nav .nav-item { padding: 2px 6px; min-width: 44px; }
            .bottom-nav .nav-item .icon { font-size: 16px; }
            .bottom-nav .nav-item .label { font-size: 7px; }
            .charts-row { grid-template-columns: 1fr; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 4px; }
            .stat-card { padding: 6px; }
            .stat-card .value { font-size: 14px; }
            .metrics-grid { grid-template-columns: 1fr; }
            .bottom-nav .nav-item { min-width: 40px; padding: 2px 4px; }
            .bottom-nav .nav-item .icon { font-size: 14px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
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
                <button class="theme-toggle" onclick="refreshData()" style="font-size:12px;">🔄</button>
            </div>
        </div>
        
        <!-- ===== СТРАНИЦЫ ===== -->
        <div id="page-dashboard" class="page active">
            <div id="dashboard-content"></div>
        </div>
        
        <div id="page-matches" class="page">
            <div id="matches-content"></div>
        </div>
        
        <div id="page-diary" class="page">
            <div id="diary-content"></div>
        </div>
        
        <div id="page-simulator" class="page">
            <div id="simulator-content"></div>
        </div>
        
        <div id="page-settings" class="page">
            <div id="settings-content"></div>
        </div>
        
        <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
    </div>
    
    <!-- ===== НИЖНЯЯ НАВИГАЦИЯ ===== -->
    <div class="bottom-nav">
        <button class="nav-item active" data-page="dashboard">
            <span class="icon">📊</span>
            <span class="label">Дашборд</span>
        </button>
        <button class="nav-item" data-page="matches">
            <span class="icon">⚽</span>
            <span class="label">Матчи</span>
        </button>
        <button class="nav-item" data-page="diary">
            <span class="icon">📖</span>
            <span class="label">Дневник</span>
        </button>
        <button class="nav-item" data-page="simulator">
            <span class="icon">🎲</span>
            <span class="label">Симулятор</span>
        </button>
        <button class="nav-item" data-page="settings">
            <span class="icon">⚙️</span>
            <span class="label">Настройки</span>
        </button>
    </div>
    
    <script>
        // ===== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====
        let cachedData = null;
        let chartInstance = null;
        let chartWeekday = null;
        let simChartInstance = null;
        let currentPage = 'dashboard';
        let isLoading = false;
        
        // ===== ТЕМА =====
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
        
        // ===== НАВИГАЦИЯ =====
        document.querySelectorAll('.bottom-nav .nav-item').forEach(btn => {
            btn.addEventListener('click', function(e) {
                const page = this.dataset.page;
                switchPage(page);
            });
        });
        
        function switchPage(page) {
            if (page === currentPage) return;
            document.querySelectorAll('.bottom-nav .nav-item').forEach(b => b.classList.remove('active'));
            document.querySelector(`.bottom-nav .nav-item[data-page="${page}"]`).classList.add('active');
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.getElementById('page-' + page).classList.add('active');
            currentPage = page;
            
            if (page === 'diary') {
                loadDiary();
            } else {
                loadPageData(page);
            }
        }
        
        // ===== ЗАГРУЗКА ДАННЫХ =====
        async function loadPageData(page) {
            if (isLoading) return;
            const contentId = page + '-content';
            const contentEl = document.getElementById(contentId);
            contentEl.innerHTML = '<div class="loader active"><div class="spinner"></div><div style="color:var(--text-secondary);font-size:12px;margin-top:6px;">Загрузка...</div></div>';
            isLoading = true;
            try {
                const response = await fetch('/api/all_data?t=' + Date.now());
                const data = await response.json();
                cachedData = data;
                switch(page) {
                    case 'dashboard': renderDashboard(data); break;
                    case 'matches': renderMatches(data); break;
                    case 'simulator': renderSimulator(data); break;
                    case 'settings': renderSettings(data); break;
                }
            } catch (error) {
                contentEl.innerHTML = '<div class="no-data"><div class="emoji">⚠️</div>Ошибка загрузки</div>';
            }
            isLoading = false;
        }
        
        function refreshData() {
            cachedData = null;
            loadPageData(currentPage);
        }
        
        // ===== ДНЕВНИК =====
        async function loadDiary() {
            const el = document.getElementById('diary-content');
            try {
                const response = await fetch('/api/diary');
                const entries = await response.json();
                renderDiary(entries);
            } catch (e) {
                el.innerHTML = '<div class="no-data"><div class="emoji">📭</div>Ошибка загрузки дневника</div>';
            }
        }
        
        function renderDiary(entries) {
            const el = document.getElementById('diary-content');
            let html = `
                <h2 style="font-size:18px;color:var(--gradient-start);margin-bottom:4px;">📖 Дневник</h2>
                <div style="color:var(--text-secondary);font-size:12px;margin-bottom:10px;">Записывай свои мысли, идеи и заметки по ставкам</div>
                
                <div class="card">
                    <h2 style="color:var(--text-secondary);font-size:12px;font-weight:normal;margin-bottom:6px;">✏️ Новая запись</h2>
                    <textarea id="diaryInput" class="diary-textarea" placeholder="Напиши свою заметку..."></textarea>
                    <button class="btn btn-success" onclick="saveDiaryEntry()" style="margin-top:6px;padding:6px 16px;">💾 Сохранить</button>
                </div>
                
                <div class="card">
                    <h2 style="color:var(--text-secondary);font-size:12px;font-weight:normal;margin-bottom:6px;">📚 Все записи (${entries.length})</h2>
                    <div id="diaryEntries">
            `;
            
            if (entries.length === 0) {
                html += `<div class="no-data"><div class="emoji">📭</div>Нет записей</div>`;
            } else {
                entries.slice().reverse().forEach(entry => {
                    html += `
                        <div class="diary-entry">
                            <span class="date">${entry.date}</span>
                            <button class="delete-btn" onclick="deleteDiaryEntry(${entry.id})">🗑️</button>
                            <div class="text">${entry.text.replace(/\n/g, '<br>')}</div>
                        </div>
                    `;
                });
            }
            
            html += `</div></div>`;
            el.innerHTML = html;
        }
        
        async function saveDiaryEntry() {
            const text = document.getElementById('diaryInput').value.trim();
            if (!text) { alert('Напиши что-нибудь!'); return; }
            
            try {
                const response = await fetch('/api/diary', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text })
                });
                const data = await response.json();
                if (data.success) {
                    document.getElementById('diaryInput').value = '';
                    loadDiary();
                }
            } catch (e) {
                alert('Ошибка сохранения');
            }
        }
        
        async function deleteDiaryEntry(id) {
            if (!confirm('Удалить эту запись?')) return;
            try {
                const response = await fetch('/api/diary/' + id, { method: 'DELETE' });
                const data = await response.json();
                if (data.success) {
                    loadDiary();
                }
            } catch (e) {
                alert('Ошибка удаления');
            }
        }
        
        // ===== РЕНДЕР ДАШБОРДА =====
        function renderDashboard(data) {
            const s = data.stats;
            const history = data.history || [];
            const profitData = data.profit_data || { dates: [], profits: [] };
            
            let html = `
                <div class="stats-grid">
                    <div class="stat-card"><div class="value">$${s.bank}</div><div class="label">💰 Текущий банк</div></div>
                    <div class="stat-card"><div class="value green">${s.wins}</div><div class="label">✅ Выигрыши</div></div>
                    <div class="stat-card"><div class="value red">${s.losses}</div><div class="label">❌ Проигрыши</div></div>
                    <div class="stat-card"><div class="value gold">$${s.profit}</div><div class="label">💰 Прибыль</div></div>
                </div>
                
                <div class="metrics-grid">
                    <div class="metric-item"><span class="label">📊 Всего ставок</span><span class="value">${s.total_bets}</span></div>
                    <div class="metric-item"><span class="label">🎯 Проходимость</span><span class="value green">${s.winrate}%</span></div>
                    <div class="metric-item"><span class="label">📈 ROI</span><span class="value gold">${s.roi}%</span></div>
                    <div class="metric-item"><span class="label">📅 Средняя ставка</span><span class="value">$${s.avg_stake}</span></div>
                </div>
                
                <div class="charts-row">
                    <div class="card">
                        <div class="card-header"><h2>📈 График прибыли</h2><span style="font-size:9px;color:var(--text-secondary);">За 7 дней</span></div>
                        <div class="chart-container"><canvas id="profitChart"></canvas></div>
                    </div>
                    <div class="card">
                        <div class="card-header"><h2>📊 По дням недели</h2><span style="font-size:9px;color:var(--text-secondary);">Средняя прибыль</span></div>
                        <div class="chart-container"><canvas id="weekdayChart"></canvas></div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <h2>📋 Все ставки</h2>
                        <span class="count">Всего: ${history.length}</span>
                    </div>
                    <div class="table-wrapper">
                        <table>
                            <thead><tr><th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead>
                            <tbody>
            `;
            
            if (history.length === 0) {
                html += `<tr><td colspan="10" class="no-data"><div class="emoji">📭</div>Нет данных</td></tr>`;
            } else {
                history.slice().reverse().forEach((bet, idx) => {
                    const profitClass = bet.profit > 0 ? 'profit-positive' : (bet.profit < 0 ? 'profit-negative' : '');
                    html += `<tr>
                        <td>${idx + 1}</td>
                        <td style="font-size:9px;white-space:nowrap;">${bet.date}</td>
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
            
            html += `</tbody></table>
                    </div>
                    <div style="margin-top:10px;">
                        <button class="btn btn-success" onclick="exportToExcel()" style="padding:6px 16px;">📥 Сохранить в Excel</button>
                    </div>
                </div>
            `;
            
            document.getElementById('dashboard-content').innerHTML = html;
            
            setTimeout(() => {
                renderCharts(profitData, history);
            }, 100);
        }
        
        // ===== ГРАФИКИ =====
        function renderCharts(profitData, history) {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textColor = isDark ? '#e0e0e0' : '#1a1a2e';
            
            // График прибыли
            const ctx1 = document.getElementById('profitChart');
            if (ctx1) {
                if (chartInstance) { chartInstance.destroy(); }
                const labels = profitData.dates || ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
                const profits = profitData.profits || [0,0,0,0,0,0,0];
                chartInstance = new Chart(ctx1, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Прибыль ($)',
                            data: profits,
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
                        plugins: { legend: { labels: { color: textColor, font: { size: 9 } } } },
                        scales: {
                            x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 8 } } },
                            y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: v => '$' + v, font: { size: 8 } } }
                        }
                    }
                });
            }
            
            // График по дням недели
            const ctx2 = document.getElementById('weekdayChart');
            if (ctx2) {
                if (chartWeekday) { chartWeekday.destroy(); }
                const weekdayData = getWeekdayData(history);
                chartWeekday = new Chart(ctx2, {
                    type: 'bar',
                    data: {
                        labels: ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],
                        datasets: [{
                            label: 'Средняя прибыль ($)',
                            data: weekdayData,
                            backgroundColor: ['#667eea', '#764ba2', '#38ef7d', '#ffd200', '#ef473a', '#667eea', '#764ba2'],
                            borderRadius: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { labels: { color: textColor, font: { size: 9 } } } },
                        scales: {
                            x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 8 } } },
                            y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: v => '$' + v, font: { size: 8 } } }
                        }
                    }
                });
            }
        }
        
        function getWeekdayData(history) {
            const days = [0,0,0,0,0,0,0];
            const counts = [0,0,0,0,0,0,0];
            history.forEach(bet => {
                try {
                    const date = new Date(bet.date);
                    const day = date.getDay();
                    const idx = day === 0 ? 6 : day - 1;
                    days[idx] += bet.profit || 0;
                    counts[idx] += 1;
                } catch(e) {}
            });
            return days.map((sum, i) => counts[i] > 0 ? Math.round((sum / counts[i]) * 100) / 100 : 0);
        }
        
        // ===== ЭКСПОРТ В EXCEL =====
        function exportToExcel() {
            window.location.href = '/api/export_excel';
        }
        
        // ===== РЕНДЕР ОСТАЛЬНЫХ СТРАНИЦ =====
        function renderMatches(data) {
            const matches = data.matches || [];
            let html = `
                <h2 style="font-size:18px;color:var(--gradient-start);margin-bottom:4px;">⚽ Матчи</h2>
                <div style="color:var(--text-secondary);font-size:12px;margin-bottom:10px;">Прогнозы и валуйные ставки</div>
                <div class="match-tabs">
                    <span class="match-tab active">Все игры</span>
                    <span class="match-tab">LIVE</span>
                    <span class="match-tab">⭐ Избранное</span>
                    <span class="match-tab">🏆 Турниры</span>
                </div>
            `;
            if (matches.length === 0) {
                html += `<div class="no-data"><div class="emoji">📭</div>Матчей не найдено</div>`;
            } else {
                matches.forEach(m => {
                    html += `
                        <div class="match-card">
                            <div class="match-title">${m.home} vs ${m.away}</div>
                            <div class="match-league">🏆 ${m.league} | ⏰ ${m.match_time}</div>
                            <div class="match-xg">📊 xG: ${m.home_xg} : ${m.away_xg}</div>
                            <div class="match-bets">
                                ${(m.bets || []).slice(0, 3).map(b => 
                                    `<span class="bet-item">${b.label} | КЭФ: ${b.odds} | EV: ${b.ev}%</span>`
                                ).join('')}
                            </div>
                        </div>
                    `;
                });
            }
            document.getElementById('matches-content').innerHTML = html;
        }
        
        function renderSimulator(data) {
            const history = data.history || [];
            let html = `
                <h2 style="font-size:18px;color:var(--gradient-start);margin-bottom:4px;">🎲 Симулятор</h2>
                <div style="color:var(--text-secondary);font-size:12px;margin-bottom:10px;">Узнай, сколько ты мог бы заработать!</div>
            `;
            if (history.length < 5) {
                html += `<div class="card"><div class="no-data"><div class="emoji">📭</div><div>Нет данных для симуляции</div><div style="font-size:11px;color:var(--text-secondary);">Сначала сделайте хотя бы 5 ставок!</div></div></div>`;
            } else {
                html += `
                    <div class="card">
                        <h2 style="color:var(--text-secondary);font-size:12px;font-weight:normal;margin-bottom:6px;">📊 Параметры симуляции</h2>
                        <div class="slider-container">
                            <label style="color:var(--text-secondary);font-size:12px;">Количество симуляций: <span id="simCountLabel">1000</span></label>
                            <input type="range" id="simCount" min="100" max="5000" step="100" value="1000" oninput="document.getElementById('simCountLabel').textContent=this.value">
                        </div>
                        <button class="btn-primary" onclick="runSimulation()">🎲 Запустить</button>
                        <button class="btn" onclick="document.getElementById('simResults').style.display='none'">🔄 Сбросить</button>
                    </div>
                    <div id="simResults" style="display:none;">...</div>
                `;
            }
            document.getElementById('simulator-content').innerHTML = html;
        }
        
        function renderSettings(data) {
            const bank = data.stats ? data.stats.bank : 1000;
            let html = `
                <h2 style="font-size:18px;color:var(--gradient-start);margin-bottom:4px;">⚙️ Настройки</h2>
                <div style="color:var(--text-secondary);font-size:12px;margin-bottom:10px;">Управление ботом</div>
                <div class="setting-group">
                    <h2>💰 Банк</h2>
                    <div class="setting-item">
                        <div><div class="label">Текущий банк</div><div class="desc">Ваш игровой банк</div></div>
                        <div class="input-group">
                            <input type="number" id="bankInput" value="${bank}" step="10">
                            <button onclick="updateBank()">Сохранить</button>
                        </div>
                    </div>
                </div>
                <div class="setting-group">
                    <h2>🤖 Автоматизация</h2>
                    <div class="setting-item">
                        <div><div class="label">Авто-ставки</div><div class="desc">Автоматическое размещение ставок</div></div>
                        <div class="toggle active" onclick="this.classList.toggle('active')"><div class="dot"></div></div>
                    </div>
                </div>
                <div class="setting-group">
                    <h2>📊 Экспорт / Импорт</h2>
                    <div class="setting-item">
                        <div><div class="label">Экспорт данных</div><div class="desc">Скачать историю в Excel</div></div>
                        <button class="btn" onclick="window.location.href='/export'">📥 Скачать</button>
                    </div>
                    <div class="setting-item" style="border-bottom:none;">
                        <div><div class="label">Импорт данных</div><div class="desc">Загрузить историю из Excel</div></div>
                        <div class="input-group">
                            <label class="file-input-label" for="importFileInput">📤 Выбрать файл</label>
                            <input type="file" id="importFileInput" accept=".xlsx,.csv" style="display:none" onchange="importExcel(event)">
                            <span id="fileName" style="color:var(--text-secondary);font-size:10px;">Файл не выбран</span>
                        </div>
                    </div>
                    <div id="importStatus" class="import-status"></div>
                </div>
            `;
            document.getElementById('settings-content').innerHTML = html;
        }
        
        // ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
        function runSimulation() {
            // Заглушка для симулятора
            alert('Симулятор скоро будет добавлен!');
        }
        
        async function updateBank() {
            const value = document.getElementById('bankInput').value;
            try {
                const response = await fetch('/api/bank', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bank: parseFloat(value) })
                });
                const data = await response.json();
                if (data.success) {
                    alert('✅ Банк обновлен: $' + data.bank);
                    refreshData();
                }
            } catch (e) {
                alert('❌ Ошибка: ' + e);
            }
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
            loadPageData('dashboard');
        });
    </script>
</body>
</html>
"""

# ============================================================
# API МАРШРУТЫ
# ============================================================

def get_data_from_bot():
    try:
        stats_response = requests.get(f'{BOT_URL}/api/stats', timeout=10)
        stats_data = stats_response.json() if stats_response.status_code == 200 else {}
        history_response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = history_response.json() if history_response.status_code == 200 else []
        return stats_data, history
    except Exception as e:
        print(f"Ошибка получения данных: {e}")
        return {'bank': 1000, 'total_bets': 0, 'wins': 0, 'losses': 0, 'profit': 0, 'winrate': 0, 'roi': 0, 'avg_stake': 0}, []

def get_profit_data(history):
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
                        try: stake = float(stake)
                        except: stake = 0
                    odds = bet.get('odds', 1)
                    if isinstance(odds, str):
                        try: odds = float(odds)
                        except: odds = 1
                    if bet.get('result') == 'win':
                        day_profit += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= stake
            except:
                pass
        profits.append(round(day_profit, 2))
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}

@app.route('/')
def index():
    return render_template_string(MAIN_HTML)

@app.route('/api/all_data')
def all_data():
    stats_data, history = get_data_from_bot()
    profit_data = get_profit_data(history)
    try:
        response = requests.get(f'{BOT_URL}/matches', timeout=10)
        matches = response.json() if response.status_code == 200 else []
    except:
        matches = []
    bank = stats_data.get('bank', 1000)
    return jsonify({
        'stats': {
            'bank': bank,
            'total_bets': stats_data.get('total_bets', 0),
            'wins': stats_data.get('wins', 0),
            'losses': stats_data.get('losses', 0),
            'profit': round(stats_data.get('profit', 0), 2),
            'winrate': stats_data.get('winrate', 0),
            'roi': stats_data.get('roi', 0),
            'avg_stake': stats_data.get('avg_stake', 0)
        },
        'history': history,
        'profit_data': profit_data,
        'matches': matches
    })

# ===== ДНЕВНИК API =====
@app.route('/api/diary', methods=['GET'])
def get_diary():
    return jsonify(load_diary())

@app.route('/api/diary', methods=['POST'])
def add_diary():
    data = request.json
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Пустая запись'}), 400
    entries = load_diary()
    entry_id = max([e.get('id', 0) for e in entries] + [0]) + 1
    entries.append({
        'id': entry_id,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'text': text
    })
    save_diary(entries)
    return jsonify({'success': True, 'id': entry_id})

@app.route('/api/diary/<int:entry_id>', methods=['DELETE'])
def delete_diary(entry_id):
    entries = load_diary()
    entries = [e for e in entries if e.get('id') != entry_id]
    save_diary(entries)
    return jsonify({'success': True})

# ===== ЭКСПОРТ В EXCEL =====
@app.route('/api/export_excel')
def export_excel():
    _, history = get_data_from_bot()
    if not history:
        return "Нет данных", 404
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Ставки')
    headers = ['Дата', 'Матч', 'Счёт', 'Ставка', 'Кэф', 'Сумма', 'EV', 'Результат', 'Прибыль']
    for col, h in enumerate(headers):
        worksheet.write(0, col, h)
    for row, bet in enumerate(history, 1):
        score = f"{bet.get('home_goals', '')}-{bet.get('away_goals', '')}" if bet.get('home_goals') is not None else '-'
        worksheet.write(row, 0, bet.get('date', ''))
        worksheet.write(row, 1, f"{bet.get('home', '')} vs {bet.get('away', '')}")
        worksheet.write(row, 2, score)
        worksheet.write(row, 3, bet.get('bet', ''))
        worksheet.write(row, 4, bet.get('odds', ''))
        worksheet.write(row, 5, bet.get('stake', ''))
        worksheet.write(row, 6, bet.get('ev', ''))
        worksheet.write(row, 7, bet.get('result', ''))
        worksheet.write(row, 8, bet.get('profit', ''))
    workbook.close()
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='history.xlsx')

# ===== ОСТАЛЬНЫЕ API =====
@app.route('/api/simulate', methods=['POST'])
def simulate():
    return jsonify({'error': 'В разработке'}), 400

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        excel_data = request.json.get('data', [])
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        history = response.json() if response.status_code == 200 else []
        imported = 0
        for row in excel_data:
            match = row.get('Матч', '') or row.get('Match', '')
            home = away = ''
            if ' vs ' in match:
                parts = match.split(' vs ')
                home = parts[0].strip()
                away = parts[1].strip()
            score = row.get('Счёт', '') or row.get('Score', '')
            home_goals = away_goals = None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except: pass
            bet = row.get('Ставка', '') or 'Ручная ставка'
            odds = float(row.get('Коэф', 1.85) or 1.85)
            stake = round(float(row.get('Сумма', 0) or 0), 2)
            ev = float(row.get('EV%', 0) or 0)
            result = row.get('Результат', 'pending')
            if result.lower() in ['win', 'выигрыш']: result = 'win'
            elif result.lower() in ['loss', 'проигрыш']: result = 'loss'
            elif result.lower() in ['push', 'возврат']: result = 'push'
            else: result = 'pending'
            profit = float(row.get('Прибыль', 0) or 0)
            date = row.get('Дата', datetime.now().strftime('%Y-%m-%d %H:%M'))
            history.append({
                'home': home or 'Unknown',
                'away': away or 'Unknown',
                'home_goals': home_goals,
                'away_goals': away_goals,
                'bet': bet,
                'odds': odds,
                'stake': stake,
                'ev': ev,
                'result': result,
                'profit': profit,
                'date': date
            })
            imported += 1
        requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def update_bank():
    data = request.json
    if 'bank' in data:
        try:
            requests.post(f'{BOT_URL}/api/bank', json={'bank': data['bank']}, timeout=10)
            return jsonify({'success': True, 'bank': data['bank']})
        except:
            return jsonify({'success': True, 'bank': data['bank']})
    return jsonify({'error': 'No bank value'}), 400

@app.route('/export')
def export_data():
    return export_excel()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
