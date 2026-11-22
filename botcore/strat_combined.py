# ============================================================
# botcore/strat_combined.py — Сводный поиск матчей (find_top_matches_with_tm25) и скоринг
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

__all__ = [
    'calc_match_score',
    'get_score_threshold',
    'get_score_weights',
    'find_top_matches_with_tm25',
    'update_pending_bets',
]


# ============================================================
# ★ v23.7: SCORE-BASED ФИЛЬТР (Без изменений)
# ============================================================
def calc_match_score(ev, prob, odds, clv_mult=1.0, total_xg=0):
    """Считает общий score матча для Score-based фильтра."""
    score = 0.0
    score += min(max(ev, 0), 50) * 0.4
    if prob >= 40:
        if prob <= 70:
            prob_score = (prob - 40) / 30 * 100
        elif prob <= 80:
            prob_score = 100
        else:
            prob_score = max(0, 100 - (prob - 80) * 3)
        score += prob_score * 0.3
    score += clv_mult * 20
    if total_xg > 0:
        if 2.0 <= total_xg <= 3.0:
            xg_score = 100
        elif total_xg < 2.0:
            xg_score = max(0, (total_xg - 1.0) / 1.0 * 100)
        else:
            xg_score = max(0, 100 - (total_xg - 3.0) * 50)
        score += xg_score * 0.1
    if 1.6 <= odds <= 2.2:
        score += 5
    elif odds < 1.5 or odds > 3.0:
        score -= 5
    return round(score, 1)


def get_score_threshold(source='70_percent'):
    thresholds = {
        '70_percent': 7.0,
        'value': 6.5,
        'btts': 6.0,
        'tm25_premium': 7.5,
        'tm25_standard': 6.5,
        'line_movement': 5.0,
        'stats': 5.0,
    }
    return thresholds.get(source, 7.0)


def get_score_weights(source='70_percent'):
    weights = {
        '70_percent': {'ev': 0.4, 'prob': 0.3, 'clv': 0.2, 'xg': 0.1},
        'value': {'ev': 0.5, 'prob': 0.2, 'clv': 0.2, 'xg': 0.1},
        'btts': {'ev': 0.4, 'prob': 0.35, 'clv': 0.15, 'xg': 0.1},
        'tm25_premium': {'ev': 0.35, 'prob': 0.35, 'clv': 0.2, 'xg': 0.1},
        'tm25_standard': {'ev': 0.4, 'prob': 0.3, 'clv': 0.2, 'xg': 0.1},
        'line_movement': {'ev': 0, 'prob': 0, 'clv': 0, 'xg': 0},
        'stats': {'ev': 0.5, 'prob': 0.3, 'clv': 0.1, 'xg': 0.1},
    }
    return weights.get(source, {'ev': 0.4, 'prob': 0.3, 'clv': 0.2, 'xg': 0.1})


# ============================================================
# КОМБИНИРОВАННЫЙ ПОИСК
# ============================================================
@timing_decorator()
def find_top_matches_with_tm25(matches):
    logger.info("=" * 60)
    logger.info("🎯 ЕДИНСТВЕННАЯ СТРАТЕГИЯ: LINE MOVEMENT (Steam Move)")
    logger.info("=" * 60)

    # 1. Запускаем ТОЛЬКО поиск движения линии
    # ★★★ ФИКС: Делаем снимки ПЕРЕД запуском LM ★★★
    try:
        logger.info("📸 [PRE-LM-FIX] Принудительный вызов снимков...")
        
        # ★ Передаем ТОЛЬКО те матчи, которые нашли сейчас
        with cache_lock:
            cache = storage.load_cache()
            fresh_matches = cache.get('top_matches', [])
            
        snapshot_odds_for_upcoming(fresh_matches) # <-- Передаем аргумент!
        
    except Exception as e:
        logger.error(f"❌ [PRE-LM-FIX] Ошибка: {e}")
    # ★★★ КОНЕЦ ФИКСА ★★★

    try:
        lm_matches = find_line_movement_matches(matches)
    except Exception as e:
        logger.error(f"❌ LINE MOVEMENT упал: {e}")
        lm_matches = []

    # ★ Сохраняем сигналы: кэш (Матчи/Live) + история (счёт после финала) + автоставки.
    #   Раньше всё это стояло ПОСЛЕ return и никогда не выполнялось.
    try:
        lm_matches = _persist_lm_picks(lm_matches)
    except Exception as e:
        logger.error(f"❌ Сохранение LM-сигналов: {e}")

    return lm_matches

    # 2. Собираем всё в один список (у нас теперь только он)
    combined = []
    keys = set()

    for m in lm_matches:
        key = f"{m['home']}_{m['away']}"
        if key not in keys:
            combined.append(m)
            keys.add(key)

    # Сортируем по силе движения (чем сильнее упал кэф, тем выше)
    def _sort_key(m):
        return abs(m['best_bet'].get('movement_pct', 0))
    
    combined.sort(key=_sort_key, reverse=True)

    if not combined:
        logger.info("⚠️ Нет сигналов Line Movement")
        return []

    # 3. Обновляем кэфы (делаем один запрос на все найденные матчи)
    logger.info(f"📡 Обновление кэфов для {len(combined)} сигналов...")
    combined = update_odds_for_matches(combined)

    # 4. Финальная фильтрация перед сохранением
    filtered = []
    for m in combined:
        bb = m.get('best_bet', {})
        # Оставляем только те, где кэф реально обновился (чтобы не ставить по шаблону)
        if bb.get('odds_updated'):
            m.pop('_preloaded_odds', None)
            m.pop('_preloaded_preds', None)
            filtered.append(m)

    logger.info(f"📊 Итоговых сигналов: {len(filtered)}")

   # 5. Сохраняем в кэш
    try:
        cache = storage.load_cache()
        cache['top_matches'] = filtered
        cache['all_analyzed'] = filtered
        storage.save_cache(cache)
        
        # Делаем снимки сразу после сохранения в кэш
        logger.info("📸 [CACHE-FIX] Кэш сохранен. Делаем снимки для найденных матчей...")
        snapshot_odds_for_upcoming()
    except Exception as e:
        logger.error(f"❌ [CACHE-FIX] Ошибка снимков: {e}")

    # 6. Добавляем в историю (в БД)
    history = storage.load_history()
    today_str = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d')
    existing = {(h.get('home'), h.get('away'), h.get('date', '').split()[0]) for h in history}
    added = 0
    for md in filtered:
        bb = md.get('best_bet', {})
        key = (md.get('home'), md.get('away'), today_str)
        if key in existing: continue
        existing.add(key)
        
        history.append({
            'home': md.get('home'), 'away': md.get('away'),
            'league': md.get('league'),
            'bet': bb.get('label', '—'),
            'odds': bb.get('odds', 0),
            'stake': bb.get('stake', 0),
            'ev': bb.get('ev', 0), 'prob': bb.get('prob', 0),
            'result': 'pending', 'profit': 0,
            'date': (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d %H:%M'),
            'match_time': md.get('match_time', ''),
            'fixture_id': md.get('fixture_id'),
            'bookmaker': bb.get('bookmaker', '—'),
            'engine': 'line_movement',
            'weather_reason': '',
            'source': 'line_movement',
            'llm_reason': '',
            'steam_move': True,
            'clv_adjusted': True,
            'score': 0,
        })
        added += 1
    
    if added > 0:
        storage.save_history(history)
        logger.info(f"📝 Добавлено в историю: {added}")

    # 7. Автоставки
    try:
        placed = autobet_manager.place_bets_from_cache()
        if placed > 0:
            logger.info(f"💸 Автоставок размещено: {placed}")
    except Exception as e:
        logger.error(f"Ошибка автоставок: {e}")

    return filtered


# ============================================================
# ОБНОВЛЕНИЕ PENDING (BATCH FIX)
# ============================================================
@timing_decorator()
def update_pending_bets():
    """
    Обновляет pending-ставки.
    ★ ФИКС: Делает один батч-запрос по дате вместо 100 запросов.
    """
    history = storage.load_history()
    updated = 0
    live_updated = 0
    
    # Группируем pending ставки по датам матчей
    pending_bets = [b for b in history if b.get('result') in ('pending', None)]
    if not pending_bets:
        return {'ft': 0, 'live': 0}
        
    dates_to_fetch = set()
    for bet in pending_bets:
        match_time = bet.get('match_time', '')
        if match_time and match_time != '?':
            try:
                dt = datetime.strptime(match_time, "%d.%m.%Y %H:%M")
                dates_to_fetch.add(dt.strftime('%Y-%m-%d'))
            except:
                pass
    
    if not dates_to_fetch:
        logger.warning("Нет валидных дат для обновления pending")
        return {'ft': 0, 'live': 0}
        
    # Запрашиваем результаты батчем по датам
    results_cache = {}
    for date_str in dates_to_fetch:
        try:
            # Используем /fixtures?date= (это один запрос вместо N)
            data = football_api._make_request('/fixtures', {'date': date_str, 'timezone': 'Europe/Moscow'})
            if data and data.get('response'):
                for f in data['response']:
                    fid = f.get('fixture', {}).get('id')
                    if fid:
                        results_cache[fid] = f
            logger.info(f"📥 Batch fetch: {len(data.get('response', []))} матчей на {date_str}")
        except Exception as e:
            logger.error(f"Batch fetch error {date_str}: {e}")

    # Теперь обновляем локально
    for bet in pending_bets:
        fid = bet.get('fixture_id')
        if not fid:
            continue
            
        f = results_cache.get(fid)
        if not f:
            continue
            
        status = f.get('fixture', {}).get('status', {})
        goals = f.get('goals', {})
        hg = goals.get('home')
        ag = goals.get('away')
        
        if hg is None or ag is None:
            continue
            
        status_short = status.get('short', 'NS')
        is_final = status_short in ('FT', 'AET', 'PEN', 'AWD', 'WO')
        is_live = status_short in ('1H', 'HT', '2H', 'ET', 'BT', 'P', 'INT', 'LIVE', 'SUSP')
        
        if is_live:
            bet['live_score'] = f"{hg}-{ag}"
            bet['live_status'] = status_short
            bet['live_minute'] = status.get('elapsed', 0)
            ht = f.get('score', {}).get('halftime', {}) or {}
            if ht.get('home') is not None:
                bet['live_halftime'] = f"{ht.get('home')}-{ht.get('away')}"
            live_updated += 1
            continue
            
        if is_final:
            result = determine_bet_result(bet.get('bet', ''), hg, ag)
            if result != 'pending':
                bet['result'] = result
                bet['home_goals'] = hg
                bet['away_goals'] = ag
                ht = f.get('score', {}).get('halftime', {}) or {}
                if ht.get('home') is not None:
                    bet['halftime_home'] = ht.get('home')
                    bet['halftime_away'] = ht.get('away')
                    
                if result == 'win':
                    bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                elif result == 'loss':
                    bet['profit'] = -bet['stake']
                else:
                    bet['profit'] = 0
                    
                for k in ['live_score', 'live_status', 'live_minute', 'live_halftime']:
                    bet.pop(k, None)
                updated += 1

    if updated > 0 or live_updated > 0:
        storage.save_history(history)
        if updated > 0:
            recalc_stats()
            
    logger.info(f"🔄 update_pending_bets (BATCH): FT={updated}, LIVE={live_updated}")
    return {'ft': updated, 'live': live_updated}
