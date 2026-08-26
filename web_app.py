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
# HTML ШАБЛОН
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
        
        .page { display: none; animation: fadeIn 0.15s ease; }
        .page.active { display: block; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
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
        
        .chart-container { position: relative; height: 140px; width: 100%; }
        
        .table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; }
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
        
        .edit-row {
            background: var(--bg-card);
            padding: 6px;
            border-radius: 4px;
            display: none;
            margin-top: 3px;
        }
        .edit-row.active { display: table-row; }
        .edit-row input, .edit-row select {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 10px;
            margin-right: 2px;
        }
        .edit-row .btn { padding: 2px 8px; font-size: 10px; }
        .edit-btn { cursor: pointer; color: var(--text-secondary); font-size: 11px; }
        .edit-btn:hover { color: var(--gradient-start); }
        
        .no-data { text-align: center; color: var(--text-secondary); padding: 16px 0; }
        .no-data .emoji { font-size: 30px; margin-bottom: 4px; }
        
        .scrollable-table { max-height: 350px; overflow-y: auto; }
        
        .footer {
            text-align: center;
            color: #444466;
            font-size: 9px;
            margin-top: 12px;
            padding: 8px 0;
            border-top: 1px solid var(--border-color);
        }
        
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
        .bottom-nav .nav-item .icon { font-size: 20px; line-height: 1.1; }
        .bottom-nav .nav-item .label { font-size: 8px; margin-top: 1px; font-weight: 500; }
        .bottom-nav .nav-item.active { color: var(--nav-active); }
        .bottom-nav .nav-item.active .icon { transform: scale(1.05); }
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
        .bottom-nav .nav-item:active { transform: scale(0.92); }
        
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
        
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: stretch; gap: 6px; padding: 10px 14px; }
            .header h1 { font-size: 16px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .metrics-grid { grid-template-columns: 1fr 1fr; gap: 4px; }
            .metrics-grid .metric-item { padding: 6px 10px; }
            .metrics-grid .metric-item .value { font-size: 14px; }
            .card { padding: 8px; }
            table { font-size: 9px; min-width: 450px; }
            th, td { padding: 3px 4px; }
            .chart-container { height: 100px; }
            .bottom-nav .nav-item { padding: 2px 6px; min-width: 44px; }
            .bottom-nav .nav-item .icon { font-size: 16px; }
            .bottom-nav .nav-item .label { font-size: 7px; }
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
        
        <div id="page-dashboard" class="page active"><div id="dashboard-content"></div></div>
        <div id="page-matches" class="page"><div id="matches-content"></div></div>
        <div id="page-diary" class="page"><div id="diary-content"></div></div>
        <div id="page-simulator" class="page"><div id="simulator-content"></div></div>
        <div id="page-settings" class="page"><div id="settings-content"></div></div>
        
        <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
    </div>
    
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
        
        // ============================================================
        // === НАВИГАЦИЯ (РАБОТАЕТ 100%!) ===
        // ============================================================
        document.addEventListener('DOMContentLoaded', function() {
            
            function switchPage(page) {
                if (page === currentPage) return;
                
                document.querySelectorAll('.bottom-nav .nav-item').forEach(b => b.classList.remove('active'));
                const activeBtn = document.querySelector(`.bottom-nav .nav-item[data-page="${page}"]`);
                if (activeBtn) activeBtn.classList.add('active');
                
                document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
                const targetPage = document.getElementById('page-' + page);
                if (targetPage) targetPage.classList.add('active');
                
                currentPage = page;
                
                if (page === 'diary') {
                    loadDiary();
                } else {
                    loadPageData(page);
                }
            }
            
            // === ДЕЛЕГИРОВАНИЕ СОБЫТИЙ ===
            document.addEventListener('click', function(e) {
                const navItem = e.target.closest('.bottom-nav .nav-item');
                if (navItem) {
                    const page = navItem.dataset.page;
                    if (page) {
                        e.preventDefault();
                        switchPage(page);
                    }
                }
            });
            
            // === ЗАГРУЗКА НАЧАЛЬНОЙ СТРАНИЦЫ ===
            loadPageData('dashboard');
            
        });
        
        // ============================================================
        // ОСТАЛЬНЫЕ ФУНКЦИИ
        // ============================================================
        
        async function loadPageData(page) {
            if (isLoading) return;
            const contentId = page + '-content';
            const contentEl = document.getElementById(contentId);
            if (!contentEl) return;
            if (page !== 'dashboard' && cachedData && contentEl.innerHTML) return;
            
            isLoading = true;
            contentEl.innerHTML = '<div class="loader active"><div class="spinner"></div><div style="color:var(--text-secondary);font-size:12px;margin-top:6px;">Загрузка...</div></div>';
            
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
                <div class="card">
                    <div class="card-header">
                        <h2>📈 График прибыли</h2>
                        <span style="font-size:9px;color:var(--text-secondary);">За последние 7 дней</span>
                    </div>
                    <div class="chart-container"><canvas id="profitChart"></canvas></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <h2>📋 Все ставки</h2>
                        <span class="count">Всего: ${history.length}</span>
                    </div>
                    <div class="scrollable-table">
                        <div class="table-wrapper">
                            <table>
                                <thead><tr><th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th><th>✏️</th></tr></thead>
                                <tbody>
            `;
            if (history.length === 0) {
                html += `<tr><td colspan="11" class="no-data"><div class="emoji">📭</div>Нет данных</td></tr>`;
            } else {
                history.slice().reverse().forEach((bet, idx) => {
                    const realIdx = history.length - 1 - idx;
                    const profitClass = bet.profit > 0 ? 'profit-positive' : (bet.profit < 0 ? 'profit-negative' : '');
                    html += `
                        <tr>
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
                            <td><span class="edit-btn" onclick="toggleEdit(${realIdx})">✏️</span></td>
                        </tr>
                        <tr id="edit-row-${realIdx}" class="edit-row">
                            <td colspan="11">
                                <div style="display:flex;flex-wrap:wrap;gap:3px;align-items:center;">
                                    <input type="text" id="edit_home_${realIdx}" value="${bet.home}" style="width:70px;">
                                    <input type="text" id="edit_away_${realIdx}" value="${bet.away}" style="width:70px;">
                                    <input type="text" id="edit_score_${realIdx}" value="${bet.home_goals !== null && bet.away_goals !== null ? bet.home_goals + '-' + bet.away_goals : ''}" style="width:50px;">
                                    <input type="text" id="edit_bet_${realIdx}" value="${bet.bet}" style="width:70px;">
                                    <input type="number" id="edit_odds_${realIdx}" value="${bet.odds}" step="0.01" style="width:50px;">
                                    <input type="number" id="edit_stake_${realIdx}" value="${bet.stake}" step="0.5" style="width:60px;">
                                    <input type="number" id="edit_ev_${realIdx}" value="${bet.ev}" step="0.1" style="width:50px;">
                                    <select id="edit_result_${realIdx}" style="padding:2px 4px;border-radius:3px;border:1px solid var(--input-border);background:var(--input-bg);color:var(--text-primary);font-size:10px;">
                                        <option value="win" ${bet.result === 'win' ? 'selected' : ''}>win</option>
                                        <option value="loss" ${bet.result === 'loss' ? 'selected' : ''}>loss</option>
                                        <option value="push" ${bet.result === 'push' ? 'selected' : ''}>push</option>
                                        <option value="pending" ${bet.result === 'pending' ? 'selected' : ''}>pending</option>
                                    </select>
                                    <button class="btn btn-success" onclick="saveEdit(${realIdx})" style="padding:2px 6px;font-size:9px;background:#38ef7d;color:#000;">💾</button>
                                    <button class="btn btn-danger" onclick="deleteBet(${realIdx})" style="padding:2px 6px;font-size:9px;background:#ef473a;color:#fff;">🗑️</button>
                                    <button class="btn" onclick="toggleEdit(${realIdx})" style="padding:2px 6px;font-size:9px;">✖</button>
                                </div>
                            </td>
                        </tr>
                    `;
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
            setTimeout(() => renderChart(data.profit_data), 50);
        }
        
        function exportToExcel() {
            window.location.href = '/api/export_excel';
        }
        
        function renderChart(profitData) {
            const ctx = document.getElementById('profitChart');
            if (!ctx) return;
            if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const data = profitData || { dates: ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], profits: [0,0,0,0,0,0,0] };
            chartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.dates,
                    datasets: [{
                        label: 'Прибыль ($)',
                        data: data.profits,
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
                    plugins: { legend: { labels: { color: isDark ? '#e0e0e0' : '#1a1a2e', font: { size: 9 } } } },
                    scales: {
                        x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 8 } } },
                        y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: function(value) { return '$' + value; }, font: { size: 8 } } }
                    }
                }
            });
        }
        
        function renderMatches(data) {
            const matches = data.matches || [];
            let html = `
                <h2 style="font-size:18px;color:var(--gradient-start);margin-bottom:4px;">⚽ Матчи</h2>
                <div style="color:var(--text-secondary);font-size:12px;margin-bottom:10px;">Прогнозы и валуйные ставки</div>
                <div class="match-tabs"><span class="match-tab active">Все игры</span><span class="match-tab">LIVE</span><span class="match-tab">⭐ Избранное</span><span class="match-tab">🏆 Турниры</span></div>
            `;
            if (matches.length === 0) {
                html += `<div class="no-data"><div class="emoji">📭</div>Матчей не найдено</div>`;
            } else {
                matches.forEach(m => {
                    html += `<div class="match-card"><div class="match-title">${m.home} vs ${m.away}</div><div class="match-league">🏆 ${m.league} | ⏰ ${m.match_time}</div><div class="match-xg">📊 xG: ${m.home_xg} : ${m.away_xg}</div><div class="match-bets">${(m.bets || []).slice(0,3).map(b => `<span class="bet-item">${b.label} | КЭФ: ${b.odds} | EV: ${b.ev}%</span>`).join('')}</div></div>`;
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
                        <div style="display:flex;gap:6px;flex-wrap:wrap;">
                            <button class="btn-primary" onclick="runSimulation()">🎲 Запустить</button>
                            <button class="btn" onclick="document.getElementById('simResults').style.display='none'">🔄 Сбросить</button>
                        </div>
                    </div>
                    <div id="simResults" style="display:none;">
                        <div class="sim-stats" id="simStats">
                            <div class="sim-stat"><div class="value gold" id="simProfit">$0</div><div class="label">💰 Ожидаемая прибыль</div></div>
                            <div class="sim-stat"><div class="value green" id="simWinrate">0%</div><div class="label">🎯 Проходимость</div></div>
                            <div class="sim-stat"><div class="value" id="simROI">0%</div><div class="label">📈 ROI</div></div>
                            <div class="sim-stat"><div class="value red" id="simRisk">0%</div><div class="label">⚠️ Риск</div></div>
                        </div>
                        <div class="card">
                            <h2 style="color:var(--text-secondary);font-size:12px;font-weight:normal;margin-bottom:6px;">📈 График симуляции</h2>
                            <div class="chart-container"><canvas id="simChart"></canvas></div>
                        </div>
                        <div class="card">
                            <h2 style="color:var(--text-secondary);font-size:12px;font-weight:normal;margin-bottom:6px;">📋 Результаты</h2>
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px;" id="simDetails">
                                <div style="color:var(--text-secondary);">Всего: <span id="simTotal" style="color:var(--text-primary);">0</span></div>
                                <div style="color:var(--text-secondary);">Выигрышей: <span id="simWins" style="color:#38ef7d;">0</span></div>
                                <div style="color:var(--text-secondary);">Проигрышей: <span id="simLosses" style="color:#ef473a;">0</span></div>
                                <div style="color:var(--text-secondary);">Макс. прибыль: <span id="simMaxProfit" style="color:#ffd200;">$0</span></div>
                                <div style="color:var(--text-secondary);">Мин. прибыль: <span id="simMinProfit" style="color:#ef473a;">$0</span></div>
                                <div style="color:var(--text-secondary);">Средняя ставка: <span id="simAvgStake" style="color:var(--text-primary);">$0</span></div>
                            </div>
                        </div>
                        <div class="card" style="background:rgba(102,126,234,0.05);border-color:#667eea;">
                            <h2 style="color:var(--text-secondary);font-size:12px;font-weight:normal;margin-bottom:6px;">💡 Рекомендация</h2>
                            <div id="simRecommendation" style="font-size:13px;line-height:1.5;">Запустите симуляцию, чтобы получить рекомендацию!</div>
                        </div>
                    </div>
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
        
        function toggleEdit(index) {
            const row = document.getElementById('edit-row-' + index);
            if (row) row.classList.toggle('active');
        }
        
        async function saveEdit(index) {
            const score = document.getElementById('edit_score_' + index).value;
            let home_goals = null, away_goals = null;
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
                bet: document.getElementById('edit_bet_' + index).value,
                odds: parseFloat(document.getElementById('edit_odds_' + index).value) || 0,
                stake: parseFloat(document.getElementById('edit_stake_' + index).value) || 0,
                ev: parseFloat(document.getElementById('edit_ev_' + index).value) || 0,
                result: document.getElementById('edit_result_' + index).value,
                index: index
            };
            try {
                const response = await fetch('/api/edit_bet', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (result.success) {
                    alert('✅ Ставка обновлена!');
                    refreshData();
                } else {
                    alert('❌ Ошибка: ' + result.error);
                }
            } catch (e) {
                alert('❌ Ошибка: ' + e);
            }
        }
        
        async function deleteBet(index) {
            if (!confirm('Удалить эту ставку?')) return;
            try {
                const response = await fetch('/api/delete_bet', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ index: index })
                });
                const result = await response.json();
                if (result.success) {
                    alert('✅ Ставка удалена!');
                    refreshData();
                } else {
                    alert('❌ Ошибка: ' + result.error);
                }
            } catch (e) {
                alert('❌ Ошибка: ' + e);
            }
        }
        
        async function runSimulation() {
            const count = parseInt(document.getElementById('simCount').value) || 1000;
            document.getElementById('simResults').style.display = 'block';
            try {
                const response = await fetch('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ count: count })
                });
                const data = await response.json();
                if (data.error) {
                    alert('❌ Ошибка: ' + data.error);
                    return;
                }
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
                    if (simChartInstance) { simChartInstance.destroy(); simChartInstance = null; }
                    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    simChartInstance = new Chart(ctx, {
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
                            plugins: { legend: { labels: { color: isDark ? '#e0e0e0' : '#1a1a2e', font: { size: 9 } } } },
                            scales: {
                                x: { ticks: { color: isDark ? '#8888aa' : '#666688', font: { size: 8 } } },
                                y: { ticks: { color: isDark ? '#8888aa' : '#666688', callback: function(value) { return '$' + value; }, font: { size: 8 } } }
                            }
                        }
                    });
                }
            } catch (e) {
                alert('❌ Ошибка: ' + e);
            }
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
                            setTimeout(() => refreshData(), 1500);
                        } else {
                            statusDiv.textContent = '❌ Ошибка: ' + data.error;
                        }
                    })
                    .catch(error => { statusDiv.textContent = '❌ Ошибка: ' + error; });
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
    entries.append({'id': entry_id, 'date': datetime.now().strftime('%Y-%m-%d %H:%M'), 'text': text})
    save_diary(entries)
    return jsonify({'success': True, 'id': entry_id})

@app.route('/api/diary/<int:entry_id>', methods=['DELETE'])
def delete_diary(entry_id):
    entries = load_diary()
    entries = [e for e in entries if e.get('id') != entry_id]
    save_diary(entries)
    return jsonify({'success': True})

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
        winrate = wins / len(history) if len(history) > 0 else 0
        avg_stake = sum(float(b.get('stake', 0)) for b in history) / len(history) if len(history) > 0 else 10
        profit_history = []
        total_profit = 0
        for _ in range(count):
            if random.random() < winrate:
                profit = avg_stake * random.uniform(0.5, 1.5)
                total_profit += profit
            else:
                profit = -avg_stake
                total_profit += profit
            profit_history.append(round(total_profit, 2))
        return jsonify({
            'total': count,
            'wins': int(winrate * count),
            'losses': count - int(winrate * count),
            'profit': round(total_profit, 2),
            'winrate': round(winrate * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'risk': round((abs(min(profit_history)) / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'max_profit': round(max(profit_history), 2),
            'min_profit': round(min(profit_history), 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@app.route('/export')
def export_data():
    return export_excel()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
