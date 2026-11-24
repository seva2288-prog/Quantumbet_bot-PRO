# ============================================================
# botcore/routes_x2.py — X2, автоставки, CLV, симулятор (API)
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

__all__ = [
    'api_x2_auto',
    'api_x2_candidates',
    'api_x2_candidates_clear',
    'api_x2_data_get',
    'api_x2_data_post',
    'api_autobets_state',
    'api_autobets_history',
    'api_autobets_place',
    'api_autobets_settle',
    'api_autobets_live',
    'api_autobets_reset',
    'api_autobets_clv_compute',
    'api_autobets_clv_stats',
    'api_clv_by_strategy',
    'api_simulator_run',
    'api_simulator_save',
    'api_simulator_presets',
    'api_simulator_grid_search',
    'api_simulator_train_test',
    'api_simulator_train_test_grid',
    'api_simulator_3way_split',
    'api_simulator_3way_split_grid',
]


# Кэш свежих кэфов для X2-кандидатов: раньше каждый заход на страницу слал по 2 запроса на каждого кандидата
_X2_FRESH_CACHE = {}   # fid -> (ts, x2, 1x) | (ts, None)  (None = матч идёт/закончен, не трогаем)
_X2_FRESH_TTL = 900


def _x2_fresh_odds(fid):
    import time as _t
    now = _t.time()
    hit = _X2_FRESH_CACHE.get(fid)
    if hit and now - hit[0] < _X2_FRESH_TTL:
        return hit[1:] if hit[1] is not None else None
    md = football_api.get_match_result(fid)
    if md and (md.get('is_final') or md.get('is_live')):
        _X2_FRESH_CACHE[fid] = (now + 86400 * 365, None)   # завершённый/идущий матч больше не опрашиваем
        return None
    od = football_api.get_match_odds(fid) if md else None
    if not od:
        _X2_FRESH_CACHE[fid] = (now, 0, 0)
        return (0, 0)
    res = (now, od.get('x2_odds', 0) or 0, od.get('1x_odds', 0) or 0)
    _X2_FRESH_CACHE[fid] = res
    return res[1:]


# ============================================================
# API: X2
# ============================================================
@app.route('/api/x2_auto', methods=['GET'])
def api_x2_auto():
    try:
        candidates = lm_filter(storage.get_x2_candidates(limit=100))
        if not candidates:
            return jsonify({'status': 'ok', 'count': 0, 'candidates': []})

        enriched = []
        for c in candidates:
            fid = c.get('fixture_id')
            league_id = None
            for lid, lname in Config.LEAGUE_NAMES.items():
                if lname == c.get('league'):
                    league_id = lid
                    break

            country_name, country_flag = ("", "")
            if league_id:
                country_name, country_flag = Config.LEAGUE_COUNTRY.get(
                    league_id, ("", "")
                )

            current_odds = float(c.get('entry_odds', 0) or 0)
            current_1x_odds = float(c.get('entry_1x_odds', 0) or 0)
            odds_trend = 0
            try:
                if fid:
                    fresh = _x2_fresh_odds(fid)
                    if fresh:
                        if fresh[0] > 0:
                            current_odds = fresh[0]
                        if fresh[1] > 0:
                            current_1x_odds = fresh[1]

                    if c.get('x2_side') == 'X2':
                        dc_hist = storage.get_odds_history(fid, 'DC', 'X2')
                    else:
                        dc_hist = storage.get_odds_history(fid, 'DC', '1X')

                    if dc_hist and len(dc_hist) >= 2:
                        first_odd = float(dc_hist[0].get('odds', 0))
                        last_odd = float(dc_hist[-1].get('odds', 0))
                        if first_odd > 0:
                            odds_trend = round(((last_odd / first_odd) - 1) * 100, 1)
                        if current_odds <= 0 and first_odd > 0:
                            current_odds = first_odd
            except Exception as e:
                logger.debug(f"x2_auto enrich {fid}: {e}")

            if current_odds <= 0 and c.get('x2_prob', 0) > 0:
                p = c.get('x2_prob', 0) / 100
                if p > 0:
                    current_odds = round((1 / p) * 0.95, 2)

            enriched.append({
                'id': c.get('id'),
                'home': c.get('home'),
                'away': c.get('away'),
                'match': f"{c.get('home')} vs {c.get('away')}",
                'favorite': c.get('favorite'),
                'underdog': c.get('underdog'),
                'league': c.get('league'),
                'country': country_name,
                'country_flag': country_flag,
                'match_time': c.get('match_time'),
                'fixture_id': fid,
                'x2_side': c.get('x2_side', 'X2'),
                'x2_ev': c.get('x2_ev', 0),
                'x2_prob': c.get('x2_prob', 0),
                'home_position': c.get('home_position'),
                'away_position': c.get('away_position'),
                'home_form': c.get('home_form'),
                'away_form': c.get('away_form'),
                'total_xg': c.get('total_xg'),
                'entry_odds': c.get('entry_odds', 0),
                'entry_1x_odds': c.get('entry_1x_odds', 0),
                'current_odds': current_odds,
                'current_1x_odds': current_1x_odds,
                'odds_trend': odds_trend,
                'result': c.get('result', 'pending'),
                'profit': c.get('profit', 0),
                'home_goals': c.get('home_goals'),
                'away_goals': c.get('away_goals'),
                'settled_at': c.get('settled_at'),
                'created_at': c.get('created_at'),
                'source': 'auto',
            })

        return jsonify({
            'status': 'ok',
            'count': len(enriched),
            'candidates': enriched,
        })
    except Exception as e:
        logger.exception(f"api_x2_auto error: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'candidates': []}), 500


@app.route('/api/x2_candidates', methods=['GET'])
def api_x2_candidates():
    try:
        candidates = storage.get_x2_candidates(limit=500)
        return jsonify({'status': 'ok', 'count': len(candidates), 'candidates': candidates})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e), 'candidates': []}), 500


@app.route('/api/x2_candidates/clear', methods=['POST'])
def api_x2_candidates_clear():
    try:
        ok = storage.clear_x2_candidates()
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/x2_data', methods=['GET'])
def api_x2_data_get():
    try:
        data = []
        if os.path.exists(X2_FILE):
            with open(X2_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        data = lm_filter(data) if isinstance(data, list) else data
        return jsonify({'status': 'ok', 'data': data or []})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/x2_data', methods=['POST'])
def api_x2_data_post():
    try:
        data = request.json
        if not data or 'data' not in data:
            return jsonify({'error': 'No data'}), 400
        try:
            os.makedirs(os.path.dirname(X2_FILE) or '.', exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(X2_FILE) or '.', suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data['data'], f, indent=2, ensure_ascii=False)
            os.replace(tmp, X2_FILE)
            ok = True
        except Exception:
            ok = False
        return jsonify({'status': 'ok' if ok else 'error', 'count': len(data['data'])})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: АВТОСТАВКИ
# ============================================================
@app.route('/api/autobets/state', methods=['GET'])
def api_autobets_state():
    try:
        return jsonify(autobet_manager.get_state())
    except Exception as e:
        return jsonify({'bank': 1000, 'start_bank': 1000, 'total_profit': 0,
                        'total_bets': 0, 'wins': 0, 'losses': 0, 'pending': 0,
                        'live_count': 0, 'roi': 0, 'winrate': 0, 'stake_pct': 2,
                        'avg_clv': 0, 'clv_count': 0}), 200


@app.route('/api/autobets/history', methods=['GET'])
def api_autobets_history():
    try:
        limit = int(request.args.get('limit', 100))
        return jsonify(lm_filter(storage.autobet_get_history(1000))[:limit])
    except Exception as e:
        return jsonify([])


@app.route('/api/autobets/place', methods=['POST'])
def api_autobets_place():
    try:
        placed = autobet_manager.place_bets_from_cache()
        return jsonify({'status': 'ok', 'placed': placed})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/settle', methods=['POST'])
def api_autobets_settle():
    try:
        updated = autobet_manager.settle_pending()
        return jsonify({'status': 'ok', 'updated': updated})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/live', methods=['POST'])
def api_autobets_live():
    try:
        updated = autobet_manager.update_live_scores()
        return jsonify({'status': 'ok', 'updated': updated})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/reset', methods=['POST'])
def api_autobets_reset():
    try:
        ok = autobet_manager.reset()
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/clv/compute', methods=['POST'])
def api_autobets_clv_compute():
    try:
        updated = autobet_manager.compute_clv_for_settled()
        return jsonify({'status': 'ok', 'updated': updated})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/clv/stats', methods=['GET'])
def api_autobets_clv_stats():
    try:
        bets = storage.autobet_load_all()
        clv_values = [b['clv'] for b in bets if b.get('clv') is not None]
        if not clv_values:
            return jsonify({'status': 'ok', 'count': 0, 'avg_clv': 0,
                            'positive_count': 0, 'negative_count': 0, 'positive_rate': 0})
        positive = [c for c in clv_values if c > 0]
        negative = [c for c in clv_values if c < 0]
        return jsonify({
            'status': 'ok', 'count': len(clv_values),
            'avg_clv': round(sum(clv_values) / len(clv_values), 2),
            'positive_count': len(positive),
            'negative_count': len(negative),
            'positive_rate': round(len(positive) / len(clv_values) * 100, 1),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/clv/by_strategy', methods=['GET'])
def api_clv_by_strategy():
    try:
        days = int(request.args.get('days', 30))
        stats = _compute_all_strategy_clv(days=days)
        return jsonify({'status': 'ok', 'days': days, 'strategies': stats})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: СИМУЛЯТОР
# ============================================================
@app.route('/api/simulator/run', methods=['POST'])
def api_simulator_run():
    try:
        params = request.json or {}
        result = strategy_simulator.simulate(params)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/save', methods=['POST'])
def api_simulator_save():
    try:
        data = request.json or {}
        name = data.get('name', 'Без названия')
        result = data.get('result', {})
        params = data.get('result', {}).get('params', {})
        if not result:
            return jsonify({'error': 'No result'}), 400
        ok = storage.save_simulation(name, params, result)
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/presets', methods=['GET'])
def api_simulator_presets():
    presets = {
        'conservative': {'name': '🛡️ Осторожная', 'params': {
            'min_ev': 15, 'max_ev': 100, 'min_prob': 60, 'max_prob': 100,
            'min_odds': 1.5, 'max_odds': 3.5, 'min_xg': 1.5, 'max_xg': 3.0,
            'bet_types': ['under', '1x', 'x2'], 'leagues': [],
            'stake_pct': 1.5, 'start_bank': 1000}},
        'balanced': {'name': '⚖️ Сбалансированная', 'params': {
            'min_ev': 10, 'max_ev': 100, 'min_prob': 52, 'max_prob': 100,
            'min_odds': 1.4, 'max_odds': 5.0, 'min_xg': 1.2, 'max_xg': 3.5,
            'bet_types': [], 'leagues': [], 'stake_pct': 2.0, 'start_bank': 1000}},
        'aggressive': {'name': '🔥 Агрессивная', 'params': {
            'min_ev': 5, 'max_ev': 200, 'min_prob': 45, 'max_prob': 100,
            'min_odds': 1.4, 'max_odds': 8.0, 'min_xg': 0.8, 'max_xg': 4.0,
            'bet_types': [], 'leagues': [], 'stake_pct': 3.0, 'start_bank': 1000}},
        'value_only': {'name': '💎 Только VALUE', 'params': {
            'min_ev': 50, 'max_ev': 500, 'min_prob': 60, 'max_prob': 100,
            'min_odds': 2.5, 'max_odds': 6.0, 'min_xg': 1.0, 'max_xg': 3.5,
            'bet_types': ['1X', 'X2', 'П1', 'П2'], 'leagues': [],
            'stake_pct': 2.0, 'start_bank': 1000}},
    }
    return jsonify(presets)


@app.route('/api/simulator/grid_search', methods=['POST'])
def api_simulator_grid_search():
    try:
        data = request.json or {}
        max_combinations = int(data.get('max_combinations', 200))
        min_bets = int(data.get('min_bets', 5))
        result = strategy_simulator.grid_search(max_combinations=max_combinations, min_bets=min_bets)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/train_test', methods=['POST'])
def api_simulator_train_test():
    try:
        data = request.json or {}
        params = data.get('params', {})
        test_size = float(data.get('test_size', 0.3))
        result = strategy_simulator.run_train_test(params, test_size)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        logger.exception(f"api_simulator_train_test error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/train_test_grid', methods=['POST'])
def api_simulator_train_test_grid():
    try:
        data = request.json or {}
        max_combinations = int(data.get('max_combinations', 100))
        min_bets = int(data.get('min_bets', 20))
        test_size = float(data.get('test_size', 0.3))
        result = strategy_simulator.grid_search_train_test(
            max_combinations=max_combinations,
            min_bets=min_bets,
            test_size=test_size,
        )
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        logger.exception(f"api_simulator_train_test_grid error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/3way_split', methods=['POST'])
def api_simulator_3way_split():
    try:
        data = request.json or {}
        params = data.get('params', {})
        test_size = float(data.get('test_size', 0.2))
        valid_size = float(data.get('valid_size', 0.2))
        result = strategy_simulator.run_3way_split(params, test_size, valid_size)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        logger.exception(f"api_simulator_3way_split error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/3way_split_grid', methods=['POST'])
def api_simulator_3way_split_grid():
    try:
        data = request.json or {}
        max_combinations = int(data.get('max_combinations', 100))
        min_bets = int(data.get('min_bets', 30))
        test_size = float(data.get('test_size', 0.2))
        valid_size = float(data.get('valid_size', 0.2))
        result = strategy_simulator.grid_search_3way(
            max_combinations=max_combinations,
            min_bets=min_bets,
            test_size=test_size,
            valid_size=valid_size,
        )
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        logger.exception(f"api_simulator_3way_split_grid error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
