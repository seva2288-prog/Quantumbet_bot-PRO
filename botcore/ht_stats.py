# -*- coding: utf-8 -*-
# botcore/ht_stats.py — статистика «как заканчиваются матчи при счёте первого тайма X»
# Данные: завершённые матчи лиг Line Movement за 2 сезона (API-Football, ~12 запросов), кэш в DATA_DIR.
import os
import json
import time
from threading import Thread, Lock
from flask import request, jsonify
from app.config import Config

from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403

__all__ = ['api_ht_stats', 'api_ht_stats_refresh']

_HT_FILE = os.path.join(DATA_DIR, 'ht_matches.json')
_ht_lock = Lock()
_ht_state = {'running': False, 'done': 0, 'total': 0, 'error': None}


def _ht_load():
    try:
        with open(_HT_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {'updated': None, 'rows': []}


def _ht_fetch_job():
    try:
        leagues = _lm_league_ids()
        cur = int(Config.USE_SEASON)
        jobs = [(l, s) for l in leagues for s in (cur, cur - 1)]
        _ht_state.update(running=True, done=0, total=len(jobs), error=None)
        rows = []
        for lid, season in jobs:
            data = football_api._make_request('/fixtures', {'league': lid, 'season': season, 'status': 'FT'})
            for f in (data or {}).get('response', []):
                sc = f.get('score') or {}
                ht, ft = sc.get('halftime') or {}, sc.get('fulltime') or {}
                if None in (ht.get('home'), ht.get('away'), ft.get('home'), ft.get('away')):
                    continue
                rows.append([lid, season, ht['home'], ht['away'], ft['home'], ft['away']])
            _ht_state['done'] += 1
        with _ht_lock:
            with open(_HT_FILE, 'w', encoding='utf-8') as fh:
                json.dump({'updated': time.strftime('%Y-%m-%d %H:%M'), 'rows': rows}, fh)
    except Exception as e:
        logger.exception(f"ht_fetch error: {e}")
        _ht_state['error'] = str(e)
    finally:
        _ht_state['running'] = False


def _pct(a, n):
    return round(100.0 * a / n, 1) if n else 0.0


def _ht_summary(rows):
    n = len(rows)
    sec = [(r[4] - r[2], r[5] - r[3]) for r in rows]          # голы во 2-м тайме (дом, гость)
    tot2 = [a + b for a, b in sec]
    return {
        'n': n,
        'g0': _pct(sum(1 for t in tot2 if t == 0), n),        # во 2-м тайме без голов (счёт остался)
        'g1': _pct(sum(1 for t in tot2 if t == 1), n),
        'g2p': _pct(sum(1 for t in tot2 if t >= 2), n),
        'same2h': _pct(sum(1 for r, s in zip(rows, sec) if s == (r[2], r[3])), n),  # 2-й тайм сыгран тем же счётом
        'home': _pct(sum(1 for r in rows if r[4] > r[5]), n),
        'draw': _pct(sum(1 for r in rows if r[4] == r[5]), n),
        'away': _pct(sum(1 for r in rows if r[4] < r[5]), n),
        'btts': _pct(sum(1 for r in rows if r[4] > 0 and r[5] > 0), n),
        'avg2h': round(sum(tot2) / n, 2) if n else 0,
    }


@app.route('/api/ht_stats', methods=['GET'])
def api_ht_stats():
    try:
        d = _ht_load()
        rows = d.get('rows') or []
        ht = (request.args.get('ht') or '').strip()      # например '0-0'
        names = Config.LEAGUE_NAMES if hasattr(Config, 'LEAGUE_NAMES') else {}
        groups = {}
        for r in rows:
            groups.setdefault('%d-%d' % (r[2], r[3]), []).append(r)
        table = []
        for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:10]:
            s = _ht_summary(v); s['ht'] = k; table.append(s)
        detail = None
        if ht in groups:
            by_l = {}
            for r in groups[ht]:
                by_l.setdefault(r[0], []).append(r)
            detail = {'ht': ht, 'overall': _ht_summary(groups[ht]),
                      'leagues': [dict(_ht_summary(v), league=names.get(l, str(l)))
                                  for l, v in sorted(by_l.items(), key=lambda kv: -len(kv[1]))]}
        return jsonify({'status': 'ok', 'updated': d.get('updated'), 'total': len(rows),
                        'overall': _ht_summary(rows), 'table': table, 'detail': detail,
                        'job': dict(_ht_state)})
    except Exception as e:
        logger.exception(f"api_ht_stats error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/ht_stats/refresh', methods=['POST'])
def api_ht_stats_refresh():
    if _ht_state['running']:
        return jsonify({'status': 'ok', 'job': dict(_ht_state)})
    Thread(target=_ht_fetch_job, daemon=True).start()
    return jsonify({'status': 'ok', 'started': True})
