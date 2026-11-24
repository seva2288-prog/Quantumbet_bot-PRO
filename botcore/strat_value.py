# ============================================================
# botcore/strat_value.py — Стратегии: VALUE, BTTS, STATS
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

__all__ = [
    'find_value_matches',
    'find_btts_matches',
    '_count_scoring_matches',
    '_calc_h2h_btts_pct',
    'find_stats_matches',
]


# ============================================================
# ★ ПОТОК 3: VALUE (КРИТИЧЕСКИЙ ФИКС EV)
# ============================================================
@timing_decorator()
def find_value_matches(matches, max_bets=None):
    """VALUE-поток."""
    bank = storage.load_bank()
    VALUE_MIN_ODDS = getattr(Config, 'VALUE_MIN_ODDS', 2.50)
    VALUE_MIN_EV = getattr(Config, 'VALUE_MIN_EV', 25)
    VALUE_MIN_PROB = getattr(Config, 'VALUE_MIN_PROB', 45) # Снижено с 50, т.к. на кэфах 2.5+ редко бывает >50%
    VALUE_MIN_XG_DIFF = getattr(Config, 'VALUE_MIN_XG_DIFF', 0.3)
    if max_bets is None:
        max_bets = getattr(Config, 'VALUE_MAX_RESULTS', 5)
    VALUE_MAX_RESULTS = max_bets

    logger.info(f"💎 [VALUE] Поиск: кэф>={VALUE_MIN_ODDS}, EV>={VALUE_MIN_EV}%, Prob>={VALUE_MIN_PROB}%")

    value_candidates = []
    blacklist = getattr(Config, 'BLACKLIST_LEAGUES', [])
    clv_skipped = 0
    prob_filtered = 0
    odds_fallback = 0

    for match in matches:
        if not match or not isinstance(match, dict): continue
        try:
            fixture = match.get('fixture')
            teams = match.get('teams')
            if not fixture or not teams: continue
            fid = fixture.get('id')
            ht = teams.get('home', {}); at = teams.get('away', {})
            home = ht.get('name', 'Unknown'); away = at.get('name', 'Unknown')
            ld = match.get('league', {})
            league_name = ld.get('name', 'Unknown')
            league_id = ld.get('id')
            if any(bad in league_name.lower() for bad in blacklist): continue
            match_time = parse_match_time_to_msk(fixture.get('date', ''))

            factors = match.get('factors', {}) or {}
            hfd = factors.get('home_form') or football_api.get_form(ht.get('id'))
            afd = factors.get('away_form') or football_api.get_form(at.get('id'))
            home_form = hfd.get('form', '') if hfd else ''
            away_form = afd.get('form', '') if afd else ''
            hga = hfd.get('goals_avg', 1.2) if hfd else 1.2
            aga = afd.get('goals_avg', 1.0) if afd else 1.0
            hca = hfd.get('conceded_avg', 1.0) if hfd else 1.0
            aca = afd.get('conceded_avg', 1.2) if afd else 1.2
            home_xg = (hga + aca) / 2   # забивает хозяин vs пропускает гость
            away_xg = (aga + hca) / 2
            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            total_xg = home_xg + away_xg
            xg_diff = abs(home_xg - away_xg)

            if xg_diff < VALUE_MIN_XG_DIFF:
                continue

            standings = football_api.get_standings(league_id) if league_id else None
            hp = standings.get(home, {}).get('position', 99) if standings else 99
            ap = standings.get(away, {}).get('position', 99) if standings else 99

            h2h = football_api.get_head_to_head(home, away)
            api_predictions = match.get('_preloaded_preds')
            if not api_predictions and fid:
                api_predictions = football_api.get_predictions(fid)
            probs = ensemble_probability(home_xg, away_xg, home_form, away_form,
                                          h2h, api_predictions=api_predictions)

            fo = match.get('_preloaded_odds')
            if not fo and fid:
                fo = football_api.get_match_odds(fid)

            if not fo and odds_api.should_use_as_fallback():
                fo = odds_api.get_odds_for_match(home, away, league_name)
                if fo:
                    logger.info(f"🔄 Odds API fallback (VALUE): {home} vs {away}")
                    odds_fallback += 1

            if not fo:
                continue

            bm_list = fo.get('all_bookmakers', {})
            if bm_list and len(bm_list) >= 2:
                skip_value = False
                skipped_mkt = None
                skipped_max = 0
                skipped_avg = 0
                for mkt_key in ['x2', '1x', 'home', 'away', 'draw']:
                    vals = [b.get(mkt_key, 0) for b in bm_list.values() if b.get(mkt_key, 0) > 1.01]
                    if len(vals) >= 2:
                        v_max = max(vals)
                        v_avg = sum(vals) / len(vals)
                        if v_max - v_avg > 1.5 or v_max / v_avg > 2.5:
                            logger.warning(
                                f"⏭️ VALUE ANOMALY SKIP: {home} vs {away} | "
                                f"{mkt_key}: max={v_max} avg={v_avg:.2f} (diff={v_max - v_avg:.2f})"
                            )
                            skip_value = True
                            skipped_mkt = mkt_key
                            skipped_max = v_max
                            skipped_avg = v_avg
                            break
                if skip_value:
                    try:
                        sel_map = {
                            'x2': 'X2', '1x': '1X',
                            'home': 'П1', 'away': 'П2', 'draw': 'X'
                        }
                        rec = {
                            'ts': datetime.now().isoformat(),
                            'home': home, 'away': away,
                            'fixture_id': fid,
                            'league': league_name,
                            'bet_type': 'VALUE',
                            'selection': sel_map.get(skipped_mkt, ''),
                            'best_odds': skipped_max,
                            'avg_odds': round(skipped_avg, 2),
                            'diff': round(skipped_max - skipped_avg, 2),
                            'anomaly_pct': round((skipped_max / skipped_avg - 1) * 100, 1) if skipped_avg > 0 else 0,
                            'source': 'value',
                            'result': 'pending',
                        }
                        storage.add_anomaly(rec)
                    except Exception as e:
                        logger.error(f"anomaly log: {e}")
                    continue

            def _compute_value(model_prob, odds):
                if model_prob <= 0 or odds <= 1.01:
                    return None
                model_prob_pct = model_prob * 100
                calibrated_pct = calibrate_prob(model_prob_pct, use_bucket=True)
                if calibrated_pct > getattr(Config, 'VALUE_MAX_PROB', 80):
                    return None
                market_prob = 1.0 / odds
                ratio = (calibrated_pct / 100) / market_prob if market_prob > 0 else 0
                if ratio > getattr(Config, 'VALUE_MAX_RATIO', 2.2):
                    return None
                
                # ★ КРИТИЧЕСКИЙ ФИКС: Считаем EV от нашей вероятности, а не от blended
                ev = (calibrated_pct / 100 * odds - 1) * 100
                
                # Фильтр: если букмекер оценивает вероятность выше, чем мы - это не валуй
                if (calibrated_pct / 100) < market_prob:
                    return None
                    
                return (ev, calibrated_pct / 100, calibrated_pct)

            candidates_bc = []

            p_1x = probs.get('1X', 0)
            odds_1x = fo.get('1x_odds', 0) or 0
            if odds_1x >= VALUE_MIN_ODDS:
                res = _compute_value(p_1x, odds_1x)
                if res:
                    ev, bp, cal = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': '1X', 'label': '1X 💎',
                            'prob': round(bp * 100, 1),
                            'prob_calibrated': round(cal, 1),
                            'model_prob': round(p_1x * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_1x,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            p_x2 = probs.get('X2', 0)
            odds_x2 = fo.get('x2_odds', 0) or 0
            if odds_x2 >= VALUE_MIN_ODDS:
                res = _compute_value(p_x2, odds_x2)
                if res:
                    ev, bp, cal = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': 'X2', 'label': 'X2 💎',
                            'prob': round(bp * 100, 1),
                            'prob_calibrated': round(cal, 1),
                            'model_prob': round(p_x2 * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_x2,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            p_home = probs.get('home_win', 0)
            odds_home = fo.get('home_odds', 0) or 0
            if odds_home >= VALUE_MIN_ODDS:
                res = _compute_value(p_home, odds_home)
                if res:
                    ev, bp, cal = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': 'П1', 'label': 'П1 💎',
                            'prob': round(bp * 100, 1),
                            'prob_calibrated': round(cal, 1),
                            'model_prob': round(p_home * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_home,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            p_away = probs.get('away_win', 0)
            odds_away = fo.get('away_odds', 0) or 0
            if odds_away >= VALUE_MIN_ODDS:
                res = _compute_value(p_away, odds_away)
                if res:
                    ev, bp, cal = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': 'П2', 'label': 'П2 💎',
                            'prob': round(bp * 100, 1),
                            'prob_calibrated': round(cal, 1),
                            'model_prob': round(p_away * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_away,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            if not candidates_bc:
                continue

            candidates_bc.sort(key=lambda x: x['ev'], reverse=True)
            best_bet = candidates_bc[0]

            if best_bet.get('prob', 0) > PROB_MAX_70:
                prob_filtered += 1
                continue

            prob_for_kelly = best_bet.get('prob_calibrated', best_bet.get('prob', 0))
            kelly_stake = calculate_stake(
                bank=bank,
                prob_pct=prob_for_kelly,
                odds=best_bet.get('odds', 1.85),
            )
            final_stake, clv_action, adjusted_prob = apply_clv_filter(
                source='value',
                base_stake=kelly_stake,
                prob_pct=prob_for_kelly,
                odds=best_bet.get('odds', 1.85),
                bank=bank,
            )
            if final_stake <= 0:
                clv_skipped += 1
                continue

            best_bet['prob_calibrated'] = round(adjusted_prob, 1)
            best_bet['clv_adjusted'] = True
            if best_bet.get('odds', 0) > 1.01:
                best_bet['ev'] = round(
                    (adjusted_prob / 100 * best_bet['odds'] - 1) * 100, 1
                )

            if best_bet['ev'] < VALUE_MIN_EV:
                continue

            for b in candidates_bc:
                b['stake'] = final_stake
                b['clv_action'] = clv_action
                b['prob_calibrated'] = round(adjusted_prob, 1)
            best_bet['stake'] = final_stake
            best_bet['clv_action'] = clv_action

            country_name, country_flag = _get_country_flag(league_id)

            value_candidates.append({
                "home": home, "away": away, "league": league_name,
                "country": country_name, "country_flag": country_flag,
                "fixture_id": fid, "match_time": match_time,
                "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
                "total_xg": round(total_xg, 2),
                "home_form": home_form, "away_form": away_form,
                "standings": {"home_position": hp, "away_position": ap},
                "bets": candidates_bc,
                "best_bet": best_bet,
                "source": "value",
                "weather_reason": match.get('weather_reason', ''),
                "_preloaded_odds": fo,
            })

            logger.info(
                f"💎 VALUE: {home} vs {away} | {best_bet['label']} @ "
                f"{best_bet['odds']} | EV: {best_bet['ev']}% | "
                f"Prob: {best_bet['prob']}% (cal: {best_bet.get('prob_calibrated')}%) | "
                f"Stake: ${best_bet['stake']} ({clv_action})"
            )

        except Exception as e:
            logger.error(f"❌ [VALUE] {e}")
            continue

    value_candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top = value_candidates[:VALUE_MAX_RESULTS]
    logger.info(
        f"💎 [VALUE] Найдено: {len(value_candidates)}, взято: {len(top)}, "
        f"CLV-skip: {clv_skipped}, Prob-filter: {prob_filtered}, "
        f"Odds-fallback: {odds_fallback}"
    )
    return top


# ============================================================
# ★ ПОТОК 4: BTTS (Без изменений)
# ============================================================
@timing_decorator()
def find_btts_matches(matches):
    bank = storage.load_bank()
    BTTS_ENABLED = getattr(Config, 'BTTS_ENABLED', True)
    if not BTTS_ENABLED:
        logger.info("⏭️ [BTTS] Отключено в конфиге")
        return []

    MAX_BETS = getattr(Config, 'BTTS_MAX_BETS', 3)
    MIN_ODDS = getattr(Config, 'BTTS_MIN_ODDS', 1.60)
    MAX_ODDS = getattr(Config, 'BTTS_MAX_ODDS', 2.20)
    MIN_EV = getattr(Config, 'BTTS_MIN_EV', 8)
    MIN_PROB = getattr(Config, 'BTTS_MIN_PROB', 50)
    MIN_XG_EACH = getattr(Config, 'BTTS_MIN_XG_EACH', 0.9)
    MIN_TOTAL_XG = getattr(Config, 'BTTS_MIN_TOTAL_XG', 2.0)

    LEAGUE_WHITELIST = getattr(Config, 'BTTS_LEAGUE_WHITELIST', [])
    LEAGUE_BLACKLIST = getattr(Config, 'BTTS_LEAGUE_BLACKLIST', [])
    LEAGUE_BONUS = getattr(Config, 'BTTS_LEAGUE_BONUS', 5)
    MAX_LEAGUE_BETS = getattr(Config, 'BTTS_MAX_LEAGUE_BETS', 1)

    FORM_FILTER = getattr(Config, 'BTTS_FORM_FILTER', True)
    FORM_MIN_SCORING = getattr(Config, 'BTTS_FORM_MIN_SCORING', 3)

    H2H_FILTER = getattr(Config, 'BTTS_H2H_FILTER', False)
    H2H_MIN_MATCHES = getattr(Config, 'BTTS_H2H_MIN_MATCHES', 4)
    H2H_MIN_PCT = getattr(Config, 'BTTS_H2H_MIN_PCT', 60)

    INCLUDE_INTERNATIONAL = getattr(Config, 'BTTS_INCLUDE_INTERNATIONAL', False)

    logger.info("🔍 [BTTS v22.9] Поиск 'Обе Забьют' + калибровка + CLV...")
    stats = {
        'found': 0,
        'intl_skipped': 0,
        'league_blacklist': 0,
        'league_limit': 0,
        'form_skipped': 0,
        'h2h_skipped': 0,
        'xg_skipped': 0,
        'clv_skipped': 0,
        'league_bonus': 0,
        'no_odds': 0,
        'prob_filtered': 0,
    }

    candidates = []
    league_bet_count = {}
    seen_keys = set()

    for match in matches:
        if len(candidates) >= MAX_BETS: break
        if not match or not isinstance(match, dict): continue
        try:
            fixture = match.get('fixture')
            teams = match.get('teams')
            if not fixture or not teams: continue
            fid = fixture.get('id')
            ht = teams.get('home', {}); at = teams.get('away', {})
            home = ht.get('name', 'Unknown'); away = at.get('name', 'Unknown')
            key = f"{home}_{away}"
            if key in seen_keys: continue
            seen_keys.add(key)

            ld = match.get('league', {})
            league_name = ld.get('name', 'Unknown')
            league_id = ld.get('id')
            match_time = parse_match_time_to_msk(fixture.get('date', ''))

            if not INCLUDE_INTERNATIONAL:
                if _is_international_league(league_id, league_name):
                    stats['intl_skipped'] += 1
                    continue

            if Config.is_btts_league_blacklisted(league_name):
                stats['league_blacklist'] += 1
                continue

            cur_bets = league_bet_count.get(league_name, 0)
            if cur_bets >= MAX_LEAGUE_BETS:
                stats['league_limit'] += 1
                continue

            factors = match.get('factors', {}) or {}
            hfd = factors.get('home_form') or football_api.get_form(ht.get('id'))
            afd = factors.get('away_form') or football_api.get_form(at.get('id'))
            home_form = hfd.get('form', '') if hfd else ''
            away_form = afd.get('form', '') if afd else ''

            hga = hfd.get('goals_avg', 1.2) if hfd else 1.2
            aga = afd.get('goals_avg', 1.0) if afd else 1.0
            hca = hfd.get('conceded_avg', 1.0) if hfd else 1.0
            aca = afd.get('conceded_avg', 1.2) if afd else 1.2

            home_xg = (hga + aca) / 2
            away_xg = (aga + hca) / 2

            if _is_international_league(league_id, league_name):
                home_adv = 1.03
            else:
                home_adv = HOME_ADVANTAGE.get(league_name, 1.08)
            home_xg *= home_adv
            away_xg /= home_adv

            total_xg = home_xg + away_xg

            if home_xg < MIN_XG_EACH or away_xg < MIN_XG_EACH:
                stats['xg_skipped'] += 1
                continue
            if total_xg < MIN_TOTAL_XG:
                stats['xg_skipped'] += 1
                continue

            if FORM_FILTER:
                home_scoring = _count_scoring_matches(home_form)
                away_scoring = _count_scoring_matches(away_form)
                if home_scoring < FORM_MIN_SCORING or away_scoring < FORM_MIN_SCORING:
                    stats['form_skipped'] += 1
                    continue

            h2h = None
            if H2H_FILTER:
                h2h = football_api.get_head_to_head(home, away)
                if h2h and h2h.get('total_matches', 0) >= H2H_MIN_MATCHES:
                    h2h_btts_pct = _calc_h2h_btts_pct(h2h)
                    if h2h_btts_pct < H2H_MIN_PCT:
                        stats['h2h_skipped'] += 1
                        continue

            h2h_patterns = analyze_h2h_patterns(h2h, home)
            if h2h_patterns.get("btts_pattern"):
                logger.info(f"H2H BTTS: {home} vs {away}")

            probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h)
            p_btts = probs.get('btts', 0)
            if p_btts * 100 < MIN_PROB:
                continue

            p_btts_pct = p_btts * 100
            if p_btts_pct > PROB_MAX_70:
                stats['prob_filtered'] += 1
                continue

            fo = match.get('_preloaded_odds') or {}
            btts_odds = fo.get('btts_yes', 0) or 0
            if btts_odds <= 1.01 and fid:
                fo_fresh = football_api.get_match_odds(fid)
                if fo_fresh:
                    btts_odds = fo_fresh.get('btts_yes', 0) or 0

            if btts_odds <= 1.01:
                stats['no_odds'] += 1
                continue

            if btts_odds < MIN_ODDS or btts_odds > MAX_ODDS:
                continue

            calibrated_p = calibrate_prob(p_btts_pct, use_bucket=True)
            ev_btts = (calibrated_p / 100 * btts_odds - 1) * 100

            is_whitelisted = Config.is_btts_league_whitelisted(league_name)
            if is_whitelisted:
                ev_btts += LEAGUE_BONUS

            if ev_btts < MIN_EV:
                continue

            kelly_stake = calculate_stake(
                bank=bank,
                prob_pct=calibrated_p,
                odds=btts_odds,
            )
            final_stake, clv_action, adjusted_prob = apply_clv_filter(
                source='btts',
                base_stake=kelly_stake,
                prob_pct=calibrated_p,
                odds=btts_odds,
                bank=bank,
            )
            if final_stake <= 0:
                stats['clv_skipped'] += 1
                continue
            if is_whitelisted:
                stats['league_bonus'] += 1

            calibrated_p = round(adjusted_prob, 1)
            ev_btts = (calibrated_p / 100 * btts_odds - 1) * 100
            if is_whitelisted:
                ev_btts += LEAGUE_BONUS
            if ev_btts < MIN_EV:
                continue

            country_name, country_flag = _get_country_flag(league_id)

            best_bet = {
                'type': 'btts',
                'label': 'ОБЗ 🔥' if is_whitelisted else 'ОБЗ',
                'prob': round(p_btts_pct, 1),
                'prob_calibrated': calibrated_p,
                'ev': round(ev_btts, 1),
                'odds': btts_odds,
                'stake': final_stake,
                'clv_action': clv_action,
                'clv_adjusted': True,
                'bookmaker': fo.get('bookmaker', '—'),
                'league_bonus': is_whitelisted,
                'odds_updated': True,
            }

            candidates.append({
                "home": home, "away": away, "league": league_name,
                "country": country_name, "country_flag": country_flag,
                "fixture_id": fid, "match_time": match_time,
                "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
                "total_xg": round(total_xg, 2),
                "home_form": home_form, "away_form": away_form,
                "standings": {},
                "bets": [best_bet],
                "best_bet": best_bet,
                "source": "btts",
                "weather_reason": match.get('weather_reason', ''),
                "_preloaded_odds": fo,
            })
            stats['found'] += 1
            league_bet_count[league_name] = cur_bets + 1

        except Exception as e:
            logger.error(f"❌ [BTTS] {e}")
            continue

    candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top = candidates[:MAX_BETS]

    logger.info(
        f"📊 [BTTS] Найдено: {len(candidates)}, взято: {len(top)} | "
        f"clv-skip: {stats['clv_skipped']}, prob-filter: {stats['prob_filtered']}"
    )
    return top


def _count_scoring_matches(form_string):
    if not form_string:
        return 0
    return form_string.count('W') + form_string.count('D')


def _calc_h2h_btts_pct(h2h_data):
    if not h2h_data or not h2h_data.get('matches'):
        return 0
    matches = h2h_data['matches']
    if not matches:
        return 0
    btts_count = 0
    for m in matches:
        if m.get('home_score', 0) > 0 and m.get('away_score', 0) > 0:
            btts_count += 1
    return round(btts_count / len(matches) * 100, 1)


# ============================================================
# ★ ПОТОК 6: СТАТИСТИКА (Углы и Карточки)
# ============================================================
@timing_decorator()
def find_stats_matches(matches):
    bank = storage.load_bank()
    if not getattr(Config, 'STATS_ENABLED', True):
        return []

    MIN_EV = getattr(Config, 'STATS_MIN_EV', 12)
    MIN_PROB = getattr(Config, 'STATS_MIN_PROB', 55)
    CORNERS_MIN_AVG = getattr(Config, 'STATS_CORNERS_MIN_AVG', 8.5)
    CARDS_MIN_AVG = getattr(Config, 'STATS_CARDS_MIN_AVG', 3.5)
    
    logger.info("📊 [STATS] Поиск ставок на угловые и карточки (реальные данные)...")
    candidates = []

    for match in matches:
        try:
            fixture = match.get('fixture')
            teams = match.get('teams')
            if not fixture or not teams: continue
            
            fid = fixture.get('id')
            home = teams.get('home', {}).get('name', 'Unknown')
            away = teams.get('away', {}).get('name', 'Unknown')
            hid = teams.get('home', {}).get('id')
            aid = teams.get('away', {}).get('id')
            league_name = match.get('league', {}).get('name', 'Unknown')

            # Получаем реальную статистику команд
            home_stats = football_api.get_team_stats_avg(hid)
            away_stats = football_api.get_team_stats_avg(aid)

            if not home_stats or not away_stats:
                continue

            # Складываем средние показатели хозяев и гостей
            avg_corners = home_stats['corners_avg'] + away_stats['corners_avg']
            avg_cards = home_stats['cards_avg'] + away_stats['cards_avg']

            if avg_corners == 0 and avg_cards == 0:
                continue

            fo = match.get('_preloaded_odds') or {}
            bets = []
            
            # Достаем кэфы из API-Sports (если есть)
            corners_over = fo.get('corners_over_9_5', 0) or 0
            corners_under = fo.get('corners_under_9_5', 0) or 0
            cards_over = fo.get('cards_over_4_5', 0) or 0
            cards_under = fo.get('cards_under_4_5', 0) or 0

            # Если кэфов в API-Sports нет, пробуем The Odds API (лимитировано)
            if corners_over == 0 and corners_under == 0 and league_name in TOP_LEAGUES:
                corners_data = odds_api.get_stats_odds_for_match(home, away, league_name, 'totals_corners')
                if corners_data:
                    corners_over = corners_data.get('over_odds', 0)
                    corners_under = corners_data.get('under_odds', 0)

            if cards_over == 0 and cards_under == 0 and league_name in TOP_LEAGUES:
                cards_data = odds_api.get_stats_odds_for_match(home, away, league_name, 'totals_cards')
                if cards_data:
                    cards_over = cards_data.get('over_odds', 0)
                    cards_under = cards_data.get('under_odds', 0)

            # --- Логика для УГЛОВЫХ ---
            if avg_corners >= CORNERS_MIN_AVG and corners_over > 0:
                prob = 0.55
                ev = (prob * corners_over - 1) * 100
                if ev >= MIN_EV and corners_over <= 2.20:
                    bets.append({
                        'type': 'corners_over', 
                        'label': f'ТБ 9.5 Угловых 📐 ({avg_corners})',
                        'prob': prob * 100, 'ev': round(ev, 1),
                        'odds': corners_over, 'stake': 0,
                        'odds_updated': True  # ★ ВАЖНО: чтобы не было TEMPLATE SKIP
                    })
            elif avg_corners < CORNERS_MIN_AVG and corners_under > 0:
                prob = 0.55
                ev = (prob * corners_under - 1) * 100
                if ev >= MIN_EV and corners_under <= 2.20:
                    bets.append({
                        'type': 'corners_under', 
                        'label': f'ТМ 9.5 Угловых 📐 ({avg_corners})',
                        'prob': prob * 100, 'ev': round(ev, 1),
                        'odds': corners_under, 'stake': 0,
                        'odds_updated': True
                    })

            # --- Логика для КАРТОЧЕК ---
            if avg_cards >= CARDS_MIN_AVG and cards_over > 0:
                prob = 0.55
                ev = (prob * cards_over - 1) * 100
                if ev >= MIN_EV and cards_over <= 2.10:
                    bets.append({
                        'type': 'cards_over', 
                        'label': f'ТБ 4.5 Карточек 🟨 ({avg_cards})',
                        'prob': prob * 100, 'ev': round(ev, 1),
                        'odds': cards_over, 'stake': 0,
                        'odds_updated': True
                    })
            elif avg_cards < CARDS_MIN_AVG and cards_under > 0:
                prob = 0.55
                ev = (prob * cards_under - 1) * 100
                if ev >= MIN_EV and cards_under <= 2.10:
                    bets.append({
                        'type': 'cards_under', 
                        'label': f'ТМ 4.5 Карточек 🟨 ({avg_cards})',
                        'prob': prob * 100, 'ev': round(ev, 1),
                        'odds': cards_under, 'stake': 0,
                        'odds_updated': True
                    })

            if bets:
                bets.sort(key=lambda x: x['ev'], reverse=True)
                best_bet = bets[0]
                kelly_stake = calculate_stake(bank, best_bet['prob'], best_bet['odds'])
                final_stake, _, _ = apply_clv_filter('stats', kelly_stake, best_bet['prob'], best_bet['odds'], bank)
                
                if final_stake > 0:
                    best_bet['stake'] = final_stake
                    candidates.append({
                        "home": home, "away": away, "league": league_name,
                        "fixture_id": fid, "match_time": parse_match_time_to_msk(fixture.get('date', '')),
                        "home_xg": 0, "away_xg": 0, "total_xg": 0,
                        "home_form": '', "away_form": '',
                        "bets": bets, "best_bet": best_bet,
                        "source": "stats", "weather_reason": "",
                        "_preloaded_odds": fo,
                    })
                    logger.info(f"📐 STATS: {home} vs {away} | {best_bet['label']} @ {best_bet['odds']} | EV: {best_bet['ev']}%")
        except Exception as e:
            logger.error(f"❌ [STATS] {e}")
            continue

    candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    logger.info(f"📊 [STATS] Найдено: {len(candidates)}")
    return candidates
