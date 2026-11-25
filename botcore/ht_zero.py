# -*- coding: utf-8 -*-
# botcore/ht_zero.py — «ТМ 0.5 в 1-м тайме» (0-0 к перерыву). Тестовый режим: сигналы пишутся, ставки не делаются.
# Идея: по истории команд (3 сезона) считаем вероятность 0-0 к перерыву, честный кэф = 1/p,
# сравниваем с предматчевым кэфом букмекеров на «Under 0.5 1st half». Если кэф выше честного на EV%, пишем сигнал.
import os
import json
import time
from datetime import datetime
from threading import Thread, Lock
from flask import jsonify

from app.config import Config

from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403
from botcore.routes_data import *  # noqa: F401,F403

__all__ = ['ht_zero_job', 'api_ht_zero']

_TM_FILE = os.path.join(DATA_DIR, 'ht_team_matches.json')
_Z_FILE = os.path.join(DATA_DIR, 'ht_zero.json')
_z_lock = Lock()
_fetch_state = {'running': False}
_IDX = {'mtime': None, 'team': {}, 'league': {}}
_LAST_N = 20          # последних матчей команды
_SHRINK = 10          # вес средней по лиге при малой выборке команды


def _cfg(name, default):
    return getattr(Config, name, default)


def _z_load():
    try:
        with open(_Z_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _z_save(d):
    with _z_lock:
        tmp = _Z_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(d, fh)
        os.replace(tmp, _Z_FILE)


# ---------- история команд: 0-0 к перерыву ----------
def _tm_fetch_job():
    """3 сезона матчей лиг Line Movement: [лига, время, id дома, id гостей, голы дома 1Т, голы гостей 1Т]."""
    if _fetch_state['running']:
        return
    _fetch_state['running'] = True
    try:
        cur = int(Config.USE_SEASON)
        rows = []
        for lid in _lm_league_ids():
            for season in range(cur, cur - 3, -1):
                data = football_api._make_request('/fixtures', {'league': lid, 'season': season, 'status': 'FT'})
                for f in (data or {}).get('response', []):
                    ht = (f.get('score') or {}).get('halftime') or {}
                    tm = f.get('teams') or {}
                    ts = (f.get('fixture') or {}).get('timestamp')
                    hid, aid = (tm.get('home') or {}).get('id'), (tm.get('away') or {}).get('id')
                    if None in (ht.get('home'), ht.get('away'), ts, hid, aid):
                        continue
                    rows.append([lid, ts, hid, aid, ht['home'], ht['away']])
        if rows:
            with open(_TM_FILE, 'w', encoding='utf-8') as fh:
                json.dump({'updated': time.time(), 'rows': rows}, fh)
            logger.info(f"🛡 ht_zero: история команд обновлена, матчей {len(rows)}")
    except Exception as e:
        logger.exception(f"ht_zero fetch: {e}")
    finally:
        _fetch_state['running'] = False


def _tm_index():
    try:
        mt = os.path.getmtime(_TM_FILE)
    except Exception:
        return None
    if _IDX['mtime'] != mt:
        try:
            with open(_TM_FILE, 'r', encoding='utf-8') as fh:
                rows = json.load(fh).get('rows') or []
        except Exception:
            return None
        team, league = {}, {}
        for lid, ts, hid, aid, hh, ha in sorted(rows, key=lambda r: r[1]):
            z = 1 if (hh + ha) == 0 else 0
            team.setdefault(hid, []).append(z)
            team.setdefault(aid, []).append(z)
            b = league.setdefault(lid, [0, 0]); b[0] += z; b[1] += 1
        _IDX.update(mtime=mt, team=team, league=league)
    return _IDX


def _calc_prob(lid, hid, aid):
    """(p, n_дома, n_гостей) или None. p = среднее по двум командам, каждая подтянута к средней по лиге."""
    idx = _tm_index()
    if not idx:
        return None
    lg = idx['league'].get(lid)
    if not lg or lg[1] < 50:
        return None
    pl = lg[0] / lg[1]
    out, ns = [], []
    for tid in (hid, aid):
        hist = (idx['team'].get(tid) or [])[-_LAST_N:]
        n = len(hist)
        out.append((sum(hist) + _SHRINK * pl) / (n + _SHRINK))
        ns.append(n)
    return (out[0] + out[1]) / 2, ns[0], ns[1], pl


# ---------- предматчевый кэф «1-й тайм, тотал меньше 0.5» ----------
def _fetch_under05(fid):
    """Возвращает (медиана, лучший, число контор) или None."""
    data = football_api._make_request('/odds', {'fixture': fid})
    vals = []
    for item in (data or {}).get('response', []):
        for bk in item.get('bookmakers', []) or []:
            for b in bk.get('bets', []) or []:
                low = str(b.get('name') or '').lower()
                if 'over/under' not in low or not ('first half' in low or '1st half' in low):
                    continue
                if any(w in low for w in ('2nd', 'second', 'team', 'home', 'away')):
                    continue
                for v in b.get('values') or []:
                    txt = str(v.get('value') or '').strip().lower()
                    if txt.replace('under', '').strip() != '0.5' or not txt.startswith('under'):
                        continue
                    try:
                        o = float(v.get('odd'))
                    except Exception:
                        continue
                    if o > 1.0:
                        vals.append(o)
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2], vals[-1], len(vals)


def _notify(rec):
    try:
        send_telegram(
            f"🛡 <b>ТМ 0.5 в 1-м тайме</b> (тест, без ставки)\n{rec['home']} — {rec['away']}\n"
            f"Кэф {rec['odds']} против честного {round(1 / rec['p'], 2)}\n"
            f"Шанс 0-0 к перерыву {round(rec['p'] * 100, 1)}% против {round(100 / rec['odds'], 1)}% в кэфе "
            f"(EV {round(rec['ev'] * 100)}%)")
        return True
    except Exception as e:
        logger.warning(f"ht_zero notify: {e}")
        return False


def ht_zero_job():
    """Каждые 20 минут: новые матчи ваших лиг, свежие кэфы, сигналы, расчёт завершённых."""
    try:
        # история команд обновляется раз в сутки (≈21 запрос)
        try:
            age = time.time() - os.path.getmtime(_TM_FILE)
        except Exception:
            age = 1e9
        if age > 86400 and not _fetch_state['running']:
            Thread(target=_tm_fetch_job, daemon=True).start()

        recs = _z_load()
        now = time.time()
        changed = False
        min_ev = float(_cfg('HT0_MIN_EV', 0.10))
        lo, hi = float(_cfg('HT0_MIN_ODDS', 1.8)), float(_cfg('HT0_MAX_ODDS', 5.0))
        min_n = int(_cfg('HT0_MIN_TEAM_N', 12))

        # 1) подхватываем новые матчи и обновляем кэфы
        for f in lm_collect_fixtures():
            fx, tm = f.get('fixture') or {}, f.get('teams') or {}
            fid = str(fx.get('id'))
            ts = fx.get('timestamp') or 0
            if not ts or ts <= now:
                continue
            hid, aid = (tm.get('home') or {}).get('id'), (tm.get('away') or {}).get('id')
            lid = (f.get('league') or {}).get('id')
            pr = _calc_prob(lid, hid, aid)
            if not pr:
                continue
            rec = recs.get(fid)
            if rec is None:
                rec = recs[fid] = {'league': lid, 'home': (tm.get('home') or {}).get('name'),
                                   'away': (tm.get('away') or {}).get('name'), 'ts': ts,
                                   'odds': None, 'best': None, 'hist': [], 'last_fetch': 0,
                                   'signal': None, 'notified': False, 'hth': None, 'hta': None, 'result': None}
            rec['p'], rec['nh'], rec['na'], rec['pl'] = round(pr[0], 4), pr[1], pr[2], round(pr[3], 4)
            gap = 2400 if ts - now < 7200 else 10800
            if now - rec['last_fetch'] >= gap:
                rec['last_fetch'] = now
                got = _fetch_under05(fx.get('id'))
                if got:
                    rec['odds'], rec['best'] = round(got[0], 2), round(got[1], 2)
                    rec['hist'] = (rec['hist'] + [[int(now), rec['odds']]])[-40:]
                changed = True
            if rec['odds']:
                rec['ev'] = round(rec['p'] * rec['odds'] - 1, 4)
                if (rec['signal'] is None and rec['ev'] >= min_ev and lo <= rec['odds'] <= hi
                        and min(rec['nh'], rec['na']) >= min_n):
                    rec['signal'] = {'odds': rec['odds'], 'ev': rec['ev'], 'p': rec['p'], 't': int(now)}
                    changed = True
            changed = True

        # 2) расчёт завершённых (кэш результатов обходим: нужен точный счёт 1-го тайма)
        for fid, rec in recs.items():
            if rec['result'] is not None or now < rec['ts'] + 9000:
                continue
            if now - rec.get('settle_try', 0) < 1800:
                continue
            rec['settle_try'] = now
            changed = True
            data = football_api._make_request('/fixtures', {'id': fid})
            fr = ((data or {}).get('response') or [None])[0]
            if not fr:
                continue
            st = ((fr.get('fixture') or {}).get('status') or {}).get('short')
            ht = (fr.get('score') or {}).get('halftime') or {}
            if st in FINAL_STATUSES and ht.get('home') is not None and ht.get('away') is not None:
                rec['hth'], rec['hta'] = ht['home'], ht['away']
                rec['result'] = 'zero' if ht['home'] + ht['away'] == 0 else 'goal'
            elif now > rec['ts'] + 4 * 86400:
                rec['result'] = 'void'

        # 3) уведомления (в тихие часы молчим, отправим позже, пока матч не начался)
        if _cfg('HT0_NOTIFY', True) and not _quiet_now():
            for rec in recs.values():
                if rec['signal'] and not rec['notified'] and rec['ts'] > now:
                    if _notify(dict(rec, odds=rec['signal']['odds'], ev=rec['signal']['ev'], p=rec['signal']['p'])):
                        rec['notified'] = True
                        changed = True

        # чистим давно завершённые без расчёта
        for fid in [k for k, r in recs.items() if r['result'] == 'void' and now > r['ts'] + 10 * 86400]:
            recs.pop(fid)
            changed = True
        if changed:
            _z_save(recs)
    except Exception as e:
        logger.exception(f"ht_zero_job error: {e}")


@app.route('/api/ht_zero', methods=['GET'])
def api_ht_zero():
    try:
        recs = _z_load()
        names = getattr(Config, 'LEAGUE_NAMES', {}) or {}
        now = time.time()
        off = TIMEZONE_OFFSET * 3600
        upcoming, signals = [], []
        done = [r for r in recs.values() if r['result'] in ('zero', 'goal')]
        for fid, r in sorted(recs.items(), key=lambda kv: kv[1]['ts']):
            if r['ts'] < now - 4 * 3600 and r['result'] in ('zero', 'goal', 'void'):
                continue
            ev = r.get('ev')
            if not r.get('odds'):
                flag = 'no_odds'
            elif min(r.get('nh', 0), r.get('na', 0)) < int(_cfg('HT0_MIN_TEAM_N', 12)):
                flag = 'few'
            elif ev is not None and ev >= float(_cfg('HT0_MIN_EV', 0.10)):
                flag = 'value'
            elif ev is not None and ev <= -0.15:
                flag = 'trap'
            else:
                flag = 'fair'
            upcoming.append({'home': r['home'], 'away': r['away'], 'league': names.get(r['league'], str(r['league'])),
                             'time': datetime.utcfromtimestamp(r['ts'] + off).strftime('%d.%m %H:%M'),
                             'p': round(r['p'] * 100, 1), 'fair': round(1 / r['p'], 2) if r['p'] else None,
                             'odds': r.get('odds'), 'best': r.get('best'), 'ev': round(ev * 100) if ev is not None else None,
                             'flag': flag, 'result': r['result'],
                             'ht': None if r['hth'] is None else '%d-%d' % (r['hth'], r['hta'])})
        sig_done = [r for r in done if r['signal']]
        wins = sum(1 for r in sig_done if r['result'] == 'zero')
        roi = round(100.0 * sum((r['signal']['odds'] - 1) if r['result'] == 'zero' else -1 for r in sig_done) / len(sig_done), 1) if sig_done else 0
        clvs = []
        for r in sig_done:
            close = [o for t, o in r['hist'] if t < r['ts']]
            if close and close[-1] > 1:
                clvs.append(r['signal']['odds'] / close[-1] - 1)
        # калибровка по всем завершённым: насколько прогноз совпал с реальностью
        calib = None
        if done:
            calib = {'n': len(done), 'pred': round(100 * sum(r['p'] for r in done) / len(done), 1),
                     'real': round(100 * sum(1 for r in done if r['result'] == 'zero') / len(done), 1)}
        return jsonify({'status': 'ok', 'upcoming': upcoming, 'calib': calib,
                        'signals': {'total': len([r for r in recs.values() if r['signal']]), 'done': len(sig_done),
                                    'wins': wins, 'losses': len(sig_done) - wins, 'roi': roi,
                                    'clv': round(100 * sum(clvs) / len(clvs), 1) if clvs else None},
                        'history_ready': _tm_index() is not None})
    except Exception as e:
        logger.exception(f"api_ht_zero error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
