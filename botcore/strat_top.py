# ============================================================
# botcore/strat_top.py — Стратегии: TOP, TM2.5
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

__all__ = [
    'find_top_matches',
    'find_tm25_matches',
    '_form_is_under',
    '_calculate_tm25_stake',
]


# ============================================================
# ★ ПОТОК 1: 70%+ (с CLV prob-boost)
# ============================================================
@timing_decorator()
def find_top_matches(matches):
    bank = storage.load_bank()
    max_bets = getattr(Config, 'MAX_BETS_PER_RUN', 30)
    total_matches = len(matches)
    logger.info(f"🔍 [70%+] Анализ {total_matches} матчей... (bank=${bank:.2f})")
    blacklist = getattr(Config, 'BLACKLIST_LEAGUES', [])
    best_matches = []
    bet_type_count = {}
    league_count = {}
    x2_saved_count = 0
    cheap_fav_skipped = 0
    prob_filtered = 0

    X2_ENABLED = getattr(Config, 'X2_ENABLED', False)
    X2_MIN_POSITION_DIFF = getattr(Config, 'X2_MIN_POSITION_DIFF', 3)
    X2_MAX_POSITION = getattr(Config, 'X2_MAX_POSITION', 20)
    X2_MIN_EV = getattr(Config, 'X2_MIN_EV', 10)
    X2_MIN_PROB = getattr(Config, 'X2_MIN_PROB', 58)
    X2_BOTH_SIDES = getattr(Config, 'X2_BOTH_SIDES', False)
    MIN_ODDS_1X = getattr(Config, 'MIN_ODDS_1X', 1.70)

    for match_idx, match in enumerate(matches):
        if not match or not isinstance(match, dict): continue
        if (match_idx + 1) % 30 == 0:
            send_telegram(f"💓 <b>АНАЛИЗ 70%+</b> | {match_idx + 1}/{total_matches}\n"
                          f"🎯 Кандидатов: {len(best_matches)} | X2: {x2_saved_count} | "
                          f"Skip-1X: {cheap_fav_skipped} | Prob-filter: {prob_filtered}")
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

            is_international = _is_international_league(league_id, league_name)

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
            h_inj = len(factors.get('home_injuries_list', []))
            a_inj = len(factors.get('away_injuries_list', []))
            if h_inj > 3: home_xg *= 0.8
            if a_inj > 3: away_xg *= 0.8

            if is_international:
                home_adv = 1.03
            else:
                home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            total_xg = home_xg + away_xg

            skip, reason, xg_mult = check_weather_skip(match.get('weather'))
            if skip:
                logger.info(f"⏭️ WEATHER SKIP: {home} vs {away} | {reason}")
                continue
            if xg_mult != 1.0:
                total_xg *= xg_mult
                home_xg *= xg_mult
                away_xg *= xg_mult

            XG_MIN = getattr(Config, 'XG_MIN_70', 1.2)
            XG_MAX = getattr(Config, 'XG_MAX_70', 3.8)
            POS_MAX = getattr(Config, 'POSITION_MAX_70', 18)
            if total_xg < XG_MIN or total_xg > XG_MAX: continue

            standings = football_api.get_standings(league_id) if league_id else None
            hp = standings.get(home, {}).get('position', 99) if standings else 99
            ap = standings.get(away, {}).get('position', 99) if standings else 99

            if is_international:
                hm = am = 'international'
            else:
                hm = get_motivation(hp); am = get_motivation(ap)
                if getattr(Config, 'SKIP_MID_TABLE_70', False) and hm == 'mid_table' and am == 'mid_table':
                    continue
            _is_cup_or_intl = (
                league_id in getattr(Config, 'CUP_LEAGUES', []) or
                is_international or
                (hp == 99 and ap == 99)
            )
            if not _is_cup_or_intl:
                if hp > POS_MAX or ap > POS_MAX: continue
                if league_name in TOP_TEAMS_LEAGUES and hp <= 6 and ap <= 6: continue

            h2h = football_api.get_head_to_head(home, away)
            api_predictions = match.get('_preloaded_preds')
            if not api_predictions and fid:
                api_predictions = football_api.get_predictions(fid)

            probs = ensemble_probability(
                home_xg, away_xg, home_form, away_form, h2h,
                match_data=None, api_predictions=api_predictions,
                is_international=is_international
            )
            # ★ H2H Паттерн: Гости проигрывают (ставка на П1)
            h2h_p1 = analyze_h2h_patterns(h2h, home)
            if h2h_p1.get("away_lose_pattern"):
                probs["home_win"] = min(probs.get("home_win", 0) + 0.10, 0.95)
                probs["1X"] = probs["home_win"] + probs.get("draw", 0)
                logger.info(f"H2H P1: {home} vs {away}")

            if hm == 'relegation' and am == 'mid_table':
                probs['home_win'] = probs.get('home_win', 0) + 0.05
            elif am == 'relegation' and hm == 'mid_table':
                probs['away_win'] = probs.get('away_win', 0) + 0.05

            bets = []
            odds_template = {'1X': 1.85, 'X2': 1.85, 'П1': 2.10, 'П2': 2.10,
                             'ТМ 2.5': 1.95, 'ТБ 2.5': 1.95, 'ОБЗ': 1.90}
            for bt, label, pk in [('1X', '1X', '1X'), ('X2', 'X2', 'X2'),
                                    ('П1', 'П1', 'home_win'), ('П2', 'П2', 'away_win'),
                                    ('under', 'ТМ 2.5', 'under25'),
                                    ('over', 'ТБ 2.5', 'over25'),
                                    ('btts', 'ОБЗ', 'btts')]:
                p = probs.get(pk, probs.get(pk.replace('25', '_2_5'), 0))
                if p <= 0: continue
                key = 'ТМ 2.5' if bt == 'under' else ('ТБ 2.5' if bt == 'over' else ('ОБЗ' if bt == 'btts' else label))
                prob_pct = round(p * 100, 1)
                calibrated_pct = calibrate_prob(prob_pct, use_bucket=True)
                ev = round((calibrated_pct / 100 * odds_template[key] - 1) * 100, 1)
                bets.append({
                    'type': bt, 'label': label,
                    'prob': prob_pct,
                    'prob_calibrated': calibrated_pct,
                    'ev': ev,
                    'odds': odds_template[key], 'stake': 0,
                    'odds_updated': False,
                })
            if not bets: continue
            bets.sort(key=lambda x: x['ev'], reverse=True)
            best_bet = bets[0]

            if best_bet['prob'] > PROB_MAX_70:
                prob_filtered += 1
                continue

            if best_bet['type'] in ('П1', '1X') and best_bet['odds'] < MIN_ODDS_1X:
                cheap_fav_skipped += 1
                continue

            EV_MIN_70 = getattr(Config, 'EV_MIN_70', 8)
            PROB_MIN_70 = getattr(Config, 'PROB_MIN_70', 52)
            if best_bet['ev'] < EV_MIN_70: continue
            if best_bet['prob'] < PROB_MIN_70: continue

            if best_bet['ev'] > 40:
                logger.warning(
                    f"⚠️ HIGH EV {best_bet['ev']}%: {home} vs {away} — "
                    f"prob={best_bet['prob']}% odds={best_bet['odds']} — понижаем stake"
                )
                best_bet['high_ev_warning'] = True

            prob_for_kelly = best_bet.get('prob_calibrated', best_bet.get('prob', 0))
            kelly_stake = calculate_stake(
                bank=bank,
                prob_pct=prob_for_kelly,
                odds=best_bet.get('odds', 1.85),
            )
            kelly_info = calculate_kelly_info(
                bank=bank,
                prob_pct=prob_for_kelly,
                odds=best_bet.get('odds', 1.85),
            )
            best_bet['kelly_full'] = kelly_info['kelly_full']
            best_bet['kelly_quarter'] = kelly_info['kelly_quarter']

            final_stake, clv_action, adjusted_prob = apply_clv_filter(
                source='70_percent',
                base_stake=kelly_stake,
                prob_pct=prob_for_kelly,
                odds=best_bet.get('odds', 1.85),
                bank=bank,
            )
            if final_stake <= 0:
                logger.info(f"⏭️ CLV SKIP (70_percent): {home} vs {away}")
                continue

            best_bet['prob_calibrated'] = round(adjusted_prob, 1)
            best_bet['clv_adjusted'] = True
            if best_bet.get('odds', 0) > 1.01:
                best_bet['ev'] = round(
                    (adjusted_prob / 100 * best_bet['odds'] - 1) * 100, 1
                )

            for b in bets:
                b['stake'] = final_stake
                b['clv_action'] = clv_action
                b['prob_calibrated'] = round(adjusted_prob, 1)
            best_bet['stake'] = final_stake
            best_bet['clv_action'] = clv_action

            if best_bet['ev'] < EV_MIN_70:
                logger.info(
                    f"⏭️ CLV EV SKIP ({best_bet['ev']}% < {EV_MIN_70}%): "
                    f"{home} vs {away}"
                )
                continue

            bt = best_bet['type']
            LIMIT_BT = getattr(Config, 'LIMIT_BET_TYPE_70', 15)
            LIMIT_LG = getattr(Config, 'LIMIT_LEAGUE_70', 5)
            bet_type_count[bt] = bet_type_count.get(bt, 0) + 1
            if bet_type_count[bt] > LIMIT_BT: continue
            league_count[league_name] = league_count.get(league_name, 0) + 1
            if league_count[league_name] > LIMIT_LG: continue

            if X2_ENABLED and not is_international:
                position_diff = abs(hp - ap)
                x2_bet = None
                x2_side = None
                for b in bets:
                    b_type = b.get('type', '')
                    if b_type == 'X2' and hp < ap:
                        x2_bet = b; x2_side = 'X2'; break
                    elif X2_BOTH_SIDES and b_type == '1X' and ap < hp:
                        x2_bet = b; x2_side = '1X'; break

                if x2_bet is not None:
                    X2_HOME_BONUS = getattr(Config, 'X2_HOME_BONUS', 3.0)
                    X2_AWAY_PENALTY = getattr(Config, 'X2_AWAY_PENALTY', 2.0)
                    underdog_is_home = (x2_side == 'X2')
                    original_prob = x2_bet.get('prob', 0)

                    if underdog_is_home:
                        x2_bet['prob'] = round(original_prob + X2_HOME_BONUS, 1)
                        x2_bet['home_advantage'] = True
                    else:
                        x2_bet['prob'] = round(original_prob - X2_AWAY_PENALTY, 1)
                        x2_bet['home_advantage'] = False

                    if x2_bet.get('odds', 0) > 1.01:
                        calibrated_x2 = calibrate_prob(x2_bet['prob'], use_bucket=True)
                        x2_bet['prob_calibrated'] = calibrated_x2
                        x2_bet['ev'] = round((calibrated_x2 / 100 * x2_bet['odds'] - 1) * 100, 1)

                    bets.sort(key=lambda x: x['ev'], reverse=True)
                    best_bet = bets[0]

                if (x2_bet is not None
                    and position_diff >= X2_MIN_POSITION_DIFF
                    and hp < X2_MAX_POSITION and ap < X2_MAX_POSITION
                    and x2_bet.get('ev', 0) >= X2_MIN_EV
                    and x2_bet.get('prob', 0) >= X2_MIN_PROB):
                    try:
                        favorite = home if hp < ap else away
                        underdog = away if hp < ap else home
                        log_no_motivation_match(home, away, hp, ap, total_xg, league_name,
                                                favorite=favorite, underdog=underdog)

                        pre_odds = match.get('_preloaded_odds') or {}
                        entry_odds = 0
                        entry_1x_odds = 0
                        if x2_side == 'X2':
                            entry_odds = pre_odds.get('x2_odds', 0) or 0
                            entry_1x_odds = pre_odds.get('1x_odds', 0) or 0
                        elif x2_side == '1X':
                            entry_odds = pre_odds.get('1x_odds', 0) or 0
                            entry_1x_odds = pre_odds.get('x2_odds', 0) or 0

                        if not entry_odds and x2_bet.get('prob', 0) > 0:
                            p = x2_bet.get('prob', 0) / 100
                            entry_odds = round((1 / p) * 0.95, 2) if p > 0 else 0

                        saved = save_x2_candidate(
                            home=home, away=away, hp=hp, ap=ap,
                            league_name=league_name, match_time=match_time,
                            fixture_id=fid, home_form=home_form, away_form=away_form,
                            total_xg=total_xg, x2_side=x2_side,
                            x2_ev=x2_bet.get('ev', 0), x2_prob=x2_bet.get('prob', 0),
                            entry_odds=entry_odds, entry_1x_odds=entry_1x_odds,
                        )
                        if saved:
                            x2_saved_count += 1
                    except Exception as e:
                        logger.error(f"X2 candidate save error: {e}")

            country_name, country_flag = _get_country_flag(league_id)

            best_matches.append({
                "home": home, "away": away, "league": league_name,
                "country": country_name, "country_flag": country_flag,
                "fixture_id": fid, "match_time": match_time,
                "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
                "total_xg": round(total_xg, 2),
                "home_form": home_form, "away_form": away_form,
                "standings": {"home_position": hp, "away_position": ap,
                              "home_motivation": hm, "away_motivation": am},
                "bets": bets, "best_bet": best_bet,
                "weather_reason": match.get('weather_reason', ''),
                "api_predictions": api_predictions,
                "factors": {}, "source": "70_percent",
                "is_international": is_international,
                "_preloaded_odds": match.get('_preloaded_odds'),
            })
        except Exception as e:
            logger.error(f"❌ [70%+] {e}")
            continue

    best_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top = best_matches[:max_bets]
    logger.info(
        f"📊 [70%+] Итого: {len(top)}, X2: {x2_saved_count}, "
        f"Skip 1X: {cheap_fav_skipped}, Prob-filter: {prob_filtered}"
    )

    if Config.LLM_ENABLED and top and Config.PREDICTION_ENGINE in ('llm', 'hybrid'):
        try:
            llm_payload = [{'home': m['home'], 'away': m['away'], 'league': m['league'],
                            'home_xg': m['home_xg'], 'away_xg': m['away_xg'],
                            'total_xg': m['total_xg'],
                            'home_form': m['home_form'], 'away_form': m['away_form'],
                            'standings': m['standings'],
                            'weather_reason': m.get('weather_reason', ''),
                            'home_injuries': [], 'away_injuries': []} for m in top[:20]]
            llm_results = llm_analyze_batch(llm_payload)
            for m, llm in zip(top[:20], llm_results):
                if llm:
                    _apply_llm_to_match(m, llm, alpha=0.7)
                    bb = m.get('best_bet', {})
                    if bb and bb.get('prob', 0) > 0 and bb.get('odds', 0) > 1.01:
                        try:
                            bet_type = (bb.get('type') or '').lower()
                            llm_key_map = {
                                '1x': None, 'x2': None, 'п1': 'home_win',
                                'п2': 'away_win', 'draw': 'draw',
                                'under': 'under25', 'over': 'over25',
                                'btts': 'btts',
                            }
                            llm_key = llm_key_map.get(bet_type)
                            if llm_key and llm.get(llm_key) is not None:
                                model_prob = bb['prob']
                                llm_prob = llm[llm_key] * 100
                                alpha = 0.3
                                blended = model_prob * (1 - alpha) + llm_prob * alpha
                                bb['prob_before_ensemble'] = model_prob
                                bb['llm_prob_raw'] = round(llm_prob, 1)
                                bb['prob'] = round(blended, 1)
                                bb['ensemble_alpha'] = alpha
                                if bb['odds'] > 1.01:
                                    bb['ev'] = round((blended / 100 * bb['odds'] - 1) * 100, 1)
                                logger.info(
                                    f"🎯 ENSEMBLE {bb.get('label')}: "
                                    f"model={model_prob:.1f}% + llm={llm_prob:.1f}% "
                                    f"-> {blended:.1f}% (α={alpha})"
                                )
                        except Exception as e:
                            logger.error(f"Ensemble error: {e}")

            for m in top[:10]:
                try:
                    reason = llm_generate_reason(m)
                    if reason:
                        m['best_bet']['llm_reason'] = reason
                        logger.info(f"💡 LLM reason: {m['home']} vs {m['away']} → {reason[:80]}")
                except Exception as e:
                    logger.debug(f"llm_generate_reason error: {e}")
        except Exception as e:
            logger.error(f"❌ LLM ошибка: {e}")
    return top


# ============================================================
# ★ ПОТОК 2: ТМ 2.5 (Kelly Fix)
# ============================================================
@timing_decorator()
def find_tm25_matches(matches):
    bank = storage.load_bank()
    tm25_candidates = []
    MAX_TM25_BETS = getattr(Config, 'MAX_TM25_BETS', 5)
    PREMIUM_MIN_EV = getattr(Config, 'PREMIUM_MIN_EV', 25) / 100
    PREMIUM_MIN_PROB = getattr(Config, 'PREMIUM_MIN_PROB', 58) / 100
    PREMIUM_XG_MIN = getattr(Config, 'PREMIUM_XG_MIN', 1.0)
    PREMIUM_XG_MAX = getattr(Config, 'PREMIUM_XG_MAX', 2.8)
    STANDARD_MIN_EV = getattr(Config, 'STANDARD_MIN_EV', 20) / 100
    STANDARD_MIN_PROB = getattr(Config, 'STANDARD_MIN_PROB', 56) / 100
    STANDARD_XG_MIN = getattr(Config, 'STANDARD_XG_MIN', 1.2)
    STANDARD_XG_MAX = getattr(Config, 'STANDARD_XG_MAX', 2.8)
    TOP_LEAGUE_EV = getattr(Config, 'TM25_TOP_LEAGUE_EV', 35) / 100
    STANDARD_TOP_LEAGUE_EV = getattr(Config, 'STANDARD_MIN_EV', 20) / 100

    INCLUDE_INTERNATIONAL = getattr(Config, 'TM25_INCLUDE_INTERNATIONAL', False)
    USE_KELLY = getattr(Config, 'TM25_USE_KELLY', True)
    FORM_FILTER = getattr(Config, 'TM25_FORM_FILTER', True)
    H2H_FILTER = getattr(Config, 'TM25_H2H_FILTER', True)
    H2H_MIN_MATCHES = getattr(Config, 'TM25_MIN_H2H_MATCHES', 3)
    H2H_AVG_MAX = getattr(Config, 'TM25_H2H_AVG_MAX', 2.8)
    LEAGUE_BONUS = getattr(Config, 'TM25_LEAGUE_BONUS', 5)
    MAX_LEAGUE_BETS = getattr(Config, 'TM25_MAX_LEAGUE_BETS', 2)

    logger.info("🔍 [ТМ 2.5 v22.9] Расширенный поиск + калибровка + CLV...")
    stats = {
        'premium_found': 0, 'standard_found': 0,
        'clv_skipped': 0, 'intl_skipped': 0,
        'league_bonus': 0, 'league_limit': 0,
        'form_skipped': 0, 'h2h_skipped': 0, 'prob_filtered': 0,
        'no_odds': 0,
    }
    seen_keys = set()
    league_bet_count = {}

    for match in matches:
        if len(tm25_candidates) >= MAX_TM25_BETS: break
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
                is_intl = _is_international_league(league_id, league_name)
                if is_intl:
                    stats['intl_skipped'] += 1
                    continue

            cur_league_bets = league_bet_count.get(league_name, 0)
            if cur_league_bets >= MAX_LEAGUE_BETS:
                stats['league_limit'] += 1
                continue

            stats_dict = football_api.get_match_statistics(fid) if fid else None
            home_xg = 1.2; away_xg = 1.0
            if stats_dict:
                for tn, ts in stats_dict.items():
                    if home.lower() in tn.lower() or tn.lower() in home.lower():
                        xg = ts.get('Expected Goals', ts.get('xG'))
                        if xg and xg > 0: home_xg = float(xg)
                    elif away.lower() in tn.lower() or tn.lower() in away.lower():
                        xg = ts.get('Expected Goals', ts.get('xG'))
                        if xg and xg > 0: away_xg = float(xg)

            if home_xg == 1.2 and away_xg == 1.0:
                if league_name in FALLBACK_XG:
                    home_xg = FALLBACK_XG[league_name]['home']
                    away_xg = FALLBACK_XG[league_name]['away']
                else:
                    home_xg = 1.3; away_xg = 1.0
                rng = random.Random(fid)
                home_xg *= (1 + rng.uniform(-0.1, 0.1))
                away_xg *= (1 + rng.uniform(-0.1, 0.1))

            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            total_xg = home_xg + away_xg

            factors = match.get('factors', {}) or {}
            hfd = factors.get('home_form') or football_api.get_form(ht.get('id'))
            afd = factors.get('away_form') or football_api.get_form(at.get('id'))
            home_form = hfd.get('form', '') if hfd else ''
            away_form = afd.get('form', '') if afd else ''

            if FORM_FILTER:
                home_under = _form_is_under(home_form)
                away_under = _form_is_under(away_form)
                if not (home_under or away_under):
                    stats['form_skipped'] += 1
                    continue

            standings = football_api.get_standings(league_id) if league_id else None
            hp = standings.get(home, {}).get('position', 99) if standings else 99
            ap = standings.get(away, {}).get('position', 99) if standings else 99

            h2h = football_api.get_head_to_head(home, away)

            if H2H_FILTER and h2h:
                h2h_total = h2h.get('total_matches', 0)
                h2h_avg = h2h.get('avg_goals', 0)
                if h2h_total >= H2H_MIN_MATCHES and h2h_avg > H2H_AVG_MAX:
                    stats['h2h_skipped'] += 1
                    continue

            probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h)
            p_under = probs.get('under25', probs.get('under_2_5', 0))
            p_under_pct = p_under * 100

            # ★ ГЛАВНЫЙ ФИКС: Берем реальный кэф из кэша, а не шаблон 1.95
            fo = match.get('_preloaded_odds') or {}
            real_odds = fo.get('under_odds', 0) or 0
            
            if real_odds <= 1.01 and fid:
                fresh_odds = football_api.get_match_odds(fid)
                if fresh_odds:
                    real_odds = fresh_odds.get('under_odds', 0) or 0

            odds_tm25 = real_odds if real_odds > 1.01 else 1.95

            is_whitelisted = Config.is_tm25_league_whitelisted(league_name)

            if p_under_pct > PROB_MAX_70:
                stats['prob_filtered'] += 1
                continue

            calibrated_p = calibrate_prob(p_under_pct, use_bucket=True)
            ev_under = (calibrated_p / 100 * odds_tm25) - 1
            if is_whitelisted:
                ev_under += LEAGUE_BONUS / 100

            country_name, country_flag = _get_country_flag(league_id)

            # === PREMIUM ===
            if (PREMIUM_XG_MIN <= total_xg <= PREMIUM_XG_MAX
                and ev_under >= PREMIUM_MIN_EV and calibrated_p / 100 >= PREMIUM_MIN_PROB):
                if league_name in TOP_LEAGUES and ev_under < TOP_LEAGUE_EV:
                    continue
                stake = _calculate_tm25_stake(USE_KELLY, bank, calibrated_p, odds_tm25)
                final_stake, clv_action, adjusted_prob = apply_clv_filter(
                    source='tm25_premium',
                    base_stake=stake,
                    prob_pct=calibrated_p,
                    odds=odds_tm25,
                    bank=bank,
                )
                if final_stake <= 0:
                    stats['clv_skipped'] += 1
                    continue
                if is_whitelisted:
                    stats['league_bonus'] += 1

                calibrated_p = round(adjusted_prob, 1)
                ev_under = (calibrated_p / 100 * odds_tm25) - 1
                if is_whitelisted:
                    ev_under += LEAGUE_BONUS / 100
                if ev_under < PREMIUM_MIN_EV:
                    continue

                best_bet = {'type': 'under', 'label': 'ТМ 2.5 🔥',
                            'prob': round(p_under_pct, 1),
                            'prob_calibrated': calibrated_p,
                            'ev': round(ev_under * 100, 1),
                            'odds': odds_tm25, 'stake': final_stake,
                            'clv_action': clv_action,
                            'clv_adjusted': True,
                            'level': 'PREMIUM',
                            'league_bonus': is_whitelisted,
                            'odds_updated': (real_odds > 1.01)}
                tm25_candidates.append({
                    "home": home, "away": away, "league": league_name,
                    "country": country_name, "country_flag": country_flag,
                    "fixture_id": fid, "match_time": match_time,
                    "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
                    "total_xg": round(total_xg, 2),
                    "home_form": home_form, "away_form": away_form,
                    "standings": {"home_position": hp, "away_position": ap},
                    "bets": [best_bet], "best_bet": best_bet,
                    "source": "tm25_premium", "weather_reason": "🌤️",
                    "_preloaded_odds": match.get('_preloaded_odds'),
                })
                stats['premium_found'] += 1
                league_bet_count[league_name] = cur_league_bets + 1
                continue

            # === STANDARD ===
            if (STANDARD_XG_MIN <= total_xg <= STANDARD_XG_MAX
                and ev_under >= STANDARD_MIN_EV and calibrated_p / 100 >= STANDARD_MIN_PROB):
                if league_name in TOP_LEAGUES and ev_under < STANDARD_TOP_LEAGUE_EV:
                    continue
                stake = _calculate_tm25_stake(USE_KELLY, bank, calibrated_p, odds_tm25)
                final_stake, clv_action, adjusted_prob = apply_clv_filter(
                    source='tm25_standard',
                    base_stake=stake,
                    prob_pct=calibrated_p,
                    odds=odds_tm25,
                    bank=bank,
                )
                if final_stake <= 0:
                    stats['clv_skipped'] += 1
                    continue
                if is_whitelisted:
                    stats['league_bonus'] += 1

                calibrated_p = round(adjusted_prob, 1)
                ev_under = (calibrated_p / 100 * odds_tm25) - 1
                if is_whitelisted:
                    ev_under += LEAGUE_BONUS / 100
                if ev_under < STANDARD_MIN_EV:
                    continue

                best_bet = {'type': 'under', 'label': 'ТМ 2.5',
                            'prob': round(p_under_pct, 1),
                            'prob_calibrated': calibrated_p,
                            'ev': round(ev_under * 100, 1),
                            'odds': odds_tm25, 'stake': final_stake,
                            'clv_action': clv_action,
                            'clv_adjusted': True,
                            'level': 'STANDARD',
                            'league_bonus': is_whitelisted,
                            'odds_updated': (real_odds > 1.01)}
                tm25_candidates.append({
                    "home": home, "away": away, "league": league_name,
                    "country": country_name, "country_flag": country_flag,
                    "fixture_id": fid, "match_time": match_time,
                    "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
                    "total_xg": round(total_xg, 2),
                    "home_form": home_form, "away_form": away_form,
                    "standings": {"home_position": hp, "away_position": ap},
                    "bets": [best_bet], "best_bet": best_bet,
                    "source": "tm25_standard", "weather_reason": "🌤️",
                    "_preloaded_odds": match.get('_preloaded_odds'),
                })
                stats['standard_found'] += 1
                league_bet_count[league_name] = cur_league_bets + 1
        except Exception as e:
            logger.error(f"❌ [ТМ2.5] {e}")
            continue

    logger.info(
        f"📊 [ТМ2.5] PREMIUM: {stats['premium_found']}, STANDARD: {stats['standard_found']} | "
        f"CLV-skip: {stats['clv_skipped']}, Prob-filter: {stats['prob_filtered']}"
    )
    tm25_candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    return tm25_candidates


def _form_is_under(form_string):
    if not form_string:
        return False
    wins = form_string.count('W')
    return wins <= 2


def _calculate_tm25_stake(use_kelly, bank, prob_pct, odds):
    if use_kelly:
        return calculate_stake(bank=bank, prob_pct=prob_pct, odds=odds)
    return 42.87
