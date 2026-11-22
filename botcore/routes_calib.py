# ============================================================
# botcore/routes_calib.py — Калибровка (API)
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

__all__ = [
    'api_calibration',
    'api_calibration_snapshots',
    'api_calibration_save',
    'api_calibration_snapshot_delete',
]


# ============================================================
# ★ API: КАЛИБРОВКА
# ============================================================
@app.route('/api/calibration', methods=['GET'])
def api_calibration():
    try:
        history = storage.load_history()
        finished = [
            b for b in history
            if b.get('result') in ('win', 'loss') and b.get('prob', 0) > 0
        ]
        if not finished:
            return jsonify({
                'status': 'ok', 'total': 0, 'message': 'Нет завершённых ставок с prob',
                'buckets': [], 'overall': {}, 'sources': [],
            })

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
            diff = actual - predicted
            buckets.append({
                'range': f'{bucket}-{bucket+5}%',
                'bucket_mid': predicted,
                'count': n,
                'predicted': round(predicted, 1),
                'actual': round(actual, 1),
                'diff': round(diff, 1),
                'wins': sum(results),
            })

        total_n = sum(b['count'] for b in buckets)
        if total_n > 0:
            overall_predicted = sum(b['predicted'] * b['count'] for b in buckets) / total_n
            overall_actual = sum(b['actual'] * b['count'] for b in buckets) / total_n
            overall_diff = overall_actual - overall_predicted
        else:
            overall_predicted = overall_actual = overall_diff = 0

        by_source = defaultdict(list)
        for b in finished:
            prob = b.get('prob', 0)
            if prob <= 0:
                continue
            src = b.get('source', '70_percent') or '70_percent'
            by_source[src].append((prob, 1 if b['result'] == 'win' else 0))

        sources = []
        for src, data in by_source.items():
            if len(data) < 5:
                continue
            avg_prob = sum(p for p, _ in data) / len(data)
            avg_actual = sum(a for _, a in data) / len(data) * 100
            sources.append({
                'source': src,
                'count': len(data),
                'avg_prob': round(avg_prob, 1),
                'avg_actual': round(avg_actual, 1),
                'diff': round(avg_actual - avg_prob, 1),
            })

        return jsonify({
            'status': 'ok',
            'total': len(finished),
            'buckets': buckets,
            'overall': {
                'count': total_n,
                'predicted': round(overall_predicted, 1),
                'actual': round(overall_actual, 1),
                'diff': round(overall_diff, 1),
                'calibration_factor': round(overall_actual / overall_predicted, 3) if overall_predicted > 0 else 1.0,
            },
            'sources': sources,
        })
    except Exception as e:
        logger.exception(f"api_calibration error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/calibration/snapshots', methods=['GET'])
def api_calibration_snapshots():
    try:
        snapshots = _load_calibration_snapshots()
        snapshots = _cleanup_calibration_snapshots(snapshots)
        snapshots.sort(key=lambda x: x.get('saved_at_ts', 0), reverse=True)
        return jsonify({
            'status': 'ok',
            'count': len(snapshots),
            'snapshots': snapshots,
        })
    except Exception as e:
        logger.exception(f"api_calibration_snapshots: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/calibration/save', methods=['POST'])
def api_calibration_save():
    try:
        ok = save_calibration_snapshot()
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        logger.exception(f"api_calibration_save: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/calibration/snapshots/<int:idx>', methods=['DELETE'])
def api_calibration_snapshot_delete(idx):
    try:
        snapshots = _load_calibration_snapshots()
        snapshots.sort(key=lambda x: x.get('saved_at_ts', 0), reverse=True)
        if idx < 0 or idx >= len(snapshots):
            return jsonify({'status': 'error', 'error': 'Index out of range'}), 404
        snapshots.pop(idx)
        _save_calibration_snapshots(snapshots)
        return jsonify({'status': 'ok', 'count': len(snapshots)})
    except Exception as e:
        logger.exception(f"api_calibration_snapshot_delete: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
