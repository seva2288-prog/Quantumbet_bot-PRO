# ============================================================
# main.py — точка входа Quantum Bet Bot PRO
# Весь код разнесён по пакету botcore/ (модули идут в порядке зависимостей).
# Запуск: python main.py   |   gunicorn: main:app
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
from botcore.jobs import *  # noqa: F401,F403
from botcore.routes_search import *  # noqa: F401,F403
from botcore.routes_core import *  # noqa: F401,F403
from botcore.routes_live import *  # noqa: F401,F403
from botcore.routes_x2 import *  # noqa: F401,F403
from botcore.routes_calib import *  # noqa: F401,F403
from botcore.routes_data import *  # noqa: F401,F403
from botcore.routes_lab import *  # noqa: F401,F403
from botcore.ops import *  # noqa: F401,F403
from botcore.ht_stats import *  # noqa: F401,F403
from botcore.ht_strategy import *  # noqa: F401,F403


if __name__ == "__main__":
    os.makedirs('data', exist_ok=True)
    if os.path.exists('/data'):
        os.makedirs('/data/storage', exist_ok=True)

    setup_logging()
    load_bot_settings()
    Config.init_db()
    _load_geo_cache()
    logger.info(f"🌍 Geocoding cache: {len(_geo_cache)} городов")
    logger.info(f"📁 DATA_DIR: {DATA_DIR}")

    # ★ FIX п.15: USE_API_LEAGUES при старте
    if getattr(Config, 'USE_API_LEAGUES', False):
        try:
            logger.info("🔍 USE_API_LEAGUES=True — построение списка лиг через API...")
            Config.build_leagues_from_api()
            logger.info(f"✅ Лиг из API: {len(Config.LEAGUES)}")
        except Exception as e:
            logger.error(f"❌ build_leagues_from_api: {e} — используем статический список")
    else:
        logger.info(f"📋 Используем статический список лиг: {len(Config.LEAGUES)}")

    # ★ FIX: 3-я часть `register_bot_commands` — теперь через проверку
    try:
        register_bot_commands()
    except Exception as e:
        logger.error(f"⚠️ Команды: {e}")

    start_scheduler()
    import threading
    def lab_loop():
        import time
        while True:
            try:
                update_lab_results()
            except: pass
            time.sleep(1800) # 30 минут
    threading.Thread(target=lab_loop, daemon=True).start()
    schedule_updates()
    schedule_notifications()
    schedule_performance_report()
    schedule_auto_backup()
    schedule_autobet()

    try:
        WEBHOOK_URL = (os.getenv('RENDER_EXTERNAL_URL', 'https://quantumbet-bot-pro.onrender.com') + '/webhook')
        r = requests.get(
            f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/setWebhook",
            params={'url': WEBHOOK_URL, 'secret_token': _WEBHOOK_SECRET}, timeout=10
        )
        resp = r.json()
        if resp.get('ok'):
            logger.info(f"✅ Webhook: {WEBHOOK_URL}")
        else:
            logger.error(f"❌ Webhook error: {resp}")
    except Exception as e:
        logger.error(f"❌ Webhook: {e}")

    # ★ TURBO SCHEDULER for 75k
    odds_scheduler = BackgroundScheduler()
    odds_scheduler.add_job(
        func=safe_job(snapshot_odds_for_upcoming, "snapshot_odds"),
        trigger='interval',
        minutes=int(getattr(Config, 'LINE_MOVEMENT_SNAPSHOT_INTERVAL_MIN', 30)),
        id='odds_snapshot',
        next_run_time=datetime.now() + timedelta(seconds=20),   # первый снимок сразу после старта
        replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    # ★ Telegram-уведомления: сильное движение кэфов и итоги матчей со снимками
    odds_scheduler.add_job(
        func=safe_job(notify_day_events, "day_notify"),
        trigger='interval', minutes=5,
        id='day_notify', replace_existing=True, max_instances=1,
        misfire_grace_time=120, coalesce=True
    )
    # ★ Ежедневный отчёт и резервная копия (проверка раз в 15 мин, отправка раз в сутки)
    odds_scheduler.add_job(
        func=safe_job(ops_report_job, "daily_report"),
        trigger='interval', minutes=15,
        id='daily_report', replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(ops_backup_job, "daily_backup"),
        trigger='interval', minutes=30,
        id='daily_backup', replace_existing=True, max_instances=1,
        misfire_grace_time=600, coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(ops_streak_job, "streak_alert"),
        trigger='interval', minutes=15,
        id='streak_alert', replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(ops_results_job, "fixture_results"),
        trigger='interval', minutes=60,
        id='fixture_results', replace_existing=True, max_instances=1,
        misfire_grace_time=600, coalesce=True
    )
    # ★ Live-кэфы в перерыве (для сравнения со статистикой «счёт 1-го тайма → итог»)
    odds_scheduler.add_job(
        func=safe_job(ht_odds_job, "ht_odds"),
        trigger='interval', minutes=5,
        id='ht_odds', replace_existing=True, max_instances=1,
        misfire_grace_time=120, coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(ht_signal_job, "ht_signals"),
        trigger='interval', minutes=3,
        id='ht_signals', replace_existing=True, max_instances=1,
        misfire_grace_time=120, coalesce=True
    )
    # ★ АВТО-ОБНОВЛЕНИЕ СПИСКА МАТЧЕЙ (чтобы бот работал 24/7)
    odds_scheduler.add_job(
        func=safe_job(get_matches_with_factors, "update_matches"),
        trigger='interval', hours=6, 
        id='update_matches',
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=1800,
        coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(lambda: storage.cleanup_old_odds_history(days=14), "cleanup_odds"),
        trigger='cron', hour=4, minute=0, id='odds_cleanup',
        replace_existing=True, misfire_grace_time=1800, coalesce=True
    )
    odds_scheduler.start()

    logger.info("=" * 60)
    logger.info("🚀 QUANTUM BET BOT PRO ЗАПУЩЕН (v23.3 — Turbo 75k)")
    logger.info("=" * 60)
    logger.info(f"📊 Лиг: {len(Config.LEAGUES)} | Кубков: {len(Config.CUP_LEAGUES)}")
    logger.info(f"🧠 ENGINE: {Config.PREDICTION_ENGINE}")
    logger.info(f"💎 VALUE: кэф>={getattr(Config, 'VALUE_MIN_ODDS', 2.5)} | "
                f"EV>={getattr(Config, 'VALUE_MIN_EV', 25)}% | "
                f"Prob>={getattr(Config, 'VALUE_MIN_PROB', 50)}%")
    logger.info(f"📈 LINE MOVEMENT: {'вкл' if getattr(Config, 'LINE_MOVEMENT_ENABLED', True) else 'выкл'}")
    logger.info(f"⚡ LIVE: окно -{getattr(Config, 'LIVE_MINUTES_AFTER', 120)}м .. "
                f"+{getattr(Config, 'LIVE_HOURS_BEFORE', 2)}ч")
    logger.info(f"🔥 X2: {'вкл' if getattr(Config, 'X2_ENABLED', False) else 'ВЫКЛ'}")
    logger.info(f"🌤️ Weather: rain>{getattr(Config, 'WEATHER_SKIP_RAIN_MM', 4.0)}мм / "
                f"wind>{getattr(Config, 'WEATHER_SKIP_WIND_MS', 15.0)}м/с")
    logger.info(f"📁 DATA_DIR: {DATA_DIR}")
    logger.info("=" * 60)

    if Config.FOOTBALL_API_KEY:
        try:
            test_headers = {
                'x-apisports-key': Config.FOOTBALL_API_KEY,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            test_r = requests.get(f"{Config.FOOTBALL_API_URL}/status",
                                   headers=test_headers, timeout=10)
            test_data = test_r.json()
            if test_data.get('response'):
                sub = test_data['response'].get('subscription', {})
                req = test_data['response'].get('requests', {})
                logger.info(f"✅ Football API: {sub.get('plan', '?')} | "
                            f"{req.get('current', 0)}/{req.get('limit_day', 0)}")
        except Exception as e:
            logger.error(f"❌ Football API: {e}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
