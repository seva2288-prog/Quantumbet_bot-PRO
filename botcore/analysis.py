# ============================================================
# botcore/analysis.py — Расчёты: Келли, CLV, steam, вероятности, H2H, Excel-экспорт
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

__all__ = [
    'calculate_stake',
    'calculate_kelly_info',
    '_CLV_CACHE',
    '_CLV_CACHE_TS',
    '_CLV_CACHE_TTL',
    'get_strategy_clv',
    '_compute_all_strategy_clv',
    '_guess_source_from_label',
    'apply_clv_filter',
    'detect_steam_move',
    'get_motivation',
    'analyze_form',
    '_get_country_flag',
    '_is_international_league',
    'export_to_excel',
    'get_profit_data',
    'calculate_poisson_probability',
    'calculate_form_probability',
    'calculate_h2h_probability',
    'ensemble_probability',
    '_apply_llm_to_match',
    'analyze_h2h_patterns',
]


# ============================================================
# ★ KELLY CRITERION (Исправлено)
# ============================================================
def calculate_stake(bank, prob_pct, odds,
                     base_pct=None, kelly_fraction=None,
                     max_pct=None, min_stake=None):
    """Quarter-Kelly с защитой + множитель по точности бакета."""
    if base_pct is None:
        base_pct = getattr(Config, 'KELLY_MIN_PCT', 0.02)
    if kelly_fraction is None:
        kelly_fraction = getattr(Config, 'KELLY_FRACTION', 0.25)
    if max_pct is None:
        max_pct = getattr(Config, 'KELLY_MAX_PCT', 0.05)
    if min_stake is None:
        min_stake = getattr(Config, 'KELLY_MIN_STAKE', 1.0)

    if not getattr(Config, 'KELLY_ENABLED', True):
        return max(round(bank * base_pct, 2), min_stake)

    if bank <= 0 or odds <= 1.01 or prob_pct <= 0:
        return min_stake

    b = odds - 1
    p = prob_pct / 100.0
    q = 1 - p

    kelly_full = (b * p - q) / b
    if kelly_full <= 0:
        return max(round(bank * base_pct, 2), min_stake)

    kelly_stake_pct = kelly_full * kelly_fraction

    try:
        bucket_factor = Config.get_kelly_bucket_factor(prob_pct)
        kelly_stake_pct *= bucket_factor
    except Exception:
        pass

    final_pct = max(base_pct, min(kelly_stake_pct, max_pct))
    stake = round(bank * final_pct, 2)
    return max(stake, min_stake)


def calculate_kelly_info(bank, prob_pct, odds, kelly_fraction=None):
    """Возвращает инфу о Kelly — для логирования/UI."""
    if kelly_fraction is None:
        kelly_fraction = getattr(Config, 'KELLY_FRACTION', 0.25)

    if odds <= 1.01 or prob_pct <= 0:
        return {'kelly_full': 0, 'kelly_quarter': 0, 'edge': 0}
    b = odds - 1
    p = prob_pct / 100.0
    q = 1 - p
    kelly_full = (b * p - q) / b if b > 0 else 0
    edge = (p * odds - 1) * 100
    return {
        'kelly_full': round(kelly_full * 100, 2),
        'kelly_quarter': round(kelly_full * kelly_fraction * 100, 2),
        'edge': round(edge, 2),
    }


# ============================================================
# ★ CLV-ФИЛЬТР (Без изменений, работает отлично)
# ============================================================
_CLV_CACHE = {}


_CLV_CACHE_TS = 0


_CLV_CACHE_TTL = 600


def get_strategy_clv(source, days=None, min_samples=None):
    """Возвращает CLV-статистику по стратегии (кэш 10 минут)."""
    global _CLV_CACHE, _CLV_CACHE_TS
    if days is None:
        days = getattr(Config, 'CLV_LOOKBACK_DAYS', 30)
    if min_samples is None:
        min_samples = getattr(Config, 'CLV_MIN_SAMPLES', 20)

    now = time.time()
    if (not _CLV_CACHE or now - _CLV_CACHE_TS > _CLV_CACHE_TTL):
        _CLV_CACHE = _compute_all_strategy_clv(days=days, min_samples=min_samples)
        _CLV_CACHE_TS = now
    return _CLV_CACHE.get(source, {
        'avg_clv': 0, 'count': 0, 'samples': 0,
        'status': 'no_data', 'multiplier': 1.0, 'skip': False,
    })


def _compute_all_strategy_clv(days=30, min_samples=20):
    """Считает CLV по каждой стратегии из автобетов."""
    result = {}
    try:
        bets = storage.autobet_load_all()
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        by_source = defaultdict(list)

        for b in bets:
            clv = b.get('clv')
            if clv is None:
                continue
            created = b.get('created_at', '')
            try:
                ct = datetime.fromisoformat(created).timestamp()
                if ct < cutoff:
                    continue
            except Exception:
                pass

            src = b.get('source', '') or _guess_source_from_label(b.get('bet_label', ''))
            by_source[src].append(clv)

        for src, clvs in by_source.items():
            if not clvs:
                continue
            avg = sum(clvs) / len(clvs)
            n = len(clvs)

            multiplier, skip, status = Config.get_clv_multiplier(avg, n)

            result[src] = {
                'avg_clv': round(avg, 2),
                'count': n,
                'samples': n,
                'status': status,
                'multiplier': multiplier,
                'skip': skip,
            }
    except Exception as e:
        logger.error(f"_compute_all_strategy_clv: {e}")

    logger.info(f"📊 CLV по стратегиям: {result}")
    return result


def _guess_source_from_label(label):
    """Восстанавливает source по label, если не сохранён."""
    l = (label or '').lower()
    if '📈' in (label or '') or 'line movement' in l or 'движение' in l:
        return 'line_movement'
    if '💎' in (label or ''):
        return 'value'
    if '🔥' in (label or '') or 'premium' in l:
        return 'tm25_premium'
    if 'обз' in l or 'btts' in l:
        return 'btts'
    if 'тм 2.5' in l or 'under' in l:
        return 'tm25_standard'
    if 'x2' in l:
        return 'x2'
    return '70_percent'


def apply_clv_filter(source, base_stake, prob_pct, odds, bank):
    """
    CLV влияет на prob, а не только на stake.

    Returns:
        (final_stake, action_str, adjusted_prob)
    """
    if source in ('tm25_premium', 'tm25_standard'):
        return base_stake, 'no_clv_tm25', prob_pct

    if source == 'line_movement':
        return base_stake, 'no_model', prob_pct

    if not getattr(Config, 'CLV_FILTER_ENABLED', True):
        return base_stake, 'disabled', prob_pct

    clv_info = get_strategy_clv(source)

    if clv_info['status'] in ('no_data', 'insufficient_data'):
        return base_stake, 'no_data', prob_pct

    if clv_info['skip']:
        logger.warning(f"⏭️ CLV SKIP {source}: avg={clv_info['avg_clv']}% n={clv_info['count']}")
        return 0, 'skipped', prob_pct

    avg_clv = clv_info['avg_clv']
    mult = clv_info['multiplier']

    if avg_clv < -3.0 and getattr(Config, 'CLV_SKIP_CRITICAL', False):
        logger.warning(f"🛑 CLV CRITICAL SKIP {source}: avg={avg_clv}%")
        return 0, 'critical_skip', prob_pct

    adjusted_prob = prob_pct
    if avg_clv > 2.0:
        adjusted_prob = prob_pct * 1.05
    elif avg_clv < -1.0:
        adjusted_prob = prob_pct * 0.90

    if mult == 1.0:
        return base_stake, 'normal', adjusted_prob

    new_stake = round(base_stake * mult, 2)
    max_stake = round(bank * getattr(Config, 'KELLY_MAX_PCT', 0.05), 2)
    if new_stake > max_stake:
        new_stake = max_stake

    action = 'boosted' if mult > 1.0 else 'reduced'
    logger.info(
        f"🎯 CLV {source}: {action} stake {base_stake} → {new_stake} "
        f"(x{mult}) | prob {prob_pct:.1f}% → {adjusted_prob:.1f}%"
    )
    return new_stake, action, adjusted_prob


# ============================================================
# ★ STEAM MOVE DETECTION (Без изменений)
# ============================================================
def detect_steam_move(fixture_id, market, selection, hours_back=3):
    """Ищет Steam Move: 3+ БК упали на 5%+ за N часов."""
    try:
        cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        snaps = storage.get_odds_history(fixture_id, market, selection)
        if not snaps or len(snaps) < 6:
            return None

        recent = [s for s in snaps if (s.get('created_at', '') or '') >= cutoff]
        if len(recent) < 6:
            return None

        by_bm = defaultdict(list)
        for s in recent:
            bm = s.get('bookmaker', '?')
            by_bm[bm].append(s)

        steam_moves = []
        for bm, bm_snaps in by_bm.items():
            if len(bm_snaps) < 2:
                continue
            bm_snaps.sort(key=lambda x: x.get('created_at', ''))
            first_odd = float(bm_snaps[0].get('odds', 0))
            last_odd = float(bm_snaps[-1].get('odds', 0))
            if first_odd <= 1.01 or last_odd <= 1.01:
                continue
            change = ((last_odd / first_odd) - 1) * 100
            if change <= -5.0:
                steam_moves.append({
                    'bookmaker': bm,
                    'first': first_odd,
                    'last': last_odd,
                    'change': round(change, 1),
                })

        if len(steam_moves) >= 3:
            avg_change = sum(m['change'] for m in steam_moves) / len(steam_moves)
            return {
                'detected': True,
                'bm_count': len(steam_moves),
                'avg_change': round(avg_change, 1),
                'moves': steam_moves[:5],
            }
        return None
    except Exception as e:
        logger.error(f"detect_steam_move {fixture_id}: {e}")
        return None


# ============================================================
# УТИЛИТЫ (Без изменений)
# ============================================================
def get_motivation(position):
    if position <= 2: return 'title_race'
    if position <= 4: return 'champions_league'
    if position <= 6: return 'europa_league'
    if position <= 14: return 'mid_table'
    if position <= 17: return 'relegation_playoff'
    return 'relegation'


def analyze_form(form_string):
    if not form_string: return 'average'
    wins = form_string.count('W')
    if wins >= 4: return 'excellent'
    if wins >= 3: return 'good'
    if wins >= 2: return 'average'
    return 'poor'


def _get_country_flag(league_id):
    try:
        lid = int(league_id) if league_id else None
    except (ValueError, TypeError):
        lid = None
    if lid is None:
        return ("", "")
    return Config.LEAGUE_COUNTRY.get(lid, ("", ""))


def _is_international_league(league_id, league_name):
    try:
        if league_id and int(league_id) in getattr(Config, 'INTERNATIONAL_LEAGUES', []):
            return True
    except (ValueError, TypeError):
        pass
    ln = (league_name or '').lower()
    markers = (
        'nations league', 'world cup', 'euro championship',
        'friendlies', 'international', 'wc qualification',
        'euro qualification',
    )
    return any(x in ln for x in markers)


def export_to_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    import io

    history = storage.load_history()
    if not history:
        return None, "📭 Нет данных для экспорта"

    wb = Workbook()
    ws = wb.active
    ws.title = "Ставки"
    headers = ["Дата", "Матч", "Счёт", "1-й тайм", "Ставка", "Коэф", "EV%", "Prob%",
               "Сумма", "Результат", "Прибыль", "Букмекер", "Источник"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill(start_color="10b981", end_color="10b981", fill_type="solid")
        c.alignment = Alignment(horizontal="center")

    total_profit = 0
    for bet in history:
        score = f"{bet.get('home_goals', '-')}-{bet.get('away_goals', '-')}"
        ht = f"{bet.get('halftime_home', '-')}-{bet.get('halftime_away', '-')}" \
            if bet.get('halftime_home') is not None else '-'
        result = bet.get('result', 'pending')
        profit = bet.get('profit', 0)
        if result == 'win' and profit == 0:
            profit = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
        elif result == 'loss' and profit == 0:
            profit = -bet.get('stake', 0)
        if result in ('win', 'loss'):
            total_profit += profit
        ws.append([bet.get('date', ''), f"{bet.get('home', '')} vs {bet.get('away', '')}",
                   score, ht, bet.get('bet', ''), bet.get('odds', 0), bet.get('ev', 0),
                   bet.get('prob', 0), bet.get('stake', 0), result, profit,
                   bet.get('bookmaker', '—'), bet.get('source', '70_percent')])
    ws.append([])
    ws.append(["ИТОГО", "", "", "", "", "", "", "", "", "", round(total_profit, 2), "", ""])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output, f"✅ Экспорт! Ставок: {len(history)}, Прибыль: ${round(total_profit, 2)}"


def get_profit_data(history, days=7):
    profits = []
    for i in range(days - 1, -1, -1):
        day_profit = 0
        day = datetime.now() - timedelta(days=i)
        for bet in history:
            try:
                bd = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bd.date() == day.date():
                    stake = float(bet.get('stake', 0))
                    odds = float(bet.get('odds', 1))
                    if bet.get('result') == 'win':
                        day_profit += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= stake
            except Exception:
                pass
        profits.append(round(day_profit, 2))
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m')
             for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}


# ============================================================
# POISSON / ENSEMBLE (Без изменений)
# ============================================================
def calculate_poisson_probability(home_xg, away_xg):
    def poisson(avg, g):
        return (math.exp(-avg) * avg ** g) / math.factorial(g)
    hgp = [poisson(home_xg, i) for i in range(6)]
    agp = [poisson(away_xg, i) for i in range(6)]
    prob = {'home_win': 0, 'away_win': 0, 'draw': 0,
            '1X': 0, 'X2': 0, 'btts': 0,
            'over25': 0, 'under25': 0, 'over_2_5': 0, 'under_2_5': 0}
    for h in range(6):
        for a in range(6):
            p = hgp[h] * agp[a]
            if h > a: prob['home_win'] += p
            elif h < a: prob['away_win'] += p
            else: prob['draw'] += p
            if h >= a: prob['1X'] += p
            if a >= h: prob['X2'] += p
            if h > 0 and a > 0: prob['btts'] += p
            if h + a > 2.5:
                prob['over25'] += p; prob['over_2_5'] += p
            else:
                prob['under25'] += p; prob['under_2_5'] += p
    return prob


def calculate_form_probability(home_form, away_form):
    hq = analyze_form(home_form)
    aq = analyze_form(away_form)
    prob = {'home_win': 0.35, 'away_win': 0.30, 'draw': 0.35,
            '1X': 0.70, 'X2': 0.65, 'btts': 0.45,
            'over25': 0.5, 'under25': 0.5, 'over_2_5': 0.45, 'under_2_5': 0.55}
    if hq == 'excellent' and aq == 'poor':
        prob['home_win'] += 0.15; prob['1X'] += 0.10
        prob['away_win'] -= 0.10; prob['X2'] -= 0.10
    elif hq == 'poor' and aq == 'excellent':
        prob['away_win'] += 0.15; prob['X2'] += 0.10
        prob['home_win'] -= 0.10; prob['1X'] -= 0.10
    return prob


def calculate_h2h_probability(h2h_data):
    prob = {'home_win': 0.33, 'away_win': 0.33, 'draw': 0.34,
            '1X': 0.67, 'X2': 0.67, 'btts': 0.50,
            'over25': 0.5, 'under25': 0.5, 'over_2_5': 0.50, 'under_2_5': 0.50}
    if h2h_data and h2h_data.get('total_matches', 0) > 0:
        total = h2h_data['total_matches']
        prob['home_win'] = (h2h_data.get('home_wins', 0) / total) * 0.5 + 0.25
        prob['away_win'] = (h2h_data.get('away_wins', 0) / total) * 0.5 + 0.25
        prob['draw'] = (h2h_data.get('draws', 0) / total) * 0.5 + 0.25
        prob['1X'] = prob['home_win'] + prob['draw']
        prob['X2'] = prob['away_win'] + prob['draw']
        avg_goals = h2h_data.get('avg_goals', 2.5)
        if avg_goals > 2.5:
            prob['over_2_5'] = 0.55; prob['under_2_5'] = 0.45
        else:
            prob['over_2_5'] = 0.45; prob['under_2_5'] = 0.55
    return prob


def ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data,
                          match_data=None, api_predictions=None,
                          is_international=False,
                          apply_calibration=False):
    """Ансамбль вероятностей."""
    engine = getattr(Config, 'PREDICTION_ENGINE', 'heuristic')
    poisson = calculate_poisson_probability(home_xg, away_xg)
    form_prob = calculate_form_probability(home_form, away_form)
    h2h_prob = calculate_h2h_probability(h2h_data)

    if is_international:
        w_p, w_f, w_h = 0.60, 0.15, 0.10
    elif engine == 'hybrid':
        w_p, w_f, w_h = 0.40, 0.30, 0.15
    else:
        w_p, w_f, w_h = 0.5, 0.3, 0.2

    final = {}
    all_keys = set(list(poisson.keys()) + list(form_prob.keys()) + list(h2h_prob.keys()))
    for k in all_keys:
        final[k] = (poisson.get(k, 0) * w_p +
                    form_prob.get(k, 0) * w_f +
                    h2h_prob.get(k, 0) * w_h)
    if api_predictions:
        w_api = 0.15
        final['home_win'] = final.get('home_win', 0) * (1 - w_api) + api_predictions.get('home_win', 0) * w_api
        final['draw'] = final.get('draw', 0) * (1 - w_api) + api_predictions.get('draw', 0) * w_api
        final['away_win'] = final.get('away_win', 0) * (1 - w_api) + api_predictions.get('away_win', 0) * w_api
    total = final.get('home_win', 0) + final.get('draw', 0) + final.get('away_win', 0)
    if total > 0:
        final['home_win'] /= total
        final['away_win'] /= total
        final['draw'] /= total
        final['1X'] = final['home_win'] + final['draw']
        final['X2'] = final['away_win'] + final['draw']

    if apply_calibration:
        for k in list(final.keys()):
            pct = final[k] * 100
            calibrated = calibrate_prob(pct, use_bucket=True)
            final[k] = calibrated / 100.0

    return final


def _apply_llm_to_match(match: dict, llm: dict, alpha: float = 0.7):
    """Применяет LLM-корректировку + калибровку + CLV."""
    if not llm:
        return
    key_map = {'draw': 'draw', 'underdog': None, 'btts': 'btts',
               'П1': 'home_win', 'П2': 'away_win',
               'over25': 'over_2_5', 'under25': None, '1X': None, 'X2': None}
    for b in match.get('bets', []):
        llm_key = key_map.get(b.get('type'))
        if llm_key and llm_key in llm:
            blended = b['prob'] * (1 - alpha) + llm[llm_key] * 100 * alpha
            b['prob'] = round(blended, 1)
            if b.get('odds', 0) > 1.01:
                calibrated_pct = calibrate_prob(b['prob'], use_bucket=True)
                b['prob_calibrated'] = calibrated_pct
                b['ev'] = round((calibrated_pct / 100 * b['odds'] - 1) * 100, 1)
    match['bets'].sort(key=lambda x: x['ev'], reverse=True)
    if match['bets']:
        match['best_bet'] = match['bets'][0]
        try:
            bank = storage.load_bank()
            prob_for_kelly = match['best_bet'].get('prob_calibrated', match['best_bet'].get('prob', 0))
            kelly_stake = calculate_stake(
                bank=bank,
                prob_pct=prob_for_kelly,
                odds=match['best_bet'].get('odds', 1.85),
            )
            src = match.get('source', '70_percent')
            final_stake, clv_action, adjusted_prob = apply_clv_filter(
                source=src,
                base_stake=kelly_stake,
                prob_pct=prob_for_kelly,
                odds=match['best_bet'].get('odds', 1.85),
                bank=bank,
            )
            if final_stake > 0:
                match['best_bet']['prob_calibrated'] = round(adjusted_prob, 1)
                match['best_bet']['clv_adjusted'] = True
                if match['best_bet'].get('odds', 0) > 1.01:
                    match['best_bet']['ev'] = round(
                        (adjusted_prob / 100 * match['best_bet']['odds'] - 1) * 100, 1
                    )
                for b in match['bets']:
                    b['stake'] = final_stake
                    b['clv_action'] = clv_action
                    b['prob_calibrated'] = round(adjusted_prob, 1)
                match['best_bet']['stake'] = final_stake
                match['best_bet']['clv_action'] = clv_action
        except Exception as e:
            logger.error(f"_apply_llm_to_match CLV: {e}")


def analyze_h2h_patterns(h2h_data, current_home_team):
    if not h2h_data or not h2h_data.get("matches"):
        return {"btts_pattern": False, "away_lose_pattern": False}
    matches = h2h_data["matches"][:5]
    btts_count, away_lose_count = 0, 0
    for m in matches:
        h, a = m.get("home_score", 0) or 0, m.get("away_score", 0) or 0
        if h > 0 and a > 0: btts_count += 1
        if m.get("away") == current_home_team:
            if h < a: away_lose_count += 1
        else:
            if a < h: away_lose_count += 1
    return {"btts_pattern": btts_count >= 4, "away_lose_pattern": away_lose_count >= 3}
