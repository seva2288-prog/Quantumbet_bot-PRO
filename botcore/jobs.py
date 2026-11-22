# ============================================================
# botcore/jobs.py — Планировщик, бэкапы, уведомления, StrategyTester, BotState
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
from botcore.lab_tasks import *  # noqa: F401,F403
from botcore.calib_tools import *  # noqa: F401,F403

__all__ = [
    'auto_update_results',
    'safe_job',
    'schedule_updates',
    'schedule_notifications',
    'schedule_performance_report',
    'schedule_autobet',
    'MAX_BACKUPS',
    'cleanup_old_backups',
    'cleanup_old_data',
    'send_auto_backup',
    'schedule_auto_backup',
    'NotificationSystem',
    'notification_system',
    'StrategyTester',
    'strategy_tester',
    'BotState',
    'bot_state',
    'load_bot_settings',
]


# ============================================================
# ★ ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def auto_update_results():
    res = update_pending_bets()
    x2 = update_x2_results()
    ft = res.get('ft', 0)
    live = res.get('live', 0)
    if ft > 0:
        send_telegram(f"🔄 Авто-обновление: {ft} результатов")
    if x2 > 0:
        send_telegram(f"🎯 X2-результатов обновлено: {x2}")
    return ft + live + x2


# === КОНЕЦ ЧАСТИ 2/3 (v23.2 — Value Fix + Trusted Odds + Batch Update) ===

# ============================================================
# main.py — ЧАСТЬ 3/3 (v23.3 — Turbo Schedulers for Ultra 75k)
# Schedulers, Webhook, API, __main__
# ★ Обновлены интервалы под 75k запросов
# ★ Добавлена защита от перегрузки Live-запросов
# ★ Все старые фиксы сохранены (CLV, Calibration, Export)
# ============================================================

# ============================================================
# SCHEDULER HELPERS
# ============================================================
def safe_job(func, name):
    def wrapper():
        try:
            logger.info(f"▶️ START: {name}")
            result = func()
            logger.info(f"✅ END: {name} | result={result}")
            return result
        except Exception as e:
            logger.exception(f"❌ FAIL: {name} | {e}")
            try:
                send_telegram(f"❌ <b>Ошибка:</b> {name}\n\n<code>{str(e)[:500]}</code>")
            except Exception:
                pass
            return None
    return wrapper


def schedule_updates():
    scheduler = BackgroundScheduler()
    # ★ 75k запросов позволяют обновлять результаты каждые 30 минут
    scheduler.add_job(
        func=safe_job(update_lab_results, "update_lab_results"),
        trigger='interval', minutes=30, id='lab_update',
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(auto_update_results, "auto_update_results"),
        trigger='interval', minutes=30, id='auto_update', # было 6 часов
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(update_anomaly_results, "update_anomaly_results"),
        trigger='interval', minutes=15, id='anomaly_update',
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.start()
    logger.info("⏰ Авто-обновление: 30м + аномалии: 15м")


def schedule_notifications():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=safe_job(notification_system.run_all_checks, "notifications"),
        trigger='interval', hours=1, id='notifications',
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.start()


def schedule_performance_report():
    def report():
        perf_monitor.print_report()
        slow = [f for f in perf_monitor.get_report() if f['avg_time'] > 3.0]
        if slow:
            msg = "⚠️ <b>МЕДЛЕННЫЕ ФУНКЦИИ</b>\n\n"
            for f in slow:
                msg += f"• {f['function']}: {f['avg_time']}с\n"
            send_telegram(msg)
        return len(slow)
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=safe_job(report, "performance_report"),
        trigger='interval', hours=6, id='perf_report',
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.start()


def schedule_autobet():
    # ★ 75k запросов: Live обновляем каждые 2-3 минуты
    live_interval = max(3, int(getattr(Config, 'LIVE_REFRESH_SEC', 10) / 3))
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=safe_job(autobet_manager.place_bets_from_cache, "autobet_place"),
        trigger='interval', minutes=30, id='autobet_place',
        replace_existing=True, max_instances=1,
        misfire_grace_time=60, coalesce=True
    )
    # ★ Settle тоже ускоряем (было 2 часа)
    scheduler.add_job(
        func=safe_job(autobet_manager.settle_pending, "autobet_settle"),
        trigger='interval', minutes=60, id='autobet_settle',
        replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    scheduler.add_job(
        func=safe_job(autobet_manager.compute_clv_for_settled, "autobet_clv"),
        trigger='interval', hours=6, id='autobet_clv',
        replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    scheduler.add_job(
        func=safe_job(autobet_manager.update_live_scores, "autobet_live_scores"),
        trigger='interval', minutes=live_interval, id='autobet_live',
        replace_existing=True, max_instances=1,
        misfire_grace_time=60, coalesce=True
    )
    scheduler.start()


MAX_BACKUPS = 1


def cleanup_old_backups():
    """Удаляет все бэкапы кроме MAX_BACKUPS последних."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        files = []
        for f in os.listdir(BACKUP_DIR):
            full = os.path.join(BACKUP_DIR, f)
            if os.path.isfile(full) and f.endswith('.zip'):
                files.append((full, os.path.getmtime(full)))
        files.sort(key=lambda x: x[1], reverse=True)
        removed = 0
        for path, _ in files[MAX_BACKUPS:]:
            try:
                os.remove(path)
                removed += 1
            except Exception as e:
                logger.error(f"Ошибка удаления {path}: {e}")
        if removed > 0:
            logger.info(f"🧹 Удалено бэкапов: {removed} (осталось {len(files) - removed})")
    except Exception as e:
        logger.error(f"❌ cleanup: {e}")


def cleanup_old_data():
    """Удаляет .bak, старые бэкапы, обрезает логи."""
    try:
        import glob
        # 1. Удаляем все .bak файлы
        for f in glob.glob(os.path.join(DATA_DIR, '*.bak')):
            try:
                os.remove(f)
                logger.info(f"🧹 Удалён: {os.path.basename(f)}")
            except Exception as e:
                logger.error(f"cleanup {f}: {e}")

        # 2. Оставляем только 1 последний бэкап
        backup_dir = os.path.join(DATA_DIR, 'backups')
        if os.path.exists(backup_dir):
            backups = sorted(
                [os.path.join(backup_dir, f) for f in os.listdir(backup_dir)],
                key=os.path.getmtime, reverse=True
            )
            for old in backups[1:]:
                try:
                    os.remove(old)
                    logger.info(f"🧹 Удалён бэкап: {os.path.basename(old)}")
                except Exception as e:
                    logger.error(f"cleanup backup {old}: {e}")

        # 3. Обрезаем matches_log.txt
        log_path = os.path.join(DATA_DIR, 'matches_log.txt')
        if os.path.exists(log_path) and os.path.getsize(log_path) > 200 * 1024:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            with open(log_path, 'w', encoding='utf-8') as f:
                f.writelines(lines[-500:])
            logger.info("🧹 Обрезан matches_log.txt")

        # 4. Логируем свободное место
        try:
            import shutil
            stat = shutil.disk_usage(DATA_DIR)
            free_mb = stat.free / (1024 * 1024)
            logger.info(f"💾 Свободно: {free_mb:.0f} MB")
        except Exception:
            pass

        return True
    except Exception as e:
        logger.exception(f"cleanup_old_data: {e}")
        return False


def send_auto_backup():
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_path = os.path.join(BACKUP_DIR, f'backup_{ts}.zip')

        items = []
        if os.path.exists('/data'):
            items.extend([
                '/data/storage',
                '/data/x2_data.json',
                '/data/bot_state.json',
                '/data/bot_settings.json',
                '/data/geocoding_cache.json',
                '/data/bot.db',
            ])
        else:
            items.extend(['data', 'bot.db', 'bot_state.json',
                          'matches_log.txt', 'bot_settings.json'])

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in items:
                if os.path.exists(item):
                    if os.path.isdir(item):
                        for root, _, files in os.walk(item):
                            for f in files:
                                full = os.path.join(root, f)
                                zf.write(full, os.path.relpath(full, '/'))

        size_kb = os.path.getsize(zip_path) / 1024
        history = storage.load_history()
        bank = storage.load_bank()
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
        with open(zip_path, 'rb') as f:
            r = requests.post(
                url,
                files={'document': (os.path.basename(zip_path), f, 'application/zip')},
                data={
                    'chat_id': Config.ADMIN_CHAT_ID,
                    'caption': (f"💾 <b>АВТОБЭКАП</b>\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                                f"📦 {size_kb:.1f} КБ\n📊 Ставок: {len(history)}\n💰 ${bank:.2f}"),
                    'parse_mode': 'HTML'
                },
                timeout=60
            )
        if r.status_code == 200:
            cleanup_old_backups()
            return zip_path
        return None
    except Exception as e:
        logger.error(f"❌ backup: {e}")
        return None


def schedule_auto_backup():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=safe_job(send_auto_backup, "auto_backup"),
        trigger='interval', hours=999999, id='auto_backup',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(cleanup_old_data, "cleanup_old_data"),
        trigger='interval', hours=6, id='cleanup_old_data',
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(trim_matches_log, "trim_matches_log"),
        trigger='cron', hour=2, minute=0, id='trim_log',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(cleanup_old_backups, "cleanup_backups"),
        trigger='cron', hour=3, minute=0, id='cleanup_backups',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(lambda: storage.cleanup_old_odds_history(days=14), "cleanup_odds"),
        trigger='cron', day_of_week='mon', hour=4, minute=0, id='cleanup_odds',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(lambda: storage.cleanup_old_anomalies(days=60), "cleanup_anomalies"),
        trigger='cron', day_of_week='mon', hour=4, minute=30, id='cleanup_anomalies',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(save_calibration_snapshot, "save_calibration"),
        trigger='cron', day='1,15', hour=5, minute=0, id='save_calibration',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(_cleanup_and_save_snapshots, "cleanup_calibration_snaps"),
        trigger='cron', hour=6, minute=0, id='cleanup_calibration_snaps',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.start()


class NotificationSystem:
    def __init__(self):
        self.last_notification = {}
        self.min_interval = 21600

    def send_if_needed(self, event_type, message, force=False):
        now = time.time()
        if not force and now - self.last_notification.get(event_type, 0) < self.min_interval:
            return
        send_telegram(message)
        self.last_notification[event_type] = now

    def check_bank_status(self):
        bank = storage.load_bank()
        stats = storage.load_stats()
        profit = stats.get('total_profit', 0)
        if profit < 0:
            dd = abs(profit); pct = (dd / bank * 100) if bank else 0
            if pct > 20:
                self.send_if_needed('bank_dd', f"🔴 Просадка ${dd:.2f} ({pct:.1f}%)")
            elif pct > 10:
                self.send_if_needed('bank_dd_mid', f"⚠️ Просадка ${dd:.2f} ({pct:.1f}%)")
        if profit > bank * 0.1:
            self.send_if_needed('bank_up', f"🟢 Прибыль ${profit:.2f}")

    def check_streaks(self):
        history = storage.load_history()
        if len(history) < 5: return
        recent = [b for b in history[-10:] if b.get('result') in ('win', 'loss')]
        if len(recent) < 5: return
        streak_type = recent[-1].get('result')
        streak = 0
        for b in reversed(recent):
            if b.get('result') == streak_type: streak += 1
            else: break
        if streak >= 5:
            emoji = "🟢" if streak_type == 'win' else "🔴"
            self.send_if_needed(f'streak_{streak_type}', f"{emoji} {streak} подряд {streak_type}")

    def check_roi(self):
        stats = storage.load_stats()
        roi = stats.get('roi', 0)
        if roi > 20:
            self.send_if_needed('roi_high', f"📈 ROI: {roi}%")
        elif roi < -10:
            self.send_if_needed('roi_low', f"📉 ROI: {roi}%")

    def run_all_checks(self):
        self.check_bank_status()
        self.check_streaks()
        self.check_roi()
        return 3


notification_system = NotificationSystem()


class StrategyTester:
    def __init__(self):
        self.strategies = {
            'value': {'name': '💎 VALUE', 'bets': [], 'profit': 0,
                      'wins': 0, 'losses': 0, 'total_stake': 0},
            '70_percent': {'name': '🎯 70%+ матчи', 'bets': [], 'profit': 0,
                           'wins': 0, 'losses': 0, 'total_stake': 0},
            'tm25_premium': {'name': '🔥 ТМ 2.5 PREMIUM', 'bets': [], 'profit': 0,
                             'wins': 0, 'losses': 0, 'total_stake': 0},
            'tm25_standard': {'name': '⭐ ТМ 2.5 STANDARD', 'bets': [], 'profit': 0,
                              'wins': 0, 'losses': 0, 'total_stake': 0},
            'btts': {'name': '⚽ BTTS (Обе Забьют)', 'bets': [], 'profit': 0,
                     'wins': 0, 'losses': 0, 'total_stake': 0},
            'line_movement': {'name': '📈 LINE MOVEMENT', 'bets': [], 'profit': 0,
                              'wins': 0, 'losses': 0, 'total_stake': 0},
        }

    def _classify(self, bet_label, source=None):
        if source == 'value':
            return 'value'
        if source == 'tm25_premium':
            return 'tm25_premium'
        if source == 'tm25_standard':
            return 'tm25_standard'
        if source == 'btts':
            return 'btts'
        if source == 'line_movement':
            return 'line_movement'
        if not bet_label:
            return '70_percent'
        l = bet_label.lower()
        if '📈' in bet_label or 'line movement' in l:
            return 'line_movement'
        if '💎' in bet_label:
            return 'value'
        if '🔥' in bet_label or 'premium' in l:
            return 'tm25_premium'
        if 'обз' in l or 'btts' in l:
            return 'btts'
        if 'тм 2.5' in l or 'under' in l:
            return 'tm25_standard'
        return '70_percent'

    def get_comparison_report(self):
        history = storage.load_history()
        for key in self.strategies:
            self.strategies[key].update({'bets': [], 'profit': 0,
                                          'wins': 0, 'losses': 0, 'total_stake': 0})

        for b in history:
            if b.get('result') not in ('win', 'loss', 'push'):
                continue
            key = self._classify(b.get('bet', ''), b.get('source'))
            s = self.strategies[key]
            s['bets'].append(b)
            s['total_stake'] += b.get('stake', 0)
            if b.get('result') == 'win':
                s['wins'] += 1
                s['profit'] += b.get('profit', 0)
            elif b.get('result') == 'loss':
                s['losses'] += 1
                s['profit'] -= b.get('stake', 0)

        report = "📊 <b>СТРАТЕГИИ</b>\n\n"
        for name, data in self.strategies.items():
            total = len(data['bets'])
            wr = (data['wins'] / total * 100) if total else 0
            roi = (data['profit'] / data['total_stake'] * 100) if data['total_stake'] else 0
            profit_str = f"+${data['profit']:.2f}" if data['profit'] >= 0 else f"-${abs(data['profit']):.2f}"
            report += (f"<b>{data['name']}</b>\n"
                       f"Ставок: {total} | WR: {wr:.1f}% | "
                       f"Прибыль: {profit_str} | ROI: {roi:.1f}%\n\n")
        return report


strategy_tester = StrategyTester()


class BotState:
    def __init__(self):
        self.state_file = STATE_PATH
        self.state = self.load_state()

    def load_state(self):
        default = {'start_time': datetime.now().isoformat(), 'search_running': False,
                   'stats': {}, 'last_full_search': None, 'version': '1.0.0'}
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file) as f:
                    state = json.load(f)
                for k, v in default.items(): state.setdefault(k, v)
                return state
        except Exception:
            pass
        return default

    def save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file) or '.', exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"save_state: {e}")

    def get_status_report(self):
        bank = storage.load_bank()
        start = datetime.fromisoformat(self.state['start_time'])
        uptime = datetime.now() - start
        return (f"🤖 <b>СТАТУС</b>\n"
                f"🕐 Аптайм: {uptime.total_seconds()/3600:.1f}ч\n"
                f"💰 Банк: ${bank:.2f}\n"
                f"🔍 Поиск: {'Да' if self.state.get('search_running') else 'Нет'}")


bot_state = BotState()


def load_bot_settings():
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, 'r') as f:
                s = json.load(f)
            for key in ['EV_MIN_70', 'PROB_MIN_70', 'XG_MIN_70', 'XG_MAX_70',
                        'POSITION_MAX_70', 'PREMIUM_MIN_EV', 'STANDARD_MIN_EV',
                        'TM25_XG_MIN', 'TM25_XG_MAX', 'MAX_TM25_BETS',
                        'VALUE_MIN_ODDS', 'VALUE_MIN_EV', 'VALUE_MIN_PROB',
                        'VALUE_MIN_XG_DIFF', 'VALUE_MAX_RESULTS',
                        'X2_MIN_EV', 'X2_MIN_PROB',
                        'LIVE_HOURS_BEFORE', 'LIVE_MINUTES_AFTER',
                        'LIVE_REFRESH_SEC', 'LIVE_CACHE_TTL_LIVE',
                        'LIVE_CACHE_TTL_SOON', 'LIVE_CACHE_TTL_FINAL',
                        'LIVE_MAX_MATCHES', 'LIVE_SPARKLINE_ENABLED',
                        'LIVE_SPARKLINE_POINTS']:
                if key.lower() in s:
                    setattr(Config, key, s[key.lower()])
            logger.info("✅ Настройки загружены")
            return True
    except Exception as e:
        logger.error(f"Ошибка настроек: {e}")
    return False
