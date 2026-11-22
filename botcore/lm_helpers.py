# ============================================================
# botcore/lm_helpers.py — Line Movement: лиги, снимки кэфов, фильтры вкладок, сохранение сигналов
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

__all__ = [
    '_LM_FIX_CACHE',
    '_LM_API_NAMES',
    '_lm_known_fixture_ids',
    'is_lm_item',
    'lm_filter',
    '_lm_snapshots_since',
    '_stats_from_history',
    '_LIVE_BATCH',
    '_fetch_live_batch',
    '_persist_lm_picks',
    '_lm_league_ids',
    '_lm_dates',
    '_lm_fixtures_for',
    'lm_collect_fixtures',
    'lm_take_snapshots',
    '_snapshot_lock',
    'snapshot_odds_for_upcoming',
    '_save_snapshot_from_odds',
]


# ============================================================
# ★ СНИМКИ КЭФОВ (LOCK + ЛИМИТ 30)
# ============================================================

# ============================================================
# ★ ФИЛЬТР «ТОЛЬКО ЛИГИ LINE MOVEMENT» для всех вкладок
# ============================================================
_LM_FIX_CACHE = {'ts': 0.0, 'ids': set()}


_LM_API_NAMES = {'premier league', 'super league 1', 'eredivisie', 'primeira liga',
                 'pro league', 'jupiler pro league', 'championship'}


def _lm_known_fixture_ids():
    """ID матчей LM-лиг, известных по снимкам (обновляется раз в минуту)."""
    now = time.time()
    if now - _LM_FIX_CACHE['ts'] > 60:
        try:
            ids = storage.get_lm_fixture_ids(_lm_league_ids())
        except Exception:
            ids = set()
        _LM_FIX_CACHE['ts'] = now
        _LM_FIX_CACHE['ids'] = ids
    return _LM_FIX_CACHE['ids']


def is_lm_item(rec):
    """Запись (матч/ставка/снимок/кандидат) относится к лигам Line Movement?
    1) есть league_id -> строго по ID; 2) матч известен по снимкам LM-лиг;
    3) старые записи без ID -> по названию лиги (+страна, если указана)."""
    if not isinstance(rec, dict):
        return True
    ids = set(_lm_league_ids())
    lid = rec.get('league_id')
    if lid not in (None, ''):
        try:
            return int(lid) in ids
        except Exception:
            return False
    fid = rec.get('fixture_id')
    if fid and fid in _lm_known_fixture_ids():
        return True
    countries = {Config.LEAGUE_COUNTRY.get(l, ('', ''))[0] for l in ids} - {''}
    country = str(rec.get('country') or '').strip()
    if country and country not in countries:
        return False
    name = str(rec.get('league') or '').strip().lower()
    allowed = set(_LM_API_NAMES) | {str(Config.LEAGUE_NAMES.get(l, '')).lower() for l in ids}
    allowed.discard('super league')          # неоднозначно (Греция/Швейцария/Китай)
    allowed.discard('')
    if name in allowed:
        return True
    return name == 'super league' and country in countries


def lm_filter(items):
    return [x for x in (items or []) if is_lm_item(x)]


def _lm_snapshots_since(cutoff):
    return [r for r in storage.get_snapshots_since(cutoff) if is_lm_item(r)]


def _stats_from_history(history):
    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    profit = sum(b.get('profit', 0) or 0 for b in history)
    stake_sum = sum(b.get('stake', 0) or 0 for b in history)
    return {
        'total': total, 'wins': wins, 'losses': losses,
        'total_profit': round(profit, 2),
        'winrate': round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0,
        'roi': round(profit / stake_sum * 100, 1) if stake_sum else 0,
        'avg_stake': round(stake_sum / total, 2) if total else 0,
    }


_LIVE_BATCH = {'date': None, 'ts': 0.0, 'data': {}}


def _fetch_live_batch(today_str):
    """Все матчи дня одним запросом (память 15 сек — Live обновляется каждые 20 сек)."""
    now = time.time()
    if _LIVE_BATCH['date'] == today_str and now - _LIVE_BATCH['ts'] < 15:
        return _LIVE_BATCH['data']
    out = {}
    try:
        batch = football_api._make_request('/fixtures', {
            'date': today_str, 'timezone': 'Europe/Moscow'
        })
        if batch and batch.get('response'):
            for f in batch['response']:
                fid = f.get('fixture', {}).get('id')
                if fid:
                    out[fid] = f
            logger.info(f"📡 Live batch: {len(out)} матчей на {today_str}")
    except Exception as e:
        logger.error(f"Live batch error: {e}")
        return _LIVE_BATCH['data'] if _LIVE_BATCH['date'] == today_str else {}
    _LIVE_BATCH.update(date=today_str, ts=now, data=out)
    return out


def _persist_lm_picks(picks):
    """Сигналы Line Movement -> кэш (вкладки Матчи/Live) + история (pending;
    счёт и результат проставит update_pending_bets после финала) + автоставки."""
    if not picks:
        return []
    for p in picks:
        p.pop('_preloaded_odds', None)
        p.pop('_preloaded_preds', None)

    with cache_lock:
        cache = storage.load_cache()
        cache['top_matches'] = picks
        cache['all_analyzed'] = picks
        storage.save_cache(cache)

    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    history = storage.load_history()
    existing_fids = {h.get('fixture_id') for h in history if h.get('fixture_id')}
    existing_keys = {(h.get('home'), h.get('away'), str(h.get('date', '')).split(' ')[0])
                     for h in history}
    today_str = now_msk.strftime('%Y-%m-%d')
    added = 0
    for md in picks:
        bb = md.get('best_bet', {}) or {}
        fid = md.get('fixture_id')
        if (fid and fid in existing_fids) or (md.get('home'), md.get('away'), today_str) in existing_keys:
            continue
        history.append({
            'home': md.get('home'), 'away': md.get('away'),
            'league': md.get('league'), 'league_id': md.get('league_id'),
            'country': md.get('country', ''), 'country_flag': md.get('country_flag', ''),
            'bet': bb.get('label', '—'),
            'odds': bb.get('odds', 0), 'stake': bb.get('stake', 0),
            'ev': bb.get('ev', 0), 'prob': bb.get('prob', 0),
            'result': 'pending', 'profit': 0,
            'date': now_msk.strftime('%Y-%m-%d %H:%M'),
            'match_time': md.get('match_time', ''),
            'fixture_id': fid,
            'bookmaker': bb.get('bookmaker', '—'),
            'engine': 'line_movement', 'source': 'line_movement',
            'weather_reason': '', 'llm_reason': '',
            'steam_move': True, 'clv_adjusted': True, 'score': 0,
        })
        added += 1
    if added:
        storage.save_history(history)
        logger.info(f"📝 LM: добавлено в историю {added}")
    try:
        placed = autobet_manager.place_bets_from_cache()
        if placed:
            logger.info(f"💸 Автоставок размещено: {placed}")
    except Exception as e:
        logger.error(f"Ошибка автоставок: {e}")
    return picks


def _lm_league_ids():
    """ID лиг Line Movement из конфига (единый источник правды)."""
    return [int(x) for x in (getattr(Config, 'LINE_MOVEMENT_LEAGUE_IDS', None) or [])]


def _lm_dates():
    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    days = int(getattr(Config, 'LINE_MOVEMENT_SNAPSHOT_DAYS_AHEAD', 1))
    return [(now_msk + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]


def _lm_fixtures_for(league_id, date):
    """Ещё не начавшиеся матчи лиги на дату (сырой формат API-Football)."""
    try:
        fixtures = football_api.get_matches(league_id, date) or []
    except Exception as e:
        logger.error(f"[LM-SNAP] fixtures {league_id} {date}: {e}")
        return []
    out = []
    now_ts = time.time()
    for f in fixtures:
        fx = f.get('fixture') or {}
        if not fx.get('id'):
            continue
        if (f.get('league') or {}).get('id') != league_id:
            continue
        if (fx.get('status') or {}).get('short') not in ('NS', 'TBD'):
            continue
        ts = fx.get('timestamp')
        if ts and ts <= now_ts:      # кэш матчей живёт 12 ч — статус мог устареть
            continue
        out.append(f)
    return out


def lm_collect_fixtures():
    """Матчи ТОЛЬКО из LINE_MOVEMENT_LEAGUE_IDS на сегодня/завтра (МСК), ещё не начавшиеся."""
    out = {}
    for lid in _lm_league_ids():
        for date in _lm_dates():
            for f in _lm_fixtures_for(lid, date):
                out[f['fixture']['id']] = f
    return list(out.values())


def lm_take_snapshots():
    """Снимки кэфов ТОЛЬКО по лигам Line Movement. Не зависит от кэша стратегий."""
    ids = _lm_league_ids()
    if not ids:
        logger.warning("[LM-SNAP] LINE_MOVEMENT_LEAGUE_IDS пуст — снимки не делаются")
        return 0
    bet_types = getattr(Config, 'LINE_MOVEMENT_BET_TYPES', ['2'])
    saved_total = 0
    for lid in ids:
        lname = Config.LEAGUE_NAMES.get(lid, str(lid))
        for date in _lm_dates():
            fixtures = _lm_fixtures_for(lid, date)
            if not fixtures:
                continue
            try:
                odds_map = football_api.get_odds_fresh_for_league(lid, date)
            except Exception as e:
                logger.error(f"[LM-SNAP] odds {lid} {date}: {e}")
                continue
            with_odds = saved = 0
            for f in fixtures:
                fid = f['fixture']['id']
                fo = odds_map.get(fid)
                if not fo:
                    continue
                with_odds += 1
                teams = f.get('teams') or {}
                home = (teams.get('home') or {}).get('name', '')
                away = (teams.get('away') or {}).get('name', '')
                league = (f.get('league') or {}).get('name', lname)
                try:
                    mt_msk = parse_match_time_to_msk((f.get('fixture') or {}).get('date', ''))
                except Exception:
                    mt_msk = ''
                for sel, key in (('1', 'home_odds'), ('X', 'draw_odds'), ('2', 'away_odds')):
                    if fo.get(key, 0) > 1.01:
                        if storage.save_odds_snapshot(fid, '1X2', sel, fo[key], 'LM-Job', home, away, league,
                                                      league_id=lid, match_time=mt_msk):
                            saved += 1
                for sel, key in (('1X', '1x_odds'), ('X2', 'x2_odds')):
                    if sel in bet_types and fo.get(key, 0) > 1.01:
                        if storage.save_odds_snapshot(fid, 'DC', sel, fo[key], 'LM-Job', home, away, league,
                                                      league_id=lid, match_time=mt_msk):
                            saved += 1
            saved_total += saved
            logger.info(f"📸 [LM-SNAP] {lname} {date}: матчей {len(fixtures)}, "
                        f"с кэфами {with_odds}, новых снимков {saved}")
    logger.info(f"📸 [LM-SNAP] Итого новых снимков: {saved_total}")
    return saved_total


_snapshot_lock = Lock()


def snapshot_odds_for_upcoming(custom_matches=None):
    """Совместимая обёртка (планировщик, /snapshot, /api/snapshot, поиск).
    custom_matches игнорируется: берём матчи только из LINE_MOVEMENT_LEAGUE_IDS."""
    if not _snapshot_lock.acquire(blocking=False):
        logger.warning("⏭️ snapshot уже выполняется — пропуск")
        return 0
    try:
        return lm_take_snapshots()
    finally:
        _snapshot_lock.release()


def _save_snapshot_from_odds(fo, fid, home='', away='', league=''):
    try:
        if not fo:
            return 0
        bookmaker = fo.get('bookmaker', 'Football API')
        saved = 0

        has_1x2 = (fo.get('home_odds', 0) > 1.01 or
                   fo.get('away_odds', 0) > 1.01 or
                   fo.get('draw_odds', 0) > 1.01)
        if has_1x2:
            odds_map = {
                '1': fo.get('home_odds', 0),
                'X': fo.get('draw_odds', 0),
                '2': fo.get('away_odds', 0),
            }
            for sel, odd in odds_map.items():
                if odd and odd > 1.01:
                    if storage.save_odds_snapshot(
                        fixture_id=fid, market='1X2',
                        selection=sel, odds=odd, bookmaker=bookmaker,
                        home=home, away=away, league=league
                    ):
                        saved += 1

        x2_odd = fo.get('x2_odds', 0) or 0
        x1_odd = fo.get('1x_odds', 0) or 0
        if x2_odd > 1.01:
            if storage.save_odds_snapshot(
                fixture_id=fid, market='DC',
                selection='X2', odds=x2_odd, bookmaker=bookmaker,
                home=home, away=away, league=league
            ):
                saved += 1
        if x1_odd > 1.01:
            if storage.save_odds_snapshot(
                fixture_id=fid, market='DC',
                selection='1X', odds=x1_odd, bookmaker=bookmaker,
                home=home, away=away, league=league
            ):
                saved += 1

        btts_yes = fo.get('btts_yes', 0) or 0
        if btts_yes > 1.01:
            if storage.save_odds_snapshot(
                fixture_id=fid, market='BTTS',
                selection='BTTS', odds=btts_yes, bookmaker=bookmaker,
                home=home, away=away, league=league
            ):
                saved += 1

        return saved
    except Exception as e:
        logger.error(f"_save_snapshot_from_odds: {e}")
        return 0
