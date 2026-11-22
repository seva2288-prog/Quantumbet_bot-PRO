# ============================================================
# botcore/lab_tasks.py — Лаборатория / аномалии / X2: фоновые обновления результатов
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

__all__ = [
    '_anomaly_calc_result',
    'update_anomaly_results',
    'register_bot_commands',
    'update_x2_results',
    '_lab_calc_result',
    'update_lab_results',
]


# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ ПРОПУЩЕННЫХ АНОМАЛИЙ
# ============================================================
def _anomaly_calc_result(rec, hg, ag):
    """Результат аномалии по счёту. None — не удалось определить."""
    fid = rec.get('fixture_id')
    sel = (rec.get('selection') or rec.get('bet_type') or '').upper().strip()
    if not sel:
        best_odds = rec.get('best_odds', 0) or 0
        avg_odds = rec.get('avg_odds', 0) or 0
        if best_odds > 20:
            logger.warning(
                f"⚠️ Anomaly с подозрительным кэфом {best_odds}: "
                f"{rec.get('home')} vs {rec.get('away')} — пропускаю"
            )
            return None
        logger.warning(
            f"⚠️ Anomaly без selection: fid={fid} | "
            f"{rec.get('home')} vs {rec.get('away')} | "
            f"bet_type={rec.get('bet_type')!r} | "
            f"best_odds={best_odds} avg_odds={avg_odds}"
        )
        return None

    if 'X2' in sel:
        return 'win' if ag >= hg else 'loss'
    if '1X' in sel:
        return 'win' if hg >= ag else 'loss'
    if sel == 'X' or 'DRAW' in sel or 'НИЧЬЯ' in sel:
        return 'win' if hg == ag else 'loss'
    if 'П1' in sel or sel == '1' or 'HOME' in sel:
        return 'win' if hg > ag else 'loss'
    if 'П2' in sel or sel == '2' or 'AWAY' in sel:
        return 'win' if ag > hg else 'loss'
    if 'ТМ' in sel or 'UNDER' in sel:
        return 'win' if (hg + ag) < 2.5 else 'loss'
    if 'ТБ' in sel or 'OVER' in sel:
        return 'win' if (hg + ag) > 2.5 else 'loss'
    if 'ОБЗ' in sel or 'BTTS' in sel:
        return 'win' if hg > 0 and ag > 0 else 'loss'
    return None


def update_anomaly_results():
    """
    Проверяет и обновляет результаты пропущенных аномалий.
    Фаза 1 (без блокировки): запросы к API. Фаза 2 (под блокировкой):
    перечитать файл и применить результаты только к ещё не закрытым записям.
    """
    try:
        path = ANOMALY_FILE
        if not os.path.exists(path):
            return 0

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        finals = {}
        checked = set()
        api_errors = 0
        for line in lines:
            try:
                rec = json.loads(line.strip())
            except Exception:
                continue
            if rec.get('result') and rec['result'] not in ('pending', None):
                continue
            fid = rec.get('fixture_id')
            if not fid or fid in checked:
                continue
            checked.add(fid)
            md = football_api.get_match_result(fid)
            if not md:
                api_errors += 1
                logger.warning(
                    f"⚠️ API error для fid={fid}: "
                    f"{rec.get('home')} vs {rec.get('away')} "
                    f"(повторная попытка через 30 мин)"
                )
                continue
            if not md.get('is_final'):
                continue
            hg = md['goals']['home']
            ag = md['goals']['away']
            if hg is None or ag is None:
                continue
            finals[fid] = (hg, ag)

        updated = 0
        if finals:
            with _jsonl_lock:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                new_lines = []
                for line in lines:
                    try:
                        rec = json.loads(line.strip())
                    except Exception:
                        new_lines.append(line)
                        continue
                    fid = rec.get('fixture_id')
                    if (fid in finals and
                            (not rec.get('result') or rec['result'] in ('pending', None))):
                        hg, ag = finals[fid]
                        res = _anomaly_calc_result(rec, hg, ag)
                        if res:
                            rec['result'] = res
                            rec['home_goals'] = hg
                            rec['away_goals'] = ag
                            rec['settled_at'] = datetime.now().isoformat()
                            updated += 1
                    new_lines.append(json.dumps(rec, ensure_ascii=False) + '\n')
                if updated > 0:
                    _atomic_write_lines(path, new_lines)

        if updated > 0:
            logger.info(f"📊 Anomaly results updated: {updated}")
        if api_errors > 0:
            logger.warning(f"⚠️ API errors: {api_errors} (retry через 30 мин)")
        return updated
    except Exception as e:
        logger.exception(f"update_anomaly_results: {e}")
        return 0


# ============================================================
# ★ FIX: register_bot_commands — безопасная заглушка
# ============================================================
def register_bot_commands():
    """Регистрация команд в Telegram. Опционально."""
    try:
        commands = [
            {"command": "start", "description": "🚀 Запуск"},
            {"command": "help", "description": "❓ Помощь"},
            {"command": "update", "description": "🔎 Поиск матчей"},
            {"command": "today", "description": "📅 Ставки сегодня"},
            {"command": "stats", "description": "📊 Статистика"},
            {"command": "bank", "description": "💰 Банк"},
            {"command": "live", "description": "⚡ Live матчи"},
            {"command": "strategies", "description": "📈 Стратегии"},
            {"command": "clv_strategies", "description": "📊 CLV по стратегиям"},
            {"command": "calibration", "description": "📊 Калибровка"},
            {"command": "status", "description": "🤖 Статус"},
        ]
        r = requests.post(
            f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/setMyCommands",
            json={"commands": commands},
            timeout=10
        )
        if r.status_code == 200:
            logger.info("✅ Команды Telegram зарегистрированы")
            return True
        else:
            logger.warning(f"⚠️ setMyCommands: {r.status_code} {r.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"❌ register_bot_commands: {e}")
        return False


# ============================================================
# __MAIN__
# ============================================================
def update_x2_results():
    try:
        candidates = storage.get_x2_candidates(limit=200)
        updated = 0
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)

        for c in candidates:
            if c.get('result') in ('win', 'loss', 'push'):
                continue
            fid = c.get('fixture_id')
            if not fid:
                continue
            md = football_api.get_match_result(fid)
            if not md:
                continue
            hg = md['goals']['home']
            ag = md['goals']['away']
            if hg is None or ag is None:
                continue
            status = md.get('status', 'NS')
            is_final = md.get('is_final', False)
            force_final = False
            
            if not is_final:
                match_time_str = c.get('match_time', '')
                if match_time_str and match_time_str != '?':
                    try:
                        mt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")
                        hours_ago = (now_msk - mt).total_seconds() / 3600
                        if hours_ago > 2.5:
                            force_final = True
                    except Exception:
                        pass
                if not force_final:
                    continue
                    
            side = c.get('x2_side', 'X2')
            if side == 'X2':
                result = 'win' if ag >= hg else 'loss'
            else:
                result = 'win' if hg >= ag else 'loss'
                
            odds = float(c.get('entry_odds', 0) or 0)
            if odds < 1.01:
                odds = 1.85
            stake = 20.0
            
            if result == 'win':
                profit = round(stake * (odds - 1), 2)
            elif result == 'loss':
                profit = -stake
            else:
                profit = 0
                
            ok = storage.update_x2_result(
                candidate_id=c['id'], result=result, profit=profit,
                home_goals=hg, away_goals=ag,
            )
            if ok:
                updated += 1
        return updated
    except Exception as e:
        logger.exception(f"update_x2_results: {e}")
        return 0


def _lab_calc_result(reverse_bet, hg, ag):
    if reverse_bet == 'П1':
        return 'win' if hg > ag else 'loss'
    if reverse_bet == 'П2':
        return 'win' if ag > hg else 'loss'
    if reverse_bet == 'X2':
        return 'win' if ag >= hg else 'loss'
    if reverse_bet == '1X':
        return 'win' if hg >= ag else 'loss'
    return 'unknown'


def update_lab_results():
    """Фаза 1 (без блокировки): запрашиваем финальные счета у API.
    Фаза 2 (под блокировкой): перечитываем файл и меняем только записи,
    которые всё ещё pending — новые записи и ручные правки не теряются."""
    try:
        lab_file = os.path.join(DATA_DIR, 'lab_anomalies.jsonl')
        if not os.path.exists(lab_file):
            return 0

        with open(lab_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        finals = {}   # fixture_id -> (hg, ag)
        checked = set()
        for line in lines:
            try:
                rec = json.loads(line.strip())
            except Exception:
                continue
            if rec.get('result') and rec['result'] != 'pending':
                continue
            fid = rec.get('fixture_id')
            if not fid or fid in checked:
                continue
            checked.add(fid)
            md = football_api.get_match_result(fid)
            if not md or not md.get('is_final'):
                continue
            hg = md['goals']['home']
            ag = md['goals']['away']
            if hg is None or ag is None:
                continue
            finals[fid] = (hg, ag)

        if not finals:
            return 0

        updated = 0
        with _jsonl_lock:
            with open(lab_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                try:
                    rec = json.loads(line.strip())
                except Exception:
                    new_lines.append(line)
                    continue
                fid = rec.get('fixture_id')
                if fid in finals and (not rec.get('result') or rec['result'] == 'pending'):
                    hg, ag = finals[fid]
                    res = _lab_calc_result(rec.get('reverse_bet', ''), hg, ag)
                    if res != 'unknown':
                        rec['result'] = res
                        rec['home_goals'] = hg
                        rec['away_goals'] = ag
                        updated += 1
                new_lines.append(json.dumps(rec, ensure_ascii=False) + '\n')
            if updated > 0:
                _atomic_write_lines(lab_file, new_lines)
                logger.info(f"🧪 Лаборатория: обновлено {updated} результатов")
        return updated
    except Exception as e:
        logger.error(f"update_lab_results: {e}")
        return 0
