# ============================================================
# botcore/strat_lm.py — Стратегия Line Movement (поиск сигналов)
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

__all__ = [
    'find_line_movement_matches',
]


# ============================================================
# ★ ПОТОК 5: LINE MOVEMENT (v5.2 — с фиксами и фильтром Scotland)
# ============================================================
@timing_decorator()
def find_line_movement_matches(matches):
    LM_ENABLED = getattr(Config, 'LINE_MOVEMENT_ENABLED', True)
    if not LM_ENABLED:
        logger.info("⏭️ [LINE MOVEMENT] Отключено в конфиге")
        return []

    # (снимки делает lm_take_snapshots() — планировщик и PRE-LM; здесь только анализ)

    bank = storage.load_bank()

    # ★ FIX 13: защита от пустого банка
    if bank <= 0:
        logger.warning("[LM] Банк = 0 — пропуск")
        return []

    MAX_BETS = getattr(Config, 'LINE_MOVEMENT_MAX_BETS', 2)
    MIN_DROP = getattr(Config, 'LINE_MOVEMENT_MIN_DROP_PCT', -6.0)
    MAX_DROP = getattr(Config, 'LINE_MOVEMENT_MAX_DROP_PCT', -15.0)
    MIN_RISE = getattr(Config, 'LINE_MOVEMENT_MIN_RISE_PCT', 8.0)
    MAX_RISE = getattr(Config, 'LINE_MOVEMENT_MAX_RISE_PCT', 20.0)
    HOURS_BEFORE = getattr(Config, 'LINE_MOVEMENT_HOURS_BEFORE', 6)
    MIN_SNAPS = getattr(Config, 'LINE_MOVEMENT_MIN_SNAPSHOTS', 3)
    MAX_SNAPS = getattr(Config, 'LINE_MOVEMENT_MAX_SNAPSHOTS', 20)
    TRADE_DROPS = getattr(Config, 'LINE_MOVEMENT_TRADE_DROPS', True)
    TRADE_RISES = getattr(Config, 'LINE_MOVEMENT_TRADE_RISES', False)
    MAX_LEAGUE_BETS = getattr(Config, 'LINE_MOVEMENT_MAX_LEAGUE_BETS', 1)
    MIN_ODDS = getattr(Config, 'LINE_MOVEMENT_MIN_ODDS', 1.40)
    MAX_ODDS = getattr(Config, 'LINE_MOVEMENT_MAX_ODDS', 3.50)
    STAKE_PCT = getattr(Config, 'LINE_MOVEMENT_STAKE_PCT', 0.015)

    # ★ FIX 6: вынести магическое число в конфиг (с дефолтом)
    MIN_SPAN_HOURS = getattr(Config, 'LINE_MOVEMENT_MIN_SPAN_HOURS', 0.5)

    # ★ FIX 5: явные границы диапазонов падения/роста
    DROP_LOW = min(MIN_DROP, MAX_DROP)     # -15.0
    DROP_HIGH = max(MIN_DROP, MAX_DROP)    # -6.0
    RISE_LOW = min(MIN_RISE, MAX_RISE)     # 8.0
    RISE_HIGH = max(MIN_RISE, MAX_RISE)    # 20.0

    logger.info("🔍 [LINE MOVEMENT v5.2] Поиск аномалий кэфов...")
    stats = {
        'found': 0,
        'blacklist': 0,
        'whitelist_miss': 0,
        'no_snaps': 0,
        'no_drop': 0,
        'no_bet': 0,
        'league_limit': 0,
        'odds_filter': 0,
        'time_filter': 0,
        'parse_error': 0,
        'rlm_rejected': 0,
        'fav_collapse_rejected': 0, # ★ Новая метрика
        'not_in_lookup': 0,        # ★ снимки матчей вне LM-лиг / уже начавшихся
    }

    # ---------- match_lookup: ТОЛЬКО матчи из LINE_MOVEMENT_LEAGUE_IDS ----------
    LM_IDS = set(_lm_league_ids())
    _lm_src = list(lm_collect_fixtures()) + [x for x in (matches or []) if isinstance(x, dict)]
    match_lookup = {}
    for m in _lm_src:
        fixture = m.get('fixture')
        if not fixture or not isinstance(fixture, dict):
            continue
        fid = fixture.get('id')
        if not fid:
            continue
        ld = m.get('league', {})
        lid = ld.get('id') if isinstance(ld, dict) else None
        if lid not in LM_IDS:
            continue
        teams = m.get('teams', {})
        ht = teams.get('home', {})
        at = teams.get('away', {})
        match_lookup[fid] = {
            'home': ht.get('name', 'Unknown'),
            'away': at.get('name', 'Unknown'),
            'league': ld.get('name', 'Unknown'),
            'league_id': lid,
            'match_time': parse_match_time_to_msk(fixture.get('date', '')),
            'fixture_date': fixture.get('date', ''),
        }

    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    cutoff_time = now_msk + timedelta(hours=HOURS_BEFORE)

    # ★ FIX 8: сузили окно снимков (было 2 дня — избыточно)
    snapshots_cutoff = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        all_snaps = storage.get_snapshots_since(snapshots_cutoff)
    except Exception as e:
        logger.error(f"[LM] Ошибка получения снимков: {e}")
        return []

    if not all_snaps:
         logger.info("[LM] База пуста. Ждем CACHE-FIX.")
         return []
        
    LM_BET_TYPES = getattr(Config, 'LINE_MOVEMENT_BET_TYPES', ['1', 'X', '2', '1X', 'X2'])
    LM_1X2_SELS = [t for t in LM_BET_TYPES if t in ('1', 'X', '2')]
    LM_DC_SELS = [t for t in LM_BET_TYPES if t in ('1X', 'X2')]



    # ---------- группировка снимков ----------
    groups = defaultdict(list)
    for s in all_snaps:
        fid = s.get('fixture_id')
        if not fid:
            continue
        market = s.get('market', '1X2')
        sel = s.get('selection', '')
        if market == '1X2' and sel in LM_1X2_SELS:
            groups[(fid, market, sel)].append(s)
        elif market == 'DC' and sel in LM_DC_SELS:
            groups[(fid, market, sel)].append(s)

    _total_groups = len(groups)
    groups = {k: v for k, v in groups.items() if k[0] in match_lookup}
    stats['not_in_lookup'] = _total_groups - len(groups)
    logger.info(f"[LM] Матчей LM-лиг (сегодня/завтра): {len(match_lookup)} | "
                f"групп снимков: {_total_groups}, из них по LM-матчам: {len(groups)} | "
                f"снимков в окне: {len(all_snaps)}")

    # ★ FIX 12: обратный словарь league_name → (country, flag) один раз
    name_to_country = {}
    for lid, lname in Config.LEAGUE_NAMES.items():
        name_to_country[lname] = Config.LEAGUE_COUNTRY.get(lid, ("", ""))

    # ---------- метки исходов (вычисляем один раз) ----------
    LABELS = {'1': 'П1', '2': 'П2', 'X': 'X', '1X': '1X', 'X2': 'X2'}

    # ---------- RLM-настройки для АПЛ ----------
    rlm_min_hours = getattr(Config, 'RLM_EPL_MIN_HOURS', 1.0)
    rlm_min_pct = getattr(Config, 'RLM_EPL_MIN_CHANGE_PCT', abs(DROP_HIGH))
    rlm_require_rise = getattr(Config, 'RLM_EPL_REQUIRE_RISE', False)

    candidates = []
    league_bet_count = {}

    for (fid, market, sel), snaps in groups.items():
        logger.debug(f"🔍 [LM] Проверяем fid={fid}, sel={sel}, snaps={len(snaps)}")
        
        if len(candidates) >= MAX_BETS * 3:
            continue

        try:
            if fid not in match_lookup:
                continue
            meta = match_lookup[fid]
            league_name = meta['league']

            # 1) лига должна быть из LINE_MOVEMENT_LEAGUE_IDS (по ID, а не по названию)
            if meta.get('league_id') not in LM_IDS:
                stats['whitelist_miss'] += 1
                continue

            # 2) проверка времени матча
            try:
                match_dt = datetime.strptime(meta['match_time'], "%d.%m.%Y %H:%M")
            except Exception:
                stats['time_filter'] += 1
                continue
            # матч ещё не начался и стартует в пределах LINE_MOVEMENT_HOURS_BEFORE
            if match_dt < now_msk:
                stats['time_filter'] += 1
                continue
            if match_dt > cutoff_time:
                stats['time_filter'] += 1
                continue

            # 3) лимит на лигу
            cur_league_bets = league_bet_count.get(league_name, 0)
            if cur_league_bets >= MAX_LEAGUE_BETS:
                stats['league_limit'] += 1
                continue

            # 4) снимки
            snaps_sorted = sorted(snaps, key=lambda x: x.get('created_at', ''))
            if len(snaps_sorted) < MIN_SNAPS:
                stats['no_snaps'] += 1
                continue
            if len(snaps_sorted) > MAX_SNAPS:
                snaps_sorted = snaps_sorted[-MAX_SNAPS:]

            first = snaps_sorted[0]
            last = snaps_sorted[-1]

            old_odds = float(first.get('odds', 0))
            new_odds = float(last.get('odds', 0))
            if old_odds <= 1.01 or new_odds <= 1.01:
                stats['odds_filter'] += 1
                continue

            change_pct = ((new_odds / old_odds) - 1) * 100

            # 5) разброс во времени
            try:
                t1 = datetime.fromisoformat(str(first.get('created_at', '')))
                t2 = datetime.fromisoformat(str(last.get('created_at', '')))
                hours_diff = (t2 - t1).total_seconds() / 3600
            except Exception:
                stats['parse_error'] += 1
                continue

            if hours_diff < MIN_SPAN_HOURS:
                stats['time_filter'] += 1
                continue

            # 6) направление
            is_drop = DROP_LOW <= change_pct <= DROP_HIGH
            is_rise = RISE_LOW <= change_pct <= RISE_HIGH

            if is_drop and not TRADE_DROPS:
                stats['no_drop'] += 1
                continue
            if is_rise and not TRADE_RISES:
                stats['no_drop'] += 1
                continue
            if not (is_drop or is_rise):
                stats['no_drop'] += 1
                continue

            # 7) кэф в диапазоне
            if new_odds < MIN_ODDS or new_odds > MAX_ODDS:
                stats['odds_filter'] += 1
                continue

            # 8) label
            label = LABELS.get(sel, sel)

            # 9) RLM-фильтр для АПЛ
            rlm_passed = False
            if league_name == 'Premier League':
                valid_time = hours_diff >= rlm_min_hours
                valid_snaps = len(snaps_sorted) >= MIN_SNAPS
                valid_move = abs(change_pct) >= rlm_min_pct
                valid_dir = is_rise if rlm_require_rise else (is_drop or is_rise)

                if not (valid_time and valid_snaps and valid_move and valid_dir):
                    stats['rlm_rejected'] += 1
                    continue

                rlm_passed = True

            # 10) размер ставки
            final_odds = new_odds
            final_stake = round(bank * STAKE_PCT, 2)
            if final_stake < 1:
                final_stake = 1.0

            direction = "📉" if is_drop else "📈"
            label_full = f'{label} {direction}'

            best_bet = {
                'type': 'lm_' + sel.lower(),
                'label': label_full,
                'prob': 0,
                'ev': 0,
                'odds': final_odds,
                'stake': final_stake,
                'clv_action': 'no_model',
                'bookmaker': last.get('bookmaker', '—'),
                'movement_pct': round(change_pct, 1),
                'movement_hours': round(hours_diff, 1),
                'old_odds': round(old_odds, 2),
                'snapshots_count': len(snaps_sorted),
                'direction': 'drop' if is_drop else 'rise',
                'odds_updated': True,
                'rlm_epl': rlm_passed,
            }

            # 11) страна/флаг
            country_name, country_flag = Config.LEAGUE_COUNTRY.get(
                meta.get('league_id'), name_to_country.get(league_name, ("", "")))
            
            candidates.append({
                "home": meta['home'],
                "away": meta['away'],
                "league": league_name,
                "league_id": meta.get('league_id'),
                "country": country_name,
                "country_flag": country_flag,
                "fixture_id": fid,
                "match_time": meta['match_time'],
                "home_xg": 0,
                "away_xg": 0,
                "total_xg": 0,
                "home_form": '',
                "away_form": '',
                "standings": {},
                "bets": [best_bet],
                "best_bet": best_bet,
                "source": "line_movement",
                "weather_reason": "",
                "_preloaded_odds": {},
            })
            stats['found'] += 1
            league_bet_count[league_name] = cur_league_bets + 1

            logger.info(
                f"📈 LM: {meta['home']} vs {meta['away']} | "
                f"{label} @ {final_odds} | "
                f"Δ {change_pct:+.1f}% за {hours_diff:.1f}ч | "
                f"снимков: {len(snaps_sorted)} | stake ${final_stake}"
            )

        except Exception as e:
            logger.error(f"❌ [LM] КРИТИЧЕСКАЯ ОШИБКА {fid}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # ---------- топ-N по силе движения ----------
    candidates.sort(
        key=lambda x: abs(x['best_bet'].get('movement_pct', 0)),
        reverse=True
    )
    top = candidates[:MAX_BETS]

    logger.info(
        f"📈 [LINE MOVEMENT] Найдено: {len(candidates)}, взято: {len(top)} | "
        f"stats: {stats}"
    )
    return top
