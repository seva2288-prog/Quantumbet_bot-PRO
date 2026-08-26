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
# ЕДИНЫЙ HTML ШАБЛОН (SPA - ВСЕ СТРАНИЦЫ В ОДНОМ ФАЙЛЕ)
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
        /* ============================================================
           МЛЕЧНЫЙ ПУТЬ — ЗВЁЗДНОЕ НЕБО
           ============================================================ */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #050510;
            color: #e8e8f0;
            min-height: 100vh;
            overflow-x: hidden;
            padding-bottom: 75px;
            position: relative;
        }
        
        /* ===== ЗВЁЗДНЫЙ ФОН ===== */
        .stars-container {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
            overflow: hidden;
            background: radial-gradient(ellipse at 30% 50%, #0a0a20 0%, #04040e 100%);
        }
        
        /* ===== МЛЕЧНЫЙ ПУТЬ ===== */
        .milky-way {
            position: absolute;
            top: -20%;
            left: -10%;
            width: 120%;
            height: 140%;
            background: radial-gradient(ellipse at 40% 50%, 
                rgba(100, 80, 180, 0.06) 0%, 
                rgba(60, 40, 120, 0.04) 20%, 
                rgba(30, 20, 80, 0.02) 50%,
                transparent 80%);
            transform: rotate(-15deg);
            filter: blur(60px);
            animation: milkyPulse 12s ease-in-out infinite alternate;
        }
        
        .milky-way-2 {
            position: absolute;
            bottom: -10%;
            right: -10%;
            width: 100%;
            height: 120%;
            background: radial-gradient(ellipse at 60% 40%, 
                rgba(140, 100, 200, 0.04) 0%, 
                rgba(80, 50, 150, 0.03) 30%, 
                transparent 70%);
            transform: rotate(25deg);
            filter: blur(80px);
            animation: milkyPulse2 15s ease-in-out infinite alternate;
        }
        
        @keyframes milkyPulse {
            0% { opacity: 0.6; transform: rotate(-15deg) scale(1); }
            100% { opacity: 1; transform: rotate(-10deg) scale(1.05); }
        }
        @keyframes milkyPulse2 {
            0% { opacity: 0.5; transform: rotate(25deg) scale(1); }
            100% { opacity: 0.9; transform: rotate(20deg) scale(1.1); }
        }
        
        /* ===== ЗВЁЗДЫ ===== */
        .star {
            position: absolute;
            border-radius: 50%;
            background: white;
            animation: twinkle var(--duration) ease-in-out infinite alternate;
        }
        
        @keyframes twinkle {
            0% { opacity: 0.2; transform: scale(0.8); }
            100% { opacity: 1; transform: scale(1.2); }
        }
        
        /* ===== ОСНОВНОЙ КОНТЕНТ (ПОВЕРХ ЗВЁЗД) ===== */
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 12px;
            position: relative;
            z-index: 1;
        }
        
        /* ===== ТЕМНЫЕ КАРТОЧКИ (С ЛЁГКИМ СВЕЧЕНИЕМ) ===== */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 14px;
            padding: 12px 16px;
            background: rgba(20, 20, 35, 0.7);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
        }
        .header h1 {
            font-size: 18px;
            font-weight: 700;
            background: linear-gradient(135deg, #a78bfa, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-shadow: 0 0 30px rgba(124, 58, 237, 0.15);
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
            color: #34d399;
            font-size: 10px;
            font-weight: 500;
        }
        .status-dot {
            width: 7px;
            height: 7px;
            background: #34d399;
            border-radius: 50%;
            animation: pulse-dot 2s ease-in-out infinite;
            box-shadow: 0 0 12px rgba(52, 211, 153, 0.3);
        }
        @keyframes pulse-dot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.8); }
        }
        
        .theme-toggle {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 50%;
            width: 30px;
            height: 30px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s ease;
            color: #e8e8f0;
        }
        .theme-toggle:hover {
            transform: scale(1.1);
            border-color: #7c3aed;
            box-shadow: 0 0 20px rgba(124, 58, 237, 0.2);
        }
        
        /* ===== КАРТОЧКИ ===== */
        .card {
            background: rgba(20, 20, 35, 0.6);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 12px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.3);
            transition: all 0.4s ease;
        }
        .card:hover {
            border-color: rgba(124, 58, 237, 0.15);
            box-shadow: 0 4px 40px rgba(124, 58, 237, 0.05);
        }
        
        /* ===== СТАТИСТИКА ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }
        .stat-card {
            padding: 12px 10px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            text-align: center;
            transition: all 0.4s ease;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        }
        .stat-card:hover {
            border-color: rgba(124, 58, 237, 0.2);
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
        }
        .stat-card .value {
            font-size: 20px;
            font-weight: 700;
            background: linear-gradient(135deg, #c4b5fd, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.green {
            background: linear-gradient(135deg, #34d399, #6ee7b7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.red {
            background: linear-gradient(135deg, #f87171, #fca5a5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .value.gold {
            background: linear-gradient(135deg, #fbbf24, #fcd34d);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-card .label {
            color: rgba(255, 255, 255, 0.5);
            font-size: 10px;
            margin-top: 4px;
            font-weight: 500;
            letter-spacing: 0.3px;
        }
        
        /* ===== НОВАЯ СЕТКА МЕТРИК (2 строки × 2 колонки) ===== */
        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 14px;
        }
        .metrics-grid .metric-item {
            background: rgba(255, 255, 255, 0.03);
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.15);
            transition: all 0.4s ease;
        }
        .metrics-grid .metric-item:hover {
            border-color: rgba(124, 58, 237, 0.15);
            background: rgba(255, 255, 255, 0.05);
        }
        .metrics-grid .metric-item .label {
            color: rgba(255, 255, 255, 0.5);
            font-size: 12px;
            font-weight: 500;
        }
        .metrics-grid .metric-item .value {
            font-size: 18px;
            font-weight: 700;
            color: #e8e8f0;
        }
        .metrics-grid .metric-item .value.green { color: #34d399; }
        .metrics-grid .metric-item .value.gold { color: #fbbf24; }
        
        /* ===== ТАБЛИЦА ===== */
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
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }
        th {
            color: rgba(255, 255, 255, 0.4);
            font-weight: 600;
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            background: rgba(255, 255, 255, 0.02);
            position: sticky;
            top: 0;
        }
        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }
        
        .badge {
            display: inline-block;
            padding: 1px 8px;
            border-radius: 10px;
            font-size: 9px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .badge.win {
            background: rgba(52, 211, 153, 0.12);
            color: #34d399;
            border: 1px solid rgba(52, 211, 153, 0.1);
        }
        .badge.loss {
            background: rgba(248, 113, 113, 0.12);
            color: #f87171;
            border: 1px solid rgba(248, 113, 113, 0.1);
        }
        .badge.push {
            background: rgba(251, 191, 36, 0.12);
            color: #fbbf24;
            border: 1px solid rgba(251, 191, 36, 0.1);
        }
        .badge.pending {
            background: rgba(255, 255, 255, 0.04);
            color: rgba(255, 255, 255, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .profit-positive { color: #34d399; font-weight: 600; }
        .profit-negative { color: #f87171; font-weight: 600; }
        
        /* ===== НАВИГАЦИЯ ===== */
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(10, 10, 20, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 6px 0;
            z-index: 1000;
            box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.5);
        }
        .bottom-nav .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            color: rgba(255, 255, 255, 0.35);
            font-size: 9px;
            transition: all 0.3s ease;
            padding: 4px 10px;
            border-radius: 8px;
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
            transition: all 0.3s ease;
        }
        .bottom-nav .nav-item .label {
            font-size: 8px;
            margin-top: 2px;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        .bottom-nav .nav-item.active {
            color: #a78bfa;
        }
        .bottom-nav .nav-item.active .icon {
            transform: scale(1.05);
            text-shadow: 0 0 20px rgba(167, 139, 250, 0.3);
        }
        .bottom-nav .nav-item.active::after {
            content: '';
            position: absolute;
            top: -1px;
            left: 50%;
            transform: translateX(-50%);
            width: 20px;
            height: 2px;
            background: linear-gradient(90deg, #7c3aed, #a78bfa);
            border-radius: 2px;
            box-shadow: 0 0 20px rgba(124, 58, 237, 0.3);
        }
        .bottom-nav .nav-item:hover {
            color: rgba(255, 255, 255, 0.7);
        }
        .bottom-nav .nav-item:active {
            transform: scale(0.92);
        }
        
        /* ===== ПРОЧЕЕ ===== */
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 10px;
        }
        .card-header h2 {
            color: rgba(255, 255, 255, 0.5);
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }
        .card-header .count {
            color: rgba(255, 255, 255, 0.3);
            font-size: 11px;
        }
        
        .chart-container {
            position: relative;
            height: 140px;
            width: 100%;
        }
        
        .btn {
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(255, 255, 255, 0.03);
            color: rgba(255, 255, 255, 0.6);
            cursor: pointer;
            font-size: 11px;
            transition: all 0.3s ease;
        }
        .btn:hover {
            background: rgba(124, 58, 237, 0.1);
            border-color: rgba(124, 58, 237, 0.2);
            color: #e8e8f0;
            box-shadow: 0 0 20px rgba(124, 58, 237, 0.05);
        }
        .btn-success {
            background: linear-gradient(135deg, #059669, #10b981);
            color: #fff;
            border-color: transparent;
        }
        .btn-success:hover {
            background: linear-gradient(135deg, #047857, #059669);
            border-color: transparent;
            box-shadow: 0 0 30px rgba(16, 185, 129, 0.2);
        }
        
        .no-data {
            text-align: center;
            color: rgba(255, 255, 255, 0.3);
            padding: 20px 0;
        }
        .no-data .emoji { font-size: 30px; margin-bottom: 6px; }
        
        .footer {
            text-align: center;
            color: rgba(255, 255, 255, 0.15);
            font-size: 9px;
            margin-top: 16px;
            padding: 10px 0;
            border-top: 1px solid rgba(255, 255, 255, 0.03);
        }
        
        .loader {
            display: none;
            text-align: center;
            padding: 20px;
            color: rgba(255, 255, 255, 0.4);
        }
        .loader.active { display: block; }
        .loader .spinner {
            width: 30px;
            height: 30px;
            border: 2px solid rgba(255, 255, 255, 0.06);
            border-top-color: #a78bfa;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 8px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .page {
            display: none;
            animation: fadeIn 0.2s ease;
        }
        .page.active { display: block; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .edit-row {
            background: rgba(255, 255, 255, 0.02);
            padding: 6px;
            border-radius: 6px;
            display: none;
            margin-top: 4px;
        }
        .edit-row.active { display: table-row; }
        .edit-row input, .edit-row select {
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: #e8e8f0;
            padding: 2px 4px;
            border-radius: 4px;
            font-size: 10px;
            margin-right: 2px;
        }
        .edit-row .btn { padding: 2px 8px; font-size: 10px; }
        .edit-btn { cursor: pointer; color: rgba(255, 255, 255, 0.3); font-size: 11px; }
        .edit-btn:hover { color: #a78bfa; }
        
        /* ===== МАТЧИ ===== */
        .match-tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 10px; }
        .match-tab {
            padding: 4px 12px;
            border-radius: 14px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: transparent;
            color: rgba(255, 255, 255, 0.4);
        }
        .match-tab.active {
            background: rgba(124, 58, 237, 0.2);
            color: #a78bfa;
            border-color: rgba(124, 58, 237, 0.15);
        }
        .match-card {
            background: rgba(20, 20, 35, 0.5);
            backdrop-filter: blur(12px);
            padding: 10px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            margin-bottom: 8px;
        }
        .match-title { font-size: 13px; font-weight: 600; color: #e8e8f0; }
        .match-league { color: rgba(255, 255, 255, 0.35); font-size: 11px; }
        .match-xg { color: #a78bfa; font-size: 11px; }
        .match-bets { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 3px; }
        .bet-item {
            background: rgba(255, 255, 255, 0.03);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            color: rgba(255, 255, 255, 0.6);
        }
        
        /* ===== НАСТРОЙКИ ===== */
        .setting-group {
            background: rgba(20, 20, 35, 0.5);
            backdrop-filter: blur(12px);
            padding: 10px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            margin-bottom: 8px;
        }
        .setting-group h2 {
            color: rgba(255, 255, 255, 0.4);
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 6px;
            letter-spacing: 0.3px;
        }
        .setting-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            flex-wrap: wrap;
            gap: 4px;
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-item .label { font-size: 12px; color: #e8e8f0; }
        .setting-item .desc { color: rgba(255, 255, 255, 0.3); font-size: 10px; }
        .input-group { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
        .input-group input {
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: #e8e8f0;
            padding: 4px 6px;
            border-radius: 4px;
            width: 80px;
            font-size: 11px;
        }
        .input-group button {
            background: linear-gradient(135deg, #7c3aed, #6d28d9);
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.3s ease;
        }
        .input-group button:hover {
            box-shadow: 0 0 20px rgba(124, 58, 237, 0.2);
        }
        .toggle {
            width: 36px;
            height: 20px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            cursor: pointer;
            position: relative;
            transition: 0.3s ease;
        }
        .toggle.active { background: rgba(124, 58, 237, 0.5); }
        .toggle .dot {
            width: 14px;
            height: 14px;
            background: #fff;
            border-radius: 50%;
            position: absolute;
            top: 3px;
            left: 3px;
            transition: 0.3s ease;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
        }
        .toggle.active .dot { left: 19px; }
        .file-input-label {
            display: inline-block;
            padding: 4px 10px;
            background: linear-gradient(135deg, #7c3aed, #6d28d9);
            color: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.3s ease;
        }
        .file-input-label:hover {
            box-shadow: 0 0 20px rgba(124, 58, 237, 0.2);
        }
        .import-status { color: rgba(255, 255, 255, 0.3); font-size: 10px; margin-top: 4px; }
        
        /* ===== СИМУЛЯТОР ===== */
        .sim-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
            margin-bottom: 10px;
        }
        .sim-stat {
            background: rgba(255, 255, 255, 0.02);
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }
        .sim-stat .value { font-size: 18px; font-weight: 700; }
        .sim-stat .value.green { color: #34d399; }
        .sim-stat .value.red { color: #f87171; }
        .sim-stat .value.gold { color: #fbbf24; }
        .sim-stat .label { color: rgba(255, 255, 255, 0.35); font-size: 10px; margin-top: 4px; }
        
        .slider-container { margin: 10px 0; }
        .slider-container input[type="range"] {
            width: 100%;
            height: 4px;
            background: rgba(255, 255, 255, 0.06);
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
            background: linear-gradient(135deg, #7c3aed, #6d28d9);
            cursor: pointer;
            box-shadow: 0 0 20px rgba(124, 58, 237, 0.2);
        }
        .btn-primary {
            background: linear-gradient(135deg, #7c3aed, #6d28d9);
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.3s ease;
        }
        .btn-primary:hover {
            box-shadow: 0 0 30px rgba(124, 58, 237, 0.2);
        }
        .btn-primary:active { transform: scale(0.95); }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .header { flex-direction: column; align-items: stretch; gap: 6px; padding: 10px 12px; }
            .header h1 { font-size: 16px; text-align: center; }
            .header-controls { justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .metrics-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
            .metrics-grid .metric-item { padding: 6px 10px; }
            .metrics-grid .metric-item .value { font-size: 14px; }
            .card { padding: 10px; }
            table { font-size: 9px; min-width: 450px; }
            th, td { padding: 3px 4px; }
            .chart-container { height: 100px; }
            .bottom-nav .nav-item { padding: 2px 6px; min-width: 44px; }
            .bottom-nav .nav-item .icon { font-size: 16px; }
            .bottom-nav .nav-item .label { font-size: 7px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 4px; }
            .stat-card { padding: 8px; }
            .stat-card .value { font-size: 16px; }
            .metrics-grid { grid-template-columns: 1fr; }
            .bottom-nav .nav-item { min-width: 40px; padding: 2px 4px; }
            .bottom-nav .nav-item .icon { font-size: 14px; }
        }
    </style>
</head>
<body>

<!-- ===== ЗВЁЗДНОЕ НЕБО ===== -->
<div class="stars-container" id="starsContainer">
    <div class="milky-way"></div>
    <div class="milky-way-2"></div>
    <!-- Звёзды генерируются JS -->
</div>

<div class="container">
    <!-- HEADER -->
    <div class="header">
        <h1>🤖 Quantum Bet Bot</h1>
        <div class="header-controls">
            <div class="status">
                <span class="status-dot"></span>
                <span>Система активна</span>
                <span style="color:rgba(255,255,255,0.2);">|</span>
                <span style="color:rgba(255,255,255,0.2);">v12 PRO</span>
            </div>
            <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">🌙</button>
            <button class="theme-toggle" onclick="refreshData()" style="font-size:12px;">🔄</button>
        </div>
    </div>

    <!-- ===== СТРАНИЦЫ ===== -->
    <div id="page-dashboard" class="page active"><div id="dashboard-content"></div></div>
    <div id="page-matches" class="page"><div id="matches-content"></div></div>
    <div id="page-stats" class="page"><div id="stats-content"></div></div>
    <div id="page-simulator" class="page"><div id="simulator-content"></div></div>
    <div id="page-settings" class="page"><div id="settings-content"></div></div>

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
    <button class="nav-item" data-page="stats">
        <span class="icon">📈</span>
        <span class="label">Статистика</span>
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
    // ============================================================
    // ГЕНЕРАЦИЯ ЗВЁЗД
    // ============================================================
    (function generateStars() {
        const container = document.getElementById('starsContainer');
        const count = 250;
        for (let i = 0; i < count; i++) {
            const star = document.createElement('div');
            star.className = 'star';
            const size = 0.5 + Math.random() * 2.5;
            star.style.width = size + 'px';
            star.style.height = size + 'px';
            star.style.left = Math.random() * 100 + '%';
            star.style.top = Math.random() * 100 + '%';
            star.style.setProperty('--duration', (2 + Math.random() * 4) + 's');
            star.style.animationDelay = (Math.random() * 5) + 's';
            star.style.opacity = 0.3 + Math.random() * 0.7;
            container.appendChild(star);
        }
    })();

    // ============================================================
    // ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
    // ============================================================
    let cachedData = null;
    let chartInstance = null;
    let simChartInstance = null;
    let currentPage = 'dashboard';
    let isLoading = false;

    // ============================================================
    // ТЕМА
    // ============================================================
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
    // НАВИГАЦИЯ
    // ============================================================
    document.querySelectorAll('.bottom-nav .nav-item').forEach(btn => {
        btn.addEventListener('click', function(e) {
            const page = this.dataset.page;
            switchPage(page);
        });
        btn.addEventListener('touchstart', function(e) {}, { passive: true });
    });

    function switchPage(page) {
        if (page === currentPage && document.getElementById('page-' + page).classList.contains('active')) return;

        document.querySelectorAll('.bottom-nav .nav-item').forEach(b => b.classList.remove('active'));
        document.querySelector(`.bottom-nav .nav-item[data-page="${page}"]`).classList.add('active');

        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById('page-' + page).classList.add('active');

        currentPage = page;
        loadPageData(page);
    }

    // ============================================================
    // ЗАГРУЗКА ДАННЫХ
    // ============================================================
    async function loadPageData(page) {
        if (isLoading) return;

        const contentId = page + '-content';
        const contentEl = document.getElementById(contentId);

        if (page !== 'dashboard' && cachedData && contentEl.innerHTML) {
            return;
        }

        isLoading = true;
        contentEl.innerHTML = '<div class="loader active"><div class="spinner"></div><div style="color:rgba(255,255,255,0.4);font-size:12px;margin-top:6px;">Загрузка...</div></div>';

        try {
            const response = await fetch('/api/all_data?t=' + Date.now());
            const data = await response.json();
            cachedData = data;

            switch(page) {
                case 'dashboard': renderDashboard(data); break;
                case 'matches': renderMatches(data); break;
                case 'stats': renderStats(data); break;
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

    // ============================================================
    // РЕНДЕР ДАШБОРДА
    // ============================================================
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

            <!-- ===== НОВЫЙ БЛОК: 2 СТРОКИ × 2 КОЛОНКИ ===== -->
            <div class="metrics-grid">
                <div class="metric-item"><span class="label">📊 Всего ставок</span><span class="value">${s.total_bets}</span></div>
                <div class="metric-item"><span class="label">🎯 Проходимость</span><span class="value green">${s.winrate}%</span></div>
                <div class="metric-item"><span class="label">📈 ROI</span><span class="value gold">${s.roi}%</span></div>
                <div class="metric-item"><span class="label">📅 Средняя ставка</span><span class="value">$${s.avg_stake}</span></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2>📈 График прибыли</h2>
                    <span style="font-size:9px;color:rgba(255,255,255,0.3);">За последние 7 дней</span>
                </div>
                <div class="chart-container">
                    <canvas id="profitChart"></canvas>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2>📋 Все ставки</h2>
                    <span class="count">Всего: ${history.length}</span>
                </div>
                <div class="scrollable-table">
                    <div class="table-wrapper">
                        <table>
                            <thead><tr>
                                <th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th><th>✏️</th>
                            </tr></thead>
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
                                <select id="edit_result_${realIdx}" style="padding:2px 4px;border-radius:3px;border:1px solid rgba(255,255,255,0.06);background:rgba(0,0,0,0.4);color:#e8e8f0;font-size:10px;">
                                    <option value="win" ${bet.result === 'win' ? 'selected' : ''}>win</option>
                                    <option value="loss" ${bet.result === 'loss' ? 'selected' : ''}>loss</option>
                                    <option value="push" ${bet.result === 'push' ? 'selected' : ''}>push</option>
                                    <option value="pending" ${bet.result === 'pending' ? 'selected' : ''}>pending</option>
                                </select>
                                <button class="btn btn-success" onclick="saveEdit(${realIdx})" style="padding:2px 6px;font-size:9px;">💾</button>
                                <button class="btn btn-danger" onclick="deleteBet(${realIdx})" style="padding:2px 6px;font-size:9px;background:rgba(248,113,113,0.15);color:#f87171;border-color:rgba(248,113,113,0.1);">🗑️</button>
                                <button class="btn" onclick="toggleEdit(${realIdx})" style="padding:2px 6px;font-size:9px;">✖</button>
                            </div>
                        </td>
                    </tr>
                `;
            });
        }

        html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('dashboard-content').innerHTML = html;
        setTimeout(() => renderChart(data.profit_data), 50);
    }

    // ============================================================
    // ГРАФИК
    // ============================================================
    function renderChart(profitData) {
        const ctx = document.getElementById('profitChart');
        if (!ctx) return;

        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
        }

        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const data = profitData || { dates: ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], profits: [0,0,0,0,0,0,0] };

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{
                    label: 'Прибыль ($)',
                    data: data.profits,
                    borderColor: '#a78bfa',
                    backgroundColor: 'rgba(167,139,250,0.08)',
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#a78bfa',
                    pointBorderColor: 'rgba(20,20,35,0.8)',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)',
                            font: { size: 9 }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
                            font: { size: 8 }
                        },
                        grid: { color: 'rgba(255,255,255,0.03)' }
                    },
                    y: {
                        ticks: {
                            color: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
                            callback: function(value) { return '$' + value; },
                            font: { size: 8 }
                        },
                        grid: { color: 'rgba(255,255,255,0.03)' }
                    }
                }
            }
        });
    }

    // ============================================================
    // РЕНДЕР МАТЧЕЙ
    // ============================================================
    function renderMatches(data) {
        const matches = data.matches || [];
        let html = `
            <h2 style="font-size:18px;color:#a78bfa;margin-bottom:4px;">⚽ Матчи</h2>
            <div style="color:rgba(255,255,255,0.4);font-size:12px;margin-bottom:10px;">Прогнозы и валуйные ставки</div>
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

    // ============================================================
    // РЕНДЕР СТАТИСТИКИ
    // ============================================================
    function renderStats(data) {
        const s = data.stats;
        const history = data.history || [];
        let html = `
            <h2 style="font-size:18px;color:#a78bfa;margin-bottom:4px;">📈 Статистика</h2>
            <div style="color:rgba(255,255,255,0.4);font-size:12px;margin-bottom:10px;">Детальный анализ ваших ставок</div>
            <div class="card">
                <h2 style="color:rgba(255,255,255,0.4);font-size:12px;font-weight:600;margin-bottom:6px;">📊 Общая статистика</h2>
                <div style="display:flex;gap:10px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:60px;"><div style="font-size:18px;font-weight:700;color:#a78bfa;">${s.total_bets}</div><div style="color:rgba(255,255,255,0.3);font-size:10px;">Всего ставок</div></div>
                    <div style="flex:1;min-width:60px;"><div style="font-size:18px;font-weight:700;color:#34d399;">${s.wins}</div><div style="color:rgba(255,255,255,0.3);font-size:10px;">Выигрыши</div></div>
                    <div style="flex:1;min-width:60px;"><div style="font-size:18px;font-weight:700;color:#f87171;">${s.losses}</div><div style="color:rgba(255,255,255,0.3);font-size:10px;">Проигрыши</div></div>
                    <div style="flex:1;min-width:60px;"><div style="font-size:18px;font-weight:700;color:#fbbf24;">$${s.profit}</div><div style="color:rgba(255,255,255,0.3);font-size:10px;">Прибыль</div></div>
                </div>
            </div>
            <div class="card">
                <h2 style="color:rgba(255,255,255,0.4);font-size:12px;font-weight:600;margin-bottom:6px;">📋 Все ставки</h2>
                <div class="table-wrapper">
                    <table>
                        <thead><tr><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>EV</th><th>Результат</th><th>Прибыль</th></tr></thead>
                        <tbody>
        `;
        if (history.length === 0) {
            html += `<tr><td colspan="8" class="no-data">Нет данных</td></tr>`;
        } else {
            history.forEach(bet => {
                html += `
                    <tr>
                        <td style="font-size:9px;">${bet.date}</td>
                        <td>${bet.home} vs ${bet.away}</td>
                        <td>${bet.home_goals !== null && bet.away_goals !== null ? bet.home_goals + ' - ' + bet.away_goals : '-'}</td>
                        <td>${bet.bet}</td>
                        <td>${bet.odds}</td>
                        <td>${bet.ev}%</td>
                        <td><span class="badge ${bet.result}">${bet.result}</span></td>
                        <td>$${bet.profit}</td>
                    </tr>
                `;
            });
        }
        html += `</tbody></table></div></div>`;
        document.getElementById('stats-content').innerHTML = html;
    }

    // ============================================================
    // РЕНДЕР СИМУЛЯТОРА
    // ============================================================
    function renderSimulator(data) {
        const history = data.history || [];
        let html = `
            <h2 style="font-size:18px;color:#a78bfa;margin-bottom:4px;">🎲 Симулятор</h2>
            <div style="color:rgba(255,255,255,0.4);font-size:12px;margin-bottom:10px;">Узнай, сколько ты мог бы заработать!</div>
        `;
        if (history.length < 5) {
            html += `
                <div class="card">
                    <div class="no-data">
                        <div class="emoji">📭</div>
                        <div>Нет данных для симуляции</div>
                        <div style="font-size:11px;color:rgba(255,255,255,0.3);">Сначала сделайте хотя бы 5 ставок!</div>
                    </div>
                </div>
            `;
        } else {
            html += `
                <div class="card">
                    <h2 style="color:rgba(255,255,255,0.4);font-size:12px;font-weight:600;margin-bottom:6px;">📊 Параметры симуляции</h2>
                    <div class="slider-container">
                        <label style="color:rgba(255,255,255,0.4);font-size:12px;">Количество симуляций: <span id="simCountLabel">1000</span></label>
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
                        <h2 style="color:rgba(255,255,255,0.4);font-size:12px;font-weight:600;margin-bottom:6px;">📈 График симуляции</h2>
                        <div class="chart-container"><canvas id="simChart"></canvas></div>
                    </div>
                    <div class="card">
                        <h2 style="color:rgba(255,255,255,0.4);font-size:12px;font-weight:600;margin-bottom:6px;">📋 Результаты</h2>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px;" id="simDetails">
                            <div style="color:rgba(255,255,255,0.4);">Всего: <span id="simTotal" style="color:#e8e8f0;">0</span></div>
                            <div style="color:rgba(255,255,255,0.4);">Выигрышей: <span id="simWins" style="color:#34d399;">0</span></div>
                            <div style="color:rgba(255,255,255,0.4);">Проигрышей: <span id="simLosses" style="color:#f87171;">0</span></div>
                            <div style="color:rgba(255,255,255,0.4);">Макс. прибыль: <span id="simMaxProfit" style="color:#fbbf24;">$0</span></div>
                            <div style="color:rgba(255,255,255,0.4);">Мин. прибыль: <span id="simMinProfit" style="color:#f87171;">$0</span></div>
                            <div style="color:rgba(255,255,255,0.4);">Средняя ставка: <span id="simAvgStake" style="color:#e8e8f0;">$0</span></div>
                        </div>
                    </div>
                    <div class="card" style="background:rgba(124,58,237,0.05);border-color:rgba(124,58,237,0.1);">
                        <h2 style="color:rgba(255,255,255,0.4);font-size:12px;font-weight:600;margin-bottom:6px;">💡 Рекомендация</h2>
                        <div id="simRecommendation" style="font-size:13px;line-height:1.5;color:rgba(255,255,255,0.6);">Запустите симуляцию, чтобы получить рекомендацию!</div>
                    </div>
                </div>
            `;
        }
        document.getElementById('simulator-content').innerHTML = html;
    }

    // ============================================================
    // РЕНДЕР НАСТРОЕК
    // ============================================================
    function renderSettings(data) {
        const bank = data.stats ? data.stats.bank : 1000;
        let html = `
            <h2 style="font-size:18px;color:#a78bfa;margin-bottom:4px;">⚙️ Настройки</h2>
            <div style="color:rgba(255,255,255,0.4);font-size:12px;margin-bottom:10px;">Управление ботом</div>
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
                        <span id="fileName" style="color:rgba(255,255,255,0.3);font-size:10px;">Файл не выбран</span>
                    </div>
                </div>
                <div id="importStatus" class="import-status"></div>
            </div>
        `;
        document.getElementById('settings-content').innerHTML = html;
    }

    // ============================================================
    // ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
    // ============================================================
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
                rec.innerHTML = '✅ <b style="color:#34d399;">Отличный результат!</b> Ваша стратегия принесла бы прибыль!<br>💡 Средняя прибыль на ставку: $' + (data.profit / data.total).toFixed(2) + '<br>🔥 Лучший результат: +$' + data.max_profit;
            } else {
                rec.innerHTML = '⚠️ <b style="color:#f87171;">Стратегия требует улучшения</b><br>💡 Попробуйте снизить сумму ставок<br>📊 Работайте над проходимостью (сейчас ' + data.winrate + '%)';
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
                            borderColor: data.profit > 0 ? '#34d399' : '#f87171',
                            backgroundColor: data.profit > 0 ? 'rgba(52,211,153,0.08)' : 'rgba(248,113,113,0.08)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { labels: { color: isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)', font: { size: 9 } } }
                        },
                        scales: {
                            x: { ticks: { color: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)', font: { size: 8 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
                            y: { ticks: { color: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)', callback: function(value) { return '$' + value; }, font: { size: 8 } }, grid: { color: 'rgba(255,255,255,0.03)' } }
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

    document.addEventListener('DOMContentLoaded', function() {
        loadPageData('dashboard');
    });
</script>
</body>
</html>
"""

# ============================================================
# API - ВСЕ ДАННЫЕ ЗА ОДИН ЗАПРОС
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
def index():
    return render_template_string(MAIN_HTML)

@app.route('/api/all_data')
def all_data():
    """Возвращает все данные за один запрос"""
    stats_data, history = get_data_from_bot()
    
    # Получаем данные для графика
    profit_data = get_profit_data(history)
    
    # Получаем матчи
    try:
        response = requests.get(f'{BOT_URL}/matches', timeout=10)
        matches = response.json() if response.status_code == 200 else []
    except:
        matches = []
    
    bank = stats_data.get('bank', 1000)
    total_bets = stats_data.get('total_bets', 0)
    wins = stats_data.get('wins', 0)
    losses = stats_data.get('losses', 0)
    total_profit = stats_data.get('profit', 0)
    winrate = stats_data.get('winrate', 0)
    roi = stats_data.get('roi', 0)
    avg_stake = stats_data.get('avg_stake', 0)
    
    return jsonify({
        'stats': {
            'bank': bank,
            'total_bets': total_bets,
            'wins': wins,
            'losses': losses,
            'profit': round(total_profit, 2),
            'winrate': winrate,
            'roi': roi,
            'avg_stake': avg_stake
        },
        'history': history,
        'profit_data': profit_data,
        'matches': matches
    })

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
    
    return {'dates': dates, 'profits': profits}

# ============================================================
# ОСТАЛЬНЫЕ API МАРШРУТЫ
# ============================================================

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
    try:
        response = requests.get(f'{BOT_URL}/export', timeout=30)
        if response.status_code == 200:
            return response.content, 200, {'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
    except:
        pass
    return "Нет данных для экспорта", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
