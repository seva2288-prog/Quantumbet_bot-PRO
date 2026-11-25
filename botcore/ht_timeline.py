# -*- coding: utf-8 -*-
# botcore/ht_timeline.py — сбор данных первых таймов (до 40-й минуты) и поиск закономерностей «гол после 40-й»
# Бот каждые 3 минуты (окно 10-22 UTC) смотрит матчи ваших лиг в 1-м тайме (8-44 мин) и каждые ~4 минуты
# сохраняет счёт, live-кэфы (в т.ч. тоталы 1-го тайма) и, после 30-й минуты, статистику ударов.
# После перерыва один запрос событий даёт минуты голов 1-го тайма.
import os
import json
from datetime import datetime
from threading import Lock
from flask import request, jsonify

from app.config import Config

from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403
from botcore.ht_stats import _parse_live_odds, _pre_odds_map, _fav_side  # noqa: F401

__all__ = ['ht_timeline_job', 'api_late_goal']

_TL_FILE = os.path.join(DATA_DIR, 'ht_timeline.json')
_tl_lock = Lock()
_CP_MIN, _CP_MAX, _CP_GAP = 8, 44, 4     # минуты, между которыми собираем «контрольные точки», и шаг


def _tl_load():
    try:
        with open(_TL_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _tl_save(d):
    with _tl_lock:
        with open(_TL_FILE, 'w', encoding='utf-8') as fh:
            json.dump(d, fh)


def _num(v):
    try:
        return int(str(v).replace('%', '').strip())
    except Exception:
        return 0


def _parse_stats(resp, home_id):
    """Удары/в створ/угловые/владение: {'sot':[h,a], 'shots':[h,a], 'corners':[h,a], 'poss':[h,a]}."""
    out = {}
    keymap = {'Shots on Goal': 'sot', 'Total Shots': 'shots', 'Corner Kicks': 'corners', 'Ball Possession': 'poss'}
    for t in (resp or {}).get('response', []):
        idx = 0 if (t.get('team') or {}).get('id') == home_id else 1
        for st in t.get('statistics', []) or []:
            k = keymap.get(st.get('type'))
            if k:
                out.setdefault(k, [0, 0])[idx] = _num(st.get('value'))
    return out


def ht_timeline_job():
    try:
        hr = datetime.utcnow().hour
        if not (10 <= hr < 22):
            return
        ids = '-'.join(str(x) for x in _lm_league_ids())
        live = football_api._make_request('/fixtures', {'live': ids})
        resp = (live or {}).get('response', [])
        if not resp:
            return
        data = _tl_load()
        changed = False
        for f in resp:
            fx = f.get('fixture') or {}
            fid = str(fx.get('id'))
            st = fx.get('status') or {}
            short, el = st.get('short'), st.get('elapsed')
            g = f.get('goals') or {}
            if g.get('home') is None or el is None:
                continue
            teams = f.get('teams') or {}
            rec = data.get(fid)
            if short == '1H' and _CP_MIN <= el <= _CP_MAX:
                if rec is None:
                    rec = data[fid] = {'league': (f.get('league') or {}).get('id'),
                                       'home': (teams.get('home') or {}).get('name'),
                                       'away': (teams.get('away') or {}).get('name'),
                                       'home_id': (teams.get('home') or {}).get('id'),
                                       'pre': (_pre_odds_map([fid]).get(fid) or None),
                                       'cps': [], 'g1h': None,
                                       'date': datetime.utcnow().strftime('%Y-%m-%d')}
                last = rec['cps'][-1]['min'] if rec['cps'] else -99
                need40 = 38 <= el <= 41 and not any(c.get('k40') for c in rec['cps'])   # обязательная точка «кэф на 40-й»
                if el - last >= _CP_GAP or need40:
                    odds, _names = _parse_live_odds(football_api._make_request('/odds/live', {'fixture': fid}))
                    cp = {'min': el, 'score': [g['home'], g['away']], 'odds': odds}
                    if need40:
                        cp['k40'] = True
                    if el >= 30:
                        cp['stats'] = _parse_stats(football_api._make_request('/fixtures/statistics', {'fixture': fid}),
                                                   rec.get('home_id'))
                    rec['cps'].append(cp)
                    changed = True
            elif rec is not None and rec.get('g1h') is None and (short == 'HT' or (short == '2H' and el <= 55)):
                ev = football_api._make_request('/fixtures/events', {'fixture': fid})
                mins = []
                for e in (ev or {}).get('response', []):
                    if e.get('type') == 'Goal' and 'Missed' not in str(e.get('detail')):
                        m = (e.get('time') or {}).get('elapsed')
                        if m is not None and m <= 45:
                            mins.append(int(m))
                rec['g1h'] = sorted(mins)
                changed = True
                logger.info(f"⏱ timeline: {rec['home']} 1T голы {rec['g1h']}")
        if changed:
            _tl_save(data)
    except Exception as e:
        logger.exception(f"ht_timeline_job error: {e}")


def _pc(a, n):
    return round(100.0 * a / n, 1) if n else 0.0


@app.route('/api/late_goal', methods=['GET'])
def api_late_goal():
    """Закономерности «гол после 40-й минуты 1-го тайма» по собранным контрольным точкам."""
    try:
        data = _tl_load()
        names = getattr(Config, 'LEAGUE_NAMES', {}) or {}
        done = [r for r in data.values() if r.get('g1h') is not None]
        rows = []
        for r in done:
            cp = next((c for c in r['cps'] if c.get('k40')), None)
            if not cp:
                continue
            g1h, m = r['g1h'], cp['min']
            # точка валидна, если счёт в ней совпал с голами по событиям и между точкой и 40-й минутой голов не было
            if sum(cp['score']) != sum(1 for x in g1h if x <= m):
                continue
            if any(m < x <= 40 for x in g1h):
                continue
            late = any(x > max(m, 40) for x in g1h)      # гол после 40-й минуты (41' и позже, включая добавленное)
            rows.append((r, cp, late, late))
        n = len(rows)
        out = {'status': 'ok', 'tracked': len(data), 'finished_1h': len(done), 'with_cp40': n,
               'late': _pc(sum(1 for x in rows if x[2]), n), 'late41': _pc(sum(1 for x in rows if x[3]), n)}

        def group(keyf):
            g = {}
            for r, cp, late, l41 in rows:
                k = keyf(r, cp)
                if k is None:
                    continue
                b = g.setdefault(k, [0, 0, 0, []]); b[0] += 1; b[1] += 1 if late else 0; b[2] += 1 if l41 else 0
                if late:
                    mins = [x for x in r['g1h'] if x > max(cp['min'], 40)]
                    b[3].append('%s – %s (гол %s′)' % (r.get('home'), r.get('away'), ', '.join(str(x) for x in mins)))
            return [{'key': k, 'n': v[0], 'late': _pc(v[1], v[0]), 'late41': _pc(v[2], v[0]), 'late_matches': v[3]}
                    for k, v in sorted(g.items(), key=lambda kv: -kv[1][0])]

        out['by_score'] = group(lambda r, cp: '%d-%d' % tuple(cp['score']))
        out['by_league'] = group(lambda r, cp: str(names.get(r.get('league'), r.get('league'))))

        def sot_bucket(r, cp):
            s = (cp.get('stats') or {}).get('sot')
            if not s:
                return None
            t = sum(s)
            return '0–2 ударов в створ' if t <= 2 else '3–5 ударов в створ' if t <= 5 else '6+ ударов в створ'
        out['by_sot'] = group(sot_bucket)

        def fav_case(r, cp):
            if not r.get('pre'):
                return None
            side = _fav_side(r['pre'])
            if side == '0':
                return 'равные команды'
            h, a = cp['score']
            if h == a:
                return 'ничья, есть фаворит'
            lead = '1' if h > a else '2'
            return 'фаворит ведёт' if side == lead else 'фаворит проигрывает'
        out['by_fav'] = group(fav_case)

        def over_odds(cp):
            line = '%.1f' % (sum(cp['score']) + 0.5)
            return ((cp.get('odds') or {}).get('ou1h') or {}).get(line, {}).get('over')

        def agg(items):
            k = len(items)
            if not k:
                return None
            avg = sum(o for o, _ in items) / k
            hit = sum(1 for _, w in items if w)
            return {'n': k, 'avg_odds': round(avg, 2), 'hit': _pc(hit, k), 'implied': round(100 / avg, 1),
                    'roi': round(100.0 * sum((o - 1) if w else -1 for o, w in items) / k, 1)}

        def buckets(items, spec):
            res = []
            for name, fnc in spec:
                a_ = agg([b for b in items if fnc(b[0])])
                if a_:
                    a_['bucket'] = name; res.append(a_)
            return res
        odds_spec = [('до 1,6', lambda o: o < 1.6), ('1,6–2,0', lambda o: 1.6 <= o < 2.0), ('2,0–2,5', lambda o: 2.0 <= o < 2.5),
                     ('2,5–3,2', lambda o: 2.5 <= o < 3.2), ('от 3,2', lambda o: o >= 3.2)]
        bets, bets00 = [], []
        moves = []
        for r, cp, late, _ in rows:
            o = over_odds(cp)
            if not o:
                continue
            bets.append((o, late))
            if sum(cp['score']) == 0:
                bets00.append((o, late))
            # движение кэфа с контрольной точки 26–36′ (при том же числе голов, т.е. той же линии)
            line = '%.1f' % (sum(cp['score']) + 0.5)
            early = [c for c in r['cps'] if 26 <= c['min'] <= 36 and c['min'] < cp['min'] and sum(c['score']) == sum(cp['score'])]
            if early:
                o0 = ((early[0].get('odds') or {}).get('ou1h') or {}).get(line, {}).get('over')
                if o0:
                    moves.append(((o / o0 - 1) * 100, o, late))
        out['odds_all'] = agg(bets)
        out['odds_buckets'] = buckets(bets, odds_spec)
        out['odds_buckets_00'] = buckets(bets00, odds_spec)
        mv_spec = [('кэф упал более чем на 10%', lambda m: m < -10), ('почти не менялся (±10%)', lambda m: -10 <= m <= 10), ('кэф вырос более чем на 10%', lambda m: m > 10)]
        mres = []
        for name, fnc in mv_spec:
            items = [(o, w) for mv, o, w in moves if fnc(mv)]
            a_ = agg(items)
            if a_:
                a_['bucket'] = name; mres.append(a_)
        out['move_buckets'] = mres
        return jsonify(out)
    except Exception as e:
        logger.exception(f"api_late_goal error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
