# -*- coding: utf-8 -*-
# botcore/ht_strategy.py — стратегия «Перерыв» (тестовый режим: сигналы пишутся, ставки не делаются)
# Идея: в перерыве сравнить live-кэф с частотой исхода из истории (5 сезонов) при таком же счёте 1-го тайма.
# Рынки: тоталы матча, «обе забьют», ничья. П1/П2 исключены: история не учитывает силу команд.
import os
import json
import time
from datetime import datetime
from threading import Lock
from flask import request, jsonify

from app.config import Config

from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403
from botcore.routes_data import *  # noqa: F401,F403
from botcore.ht_stats import _hto_load, _ht_load, _sel_hit  # noqa: F401

__all__ = ['ht_signal_job', 'api_ht_signals']

_SIG_FILE = os.path.join(DATA_DIR, 'ht_signals.json')
_sig_lock = Lock()
_MODEL_CACHE = {'mtime': None, 'groups': {}}
_SHRINK_M = 40          # «вес» общей статистики при малой выборке лиги


def _cfg(name, default):
    return getattr(Config, name, default)


def _sig_load():
    try:
        with open(_SIG_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _sig_save(d):
    with _sig_lock:
        with open(_SIG_FILE, 'w', encoding='utf-8') as fh:
            json.dump(d, fh)


def _groups():
    """Матчи 5 сезонов: {'0-0': {'all': [(h,a)...], lid: [...]}}"""
    try:
        mt = os.path.getmtime(os.path.join(DATA_DIR, 'ht_matches.json'))
    except Exception:
        return {}
    if _MODEL_CACHE['mtime'] != mt:
        g = {}
        for r in (_ht_load().get('rows') or []):
            k = '%d-%d' % (r[2], r[3])
            d = g.setdefault(k, {'all': []})
            d['all'].append((r[4], r[5]))
            d.setdefault(r[0], []).append((r[4], r[5]))
        _MODEL_CACHE.update(mtime=mt, groups=g)
    return _MODEL_CACHE['groups']


def _prob(sel, ht_key, lid):
    """Вероятность исхода: доля в лиге, подтянутая к общей доле (при малой выборке лиги)."""
    g = _groups().get(ht_key)
    if not g or len(g['all']) < int(_cfg('HT_MIN_SAMPLE', 30)):
        return None, 0
    allr = g['all']
    p_all = sum(1 for ft in allr if _sel_hit(sel, ft)) / len(allr)
    lr = g.get(lid) or []
    hits_l = sum(1 for ft in lr if _sel_hit(sel, ft))
    p = (hits_l + _SHRINK_M * p_all) / (len(lr) + _SHRINK_M)
    return p, len(allr)


def _sel_name(sel):
    kind, arg = sel
    if kind == '1x2':
        return {'1': 'П1', 'X': 'Ничья', '2': 'П2'}.get(arg, arg)
    if kind == 'btts':
        return 'Обе забьют: ' + ('да' if arg == 'yes' else 'нет')
    return ('Тотал больше ' if arg[0] == 'over' else 'Тотал меньше ') + arg[1]


def _candidates(rec):
    o = rec.get('odds') or {}
    out = []
    if (o.get('1x2') or {}).get('X'):
        out.append((('1x2', 'X'), o['1x2']['X']))
    for k, v in (o.get('btts') or {}).items():
        out.append((('btts', k), v))
    for ln, sd in (o.get('ou') or {}).items():
        if 1.5 <= float(ln) <= 4.5:
            for side, v in sd.items():
                out.append((('ou', (side, ln)), v))
    return out


def _pack(sel):
    return [sel[0], list(sel[1]) if isinstance(sel[1], tuple) else sel[1]]


def _unpack(s):
    return (s[0], tuple(s[1]) if isinstance(s[1], list) else s[1])


def ht_signal_job():
    """Каждые 3 минуты: новые сигналы по сохранённым перерывам + расчёт завершённых матчей."""
    try:
        recs = _hto_load()
        sigs = _sig_load()
        changed = False
        min_ev = float(_cfg('HT_MIN_EV', 0.12))
        lo, hi = float(_cfg('HT_MIN_ODDS', 1.5)), float(_cfg('HT_MAX_ODDS', 8.0))
        for fid, r in recs.items():
            if fid in sigs or r.get('ft') is not None:
                continue
            ht_key = '%d-%d' % tuple(r['ht'])
            best = None
            for sel, odd in _candidates(r):
                if not (lo <= odd <= hi):
                    continue
                p, n = _prob(sel, ht_key, r.get('league'))
                if p is None:
                    continue
                ev = p * odd - 1
                if min_ev <= ev <= 0.6 and (best is None or ev > best['ev']):
                    best = {'sel': _pack(sel), 'odds': odd, 'p': round(p, 4), 'ev': round(ev, 4), 'n': n}
            if best:
                best.update(league=r.get('league'), home=r.get('home'), away=r.get('away'), ht=r['ht'],
                            ts=r.get('ts'), ft=None, result=None, notified=False)
                sigs[fid] = best
                changed = True
        # расчёт завершённых
        for fid, s in sigs.items():
            r = recs.get(fid) or {}
            if s.get('result') is None and r.get('ft') is not None:
                hit = _sel_hit(_unpack(s['sel']), r['ft'])
                s['ft'] = r['ft']
                s['result'] = 'win' if hit else 'loss'
                changed = True
        # уведомления (в тихие часы молчим, отправятся позже, пока матч не закончился)
        if _cfg('HT_SIGNAL_NOTIFY', True) and not _quiet_now():
            for fid, s in sigs.items():
                if s.get('notified') or s.get('result') is not None:
                    continue
                try:
                    send_telegram(
                        f"⏱ <b>Перерыв</b> (тест, без ставки)\n{s['home']} — {s['away']}\n"
                        f"Счёт {s['ht'][0]}:{s['ht'][1]}\n"
                        f"<b>{_sel_name(_unpack(s['sel']))}</b> @ {s['odds']}\n"
                        f"Шанс по истории {round(s['p'] * 100, 1)}% против {round(100 / s['odds'], 1)}% в кэфе "
                        f"(EV {round(s['ev'] * 100)}%, выборка {s['n']})")
                    s['notified'] = True
                    changed = True
                except Exception as e:
                    logger.warning(f"ht signal notify: {e}")
        if changed:
            _sig_save(sigs)
    except Exception as e:
        logger.exception(f"ht_signal_job error: {e}")


@app.route('/api/ht_signals', methods=['GET'])
def api_ht_signals():
    try:
        sigs = _sig_load()
        names = getattr(Config, 'LEAGUE_NAMES', {}) or {}
        items = []
        for fid, s in sigs.items():
            sel = _unpack(s['sel'])
            profit = None
            if s.get('result'):
                profit = round(s['odds'] - 1, 2) if s['result'] == 'win' else -1.0
            items.append({'fid': fid, 'match': f"{s['home']} — {s['away']}", 'league': names.get(s.get('league'), s.get('league')),
                          'ht': '%d:%d' % tuple(s['ht']), 'ft': ('%d:%d' % tuple(s['ft'])) if s.get('ft') else None,
                          'sel': _sel_name(sel), 'odds': s['odds'], 'p': round(s['p'] * 100, 1),
                          'implied': round(100 / s['odds'], 1), 'ev': round(s['ev'] * 100), 'n': s['n'],
                          'result': s.get('result'), 'profit': profit, 'ts': s.get('ts')})
        items.sort(key=lambda x: x['ts'] or '', reverse=True)
        done = [x for x in items if x['result']]
        wins = sum(1 for x in done if x['result'] == 'win')
        profit = sum(x['profit'] for x in done)
        by_sel = {}
        for x in done:
            b = by_sel.setdefault(x['sel'], {'n': 0, 'w': 0, 'p': 0.0})
            b['n'] += 1; b['w'] += 1 if x['result'] == 'win' else 0; b['p'] += x['profit']
        return jsonify({'status': 'ok', 'total': len(items), 'settled': len(done), 'wins': wins,
                        'losses': len(done) - wins, 'pending': len(items) - len(done),
                        'roi': round(100.0 * profit / len(done), 1) if done else 0,
                        'by_sel': [{'sel': k, 'n': v['n'], 'wins': v['w'], 'roi': round(100.0 * v['p'] / v['n'], 1)}
                                   for k, v in sorted(by_sel.items(), key=lambda kv: -kv[1]['n'])],
                        'items': items[:80],
                        'params': {'min_ev': float(_cfg('HT_MIN_EV', 0.12)), 'odds': [float(_cfg('HT_MIN_ODDS', 1.5)), float(_cfg('HT_MAX_ODDS', 8.0))]}})
    except Exception as e:
        logger.exception(f"api_ht_signals error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
