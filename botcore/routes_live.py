# ============================================================
# botcore/routes_live.py — Вкладка Live (/api/live)
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

__all__ = [
    'api_live',
]


# ============================================================
# ★ API: LIVE
# ============================================================
@app.route('/api/live', methods=['GET'])
def api_live():
    try:
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
        today_str = now_msk.strftime('%Y-%m-%d')

        with cache_lock:
            cache = storage.load_cache()

        _all_analyzed = cache.get('all_analyzed', [])
        _top_matches = cache.get('top_matches', [])

        _top_by_fid = {}
        for _m in _top_matches:
            _fid = _m.get('fixture_id')
            if _fid:
                _top_by_fid[_fid] = _m

        all_matches = []
        _seen_fids = set()
        for _m in _all_analyzed:
            _fid = _m.get('fixture_id')
            if _fid and _fid in _top_by_fid:
                if _fid not in _seen_fids:
                    all_matches.append(_top_by_fid[_fid])
                    _seen_fids.add(_fid)
            else:
                if _fid not in _seen_fids or not _fid:
                    all_matches.append(_m)
                    if _fid:
                        _seen_fids.add(_fid)

        for _m in _top_matches:
            _fid = _m.get('fixture_id')
            if _fid and _fid not in _seen_fids:
                all_matches.append(_m)
                _seen_fids.add(_fid)

        # ★ только лиги Line Movement
        all_matches = lm_filter(all_matches)

        # ★ + все матчи этих лиг из дневного батча (чтобы вкладка не была пустой)
        live_data = {}
        if getattr(Config, 'LIVE_BATCH_ENABLED', True):
            live_data = dict(_fetch_live_batch(today_str))
        _known = {x.get('fixture_id') for x in all_matches}
        _ids = set(_lm_league_ids())
        for _fid, _f in live_data.items():
            if _fid in _known:
                continue
            _lg = _f.get('league') or {}
            if _lg.get('id') not in _ids:
                continue
            _ts = (_f.get('fixture') or {}).get('timestamp')
            if not _ts:
                continue
            _dt = datetime(1970, 1, 1) + timedelta(seconds=_ts + TIMEZONE_OFFSET * 3600)
            _tm = _f.get('teams') or {}
            _cn, _cf = Config.LEAGUE_COUNTRY.get(_lg.get('id'), ('', ''))
            all_matches.append({
                'fixture_id': _fid,
                'home': (_tm.get('home') or {}).get('name', '?'),
                'away': (_tm.get('away') or {}).get('name', '?'),
                'league': _lg.get('name', ''), 'league_id': _lg.get('id'),
                'country': _cn, 'country_flag': _cf,
                'match_time': _dt.strftime('%d.%m.%Y %H:%M'),
                'source': 'line_movement', 'best_bet': {}, 'total_xg': 0,
            })

        if not all_matches:
            return jsonify({'status': 'ok', 'count': 0, 'matches': [],
                            'now': now_msk.strftime('%H:%M')})

        hours_before = getattr(Config, 'LIVE_HOURS_BEFORE', 2)
        minutes_after = getattr(Config, 'LIVE_MINUTES_AFTER', 120)
        max_matches = getattr(Config, 'LIVE_MAX_MATCHES', 50)

        in_window = []
        seen_fids = set()
        for m in all_matches:
            fid = m.get('fixture_id')
            if not fid or fid in seen_fids:
                continue
            mt_str = m.get('match_time', '')
            if not mt_str or mt_str == '?':
                continue
            try:
                match_dt = datetime.strptime(mt_str, "%d.%m.%Y %H:%M")
            except ValueError:
                continue
            delta_min = (match_dt - now_msk).total_seconds() / 60
            if -minutes_after <= delta_min <= hours_before * 60:
                in_window.append((m, match_dt, delta_min))
                seen_fids.add(fid)

        if not in_window:
            return jsonify({'status': 'ok', 'count': 0, 'matches': [],
                            'now': now_msk.strftime('%H:%M'),
                            'window': f"-{minutes_after}м .. +{hours_before}ч"})

        in_window.sort(key=lambda x: x[2])
        in_window = in_window[:max_matches]

        # live_data уже загружен выше (_fetch_live_batch)

        sparkline_data = {}
        if getattr(Config, 'LIVE_SPARKLINE_ENABLED', True):
            try:
                all_fids = [m.get('fixture_id') for m, _, _ in in_window if m.get('fixture_id')]
                if all_fids:
                    MARKETS_TO_SCAN = [
                        ('1X2', '1', 'П1'),
                        ('1X2', 'X', 'X'),
                        ('1X2', '2', 'П2'),
                        ('DC', '1X', '1X'),
                        ('DC', 'X2', 'X2'),
                        ('O/U 2.5', 'Under', 'ТМ 2.5'),
                        ('O/U 2.5', 'Over', 'ТБ 2.5'),
                    ]
                    sparkline_data = {}
                    for mkt, sel, lbl in MARKETS_TO_SCAN:
                        try:
                            batch = storage.get_odds_history_batch(
                                fixture_ids=all_fids,
                                market=mkt,
                                selection=sel,
                                limit=getattr(Config, 'LIVE_SPARKLINE_POINTS', 10),
                            )
                        except Exception as e:
                            logger.debug(f"batch {mkt}/{sel}: {e}")
                            continue
                        for fid_key, points in (batch or {}).items():
                            if not points or len(points) < 2:
                                continue
                            first = float(points[0].get('odds', 0) or 0)
                            last = float(points[-1].get('odds', 0) or 0)
                            if first <= 1.01 or last <= 1.01:
                                continue
                            change_pct = abs((last / first) - 1) * 100
                            existing = sparkline_data.get(fid_key)
                            if existing and existing.get('change_pct', 0) >= change_pct:
                                continue
                            sparkline_data[fid_key] = {
                                'points': points,
                                'market': mkt,
                                'selection': sel,
                                'label': lbl,
                                'change_pct': round(change_pct, 1),
                            }
                    logger.info(f"📈 Sparkline: {len(sparkline_data)} матчей (из {len(all_fids)})")
            except Exception as e:
                logger.error(f"Sparkline batch error: {e}")

        result = []
        for m, match_dt, delta_min in in_window:
            fid = m.get('fixture_id')

            if (delta_min < 0 and fid and fid not in live_data
                    and delta_min > -180):
                try:
                    single = football_api.get_match_result(fid)
                    if single:
                        live_data[fid] = {
                            'fixture': {'status': {
                                'short': single.get('status', 'NS'),
                                'elapsed': single.get('minute', 0)
                            }},
                            'goals': single.get('goals', {}),
                            'score': {
                                'halftime': single.get('halftime', {})
                            }
                        }
                        logger.info(f"🔍 Live single fetch: {fid} → {single.get('status')}")
                except Exception as e:
                    logger.debug(f"Live single fetch {fid}: {e}")

            best_bet = m.get('best_bet', {}) or {}

            if not best_bet.get('label') or (best_bet.get('odds') or 0) <= 1.01:
                try:
                    with cache_lock:
                        _cache = storage.load_cache()
                    _top = _cache.get('top_matches', [])
                    for _tm in _top:
                        if _tm.get('fixture_id') == fid:
                            best_bet = _tm.get('best_bet', {}) or {}
                            break
                except Exception as e:
                    logger.debug(f"api_live best_bet lookup {fid}: {e}")

            bet_label = best_bet.get('label') or '—'
            bet_odds = best_bet.get('odds', 0) or 0
            bet_ev = best_bet.get('ev', 0) or 0
            bet_prob = best_bet.get('prob', 0) or 0

            live_status = None
            live_minute = 0
            live_score = None
            live_halftime = None
            is_live = False
            is_final = False
            status_short = 'NS'

            if fid and fid in live_data:
                f = live_data[fid]
                status = f.get('fixture', {}).get('status', {})
                goals = f.get('goals', {})
                score = f.get('score', {})
                status_short = status.get('short', 'NS')
                live_minute = status.get('elapsed', 0) or 0

                ht = score.get('halftime', {}) or {}
                if ht.get('home') is not None and ht.get('away') is not None:
                    live_halftime = f"{ht['home']}-{ht['away']}"

                force_final_by_minute = (
                    live_minute >= 95
                    and status_short not in ('HT', 'ET', 'BT', 'P', 'SUSP')
                )

                if status_short in FINAL_STATUSES or force_final_by_minute:
                    is_final = True
                    is_live = False
                    if force_final_by_minute and status_short not in FINAL_STATUSES:
                        logger.warning(
                            f"⚠️ Force-final: fid={fid} | status={status_short} | min={live_minute}"
                        )
                    hg = goals.get('home')
                    ag = goals.get('away')
                    if hg is not None and ag is not None:
                        live_score = f"{hg}:{ag}"
                elif status_short in LIVE_STATUSES:
                    is_live = True
                    hg = goals.get('home')
                    ag = goals.get('away')
                    if hg is not None and ag is not None:
                        live_score = f"{hg}:{ag}"

            odds_trend = 0
            try:
                if fid and bet_label:
                    bt_lower = bet_label.lower()
                    if 'x2' in bt_lower:
                        dc_hist = storage.get_odds_history(fid, 'DC', 'X2')
                    elif '1x' in bt_lower:
                        dc_hist = storage.get_odds_history(fid, 'DC', '1X')
                    else:
                        dc_hist = []
                    if dc_hist and len(dc_hist) >= 2:
                        f0 = float(dc_hist[0].get('odds', 0))
                        f1 = float(dc_hist[-1].get('odds', 0))
                        if f0 > 0:
                            odds_trend = round(((f1 / f0) - 1) * 100, 1)
            except Exception:
                pass

            sparkline_points = []
            sparkline_label = '—'
            sparkline_market = '—'
            sparkline_selection = '—'
            sparkline_change = 0
            spark_info = sparkline_data.get(fid)
            if spark_info:
                sparkline_points = [
                    {'odds': p.get('odds', 0), 'ts': p.get('ts', '')}
                    for p in spark_info.get('points', [])
                ]
                sparkline_label = spark_info.get('label', '—')
                sparkline_market = spark_info.get('market', '—')
                sparkline_selection = spark_info.get('selection', '—')
                sparkline_change = spark_info.get('change_pct', 0)

            result.append({
                'fixture_id': fid,
                'home': m.get('home', '?'),
                'away': m.get('away', '?'),
                'league': m.get('league', '?'),
                'country': m.get('country', ''),
                'country_flag': m.get('country_flag', ''),
                'match_time': m.get('match_time', ''),
                'match_time_iso': match_dt.isoformat(),
                'minutes_to_match': int(delta_min),
                'is_live': is_live,
                'is_final': is_final,
                'status': status_short,
                'minute': live_minute,
                'score': live_score,
                'halftime': live_halftime,
                'best_bet': {
                    'label': bet_label if bet_prob > 0 else '—',
                    'odds': bet_odds if bet_prob > 0 else 0,
                    'ev': bet_ev if bet_prob > 0 else 0,
                    'prob': bet_prob,
                },
                'odds_trend': odds_trend,
                'sparkline': sparkline_points,
                'sparkline_market': sparkline_market,
                'sparkline_selection': sparkline_selection,
                'sparkline_label': sparkline_label,
                'sparkline_change': sparkline_change,
                'source': m.get('source', '70_percent'),
                'total_xg': m.get('total_xg', 0),
            })

        logger.info(f"⚡ Live: {len(result)} матчей в окне")
        return jsonify({
            'status': 'ok',
            'count': len(result),
            'now': now_msk.strftime('%H:%M'),
            'window': f"-{minutes_after}м .. +{hours_before}ч",
            'matches': result,
        })
    except Exception as e:
        logger.exception(f"api_live error: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'matches': []}), 500
