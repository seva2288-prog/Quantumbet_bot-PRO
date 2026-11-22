# ============================================================
# botcore/odds_matches.py — Обновление кэфов, сбор матчей, погода
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

__all__ = [
    'update_odds_for_matches',
    'get_matches_with_factors',
    'check_weather_skip',
]


def update_odds_for_matches(matches):
    if not matches:
        return []

    groups = defaultdict(list)
    for md in matches:
        fid = md.get('fixture_id')
        if not fid:
            continue
        league_name = md.get('league', '')
        league_id = None
        for lid, lname in Config.LEAGUE_NAMES.items():
            if lname == league_name:
                league_id = lid
                break
        if not league_id:
            groups[('single', fid)].append(md)
            continue
        match_time = md.get('match_time', '')
        date_str = None
        try:
            dt = datetime.strptime(match_time, "%d.%m.%Y %H:%M")
            date_str = dt.strftime('%Y-%m-%d')
        except Exception:
            date_str = None
        if date_str:
            groups[(league_id, date_str)].append(md)
        else:
            groups[('single', fid)].append(md)

    batch_odds = {}
    for key, group_matches in groups.items():
        if isinstance(key, tuple) and key[0] == 'single':
            continue
        league_id, date_str = key
        try:
            batch = football_api.get_odds_batch_for_league(league_id, date_str)
            if batch:
                batch_odds.update(batch)
                logger.info(f"📦 Batch odds: league={league_id} date={date_str} → {len(batch)} матчей")
        except Exception as e:
            logger.error(f"Batch odds error {key}: {e}")

    updated = []
    total = len(matches)
    
    # ============================================================
    # ★★★ ЖЕСТКИЙ ФИКС: Сохраняем снимки для ВСЕХ матчей ДО фильтров ★★★
    # ============================================================
    logger.info(f"📸 [SNAPSHOT FIX] Принудительное сохранение снимков для {total} матчей...")
    saved_count = 0
    skipped_count = 0
    
    for md in matches:
        try:
            fid = md.get('fixture_id')
            if not fid:
                continue
                
            fo = batch_odds.get(fid) if batch_odds else None
            if not fo:
                fo = football_api.get_match_odds(fid)
            
            if fo:
                home = md.get('home', '')
                away = md.get('away', '')
                league = md.get('league', '')
                
                if fo.get('home_odds', 0) > 1.01:
                    storage.save_odds_snapshot(fid, '1X2', '1', fo['home_odds'], 'Fix', home, away, league)
                if fo.get('draw_odds', 0) > 1.01:
                    storage.save_odds_snapshot(fid, '1X2', 'X', fo['draw_odds'], 'Fix', home, away, league)
                if fo.get('away_odds', 0) > 1.01:
                    storage.save_odds_snapshot(fid, '1X2', '2', fo['away_odds'], 'Fix', home, away, league)
                    logger.info(f"✅ [SNAPSHOT FIX] Сохранен снимок: {home} vs {away} | П2: {fo['away_odds']}")
                
                saved_count += 1
            else:
                skipped_count += 1
                logger.debug(f"⚠️ [SNAPSHOT FIX] Нет кэфов для {md.get('home')} vs {md.get('away')}")
                
        except Exception as e:
            logger.error(f"❌ [SNAPSHOT FIX] Ошибка для {md.get('home')}: {e}")
            continue
    
    if saved_count > 0:
        logger.info(f"📸 [SNAPSHOT FIX] Всего сохранено снимков для {saved_count} матчей (пропущено: {skipped_count})")
    # ============================================================

    # ★★★ ДАЛЬШЕ ИДЕТ СТАРАЯ ЛОГИКА ДЛЯ BEST_BET ★★★
    for idx, md in enumerate(matches, 1):
        if idx % 10 == 0:
            send_telegram(f"💓 <b>ОБНОВЛЕНИЕ КЭФОВ</b> | {idx}/{total}")
        try:
            home = md.get('home')
            away = md.get('away')
            fid = md.get('fixture_id')
            league_name = md.get('league', '')
            best_bet = md.get('best_bet', {})
            bt = best_bet.get('type', 'under')
            new_odds = None
            bookmaker = '—'
            source = None
            md_source = md.get('source', '')

            logger.info(f"🔍 [{idx}] {home} vs {away} | fid={fid} | type={bt} | src={md_source}")

            fo = batch_odds.get(fid) if fid else None
            if not fo and fid:
                fo = football_api.get_match_odds(fid)

            # ★★★ ДУБЛЬ-ФИКС: Сохраняем снимки внутри цикла (если кэфы обновились) ★★★
            if fo and fid:
                try:
                    h_name = md.get('home', '')
                    a_name = md.get('away', '')
                    l_name = md.get('league', '')
                    
                    if fo.get('home_odds', 0) > 1.01:
                        storage.save_odds_snapshot(fid, '1X2', '1', fo['home_odds'], 'Fix', h_name, a_name, l_name)
                    if fo.get('draw_odds', 0) > 1.01:
                        storage.save_odds_snapshot(fid, '1X2', 'X', fo['draw_odds'], 'Fix', h_name, a_name, l_name)
                    if fo.get('away_odds', 0) > 1.01:
                        storage.save_odds_snapshot(fid, '1X2', '2', fo['away_odds'], 'Fix', h_name, a_name, l_name)
                except Exception as snap_err:
                    logger.error(f"Ошибка записи снимков для {fid}: {snap_err}")
            # ============================================================

            # Двойная проверка для VALUE
            if md_source == 'value' and fo and best_bet.get('ev', 0) > 80:
                try:
                    fresh = football_api.get_match_odds(fid)
                    if fresh:
                        for k in ['1x_odds', 'x2_odds', 'home_odds', 'away_odds']:
                            old_v = fo.get(k, 0)
                            new_v = fresh.get(k, 0)
                            if old_v > 0 and new_v > 0 and abs(old_v - new_v) > 0.3:
                                logger.warning(f"⚠️ Кэф устарел {k}: {old_v} → {new_v}")
                                fo = fresh
                                break
                except Exception as e:
                    logger.error(f"Двойная проверка: {e}")

            if fo and fo.get('best_odds', 0) > 0:
                bm_list = fo.get('all_bookmakers', {})
                
                # Фильтр TRUSTED BOOKMAKERS
                if bm_list:
                    trusted_bm_list = {
                        bm: data for bm, data in bm_list.items() 
                        if bm in TRUSTED_BOOKMAKERS
                    }
                    if not trusted_bm_list:
                        logger.warning(f"⏭️ Все БК ненадежные: {home} vs {away}")
                        updated.append(md)
                        continue
                    
                    if bt == 'X2': target = 'x2'
                    elif bt == '1X': target = '1x'
                    elif bt in ('П1', '1'): target = 'home'
                    elif bt in ('П2', '2'): target = 'away'
                    elif bt == 'draw': target = 'draw'
                    else: target = 'home'
                    
                    target_odds = {bm: data.get(target, 0)
                                   for bm, data in trusted_bm_list.items()
                                   if data.get(target, 0) > 0}
                    if target_odds:
                        best_bm = max(target_odds, key=target_odds.get)
                        best_odds_val = target_odds[best_bm]
                        avg_odds = sum(target_odds.values()) / len(target_odds)
                        anomaly_pct = ((best_odds_val / avg_odds) - 1) * 100 if avg_odds > 0 else 0
                        new_odds = best_odds_val
                        bookmaker = f"{best_bm} (+{anomaly_pct:.1f}%)"
                        source = 'Line Analysis'
                        if anomaly_pct > 5:
                            logger.info(f"🎯 АНОМАЛИЯ: {home} vs {away} | {best_bm} = {best_odds_val} (+{anomaly_pct:.1f}%)")
                            prob = best_bet.get('prob', 0) / 100
                            anomaly_bonus = min(anomaly_pct / 100, 0.03)
                            boosted = min(prob + anomaly_bonus, 0.95)
                            best_bet['prob'] = round(boosted * 100, 1)
                            best_bet['anomaly_bonus'] = round(anomaly_bonus * 100, 1)
                            
                            if boosted * best_odds_val - 1 > 0.50:
                                try:
                                    reverse_bet = '—'
                                    lbl = best_bet.get('label', '').upper()
                                    if 'X2' in lbl: reverse_bet = 'П1'
                                    elif '1X' in lbl: reverse_bet = 'П2'
                                    elif 'П1' in lbl: reverse_bet = 'П2'
                                    elif 'П2' in lbl: reverse_bet = 'П1'
                                    
                                    lab_file = os.path.join(DATA_DIR, 'lab_anomalies.jsonl')
                                    lab_record = {
                                        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                        'home': home, 'away': away, 'league': md.get('league', ''),
                                        'fixture_id': fid, 'original_bet': best_bet.get('label', ''),
                                        'reverse_bet': reverse_bet, 'odds': best_odds_val,
                                        'ev': round((boosted * best_odds_val - 1) * 100, 1),
                                        'prob': round(boosted * 100, 1), 'result': 'pending'
                                    }
                                    with _jsonl_lock:
                                        with open(lab_file, 'a', encoding='utf-8') as f:
                                            f.write(json.dumps(lab_record, ensure_ascii=False) + '\n')
                                except Exception as e:
                                    logger.error(f"Lab write error: {e}")
                
                if not new_odds:
                    # Fallback логика
                    if bt == 'X2' and fo.get('x2_odds', 0) > 0:
                        new_odds = fo['x2_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API (X2)'
                    elif bt == '1X' and fo.get('1x_odds', 0) > 0:
                        new_odds = fo['1x_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API (1X)'
                    elif bt in ('П1', '1') and fo.get('home_odds', 0) > 0:
                        new_odds = fo['home_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API'
                    elif bt in ('П2', '2') and fo.get('away_odds', 0) > 0:
                        new_odds = fo['away_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API'
                    elif bt == 'draw' and fo.get('draw_odds', 0) > 0:
                        new_odds = fo['draw_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API'
                    elif bt == 'under' and fo.get('under_odds', 0) > 0:
                        new_odds = fo['under_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API'
                    elif bt == 'over' and fo.get('over_odds', 0) > 0:
                        new_odds = fo['over_odds']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API'
                    elif bt == 'btts' and fo.get('btts_yes', 0) > 0:
                        new_odds = fo['btts_yes']; bookmaker = fo.get('bookmaker', 'Football API'); source = 'Football API'
                    else:
                        new_odds = fo.get('best_odds', 0)
                        if new_odds:
                            bookmaker = fo.get('bookmaker', 'Football API')
                            source = 'Football API'

            if new_odds and new_odds > 0:
                MIN_ODDS = getattr(Config, 'MIN_ODDS', 1.40)
                MAX_ODDS = getattr(Config, 'MAX_ODDS', 8.00)
                if new_odds < MIN_ODDS or new_odds > MAX_ODDS:
                    logger.info(f"⏭️ Кэф {new_odds} вне [{MIN_ODDS}, {MAX_ODDS}]")
                    updated.append(md)
                    continue
                prob_pct = best_bet.get('prob', 0)
                calibrated_pct = calibrate_prob(prob_pct, use_bucket=True)
                best_bet['prob_calibrated'] = calibrated_pct
                calibrated_prob = calibrated_pct / 100
                best_bet['odds'] = round(new_odds, 2)
                best_bet['ev'] = round((calibrated_prob * new_odds - 1) * 100, 1)
                best_bet['bookmaker'] = bookmaker
                best_bet['odds_source'] = source
                best_bet['odds_updated'] = True

                try:
                    bank = storage.load_bank()
                    kelly_stake = calculate_stake(
                        bank=bank,
                        prob_pct=calibrated_pct,
                        odds=new_odds,
                    )
                    src_key = md.get('source', '70_percent')
                    final_stake, clv_action, adjusted_prob = apply_clv_filter(
                        source=src_key,
                        base_stake=kelly_stake,
                        prob_pct=calibrated_pct,
                        odds=new_odds,
                        bank=bank,
                    )
                    if final_stake > 0:
                        best_bet['prob_calibrated'] = round(adjusted_prob, 1)
                        best_bet['clv_adjusted'] = True
                        best_bet['ev'] = round((adjusted_prob / 100 * new_odds - 1) * 100, 1)
                    best_bet['stake'] = final_stake if final_stake > 0 else kelly_stake
                    best_bet['clv_action'] = clv_action
                except Exception as e:
                    logger.error(f"Kelly/CLV recalc: {e}")

                md['best_bet'] = best_bet
                md['odds_updated'] = True
                updated.append(md)
            else:
                logger.warning(f"⏭️ Кэф не найден: {home} vs {away}")
                updated.append(md)
                continue
        except Exception as e:
            logger.error(f"Ошибка кэфов: {e}")
            continue
    return updated


# ============================================================
# ПОИСК МАТЧЕЙ + ФАКТОРЫ (Без изменений)
# ============================================================
def get_matches_with_factors():
    all_matches = []
    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    if now_msk.hour >= 22:
        today = (now_msk + timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"🌙 Позднее время ({now_msk.strftime('%H:%M')} МСК) — ищем матчи на {today} (завтра)")
    else:
        today = now_msk.strftime('%Y-%m-%d')
    all_leagues = list(set(Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])))
    total_leagues = len(all_leagues)
    logger.info(f"🔍 Поиск: {today}, лиг: {total_leagues}")
    send_telegram(
        f"🔎 <b>СТАРТ ПОИСКА</b>\n"
        f"📅 {today}\n📊 Лиг: {total_leagues}\n⏱️ 5-10 минут"
    )
    start_time = time.time()
    processed = 0
    found_total = 0
    progress_step = 25
    seen_fixtures = set()

    for league_id in all_leagues:
        try:
            matches = football_api.get_matches(league_id, today)
            league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
            processed += 1

            batch_odds = {}
            batch_preds = {}
            if matches:
                try:
                    batch_odds = football_api.get_odds_batch_for_league(league_id, today)
                except Exception as e:
                    logger.debug(f"batch odds {league_id}: {e}")
                try:
                    batch_preds = football_api.get_predictions_batch_for_league(league_id, today)
                except Exception as e:
                    logger.debug(f"batch preds {league_id}: {e}")

            if matches:
                new_matches = 0
                for m in matches:
                    if not isinstance(m, dict): continue
                    fixture = m.get('fixture')
                    if not fixture or not isinstance(fixture, dict): continue
                    if fixture.get('status', {}).get('short') != 'NS': continue
                    mid = fixture.get('id')
                    if not mid or mid in seen_fixtures: continue
                    seen_fixtures.add(mid)
                    teams = m.get('teams', {})
                    hid = teams.get('home', {}).get('id')
                    aid = teams.get('away', {}).get('id')
                    if not hid or not aid: continue

                    m['factors'] = {
                        'home_form': football_api.get_form(hid),
                        'away_form': football_api.get_form(aid),
                        'home_injuries_list': football_api.get_injuries(hid),
                        'away_injuries_list': football_api.get_injuries(aid),
                        'home_id': hid, 'away_id': aid,
                        'referee': fixture.get('referee'),
                    }

                    weather = None
                    venue = fixture.get('venue', {})
                    city = venue.get('city') if isinstance(venue, dict) else None
                    if city and Config.WEATHER_ENABLED:
                        weather = get_weather_for_city_enhanced(city)
                    m['weather'] = weather
                    if weather:
                        m['weather_reason'] = (f"🌤️ {weather['desc']}, {weather['temp']}°C, "
                                                f"ветер {weather['wind']} м/с, "
                                                f"дождь {weather['rain']} мм")
                    else:
                        m['weather_reason'] = "🌤️ Нет данных"

                    if mid in batch_odds:
                        m['_preloaded_odds'] = batch_odds[mid]
                    if mid in batch_preds:
                        m['_preloaded_preds'] = batch_preds[mid]

                    ld = m.get('league', {})
                    if isinstance(ld, dict):
                        ld['name'] = league_name
                    all_matches.append(m)
                    new_matches += 1
                if new_matches > 0:
                    found_total += new_matches

            if processed % progress_step == 0:
                elapsed = (time.time() - start_time) / 60
                remaining = total_leagues - processed
                eta = (elapsed / processed) * remaining if processed > 0 else 0
                send_telegram(f"💓 <b>HEARTBEAT</b> | {processed}/{total_leagues}\n"
                              f"🎯 Матчей: {found_total}\n⏱️ Осталось: ~{eta:.1f} мин")
        except Exception as e:
            logger.error(f"❌ {league_id}: {e}")
        time.sleep(0.01)

    elapsed_total = (time.time() - start_time) / 60
    send_telegram(f"✅ <b>ПОИСК ЗАВЕРШЁН</b>\n"
                  f"📊 Лиг: {processed}/{total_leagues}\n"
                  f"🎯 Матчей: {found_total}\n"
                  f"⏱️ {elapsed_total:.1f} мин")
    logger.info(f"📊 Найдено матчей: {len(all_matches)}")
    return all_matches


# ============================================================
# ★ ПОГОДНЫЙ ФИЛЬТР (Без изменений)
# ============================================================
def check_weather_skip(weather):
    """
    Проверяет, нужно ли пропустить матч из-за погоды.
    Возвращает: (skip: bool, reason: str, xg_multiplier: float)
    """
    if not weather:
        return False, '', 1.0

    rain = weather.get('rain', 0) or 0
    wind = weather.get('wind', 0) or 0
    temp = weather.get('temp', 20) or 20
    desc = (weather.get('desc', '') or '').lower()

    heavy_pen = getattr(Config, 'WEATHER_HEAVY_RAIN_XG_PENALTY', 0.80)
    if rain > getattr(Config, 'WEATHER_SKIP_RAIN_MM', 4.0):
        return True, f'🌧️ Дождь {rain:.1f}мм', heavy_pen
    if wind > getattr(Config, 'WEATHER_SKIP_WIND_MS', 15.0):
        return True, f'💨 Ветер {wind:.0f}м/с', 0.85
    if getattr(Config, 'WEATHER_SKIP_SNOW', True) and ('snow' in desc or 'снег' in desc):
        return True, f'❄️ Снег', 0.75
    if temp < getattr(Config, 'WEATHER_SKIP_TEMP_MIN', -10):
        return True, f'🥶 {temp:.0f}°C', 0.90
    if temp > getattr(Config, 'WEATHER_SKIP_TEMP_MAX', 40):
        return True, f'🔥 {temp:.0f}°C', 0.90

    xg_mult = 1.0
    if rain > 2.0:
        xg_mult *= getattr(Config, 'WEATHER_RAIN_XG_PENALTY', 0.90)
    elif rain > 0.5:
        xg_mult *= 0.96
    if wind > 10:
        xg_mult *= getattr(Config, 'WEATHER_WIND_XG_PENALTY', 0.92)
    elif wind > 7:
        xg_mult *= 0.97
    if temp > 35:
        xg_mult *= getattr(Config, 'WEATHER_HEAT_XG_PENALTY', 0.95)
    elif temp < -5:
        xg_mult *= getattr(Config, 'WEATHER_COLD_XG_PENALTY', 0.93)

    return False, '', round(xg_mult, 3)
