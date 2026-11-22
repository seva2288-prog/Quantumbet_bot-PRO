# ============================================================
# botcore/simulator.py — Симулятор стратегий + train/test/3-way grid search
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

__all__ = [
    'StrategySimulator',
    'strategy_simulator',
    '_tt_split_data',
    '_tt_simulate_subset',
    '_tt_collect_all_matches',
    '_tt_apply_filters',
    '_tt_run_train_test',
    '_tt_grid_search_train_test',
    '_tt_split_data_3way',
    '_tt_run_3way_split',
    '_tt_grid_search_3way',
]


# ============================================================
# СИМУЛЯТОР — базовые методы (simulate, grid_search)
# ============================================================
class StrategySimulator:
    """Симулятор стратегий. Train/Test + 3-Way Split методы — в Части 2."""

    def simulate(self, params, use_history=True, use_cache=True):
        all_matches = []
        if use_cache:
            try:
                cache = storage.load_cache()
                all_matches.extend(cache.get('all_analyzed', []))
                all_matches.extend(cache.get('top_matches', []))
            except Exception as e:
                logger.error(f"simulate: cache error {e}")
        if use_history:
            try:
                history = storage.load_history()
                for h in history:
                    all_matches.append({
                        'home': h.get('home'), 'away': h.get('away'),
                        'league': h.get('league'), 'match_time': h.get('date', ''),
                        'fixture_id': h.get('fixture_id'), 'total_xg': 0,
                        'best_bet': {
                            'type': (h.get('bet') or '').lower(),
                            'label': h.get('bet', ''),
                            'odds': h.get('odds', 0), 'ev': h.get('ev', 0),
                            'prob': h.get('prob', 0),
                        },
                        'result': h.get('result'), 'profit_real': h.get('profit', 0),
                        'from_history': True,
                    })
            except Exception as e:
                logger.error(f"simulate: history error {e}")
        seen = set()
        unique = []
        for m in all_matches:
            key = f"{m.get('home')}_{m.get('away')}_{m.get('match_time', '')}"
            if key not in seen:
                seen.add(key)
                unique.append(m)
        all_matches = unique

        filtered = []
        for m in all_matches:
            bb = m.get('best_bet', {})
            if not bb: continue
            ev = bb.get('ev', 0) or 0
            prob = bb.get('prob', 0) or 0
            odds = bb.get('odds', 0) or 0
            bt = (bb.get('type') or '').lower()
            total_xg = m.get('total_xg', 0) or 0
            league = m.get('league', '') or ''
            if ev < params.get('min_ev', -100): continue
            if ev > params.get('max_ev', 999): continue
            if prob < params.get('min_prob', 0): continue
            if prob > params.get('max_prob', 100): continue
            if odds < params.get('min_odds', 0): continue
            if odds > params.get('max_odds', 999): continue
            if total_xg > 0:
                if total_xg < params.get('min_xg', 0): continue
                if total_xg > params.get('max_xg', 99): continue
            bet_types = params.get('bet_types') or []
            if bet_types and bt not in [b.lower() for b in bet_types]: continue
            leagues = params.get('leagues') or []
            if leagues and league not in leagues: continue
            filtered.append(m)

        start_bank = float(params.get('start_bank', 1000))
        stake_pct = float(params.get('stake_pct', 2)) / 100
        bank = start_bank
        peak_bank = start_bank
        max_drawdown = 0
        wins = losses = pushes = 0
        total_staked = 0
        bets_log = []

        for m in filtered:
            bb = m.get('best_bet', {})
            odds = bb.get('odds', 0) or 0
            if odds < 1.01 or bank <= 0: continue
            stake = round(bank * stake_pct, 2)
            if stake < 1: continue
            result = m.get('result')
            if result in (None, 'pending'):
                try:
                    history = storage.load_history()
                    for h in history:
                        if h.get('home') == m.get('home') and h.get('away') == m.get('away'):
                            result = h.get('result')
                            break
                except Exception:
                    pass
            if result == 'win':
                profit = round(stake * (odds - 1), 2); wins += 1
            elif result == 'loss':
                profit = -stake; losses += 1
            elif result == 'push':
                profit = 0; pushes += 1
            else:
                continue
            bank += profit
            total_staked += stake
            peak_bank = max(peak_bank, bank)
            drawdown = ((peak_bank - bank) / peak_bank * 100) if peak_bank > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
            bets_log.append({
                'home': m.get('home'), 'away': m.get('away'), 'league': m.get('league'),
                'match_time': m.get('match_time'), 'bet': bb.get('label'),
                'odds': odds, 'stake': stake, 'ev': bb.get('ev'),
                'prob': bb.get('prob'), 'result': result,
                'profit': profit, 'bank_after': round(bank, 2),
            })

        total_bets = wins + losses + pushes
        profit_total = round(bank - start_bank, 2)
        roi = (profit_total / total_staked * 100) if total_staked > 0 else 0
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        return {
            'params': params, 'total_matches_analyzed': len(all_matches),
            'total_matches_filtered': len(filtered),
            'total_bets': total_bets, 'wins': wins, 'losses': losses, 'pushes': pushes,
            'total_staked': round(total_staked, 2), 'profit': profit_total,
            'roi': round(roi, 1), 'winrate': round(winrate, 1),
            'start_bank': start_bank, 'end_bank': round(bank, 2),
            'max_drawdown': round(max_drawdown, 1), 'bets': bets_log[:100],
        }

    def grid_search(self, max_combinations=200, min_bets=5):
        try:
            logger.info(f"🔍 GRID SEARCH: до {max_combinations} комбинаций...")
            grid = {
                'min_ev': [5, 8, 10, 12],
                'min_prob': [45, 50, 52, 55, 60],
                'min_odds': [1.4, 1.5, 1.6],
                'max_odds': [2.5, 3.0, 4.0, 5.0],
                'min_xg': [1.0, 1.2, 1.5],
                'stake_pct': [1.5, 2.0, 3.0, 5.0],
            }
            results = []
            count = 0
            keys = list(grid.keys())
            values = [grid[k] for k in keys]
            for combo in itertools.product(*values):
                if count >= max_combinations: break
                params = dict(zip(keys, combo))
                params.update({'max_ev': 500, 'max_prob': 100,
                               'max_xg': 4.0,
                               'bet_types': [], 'leagues': [], 'start_bank': 1000})
                if params['min_odds'] >= params['max_odds']: continue
                try:
                    res = self.simulate(params, use_history=True, use_cache=True)
                except Exception:
                    continue
                count += 1
                if res['total_bets'] < min_bets: continue
                results.append({
                    'params': params, 'total_bets': res['total_bets'],
                    'wins': res['wins'], 'losses': res['losses'],
                    'profit': res['profit'], 'roi': res['roi'],
                    'winrate': res['winrate'], 'max_drawdown': res['max_drawdown'],
                    'end_bank': res['end_bank'],
                })
            results.sort(key=lambda x: x['roi'], reverse=True)
            top = results[:5]
            logger.info(f"🎯 GRID SEARCH: проверено {count}, найдено {len(results)}")
            if top:
                best = top[0]
                try:
                    p = best['params']
                    send_telegram(
                        f"🎯 <b>GRID SEARCH ЗАВЕРШЁН</b>\n\n"
                        f"Проверено: {count}\nНайдено: {len(results)}\n\n"
                        f"🏆 <b>ЛУЧШАЯ СТРАТЕГИЯ:</b>\n"
                        f"📊 ROI: {best['roi']}%\n"
                        f"📈 Прибыль: ${best['profit']:.2f}\n"
                        f"🎲 Ставок: {best['total_bets']}\n"
                        f"🎯 Winrate: {best['winrate']}%\n"
                        f"📉 Просадка: {best['max_drawdown']}%\n\n"
                        f"⚙️ Параметры:\n"
                        f"• Min EV: {p['min_ev']}%\n"
                        f"• Min Prob: {p['min_prob']}%\n"
                        f"• Кэф: {p['min_odds']}-{p['max_odds']}\n"
                        f"• Ставка: {p['stake_pct']}% банка"
                    )
                except Exception as e:
                    logger.error(f"Telegram notify grid: {e}")
            return {'total_checked': count, 'total_valid': len(results), 'top': top}
        except Exception as e:
            logger.error(f"grid_search: {e}")
            return {'total_checked': 0, 'total_valid': 0, 'top': []}


strategy_simulator = StrategySimulator()


# === КОНЕЦ ЧАСТИ 1/3 ===

# ============================================================
# main.py — ЧАСТЬ 2/3 (v23.2 — Value Fix + Trusted Odds + Batch Update)
# Стратегии, 6 потоков поиска, обновление результатов
# ============================================================

# ============================================================
# ★ TRAIN/TEST МЕТОДЫ (Без изменений, работают отлично)
# ============================================================

def _tt_split_data(self, all_matches, test_size=0.3):
    """Разделяет данные на train и test по времени."""
    def sort_key(m):
        mt = m.get('match_time', '') or ''
        try:
            return datetime.strptime(mt, "%d.%m.%Y %H:%M")
        except Exception:
            try:
                return datetime.strptime(mt.split()[0], "%Y-%m-%d")
            except Exception:
                return datetime(1970, 1, 1)

    sorted_matches = sorted(all_matches, key=sort_key)
    split_idx = int(len(sorted_matches) * (1 - test_size))

    if split_idx < 3:
        split_idx = max(3, len(sorted_matches) // 2)

    train = sorted_matches[:split_idx]
    test = sorted_matches[split_idx:]

    logger.info(
        f"🎓 Train/Test split: train={len(train)}, "
        f"test={len(test)} (test_size={test_size})"
    )
    return train, test


def _tt_simulate_subset(self, matches, params):
    """Симуляция на подмножестве БЕЗ подглядывания в историю."""
    start_bank = float(params.get('start_bank', 1000))
    stake_pct = float(params.get('stake_pct', 2)) / 100
    bank = start_bank
    peak_bank = start_bank
    max_drawdown = 0
    wins = losses = pushes = 0
    total_staked = 0
    bets_log = []

    for m in matches:
        bb = m.get('best_bet', {})
        odds = bb.get('odds', 0) or 0
        if odds < 1.01 or bank <= 0:
            continue
        stake = round(bank * stake_pct, 2)
        if stake < 1:
            continue

        result = m.get('result')
        if result in (None, 'pending'):
            continue

        if result == 'win':
            profit = round(stake * (odds - 1), 2)
            wins += 1
        elif result == 'loss':
            profit = -stake
            losses += 1
        elif result == 'push':
            profit = 0
            pushes += 1
        else:
            continue

        bank += profit
        total_staked += stake
        peak_bank = max(peak_bank, bank)
        drawdown = ((peak_bank - bank) / peak_bank * 100) if peak_bank > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

        bets_log.append({
            'home': m.get('home'), 'away': m.get('away'),
            'league': m.get('league'),
            'match_time': m.get('match_time'),
            'bet': bb.get('label'), 'odds': odds, 'stake': stake,
            'result': result, 'profit': profit,
            'bank_after': round(bank, 2),
        })

    total_bets = wins + losses + pushes
    profit_total = round(bank - start_bank, 2)
    roi = (profit_total / total_staked * 100) if total_staked > 0 else 0
    winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    return {
        'total_bets': total_bets,
        'wins': wins, 'losses': losses, 'pushes': pushes,
        'total_staked': round(total_staked, 2),
        'profit': profit_total,
        'roi': round(roi, 1),
        'winrate': round(winrate, 1),
        'start_bank': start_bank,
        'end_bank': round(bank, 2),
        'max_drawdown': round(max_drawdown, 1),
        'bets': bets_log[:50],
    }


def _tt_collect_all_matches(self):
    """Собирает и дедуплицирует все матчи (кэш + история)."""
    all_matches = []

    try:
        cache = storage.load_cache()
        all_matches.extend(cache.get('all_analyzed', []))
        all_matches.extend(cache.get('top_matches', []))
    except Exception as e:
        logger.error(f"_collect_all_matches_for_tt cache: {e}")

    try:
        history = storage.load_history()
        for h in history:
            if h.get('result') not in ('win', 'loss', 'push'):
                continue
            all_matches.append({
                'home': h.get('home'),
                'away': h.get('away'),
                'league': h.get('league'),
                'match_time': h.get('date', ''),
                'fixture_id': h.get('fixture_id'),
                'total_xg': 0,
                'best_bet': {
                    'type': (h.get('bet') or '').lower(),
                    'label': h.get('bet', ''),
                    'odds': h.get('odds', 0),
                    'ev': h.get('ev', 0),
                    'prob': h.get('prob', 0),
                },
                'result': h.get('result'),
                'profit_real': h.get('profit', 0),
                'from_history': True,
            })
    except Exception as e:
        logger.error(f"_collect_all_matches_for_tt history: {e}")

    seen = set()
    unique = []
    for m in all_matches:
        key = f"{m.get('home')}_{m.get('away')}_{m.get('match_time', '')}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    logger.info(f"📦 Собрано уникальных матчей: {len(unique)}")
    return unique


def _tt_apply_filters(self, matches, params):
    """Применяет фильтры параметров к списку матчей."""
    filtered = []
    for m in matches:
        bb = m.get('best_bet', {})
        if not bb:
            continue
        ev = bb.get('ev', 0) or 0
        prob = bb.get('prob', 0) or 0
        odds = bb.get('odds', 0) or 0
        bt = (bb.get('type') or '').lower()
        total_xg = m.get('total_xg', 0) or 0
        league = m.get('league', '') or ''

        if ev < params.get('min_ev', -100): continue
        if ev > params.get('max_ev', 999): continue
        if prob < params.get('min_prob', 0): continue
        if prob > params.get('max_prob', 100): continue
        if odds < params.get('min_odds', 0): continue
        if odds > params.get('max_odds', 999): continue
        if total_xg > 0:
            if total_xg < params.get('min_xg', 0): continue
            if total_xg > params.get('max_xg', 99): continue

        bet_types = params.get('bet_types') or []
        if bet_types and bt not in [b.lower() for b in bet_types]: continue

        leagues = params.get('leagues') or []
        if leagues and league not in leagues: continue

        filtered.append(m)
    return filtered


# ============================================================
# ★ GRID SEARCH + TRAIN/TEST
# ============================================================
def _tt_run_train_test(self, params, test_size=0.3):
    """Главный метод Train/Test."""
    all_matches = self._tt_collect_all_matches()
    filtered = self._tt_apply_filters(all_matches, params)

    if len(filtered) < 10:
        return {
            'error': (f'Недостаточно данных: {len(filtered)} матчей. '
                      f'Нужно минимум 10 для Train/Test.'),
            'train': None,
            'test': None,
        }

    train, test = self._tt_split_data(filtered, test_size)

    if len(train) < 3 or len(test) < 3:
        return {
            'error': (f'Недостаточно данных после split: '
                      f'train={len(train)}, test={len(test)}.'),
            'train': None,
            'test': None,
        }

    train_result = self._tt_simulate_subset(train, params)
    test_result = self._tt_simulate_subset(test, params)

    gap = round(train_result['roi'] - test_result['roi'], 1)

    if gap > 30:
        verdict = '🔴 СИЛЬНЫЙ OVERFITTING'
    elif gap > 15:
        verdict = '🟡 ВОЗМОЖЕН OVERFITTING'
    elif gap > 5:
        verdict = '🟠 НЕБОЛЬШОЙ РАЗРЫВ'
    elif gap >= -5:
        verdict = '✅ СТАБИЛЬНАЯ СТРАТЕГИЯ'
    else:
        verdict = '🔵 TEST ЛУЧШЕ TRAIN (хорошо!)'

    logger.info(
        f"🎓 TRAIN/TEST: train_roi={train_result['roi']}%, "
        f"test_roi={test_result['roi']}%, gap={gap}% | {verdict}"
    )

    return {
        'train': train_result,
        'test': test_result,
        'gap': gap,
        'verdict': verdict,
        'total_filtered': len(filtered),
        'train_count': len(train),
        'test_count': len(test),
    }


def _tt_grid_search_train_test(self, max_combinations=100, min_bets=30, test_size=0.3):
    """Grid Search + Train/Test."""
    try:
        logger.info(
            f"🔍 GRID SEARCH + TRAIN/TEST: до {max_combinations} комбинаций, "
            f"min_bets={min_bets}, test_size={test_size}"
        )

        all_matches = self._tt_collect_all_matches()
        if len(all_matches) < 30:
            return {
                'error': f'Недостаточно данных: {len(all_matches)}',
                'total_checked': 0, 'total_valid': 0, 'top': [],
            }

        grid = {
            'min_ev': [5, 8, 10, 12, 15],
            'min_prob': [45, 50, 52, 55, 60],
            'min_odds': [1.3, 1.4, 1.5, 1.6],
            'max_odds': [2.5, 3.0, 4.0, 5.0, 6.0],
            'stake_pct': [1.5, 2.0, 3.0],
        }

        results = []
        count = 0
        seen_signatures = set()
        seen_results = set()
        keys = list(grid.keys())
        values = [grid[k] for k in keys]

        for combo in itertools.product(*values):
            if count >= max_combinations:
                break
            params = dict(zip(keys, combo))
            params.update({
                'max_ev': 500, 'max_prob': 100,
                'min_xg': 0, 'max_xg': 99,
                'bet_types': [], 'leagues': [],
                'start_bank': 1000,
            })
            if params['min_odds'] >= params['max_odds']:
                continue

            try:
                filtered = self._tt_apply_filters(all_matches, params)
                if len(filtered) < min_bets * 2:
                    continue

                train, test = self._tt_split_data(filtered, test_size)
                if len(train) < min_bets or len(test) < 5:
                    continue

                train_sig = tuple(sorted(
                    (m.get('home'), m.get('away'), m.get('match_time', ''))
                    for m in train
                ))
                if train_sig in seen_signatures:
                    continue
                seen_signatures.add(train_sig)

                train_res = self._tt_simulate_subset(train, params)
                test_res = self._tt_simulate_subset(test, params)

                if train_res['total_bets'] < min_bets:
                    continue
                if test_res['total_bets'] < 5:
                    continue

                result_sig = (
                    train_res['total_bets'],
                    train_res['wins'],
                    round(train_res['roi'], 1),
                    round(test_res['roi'], 1),
                )
                if result_sig in seen_results:
                    continue
                seen_results.add(result_sig)

                gap = round(train_res['roi'] - test_res['roi'], 1)
                count += 1

                penalty = max(0, gap) * 0.5
                score = test_res['roi'] - penalty

                results.append({
                    'params': params,
                    'total_bets': train_res['total_bets'] + test_res['total_bets'],
                    'train_bets': train_res['total_bets'],
                    'test_bets': test_res['total_bets'],
                    'train_roi': train_res['roi'],
                    'test_roi': test_res['roi'],
                    'gap': gap,
                    'train_wr': train_res['winrate'],
                    'test_wr': test_res['winrate'],
                    'train_profit': train_res['profit'],
                    'test_profit': test_res['profit'],
                    'train_dd': train_res['max_drawdown'],
                    'test_dd': test_res['max_drawdown'],
                    'score': round(score, 1),
                })
            except Exception as e:
                logger.debug(f"grid_tt combo error: {e}")
                continue

        results.sort(key=lambda x: x['score'], reverse=True)
        top = results[:5]

        logger.info(
            f"🎯 GRID SEARCH + TT: проверено {count}, "
            f"уникальных {len(results)}, показано {len(top)}"
        )

        if top:
            best = top[0]
            try:
                send_telegram(
                    f"🎓 <b>GRID SEARCH + TRAIN/TEST</b>\n\n"
                    f"Проверено уникальных: {count}\n\n"
                    f"🏆 <b>ЛУЧШАЯ:</b>\n"
                    f"🎓 Train ROI: {best['train_roi']}% ({best['train_bets']} ставок)\n"
                    f"🧪 Test ROI: {best['test_roi']}% ({best['test_bets']} ставок)\n"
                    f"📊 Gap: {best['gap']}%\n"
                    f"🎯 Test WR: {best['test_wr']}%\n\n"
                    f"⚙️ Параметры:\n"
                    f"• Min EV: {best['params']['min_ev']}%\n"
                    f"• Min Prob: {best['params']['min_prob']}%\n"
                    f"• Кэф: {best['params']['min_odds']}-{best['params']['max_odds']}\n"
                    f"• Ставка: {best['params']['stake_pct']}%"
                )
            except Exception as e:
                logger.error(f"Telegram grid_tt: {e}")

        return {
            'total_checked': count,
            'total_valid': len(results),
            'top': top,
        }
    except Exception as e:
        logger.exception(f"grid_search_train_test: {e}")
        return {
            'total_checked': 0, 'total_valid': 0, 'top': [],
            'error': str(e),
        }


# ============================================================
# ★ 3-WAY SPLIT
# ============================================================
def _tt_split_data_3way(self, all_matches, test_size=0.2, valid_size=0.2):
    """Train/Validate/Test по времени."""
    def sort_key(m):
        mt = m.get('match_time', '') or ''
        try:
            return datetime.strptime(mt, "%d.%m.%Y %H:%M")
        except Exception:
            try:
                return datetime.strptime(mt.split()[0], "%Y-%m-%d")
            except Exception:
                return datetime(1970, 1, 1)

    sorted_matches = sorted(all_matches, key=sort_key)
    n = len(sorted_matches)

    test_count = int(n * test_size)
    valid_count = int(n * valid_size)
    train_count = n - test_count - valid_count

    if train_count < 3:
        train_count = max(3, n - 6)
    if valid_count < 2:
        valid_count = max(2, (n - train_count - 2) // 2)
    if test_count < 2:
        test_count = max(2, n - train_count - valid_count)

    train = sorted_matches[:train_count]
    valid = sorted_matches[train_count:train_count + valid_count]
    test = sorted_matches[train_count + valid_count:]

    logger.info(
        f"🎓 3-way split: train={len(train)}, "
        f"valid={len(valid)}, test={len(test)} "
        f"(test_size={test_size}, valid_size={valid_size})"
    )
    return train, valid, test


def _tt_run_3way_split(self, params, test_size=0.2, valid_size=0.2):
    """Запускает Train/Validate/Test (3-way split)."""
    all_matches = self._tt_collect_all_matches()
    filtered = self._tt_apply_filters(all_matches, params)

    if len(filtered) < 15:
        return {
            'error': (f'Недостаточно данных: {len(filtered)} матчей. '
                      f'Нужно минимум 15 для 3-way Split.'),
            'train': None, 'valid': None, 'test': None,
        }

    train, valid, test = self._tt_split_data_3way(
        filtered, test_size=test_size, valid_size=valid_size
    )

    if len(train) < 3 or len(valid) < 2 or len(test) < 2:
        return {
            'error': (f'Недостаточно данных после split: '
                      f'train={len(train)}, valid={len(valid)}, test={len(test)}.'),
            'train': None, 'valid': None, 'test': None,
        }

    train_result = self._tt_simulate_subset(train, params)
    valid_result = self._tt_simulate_subset(valid, params)
    test_result = self._tt_simulate_subset(test, params)

    train_roi = train_result['roi']
    valid_roi = valid_result['roi']
    test_roi = test_result['roi']

    max_roi = max(train_roi, valid_roi, test_roi)
    min_roi = min(train_roi, valid_roi, test_roi)
    spread = round(max_roi - min_roi, 1)

    oos_roi = round((valid_roi + test_roi) / 2, 1)
    gap_train_oos = round(train_roi - oos_roi, 1)

    if gap_train_oos < 5 and abs(spread) < 10 and oos_roi > 0:
        verdict = '✅ СТАБИЛЬНАЯ СТРАТЕГИЯ'
        verdict_color = 'green'
    elif gap_train_oos < 5 and oos_roi > 0:
        verdict = '🟢 НЕБОЛЬШОЙ РАЗБРОС (но стабильно)'
        verdict_color = 'green'
    elif gap_train_oos > 25:
        verdict = '🔴 СИЛЬНЫЙ OVERFITTING'
        verdict_color = 'red'
    elif gap_train_oos > 15:
        verdict = '🟡 ВОЗМОЖЕН OVERFITTING'
        verdict_color = 'gold'
    elif gap_train_oos > 5:
        verdict = '🟠 НЕБОЛЬШОЙ РАЗРЫВ'
        verdict_color = 'orange'
    elif oos_roi > train_roi and spread < 25:
        verdict = '🔵 OOS ЛУЧШЕ TRAIN (хорошо!)'
        verdict_color = 'blue'
    elif spread > 25:
        verdict = '⚪ НЕСТАБИЛЬНО (большой разброс)'
        verdict_color = 'gray'
    else:
        verdict = '⚪ СМЕШАННЫЕ СИГНАЛЫ'
        verdict_color = 'gray'

    logger.info(
        f"🎓 3-WAY: train={train_roi}%, valid={valid_roi}%, "
        f"test={test_roi}%, spread={spread}%, oos={oos_roi}% | {verdict}"
    )

    return {
        'train': train_result,
        'valid': valid_result,
        'test': test_result,
        'gap': gap_train_oos,
        'gap_valid': round(train_roi - valid_roi, 1),
        'gap_test': round(train_roi - test_roi, 1),
        'spread': spread,
        'oos_roi': oos_roi,
        'verdict': verdict,
        'verdict_color': verdict_color,
        'total_filtered': len(filtered),
        'train_count': len(train),
        'valid_count': len(valid),
        'test_count': len(test),
    }


def _tt_grid_search_3way(self, max_combinations=100, min_bets=30,
                          test_size=0.2, valid_size=0.2):
    """Grid Search с 3-way split."""
    try:
        logger.info(
            f"🔍 GRID SEARCH + 3-WAY: до {max_combinations} комбинаций, "
            f"min_bets={min_bets}, test_size={test_size}, valid_size={valid_size}"
        )

        all_matches = self._tt_collect_all_matches()
        if len(all_matches) < 45:
            return {
                'error': f'Недостаточно данных: {len(all_matches)}. Нужно ≥45 для 3-way.',
                'total_checked': 0, 'total_valid': 0, 'top': [],
            }

        grid = {
            'min_ev': [5, 8, 10, 12, 15],
            'min_prob': [45, 50, 52, 55, 60],
            'min_odds': [1.3, 1.4, 1.5, 1.6],
            'max_odds': [2.5, 3.0, 4.0, 5.0, 6.0],
            'stake_pct': [1.5, 2.0, 3.0],
        }

        results = []
        count = 0
        seen_signatures = set()
        seen_results = set()
        keys = list(grid.keys())
        values = [grid[k] for k in keys]

        for combo in itertools.product(*values):
            if count >= max_combinations:
                break
            params = dict(zip(keys, combo))
            params.update({
                'max_ev': 500, 'max_prob': 100,
                'min_xg': 0, 'max_xg': 99,
                'bet_types': [], 'leagues': [],
                'start_bank': 1000,
            })
            if params['min_odds'] >= params['max_odds']:
                continue

            try:
                filtered = self._tt_apply_filters(all_matches, params)
                if len(filtered) < min_bets * 3:
                    continue

                train, valid, test = self._tt_split_data_3way(
                    filtered, test_size=test_size, valid_size=valid_size
                )
                if len(train) < min_bets or len(valid) < 5 or len(test) < 5:
                    continue

                train_sig = tuple(sorted(
                    (m.get('home'), m.get('away'), m.get('match_time', ''))
                    for m in train
                ))
                if train_sig in seen_signatures:
                    continue
                seen_signatures.add(train_sig)

                train_res = self._tt_simulate_subset(train, params)
                valid_res = self._tt_simulate_subset(valid, params)
                test_res = self._tt_simulate_subset(test, params)

                if train_res['total_bets'] < min_bets:
                    continue
                if valid_res['total_bets'] < 5:
                    continue
                if test_res['total_bets'] < 5:
                    continue

                result_sig = (
                    train_res['total_bets'],
                    train_res['wins'],
                    round(train_res['roi'], 1),
                    round(valid_res['roi'], 1),
                    round(test_res['roi'], 1),
                )
                if result_sig in seen_results:
                    continue
                seen_results.add(result_sig)

                train_roi = train_res['roi']
                valid_roi = valid_res['roi']
                test_roi = test_res['roi']
                oos_roi = (valid_roi + test_roi) / 2
                gap_train_oos = train_roi - oos_roi
                spread = max(train_roi, valid_roi, test_roi) - min(train_roi, valid_roi, test_roi)

                penalty = max(0, gap_train_oos) * 0.5 + spread * 0.2
                score = test_roi - penalty
                count += 1

                results.append({
                    'params': params,
                    'total_bets': train_res['total_bets'] + valid_res['total_bets'] + test_res['total_bets'],
                    'train_bets': train_res['total_bets'],
                    'valid_bets': valid_res['total_bets'],
                    'test_bets': test_res['total_bets'],
                    'train_roi': train_roi,
                    'valid_roi': valid_roi,
                    'test_roi': test_roi,
                    'oos_roi': round(oos_roi, 1),
                    'gap_train_oos': round(gap_train_oos, 1),
                    'spread': round(spread, 1),
                    'train_wr': train_res['winrate'],
                    'valid_wr': valid_res['winrate'],
                    'test_wr': test_res['winrate'],
                    'train_profit': train_res['profit'],
                    'valid_profit': valid_res['profit'],
                    'test_profit': test_res['profit'],
                    'score': round(score, 1),
                })
            except Exception as e:
                logger.debug(f"grid_3way combo error: {e}")
                continue

        results.sort(key=lambda x: x['score'], reverse=True)
        top = results[:5]

        logger.info(
            f"🎯 GRID SEARCH + 3-WAY: проверено {count}, "
            f"уникальных {len(results)}, показано {len(top)}"
        )

        if top:
            best = top[0]
            try:
                send_telegram(
                    f"🎓 <b>GRID SEARCH + 3-WAY SPLIT</b>\n\n"
                    f"Проверено: {count}\n\n"
                    f"🏆 <b>ЛУЧШАЯ:</b>\n"
                    f"🎓 Train: {best['train_roi']}% ({best['train_bets']} ст.)\n"
                    f"📊 Valid: {best['valid_roi']}% ({best['valid_bets']} ст.)\n"
                    f"🧪 Test: {best['test_roi']}% ({best['test_bets']} ст.)\n"
                    f"📈 OOS: {best['oos_roi']}% • Spread: {best['spread']}%\n\n"
                    f"⚙️ Параметры:\n"
                    f"• Min EV: {best['params']['min_ev']}%\n"
                    f"• Min Prob: {best['params']['min_prob']}%\n"
                    f"• Кэф: {best['params']['min_odds']}-{best['params']['max_odds']}\n"
                    f"• Ставка: {best['params']['stake_pct']}%"
                )
            except Exception as e:
                logger.error(f"Telegram 3way: {e}")

        return {
            'total_checked': count,
            'total_valid': len(results),
            'top': top,
        }
    except Exception as e:
        logger.exception(f"grid_search_3way: {e}")
        return {
            'total_checked': 0, 'total_valid': 0, 'top': [],
            'error': str(e),
        }


# ============================================================
# ★ ПРИВЯЗКА МЕТОДОВ К StrategySimulator
# ============================================================
if not hasattr(strategy_simulator, '_tt_split_data'):
    StrategySimulator._tt_split_data = _tt_split_data
    StrategySimulator._tt_simulate_subset = _tt_simulate_subset
    StrategySimulator._tt_collect_all_matches = _tt_collect_all_matches
    StrategySimulator._tt_apply_filters = _tt_apply_filters
    StrategySimulator._tt_run_train_test = _tt_run_train_test
    StrategySimulator._tt_grid_search_train_test = _tt_grid_search_train_test

    StrategySimulator.run_train_test = _tt_run_train_test
    StrategySimulator.grid_search_train_test = _tt_grid_search_train_test
    StrategySimulator.split_data = _tt_split_data
    StrategySimulator._simulate_subset = _tt_simulate_subset
    StrategySimulator._collect_all_matches_for_tt = _tt_collect_all_matches
    StrategySimulator._apply_filters = _tt_apply_filters

    StrategySimulator._tt_split_data_3way = _tt_split_data_3way
    StrategySimulator.split_data_3way = _tt_split_data_3way
    StrategySimulator.run_3way_split = _tt_run_3way_split
    StrategySimulator.grid_search_3way = _tt_grid_search_3way
