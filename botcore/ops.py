# ============================================================
# botcore/ops.py — настройки из приложения, ежедневный отчёт, бэкап
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
from botcore.routes_data import *  # noqa: F401,F403
from botcore.routes_lab import *  # noqa: F401,F403

__all__ = [
    'api_bot_settings_get',
    'api_bot_settings_set',
    'api_backup_download',
    'ops_report_job',
    'ops_backup_job',
    'build_daily_report',
    'ops_make_backup',
    'ops_streak_job',
    'ops_results_job',
    'api_backtest',
]

# ============================================================
# Настройки, которые можно менять из приложения (без правки кода)
# ============================================================
_BOT_SETTINGS_SCHEMA = {
    # ключ Config: (тип, минимум, максимум, значение по умолчанию)
    'LINE_MOVEMENT_MIN_DROP_PCT': ('float', -30.0, 0.0, -4.0),
    'LINE_MOVEMENT_MAX_DROP_PCT': ('float', -60.0, 0.0, -15.0),
    'LINE_MOVEMENT_MIN_ODDS': ('float', 1.01, 20.0, 2.0),
    'LINE_MOVEMENT_MAX_ODDS': ('float', 1.01, 50.0, 4.5),
    'LINE_MOVEMENT_STAKE_PCT': ('float', 0.001, 0.2, 0.015),
    'LINE_MOVEMENT_MAX_BETS': ('int', 1, 20, 3),
    'DAY_NOTIFY_MOVE_PCT': ('float', 1.0, 50.0, 8.0),
    'NOTIFY_QUIET_ENABLED': ('bool', 0, 1, True),
    'NOTIFY_QUIET_FROM': ('int', 0, 23, 0),
    'NOTIFY_QUIET_TO': ('int', 0, 23, 8),
    'DAILY_REPORT_ENABLED': ('bool', 0, 1, True),
    'DAILY_REPORT_HOUR': ('int', 0, 23, 9),
    'STREAK_ALERT_LOSSES': ('int', 0, 20, 4),
}
_settings_lock = Lock()


def _current_bot_settings():
    return {k: getattr(Config, k, v[3]) for k, v in _BOT_SETTINGS_SCHEMA.items()}


@app.route('/api/bot_settings_ui', methods=['GET'])
def api_bot_settings_get():
    return jsonify({'status': 'ok', 'settings': _current_bot_settings()})


@app.route('/api/bot_settings_ui', methods=['POST'])
def api_bot_settings_set():
    try:
        body = request.get_json(silent=True) or {}
        clean = {}
        for k, raw in body.items():
            if k not in _BOT_SETTINGS_SCHEMA:
                continue
            typ, lo, hi, _ = _BOT_SETTINGS_SCHEMA[k]
            if typ == 'bool':
                clean[k] = bool(raw)
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'error': f'{k}: не число'}), 400
            if not (lo <= v <= hi):
                return jsonify({'status': 'error', 'error': f'{k}: допустимо {lo}…{hi}'}), 400
            clean[k] = int(v) if typ == 'int' else v
        cur = dict(_current_bot_settings(), **clean)
        if cur['LINE_MOVEMENT_MIN_ODDS'] >= cur['LINE_MOVEMENT_MAX_ODDS']:
            return jsonify({'status': 'error', 'error': 'Мин. кэф должен быть меньше макс.'}), 400
        if cur['LINE_MOVEMENT_MAX_DROP_PCT'] > cur['LINE_MOVEMENT_MIN_DROP_PCT']:
            return jsonify({'status': 'error', 'error': 'Макс. падение должно быть глубже мин. падения'}), 400
        with _settings_lock:
            try:
                with open(SETTINGS_PATH, 'r') as f:
                    stored = json.load(f)
                if not isinstance(stored, dict):
                    stored = {}
            except Exception:
                stored = {}
            for k, v in clean.items():
                setattr(Config, k, v)
                stored[k.lower()] = v
            tmp = SETTINGS_PATH + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(stored, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SETTINGS_PATH)
        logger.info(f"⚙️ Настройки обновлены из приложения: {clean}")
        return jsonify({'status': 'ok', 'settings': _current_bot_settings()})
    except Exception as e:
        logger.exception(f"api_bot_settings_set error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# Состояние «раз в сутки» для отчёта и бэкапа
# ============================================================
_OPS_STATE_FILE = os.path.join(DATA_DIR, 'ops_state.json')


def _ops_state():
    try:
        with open(_OPS_STATE_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ops_state_set(key, value):
    st = _ops_state()
    st[key] = value
    try:
        with open(_OPS_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f)
    except Exception as e:
        logger.warning(f"ops_state: не удалось сохранить: {e}")


# ============================================================
# Ежедневный отчёт в Telegram
# ============================================================
def build_daily_report(day_dm):
    """Отчёт за день по матчам 'дд.мм.гггг' (МСК)."""
    import html as _html
    all_rows = _lm_bets_with_clv()
    rows = [r for r in all_rows if str(r.get('match_time', '')).startswith(day_dm)]
    a = _agg_bets(rows)
    pending = a['n'] - a['settled']
    lines = [f"📊 <b>Итоги за {day_dm}</b>"]
    if not rows:
        lines.append("Сигналов Line Movement не было.")
    else:
        lines.append(f"Ставок: {a['n']} • ✅ {a['wins']} / ❌ {a['losses']}" + (f" / ⏳ {pending}" if pending else ""))
        lines.append(f"Прибыль: {a['profit']:+.2f}")
        if a['avg_clv'] is not None:
            lines.append(f"Средний CLV: {a['avg_clv']:+.2f}%")
        for r in rows[:10]:
            icon = {'win': '✅', 'loss': '❌', 'push': '➖'}.get(r.get('result'), '⏳')
            lines.append(f"{icon} {_html.escape(str(r.get('home')))} — {_html.escape(str(r.get('away')))} • {r.get('bet')} @ {r.get('odds')}")
    tot = _agg_bets(all_rows)
    if tot['settled']:
        roi = f"{tot['roi']:+.1f}%" if tot['roi'] is not None else '—'
        clv = f"{tot['avg_clv']:+.2f}%" if tot['avg_clv'] is not None else '—'
        lines.append(f"\n<b>За всё время:</b> {tot['settled']} ставок, ROI {roi}, CLV {clv}")
    leagues = {}
    for r in all_rows:
        leagues.setdefault(r.get('league') or '?', []).append(r)
    for name, v in leagues.items():
        w = _flag_weak(dict(_agg_bets(v), league=name))
        if w['weak']:
            lines.append(f"⚠️ {_html.escape(str(name))}: CLV {w['avg_clv']:+.2f}% после {w['settled']} ставок — стоит рассмотреть исключение лиги")
    return '\n'.join(lines)


def ops_report_job():
    """Каждые 15 мин проверяет: пора ли слать вчерашний отчёт (раз в сутки, не раньше DAILY_REPORT_HOUR по МСК)."""
    try:
        if not getattr(Config, 'DAILY_REPORT_ENABLED', True):
            return
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
        if now_msk.hour < int(getattr(Config, 'DAILY_REPORT_HOUR', 9)):
            return
        today = now_msk.strftime('%Y-%m-%d')
        if _ops_state().get('last_report') == today:
            return
        yesterday = (now_msk - timedelta(days=1)).strftime('%d.%m.%Y')
        send_telegram(build_daily_report(yesterday))
        _ops_state_set('last_report', today)
        logger.info(f"📨 Ежедневный отчёт за {yesterday} отправлен")
    except Exception as e:
        logger.exception(f"ops_report_job error: {e}")


# ============================================================
# Резервная копия данных
# ============================================================
_BACKUP_EXT = ('.json', '.jsonl', '.db', '.sqlite', '.sqlite3')


def ops_make_backup(keep=7):
    """Архив данных (история, снимки, заметки, настройки) в BACKUP_DIR; хранит последние keep штук."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    dirs = []
    for d in (DATA_DIR, getattr(storage, 'data_dir', None)):
        if d and os.path.isdir(d) and os.path.abspath(d) not in [os.path.abspath(x) for x in dirs]:
            dirs.append(d)
    seen = set()
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for d in dirs:
            for root, subdirs, files in os.walk(d):
                subdirs[:] = [x for x in subdirs if x not in ('backups', '__pycache__')]
                for fn in files:
                    full = os.path.join(root, fn)
                    if not fn.lower().endswith(_BACKUP_EXT) or full in seen:
                        continue
                    try:
                        if os.path.getsize(full) > 80 * 1024 * 1024:
                            continue
                    except OSError:
                        continue
                    seen.add(full)
                    zf.write(full, os.path.relpath(full, d))
    old = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_') and f.endswith('.zip'))
    for f in old[:-keep]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except OSError:
            pass
    return path


def ops_backup_job():
    """Раз в сутки (около 04:00 МСК): архив на диск + файл в Telegram."""
    try:
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
        if now_msk.hour < 4:
            return
        today = now_msk.strftime('%Y-%m-%d')
        if _ops_state().get('last_backup') == today:
            return
        path = ops_make_backup()
        _ops_state_set('last_backup', today)
        size = os.path.getsize(path)
        if size < 45 * 1024 * 1024:
            with open(path, 'rb') as f:
                requests.post(
                    f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument",
                    files={'document': (os.path.basename(path), f, 'application/zip')},
                    data={'chat_id': Config.ADMIN_CHAT_ID,
                          'caption': f"💾 Резервная копия {today} • {size / 1024:.0f} КБ"},
                    timeout=90)
        logger.info(f"💾 Бэкап создан: {path} ({size / 1024:.0f} КБ)")
    except Exception as e:
        logger.exception(f"ops_backup_job error: {e}")


@app.route('/api/backup/download', methods=['GET'])
def api_backup_download():
    try:
        from flask import send_file
        path = ops_make_backup()
        return send_file(path, mimetype='application/zip', as_attachment=True,
                         download_name=os.path.basename(path))
    except Exception as e:
        logger.exception(f"api_backup_download error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# Серия поражений: предупреждение в Telegram
# ============================================================
def ops_streak_job():
    try:
        n = int(getattr(Config, 'STREAK_ALERT_LOSSES', 4))
        if n <= 0 or _quiet_now():
            return
        st = _streaks(_lm_bets_with_clv())
        cur = st['current'] if st['current_type'] == 'loss' else 0
        alerted = int(_ops_state().get('streak_alerted', 0))
        if cur < n:
            if alerted:
                _ops_state_set('streak_alerted', 0)
            return
        if cur > alerted:
            send_telegram(f"⚠️ <b>Серия поражений: {cur} подряд</b>\n"
                          f"Рекордная серия за всё время: {st['best_loss']}. "
                          f"Проверьте аналитику и пороги Line Movement.")
            _ops_state_set('streak_alerted', cur)
    except Exception as e:
        logger.exception(f"ops_streak_job error: {e}")


# ============================================================
# Итоговые счета матчей со снимками (нужны для бэктеста)
# ============================================================
_FIXTURE_RESULTS_FILE = os.path.join(DATA_DIR, 'fixture_results.json')


def _load_fixture_results():
    try:
        with open(_FIXTURE_RESULTS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def ops_results_job():
    """Раз в час: сохраняет финальные счета матчей, по которым есть снимки (вчера и сегодня, МСК)."""
    try:
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
        cutoff = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S')
        fids = {r.get('fixture_id') for r in storage.get_snapshots_since(cutoff) if is_lm_item(r)}
        if not fids:
            return
        res = _load_fixture_results()
        added = 0
        for d in ((now_msk - timedelta(days=1)).strftime('%Y-%m-%d'), now_msk.strftime('%Y-%m-%d')):
            batch = football_api._make_request('/fixtures', {'date': d, 'timezone': 'Europe/Moscow'})
            for f in (batch or {}).get('response', []):
                fid = (f.get('fixture') or {}).get('id')
                st = ((f.get('fixture') or {}).get('status') or {}).get('short')
                g = f.get('goals') or {}
                if fid in fids and st in ('FT', 'AET', 'PEN') and g.get('home') is not None and str(fid) not in res:
                    res[str(fid)] = {'hg': g['home'], 'ag': g['away']}
                    added += 1
        if added:
            with open(_FIXTURE_RESULTS_FILE, 'w', encoding='utf-8') as fh:
                json.dump(res, fh)
            logger.info(f"📝 Сохранено счетов для бэктеста: {added}")
    except Exception as e:
        logger.exception(f"ops_results_job error: {e}")


# ============================================================
# Бэктест: «что было бы с другими настройками»
# ============================================================
def _sel_wins(sel, hg, ag):
    return {'1': hg > ag, 'X': hg == ag, '2': ag > hg, '1X': hg >= ag, 'X2': ag >= hg}.get(sel)


def _bt_collect(days):
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    series, meta = {}, {}
    for r in storage.get_snapshots_since(cutoff):
        if not is_lm_item(r):
            continue
        fid, sel, o = r.get('fixture_id'), r.get('selection'), r.get('odds') or 0
        if not fid or not sel or o <= 1.01 or r.get('market', '1X2') not in ('1X2', 'DC'):
            continue
        series.setdefault((fid, sel), []).append((r.get('created_at') or '', float(o)))
        if r.get('match_time') and fid not in meta:
            meta[fid] = r['match_time']
    for v in series.values():
        v.sort()
    results = dict(_load_fixture_results())
    for b in storage.load_history():
        if b.get('fixture_id') and b.get('home_goals') is not None and b.get('away_goals') is not None:
            results[str(b['fixture_id'])] = {'hg': b['home_goals'], 'ag': b['away_goals']}
    return series, meta, results


def _bt_run(series, meta, results, p):
    wins = n = 0
    profit = 0.0
    clvs = []
    for (fid, sel), pts in series.items():
        if sel not in p['sels']:
            continue
        r = results.get(str(fid))
        if not r:
            continue
        try:
            match_dt = datetime.strptime(meta.get(fid, ''), '%d.%m.%Y %H:%M')
        except Exception:
            continue
        for i in range(len(pts)):
            window = pts[max(0, i - p['max_snaps'] + 1): i + 1]
            if len(window) < p['min_snaps']:
                continue
            try:
                t1 = datetime.fromisoformat(window[0][0]); t2 = datetime.fromisoformat(window[-1][0])
            except Exception:
                continue
            if (t2 - t1).total_seconds() / 3600 < p['min_span']:
                continue
            t_msk = t2 + timedelta(hours=TIMEZONE_OFFSET)
            if t_msk >= match_dt or (match_dt - t_msk).total_seconds() / 3600 > p['hours_before']:
                continue
            new, old = window[-1][1], window[0][1]
            change = (new / old - 1) * 100
            lo, hi = min(p['min_drop'], p['max_drop']), max(p['min_drop'], p['max_drop'])
            if not (lo <= change <= hi) or not (p['min_odds'] <= new <= p['max_odds']):
                continue
            won = _sel_wins(sel, r['hg'], r['ag'])
            if won is None:
                break
            n += 1
            wins += 1 if won else 0
            profit += (new - 1) if won else -1
            clvs.append((new / pts[-1][1] - 1) * 100)
            break
    return {'n': n, 'wins': wins, 'losses': n - wins,
            'winrate': round(wins / n * 100, 1) if n else None,
            'profit': round(profit, 2), 'roi': round(profit / n * 100, 1) if n else None,
            'avg_clv': round(sum(clvs) / len(clvs), 2) if clvs else None}


@app.route('/api/backtest', methods=['GET'])
def api_backtest():
    try:
        g = request.args.get

        def f(name, cfg, default):
            try:
                return float(g(name)) if g(name) not in (None, '') else float(getattr(Config, cfg, default))
            except ValueError:
                return float(default)
        days = min(max(int(float(g('days', 60))), 1), 180)
        p = {
            'min_drop': f('min_drop', 'LINE_MOVEMENT_MIN_DROP_PCT', -4.0),
            'max_drop': f('max_drop', 'LINE_MOVEMENT_MAX_DROP_PCT', -15.0),
            'min_odds': f('min_odds', 'LINE_MOVEMENT_MIN_ODDS', 2.0),
            'max_odds': f('max_odds', 'LINE_MOVEMENT_MAX_ODDS', 4.5),
            'hours_before': f('hours_before', 'LINE_MOVEMENT_HOURS_BEFORE', 12),
            'min_snaps': int(getattr(Config, 'LINE_MOVEMENT_MIN_SNAPSHOTS', 3)),
            'max_snaps': int(getattr(Config, 'LINE_MOVEMENT_MAX_SNAPSHOTS', 20)),
            'min_span': float(getattr(Config, 'LINE_MOVEMENT_MIN_SPAN_HOURS', 0.5)),
            'sels': [x for x in (g('sels') or ','.join(getattr(Config, 'LINE_MOVEMENT_BET_TYPES', ['2']))).split(',') if x],
        }
        series, meta, results = _bt_collect(days)
        fids = {fid for (fid, _) in series}
        with_res = sum(1 for fid in fids if str(fid) in results)
        grid_drop = [dict(_bt_run(series, meta, results, dict(p, min_drop=d)), value=d)
                     for d in (-2, -3, -4, -5, -6, -8, -10)]
        grid_odds = [dict(_bt_run(series, meta, results, dict(p, min_odds=a, max_odds=b)), value=f'{a}–{b}')
                     for a, b in ((1.4, 2.5), (2.0, 3.0), (2.0, 4.5), (3.0, 6.0))]
        return jsonify({'status': 'ok', 'params': p, 'days': days,
                        'coverage': {'fixtures': len(fids), 'with_result': with_res},
                        'result': _bt_run(series, meta, results, p),
                        'grid_drop': grid_drop, 'grid_odds': grid_odds})
    except Exception as e:
        logger.exception(f"api_backtest error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
