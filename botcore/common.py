# ============================================================
# botcore/common.py — Общее: Flask-приложение, авторизация, пути, калибровка, геокод, Telegram, кэш, retry
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



__all__ = [
    'logger',
    'storage',
    'app',
    'TIMEZONE_OFFSET',
    'cache_lock',
    'ADMIN_TOKEN',
    '_WEBHOOK_SECRET',
    '_PUBLIC_PATHS',
    '_PROTECTED_EXACT',
    '_token_ok',
    '_require_admin_token',
    '_jsonl_lock',
    '_atomic_write_lines',
    '_RENDER_DISK',
    'DATA_DIR',
    'X2_FILE',
    'LOG_PATH',
    'STATE_PATH',
    'SETTINGS_PATH',
    'BACKUP_DIR',
    'GEOCODING_CACHE_FILE',
    'CALIBRATION_FILE',
    'ANOMALY_FILE',
    '_x2_candidates_lock',
    'CALIBRATION_FACTOR',
    'CALIBRATION_BY_BUCKET',
    'PROB_MAX_70',
    'calibrate_prob',
    'get_calibration_info',
    'save_x2_candidate',
    '_geo_cache',
    '_geo_cache_loaded',
    '_load_geo_cache',
    '_save_geo_cache',
    'get_coords_by_city',
    'get_weather_for_city_enhanced',
    'FINAL_STATUSES',
    'LIVE_STATUSES',
    'force_utf8',
    'TOP_LEAGUES',
    'TOP_TEAMS_LEAGUES',
    'HOME_ADVANTAGE',
    'FALLBACK_XG',
    '_telegram_lock',
    '_last_telegram_send',
    'TELEGRAM_MIN_INTERVAL',
    'parse_match_time_to_msk',
    'is_force_final',
    'PerformanceMonitor',
    'perf_monitor',
    'timing_decorator',
    'SmartCache',
    'APIError',
    'APIErrorRetry',
    'APIErrorFatal',
    'APIRateLimiter',
    'RetryManager',
    'send_error_to_telegram',
    'send_telegram',
    '_logged_matches_today',
    'log_no_motivation_match',
    'trim_matches_log',
]


logger = get_logger('__main__')   # то же имя логгера, что было в main.py


storage.SNAPSHOT_HEARTBEAT_SEC = int(getattr(Config, 'LINE_MOVEMENT_SNAPSHOT_HEARTBEAT_MIN', 25) * 60)


# root_path = корень проекта (папка с main.py), чтобы templates/, static/, sw.js находились как раньше
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask('main', root_path=_PROJECT_ROOT, template_folder='templates', static_folder='static')


TIMEZONE_OFFSET = 3


cache_lock = Lock()


# ============================================================
# 🔐 АВТОРИЗАЦИЯ API + ЗАЩИТА ВЕБХУКА + БЛОКИРОВКИ ФАЙЛОВ
# ============================================================
# ADMIN_TOKEN — задать в Render → Environment. Без него /api/* закрыт (503).
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '').strip()


# secret_token для Telegram: берём из env WEBHOOK_SECRET (A-Z a-z 0-9 _ -)
# или выводим из TELEGRAM_TOKEN — отдельной переменной не нужно.
_WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '').strip() or hashlib.sha256(
    ('qb-webhook:' + (getattr(Config, 'TELEGRAM_TOKEN', '') or '')).encode()
).hexdigest()


_PUBLIC_PATHS = {'/api/keepalive'}          # пингуется без токена


_PROTECTED_EXACT = {'/export', '/void_old'}  # вне /api/, но тоже закрыты


def _token_ok(supplied: str) -> bool:
    if not ADMIN_TOKEN or not supplied:
        return False
    return hmac.compare_digest(supplied.encode('utf-8'), ADMIN_TOKEN.encode('utf-8'))


@app.before_request
def _require_admin_token():
    if request.method == 'OPTIONS':
        return None
    p = request.path
    if not (p.startswith('/api/') or p in _PROTECTED_EXACT):
        return None
    if p in _PUBLIC_PATHS:
        return None
    if not ADMIN_TOKEN:
        return jsonify({'status': 'error',
                        'error': 'ADMIN_TOKEN не задан на сервере'}), 503
    if not _token_ok(request.headers.get('X-Admin-Token', '')):
        return jsonify({'status': 'error', 'error': 'unauthorized'}), 401
    return None


# Блокировка для read-modify-write над jsonl-файлами (lab / anomalies)
_jsonl_lock = RLock()


def _atomic_write_lines(path, lines):
    """Атомарная запись: tmp-файл + os.replace (читатели не видят полфайла)."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ============================================================
# ★ ПУТИ НА ПЕРСИСТЕНТНЫЙ ДИСК RENDER (/data)
# ============================================================
_RENDER_DISK = '/opt/render/project/src/data'


DATA_DIR = _RENDER_DISK if os.path.exists(_RENDER_DISK) else '/data' if os.path.exists('/data') else '.'


X2_FILE = os.path.join(DATA_DIR, 'x2_data.json')


LOG_PATH = os.path.join(DATA_DIR, 'matches_log.txt')


STATE_PATH = os.path.join(DATA_DIR, 'bot_state.json')


SETTINGS_PATH = os.path.join(DATA_DIR, 'bot_settings.json')


BACKUP_DIR = os.path.join(DATA_DIR, 'backups')


GEOCODING_CACHE_FILE = os.path.join(DATA_DIR, 'geocoding_cache.json')


CALIBRATION_FILE = os.path.join(DATA_DIR, 'calibration_snapshots.json')


ANOMALY_FILE = os.path.join(DATA_DIR, 'anomaly_skipped.jsonl')


_x2_candidates_lock = Lock()


# ============================================================
# ★ FIX п.2: константы калибровки — из Config
# ============================================================
CALIBRATION_FACTOR = getattr(Config, 'CALIBRATION_FACTOR', 0.91)


CALIBRATION_BY_BUCKET = getattr(Config, 'CALIBRATION_BY_BUCKET', {
    (0, 50): 1.00, (50, 65): 1.00, (65, 70): 1.00,
    (70, 75): 0.98, (75, 80): 0.90, (80, 85): 0.75,
    (85, 90): 0.65, (90, 100): 0.60,
})


PROB_MAX_70 = getattr(Config, 'PROB_MAX_70', 85.0)


def calibrate_prob(prob_pct: float, use_bucket: bool = True) -> float:
    """Корректирует вероятность с учётом калибровки."""
    if prob_pct <= 0:
        return prob_pct

    if use_bucket:
        for (lo, hi), coef in CALIBRATION_BY_BUCKET.items():
            if lo <= prob_pct < hi:
                return round(prob_pct * coef, 1)
        return prob_pct

    return round(prob_pct * CALIBRATION_FACTOR, 1)


def get_calibration_info(prob_pct: float) -> dict:
    """Возвращает информацию о калибровке для UI/логов."""
    calibrated = calibrate_prob(prob_pct, use_bucket=True)
    diff = calibrated - prob_pct
    return {
        'original': prob_pct,
        'calibrated': calibrated,
        'diff': round(diff, 1),
        'factor': round(calibrated / prob_pct, 3) if prob_pct > 0 else 1.0,
    }


# ============================================================
# SAVE X2 CANDIDATE
# ============================================================
def save_x2_candidate(home, away, hp, ap, league_name, match_time,
                       fixture_id, home_form='', away_form='', total_xg=0,
                       x2_side='X2', x2_ev=0, x2_prob=0,
                       entry_odds=0, entry_1x_odds=0):
    try:
        saved = storage.save_x2_candidate(
            home=home, away=away, hp=hp, ap=ap,
            league_name=league_name, match_time=match_time,
            fixture_id=fixture_id, home_form=home_form, away_form=away_form,
            total_xg=total_xg, x2_side=x2_side,
            x2_ev=x2_ev, x2_prob=x2_prob,
            entry_odds=entry_odds, entry_1x_odds=entry_1x_odds,
        )
        if saved:
            logger.info(f"💾 X2 candidate: {home} vs {away} | {x2_side} @ {entry_odds}")
        return saved
    except Exception as e:
        logger.error(f"save_x2_candidate: {e}")
        return False


# ============================================================
# GEOCODING
# ============================================================
_geo_cache = {}


_geo_cache_loaded = False


def _load_geo_cache():
    global _geo_cache_loaded
    if _geo_cache_loaded:
        return
    if os.path.exists(GEOCODING_CACHE_FILE):
        try:
            with open(GEOCODING_CACHE_FILE, 'r', encoding='utf-8') as f:
                _geo_cache.clear()
                _geo_cache.update(json.load(f) or {})
        except Exception:
            _geo_cache.clear()
    _geo_cache_loaded = True


def _save_geo_cache():
    try:
        os.makedirs(os.path.dirname(GEOCODING_CACHE_FILE) or '.', exist_ok=True)
        with open(GEOCODING_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_geo_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"geo cache save: {e}")


def get_coords_by_city(city_name):
    if not city_name:
        return None
    if city_name in Config.CITY_COORDS:
        return Config.CITY_COORDS[city_name]
    _load_geo_cache()
    if city_name in _geo_cache:
        cached = _geo_cache[city_name]
        if cached:
            return tuple(cached)
    if not Config.WEATHER_ENABLED or not Config.WEATHER_API_KEY:
        return None
    try:
        r = requests.get(
            "http://api.openweathermap.org/geo/1.0/direct",
            params={'q': city_name, 'limit': 1, 'appid': Config.WEATHER_API_KEY},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                coords = [data[0]['lat'], data[0]['lon']]
                _geo_cache[city_name] = coords
                _save_geo_cache()
                return tuple(coords)
            else:
                _geo_cache[city_name] = None
                _save_geo_cache()
    except Exception as e:
        logger.error(f"Geocoding error '{city_name}': {e}")
    return None


def get_weather_for_city_enhanced(city_name):
    if not Config.WEATHER_ENABLED or not city_name:
        return None
    coords = get_coords_by_city(city_name)
    if not coords:
        return None
    return Config.get_weather(coords[0], coords[1])


# ============================================================
# КОНСТАНТЫ
# ============================================================
FINAL_STATUSES = ('FT', 'AET', 'PEN', 'AWD', 'WO')


LIVE_STATUSES = ('1H', 'HT', '2H', 'ET', 'BT', 'P', 'INT', 'LIVE', 'SUSP')


@app.after_request
def force_utf8(response):
    if response.mimetype == 'text/html':
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    elif response.mimetype == 'application/json':
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response


TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']


TOP_TEAMS_LEAGUES = [
    'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1',
    'Champions League', 'UEFA Champions League',
    'Europa League', 'UEFA Europa League',
]


HOME_ADVANTAGE = {
    'Premier League': 1.15, 'La Liga': 1.12, 'Bundesliga': 1.18,
    'Serie A': 1.10, 'Ligue 1': 1.13, 'Championship': 1.12,
    '2. Bundesliga': 1.15, 'Eredivisie': 1.14, 'Primeira Liga': 1.11,
    'Süper Lig': 1.16,
    'UEFA Champions League': 1.06,
    'UEFA Europa League':    1.10,
    'UEFA Conference League': 1.13,
    'Champions League':      1.06,
    'Europa League':         1.10,
    'Conference League':     1.13,
}


FALLBACK_XG = {
    'Premier League': {'home': 1.6, 'away': 1.2},
    'La Liga': {'home': 1.5, 'away': 1.2},
    'Bundesliga': {'home': 1.7, 'away': 1.3},
    'Serie A': {'home': 1.5, 'away': 1.1},
    'Ligue 1': {'home': 1.5, 'away': 1.2},
    'Championship': {'home': 1.4, 'away': 1.1},
    'League One': {'home': 1.3, 'away': 1.0},
    'League Two': {'home': 1.2, 'away': 0.9},
    'La Liga 2': {'home': 1.3, 'away': 1.0},
    'Süper Lig': {'home': 1.5, 'away': 1.1},
    'Primeira Liga': {'home': 1.4, 'away': 1.1},
}


_telegram_lock = Lock()


_last_telegram_send = 0


TELEGRAM_MIN_INTERVAL = 0.05


def parse_match_time_to_msk(date_str):
    if not date_str:
        return "?"
    try:
        s = str(date_str).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        if '+' not in s and s.count('-') <= 2:
            s = s + '+00:00'
        if ' ' in s and 'T' not in s:
            s = s.replace(' ', 'T', 1)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_msk = dt + timedelta(hours=TIMEZONE_OFFSET)
        return dt_msk.strftime("%d.%m.%Y %H:%M")
    except Exception as e:
        logger.warning(f"⚠️ Дата '{date_str}': {e}")
        try:
            return str(date_str)[:16]
        except Exception:
            return "?"


def is_force_final(match_time_str, status):
    if status != 'NS':
        return False
    if not match_time_str or match_time_str == '?':
        return False
    try:
        mt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
        return (now_msk - mt).total_seconds() / 3600 > 2.5
    except Exception:
        return False


# ============================================================
# PERFORMANCE MONITOR
# ============================================================
class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(lambda: {
            'calls': 0, 'total_time': 0, 'max_time': 0,
            'min_time': float('inf'), 'errors': 0
        })
        self.lock = Lock()

    def record(self, func_name, elapsed, error=False):
        with self.lock:
            m = self.metrics[func_name]
            m['calls'] += 1
            m['total_time'] += elapsed
            m['max_time'] = max(m['max_time'], elapsed)
            m['min_time'] = min(m['min_time'], elapsed)
            if error:
                m['errors'] += 1

    def get_report(self):
        report = []
        for fn, m in sorted(self.metrics.items()):
            avg = m['total_time'] / m['calls'] if m['calls'] else 0
            err = m['errors'] / m['calls'] * 100 if m['calls'] else 0
            report.append({
                'function': fn, 'calls': m['calls'],
                'avg_time': round(avg, 3), 'max_time': round(m['max_time'], 3),
                'min_time': round(m['min_time'], 3),
                'error_rate': round(err, 1), 'total_time': round(m['total_time'], 3)
            })
        return report

    def print_report(self):
        logger.info("=" * 60)
        logger.info("📊 ОТЧЕТ О ПРОИЗВОДИТЕЛЬНОСТИ")
        logger.info("=" * 60)
        for item in self.get_report():
            status = "✅" if item['error_rate'] < 5 else "⚠️" if item['error_rate'] < 20 else "❌"
            logger.info(f"{status} {item['function']}: {item['calls']} вызовов, "
                        f"среднее {item['avg_time']}с, макс {item['max_time']}с, "
                        f"ошибки {item['error_rate']}%")


perf_monitor = PerformanceMonitor()


def timing_decorator(name=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            fn = name or func.__name__
            start = time.time()
            error = False
            try:
                return func(*args, **kwargs)
            except Exception:
                error = True
                raise
            finally:
                elapsed = time.time() - start
                perf_monitor.record(fn, elapsed, error)
                if elapsed > 2.0:
                    logger.warning(f"⏱️ {fn} выполняется {elapsed:.2f}с")
        return wrapper
    return decorator


# ============================================================
# SMART CACHE
# ============================================================
class SmartCache:
    def __init__(self, max_size=2000):
        self.cache = {}
        self.cache_timestamps = {}
        self.hit_count = {}
        self.last_access = {}
        self.max_size = max_size
        self.default_ttl = 3600
        self.ttl_by_type = {
            'form': 86400, 'odds': 60, 'statistics': 172800,
            'standings': 86400, 'matches': 43200, 'h2h': 604800,
            'result': 300, 'predictions': 43200,
        }

    def get(self, key, data_type='default'):
        if key in self.cache:
            ttl = self.ttl_by_type.get(data_type, self.default_ttl)
            if time.time() - self.cache_timestamps.get(key, 0) < ttl:
                self.hit_count[key] = self.hit_count.get(key, 0) + 1
                self.last_access[key] = time.time()
                return self.cache[key]
            self._remove(key)
        return None

    def set(self, key, value):
        if len(self.cache) >= self.max_size:
            to_remove = min(self.cache.keys(),
                            key=lambda k: (self.hit_count.get(k, 0), self.last_access.get(k, 0)))
            self._remove(to_remove)
        self.cache[key] = value
        self.cache_timestamps[key] = time.time()
        self.hit_count[key] = 0
        self.last_access[key] = time.time()

    def _remove(self, key):
        for d in (self.cache, self.cache_timestamps, self.hit_count, self.last_access):
            d.pop(key, None)

    def clear(self):
        self.cache.clear()
        self.cache_timestamps.clear()
        self.hit_count.clear()
        self.last_access.clear()


class APIError(Exception): pass


class APIErrorRetry(Exception): pass


class APIErrorFatal(Exception): pass


class APIRateLimiter:
    def __init__(self, max_requests=250, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self.lock = Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.requests = [t for t in self.requests if now - t < self.time_window]
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    logger.warning(f"⏳ Rate limit: ждем {sleep_time:.1f} сек")
                    time.sleep(sleep_time + 1)
                    return self.wait_if_needed()
            self.requests.append(now)


class RetryManager:
    def __init__(self, max_retries=3, base_delay=1, max_delay=10):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def retry(self, func, *args, **kwargs):
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except APIErrorRetry as e:
                if attempt == self.max_retries:
                    raise APIErrorFatal(f"Превышено число попыток: {e}")
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                jitter = random.uniform(0, delay * 0.1)
                logger.warning(f"🔄 Попытка {attempt + 1}/{self.max_retries + 1}: {e}")
                time.sleep(delay + jitter)
            except APIErrorFatal:
                raise
            except Exception as e:
                raise APIErrorFatal(f"Неожиданная ошибка: {e}")


# ============================================================
# TELEGRAM
# ============================================================
def send_error_to_telegram(error_text: str):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        if len(error_text) > 4000:
            error_text = error_text[:4000] + "...(обрезано)"
        requests.post(url, json={
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': f"❌ <b>ОШИБКА БОТА</b>\n\n{error_text}",
            'parse_mode': 'HTML'
        }, timeout=5)
    except Exception as e:
        logger.error(f"Не удалось отправить ошибку: {e}")


def send_telegram(text: str, parse_mode: str = 'HTML'):
    global _last_telegram_send
    targets = [Config.ADMIN_CHAT_ID]
    if Config.CHANNEL_ID and str(Config.CHANNEL_ID) != str(Config.ADMIN_CHAT_ID):
        targets.append(Config.CHANNEL_ID)
    for chat_id in targets:
        try:
            with _telegram_lock:
                now = time.time()
                delta = now - _last_telegram_send
                if delta < TELEGRAM_MIN_INTERVAL:
                    time.sleep(TELEGRAM_MIN_INTERVAL - delta)
                _last_telegram_send = time.time()

            url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
            r = requests.post(url, json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }, timeout=10)

            if r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 5))
                logger.warning(f"⏳ Telegram rate limit: ждём {retry_after} сек")
                time.sleep(retry_after)
                r = requests.post(url, json={
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode
                }, timeout=10)

            if r.status_code != 200:
                logger.error(f"❌ Ошибка отправки в {chat_id}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Send error → {chat_id}: {e}")


# ============================================================
# ЛОГ МАТЧЕЙ
# ============================================================
_logged_matches_today = set()


def log_no_motivation_match(home, away, hp, ap, total_xg, league_name='',
                             favorite=None, underdog=None):
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        key = f"{today}_{home}_{away}"
        if key in _logged_matches_today:
            return
        _logged_matches_today.add(key)
        if len(_logged_matches_today) > 5000:
            _logged_matches_today.clear()

        if favorite and underdog:
            note = f"X2 candidate | Fav: {favorite} | Und: {underdog}"
        else:
            note = "нет мотивации"

        os.makedirs(os.path.dirname(LOG_PATH) or '.', exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | "
                    f"{home} vs {away} | {note} | "
                    f"H: #{hp}, A: #{ap} | XG: {total_xg:.2f} | {league_name}\n")
    except Exception as e:
        logger.error(f"Ошибка записи matches_log: {e}")


def trim_matches_log():
    try:
        if os.path.exists(LOG_PATH):
            size = os.path.getsize(LOG_PATH)
            if size > 500 * 1024:
                with open(LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                with open(LOG_PATH, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-1000:])
                logger.info(f"🧹 matches_log обрезан")
    except Exception as e:
        logger.error(f"Ошибка trim_matches_log: {e}")
