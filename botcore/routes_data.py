# ============================================================
# botcore/routes_data.py — Данные: статистика, история, матчи, снимки, аномалии, правка ставок
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

__all__ = [
    'api_stats',
    'api_history',
    'api_matches',
    'all_data',
    'update_bank',
    'keepalive',
    'api_matches_log',
    'api_snapshot',
    'api_anomaly_set_result',
    'api_anomalies',
    'api_snapshots_list',
    'api_day_matches',
    '_build_day_matches',
    'notify_day_events',
    '_quiet_now',
    '_lm_bets_with_clv',
    '_agg_bets',
    '_flag_weak',
    '_bet_ts',
    '_streaks',
    'api_real_odds_get',
    'api_real_odds_set',
    '_bet_selection',
    'api_lm_analytics',
    'api_export_history_csv',
    'api_bot_health',
    'api_notes_get',
    'api_notes_set',
    'api_snapshots_detail',
    'api_snapshot_anomalies',
    'api_snapshot_anomalies_stats',
    'edit_bet',
    'delete_bet',
    'add_manual_match',
    'update_settings',
    'import_project',
    'void_old_endpoint',
]


# ============================================================
# API: ОСНОВНЫЕ
# ============================================================
@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = storage.load_stats()
    bank = storage.load_bank()
    return jsonify({'bank': bank, **stats})


@app.route('/api/history', methods=['GET'])
def api_history():
    return jsonify(storage.load_history())


@app.route('/api/matches', methods=['GET'])
def api_matches():
    cache = storage.load_cache()
    return jsonify(lm_filter(cache.get('top_matches', [])))


@app.route('/api/all_data', methods=['GET'])
def all_data():
    try:
        bank = storage.load_bank()
        history = lm_filter(storage.load_history())     # ★ только лиги Line Movement
        stats = _stats_from_history(history)
        cache = storage.load_cache()
        profit_data = get_profit_data(history)
        return jsonify({
            'stats': {'bank': bank, 'total_bets': stats.get('total', 0),
                      'wins': stats.get('wins', 0), 'losses': stats.get('losses', 0),
                      'profit': stats.get('total_profit', 0),
                      'winrate': stats.get('winrate', 0),
                      'roi': stats.get('roi', 0), 'avg_stake': stats.get('avg_stake', 0)},
            'history': history, 'profit_data': profit_data,
            'matches': lm_filter(cache.get('top_matches', []))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        if 'bank' in data:
            storage.save_bank(data['bank'])
            return jsonify({'success': True, 'bank': data['bank']})
        return jsonify({'error': 'No bank value'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keepalive', methods=['GET'])
def keepalive():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


@app.route('/api/matches_log', methods=['GET'])
def api_matches_log():
    try:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return jsonify({'log': content[-100000:], 'status': 'ok', 'size': len(content)})
        return jsonify({'log': '', 'status': 'empty'})
    except Exception as e:
        return jsonify({'log': '', 'error': str(e)}), 500


@app.route('/api/snapshot', methods=['GET'])
def api_snapshot():
    try:
        n = snapshot_odds_for_upcoming()
        return jsonify({'status': 'ok', 'snapshots': n})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/anomaly_set_result', methods=['POST'])
def api_anomaly_set_result():
    """Ручной ввод результата аномалии."""
    try:
        data = request.json or {}
        fixture_id = data.get('fixture_id')
        home_goals = data.get('home_goals')
        away_goals = data.get('away_goals')
        selection = (data.get('selection') or '').upper().strip()

        if fixture_id is None or home_goals is None or away_goals is None:
            return jsonify({'status': 'error', 'error': 'fixture_id, home_goals, away_goals обязательны'}), 400

        hg = int(home_goals)
        ag = int(away_goals)

        if selection == 'X2':
            result = 'win' if ag >= hg else 'loss'
        elif selection == '1X':
            result = 'win' if hg >= ag else 'loss'
        elif selection in ('П1', '1'):
            result = 'win' if hg > ag else 'loss'
        elif selection in ('П2', '2'):
            result = 'win' if ag > hg else 'loss'
        elif selection == 'X':
            result = 'win' if hg == ag else 'loss'
        elif selection == 'ТМ 2.5':
            result = 'win' if (hg + ag) < 2.5 else 'loss'
        elif selection == 'ТБ 2.5':
            result = 'win' if (hg + ag) > 2.5 else 'loss'
        elif selection == 'ОБЗ':
            result = 'win' if hg > 0 and ag > 0 else 'loss'
        else:
            result = 'unknown'

        ok = storage.update_anomaly(
            fixture_id=int(fixture_id),
            result=result,
            home_goals=hg,
            away_goals=ag,
        )

        if ok:
            logger.info(f"✏️ Аномалия вручную: fid={fixture_id} | {hg}:{ag} | {result.upper()}")
            return jsonify({
                'status': 'ok',
                'result': result,
                'home_goals': hg,
                'away_goals': ag,
            })
        return jsonify({'status': 'error', 'error': 'Не удалось сохранить'}), 500
    except Exception as e:
        logger.exception(f"api_anomaly_set_result: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/anomalies', methods=['GET'])
def api_anomalies():
    """Возвращает пропущенные аномалии с результатами (через storage)."""
    try:
        items = lm_filter(storage.load_anomalies(limit=200))
        stats = storage.get_anomaly_stats(stake_per_bet=50.0)
        return jsonify({
            'status': 'ok',
            'count': len(items),
            'items': items,
            'stats': stats,
        })
    except Exception as e:
        logger.exception(f"api_anomalies: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ API: СНИМКИ — список
# ============================================================
@app.route('/api/snapshots', methods=['GET'])
def api_snapshots_list():
    try:
        days = int(request.args.get('days', 7))
        only_anomaly = request.args.get('only_anomaly', 'false').lower() == 'true'
        only_today = request.args.get('only_today', 'false').lower() == 'true'
        q_text = request.args.get('q', '').strip().lower()
        today_ddmmyyyy = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%d.%m.%Y')
        limit = int(request.args.get('limit', 50))
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        matches_raw = _lm_snapshots_since(cutoff)

        grouped = {}
        for row in matches_raw:
            fid = row.get('fixture_id')
            if not fid: continue
            if fid not in grouped:
                grouped[fid] = {
                    'fixture_id': fid,
                    'snapshots': [],
                    'home': row.get('home', ''),
                    'away': row.get('away', ''),
                    'league': row.get('league', ''),
                    'match_time': row.get('match_time') or '',
                    'first_time': None,
                    'last_time': None,
                }
            grouped[fid]['snapshots'].append(row)
            if row.get('home') and not grouped[fid]['home']:
                grouped[fid]['home'] = row['home']
            if row.get('away') and not grouped[fid]['away']:
                grouped[fid]['away'] = row['away']
            if row.get('league') and not grouped[fid]['league']:
                grouped[fid]['league'] = row['league']
            if row.get('match_time') and not grouped[fid]['match_time']:
                grouped[fid]['match_time'] = row['match_time']

            t = row.get('created_at')
            if t:
                if not grouped[fid]['first_time'] or t < grouped[fid]['first_time']:
                    grouped[fid]['first_time'] = t
                if not grouped[fid]['last_time'] or t > grouped[fid]['last_time']:
                    grouped[fid]['last_time'] = t

        cache = storage.load_cache()
        all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
        match_time_lookup = {}
        for m in all_matches:
            fid = m.get('fixture_id')
            if fid and fid not in match_time_lookup:
                match_time_lookup[fid] = m.get('match_time', '?')

        result = []
        for fid, info in grouped.items():
            snaps = info['snapshots']
            if not snaps: continue

            first_odds = {'1': 0, 'X': 0, '2': 0, '1X': 0, 'X2': 0}
            last_odds = {'1': 0, 'X': 0, '2': 0, '1X': 0, 'X2': 0}
            anomalies = []

            for s in snaps:
                sel = s.get('selection', '')
                odd = s.get('odds', 0)
                if sel in first_odds:
                    if not first_odds[sel]: first_odds[sel] = odd
                    last_odds[sel] = odd

            for sel in ['1', 'X', '2', '1X', 'X2']:
                if first_odds[sel] > 0 and last_odds[sel] > 0:
                    trend = ((last_odds[sel] / first_odds[sel]) - 1) * 100
                    if abs(trend) > 5:
                        anomalies.append({
                            'selection': sel, 'first': first_odds[sel],
                            'last': last_odds[sel], 'trend': round(trend, 1)
                        })
            if only_anomaly and not anomalies:
                continue
            if q_text and q_text not in f"{info['home']} {info['away']} {info['league']}".lower():
                continue

            mt_value = info.get('match_time') or match_time_lookup.get(fid, '?')
            if only_today and not str(mt_value).startswith(today_ddmmyyyy):
                continue

            result.append({
                'fixture_id': fid,
                'home': info['home'] or '?',
                'away': info['away'] or '?',
                'league': info['league'] or '?',
                'match_time': mt_value,
                'snapshot_count': len(snaps),
                'first_time': info['first_time'],
                'last_time': info['last_time'],
                'first': first_odds,
                'last': last_odds,
                'anomalies': anomalies,
            })

        result.sort(key=lambda x: x.get('last_time', ''), reverse=True)
        result = result[:limit]
        return jsonify({
            'status': 'ok', 'count': len(result), 'days': days,
            'only_anomaly': only_anomaly, 'matches': result,
        })
    except Exception as e:
        logger.exception(f"api_snapshots_list error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


def _build_day_matches():
    """Матчи дня со снимками: счёт + движение кэфов (общая логика для API и уведомлений)."""
    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    today_dm = now_msk.strftime('%d.%m.%Y')
    today_api = now_msk.strftime('%Y-%m-%d')
    cutoff = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
    rows = _lm_snapshots_since(cutoff)
    try:
        batch = _fetch_live_batch(today_api) or {}
    except Exception:
        batch = {}

    grouped = {}
    for r in rows:
        fid = r.get('fixture_id')
        if fid:
            grouped.setdefault(fid, []).append(r)

    try:
        hist = {}
        for b in storage.load_history():
            if b.get('fixture_id'):
                hist[b['fixture_id']] = b
    except Exception:
        hist = {}

    out = []
    for fid, snaps in grouped.items():
        snaps.sort(key=lambda s: s.get('created_at') or '')
        first = snaps[0]
        mt = next((s.get('match_time') for s in snaps if s.get('match_time')), '') or ''
        fx = batch.get(fid)
        if not fx and not str(mt).startswith(today_dm):
            continue

        sel = {}
        for s in snaps:
            k = s.get('selection')
            o = s.get('odds') or 0
            if not k or o <= 0:
                continue
            d = sel.setdefault(k, {'points': []})
            d['points'].append([(s.get('created_at') or '')[11:16], o])
        selections = {}
        for k, d in sel.items():
            pts = d['points']
            f0, l0 = pts[0][1], pts[-1][1]
            vals = [p[1] for p in pts]
            selections[k] = {
                'first': f0, 'last': l0, 'min': min(vals), 'max': max(vals),
                'change_pct': round((l0 / f0 - 1) * 100, 1) if f0 else 0,
                'count': len(pts), 'points': pts[-120:],
            }

        lid = first.get('league_id')
        cn, cf = Config.LEAGUE_COUNTRY.get(lid, ('', ''))
        item = {
            'fixture_id': fid,
            'home': first.get('home') or '?', 'away': first.get('away') or '?',
            'league': first.get('league') or '', 'league_id': lid,
            'country': cn, 'country_flag': cf,
            'match_time': mt, 'snapshots_count': len(snaps),
            'selections': selections,
            'status': 'NS', 'elapsed': None,
            'home_goals': None, 'away_goals': None,
            'halftime_home': None, 'halftime_away': None,
        }
        if fx:
            st = (fx.get('fixture') or {}).get('status') or {}
            g = fx.get('goals') or {}
            ht = (fx.get('score') or {}).get('halftime') or {}
            item.update(status=st.get('short') or 'NS', elapsed=st.get('elapsed'),
                        home_goals=g.get('home'), away_goals=g.get('away'),
                        halftime_home=ht.get('home'), halftime_away=ht.get('away'))
        b = hist.get(fid)
        if b:
            item['bet'] = {'bet': b.get('bet'), 'odds': b.get('odds'),
                           'stake': b.get('stake'), 'result': b.get('result'),
                           'profit': b.get('profit')}
        out.append(item)

    out.sort(key=lambda x: (str(x['match_time'])[11:16], x['fixture_id']))
    return out, today_dm


@app.route('/api/day_matches', methods=['GET'])
def api_day_matches():
    try:
        out, today_dm = _build_day_matches()
        return jsonify({'status': 'ok', 'date': today_dm, 'count': len(out), 'matches': out})
    except Exception as e:
        logger.exception(f"api_day_matches error: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'matches': []}), 500


_DAY_NOTIFY_FILE = os.path.join(DATA_DIR, 'day_notify.json')
_SEL_NAMES = {'1': 'П1', 'X': 'Х', '2': 'П2', '1X': '1Х', 'X2': 'Х2'}


def _quiet_now():
    """Тихие часы уведомлений (по МСК). Окно может переходить через полночь."""
    if not getattr(Config, 'NOTIFY_QUIET_ENABLED', True):
        return False
    h = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).hour
    a = int(getattr(Config, 'NOTIFY_QUIET_FROM', 0))
    b = int(getattr(Config, 'NOTIFY_QUIET_TO', 8))
    if a == b:
        return False
    return (a <= h < b) if a < b else (h >= a or h < b)


def notify_day_events():
    """Telegram: сильное движение кэфа и завершение матчей со снимками (без повторов)."""
    if not getattr(Config, 'DAY_NOTIFY_ENABLED', True):
        return
    if _quiet_now():          # ночью молчим; события накопятся и придут утром одним сообщением
        return
    try:
        import html as _html
        items, today = _build_day_matches()
        try:
            with open(_DAY_NOTIFY_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            state = {}
        first = state.get('date') != today
        sent = set() if first else set(state.get('sent', []))
        thr = float(getattr(Config, 'DAY_NOTIFY_MOVE_PCT', 8))
        lines = []
        for d in items:
            fid = d['fixture_id']
            title = _html.escape(f"{d['home']} — {d['away']}")
            if d['status'] in ('FT', 'AET', 'PEN'):
                key = f"ft:{fid}"
                if key in sent:
                    continue
                sent.add(key)
                if first or d.get('home_goals') is None:
                    continue
                txt = f"🏁 <b>{title}</b>\nИтог: {d['home_goals']}:{d['away_goals']}"
                b = d.get('bet')
                if b and b.get('result') in ('win', 'loss', 'push'):
                    icon = {'win': '✅ WIN', 'loss': '❌ LOSS', 'push': '➖ PUSH'}[b['result']]
                    txt += f"\nСтавка {b.get('bet')} @ {b.get('odds')} — {icon}"
                lines.append(txt)
            else:
                for k, x in d['selections'].items():
                    ch = x.get('change_pct') or 0
                    if abs(ch) < thr:
                        continue
                    key = f"mv:{fid}:{k}:{1 if ch > 0 else -1}"
                    if key in sent:
                        continue
                    sent.add(key)
                    arrow = '📉' if ch < 0 else '📈'
                    lines.append(f"{arrow} <b>{title}</b>\n{_SEL_NAMES.get(k, k)}: {x['first']} → {x['last']} ({ch:+.1f}%)")
        try:
            with open(_DAY_NOTIFY_FILE, 'w', encoding='utf-8') as f:
                json.dump({'date': today, 'sent': sorted(sent)}, f)
        except Exception as e:
            logger.warning(f"day_notify: не удалось сохранить состояние: {e}")
        if lines:
            send_telegram('\n\n'.join(lines[:15]))
            logger.info(f"📨 day_notify: отправлено событий {min(len(lines), 15)}")
    except Exception as e:
        logger.exception(f"notify_day_events error: {e}")


# ============================================================
# ★ АНАЛИТИКА LINE MOVEMENT: CLV, разрезы по лигам и размеру движения
# ============================================================
_BET_SEL = {'П1': '1', 'P1': '1', '1': '1', 'Х': 'X', 'X': 'X', 'Н': 'X',
            'П2': '2', 'P2': '2', '2': '2', '1Х': '1X', '1X': '1X', 'Х2': 'X2', 'X2': 'X2'}


def _bet_selection(label):
    t = str(label or '').upper().replace(' ', '')
    return _BET_SEL.get(t)


_REAL_ODDS_FILE = os.path.join(DATA_DIR, 'real_odds.json')
_real_odds_lock = Lock()


def _load_real_odds():
    try:
        with open(_REAL_ODDS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


@app.route('/api/real_odds', methods=['GET'])
def api_real_odds_get():
    return jsonify({'status': 'ok', 'odds': _load_real_odds()})


@app.route('/api/real_odds', methods=['POST'])
def api_real_odds_set():
    try:
        body = request.get_json(silent=True) or {}
        key = str(body.get('key', '')).strip()[:100]
        if not key:
            return jsonify({'status': 'error', 'error': 'key required'}), 400
        raw = body.get('odds')
        with _real_odds_lock:
            d = _load_real_odds()
            if raw in (None, '', 0):
                d.pop(key, None)
            else:
                v = float(raw)
                if not (1.01 <= v <= 100):
                    return jsonify({'status': 'error', 'error': 'кэф должен быть 1.01…100'}), 400
                d[key] = round(v, 3)
            with open(_REAL_ODDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(d, f)
        return jsonify({'status': 'ok'})
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'error': 'кэф не число'}), 400
    except Exception as e:
        logger.exception(f"api_real_odds_set error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


def _bet_ts(b):
    """Время матча ставки (для порядка серий)."""
    for fmt, key in (('%d.%m.%Y %H:%M', 'match_time'), ('%Y-%m-%d %H:%M', 'date')):
        try:
            return datetime.strptime(str(b.get(key, ''))[:16], fmt)
        except Exception:
            pass
    return datetime.min


def _streaks(rows):
    seq = [b['result'] for b in sorted((b for b in rows if b.get('result') in ('win', 'loss')), key=_bet_ts)]
    best_w = best_l = cur = 0
    cur_type = None
    for r in seq:
        if r == cur_type:
            cur += 1
        else:
            cur_type, cur = r, 1
        if r == 'win':
            best_w = max(best_w, cur)
        else:
            best_l = max(best_l, cur)
    return {'best_win': best_w, 'best_loss': best_l,
            'current': cur if seq else 0, 'current_type': cur_type if seq else None}


def _lm_bets_with_clv():
    """Ставки Line Movement + CLV (кэф ставки vs последний снимок) и движение (первый снимок -> кэф ставки)."""
    hist = [b for b in lm_filter(storage.load_history())
            if b.get('source') == 'line_movement' or b.get('engine') == 'line_movement']
    cutoff = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
    idx = {}
    for r in storage.get_snapshots_since(cutoff):
        fid, sel, o, t = r.get('fixture_id'), r.get('selection'), r.get('odds') or 0, r.get('created_at') or ''
        if not fid or not sel or o <= 0:
            continue
        d = idx.setdefault((fid, sel), {'first': (t, o), 'last': (t, o)})
        if t < d['first'][0]:
            d['first'] = (t, o)
        if t >= d['last'][0]:
            d['last'] = (t, o)
    out = []
    real = _load_real_odds()
    for b in hist:
        row = dict(b)
        if b.get('fixture_id') and real.get('f' + str(b['fixture_id'])):
            row['real_odds'] = real['f' + str(b['fixture_id'])]
        sel = _bet_selection(b.get('bet'))
        d = idx.get((b.get('fixture_id'), sel)) if sel else None
        odds = b.get('odds') or 0
        row['clv'] = round((odds / d['last'][1] - 1) * 100, 2) if d and odds and d['last'][1] else None
        row['move'] = round((odds / d['first'][1] - 1) * 100, 2) if d and odds and d['first'][1] else None
        out.append(row)
    return out


def _agg_bets(rows):
    settled = [b for b in rows if b.get('result') in ('win', 'loss')]
    wins = sum(1 for b in settled if b['result'] == 'win')
    stake = sum(b.get('stake') or 0 for b in settled)
    profit = sum(b.get('profit') or 0 for b in settled)
    clvs = [b['clv'] for b in rows if b.get('clv') is not None]
    real_rows = [b for b in settled if b.get('real_odds')]
    real_stake = sum(b.get('stake') or 0 for b in real_rows)
    real_profit = sum((b.get('stake') or 0) * (b['real_odds'] - 1) if b['result'] == 'win' else -(b.get('stake') or 0)
                      for b in real_rows)
    return {
        'real': {'n': len(real_rows), 'profit': round(real_profit, 2),
                 'model_profit': round(sum(b.get('profit') or 0 for b in real_rows), 2),
                 'roi': round(real_profit / real_stake * 100, 1) if real_stake else None},
        'n': len(rows), 'settled': len(settled), 'wins': wins, 'losses': len(settled) - wins,
        'winrate': round(wins / len(settled) * 100, 1) if settled else None,
        'profit': round(profit, 2),
        'roi': round(profit / stake * 100, 1) if stake else None,
        'clv_n': len(clvs),
        'avg_clv': round(sum(clvs) / len(clvs), 2) if clvs else None,
        'clv_pos': round(sum(1 for c in clvs if c > 0) / len(clvs) * 100, 1) if clvs else None,
    }


def _flag_weak(a):
    """Лига «слабая»: не меньше 30 рассчитанных ставок и отрицательный средний CLV."""
    a['weak'] = bool(a['settled'] >= 30 and a['avg_clv'] is not None and a['avg_clv'] < 0)
    return a


@app.route('/api/lm_analytics', methods=['GET'])
def api_lm_analytics():
    try:
        rows = _lm_bets_with_clv()
        by_league = {}
        for b in rows:
            by_league.setdefault(b.get('league') or '?', []).append(b)
        buckets = [('до 3%', 0, 3), ('3–5%', 3, 5), ('5–8%', 5, 8), ('8–12%', 8, 12), ('12%+', 12, 10 ** 6)]
        by_move = []
        for name, lo, hi in buckets:
            sub = [b for b in rows if b.get('move') is not None and lo <= abs(b['move']) < hi]
            by_move.append(dict(_agg_bets(sub), bucket=name))
        return jsonify({
            'status': 'ok',
            'overall': _agg_bets(rows),
            'streaks': _streaks(rows),
            'by_league': sorted([_flag_weak(dict(_agg_bets(v), league=k)) for k, v in by_league.items()],
                                key=lambda x: -x['n']),
            'by_move': by_move,
        })
    except Exception as e:
        logger.exception(f"api_lm_analytics error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ ЭКСПОРТ ИСТОРИИ В CSV
# ============================================================
@app.route('/api/export_history.csv', methods=['GET'])
def api_export_history_csv():
    try:
        import csv, io
        from flask import Response as _Resp
        try:
            by_fid = {r.get('fixture_id'): r for r in _lm_bets_with_clv() if r.get('fixture_id')}
        except Exception:
            by_fid = {}
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow(['Дата', 'Время матча', 'Лига', 'Хозяева', 'Гости', 'Ставка', 'Кэф', 'Сумма',
                    'Результат', 'Прибыль', 'Голы дома', 'Голы гости', '1-й тайм', 'Движение %', 'CLV %', 'Источник'])
        for b in storage.load_history():
            e = by_fid.get(b.get('fixture_id'), {})
            ht = (f"{b.get('halftime_home')}-{b.get('halftime_away')}"
                  if b.get('halftime_home') is not None else '')
            w.writerow([b.get('date', ''), b.get('match_time', ''), b.get('league', ''), b.get('home', ''),
                        b.get('away', ''), b.get('bet', ''), b.get('odds', ''), b.get('stake', ''),
                        b.get('result', ''), b.get('profit', ''), b.get('home_goals', ''), b.get('away_goals', ''),
                        ht, e.get('move', ''), e.get('clv', ''), b.get('source', '')])
        data = '﻿' + buf.getvalue()
        return _Resp(data, mimetype='text/csv; charset=utf-8',
                     headers={'Content-Disposition': 'attachment; filename=history.csv'})
    except Exception as e:
        logger.exception(f"export csv error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ СОСТОЯНИЕ БОТА
# ============================================================
@app.route('/api/bot_health', methods=['GET'])
def api_bot_health():
    try:
        now = datetime.now()
        interval = int(getattr(Config, 'LINE_MOVEMENT_SNAPSHOT_INTERVAL_MIN', 30))
        rows = storage.get_snapshots_since((now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'))
        rows = [r for r in rows if is_lm_item(r)]
        last = max((r.get('created_at') or '' for r in rows), default='')
        today0 = now.strftime('%Y-%m-%d')
        today_rows = [r for r in rows if str(r.get('created_at', '')).startswith(today0)]
        minutes_ago = None
        if last:
            try:
                minutes_ago = int((now - datetime.strptime(last[:19], '%Y-%m-%d %H:%M:%S')).total_seconds() // 60)
            except Exception:
                pass
        disk_ok = os.path.abspath(DATA_DIR) != os.path.abspath('.')
        quota = getattr(football_api, 'quota', None) or {}
        warnings = []
        if minutes_ago is None:
            warnings.append('Снимков за сутки нет')
        elif minutes_ago > interval * 2 + 10:
            warnings.append(f'Снимки не делались {minutes_ago} мин (интервал {interval} мин)')
        if not disk_ok:
            warnings.append('Диск Render не подключён: снимки пропадут при перезапуске')
        try:
            if quota.get('remaining') is not None and int(quota['remaining']) < 100:
                warnings.append(f"Лимит API-Football почти исчерпан: осталось {quota['remaining']}")
        except Exception:
            pass
        if not getattr(football_api, 'api_key', None):
            warnings.append('FOOTBALL_API_KEY не задан')
        return jsonify({
            'status': 'ok', 'ok': not warnings, 'warnings': warnings,
            'last_snapshot': last, 'minutes_ago': minutes_ago, 'interval_min': interval,
            'snapshots_today': len(today_rows),
            'fixtures_today': len({r.get('fixture_id') for r in today_rows}),
            'leagues': len(_lm_league_ids()),
            'disk_ok': disk_ok, 'quota': quota,
        })
    except Exception as e:
        logger.exception(f"api_bot_health error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ ЗАМЕТКИ К СТАВКАМ (хранятся на сервере)
# ============================================================
_NOTES_FILE = os.path.join(DATA_DIR, 'bet_notes.json')
_notes_lock = Lock()


def _load_notes():
    try:
        with open(_NOTES_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


@app.route('/api/notes', methods=['GET'])
def api_notes_get():
    return jsonify({'status': 'ok', 'notes': _load_notes()})


@app.route('/api/notes', methods=['POST'])
def api_notes_set():
    try:
        body = request.get_json(silent=True) or {}
        key = str(body.get('key', '')).strip()[:200]
        note = str(body.get('note', '')).strip()[:500]
        if not key:
            return jsonify({'status': 'error', 'error': 'key required'}), 400
        with _notes_lock:
            notes = _load_notes()
            if note:
                notes[key] = note
            else:
                notes.pop(key, None)
            with open(_NOTES_FILE, 'w', encoding='utf-8') as f:
                json.dump(notes, f, ensure_ascii=False)
        return jsonify({'status': 'ok', 'saved': bool(note)})
    except Exception as e:
        logger.exception(f"api_notes_set error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/snapshots/<int:fixture_id>', methods=['GET'])
def api_snapshots_detail(fixture_id):
    try:
        rows = storage.get_snapshots_by_fixture(fixture_id)
        if not rows:
            return jsonify({
                'status': 'ok', 'fixture_id': fixture_id,
                'bet': None, 'history': [],
            })

        m_info = storage.get_snapshot_match_info(fixture_id) or {}
        match_time = '?'
        bet_info = None
        try:
            cache = storage.load_cache()
            all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
            for m in all_matches:
                if m.get('fixture_id') != fixture_id:
                    continue
                match_time = m.get('match_time', '?')

                bb = m.get('best_bet') or {}
                if bb.get('label') and bb.get('odds', 0) > 1.01:
                    minutes_to_match = None
                    if match_time and match_time != '?':
                        try:
                            match_dt = datetime.strptime(match_time, "%d.%m.%Y %H:%M")
                            now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
                            minutes_to_match = int((match_dt - now_msk).total_seconds() / 60)
                        except Exception:
                            pass

                    if minutes_to_match is not None and -120 <= minutes_to_match <= 30:
                        bet_info = {
                            'label': bb.get('label'),
                            'odds': bb.get('odds'),
                            'ev': bb.get('ev', 0),
                            'prob': bb.get('prob', 0),
                            'stake': bb.get('stake', 0),
                            'source': m.get('source', '70_percent'),
                            'bookmaker': bb.get('bookmaker', '—'),
                            'movement_pct': bb.get('movement_pct'),
                            'movement_hours': bb.get('movement_hours'),
                            'old_odds': bb.get('old_odds'),
                            'snapshots_count': bb.get('snapshots_count'),
                            'llm_reason': bb.get('llm_reason', ''),
                            'minutes_to_match': minutes_to_match,
                        }
                break
        except Exception as e:
            logger.error(f"snapshot bet lookup error: {e}")

        history_map = {}
        for r in rows:
            t = r.get('created_at')
            sel = r.get('selection', '')
            odd = r.get('odds', 0)
            bm = r.get('bookmaker', '—')
            if not t: continue
            if t not in history_map:
                history_map[t] = {
                    'created_at': t,
                    'odds': {'1': 0, 'X': 0, '2': 0, '1X': 0, 'X2': 0},
                    'bookmaker': bm,
                }
            if sel in history_map[t]['odds']:
                history_map[t]['odds'][sel] = odd
            history_map[t]['bookmaker'] = bm

        history = sorted(history_map.values(), key=lambda x: x['created_at'])
        return jsonify({
            'status': 'ok',
            'fixture_id': fixture_id,
            'match': {
                'home': m_info.get('home', '?'),
                'away': m_info.get('away', '?'),
                'league': m_info.get('league', '?'),
                'match_time': match_time,
            },
            'bet': bet_info,
            'history': history,
        })
    except Exception as e:
        logger.exception(f"api_snapshots_detail error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ API: АНОМАЛИИ
# ============================================================
@app.route('/api/snapshot_anomalies', methods=['GET'])
def api_snapshot_anomalies():
    try:
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        matches_raw = _lm_snapshots_since(cutoff)

        grouped = {}
        for row in matches_raw:
            fid = row.get('fixture_id')
            if not fid: continue
            if fid not in grouped:
                grouped[fid] = {
                    'snapshots': [],
                    'home': row.get('home', '') or '?',
                    'away': row.get('away', '') or '?',
                    'league': row.get('league', '') or '?',
                }
            grouped[fid]['snapshots'].append(row)
            if row.get('home') and grouped[fid]['home'] == '?':
                grouped[fid]['home'] = row['home']
            if row.get('away') and grouped[fid]['away'] == '?':
                grouped[fid]['away'] = row['away']
            if row.get('league') and grouped[fid]['league'] == '?':
                grouped[fid]['league'] = row['league']

        match_time_lookup = {}
        try:
            cache = storage.load_cache()
            all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
            for m in all_matches:
                fid = m.get('fixture_id')
                if fid and fid not in match_time_lookup:
                    match_time_lookup[fid] = m.get('match_time', '?')
        except Exception:
            pass

        result = []
        for fid, info in grouped.items():
            snaps = info['snapshots']
            odds_by_time = {}
            for s in snaps:
                t = s.get('created_at')
                sel = s.get('selection')
                odd = s.get('odds', 0)
                if not t or sel not in ['1', 'X', '2']: continue
                odds_by_time.setdefault(t, {'1': 0, 'X': 0, '2': 0})[sel] = odd

            sorted_times = sorted(odds_by_time.keys())
            for sel in ['1', 'X', '2']:
                values = [odds_by_time[t][sel] for t in sorted_times if odds_by_time[t][sel] > 0]
                if len(values) < 2: continue
                first_odd = values[0]
                max_odd = max(values)
                anomaly_pct = ((max_odd / first_odd) - 1) * 100 if first_odd > 0 else 0
                if anomaly_pct > 5:
                    result.append({
                        'fixture_id': fid,
                        'home': info['home'],
                        'away': info['away'],
                        'league': info['league'],
                        'match_time': match_time_lookup.get(fid, '?'),
                        'selection': sel,
                        'first_odds': first_odd,
                        'max_odds': max_odd,
                        'anomaly_pct': round(anomaly_pct, 1),
                        'snapshots_count': len(values),
                    })
        result.sort(key=lambda x: x['anomaly_pct'], reverse=True)
        result = result[:limit]
        return jsonify({'status': 'ok', 'count': len(result), 'anomalies': result})
    except Exception as e:
        logger.exception(f"api_snapshot_anomalies error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/snapshot_anomalies/stats', methods=['GET'])
def api_snapshot_anomalies_stats():
    try:
        days = int(request.args.get('days', 7))
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        matches_raw = _lm_snapshots_since(cutoff)

        grouped = {}
        for row in matches_raw:
            fid = row.get('fixture_id')
            if not fid: continue
            if fid not in grouped:
                grouped[fid] = {
                    'snapshots': [],
                    'home': row.get('home', '') or '?',
                    'away': row.get('away', '') or '?',
                    'league': row.get('league', '') or '?',
                }
            grouped[fid]['snapshots'].append(row)
            if row.get('home') and grouped[fid]['home'] == '?':
                grouped[fid]['home'] = row['home']
            if row.get('away') and grouped[fid]['away'] == '?':
                grouped[fid]['away'] = row['away']
            if row.get('league') and grouped[fid]['league'] == '?':
                grouped[fid]['league'] = row['league']

        history = storage.load_history()
        results_lookup = {}
        for h in history:
            fid = h.get('fixture_id')
            if fid:
                results_lookup[fid] = {
                    'result': h.get('result'),
                    'home_goals': h.get('home_goals'),
                    'away_goals': h.get('away_goals'),
                }

        total_matches = len(grouped)
        total_snapshots = len(matches_raw)
        total_anomalies = 0
        correct_anomalies = 0
        wrong_anomalies = 0
        unknown_anomalies = 0
        sum_growth = 0

        top_good = []
        top_bad = []

        for fid, info in grouped.items():
            snaps = info['snapshots']
            odds_by_time = {}
            for s in snaps:
                t = s.get('created_at')
                sel = s.get('selection')
                odd = s.get('odds', 0)
                if not t or sel not in ['1', 'X', '2']:
                    continue
                odds_by_time.setdefault(t, {'1': 0, 'X': 0, '2': 0})[sel] = odd

            sorted_times = sorted(odds_by_time.keys())

            for sel in ['1', 'X', '2']:
                values = [odds_by_time[t][sel] for t in sorted_times if odds_by_time[t][sel] > 0]
                if len(values) < 2:
                    continue
                first_odd = values[0]
                max_odd = max(values)
                anomaly_pct = ((max_odd / first_odd) - 1) * 100 if first_odd > 0 else 0

                if anomaly_pct < 5:
                    continue

                total_anomalies += 1
                sum_growth += anomaly_pct

                match_res = results_lookup.get(fid)
                is_correct = None
                if match_res and match_res.get('result') in ('win', 'loss'):
                    hg = match_res.get('home_goals')
                    ag = match_res.get('away_goals')
                    if hg is not None and ag is not None:
                        if sel == '1':
                            is_correct = hg > ag
                        elif sel == '2':
                            is_correct = ag > hg
                        elif sel == 'X':
                            is_correct = hg == ag

                if is_correct is True:
                    correct_anomalies += 1
                    top_good.append({
                        'fixture_id': fid, 'selection': sel,
                        'first_odds': first_odd, 'max_odds': max_odd,
                        'anomaly_pct': round(anomaly_pct, 1),
                        'home': info['home'], 'away': info['away'],
                        'league': info['league'],
                    })
                elif is_correct is False:
                    wrong_anomalies += 1
                    top_bad.append({
                        'fixture_id': fid, 'selection': sel,
                        'first_odds': first_odd, 'max_odds': max_odd,
                        'anomaly_pct': round(anomaly_pct, 1),
                        'home': info['home'], 'away': info['away'],
                        'league': info['league'],
                    })
                else:
                    unknown_anomalies += 1

        top_good_sorted = sorted(top_good, key=lambda x: x['anomaly_pct'], reverse=True)[:5]
        top_bad_sorted = sorted(top_bad, key=lambda x: x['anomaly_pct'])[:5]

        total_resolved = correct_anomalies + wrong_anomalies
        hit_rate = round(correct_anomalies / total_resolved * 100, 1) if total_resolved > 0 else 0
        avg_growth = round(sum_growth / total_anomalies, 1) if total_anomalies > 0 else 0

        return jsonify({
            'status': 'ok',
            'days': days,
            'total_matches': total_matches,
            'total_snapshots': total_snapshots,
            'total_anomalies': total_anomalies,
            'correct_anomalies': correct_anomalies,
            'wrong_anomalies': wrong_anomalies,
            'unknown_anomalies': unknown_anomalies,
            'hit_rate': hit_rate,
            'avg_growth': avg_growth,
            'top_good': top_good_sorted,
            'top_bad': top_bad_sorted,
        })
    except Exception as e:
        logger.exception(f"api_snapshot_anomalies_stats error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: РЕДАКТИРОВАНИЕ СТАВОК
# ============================================================
@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        if index is None or index >= len(history):
            return jsonify({'error': 'Не найдено'}), 404
        for field in ['home', 'away', 'bet', 'odds', 'stake', 'ev', 'prob',
                      'result', 'bookmaker', 'halftime_home', 'halftime_away',
                      'home_goals', 'away_goals', 'date', 'league', 'source']:
            if field in data:
                history[index][field] = data[field]
        if history[index].get('result') == 'win':
            history[index]['profit'] = round(history[index].get('stake', 0) * (history[index].get('odds', 1) - 1), 2)
        elif history[index].get('result') == 'loss':
            history[index]['profit'] = -history[index].get('stake', 0)
        else:
            history[index]['profit'] = 0
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        if index is None or index >= len(history):
            return jsonify({'error': 'Не найдено'}), 404
        history.pop(index)
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        match_name = data.get('match', '')
        score = data.get('score', '-')
        result = data.get('result', 'win')
        stake = float(data.get('stake', 0))
        bet_type = data.get('bet', '')
        odds = float(data.get('odds', 1.85))
        bookmaker = data.get('bookmaker', 'Ручное добавление')
        if not match_name:
            return jsonify({'error': 'Название обязательно'}), 400
        hg = ag = None
        if score and '-' in score:
            p = score.split('-')
            try:
                hg = int(p[0].strip()); ag = int(p[1].strip())
            except Exception:
                pass
        home = away = 'Unknown'
        if ' vs ' in match_name:
            p = match_name.split(' vs ')
            home, away = p[0].strip(), p[1].strip()
        elif ' - ' in match_name:
            p = match_name.split(' - ')
            home, away = p[0].strip(), p[1].strip()
        if result == 'win': profit = round(stake * (odds - 1), 2)
        elif result == 'loss': profit = -stake
        else: profit = 0
        history = storage.load_history()
        history.append({
            'home': home or 'Unknown',
            'away': away or 'Unknown',
            'league': 'Ручное добавление',
            'bet': bet_type, 'odds': odds, 'stake': stake,
            'ev': 0, 'prob': 0, 'result': result, 'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': hg, 'away_goals': ag,
            'manual': True, 'bookmaker': bookmaker,
            'source': 'manual',
        })
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True, 'count': 1})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    try:
        data = request.json
        os.makedirs(os.path.dirname(SETTINGS_PATH) or '.', exist_ok=True)
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        for key in ['EV_MIN_70', 'PROB_MIN_70', 'XG_MIN_70', 'XG_MAX_70',
                    'POSITION_MAX_70', 'PREMIUM_MIN_EV', 'STANDARD_MIN_EV',
                    'TM25_XG_MIN', 'TM25_XG_MAX', 'MAX_TM25_BETS',
                    'VALUE_MIN_ODDS', 'VALUE_MIN_EV', 'VALUE_MIN_PROB',
                    'VALUE_MIN_XG_DIFF', 'VALUE_MAX_RESULTS',
                    'X2_MIN_EV', 'X2_MIN_PROB',
                    'LIVE_HOURS_BEFORE', 'LIVE_MINUTES_AFTER',
                    'LIVE_REFRESH_SEC', 'LIVE_MAX_MATCHES',
                    'LIVE_SPARKLINE_ENABLED', 'LIVE_SPARKLINE_POINTS']:
            if key.lower() in data:
                setattr(Config, key, data[key.lower()])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        history = data.get('history', [])
        stats = data.get('stats', {})
        if not history:
            return jsonify({'error': 'Нет данных'}), 400
        current = storage.load_history()
        keys = {f"{b.get('date', '')}_{b.get('home', '')}_{b.get('away', '')}" for b in current}
        imported = 0
        for bet in history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            if key not in keys:
                current.append(bet); imported += 1; keys.add(key)
        if stats and 'bank' in stats:
            storage.save_bank(stats['bank'])
        storage.save_history(current)
        recalc_stats()
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/void_old', methods=['POST'])
def void_old_endpoint():
    bets = storage.autobet_load_all()
    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    voided = 0
    for b in bets:
        if b.get('result') != 'pending': continue
        mt = b.get('match_time', '')
        if not mt or mt == '?': continue
        try:
            m = datetime.strptime(mt, '%d.%m.%Y %H:%M')
            hours = (now_msk - m).total_seconds() / 3600
            if hours > 6:
                b['result'] = 'void'
                b['profit'] = 0
                b['note'] = 'Voided (stale)'
                for k in ['live_score', 'live_status', 'live_minute', 'live_halftime']:
                    b.pop(k, None)
                voided += 1
        except Exception:
            pass
    storage.autobet_save_all(bets)
    return jsonify({'status': 'ok', 'voided': voided})
