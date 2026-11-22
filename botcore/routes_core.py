# ============================================================
# botcore/routes_core.py — Базовые маршруты: sw.js, manifest, экспорт, /health, /
# (часть бывшего main.py; порядок модулей см. main.py)
# ============================================================
import sys
import os
import copy
import requests
import time
import json
import logging
import random
import math
import functools
import zipfile
import shutil
import itertools
import tempfile
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from threading import Lock, RLock, Thread
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory, render_template
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Config
from app.database.storage import storage
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler
from app.llm import (
    llm_analyze_match,
    llm_analyze_batch,
    llm_generate_reason,
    llm_pick_best,
)


from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.autobet import *  # noqa: F401,F403
from botcore.simulator import *  # noqa: F401,F403
from botcore.analysis import *  # noqa: F401,F403
from botcore.odds_matches import *  # noqa: F401,F403
from botcore.strat_top import *  # noqa: F401,F403
from botcore.strat_value import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403
from botcore.strat_lm import *  # noqa: F401,F403
from botcore.results import *  # noqa: F401,F403
from botcore.strat_combined import *  # noqa: F401,F403
from botcore.lab_tasks import *  # noqa: F401,F403
from botcore.calib_tools import *  # noqa: F401,F403
from botcore.jobs import *  # noqa: F401,F403
from botcore.routes_search import *  # noqa: F401,F403

__all__ = [
    'serve_sw',
    'serve_manifest',
    'export_excel_route',
    'export_csv_route',
    'health',
    'index',
]


# ============================================================
# PWA
# ============================================================
@app.route('/sw.js')
def serve_sw():
    try:
        return send_from_directory('.', 'sw.js', mimetype='application/javascript')
    except Exception:
        return "Service Worker не найден", 404


@app.route('/manifest.json')
def serve_manifest():
    try:
        return send_from_directory('.', 'manifest.json', mimetype='application/json')
    except Exception:
        return "Манифест не найден", 404


# ============================================================
# ★ FIX: /export и /api/export/csv (было 404)
# ============================================================
@app.route('/export', methods=['GET'])
def export_excel_route():
    """★ FIX: кнопка «📥 Excel» в настройках — раньше 404."""
    try:
        file, message = export_to_excel()
        if file is None:
            return message, 400
        from flask import send_file
        return send_file(
            file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'history_{datetime.now().strftime("%Y-%m-%d")}.xlsx'
        )
    except Exception as e:
        logger.exception(f"export_excel_route: {e}")
        return f"❌ Ошибка экспорта: {e}", 500


@app.route('/api/export/csv', methods=['GET'])
def export_csv_route():
    """★ FIX: кнопка «📄 CSV» в настройках."""
    try:
        import csv
        import io
        history = storage.load_history()
        if not history:
            return "📭 Нет данных", 400

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Дата', 'Матч', 'Счёт', '1-й тайм', 'Ставка', 'Коэф',
                         'EV%', 'Prob%', 'Сумма', 'Результат', 'Прибыль',
                         'Букмекер', 'Источник'])
        for bet in history:
            score = f"{bet.get('home_goals', '-')}-{bet.get('away_goals', '-')}"
            ht = (f"{bet.get('halftime_home', '-')}-{bet.get('halftime_away', '-')}"
                  if bet.get('halftime_home') is not None else '-')
            writer.writerow([
                bet.get('date', ''),
                f"{bet.get('home', '')} vs {bet.get('away', '')}",
                score, ht,
                bet.get('bet', ''), bet.get('odds', 0),
                bet.get('ev', 0), bet.get('prob', 0),
                bet.get('stake', 0), bet.get('result', 'pending'),
                bet.get('profit', 0),
                bet.get('bookmaker', '—'),
                bet.get('source', '70_percent'),
            ])

        from flask import Response
        return Response(
            '\ufeff' + output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition':
                     f'attachment; filename=history_{datetime.now().strftime("%Y-%m-%d")}.csv'}
        )
    except Exception as e:
        logger.exception(f"export_csv_route: {e}")
        return f"❌ Ошибка экспорта: {e}", 500


@app.route('/health', methods=['GET'])
def health():
    if not _token_ok(request.headers.get('X-Admin-Token', '')):
        return {'status': 'ok', 'time': datetime.now().isoformat(), 'version': 'v23.3'}
    try:
        bank = storage.load_bank()
        history = storage.load_history()
        state = bot_state.state
        try:
            start_dt = datetime.fromisoformat(state.get('start_time', datetime.now().isoformat()))
            uptime_sec = (datetime.now() - start_dt).total_seconds()
            uptime_hours = round(uptime_sec / 3600, 2)
        except Exception:
            uptime_sec = 0; uptime_hours = 0
        try:
            autobets_state = storage.autobet_get_state(default_bank=1000.0)
        except Exception:
            autobets_state = {}
        try:
            odds_size = storage.get_odds_history_size()
        except Exception:
            odds_size = {'matches': 0, 'snapshots': 0}
        try:
            x2_count = storage.x2_count()
        except Exception:
            x2_count = 0
        return {
            'status': 'ok', 'time': datetime.now().isoformat(),
            'uptime_hours': uptime_hours, 'uptime_sec': int(uptime_sec),
            'bank': bank, 'total_bets': len(history),
            'search_running': state.get('search_running', False),
            'geocoding_cache_size': len(_geo_cache),
            'data_dir': DATA_DIR,
            'x2_candidates': x2_count,
            'version': 'v23.3',
            'autobets': {
                'count': autobets_state.get('total_bets', 0),
                'bank': autobets_state.get('bank', 1000),
                'profit': autobets_state.get('total_profit', 0),
                'roi': autobets_state.get('roi', 0),
                'winrate': autobets_state.get('winrate', 0),
                'pending': autobets_state.get('pending', 0),
                'live_count': autobets_state.get('live_count', 0),
                'avg_clv': autobets_state.get('avg_clv', 0),
                'clv_count': autobets_state.get('clv_count', 0),
            },
            'odds_history': {
                'matches': odds_size.get('matches', 0),
                'snapshots': odds_size.get('snapshots', 0),
            },
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}, 500


@app.route('/', methods=['GET'])
def index():
    try:
        return render_template('index.html')
    except Exception:
        return f"🤖 Quantum Bet Bot PRO | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
