# ============================================================
# botcore/routes_lab.py — Лаборатория (API)
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
from botcore.routes_core import *  # noqa: F401,F403
from botcore.routes_live import *  # noqa: F401,F403
from botcore.routes_x2 import *  # noqa: F401,F403
from botcore.routes_calib import *  # noqa: F401,F403
from botcore.routes_data import *  # noqa: F401,F403

__all__ = [
    'api_lab',
    'api_lab_set_result',
]


@app.route('/api/lab', methods=['GET'])
def api_lab():
    try:
        lab_file = os.path.join(DATA_DIR, 'lab_anomalies.jsonl')
        items = []
        if os.path.exists(lab_file):
            with open(lab_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-200:]:
                    try:
                        items.append(json.loads(line.strip()))
                    except: pass
        items = lm_filter(items)
        items.sort(key=lambda x: x.get('date', ''), reverse=True)
        return jsonify({'status': 'ok', 'count': len(items), 'items': items})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ РУЧНОЕ ОБНОВЛЕНИЕ РЕЗУЛЬТАТА ЛАБОРАТОРИИ
# ============================================================
@app.route('/api/lab/set_result', methods=['POST'])
def api_lab_set_result():
    """
    Ручное обновление результата лабораторной аномалии.
    Принимает: fixture_id, home_goals, away_goals, reverse_bet
    """
    try:
        data = request.json or {}
        fixture_id = data.get('fixture_id')
        home_goals = data.get('home_goals')
        away_goals = data.get('away_goals')
        reverse_bet = (data.get('reverse_bet') or '').upper().strip()

        if fixture_id is None or home_goals is None or away_goals is None:
            return jsonify({
                'status': 'error',
                'error': 'fixture_id, home_goals, away_goals обязательны'
            }), 400

        hg = int(home_goals)
        ag = int(away_goals)

        # Вычисляем результат обратной ставки
        if reverse_bet == 'П1':
            result = 'win' if hg > ag else 'loss'
        elif reverse_bet == 'П2':
            result = 'win' if ag > hg else 'loss'
        elif reverse_bet == 'X2':
            result = 'win' if ag >= hg else 'loss'
        elif reverse_bet == '1X':
            result = 'win' if hg >= ag else 'loss'
        elif reverse_bet == 'X':
            result = 'win' if hg == ag else 'loss'
        else:
            return jsonify({
                'status': 'error',
                'error': f'Неизвестная ставка: {reverse_bet}'
            }), 400

        lab_file = os.path.join(DATA_DIR, 'lab_anomalies.jsonl')
        if not os.path.exists(lab_file):
            return jsonify({'status': 'error', 'error': 'Файл лаборатории не найден'}), 404

        with _jsonl_lock:
            # Читаем файл, ищем нужную запись
            with open(lab_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            updated = False
            new_lines = []
            for line in lines:
                try:
                    rec = json.loads(line.strip())
                except Exception:
                    new_lines.append(line)
                    continue

                if rec.get('fixture_id') == int(fixture_id):
                    rec['result'] = result
                    rec['home_goals'] = hg
                    rec['away_goals'] = ag
                    rec['manual'] = True
                    rec['settled_at'] = datetime.now().isoformat()
                    updated = True
                    logger.info(
                        f"🧪 Лаб. вручную: fid={fixture_id} | {hg}:{ag} | "
                        f"{reverse_bet} → {result.upper()}"
                    )

                new_lines.append(json.dumps(rec, ensure_ascii=False) + '\n')

            if not updated:
                return jsonify({'status': 'error', 'error': 'Матч не найден в лаборатории'}), 404

            # Атомарная запись
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(lab_file) or '.', suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            os.replace(tmp, lab_file)

        return jsonify({
            'status': 'ok',
            'result': result,
            'home_goals': hg,
            'away_goals': ag,
            'reverse_bet': reverse_bet,
        })
    except Exception as e:
        logger.exception(f"api_lab_set_result: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
