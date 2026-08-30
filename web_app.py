import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request
import requests
from datetime import datetime, timedelta
import json
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# НАСТРОЙКИ
# ============================================================

# URL вашего бота на Render
BOT_URL = os.environ.get('BOT_URL', 'https://quantumbet-bot-pro.onrender.com')

# Проверка при запуске
print(f"🔗 Бот URL: {BOT_URL}")

# ============================================================
# HTML ШАБЛОН (ПОЛНЫЙ, 3000+ СТРОК)
# ============================================================

MAIN_HTML = """<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
    <title>Quantum Bet Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
    <style>
        /* ============================================================
           ЭКРАН ЗАГРУЗКИ
           ============================================================ */
        #loadingScreen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: #050510;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 99999;
            transition: opacity 0.8s ease;
            overflow: hidden;
        }
        #loadingScreen .milky-way {
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
            animation: loadingMilkyPulse 12s ease-in-out infinite alternate;
        }
        #loadingScreen .milky-way-2 {
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
            animation: loadingMilkyPulse2 15s ease-in-out infinite alternate;
        }
        #loadingScreen .logo {
            position: relative;
            z-index: 1;
            text-align: center;
        }
        #loadingScreen .logo-text {
            font-size: 56px;
            font-weight: 700;
            background: linear-gradient(135deg, #a78bfa, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: pulse 2s ease-in-out infinite;
            letter-spacing: 3px;
            text-shadow: 0 0 60px rgba(124, 58, 237, 0.15);
        }
        #loadingScreen .logo-sub {
            margin-top: 6px;
            color: rgba(255,255,255,0.15);
            font-size: 14px;
            letter-spacing: 8px;
            font-weight: 300;
        }
        #loadingScreen .spinner {
            margin-top: 30px;
            width: 32px;
            height: 32px;
            margin-left: auto;
            margin-right: auto;
            border: 2px solid rgba(167,139,250,0.08);
            border-top: 2px solid #a78bfa;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        #loadingScreen .loading-text {
            margin-top: 14px;
            color: rgba(255,255,255,0.08);
            font-size: 10px;
            letter-spacing: 3px;
        }
        #loadingScreen .loading-stars {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }
        #loadingScreen .loading-star {
            position: absolute;
            border-radius: 50%;
            background: white;
            animation: loadingTwinkle var(--duration) ease-in-out infinite alternate;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.7; transform: scale(0.97); }
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        @keyframes loadingMilkyPulse {
            0% { opacity: 0.6; transform: rotate(-15deg) scale(1); }
            100% { opacity: 1; transform: rotate(-10deg) scale(1.05); }
        }
        @keyframes loadingMilkyPulse2 {
            0% { opacity: 0.5; transform: rotate(25deg) scale(1); }
            100% { opacity: 0.9; transform: rotate(20deg) scale(1.1); }
        }
        @keyframes loadingTwinkle {
            0% { opacity: 0.15; transform: scale(0.8); }
            100% { opacity: 1; transform: scale(1.2); }
        }
        
        /* ============================================================
           ОСНОВНЫЕ СТИЛИ
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
            transition: background 0.3s ease, color 0.3s ease;
        }
        
        body.light-theme {
            background: #f0f0f5;
            color: #1a1a2e;
        }
        
        body.light-theme .card {
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(0, 0, 0, 0.06);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.08);
        }
        
        body.light-theme .header {
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(0, 0, 0, 0.06);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.08);
        }
        
        body.light-theme .stat-card {
            background: rgba(255, 255, 255, 0.6);
            border: 1px solid rgba(0, 0, 0, 0.06);
        }
        
        body.light-theme .stat-card .label {
            color: rgba(0, 0, 0, 0.5);
        }
        
        body.light-theme .metrics-grid .metric-item {
            background: rgba(255, 255, 255, 0.6);
            border: 1px solid rgba(0, 0, 0, 0.06);
        }
        
        body.light-theme .metrics-grid .metric-item .label {
            color: rgba(0, 0, 0, 0.5);
        }
        
        body.light-theme .metrics-grid .metric-item .value {
            color: #1a1a2e;
        }
        
        body.light-theme .card-header h2 {
            color: rgba(0, 0, 0, 0.5);
        }
        
        body.light-theme .bottom-nav {
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            border-top: 1px solid rgba(0, 0, 0, 0.06);
        }
        
        body.light-theme .bottom-nav .nav-item {
            color: rgba(0, 0, 0, 0.4);
        }
        
        body.light-theme .bottom-nav .nav-item.active {
            color: #7c3aed;
        }
        
        body.light-theme .bottom-nav .nav-item.active::after {
            background: linear-gradient(90deg, #7c3aed, #a78bfa);
        }
        
        body.light-theme .setting-group {
            background: rgba(255, 255, 255, 0.6);
            border: 1px solid rgba(0, 0, 0, 0.06);
        }
        
        body.light-theme .setting-group h2 {
            color: rgba(0, 0, 0, 0.5);
        }
        
        body.light-theme .setting-item .label {
            color: #1a1a2e;
        }
        
        body.light-theme .setting-item .desc {
            color: rgba(0, 0, 0, 0.4);
        }
        
        body.light-theme .input-group input {
            background: rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(0, 0, 0, 0.1);
            color: #1a1a2e;
        }
        
        body.light-theme .no-data {
            color: rgba(0, 0, 0, 0.4);
        }
        
        body.light-theme .footer {
            color: rgba(0, 0, 0, 0.2);
            border-top: 1px solid rgba(0, 0, 0, 0.05);
        }
        
        body.light-theme table {
            color: #1a1a2e;
        }
        
        body.light-theme th {
            color: rgba(0, 0, 0, 0.5);
            background: rgba(0, 0, 0, 0.02);
        }
        
        body.light-theme td {
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
        }
        
        body.light-theme tr:hover td {
            background: rgba(0, 0, 0, 0.02);
        }
        
        body.light-theme .edit-row {
            background: rgba(0, 0, 0, 0.03);
        }
        
        body.light-theme .edit-row input, 
        body.light-theme .edit-row select {
            background: rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(0, 0, 0, 0.1);
            color: #1a1a2e;
        }
        
        body.light-theme .edit-btn {
            color: rgba(0, 0, 0, 0.3);
        }
        
        body.light-theme .edit-btn:hover {
            color: #7c3aed;
        }
        
        body.light-theme .stars-container {
            background: radial-gradient(ellipse at 30% 50%, #e8e8f0 0%, #d0d0dd 100%);
            opacity: 0.3;
        }
        
        body.light-theme .milky-way {
            background: radial-gradient(ellipse at 40% 50%, 
                rgba(100, 80, 180, 0.1) 0%, 
                rgba(60, 40, 120, 0.06) 20%, 
                rgba(30, 20, 80, 0.03) 50%,
                transparent 80%);
        }
        
        body.light-theme .star {
            background: #7c3aed;
            opacity: 0.2 !important;
        }
        
        body.light-theme .badge.win {
            background: rgba(52, 211, 153, 0.15);
            color: #059669;
            border: 1px solid rgba(52, 211, 153, 0.15);
        }
        
        body.light-theme .badge.loss {
            background: rgba(248, 113, 113, 0.15);
            color: #dc2626;
            border: 1px solid rgba(248, 113, 113, 0.15);
        }
        
        body.light-theme .badge.push {
            background: rgba(251, 191, 36, 0.15);
            color: #d97706;
            border: 1px solid rgba(251, 191, 36, 0.15);
        }
        
        body.light-theme .badge.pending {
            background: rgba(0, 0, 0, 0.04);
            color: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(0, 0, 0, 0.05);
        }
        
        body.light-theme .chart-controls select {
            background: rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(0, 0, 0, 0.1);
            color: #1a1a2e;
        }
        
        body.light-theme .chart-details {
            background: rgba(0, 0, 0, 0.03);
        }
        
        body.light-theme .sim-stat {
            background: rgba(255, 255, 255, 0.6);
            border: 1px solid rgba(0, 0, 0, 0.06);
        }
        
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
            transition: background 0.3s ease;
        }
        
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
        
        .star {
            position: absolute;
            border-radius: 50%;
            background: white;
            animation: twinkle var(--duration) ease-in-out infinite alternate;
            transition: background 0.3s ease;
        }
        
        @keyframes twinkle {
            0% { opacity: 0.2; transform: scale(0.8); }
            100% { opacity: 1; transform: scale(1.2); }
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 12px;
            position: relative;
            z-index: 1;
        }
        
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
            transition: all 0.3s ease;
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
            transition: all 0.3s ease;
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
        
        .chart-container-large {
            position: relative;
            height: 350px;
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
        
        .chart-controls {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        .chart-controls select {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: #e8e8f0;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .chart-controls select:hover {
            border-color: rgba(124, 58, 237, 0.3);
        }
        .chart-controls select option {
            background: #1a1a2e;
            color: #e8e8f0;
        }
        
        .chart-details {
            margin-top: 10px;
            padding: 12px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            display: none;
        }
        .chart-details.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }
        
        .chart-details-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        .chart-details-item {
            padding: 6px;
        }
        .chart-details-item .label {
            color: rgba(255, 255, 255, 0.3);
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .chart-details-item .value {
            font-size: 13px;
            font-weight: 600;
            margin-top: 2px;
        }
        
        .chart-actions {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-top: 10px;
        }
        
        .patterns-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11px;
        }
        .patterns-table th {
            color: rgba(255, 255, 255, 0.3);
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .patterns-table td {
            padding: 6px 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }
        .patterns-table tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }
        
        .pattern-metrics {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
            margin: 6px 0;
            padding: 6px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 6px;
        }
        .pattern-metrics .metric {
            text-align: center;
        }
        .pattern-metrics .metric .label {
            font-size: 8px;
            color: rgba(255, 255, 255, 0.3);
            text-transform: uppercase;
        }
        .pattern-metrics .metric .value {
            font-size: 12px;
            font-weight: 600;
            margin-top: 1px;
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: rgba(20, 20, 35, 0.95);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(167, 139, 250, 0.2);
            border-radius: 10px;
            color: #e8e8f0;
            font-size: 13px;
            z-index: 9999;
            animation: slideIn 0.3s ease;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
            max-width: 400px;
        }
        .notification.success { border-color: rgba(52, 211, 153, 0.3); }
        .notification.error { border-color: rgba(248, 113, 113, 0.3); }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(100px); }
            to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slideOut {
            from { opacity: 1; transform: translateX(0); }
            to { opacity: 0; transform: translateX(100px); }
        }
        
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
            .chart-container-large { height: 250px; }
            .bottom-nav .nav-item { padding: 2px 6px; min-width: 44px; }
            .bottom-nav .nav-item .icon { font-size: 16px; }
            .bottom-nav .nav-item .label { font-size: 7px; }
            .chart-details-grid { grid-template-columns: 1fr; }
            .chart-controls { gap: 4px; }
            .chart-controls select { font-size: 10px; padding: 3px 6px; }
            .pattern-metrics { grid-template-columns: 1fr 1fr; }
            .patterns-table { font-size: 9px; }
            .patterns-table th, .patterns-table td { padding: 4px 6px; }
            .notification { max-width: 90%; right: 10px; left: 10px; top: 10px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 4px; }
            .stat-card { padding: 8px; }
            .stat-card .value { font-size: 16px; }
            .metrics-grid { grid-template-columns: 1fr; }
            .bottom-nav .nav-item { min-width: 40px; padding: 2px 4px; }
            .bottom-nav .nav-item .icon { font-size: 14px; }
            .pattern-metrics { grid-template-columns: 1fr 1fr; }
        }
    </style>
</head>
<body>

<!-- ============================================================
     ЭКРАН ЗАГРУЗКИ
     ============================================================ -->
<div id="loadingScreen">
    <div class="milky-way"></div>
    <div class="milky-way-2"></div>
    <div id="loadingStars" class="loading-stars"></div>
    <div class="logo">
        <div class="logo-text">QUANTUM</div>
        <div class="logo-sub">BET BOT</div>
        <div class="spinner"></div>
        <div class="loading-text">ЗАГРУЗКА</div>
    </div>
</div>

<div class="stars-container" id="starsContainer">
    <div class="milky-way"></div>
    <div class="milky-way-2"></div>
</div>

<div class="container">
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

    <div id="page-dashboard" class="page active"><div id="dashboard-content"></div></div>
    <div id="page-analytics" class="page"><div id="analytics-content"></div></div>
    <div id="page-simulator" class="page"><div id="simulator-content"></div></div>
    <div id="page-settings" class="page"><div id="settings-content"></div></div>

    <div class="footer">Quantum Bet Bot v12 PRO © 2026</div>
</div>

<div class="bottom-nav">
    <button class="nav-item active" data-page="dashboard">
        <span class="icon">📊</span>
        <span class="label">Дашборд</span>
    </button>
    <button class="nav-item" data-page="analytics">
        <span class="icon">📈</span>
        <span class="label">Аналитика</span>
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
    // КОНФИГУРАЦИЯ
    // ============================================================
    const API_BASE = window.location.origin;
    
    // ============================================================
    // ЗВЁЗДЫ ДЛЯ ЭКРАНА ЗАГРУЗКИ
    // ============================================================
    (function generateLoadingStars() {
        const container = document.getElementById('loadingStars');
        if (!container) return;
        const count = 150;
        for (let i = 0; i < count; i++) {
            const star = document.createElement('div');
            star.className = 'loading-star';
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
    // СКРЫТИЕ ЭКРАНА ЗАГРУЗКИ
    // ============================================================
    function hideLoadingScreen() {
        const loading = document.getElementById('loadingScreen');
        if (loading) {
            loading.style.opacity = '0';
            setTimeout(function() {
                loading.style.display = 'none';
            }, 800);
        }
    }

    window.addEventListener('load', function() {
        setTimeout(hideLoadingScreen, 600);
    });

    // ============================================================
    // ЗВЁЗДЫ ДЛЯ ОСНОВНОГО ФОНА
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
    // ПЕРЕМЕННЫЕ
    // ============================================================
    let cachedData = null;
    let chartInstance = null;
    let interactiveChartInstance = null;
    let simChartInstance = null;
    let currentPage = 'dashboard';
    let isLoading = false;
    let chartData = null;
    let matchesCache = null;  // ← ДОБАВЛЕНО ДЛЯ КЭША МАТЧЕЙ

    // ============================================================
    // УВЕДОМЛЕНИЯ
    // ============================================================
    function showNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = 'notification' + (type === 'success' ? ' success' : type === 'error' ? ' error' : '');
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }, 3000);
    }

    // ============================================================
    // ТЕМА
    // ============================================================
    function toggleTheme() {
        const body = document.body;
        const btn = document.getElementById('themeBtn');
        
        if (body.classList.contains('light-theme')) {
            body.classList.remove('light-theme');
            btn.textContent = '🌙';
            localStorage.setItem('theme', 'dark');
            updateAllCharts(false);
        } else {
            body.classList.add('light-theme');
            btn.textContent = '☀️';
            localStorage.setItem('theme', 'light');
            updateAllCharts(true);
        }
    }

    function updateAllCharts(isLight) {
        const color = isLight ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.6)';
        const gridColor = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.03)';
        
        [chartInstance, interactiveChartInstance, simChartInstance].forEach(chart => {
            if (chart) {
                chart.options.plugins.legend.labels.color = color;
                chart.options.scales.x.ticks.color = color;
                chart.options.scales.y.ticks.color = color;
                chart.options.scales.x.grid.color = gridColor;
                chart.options.scales.y.grid.color = gridColor;
                chart.update();
            }
        });
    }

    const savedTheme = localStorage.getItem('theme') || 'dark';
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        document.getElementById('themeBtn').textContent = '☀️';
    } else {
        document.body.classList.remove('light-theme');
        document.getElementById('themeBtn').textContent = '🌙';
    }

    // ============================================================
    // НАВИГАЦИЯ
    // ============================================================
    document.querySelectorAll('.bottom-nav .nav-item').forEach(btn => {
        btn.addEventListener('click', function(e) {
            const page = this.dataset.page;
            switchPage(page);
        });
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
    // ЗАГРУЗКА МАТЧЕЙ ОТДЕЛЬНО (НОВАЯ ФУНКЦИЯ)
    // ============================================================
    async function loadMatches() {
        try {
            const response = await fetch(API_BASE + '/api/matches?t=' + Date.now());
            if (response.ok) {
                const data = await response.json();
                matchesCache = data;
                return data;
            }
            return null;
        } catch (e) {
            console.log('Ошибка загрузки матчей:', e);
            return null;
        }
    }

    // ============================================================
    // ЗАГРУЗКА ДАННЫХ (ИСПРАВЛЕННАЯ)
    // ============================================================
    async function loadPageData(page) {
        if (isLoading) return;

        const contentId = page + '-content';
        const contentEl = document.getElementById(contentId);

        if (page !== 'dashboard' && cachedData && contentEl.innerHTML && page !== 'analytics') {
            return;
        }

        isLoading = true;
        contentEl.innerHTML = '<div class="loader active"><div class="spinner"></div><div style="color:rgba(255,255,255,0.4);font-size:12px;margin-top:6px;">Загрузка...</div></div>';

        try {
            const response = await fetch(API_BASE + '/api/all_data?t=' + Date.now());
            if (!response.ok) {
                throw new Error('Сервер вернул ошибку: ' + response.status);
            }
            const data = await response.json();
            
            // ============================================================
            // ДОБАВЛЯЕМ ЗАГРУЗКУ МАТЧЕЙ ОТДЕЛЬНО
            // ============================================================
            try {
                const matchesData = await loadMatches();
                if (matchesData && matchesData.length > 0) {
                    data.matches = matchesData;
                    console.log('✅ Загружено матчей:', matchesData.length);
                } else if (data.matches && data.matches.length > 0) {
                    console.log('✅ Матчи из all_data:', data.matches.length);
                } else {
                    console.log('ℹ️ Нет активных матчей');
                }
            } catch (e) {
                console.log('Матчи не загружены отдельно');
            }
            
            cachedData = data;

            switch(page) {
                case 'dashboard': renderDashboard(data); break;
                case 'analytics': renderAnalytics(data); break;
                case 'simulator': renderSimulator(data); break;
                case 'settings': renderSettings(data); break;
            }
            
            hideLoadingScreen();
        } catch (error) {
            console.error('Ошибка загрузки:', error);
            contentEl.innerHTML = `
                <div class="no-data">
                    <div class="emoji">⚠️</div>
                    <div>Ошибка загрузки данных!</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.3);margin-top:4px;">
                        ${error.message}
                    </div>
                    <button onclick="refreshData()" style="margin-top:8px;padding:6px 16px;background:rgba(124,58,237,0.2);border:1px solid rgba(124,58,237,0.3);border-radius:6px;color:#a78bfa;cursor:pointer;">
                        🔄 Повторить
                    </button>
                </div>
            `;
            hideLoadingScreen();
            showNotification('❌ Ошибка загрузки: ' + error.message, 'error');
        }

        isLoading = false;
    }

    // ============================================================
    // ОБНОВЛЕНИЕ ДАННЫХ (ИСПРАВЛЕННОЕ)
    // ============================================================
    function refreshData() {
        cachedData = null;
        matchesCache = null;  // ← СБРАСЫВАЕМ КЭШ МАТЧЕЙ
        loadPageData(currentPage);
        showNotification('🔄 Обновление данных...', '');
    }

    // ============================================================
    // ДЕТЕКТОР ДРОБНЫХ СУММ
    // ============================================================
    function getDecimalPlaces(num) {
        const str = num.toString();
        const decimalIndex = str.indexOf('.');
        if (decimalIndex === -1) return 0;
        return str.length - decimalIndex - 1;
    }

    function shouldAnalyzeStake(stake) {
        const decimalPlaces = getDecimalPlaces(stake);
        return decimalPlaces >= 3;
    }

    function detectDecimalPatterns(history) {
        const settings = JSON.parse(localStorage.getItem('bot_settings')) || {};
        if (!settings.anomaly_detection) return [];
        
        const patterns = [];
        const stakeGroups = {};
        
        history.forEach((bet, index) => {
            const stake = parseFloat(bet.stake) || 0;
            if (stake > 0 && shouldAnalyzeStake(stake)) {
                const key = stake.toString();
                if (!stakeGroups[key]) {
                    stakeGroups[key] = {
                        stake: stake,
                        bets: []
                    };
                }
                stakeGroups[key].bets.push({
                    index: index,
                    bet: bet,
                    match: `${bet.home} vs ${bet.away}`,
                    score: bet.home_goals !== null && bet.away_goals !== null ? `${bet.home_goals}-${bet.away_goals}` : '-',
                    result: bet.result,
                    profit: bet.profit,
                    date: bet.date,
                    odds: bet.odds,
                    ev: bet.ev
                });
            }
        });
        
        Object.values(stakeGroups).forEach(group => {
            if (group.bets.length >= 2) {
                const wins = group.bets.filter(b => b.result === 'win').length;
                const losses = group.bets.filter(b => b.result === 'loss').length;
                const pushes = group.bets.filter(b => b.result === 'push').length;
                const totalProfit = group.bets.reduce((sum, b) => sum + (b.profit || 0), 0);
                const winrate = group.bets.length > 0 ? (wins / group.bets.length * 100) : 0;
                
                const profits = group.bets.map(b => b.profit || 0);
                const avgProfit = profits.reduce((a, b) => a + b, 0) / profits.length || 0;
                const maxProfit = Math.max(...profits) || 0;
                const minProfit = Math.min(...profits) || 0;
                const totalStakes = group.bets.reduce((sum, b) => sum + (b.bet.stake || 0), 0);
                const roi = totalStakes > 0 ? (totalProfit / totalStakes * 100) : 0;
                
                let status = '📌';
                let recommendation = '';
                if (winrate >= 70 && group.bets.length >= 3) {
                    status = '🟢';
                    recommendation = '🔥 Отличная рабочая сумма! Продолжайте использовать.';
                } else if (winrate >= 50 && group.bets.length >= 3) {
                    status = '🟢';
                    recommendation = '👍 Хорошая сумма, стабильный результат.';
                } else if (winrate < 40 && group.bets.length >= 3) {
                    status = '🔴';
                    recommendation = '⚠️ Неудачная сумма! Рекомендуем изменить размер.';
                } else if (group.bets.length >= 4) {
                    status = '🟡';
                    recommendation = 'Часто используемая сумма. Анализируйте результаты.';
                } else {
                    status = '🟡';
                    recommendation = 'Повторяющаяся сумма. Следите за статистикой.';
                }
                
                patterns.push({
                    stake: group.stake,
                    count: group.bets.length,
                    wins: wins,
                    losses: losses,
                    pushes: pushes,
                    winrate: winrate,
                    totalProfit: totalProfit,
                    avgProfit: avgProfit,
                    maxProfit: maxProfit,
                    minProfit: minProfit,
                    roi: roi,
                    status: status,
                    recommendation: recommendation,
                    bets: group.bets
                });
            }
        });
        
        patterns.sort((a, b) => b.count - a.count);
        return patterns;
    }

    function getSkippedSums(history) {
        const skipped = {};
        history.forEach(bet => {
            const stake = parseFloat(bet.stake) || 0;
            if (stake > 0 && !shouldAnalyzeStake(stake)) {
                const key = stake.toFixed(2);
                if (!skipped[key]) {
                    skipped[key] = { stake: stake, count: 0 };
                }
                skipped[key].count++;
            }
        });
        return Object.values(skipped).filter(s => s.count >= 2);
    }

    function getRecommendation(stake) {
        const stakeStr = stake.toString();
        
        const recommendations = {
            '45.125': {
                bet: '1X',
                icon: '🏠',
                description: 'Хозяева не проиграют (Победа или ничья хозяев)'
            },
            '40.7253125': {
                bet: 'ОБЗ',
                icon: '⚽',
                description: 'Обе команды забьют'
            },
            '42.86875000000006': {
                bet: 'ТМ 2.5',
                icon: '🔽',
                description: 'Тотал меньше 2.5 голов'
            },
            '42.86875000000001': {
                bet: 'X2',
                icon: '✈️',
                description: 'Гости не проиграют (Победа или ничья гостей)'
            }
        };
        
        for (const [key, value] of Object.entries(recommendations)) {
            if (stakeStr === key || stakeStr.startsWith(key) || key.startsWith(stakeStr)) {
                return value;
            }
        }
        
        return {
            bet: '—',
            icon: '📌',
            description: 'Нет рекомендации для этой суммы'
        };
    }

    // ============================================================
    // РЕНДЕР ДАШБОРДА (ИСПРАВЛЕННЫЙ)
    // ============================================================
    function renderDashboard(data) {
        const s = data.stats || {};
        const history = data.history || [];
        const matches = data.matches || [];

        // ОБЪЕДИНЯЕМ ИСТОРИЮ И МАТЧИ
        let allItems = [];

        // Добавляем активные матчи
        if (matches && matches.length > 0) {
            matches.forEach((match) => {
                const bestBet = match.best_bet || match.bets?.[0] || {};
                allItems.push({
                    type: 'match',
                    date: match.match_time || 'Сегодня',
                    home: match.home || 'Unknown',
                    away: match.away || 'Unknown',
                    home_goals: null,
                    away_goals: null,
                    score: '-',
                    bet: bestBet.label || '—',
                    odds: bestBet.odds || 0,
                    stake: bestBet.stake || 0,
                    ev: bestBet.ev || 0,
                    result: 'pending',
                    profit: 0,
                    is_active: true,
                    xg: match.total_xg || 0,
                    league: match.league || ''
                });
            });
        }

        // Добавляем историю ставок
        if (history && history.length > 0) {
            history.forEach((bet) => {
                allItems.push({
                    type: 'history',
                    date: bet.date || '-',
                    home: bet.home || 'Unknown',
                    away: bet.away || 'Unknown',
                    home_goals: bet.home_goals,
                    away_goals: bet.away_goals,
                    score: (bet.home_goals !== null && bet.away_goals !== null) ? bet.home_goals + ' - ' + bet.away_goals : '-',
                    bet: bet.bet || '—',
                    odds: bet.odds || 0,
                    stake: bet.stake || 0,
                    ev: bet.ev || 0,
                    result: bet.result || 'pending',
                    profit: bet.profit || 0,
                    is_active: false,
                    xg: 0,
                    league: bet.league || ''
                });
            });
        }

        // Сортируем: сначала активные матчи, потом история по дате
        allItems.sort((a, b) => {
            if (a.is_active && !b.is_active) return -1;
            if (!a.is_active && b.is_active) return 1;
            try { return new Date(b.date) - new Date(a.date); } catch { return 0; }
        });

        // Ограничиваем количество
        allItems = allItems.slice(0, 50);

        // Подсчет статистики
        const totalBets = allItems.filter(i => i.type === 'history').length;
        const activeMatches = allItems.filter(i => i.type === 'match').length;

        let html = `
            <div class="stats-grid">
                <div class="stat-card"><div class="value">$${s.bank || 1000}</div><div class="label">💰 Банк</div></div>
                <div class="stat-card"><div class="value green">${s.wins || 0}</div><div class="label">✅ Выигрыши</div></div>
                <div class="stat-card"><div class="value red">${s.losses || 0}</div><div class="label">❌ Проигрыши</div></div>
                <div class="stat-card"><div class="value gold">$${s.profit || 0}</div><div class="label">📈 Прибыль</div></div>
            </div>

            <div class="metrics-grid">
                <div class="metric-item"><span class="label">📊 Всего ставок</span><span class="value">${s.total_bets || 0}</span></div>
                <div class="metric-item"><span class="label">🎯 Проходимость</span><span class="value green">${s.winrate || 0}%</span></div>
                <div class="metric-item"><span class="label">📈 ROI</span><span class="value gold">${s.roi || 0}%</span></div>
                <div class="metric-item"><span class="label">📅 Активных матчей</span><span class="value">${activeMatches}</span></div>
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
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                    <h2 style="color:rgba(255,255,255,0.5);font-size:13px;">📋 Все ставки и матчи</h2>
                    <span style="color:rgba(255,255,255,0.3);font-size:11px;">Всего: ${allItems.length} (активных: ${activeMatches})</span>
                </div>
                <div class="table-wrapper">
                    <table>
                        <thead><tr>
                            <th>#</th><th>Дата</th><th>Матч</th><th>Счёт</th><th>Ставка</th><th>Кэф</th><th>Сумма</th><th>EV</th><th>Результат</th><th>Прибыль</th>
                        </tr></thead>
                        <tbody>
        `;

        if (allItems.length === 0) {
            html += `<tr><td colspan="10" class="no-data"><div class="emoji">📭</div>Нет данных</td></tr>`;
        } else {
            allItems.forEach((item, idx) => {
                const profitClass = item.profit > 0 ? 'profit-positive' : (item.profit < 0 ? 'profit-negative' : '');
                const isActive = item.is_active;
                const rowStyle = isActive ? 'background:rgba(167,139,250,0.05);' : '';
                
                html += `
                    <tr style="${rowStyle}">
                        <td>${idx + 1}</td>
                        <td style="font-size:9px;white-space:nowrap;">${item.date}</td>
                        <td><strong>${item.home}</strong> vs <strong>${item.away}</strong></td>
                        <td>${item.score}</td>
                        <td>${item.bet}${isActive ? ' 🟢' : ''}</td>
                        <td>${item.odds}</td>
                        <td>$${item.stake}</td>
                        <td>${item.ev}%</td>
                        <td><span class="badge ${item.result}">${item.result}</span></td>
                        <td class="${profitClass}">${item.profit > 0 ? '+' : ''}$${item.profit}</td>
                    </tr>
                `;
            });
        }

        html += `
                        </tbody>
                    </table>
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

        const isLight = document.body.classList.contains('light-theme');
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
                    pointBorderColor: isLight ? 'rgba(255,255,255,0.8)' : 'rgba(20,20,35,0.8)',
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
                            color: isLight ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.6)',
                            font: { size: 9 }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: isLight ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)',
                            font: { size: 8 }
                        },
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.03)' }
                    },
                    y: {
                        ticks: {
                            color: isLight ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)',
                            callback: function(value) { return '$' + value; },
                            font: { size: 8 }
                        },
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.03)' }
                    }
                }
            }
        });
    }

    // ============================================================
    // РЕНДЕР АНАЛИТИКИ
    // ============================================================
    function renderAnalytics(data) {
        const history = data.history || [];
        const settings = JSON.parse(localStorage.getItem('bot_settings')) || {};
        
        window._historyData = history;
        
        const patterns = detectDecimalPatterns(history);
        const hasPatterns = patterns.length > 0;
        const skippedSums = getSkippedSums(history);
        
        let html = `
            <h2 style="font-size:18px;color:#a78bfa;margin-bottom:4px;">📈 Интерактивная аналитика</h2>
            <div style="color:rgba(255,255,255,0.4);font-size:12px;margin-bottom:10px;">Исследуйте свои ставки в деталях</div>
            
            <div class="card">
                <div class="card-header">
                    <h2>📊 Интерактивный график</h2>
                    <div class="chart-controls">
                        <select id="chartPeriod" onchange="updateInteractiveChart()">
                            <option value="7">7 дней</option>
                            <option value="14">14 дней</option>
                            <option value="30" selected>30 дней</option>
                            <option value="90">90 дней</option>
                            <option value="all">Всё время</option>
                        </select>
                        <select id="chartType" onchange="updateInteractiveChart()">
                            <option value="profit">Прибыль</option>
                            <option value="bank">Банк</option>
                            <option value="winrate">Проходимость</option>
                        </select>
                        <button class="btn" onclick="resetInteractiveChart()">🔄 Сбросить</button>
                        <button class="btn" onclick="exportChart()">💾 PNG</button>
                    </div>
                </div>
                <div class="chart-container-large">
                    <canvas id="interactiveChart"></canvas>
                </div>
                <div class="chart-details" id="chartDetails">
                    <div class="chart-details-grid" id="chartDetailsContent"></div>
                    <div class="chart-actions">
                        <button class="btn" onclick="document.getElementById('chartDetails').classList.remove('active')">✖ Закрыть</button>
                    </div>
                </div>
            </div>
        `;

        if (settings.anomaly_detection) {
            html += `
            <div class="card" style="border:2px solid rgba(167,139,250,0.15);">
                <div class="card-header">
                    <h2 style="color:#a78bfa;">🕵️ Детектор дробных сумм (3+ знаков)</h2>
                    <span style="font-size:9px;color:rgba(255,255,255,0.3);">${patterns.length} паттернов</span>
                </div>
                
                <div style="font-size:10px;color:rgba(255,255,255,0.3);padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);margin-bottom:8px;">
                    ⚡ Анализируются только суммы с 3+ знаками после запятой
                </div>
                
                ${hasPatterns ? `
                <div style="overflow-x:auto;margin-bottom:12px;">
                    <table class="patterns-table">
                        <thead>
                            <tr>
                                <th>Сумма</th>
                                <th>Ставок</th>
                                <th>WIN</th>
                                <th>LOSS</th>
                                <th>PUSH</th>
                                <th>Проход</th>
                                <th>Прибыль</th>
                                <th>ROI</th>
                                <th>Рекомендация</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${patterns.map(p => `
                                <tr>
                                    <td><strong>$${p.stake.toString()}</strong></td>
                                    <td>${p.count}</td>
                                    <td style="color:#34d399;">${p.wins}</td>
                                    <td style="color:#f87171;">${p.losses}</td>
                                    <td style="color:#fbbf24;">${p.pushes}</td>
                                    <td style="color:${p.winrate >= 60 ? '#34d399' : (p.winrate >= 40 ? '#fbbf24' : '#f87171')};font-weight:600;">${p.winrate.toFixed(1)}%</td>
                                    <td style="color:${p.totalProfit >= 0 ? '#34d399' : '#f87171'};font-weight:600;">${p.totalProfit >= 0 ? '+' : ''}$${p.totalProfit.toFixed(2)}</td>
                                    <td style="color:${p.roi >= 0 ? '#34d399' : '#f87171'};">${p.roi.toFixed(1)}%</td>
                                    <td>${getRecommendation(p.stake).icon} ${getRecommendation(p.stake).bet}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                
                <div style="display:flex;flex-direction:column;gap:8px;">
                    ${patterns.map((pattern, idx) => renderPatternCard(pattern, idx)).join('')}
                </div>
                
                ${skippedSums.length > 0 ? `
                <div style="margin-top:10px;padding:8px;background:rgba(255,255,255,0.02);border-radius:6px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:10px;color:rgba(255,255,255,0.3);">
                        ⏭️ Пропущенные суммы (1-2 знака): 
                        ${skippedSums.map(s => `$${s.stake.toFixed(2)} (${s.count} ставки)`).join(' • ')}
                    </div>
                </div>
                ` : ''}
                ` : `
                <div class="no-data" style="padding:20px 0;">
                    <div class="emoji">📭</div>
                    <div>Нет повторяющихся дробных сумм (3+ знаков)</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.3);margin-top:4px;">
                        Сделайте ставки с одинаковыми дробными суммами
                    </div>
                </div>
                `}
            </div>
            `;
        } else {
            html += `
            <div class="card" style="border:1px solid rgba(255,255,255,0.05);">
                <div class="card-header">
                    <h2 style="color:rgba(255,255,255,0.3);">🕵️ Детектор дробных сумм</h2>
                    <span style="font-size:9px;color:rgba(255,255,255,0.2);">🔒 Отключен</span>
                </div>
                <div style="font-size:12px;color:rgba(255,255,255,0.3);text-align:center;padding:20px 0;">
                    Включите детектор в <a href="#" onclick="switchPage('settings')" style="color:#a78bfa;text-decoration:none;">Настройках</a>
                </div>
            </div>
            `;
        }

        html += `
            <div class="card">
                <div class="card-header">
                    <h2>📊 Быстрая статистика</h2>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;text-align:center;">
                    <div>
                        <div style="color:rgba(255,255,255,0.3);font-size:10px;">📊 Всего ставок</div>
                        <div style="font-size:22px;font-weight:700;color:#a78bfa;">${data.stats?.total_bets || 0}</div>
                    </div>
                    <div>
                        <div style="color:rgba(255,255,255,0.3);font-size:10px;">🎯 Проходимость</div>
                        <div style="font-size:22px;font-weight:700;color:#34d399;">${data.stats?.winrate || 0}%</div>
                    </div>
                    <div>
                        <div style="color:rgba(255,255,255,0.3);font-size:10px;">📈 ROI</div>
                        <div style="font-size:22px;font-weight:700;color:#fbbf24;">${data.stats?.roi || 0}%</div>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('analytics-content').innerHTML = html;
        setTimeout(() => initInteractiveChart(history), 100);
    }

    // ============================================================
    // РЕНДЕР КАРТОЧКИ ПАТТЕРНА
    // ============================================================
    function renderPatternCard(pattern, idx) {
        let statusColor;
        let statusIcon;
        let glowEffect = '';
        
        if (pattern.winrate === 100) {
            statusColor = '#34d399';
            statusIcon = '🌟';
            glowEffect = 'box-shadow: 0 0 30px rgba(52,211,153,0.15); border: 1px solid rgba(52,211,153,0.2);';
        } else if (pattern.winrate >= 60) {
            statusColor = '#34d399';
            statusIcon = '🟢';
        } else if (pattern.winrate >= 40) {
            statusColor = '#fbbf24';
            statusIcon = '🟡';
        } else {
            statusColor = '#f87171';
            statusIcon = '🔴';
        }
        
        const formattedStake = pattern.stake.toString();
        const recommendation = getRecommendation(pattern.stake);
        
        const isPerfect = pattern.winrate === 100;
        const perfectBadge = isPerfect ? `
            <span style="background:rgba(52,211,153,0.15);color:#34d399;padding:2px 8px;border-radius:10px;font-size:8px;font-weight:600;border:1px solid rgba(52,211,153,0.2);">
                🏆 100% ПРОХОДИМОСТЬ
            </span>
        ` : '';
        
        const betsHtml = pattern.bets.map(b => {
            const resultColor = b.result === 'win' ? '#34d399' : (b.result === 'loss' ? '#f87171' : '#fbbf24');
            return `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;font-size:10px;border-bottom:1px solid rgba(255,255,255,0.02);">
                    <span style="color:rgba(255,255,255,0.6);">${b.match}</span>
                    <div style="display:flex;gap:6px;align-items:center;">
                        <span style="color:rgba(255,255,255,0.3);">${b.score}</span>
                        <span style="color:${resultColor};font-weight:600;">${b.result.toUpperCase()}</span>
                        <span style="color:${b.profit > 0 ? '#34d399' : '#f87171'};font-weight:600;">
                            ${b.profit > 0 ? '+' : ''}$${b.profit.toFixed(2)}
                        </span>
                    </div>
                </div>
            `;
        }).join('');
        
        return `
            <div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:10px;border-left:3px solid ${statusColor};${glowEffect}">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span style="font-size:16px;">${statusIcon}</span>
                        <span style="font-size:14px;font-weight:700;color:${statusColor};">$${formattedStake}</span>
                        <span style="font-size:10px;color:rgba(255,255,255,0.3);">${pattern.count} ставки</span>
                        ${perfectBadge}
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:12px;font-weight:600;color:${pattern.totalProfit >= 0 ? '#34d399' : '#f87171'};">
                            ${pattern.totalProfit >= 0 ? '+' : ''}$${pattern.totalProfit.toFixed(2)}
                        </div>
                        <div style="font-size:9px;color:${statusColor};font-weight:600;">
                            ${pattern.winrate.toFixed(1)}% (${pattern.wins}/${pattern.count})
                            ${pattern.winrate === 100 ? ' 🏆' : ''}
                        </div>
                    </div>
                </div>
                
                <div class="pattern-metrics">
                    <div class="metric">
                        <div class="label">Средняя прибыль</div>
                        <div class="value" style="color:${pattern.avgProfit >= 0 ? '#34d399' : '#f87171'};">${pattern.avgProfit >= 0 ? '+' : ''}$${pattern.avgProfit.toFixed(2)}</div>
                    </div>
                    <div class="metric">
                        <div class="label">Макс. прибыль</div>
                        <div class="value" style="color:#34d399;">+$${pattern.maxProfit.toFixed(2)}</div>
                    </div>
                    <div class="metric">
                        <div class="label">Мин. прибыль</div>
                        <div class="value" style="color:#f87171;">$${pattern.minProfit.toFixed(2)}</div>
                    </div>
                    <div class="metric">
                        <div class="label">ROI</div>
                        <div class="value" style="color:${pattern.roi >= 0 ? '#34d399' : '#f87171'};">${pattern.roi.toFixed(1)}%</div>
                    </div>
                </div>
                
                <div style="background:${pattern.winrate === 100 ? 'rgba(52,211,153,0.08)' : 'rgba(167,139,250,0.08)'};border-radius:6px;padding:6px 10px;margin:6px 0;border:1px solid ${pattern.winrate === 100 ? 'rgba(52,211,153,0.2)' : 'rgba(167,139,250,0.15)'};">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px;">
                        <div>
                            <span style="font-size:10px;color:rgba(255,255,255,0.3);">🎯 Рекомендация:</span>
                            <span style="font-size:14px;font-weight:700;color:#a78bfa;">${recommendation.icon} ${recommendation.bet}</span>
                        </div>
                        <div style="font-size:10px;color:${pattern.winrate === 100 ? '#34d399' : 'rgba(255,255,255,0.3)'};font-weight:${pattern.winrate === 100 ? '700' : '400'};">
                            🎯 ${pattern.winrate.toFixed(1)}% сыгранных матчей
                            ${pattern.winrate === 100 ? ' ✅ ИДЕАЛЬНО!' : ''}
                        </div>
                    </div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.4);margin-top:2px;">
                        ${recommendation.description}
                    </div>
                </div>
                
                <div style="display:flex;flex-direction:column;gap:2px;margin-top:4px;padding-left:4px;">
                    ${betsHtml}
                </div>
                
                <button onclick="addMatchManually('${pattern.stake}', '${recommendation.bet}')" 
                        style="width:100%;margin-top:6px;padding:6px;background:rgba(52,211,153,0.08);border:1px dashed rgba(52,211,153,0.2);border-radius:6px;color:#34d399;cursor:pointer;font-size:10px;transition:all 0.3s ease;"
                        onmouseover="this.style.background='rgba(52,211,153,0.15)'" 
                        onmouseout="this.style.background='rgba(52,211,153,0.08)'">
                    ➕ Добавить матч
                </button>
                
                <div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:4px;padding-top:4px;border-top:1px solid rgba(255,255,255,0.03);">
                    💡 ${pattern.recommendation}
                    ${pattern.winrate === 100 ? ' 🏆 Идеальная проходимость!' : ''}
                </div>
            </div>
        `;
    }

    // ============================================================
    // РУЧНОЕ ДОБАВЛЕНИЕ МАТЧА
    // ============================================================
    function addMatchManually(stake, betType) {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(10px);
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        `;
        
        modal.innerHTML = `
            <div style="background:rgba(20,20,35,0.95);border-radius:16px;border:1px solid rgba(167,139,250,0.15);padding:24px;max-width:450px;width:100%;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                    <h3 style="color:#a78bfa;margin:0;">➕ Добавить матч</h3>
                    <button onclick="this.closest('div[style]').remove()" style="background:rgba(255,255,255,0.05);border:none;border-radius:50%;width:30px;height:30px;font-size:16px;color:rgba(255,255,255,0.5);cursor:pointer;">✖</button>
                </div>
                
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
                    <div>
                        <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-bottom:2px;">💰 Сумма маркера</div>
                        <div style="font-size:14px;font-weight:700;color:#a78bfa;">$${stake}</div>
                    </div>
                    <div>
                        <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-bottom:2px;">🎯 Тип ставки</div>
                        <div style="font-size:14px;font-weight:600;color:#34d399;">${betType}</div>
                    </div>
                </div>
                
                <div style="margin-bottom:10px;">
                    <label style="font-size:11px;color:rgba(255,255,255,0.3);display:block;margin-bottom:4px;">🏟️ Название матча</label>
                    <input type="text" id="matchNameInput" placeholder="Например: Real Madrid vs Barcelona" style="width:100%;padding:8px 12px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.06);border-radius:6px;color:#e8e8f0;font-size:13px;">
                </div>
                
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">
                    <div>
                        <label style="font-size:11px;color:rgba(255,255,255,0.3);display:block;margin-bottom:4px;">⚽ Счёт</label>
                        <input type="text" id="scoreInput" placeholder="2-1" style="width:100%;padding:8px 12px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.06);border-radius:6px;color:#e8e8f0;font-size:13px;">
                    </div>
                    <div>
                        <label style="font-size:11px;color:rgba(255,255,255,0.3);display:block;margin-bottom:4px;">📊 Результат</label>
                        <select id="resultSelect" style="width:100%;padding:8px 12px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.06);border-radius:6px;color:#e8e8f0;font-size:13px;">
                            <option value="win">✅ WIN</option>
                            <option value="loss">❌ LOSS</option>
                            <option value="push">🔄 PUSH</option>
                        </select>
                    </div>
                </div>
                
                <div style="display:flex;gap:8px;">
                    <button onclick="saveManualMatch('${stake}', '${betType}')" style="flex:1;padding:10px;background:linear-gradient(135deg,#7c3aed,#6d28d9);border:none;border-radius:8px;color:white;font-size:14px;font-weight:600;cursor:pointer;">
                        💾 Сохранить
                    </button>
                    <button onclick="this.closest('div[style]').remove()" style="padding:10px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.06);border-radius:8px;color:rgba(255,255,255,0.4);cursor:pointer;font-size:14px;">
                        Отмена
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }

    function saveManualMatch(stake, betType) {
        const matchName = document.getElementById('matchNameInput').value;
        const score = document.getElementById('scoreInput').value;
        const result = document.getElementById('resultSelect').value;
        
        if (!matchName) {
            alert('❌ Введите название матча!');
            return;
        }
        
        fetch(API_BASE + '/api/add_manual_match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                match: matchName,
                score: score || '-',
                result: result,
                stake: parseFloat(stake),
                bet: betType,
                odds: 1.85
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('✅ Матч добавлен!');
                location.reload();
            } else {
                alert('❌ Ошибка: ' + data.error);
            }
        })
        .catch(error => {
            alert('❌ Ошибка: ' + error);
        });
    }

    // ============================================================
    // ИНТЕРАКТИВНЫЙ ГРАФИК
    // ============================================================
    function initInteractiveChart(history) {
        const ctx = document.getElementById('interactiveChart');
        if (!ctx) return;

        if (interactiveChartInstance) {
            interactiveChartInstance.destroy();
            interactiveChartInstance = null;
        }

        window._historyData = history;
        
        const isLight = document.body.classList.contains('light-theme');
        const color = isLight ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.6)';
        const gridColor = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.03)';

        interactiveChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Прибыль ($)',
                    data: [],
                    borderColor: '#a78bfa',
                    backgroundColor: 'rgba(167,139,250,0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 8,
                    pointBackgroundColor: '#a78bfa',
                    pointBorderColor: isLight ? 'rgba(255,255,255,0.8)' : 'rgba(20,20,35,0.8)',
                    pointBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        labels: {
                            color: color,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: isLight ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)',
                        titleColor: isLight ? '#1a1a2e' : '#fff',
                        bodyColor: isLight ? '#1a1a2e' : '#fff',
                        borderColor: 'rgba(167,139,250,0.3)',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                return label + ': $' + value.toFixed(2);
                            },
                            afterBody: function(tooltipItems) {
                                if (chartData && chartData[tooltipItems[0].dataIndex]) {
                                    const bet = chartData[tooltipItems[0].dataIndex];
                                    return [
                                        'Матч: ' + bet.home + ' vs ' + bet.away,
                                        'Ставка: ' + bet.bet,
                                        'Кэф: ' + bet.odds,
                                        'Результат: ' + bet.result
                                    ];
                                }
                                return [];
                            }
                        }
                    },
                    zoom: {
                        limits: {
                            x: { min: 'original', max: 'original' }
                        },
                        pan: {
                            enabled: true,
                            mode: 'x'
                        },
                        zoom: {
                            wheel: {
                                enabled: true,
                                speed: 0.1
                            },
                            pinch: {
                                enabled: true
                            },
                            mode: 'x'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: color,
                            font: { size: 9 },
                            maxTicksLimit: 20
                        },
                        grid: {
                            color: gridColor
                        }
                    },
                    y: {
                        ticks: {
                            color: color,
                            font: { size: 9 },
                            callback: function(value) {
                                return '$' + value;
                            }
                        },
                        grid: {
                            color: gridColor
                        }
                    }
                },
                onClick: function(event, elements) {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        showChartDetails(index);
                    }
                }
            }
        });

        updateInteractiveChart();
    }

    function updateInteractiveChart() {
        if (!interactiveChartInstance) return;

        const period = document.getElementById('chartPeriod').value;
        const type = document.getElementById('chartType').value;
        const history = window._historyData || [];

        let filtered = [...history];
        if (period !== 'all') {
            const days = parseInt(period);
            const cutoff = new Date();
            cutoff.setDate(cutoff.getDate() - days);
            filtered = filtered.filter(bet => {
                try {
                    const betDate = new Date(bet.date.split(' ')[0]);
                    return betDate >= cutoff;
                } catch {
                    return false;
                }
            });
        }

        filtered.sort((a, b) => {
            try {
                return new Date(a.date) - new Date(b.date);
            } catch {
                return 0;
            }
        });

        const labels = [];
        const values = [];
        let cumulative = 0;
        let bank = 1000;

        filtered.forEach((bet, index) => {
            labels.push(bet.date);
            
            if (type === 'profit') {
                cumulative += bet.profit || 0;
                values.push(Math.round(cumulative * 100) / 100);
            } else if (type === 'bank') {
                bank += bet.profit || 0;
                values.push(Math.round(bank * 100) / 100);
            } else {
                const wins = filtered.slice(0, index + 1).filter(b => b.result === 'win').length;
                const total = index + 1;
                values.push(Math.round((wins / total) * 1000) / 10);
            }
        });

        chartData = filtered;

        const labelsMap = {
            'profit': 'Прибыль ($)',
            'bank': 'Банк ($)',
            'winrate': 'Проходимость (%)'
        };

        interactiveChartInstance.data.labels = labels;
        interactiveChartInstance.data.datasets[0].data = values;
        interactiveChartInstance.data.datasets[0].label = labelsMap[type] || 'Прибыль ($)';
        interactiveChartInstance.update();
    }

    function showChartDetails(index) {
        const details = document.getElementById('chartDetails');
        const content = document.getElementById('chartDetailsContent');
        const bet = chartData[index];
        
        if (bet) {
            details.classList.add('active');
            const isLight = document.body.classList.contains('light-theme');
            const color = isLight ? '#1a1a2e' : '#e8e8f0';
            
            content.innerHTML = `
                <div class="chart-details-item">
                    <div class="label">Матч</div>
                    <div class="value" style="color:${color};">${bet.home} vs ${bet.away}</div>
                </div>
                <div class="chart-details-item">
                    <div class="label">Дата</div>
                    <div class="value" style="color:${color};">${bet.date}</div>
                </div>
                <div class="chart-details-item">
                    <div class="label">Ставка</div>
                    <div class="value" style="color:${color};">${bet.bet} (Кэф: ${bet.odds})</div>
                </div>
                <div class="chart-details-item">
                    <div class="label">Результат</div>
                    <div class="value"><span class="badge ${bet.result}">${bet.result}</span></div>
                </div>
                <div class="chart-details-item">
                    <div class="label">Сумма</div>
                    <div class="value" style="color:${color};">$${bet.stake}</div>
                </div>
                <div class="chart-details-item">
                    <div class="label">Прибыль</div>
                    <div class="value" style="color:${bet.profit > 0 ? '#34d399' : '#f87171'};font-weight:700;">
                        ${bet.profit > 0 ? '+' : ''}$${bet.profit}
                    </div>
                </div>
            `;
        }
    }

    function resetInteractiveChart() {
        document.getElementById('chartPeriod').value = '30';
        document.getElementById('chartType').value = 'profit';
        document.getElementById('chartDetails').classList.remove('active');
        updateInteractiveChart();
    }

    function exportChart() {
        const canvas = document.getElementById('interactiveChart');
        const link = document.createElement('a');
        link.download = 'chart_' + new Date().toISOString().slice(0,10) + '.png';
        link.href = canvas.toDataURL('image/png');
        link.click();
    }

    // ============================================================
    // СИМУЛЯТОР
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
    // НАСТРОЙКИ
    // ============================================================
    function renderSettings(data) {
        const bank = data.stats ? data.stats.bank : 1000;
        const settings = JSON.parse(localStorage.getItem('bot_settings')) || {
            anomaly_detection: false
        };
        
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
            
            <div class="setting-group" style="border:1px solid rgba(167,139,250,0.15);">
                <h2>🕵️ Детектор дробных сумм</h2>
                <div class="setting-item">
                    <div>
                        <div class="label" style="font-size:13px;font-weight:600;">Включить детектор</div>
                        <div class="desc">Анализирует суммы с 3+ знаками после запятой</div>
                    </div>
                    <div class="toggle ${settings.anomaly_detection ? 'active' : ''}" onclick="toggleSetting('anomaly_detection', this)">
                        <div class="dot"></div>
                    </div>
                </div>
                <div style="font-size:9px;color:rgba(255,255,255,0.3);padding:6px 0;border-top:1px solid rgba(255,255,255,0.05);margin-top:4px;">
                    📌 Анализируются: 45.125, 40.7253125, 42.86875<br>
                    ⏭️ Пропускаются: 50, 47.5, 45.12
                </div>
            </div>
            
            <div class="setting-group">
                <h2>💾 Проект</h2>
                <div class="setting-item">
                    <div>
                        <div class="label">Сохранить проект</div>
                        <div class="desc">Скачать все данные и настройки в JSON</div>
                    </div>
                    <button class="btn" onclick="exportProject()" style="background:rgba(52,211,153,0.1);border-color:rgba(52,211,153,0.2);color:#34d399;">
                        💾 Сохранить
                    </button>
                </div>
                <div class="setting-item" style="border-bottom:none;">
                    <div>
                        <div class="label">Загрузить проект</div>
                        <div class="desc">Восстановить данные из сохраненного файла</div>
                    </div>
                    <div class="input-group">
                        <label class="file-input-label" for="projectFileInput" style="background:rgba(167,139,250,0.15);color:#a78bfa;border:1px solid rgba(167,139,250,0.2);">
                            📂 Загрузить
                        </label>
                        <input type="file" id="projectFileInput" accept=".json" style="display:none" onchange="importProject(event)">
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
    // ЭКСПОРТ/ИМПОРТ ПРОЕКТА
    // ============================================================
    function exportProject() {
        const projectData = {
            version: '1.0',
            exportDate: new Date().toISOString(),
            exportedAt: new Date().toLocaleString(),
            settings: JSON.parse(localStorage.getItem('bot_settings')) || {},
            theme: localStorage.getItem('theme') || 'dark',
            data: cachedData || null
        };
        
        if (!projectData.data) {
            showNotification('⏳ Загрузка данных...', '');
            fetch(API_BASE + '/api/all_data')
                .then(response => response.json())
                .then(data => {
                    projectData.data = data;
                    downloadProjectFile(projectData);
                })
                .catch(error => {
                    showNotification('❌ Ошибка загрузки данных: ' + error, 'error');
                });
            return;
        }
        
        downloadProjectFile(projectData);
    }

    function downloadProjectFile(projectData) {
        const json = JSON.stringify(projectData, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const link = document.createElement('a');
        link.href = url;
        link.download = `quantum_bet_project_${new Date().toISOString().slice(0,10)}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        
        showNotification('✅ Проект успешно сохранен!', 'success');
    }

    function importProject(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        showNotification('⏳ Загрузка файла...', '');
        
        const reader = new FileReader();
        reader.onload = function(e) {
            try {
                const projectData = JSON.parse(e.target.result);
                
                if (!projectData.version) {
                    showNotification('❌ Неверный формат файла!', 'error');
                    return;
                }
                
                if (projectData.settings) {
                    localStorage.setItem('bot_settings', JSON.stringify(projectData.settings));
                }
                
                if (projectData.theme) {
                    localStorage.setItem('theme', projectData.theme);
                    if (projectData.theme === 'light') {
                        document.body.classList.add('light-theme');
                        document.getElementById('themeBtn').textContent = '☀️';
                    } else {
                        document.body.classList.remove('light-theme');
                        document.getElementById('themeBtn').textContent = '🌙';
                    }
                }
                
                if (projectData.data && projectData.data.history) {
                    showNotification('⏳ Отправка данных на сервер...', '');
                    
                    fetch(API_BASE + '/api/import_project', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            history: projectData.data.history,
                            stats: projectData.data.stats
                        })
                    })
                    .then(response => response.json())
                    .then(result => {
                        if (result.success) {
                            showNotification(`✅ Проект загружен! Импортировано ${result.count || 0} ставок.`, 'success');
                            refreshData();
                        } else {
                            showNotification('❌ Ошибка загрузки: ' + result.error, 'error');
                        }
                    })
                    .catch(error => {
                        showNotification('❌ Ошибка: ' + error, 'error');
                    });
                } else {
                    showNotification('✅ Настройки загружены! Данные не найдены.', 'success');
                    refreshData();
                }
                
            } catch (error) {
                showNotification('❌ Ошибка чтения файла: ' + error, 'error');
            }
        };
        reader.readAsText(file);
        event.target.value = '';
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
            const response = await fetch(API_BASE + '/api/edit_bet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.success) {
                showNotification('✅ Ставка обновлена!', 'success');
                refreshData();
            } else {
                showNotification('❌ Ошибка: ' + result.error, 'error');
            }
        } catch (e) {
            showNotification('❌ Ошибка: ' + e, 'error');
        }
    }

    async function deleteBet(index) {
        if (!confirm('Удалить эту ставку?')) return;
        try {
            const response = await fetch(API_BASE + '/api/delete_bet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ index: index })
            });
            const result = await response.json();
            if (result.success) {
                showNotification('✅ Ставка удалена!', 'success');
                refreshData();
            } else {
                showNotification('❌ Ошибка: ' + result.error, 'error');
            }
        } catch (e) {
            showNotification('❌ Ошибка: ' + e, 'error');
        }
    }

    async function runSimulation() {
        const count = parseInt(document.getElementById('simCount').value) || 1000;
        document.getElementById('simResults').style.display = 'block';
        try {
            const response = await fetch(API_BASE + '/api/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: count })
            });
            const data = await response.json();
            if (data.error) {
                showNotification('❌ Ошибка: ' + data.error, 'error');
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
                const isLight = document.body.classList.contains('light-theme');
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
                            legend: { labels: { color: isLight ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.6)', font: { size: 9 } } }
                        },
                        scales: {
                            x: { ticks: { color: isLight ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)', font: { size: 8 } }, grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.03)' } },
                            y: { ticks: { color: isLight ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)', callback: function(value) { return '$' + value; }, font: { size: 8 } }, grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.03)' } }
                        }
                    }
                });
            }
        } catch (e) {
            showNotification('❌ Ошибка: ' + e, 'error');
        }
    }

    async function updateBank() {
        const value = document.getElementById('bankInput').value;
        try {
            const response = await fetch(API_BASE + '/api/bank', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bank: parseFloat(value) })
            });
            const data = await response.json();
            if (data.success) {
                showNotification('✅ Банк обновлен: $' + data.bank, 'success');
                refreshData();
            }
        } catch (e) {
            showNotification('❌ Ошибка: ' + e, 'error');
        }
    }

    function toggleSetting(key, element) {
        const settings = JSON.parse(localStorage.getItem('bot_settings')) || {};
        element.classList.toggle('active');
        settings[key] = element.classList.contains('active');
        localStorage.setItem('bot_settings', JSON.stringify(settings));
        refreshData();
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
                fetch(API_BASE + '/api/import_excel', {
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

    // ============================================================
    // ЗАПУСК
    // ============================================================
    document.addEventListener('DOMContentLoaded', function() {
        loadPageData('dashboard');
    });
</script>
</body>
</html>
"""

# ============================================================
# ПРОВЕРКА БОТА
# ============================================================

def check_bot_health():
    try:
        response = requests.get(f'{BOT_URL}/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Бот доступен: {data}")
            return True, data
        else:
            logger.warning(f"⚠️ Бот вернул код {response.status_code}")
            return False, None
    except Exception as e:
        logger.error(f"❌ Бот недоступен: {e}")
        return False, None

# ============================================================
# API МАРШРУТЫ (ПРОКСИ К БОТУ)
# ============================================================

@app.route('/')
def index():
    return render_template_string(MAIN_HTML)

@app.route('/api/all_data')
def api_all_data():
    """Прокси к боту для получения всех данных"""
    try:
        logger.info(f"📡 Запрос к боту: {BOT_URL}/api/all_data")
        response = requests.get(f'{BOT_URL}/api/all_data', timeout=15)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': f'Бот вернул ошибку {response.status_code}'}), 500
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/matches')
def api_matches():
    """Прокси для получения матчей"""
    try:
        response = requests.get(f'{BOT_URL}/api/matches', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify([])
    except:
        return jsonify([])

@app.route('/api/stats')
def api_stats():
    try:
        response = requests.get(f'{BOT_URL}/api/stats', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({'bank': 1000, 'total_bets': 0, 'wins': 0, 'losses': 0, 'profit': 0})
    except:
        return jsonify({'bank': 1000, 'total_bets': 0, 'wins': 0, 'losses': 0, 'profit': 0})

@app.route('/api/history')
def api_history():
    try:
        response = requests.get(f'{BOT_URL}/api/history', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify([])
    except:
        return jsonify([])

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/import_excel', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/import_project', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/edit_bet', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/delete_bet', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/bank', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/simulate', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        response = requests.post(f'{BOT_URL}/api/add_manual_match', json=data, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    bot_ok, bot_data = check_bot_health()
    return jsonify({
        'status': 'ok',
        'web': 'running',
        'bot': 'ok' if bot_ok else 'error',
        'bot_data': bot_data,
        'bot_url': BOT_URL
    })

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"🌐 Запуск веб-интерфейса на порту {port}")
    logger.info(f"📡 Подключение к боту: {BOT_URL}")
    
    bot_ok, bot_data = check_bot_health()
    if bot_ok:
        logger.info("✅ Бот доступен")
    else:
        logger.warning("⚠️ Бот недоступен! Убедитесь, что бот запущен на Render")
    
    app.run(host='0.0.0.0', port=port, debug=False)
