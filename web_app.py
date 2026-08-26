import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request, send_file
from datetime import datetime, timedelta
import json
import random
import io
import xlsxwriter

app = Flask(__name__)

DATA_FILE = 'data.json'
DIARY_FILE = 'diary.json'

# ============================================================
# РАБОТА С ДАННЫМИ
# ============================================================

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'bank': 1000, 'history': []}
    return {'bank': 1000, 'history': []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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

def get_stats(history):
    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    profit = sum(float(b.get('profit', 0)) for b in history)
    total_stake = sum(float(b.get('stake', 0)) for b in history)
    return {
        'bank': load_data().get('bank', 1000),
        'total_bets': total,
        'wins': wins,
        'losses': losses,
        'profit': round(profit, 2),
        'winrate': round(wins / total * 100, 1) if total > 0 else 0,
        'roi': round((profit / (total_stake or 1)) * 100, 2) if total > 0 else 0,
        'avg_stake': round(total_stake / total, 2) if total > 0 else 0
    }

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

# ============================================================
# HTML ШАБЛОН (ТЕМА КАК В GROK)
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
            --bg-primary: #0a0a0f;
            --bg-secondary: #14141e;
            --bg-card: rgba(255,255,255,0.04);
            --bg-hover: rgba(255,255,255,0.06);
            --text-primary: #ececec;
            --text-secondary: #8a8aa0;
            --text-muted: #5a5a7a;
            --border-color: rgba(255,255,255,0.06);
            --shadow: rgba(0,0,0,0.6);
            --gradient-start: #6c5ce7;
            --gradient-end: #a855f7;
            --nav-bg: rgba(20,20,30,0.92);
            --nav-active: #a855f7;
            --input-bg: rgba(255,255,255,0.05);
            --input-border: rgba(255,255,255,0.08);
            --glow: rgba(168,85,247,0.2);
        }
        [data-theme="light"] {
            --bg-primary: #f0edf5;
            --bg-secondary: #ffffff;
            --bg-card: rgba(0,0,0,0.03);
            --bg-hover: rgba(0,0,0,0.04);
            --text-primary: #1a1a2e;
            --text-secondary: #6a6a8a;
            --text-muted: #aaaac0;
            --border-color: rgba(0,0,0,0.06);
            --shadow: rgba(0,0,0,0.08);
            --gradient-start: #6c5ce7;
            --gradient-end: #a855f7;
            --nav-bg: rgba(255,255,255,0.92);
            --nav-active: #7c3aed;
            --input-bg: rgba(0,0,0,0.04);
            --input-border: rgba(0,0,0,0.1);
            --glow: rgba(124,58,237,0.15);
        }
        * { transition: background-color 0.4s cubic-bezier(0.4,0,0.2,1), color 0.3s cubic-bezier(0.4,0,0.2,1), border-color 0.3s cubic-bezier(0.4,0,0.2,1), box-shadow 0.4s cubic-bezier(0.4,0,0.2,1); }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            padding-bottom: 80px;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 16px 20px; }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            padding: 14px 20px;
            background: var(--bg-secondary);
            border-radius: 16px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 30px var(--shadow);
            margin-bottom: 20px;
            backdrop-filter: blur(20px);
        }
        .header h1 {
            font-size: 20px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.5px;
        }
        .header-controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        .status {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #22d3ee;
            font-size: 12px;
            font-weight: 500;
        }
        .status-dot {
            width: 8px; height: 8px;
            background: #22d3ee;
            border-radius: 50%;
            animation: pulse-dot 2s ease-in-out infinite;
            box-shadow: 0 0 12px rgba(34,211,238,0.3);
        }
        @keyframes pulse-dot { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:0.5; transform:scale(0.85); } }
        
        .theme-toggle {
            position: relative;
            width: 52px; height: 28px;
            border-radius: 14px;
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: all 0.4s cubic-bezier(0.4,0,0.2,1);
            padding: 0;
            flex-shrink: 0;
        }
        .theme-toggle:hover { border-color: var(--gradient-end); box-shadow: 0 0 20px var(--glow); }
        .theme-toggle .toggle-track { position: relative; width: 100%; height: 100%; border-radius: 14px; overflow: hidden; }
        .theme-toggle .toggle-thumb {
            position: absolute;
            top: 3px; left: 3px;
            width: 20px; height: 20px;
            border-radius: 50%;
            background: var(--gradient-start);
            transition: all 0.4s cubic-bezier(0.4,0,0.2,1);
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        .theme-toggle .toggle-thumb .icon {
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            font-size: 11px;
            line-height: 1;
            transition: all 0.4s cubic-bezier(0.4,0,0.2,1);
        }
        .theme-toggle .toggle-thumb .icon-dark { opacity: 1; }
        .theme-toggle .toggle-thumb .icon-light { opacity: 0; }
        [data-theme="light"] .theme-toggle .toggle-thumb { left: 27px; background: #fbbf24; }
        [data-theme="light"] .theme-toggle .toggle-thumb .icon-dark { opacity: 0; }
        [data-theme="light"] .theme-toggle .toggle-thumb .icon-light { opacity: 1; }
        
        .bottom-nav {
            position: fixed;
            bottom: 0; left: 0; right: 0;
            background: var(--nav-bg);
            backdrop-filter: blur(20px) saturate(1.4);
            -webkit-backdrop-filter: blur(20px) saturate(1.4);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 6px 0 env(safe-area-inset-bottom,6px);
            z-index: 1000;
            box-shadow: 0 -4px 30px var(--shadow);
        }
        .bottom-nav .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: var(--text-secondary);
            font-size: 9px;
            transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
            padding: 4px 12px;
            border-radius: 12px;
            border: none;
            background: transparent;
            cursor: pointer;
            min-width: 52px;
            position: relative;
            -webkit-tap-highlight-color: transparent;
            user-select: none;
            gap: 2px;
        }
        .bottom-nav .nav-item .icon { font-size: 20px; line-height: 1.2; transition: all 0.3s cubic-bezier(0.4,0,0.2,1); }
        .bottom-nav .nav-item .label { font-size: 8px; font-weight: 500; letter-spacing: 0.3px; opacity: 0.8; transition: all 0.3s cubic-bezier(0.4,0,0.2,1); }
        .bottom-nav .nav-item.active { color: var(--nav-active); }
        .bottom-nav .nav-item.active .icon { transform: scale(1.1); }
        .bottom-nav .nav-item.active .label { opacity: 1; }
        .bottom-nav .nav-item.active::after {
            content: ''; position: absolute; top: -1px; left: 50%; transform: translateX(-50%);
            width: 20px; height: 2px; background: var(--nav-active); border-radius: 2px; box-shadow: 0 0 16px var(--glow);
        }
        .bottom-nav .nav-item:hover { color: var(--text-primary); background: var(--bg-hover); }
        .bottom-nav .nav-item:active { transform: scale(0.92); }
        
        .card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 20px var(--shadow);
        }
        .card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
        .card-header h2 { color: var(--text-secondary); font-size: 13px; font-weight: 600; letter-spacing: 0.3px; }
        .card-header .count { color: var(--text-muted); font-size: 11px; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }
        .stat-card {
            padding: 14px;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            background: var(--bg-secondary);
            text-align: center;
            box-shadow: 0 2px 12px var(--shadow);
        }
        .stat-card:hover { transform: translateY(-2px); border-color: var(--gradient-end); box-shadow: 0 8px 30px var(--shadow); }
        .stat-card .value {
            font-size: 22px; font-weight: 700;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.green { background: linear-gradient(135deg, #10b981, #34d399); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.red { background: linear-gradient(135deg, #ef4444, #f87171); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .value.gold { background: linear-gradient(135deg, #f59e0b, #fbbf24); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .stat-card .label { color: var(--text-secondary); font-size: 11px; margin-top: 4px; font-weight: 500; }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 14px;
        }
        .metrics-grid .metric-item {
            background: var(--bg-secondary);
            padding: 10px 16px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px var(--shadow);
        }
        .metrics-grid .metric-item .label { color: var(--text-secondary); font-size: 12px; font-weight: 500; }
        .metrics-grid .metric-item .value { font-size: 18px; font-weight: 700; color: var(--text-primary); }
        .metrics-grid .metric-item .value.green { color: #34d399; }
        .metrics-grid .metric-item .value.gold { color: #fbbf24; }
        
        .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
        .chart-container { position: relative; height: 160px; width: 100%; }
        
        .table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 600px; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
        th { color: var(--text-secondary); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; background: var(--bg-card); position: sticky; top: 0; }
        tr:hover td { background: var(--bg-hover); }
        
        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .badge.win { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.2); }
        .badge.loss { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.2); }
        .badge.push { background: rgba(251,191,36,0.15); color: #fbbf24; border: 1px solid rgba(251,191,36,0.2); }
        .badge.pending { background: rgba(255,255,255,0.05); color: var(--text-secondary); border: 1px solid var(--border-color); }
        .profit-positive { color: #34d399; font-weight: 700; }
        .profit-negative { color: #f87171; font-weight: 700; }
        
        .btn {
            padding: 6px 14px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .btn:hover { background: var(--bg-hover); border-color: var(--gradient-end); color: var(--text-primary); box-shadow: 0 4px 16px var(--glow); }
        .btn-success {
            background: linear-gradient(135deg, #10b981, #059669);
            color: #fff;
            border-color: transparent;
        }
        .btn-success:hover { background: linear-gradient(135deg, #059669, #047857); border-color: transparent; box-shadow: 0 4px 20px rgba(16,185,129,0.3); }
        .btn-primary {
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            color: #fff;
            border: none;
            padding: 8px 20px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .btn-primary:hover { transform: scale(1.02); box-shadow: 0 4px 24px var(--glow); }
        
        .no-data { text-align: center; color: var(--text-secondary); padding: 30px 0; }
        .no-data .emoji { font-size: 40px; margin-bottom: 8px; }
        
        .footer { text-align: center; color: var(--text-muted); font-size: 10px; margin-top: 20px; padding: 12px 0; border-top: 1px solid var(--border-color); }
        .loader { display: none; text-align: center; padding: 30px 0; color: var(--text-secondary); }
        .loader.active { display: block; }
        .loader .spinner {
            width: 32px; height: 32px;
            border: 3px solid var(--border-color);
            border-top-color: var(--gradient-start);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        /* ===== ДНЕВНИК ===== */
        .diary-textarea {
            width: 100%;
            padding: 12px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-primary);
            resize: vertical;
            min-height: 80px;
            font-family: inherit;
            font-size: 13px;
        }
        .diary-textarea:focus { outline: none; border-color: var(--gradient-end); box-shadow: 0 0 24px var(--glow); }
        .diary-entry {
            background: var(--bg-card);
            padding: 12px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            margin-bottom: 8px;
        }
        .diary-entry:hover { border-color: var(--gradient-end); }
        .diary-entry .date { color: var(--text-muted); font-size: 10px; }
        .diary-entry .text { font-size: 13px; margin-top: 4px; line-height: 1.5; }
        .diary-entry .delete-btn {
            float: right;
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 14px;
        }
        .diary-entry .delete-btn:hover { color: #f87171; transform: scale(1.1); }
        
        .match-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
        .match-tab {
            padding: 5px 14px;
            border-radius: 20px;
            font-size: 12px;
            cursor: pointer;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-secondary);
            font-weight: 500;
        }
        .match-tab.active { background: var(--gradient-start); color: #fff; border-color: var(--gradient-start); box-shadow: 0 4px 16px var(--glow); }
        .match-card {
            background: var(--bg-secondary);
            padding: 14px;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            margin-bottom: 10px;
        }
        .match-card:hover { border-color: var(--gradient-end); }
        .match-title { font-size: 14px; font-weight: 600; }
        .match-league { color: var(--text-secondary); font-size: 12px; }
        .match-xg { color: var(--gradient-start); font-size: 12px; }
        .match-bets { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
        .bet-item { background: var(--bg-card); padding: 3px 10px; border-radius: 6px; font-size: 11px; border: 1px solid var(--border-color); }
        
        .setting-group {
            background: var(--bg-secondary);
            padding: 14px;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            margin-bottom: 10px;
        }
        .setting-group h2 { color: var(--text-secondary); font-size: 13px; font-weight: 600; margin-bottom: 8px; }
        .setting-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0;
            border-bottom: 1px solid var(--border-color);
            flex-wrap: wrap;
            gap: 6px;
        }
        .setting-item:last-child { border-bottom: none; }
        .input-group { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
        .input-group input {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            color: var(--text-primary);
            padding: 6px 10px;
            border-radius: 8px;
            width: 90px;
            font-size: 13px;
        }
        .input-group input:focus { outline: none; border-color: var(--gradient-end); box-shadow: 0 0 20px var(--glow); }
        .input-group button {
            background: var(--gradient-start);
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
        }
        .input-group button:hover { background: var(--gradient-end); box-shadow: 0 4px 16px var(--glow); }
        .toggle {
            width: 44px; height: 24px;
            background: var(--input-border);
            border-radius: 12px;
            cursor: pointer;
            position: relative;
        }
        .toggle.active { background: var(--gradient-start); box-shadow: 0 0 20px var(--glow); }
        .toggle .dot {
            width: 18px; height: 18px;
            background: #fff;
            border-radius: 50%;
            position: absolute;
            top: 3px; left: 3px;
            transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .toggle.active .dot { left: 23px; }
        .file-input-label {
            display: inline-block;
            padding: 6px 14px;
            background: var(--gradient-start);
            color: #fff;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
        }
        .file-input-label:hover { background: var(--gradient-end); box-shadow: 0 4px 16px var(--glow); }
        .import-status { color: var(--text-secondary); font-size: 11px; margin-top: 4px; }
        
        .sim-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 10px;
            margin-bottom: 12px;
        }
        .sim-stat {
            background: var(--bg-card);
            padding: 12px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid var(--border-color);
        }
        .sim-stat .value { font-size: 22px; font-weight: 700; }
        .sim-stat .value.green { color: #34d399; }
        .sim-stat .value.red { color: #f87171; }
        .sim-stat .value.gold { color: #fbbf24; }
        .sim-stat .label { color: var(--text-secondary); font-size: 11px; margin-top: 4px; }
        
        .slider-container { margin: 12px 0; }
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
            width: 18px; height: 18px;
            border-radius: 50%;
            background: var(--gradient-start);
            cursor: pointer;
            box-shadow: 0 0 20px var(--glow);
        }
        
        @media (max-width: 768px) {
            .container { padding: 12px; }
            .header { flex-direction: column; align-items: stretch; gap: 8px; padding: 12px 16px; }
            .header h1 { font-size: 18px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
            .metrics-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .charts-row { grid-template-columns: 1fr; gap: 10px; }
            .chart-container { height: 130px; }
            .bottom-nav .nav-item { padding: 2px 8px; min-width: 44px; }
            .bottom-nav .nav-item .icon { font-size: 17px; }
            .bottom-nav .nav-item .label { font-size: 7px; }
            table { font-size: 10px; min-width: 450px; }
            th, td { padding: 5px 6px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .stat-card { padding: 10px; }
            .stat-card .value { font-size: 18px; }
            .metrics-grid { grid-template-columns: 1fr; }
            .bottom-nav .nav-item { min-width: 38px; padding: 2px 4px; }
            .bottom-nav .nav-item .icon { font-size: 15px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Quantum Bet Bot</h1>
            <div class="header-controls">
                <div class="status"><span class="status-dot"></span><span>Система активна</span><span style="color:var(--text-muted);">|</span><span style="color:var(--text-muted);">v12 PRO</span></div>
                <button class="theme-toggle" id="themeToggle" aria-label="Переключить тему">
                    <div class="toggle-track"><div class="toggle-thumb"><span class="icon icon-dark">🌙</span><span class="icon icon-light">☀️</span></div></div>
                </button>
                <button class="btn" onclick="refreshData()" style="font-size:14px;padding:4px 10px;">🔄</button>
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
        <button class="nav-item active" data-page="dashboard"><span class="icon">📊</span><span class="label">Дашборд</span></button>
        <button class="nav-item" data-page="matches"><span class="icon">⚽</span><span class="label">Матчи</span></button>
        <button class="nav-item" data-page="diary"><span class="icon">📖</span><span class="label">Дневник</span></button>
        <button class="nav-item" data-page="simulator"><span class="icon">🎲</span><span class="label">Симулятор</span></button>
        <button class="nav-item" data-page="settings"><span class="icon">⚙️</span><span class="label">Настройки</span></button>
    </div>
    
    <script>
        // ============================================================
        // ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
        // ============================================================
        let cachedData = null;
        let chartInstance = null;
        let chartWeekday = null;
        let simChartInstance = null;
        let currentPage = 'dashboard';
        let isLoading = false;
        
        // ============================================================
        // ТЕМА
        // ============================================================
        function setTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
        }
        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme');
            setTheme(current === 'dark' ? 'light' : 'dark');
        }
        const savedTheme = localStorage.getItem('theme') || 'dark';
        setTheme(savedTheme);
        document.addEventListener('DOMContentLoaded', function() {
            const toggleBtn = document.getElementById('themeToggle');
            if (toggleBtn) toggleBtn.addEventListener('click', toggleTheme);
        });
        
        // ============================================================
        // НАВИГАЦИЯ
        // ============================================================
        document.querySelectorAll('.bottom-nav .nav-item').forEach(btn => {
            btn.addEventListener('click', function(e) {
                const page = this.dataset.page;
                if (page) switchPage(page);
            });
        });
        function switchPage(page) {
            if (page === currentPage) return;
            document.querySelectorAll('.bottom-nav .nav-item').forEach(b => b.classList.remove('active'));
            document.querySelector(`.bottom-nav .nav-item[data-page="${page}"]`).classList.add('active');
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            const target = document.getElementById('page-' + page);
            if (target) target.classList.add('active');
            currentPage = page;
            if (page === 'diary') { loadDiary(); } else { loadPageData(page); }
        }
        
        // ============================================================
        // ЗАГРУЗКА ДАННЫХ
        // ============================================================
        async function loadPageData(page) {
            if (isLoading) return;
            const contentEl = document.getElementById(page + '-content');
            if (!contentEl) return;
            contentEl.innerHTML = '<div class="loader active"><div class="spinner"></div><div style="color:var(--text-secondary);font-size:12px;margin-top:8px;">Загрузка...</div></div>';
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
        function refreshData() { cachedData = null; loadPageData(currentPage); }
        
        // ============================================================
        // ДНЕВНИК
        // ============================================================
        async function loadDiary() {
            const el = document.getElementById('diary-content');
            if (!el) return;
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
            if (!el) return;
            let html = `
                <h2 style="font-size:20px;color:var(--gradient-start);margin-bottom:4px;font-weight:700;">📖 Дневник</h2>
                <div style="color:var(--text-secondary);font-size:13px;margin-bottom:14px;">Записывай свои мысли, идеи и заметки по ставкам</div>
                <div class="card">
                    <h2 style="color:var(--text-secondary);font-size:13px;font-weight:600;margin-bottom:8px;">✏️ Новая запись</h2>
                    <textarea id="diaryInput" class="diary-textarea" placeholder="Напиши свою заметку..."></textarea>
                    <button class="btn btn-success" onclick="saveDiaryEntry()" style="margin-top:8px;padding:8px 20px;">💾 Сохранить</button>
                </div>
                <div class="card">
                    <h2 style="color:var(--text-secondary);font-size:13px;font-weight:600;margin-bottom:8px;">📚 Все записи (${entries.length})</h2>
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
                const response = await fetch('/api/diary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
                const data = await response.json();
                if (data.success) { document.getElementById('diaryInput').value = ''; loadDiary(); }
            } catch (e) { alert('Ошибка сохранения'); }
        }
        async function deleteDiaryEntry(id) {
            if (!confirm('Удалить эту запись?')) return;
            try {
                const response = await fetch('/api/diary/' + id, { method: 'DELETE' });
                const data = await response.json();
                if (data.success) loadDiary();
            } catch (e) { alert('Ошибка удаления'); }
        }
        
        // ============================================================
        // РЕНДЕР ДАШБОРДА
        // ============================================================
        function renderDashboard(data) {
            const s = data.stats;
            const history = data.history || [];
            const profitData = data.profit_data || { dates: [], profits: [] };
            const el = document.getElementById('dashboard-content');
            if (!el) return;
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
                    <div class="card"><div class="card-header"><h2>📈 График прибыли</h2><span style="font-size:9px;color:var(--text-muted);">За 7 дней</span></div><div class="chart-container"><canvas id="profitChart"></canvas></div></div>
                    <div class="card"><div class="card-header"><h2>📊 По дням недели</h2><span style="font-size:9px;color:var(--text-muted);">Средняя прибыль</span></div><div class="chart-container"><canvas id="weekdayChart"></canvas></div></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>📋 Все ставки</h2><span class="count">Всего: ${history.length}</span></div>
                    <div class="table-wrapper"><table><thead><tr><th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead><tbody>
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
            html += `</tbody></table></div>
                    <div style="margin-top:12px;">
                        <button class="btn btn-success" onclick="exportToExcel()" style="padding:8px 20px;">📥 Сохранить в Excel</button>
                    </div>
                </div>
            `;
            el.innerHTML = html;
            setTimeout(() => renderCharts(profitData, history), 150);
        }
        
        // ============================================================
        // ГРАФИКИ
        // ============================================================
        function renderCharts(profitData, history) {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textColor = isDark ? '#ececec' : '#1a1a2e';
            const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
            const ctx1 = document.getElementById('profitChart');
            if (ctx1) {
                if (chartInstance) chartInstance.destroy();
                const labels = profitData.dates || ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
                const profits = profitData.profits || [0,0,0,0,0,0,0];
                chartInstance = new Chart(ctx1, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Прибыль ($)',
                            data: profits,
                            borderColor: '#a855f7',
                            backgroundColor: 'rgba(168,85,247,0.1)',
                            fill: true,
                            tension: 0.4,
                            pointBackgroundColor: '#a855f7',
                            pointBorderColor: isDark ? '#1a1a2e' : '#ffffff',
                            pointBorderWidth: 2,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { labels: { color: textColor, font: { size: 10 } } } },
                        scales: {
                            x: { grid: { color: gridColor }, ticks: { color: isDark ? '#8a8aa0' : '#6a6a8a', font: { size: 9 } } },
                            y: { grid: { color: gridColor }, ticks: { color: isDark ? '#8a8aa0' : '#6a6a8a', callback: v => '$' + v, font: { size: 9 } } }
                        }
                    }
                });
            }
            const ctx2 = document.getElementById('weekdayChart');
            if (ctx2) {
                if (chartWeekday) chartWeekday.destroy();
                const weekdayData = getWeekdayData(history);
                chartWeekday = new Chart(ctx2, {
                    type: 'bar',
                    data: {
                        labels: ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],
                        datasets: [{
                            label: 'Средняя прибыль ($)',
                            data: weekdayData,
                            backgroundColor: ['#a855f7','#7c3aed','#6d28d9','#5b21b6','#4c1d95','#a855f7','#7c3aed'],
                            borderRadius: 6,
                            hoverBackgroundColor: ['#c084fc','#8b5cf6','#7c3aed','#6d28d9','#5b21b6','#c084fc','#8b5cf6']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { labels: { color: textColor, font: { size: 10 } } } },
                        scales: {
                            x: { grid: { color: gridColor }, ticks: { color: isDark ? '#8a8aa0' : '#6a6a8a', font: { size: 9 } } },
                            y: { grid: { color: gridColor }, ticks: { color: isDark ? '#8a8aa0' : '#6a6a8a', callback: v => '$' + v, font: { size: 9 } } }
                        }
                    }
                });
            }
        }
        function getWeekdayData(history) {
            const days = [0,0,0,0,0,0,0], counts = [0,0,0,0,0,0,0];
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
        function exportToExcel() { window.location.href = '/api/export_excel'; }
        
        // ============================================================
        // РЕНДЕР МАТЧЕЙ
        // ============================================================
        function renderMatches(data) {
            const matches = data.matches || [];
            const el = document.getElementById('matches-content');
            if (!el) return;
            let html = `
                <h2 style="font-size:20px;color:var(--gradient-start);margin-bottom:4px;font-weight:700;">⚽ Матчи</h2>
                <div style="color:var(--text-secondary);font-size:13px;margin-bottom:14px;">Прогнозы и валуйные ставки</div>
                <div class="match-tabs"><span class="match-tab active">Все игры</span><span class="match-tab">LIVE</span><span class="match-tab">⭐ Избранное</span><span class="match-tab">🏆 Турниры</span></div>
            `;
            if (matches.length === 0) {
                html += `<div class="no-data"><div class="emoji">📭</div>Матчей не найдено</div>`;
            } else {
                matches.forEach(m => {
                    html += `<div class="match-card"><div class="match-title">${m.home} vs ${m.away}</div><div class="match-league">🏆 ${m.league} | ⏰ ${m.match_time}</div><div class="match-xg">📊 xG: ${m.home_xg} : ${m.away_xg}</div><div class="match-bets">${(m.bets || []).slice(0,3).map(b => `<span class="bet-item">${b.label} | КЭФ: ${b.odds} | EV: ${b.ev}%</span>`).join('')}</div></div>`;
                });
            }
            el.innerHTML = html;
        }
        
        // ============================================================
        // РЕНДЕР СИМУЛЯТОРА
        // ============================================================
        function renderSimulator(data) {
            const history = data.history || [];
            const el = document.getElementById('simulator-content');
            if (!el) return;
            let html = `
                <h2 style="font-size:20px;color:var(--gradient-start);margin-bottom:4px;font-weight:700;">🎲 Симулятор</h2>
                <div style="color:var(--text-secondary);font-size:13px;margin-bottom:14px;">Узнай, сколько ты мог бы заработать!</div>
            `;
            if (history.length < 5) {
                html += `<div class="card"><div class="no-data"><div class="emoji">📭</div><div>Нет данных для симуляции</div><div style="font-size:12px;color:var(--text-secondary);">Сначала сделайте хотя бы 5 ставок!</div></div></div>`;
            } else {
                html += `
                    <div class="card">
                        <h2 style="color:var(--text-secondary);font-size:13px;font-weight:600;margin-bottom:8px;">📊 Параметры симуляции</h2>
                        <div class="slider-container">
                            <label style="color:var(--text-secondary);font-size:12px;">Количество симуляций: <span id="simCountLabel">1000</span></label>
                            <input type="range" id="simCount" min="100" max="5000" step="100" value="1000" oninput="document.getElementById('simCountLabel').textContent=this.value">
                        </div>
                        <button class="btn-primary" onclick="runSimulation()">🎲 Запустить</button>
                        <button class="btn" onclick="document.getElementById('simResults').style.display='none'" style="margin-left:8px;">🔄 Сбросить</button>
                    </div>
                    <div id="simResults" style="display:none;">
                        <div class="sim-stats">
                            <div class="sim-stat"><div class="value gold" id="simProfit">$0</div><div class="label">💰 Ожидаемая прибыль</div></div>
                            <div class="sim-stat"><div class="value green" id="simWinrate">0%</div><div class="label">🎯 Проходимость</div></div>
                            <div class="sim-stat"><div class="value" id="simROI">0%</div><div class="label">📈 ROI</div></div>
                            <div class="sim-stat"><div class="value red" id="simRisk">0%</div><div class="label">⚠️ Риск</div></div>
                        </div>
                        <div class="card"><h2 style="color:var(--text-secondary);font-size:13px;font-weight:600;margin-bottom:8px;">📈 График симуляции</h2><div class="chart-container"><canvas id="simChart"></canvas></div></div>
                        <div class="card">
                            <h2 style="color:var(--text-secondary);font-size:13px;font-weight:600;margin-bottom:8px;">📋 Результаты</h2>
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px;">
                                <div style="color:var(--text-secondary);">Всего: <span id="simTotal" style="color:var(--text-primary);">0</span></div>
                                <div style="color:var(--text-secondary);">Выигрышей: <span id="simWins" style="color:#34d399;">0</span></div>
                                <div style="color:var(--text-secondary);">Проигрышей: <span id="simLosses" style="color:#f87171;">0</span></div>
                                <div style="color:var(--text-secondary);">Макс. прибыль: <span id="simMaxProfit" style="color:#fbbf24;">$0</span></div>
                                <div style="color:var(--text-secondary);">Мин. прибыль: <span id="simMinProfit" style="color:#f87171;">$0</span></div>
                                <div style="color:var(--text-secondary);">Средняя ставка: <span id="simAvgStake" style="color:var(--text-primary);">$0</span></div>
                            </div>
                        </div>
                        <div class="card" style="background:rgba(168,85,247,0.05);border-color:rgba(168,85,247,0.2);">
                            <h2 style="color:var(--text-secondary);font-size:13px;font-weight:600;margin-bottom:8px;">💡 Рекомендация</h2>
                            <div id="simRecommendation" style="font-size:14px;line-height:1.6;">Запустите симуляцию, чтобы получить рекомендацию!</div>
                        </div>
                    </div>
                `;
            }
            el.innerHTML = html;
        }
        async function runSimulation() {
            const count = parseInt(document.getElementById('simCount').value) || 1000;
            document.getElementById('simResults').style.display = 'block';
            try {
                const response = await fetch('/api/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ count: count }) });
                const data = await response.json();
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
                    rec.innerHTML = '✅ <b style="color:#34d399;">Отличный результат!</b> Ваша стратегия принесла бы прибыль!<br>💡 Средняя прибыль на ставку: $' + (data.profit / data.total).toFixed(2) + '<br>🔥 Лучший результат: +$' + data.max_profit;
                } else {
                    rec.innerHTML = '⚠️ <b style="color:#f87171;">Стратегия требует улучшения</b><br>💡 Попробуйте снизить сумму ставок<br>📊 Работайте над проходимостью (сейчас ' + data.winrate + '%)';
                }
                const ctx = document.getElementById('simChart');
                if (ctx) {
                    if (simChartInstance) simChartInstance.destroy();
                    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    const textColor = isDark ? '#ececec' : '#1a1a2e';
                    simChartInstance = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.labels || Array.from({length: data.history?.length || 10}, (_, i) => i + 1),
                            datasets: [{
                                label: 'Прибыль ($)',
                                data: data.history || [],
                                borderColor: data.profit > 0 ? '#34d399' : '#f87171',
                                backgroundColor: data.profit > 0 ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                                fill: true,
                                tension: 0.4,
                                pointRadius: 2,
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { labels: { color: textColor, font: { size: 10 } } } },
                            scales: {
                                x: { ticks: { color: isDark ? '#8a8aa0' : '#6a6a8a', font: { size: 8 } } },
                                y: { ticks: { color: isDark ? '#8a8aa0' : '#6a6a8a', callback: v => '$' + v, font: { size: 8 } } }
                            }
                        }
                    });
                }
            } catch (e) { alert('❌ Ошибка: ' + e); }
        }
        
        // ============================================================
        // РЕНДЕР НАСТРОЕК
        // ============================================================
        function renderSettings(data) {
            const bank = data.stats ? data.stats.bank : 1000;
            const el = document.getElementById('settings-content');
            if (!el) return;
            let html = `
                <h2 style="font-size:20px;color:var(--gradient-start);margin-bottom:4px;font-weight:700;">⚙️ Настройки</h2>
                <div style="color:var(--text-secondary);font-size:13px;margin-bottom:14px;">Управление ботом</div>
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
                            <span id="fileName" style="color:var(--text-secondary);font-size:11px;">Файл не выбран</span>
                        </div>
                    </div>
                    <div id="importStatus" class="import-status"></div>
                </div>
            `;
            el.innerHTML = html;
        }
        async function updateBank() {
            const value = document.getElementById('bankInput').value;
            try {
                const response = await fetch('/api/bank', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ bank: parseFloat(value) }) });
                const data = await response.json();
                if (data.success) { alert('✅ Банк обновлен: $' + data.bank); refreshData(); }
            } catch (e) { alert('❌ Ошибка: ' + e); }
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
                    fetch('/api/import_excel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data: json }) })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            statusDiv.textContent = '✅ Импортировано ' + data.count + ' ставок!';
                            setTimeout(() => location.reload(), 1500);
                        } else {
                            statusDiv.textContent = '❌ Ошибка: ' + data.error;
                        }
                    });
                } catch (error) { statusDiv.textContent = '❌ Ошибка: ' + error; }
            };
            reader.readAsArrayBuffer(file);
        }
        document.addEventListener('DOMContentLoaded', function() { loadPageData('dashboard'); });
    </script>
</body>
</html>
"""

# ============================================================
# API МАРШРУТЫ
# ============================================================

@app.route('/')
def index():
    return render_template_string(MAIN_HTML)

@app.route('/api/all_data')
def all_data():
    data = load_data()
    history = data.get('history', [])
    stats = get_stats(history)
    profit_data = get_profit_data(history)
    return jsonify({'stats': stats, 'history': history, 'profit_data': profit_data, 'matches': []})

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
    entries.append({'id': entry_id, 'date': datetime.now().strftime('%Y-%m-%d %H:%M'), 'text': text})
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
    data = load_data()
    history = data.get('history', [])
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
        history = load_data().get('history', [])
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок'}), 400
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
        excel_data = request.json.get('data', [])
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        data = load_data()
        history = data.get('history', [])
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
        data['history'] = history
        save_data(data)
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def update_bank():
    data = request.json
    if 'bank' in data:
        d = load_data()
        d['bank'] = data['bank']
        save_data(d)
        return jsonify({'success': True, 'bank': data['bank']})
    return jsonify({'error': 'No bank value'}), 400

@app.route('/export')
def export_data():
    return export_excel()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
