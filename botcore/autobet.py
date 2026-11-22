# ============================================================
# botcore/autobet.py — Автоставки (AutoBetManager) и расчёт результата ставки
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

__all__ = [
    'AutoBetManager',
    'autobet_manager',
    'determine_bet_result',
]


# ============================================================
# AUTO BET MANAGER
# ============================================================
class AutoBetManager:
    DEFAULT_BANK = 1000.0
    DEFAULT_STAKE_PCT = 0.02

    def __init__(self):
        self.enabled = True
        self.bank = self.DEFAULT_BANK
        self.stake_pct = self.DEFAULT_STAKE_PCT

    def get_state(self):
        state = storage.autobet_get_state(default_bank=self.DEFAULT_BANK)
        state['stake_pct'] = self.stake_pct * 100
        return state

    def place_bet(self, match_data):
        if not self.enabled:
            return False
        try:
            state = self.get_state()
            current_bank = state['bank']
            if current_bank <= 0:
                return False
            best_bet = match_data.get('best_bet', {})
            if not best_bet or best_bet.get('odds', 0) < 1.01:
                return False
            if not best_bet.get('odds_updated'):
                return False
            stake = round(current_bank * self.stake_pct, 2)
            if stake < 1:
                return False
            match_key = (f"{match_data.get('home')}_{match_data.get('away')}_"
                         f"{match_data.get('match_time', '')}")
            inserted = storage.autobet_insert(
                match_key=match_key,
                home=match_data.get('home', ''),
                away=match_data.get('away', ''),
                league=match_data.get('league', ''),
                match_time=match_data.get('match_time', ''),
                fixture_id=match_data.get('fixture_id'),
                bet_label=best_bet.get('label', '—'),
                bet_type=best_bet.get('type', ''),
                odds=best_bet.get('odds', 0),
                stake=stake,
                ev=best_bet.get('ev', 0),
                prob=best_bet.get('prob', 0),
                bookmaker=best_bet.get('bookmaker', '—'),
            )
            if inserted:
                logger.info(f"💸 АВТОСТАВКА: {match_data.get('home')} vs {match_data.get('away')}")
                try:
                    src = match_data.get('source', '')
                    src_emoji = '💎' if src == 'value' else ('🔥' if src == 'tm25_premium' else '🎯')
                    send_telegram(
                        f"💸 <b>НОВАЯ АВТОСТАВКА</b>\n\n"
                        f"{src_emoji} {match_data.get('home')} vs {match_data.get('away')}\n"
                        f"🎯 {best_bet.get('label')} @ {best_bet.get('odds')}\n"
                        f"📈 EV: {best_bet.get('ev', 0)}% | Prob: {best_bet.get('prob', 0)}%\n"
                        f"💰 ${stake} | 💎 ${state['bank']:.2f}"
                    )
                except Exception as e:
                    logger.error(f"Telegram notify place: {e}")
            return inserted
        except Exception as e:
            logger.error(f"AutoBetManager.place_bet: {e}")
            return False

    def place_bets_from_cache(self):
        if not self.enabled:
            return 0
        try:
            cache = storage.load_cache()
            top = cache.get('top_matches', [])
            VALID_SOURCES = ('Football API', 'Line Analysis',
                 'Football API (X2)', 'Football API (1X)',
                 'tm25_premium', 'tm25_standard', 'value', 'btts', 'stats')
            valid_matches = []
            for m in top:
                bb = m.get('best_bet', {})
                if bb.get('odds_updated') or bb.get('odds_source') in VALID_SOURCES:
                    valid_matches.append(m)
            if not valid_matches:
                logger.info("⏭️ Автоставки: нет матчей с реальными кэфами")
                return 0
            placed = 0
            for m in valid_matches:
                if self.place_bet(m):
                    placed += 1
            if placed > 0:
                logger.info(f"💸 Автоставок размещено: {placed}")
            return placed
        except Exception as e:
            logger.error(f"place_bets_from_cache: {e}")
            return 0

    def settle_pending(self):
        try:
            pending = storage.autobet_get_pending()
            updated = 0
            live_updated = 0
            for b in pending:
                fid = b.get('fixture_id')
                home = b.get('home', '')
                away = b.get('away', '')
                if not fid:
                    fid = football_api.find_fixture_by_teams(home, away)
                    if fid:
                        try:
                            bets_all = storage.autobet_load_all()
                            for bb in bets_all:
                                if bb.get('match_key') == b.get('match_key'):
                                    bb['fixture_id'] = fid
                                    break
                            storage.autobet_save_all(bets_all)
                        except Exception as e:
                            logger.error(f"Ошибка сохранения fixture_id: {e}")
                if not fid:
                    continue

                md = football_api.get_match_result(fid)
                if not md:
                    continue
                if md.get('goals', {}).get('home') is None:
                    continue

                hg = md['goals']['home']
                ag = md['goals']['away']
                status = md.get('status', 'NS')
                ht = md.get('halftime', {}) or {}
                match_time_str = b.get('match_time', '')

                force_final = is_force_final(match_time_str, status)

                if not md.get('is_final', False) and not force_final:
                    if md.get('is_live', False):
                        storage.autobet_update_live(
                            match_key=b.get('match_key'),
                            home_goals=hg, away_goals=ag,
                            status=status, minute=md.get('minute', 0),
                            halftime_home=ht.get('home'),
                            halftime_away=ht.get('away'),
                        )
                        live_updated += 1
                    continue

                result = determine_bet_result(b.get('bet_type', ''), hg, ag)
                if result == 'pending':
                    continue
                odds = float(b.get('odds', 0))
                stake = float(b.get('stake', 0))
                if result == 'win':
                    profit = round(stake * (odds - 1), 2)
                elif result == 'loss':
                    profit = -stake
                else:
                    profit = 0
                match_key = b.get('match_key')
                storage.autobet_settle(
                    match_key=match_key, result=result, profit=profit,
                    home_goals=hg, away_goals=ag,
                    halftime_home=ht.get('home'), halftime_away=ht.get('away'),
                )
                updated += 1
                try:
                    emoji = "✅" if result == 'win' else "❌" if result == 'loss' else "➖"
                    profit_str = f"+${profit:.2f}" if profit > 0 else (f"-${abs(profit):.2f}" if profit < 0 else "$0")
                    st = self.get_state()
                    ht_str = f" (1-й: {ht.get('home')}-{ht.get('away')})" if ht.get('home') is not None else ""
                    send_telegram(
                        f"{emoji} <b>АВТОСТАВКА: {result.upper()}</b>\n\n"
                        f"🏟️ {home} vs {away}\n"
                        f"⚽ Счёт: {hg}-{ag}{ht_str}\n"
                        f"💰 Прибыль: {profit_str}\n"
                        f"💎 Банк: ${st['bank']:.2f}\n"
                        f"📊 ROI: {st['roi']}% | WIN: {st['winrate']}%"
                    )
                except Exception as e:
                    logger.error(f"Telegram notify settle: {e}")
            if updated > 0:
                logger.info(f"✅ Автоставки обновлены (FT): {updated}")
            if live_updated > 0:
                logger.info(f"⚽ Live-счёт обновлён: {live_updated}")
            return updated
        except Exception as e:
            logger.error(f"AutoBetManager.settle_pending: {e}")
            return 0

    def update_live_scores(self):
        try:
            pending = storage.autobet_get_pending()
            updated = 0
            skipped_ns = 0
            skipped_old = 0
            now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)

            for b in pending:
                fid = b.get('fixture_id')
                if not fid:
                    continue
                match_time_str = b.get('match_time', '')
                if match_time_str and match_time_str != '?':
                    try:
                        match_dt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")
                        hours_ago = (now_msk - match_dt).total_seconds() / 3600
                        if hours_ago > 3:
                            skipped_old += 1
                            continue
                    except Exception:
                        pass
                md = football_api.get_match_result(fid)
                if not md or md.get('goals', {}).get('home') is None:
                    continue
                if md.get('is_final', False):
                    continue
                status = md.get('status', 'NS')
                if status == 'NS' or not md.get('is_live', False):
                    skipped_ns += 1
                    continue
                hg = md['goals']['home']
                ag = md['goals']['away']
                minute = md.get('minute', 0)
                ht = md.get('halftime', {}) or {}
                storage.autobet_update_live(
                    match_key=b.get('match_key'),
                    home_goals=hg, away_goals=ag,
                    status=status, minute=minute,
                    halftime_home=ht.get('home'),
                    halftime_away=ht.get('away'),
                )
                updated += 1
            if updated > 0:
                logger.info(f"⚽ Live-счёт обновлён для {updated} матчей")
            return updated
        except Exception as e:
            logger.error(f"update_live_scores: {e}")
            return 0

    def compute_clv_for_settled(self):
        try:
            candidates = storage.autobet_get_pending_clv()
            if not candidates:
                return 0
            updated = 0
            for b in candidates:
                fid = b.get('fixture_id')
                if not fid:
                    continue
                bt = (b.get('bet_type') or '').lower()
                if bt == 'under' or 'тм' in bt:
                    mkt, sel = 'O/U 2.5', 'Under'
                elif bt == 'over' or 'тб' in bt:
                    mkt, sel = 'O/U 2.5', 'Over'
                elif bt == 'x2':
                    mkt, sel = 'DC', 'X2'
                elif bt == '1x':
                    mkt, sel = 'DC', '1X'
                elif bt in ('п1', '1', 'home'):
                    mkt, sel = '1X2', '1'
                elif bt in ('п2', '2', 'away'):
                    mkt, sel = '1X2', '2'
                elif bt == 'draw':
                    mkt, sel = '1X2', 'X'
                else:
                    mkt, sel = '1X2', '1'
                match_time_str = b.get('match_time', '')
                before_iso = None
                if match_time_str and match_time_str != '?':
                    try:
                        match_dt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")
                        match_dt = match_dt - timedelta(minutes=10)
                        before_iso = match_dt.isoformat()
                    except Exception:
                        pass
                if not before_iso:
                    storage.autobet_update_clv(match_key=b.get('match_key'),
                                                closing_odds=None, clv=None)
                    continue
                snapshot = storage.get_latest_odds_before(fid, mkt, sel, before_iso)
                if not snapshot or not snapshot.get('odds'):
                    storage.autobet_update_clv(match_key=b.get('match_key'),
                                                closing_odds=None, clv=None)
                    continue
                our_odds = float(b.get('odds', 0))
                closing = float(snapshot['odds'])
                if our_odds <= 0 or closing <= 0:
                    continue
                clv = ((our_odds / closing) - 1) * 100
                storage.autobet_update_clv(
                    match_key=b.get('match_key'),
                    closing_odds=closing,
                    clv=round(clv, 2)
                )
                updated += 1
            if updated > 0:
                logger.info(f"📊 CLV обновлён для {updated} автоставок")
            return updated
        except Exception as e:
            logger.error(f"compute_clv_for_settled: {e}")
            return 0

    def reset(self):
        return storage.autobet_reset()


autobet_manager = AutoBetManager()


# ============================================================
# ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА СТАВКИ
# ============================================================
def determine_bet_result(bet_type, home_goals, away_goals):
    total = home_goals + away_goals
    bt = (bet_type or '').lower()
    if 'п1' in bt or bt == '1':
        return 'win' if home_goals > away_goals else ('push' if home_goals == away_goals else 'loss')
    if 'п2' in bt or bt == '2':
        return 'win' if away_goals > home_goals else ('push' if home_goals == away_goals else 'loss')
    if '1x' in bt:
        return 'win' if home_goals >= away_goals else 'loss'
    if 'x2' in bt:
        return 'win' if away_goals >= home_goals else 'loss'
    if 'обз' in bt or 'btts' in bt:
        return 'win' if home_goals > 0 and away_goals > 0 else 'loss'
    if 'ничья' in bt or bt == 'x' or '(x)' in bt:
        return 'win' if home_goals == away_goals else 'loss'
    if 'андердог' in bt:
        if '(д)' in bt: return 'win' if home_goals > away_goals else 'loss'
        elif '(г)' in bt: return 'win' if away_goals > home_goals else 'loss'
        return 'pending'
    if 'тм 2.5' in bt or 'under' in bt or 'тм2.5' in bt:
        return 'win' if total < 2.5 else 'loss'
    if 'тб 2.5' in bt or 'over' in bt or 'тб2.5' in bt:
        return 'win' if total > 2.5 else 'loss'
    return 'pending'
