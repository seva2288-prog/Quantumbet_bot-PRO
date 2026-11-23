# -*- coding: utf-8 -*-
# botcore/ht_stats.py — статистика «как заканчиваются матчи при счёте первого тайма X»
# Данные: завершённые матчи лиг Line Movement за 2 сезона (API-Football, ~12 запросов), кэш в DATA_DIR.
import os
import json
import time
from datetime import datetime
from threading import Thread, Lock
from flask import request, jsonify

from app.config import Config

from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403

__all__ = ['api_ht_stats', 'api_ht_stats_refresh', 'ht_odds_job', 'api_ht_live']

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
        jobs = [(l, s) for l in leagues for s in range(cur, cur - 5, -1)]   # 5 сезонов
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


# ============================================================
# Live-кэфы в перерыве: бот сохраняет кэфы на матчи ваших лиг, когда статус HT,
# потом дописывает итоговый счёт. Сравнение с реальной частотой исходов -> видно, есть ли перевес.
# ============================================================
_HTO_FILE = os.path.join(DATA_DIR, 'ht_live_odds.json')
_hto_lock = Lock()
_HT_POLL_UTC_FROM, _HT_POLL_UTC_TO = 10, 22   # часы по UTC, когда опрашиваем live (вне окна матчей нет)
_BAD_WORDS = ('half', 'first', 'second', 'corner', 'card', 'player', 'handicap', 'exact', 'odd/even', 'home team', 'away team', 'result/')


def _hto_load():
    try:
        with open(_HTO_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _hto_save(d):
    with _hto_lock:
        with open(_HTO_FILE, 'w', encoding='utf-8') as fh:
            json.dump(d, fh)


def _to_f(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except Exception:
        return None


def _parse_live_odds(resp):
    """Из ответа /odds/live: 1X2, тотал матча, обе забьют. Возвращает (odds, названия рынков)."""
    out = {'1x2': {}, 'ou': {}, 'btts': {}}
    names = []
    for item in (resp or {}).get('response', []):
        books = item.get('odds')
        bets = books if isinstance(books, list) else []
        if not bets:
            for bk in item.get('bookmakers', []) or []:
                bets += bk.get('bets', []) or []
        for b in bets:
            nm = str(b.get('name') or '').strip()
            low = nm.lower()
            names.append(nm)
            if any(w in low for w in _BAD_WORDS):
                continue
            vals = b.get('values') or []
            if low in ('fulltime result', 'match winner', '1x2', 'full time result'):
                for v in vals:
                    key = {'home': '1', 'draw': 'X', 'away': '2'}.get(str(v.get('value')).strip().lower())
                    o = _to_f(v.get('odd'))
                    if key and o and not v.get('suspended'):
                        out['1x2'][key] = o
            elif low.startswith('over/under') or low in ('match goals', 'goals over/under'):
                for v in vals:
                    txt = str(v.get('value') or '').strip().lower()
                    line = v.get('handicap')
                    side = 'over' if txt.startswith('over') else 'under' if txt.startswith('under') else None
                    if side and line in (None, ''):
                        try:
                            line = txt.split()[-1]
                        except Exception:
                            line = None
                    o = _to_f(v.get('odd'))
                    if side and line not in (None, '') and o and not v.get('suspended'):
                        try:
                            ln = '%.1f' % float(line)
                        except Exception:
                            continue
                        out['ou'].setdefault(ln, {})[side] = o
            elif low in ('both teams to score', 'both teams score'):
                for v in vals:
                    key = str(v.get('value')).strip().lower()
                    o = _to_f(v.get('odd'))
                    if key in ('yes', 'no') and o and not v.get('suspended'):
                        out['btts'][key] = o
    return out, sorted(set(names))[:25]


def ht_odds_job():
    """Каждые 5 минут в окне матчей: находит матчи лиг LM на перерыве и сохраняет live-кэфы; дописывает итоговые счета."""
    try:
        hr = datetime.utcnow().hour
        data = _hto_load()
        changed = False
        # 1) дописываем итог для сохранённых матчей без финала (одним запросом до 20 id)
        pend = [fid for fid, r in data.items() if r.get('ft') is None][:20]
        if pend:
            b = football_api._make_request('/fixtures', {'ids': '-'.join(pend)})
            for f in (b or {}).get('response', []):
                fid = str((f.get('fixture') or {}).get('id'))
                st = ((f.get('fixture') or {}).get('status') or {}).get('short')
                g = f.get('goals') or {}
                if fid in data and st in ('FT', 'AET', 'PEN') and g.get('home') is not None:
                    data[fid]['ft'] = [g['home'], g['away']]
                    changed = True
        # 2) ищем матчи на перерыве
        if _HT_POLL_UTC_FROM <= hr < _HT_POLL_UTC_TO:
            ids = '-'.join(str(x) for x in _lm_league_ids())
            live = football_api._make_request('/fixtures', {'live': ids})
            for f in (live or {}).get('response', []):
                fx = f.get('fixture') or {}
                fid = str(fx.get('id'))
                if (fx.get('status') or {}).get('short') != 'HT' or fid in data:
                    continue
                g = f.get('goals') or {}
                if g.get('home') is None:
                    continue
                od = football_api._make_request('/odds/live', {'fixture': fid})
                odds, names = _parse_live_odds(od)
                data[fid] = {
                    'league': (f.get('league') or {}).get('id'),
                    'home': (f.get('teams') or {}).get('home', {}).get('name'),
                    'away': (f.get('teams') or {}).get('away', {}).get('name'),
                    'ht': [g['home'], g['away']], 'ft': None,
                    'odds': odds, 'markets': names,
                    'ts': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                }
                changed = True
                logger.info(f"⏱ HT odds saved: {fid} {data[fid]['home']} {g['home']}-{g['away']}")
        if changed:
            _hto_save(data)
    except Exception as e:
        logger.exception(f"ht_odds_job error: {e}")


def _sel_hit(sel, ft):
    h, a = ft
    kind, arg = sel
    if kind == '1x2':
        return {'1': h > a, 'X': h == a, '2': a > h}[arg]
    if kind == 'btts':
        return (h > 0 and a > 0) if arg == 'yes' else not (h > 0 and a > 0)
    side, ln = arg
    tot = h + a
    return tot > float(ln) if side == 'over' else tot < float(ln)


@app.route('/api/ht_live', methods=['GET'])
def api_ht_live():
    """Live-кэфы в перерыве против реальных исходов. ?ht=0-0 (пусто = все счета)."""
    try:
        want = (request.args.get('ht') or '').strip()
        data = _hto_load()
        recs = [r for r in data.values() if r.get('ft') is not None and (not want or '%d-%d' % tuple(r['ht']) == want)]
        agg = {}
        for r in recs:
            o = r.get('odds') or {}
            sels = []
            for k, v in (o.get('1x2') or {}).items():
                sels.append((('1x2', k), v))
            for k, v in (o.get('btts') or {}).items():
                sels.append((('btts', k), v))
            for ln, sd in (o.get('ou') or {}).items():
                for side, v in sd.items():
                    sels.append((('ou', (side, ln)), v))
            for sel, odd in sels:
                try:
                    hit = _sel_hit(sel, r['ft'])
                except Exception:
                    continue
                if sel[0] == '1x2':
                    name = {'1': 'П1', 'X': 'Ничья', '2': 'П2'}.get(sel[1], sel[1])
                elif sel[0] == 'btts':
                    name = 'Обе забьют: ' + ('да' if sel[1] == 'yes' else 'нет')
                else:
                    name = ('Тотал больше ' if sel[1][0] == 'over' else 'Тотал меньше ') + sel[1][1]
                a = agg.setdefault(name, {'n': 0, 'hits': 0, 'sum_odds': 0.0, 'profit': 0.0})
                a['n'] += 1; a['sum_odds'] += odd
                if hit:
                    a['hits'] += 1; a['profit'] += odd - 1
                else:
                    a['profit'] -= 1
        rows = []
        for name, a in agg.items():
            n = a['n']
            avg = a['sum_odds'] / n
            rows.append({'sel': name, 'n': n, 'avg_odds': round(avg, 2), 'hit': round(100.0 * a['hits'] / n, 1),
                         'implied': round(100.0 / avg, 1), 'roi': round(100.0 * a['profit'] / n, 1)})
        rows.sort(key=lambda x: -x['n'])
        markets = sorted({m for r in data.values() for m in (r.get('markets') or [])})
        return jsonify({'status': 'ok', 'saved': len(data), 'finished': len([r for r in data.values() if r.get('ft') is not None]),
                        'matching': len(recs), 'rows': rows[:30], 'markets_seen': markets[:25]})
    except Exception as e:
        logger.exception(f"api_ht_live error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
