# ============================================================
# botcore/calib_tools.py — Калибровка: сообщения, снапшоты
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

__all__ = [
    '_build_calibration_message',
    '_load_calibration_snapshots',
    '_save_calibration_snapshots',
    '_cleanup_calibration_snapshots',
    '_build_calibration_data',
    'save_calibration_snapshot',
    '_cleanup_and_save_snapshots',
]


def _build_calibration_message():
    history = storage.load_history()
    finished = [b for b in history if b.get('result') in ('win', 'loss') and b.get('prob', 0) > 0]

    if not finished:
        return "📭 Нет завершённых ставок с prob"

    buckets_map = defaultdict(list)
    for b in finished:
        prob = b.get('prob', 0)
        bucket = int(prob // 5) * 5
        if bucket < 30:
            continue
        if bucket > 95:
            bucket = 95
        buckets_map[bucket].append(1 if b['result'] == 'win' else 0)

    total_n = sum(len(v) for v in buckets_map.values())
    if total_n == 0:
        return "📭 Нет данных для бакетов"

    sum_pred = 0
    sum_act = 0
    for bucket, results in buckets_map.items():
        n = len(results)
        pred = bucket + 2.5
        act = sum(results) / n * 100
        sum_pred += pred * n
        sum_act += act * n

    overall_pred = sum_pred / total_n
    overall_act = sum_act / total_n
    diff = overall_act - overall_pred

    if abs(diff) < 3:
        emoji = "✅"
        verdict = "КАЛИБРОВКА ХОРОШАЯ"
    elif diff < -10:
        emoji = "🔴"
        verdict = "СИЛЬНО ЗАВЫШАЕТ"
    elif diff < -3:
        emoji = "🟡"
        verdict = "ЗАВЫШАЕТ"
    elif diff > 10:
        emoji = "🔵"
        verdict = "СИЛЬНО ЗАНИЖАЕТ"
    else:
        emoji = "🔵"
        verdict = "ЗАНИЖАЕТ"

    msg = (f"📊 <b>КАЛИБРОВКА</b>\n"
           f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
           f"{emoji} <b>{verdict}</b>\n\n"
           f"📊 Модель: <b>{overall_pred:.1f}%</b>\n"
           f"🎯 Реально: <b>{overall_act:.1f}%</b>\n"
           f"📈 Разница: <b>{diff:+.1f}%</b>\n"
           f"🎲 Ставок: {total_n}\n"
           f"⚙️ Коэффициент: <b>{overall_act/overall_pred:.3f}</b>\n\n"
           f"<b>По бакетам:</b>\n")

    for bucket in sorted(buckets_map.keys()):
        results = buckets_map[bucket]
        n = len(results)
        if n < 3:
            continue
        actual = sum(results) / n * 100
        predicted = bucket + 2.5
        d = actual - predicted
        icon = "🟢" if abs(d) < 5 else "🟡" if abs(d) < 10 else "🔴"
        msg += f"{icon} {bucket}-{bucket+5}%: {predicted:.0f}% → {actual:.0f}% ({d:+.1f}%)\n"

    return msg


# ============================================================
# ★ CALIBRATION SNAPSHOTS
# ============================================================
def _load_calibration_snapshots():
    try:
        if os.path.exists(CALIBRATION_FILE):
            with open(CALIBRATION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception as e:
        logger.error(f"_load_calibration_snapshots: {e}")
    return []


def _save_calibration_snapshots(snapshots):
    try:
        os.makedirs(os.path.dirname(CALIBRATION_FILE) or '.', exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CALIBRATION_FILE) or '.', suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CALIBRATION_FILE)
        return True
    except Exception as e:
        logger.error(f"_save_calibration_snapshots: {e}")
        return False


def _cleanup_calibration_snapshots(snapshots):
    now = time.time()
    cleaned = []
    for s in snapshots:
        saved_at = s.get('saved_at_ts', 0)
        cleaned.append((saved_at, s))
    cleaned.sort(key=lambda x: x[0], reverse=True)

    result = []
    for i, (saved_at, s) in enumerate(cleaned):
        if i == 0:
            result.append(s)
        else:
            age_hours = (now - saved_at) / 3600
            if age_hours < 24:
                result.append(s)
    return result


def _build_calibration_data():
    history = storage.load_history()
    finished = [
        b for b in history
        if b.get('result') in ('win', 'loss') and b.get('prob', 0) > 0
    ]

    buckets_map = defaultdict(list)
    for b in finished:
        prob = b.get('prob', 0)
        bucket = int(prob // 5) * 5
        if bucket < 30:
            continue
        if bucket > 95:
            bucket = 95
        buckets_map[bucket].append(1 if b['result'] == 'win' else 0)

    buckets = []
    for bucket in sorted(buckets_map.keys()):
        results = buckets_map[bucket]
        n = len(results)
        if n < 3:
            continue
        actual = sum(results) / n * 100
        predicted = bucket + 2.5
        buckets.append({
            'range': f'{bucket}-{bucket+5}%',
            'count': n,
            'predicted': round(predicted, 1),
            'actual': round(actual, 1),
            'diff': round(actual - predicted, 1),
        })

    total_n = sum(b['count'] for b in buckets)
    if total_n > 0:
        overall_predicted = sum(b['predicted'] * b['count'] for b in buckets) / total_n
        overall_actual = sum(b['actual'] * b['count'] for b in buckets) / total_n
        overall_diff = overall_actual - overall_predicted
    else:
        overall_predicted = overall_actual = overall_diff = 0

    return {
        'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'saved_at_ts': time.time(),
        'total': len(finished),
        'buckets': buckets,
        'overall': {
            'count': total_n,
            'predicted': round(overall_predicted, 1),
            'actual': round(overall_actual, 1),
            'diff': round(overall_diff, 1),
            'calibration_factor': round(overall_actual / overall_predicted, 3) if overall_predicted > 0 else 1.0,
        },
    }


def save_calibration_snapshot():
    try:
        snapshots = _load_calibration_snapshots()
        new_snap = _build_calibration_data()
        snapshots.append(new_snap)
        snapshots = _cleanup_calibration_snapshots(snapshots)
        ok = _save_calibration_snapshots(snapshots)
        if ok:
            logger.info(
                f"📸 Калибровка сохранена: {new_snap['saved_at']} | "
                f"ставок={new_snap['total']} | снапшотов={len(snapshots)}"
            )
        return ok
    except Exception as e:
        logger.exception(f"save_calibration_snapshot: {e}")
        return False


def _cleanup_and_save_snapshots():
    try:
        snapshots = _load_calibration_snapshots()
        cleaned = _cleanup_calibration_snapshots(snapshots)
        if len(cleaned) != len(snapshots):
            _save_calibration_snapshots(cleaned)
            logger.info(f"🧹 Калибровка: очищено {len(snapshots) - len(cleaned)} снапшотов")
        return len(cleaned)
    except Exception as e:
        logger.error(f"_cleanup_and_save_snapshots: {e}")
        return 0
