# ============================================================
# main.py — ЧАСТЬ 1/3
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
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory, render_template
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Config
from app.database.storage import storage
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler
from app.llm import llm_analyze_match, llm_analyze_batch

logger = get_logger(__name__)
app = Flask(__name__, template_folder='templates', static_folder='static')

search_running = False
search_state = {}
TIMEZONE_OFFSET = 3

cache_lock = Lock()

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

_x2_candidates_lock = Lock()


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
    global _geo_cache, _geo_cache_loaded
    if _geo_cache_loaded:
        return
    if os.path.exists(GEOCODING_CACHE_FILE):
        try:
            with open(GEOCODING_CACHE_FILE, 'r', encoding='utf-8') as f:
                _geo_cache = json.load(f) or {}
        except Exception:
            _geo_cache = {}
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


# ============================================================
# FOOTBALL API
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or Config.FOOTBALL_API_URL
        self.cache = SmartCache(max_size=2000)
        self.last_request_time = 0
        self.min_request_interval = 0.15
        self.rate_limiter = APIRateLimiter(max_requests=250, time_window=60)
        self.retry_manager = RetryManager(max_retries=3, base_delay=1)
        self.error_stats = defaultdict(int)
        if self.api_key and len(self.api_key) > 10:
            logger.info(f"🔑 Football API: {self.api_key[:8]}...{self.api_key[-4:]}")
        else:
            logger.error("❌ FOOTBALL_API_KEY НЕ НАЙДЕН!")

    def _make_request(self, endpoint, params=None):
        try:
            self.rate_limiter.wait_if_needed()
            return self.retry_manager.retry(self._make_request_impl, endpoint, params)
        except APIErrorFatal as e:
            logger.error(f"❌ Фатальная ошибка API: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка: {e}")
            return None

    def _make_request_impl(self, endpoint, params=None):
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval - (now - self.last_request_time))

        if not self.api_key or len(self.api_key) < 10:
            raise APIErrorFatal("FOOTBALL_API_KEY не задан")

        headers = {
            'x-apisports-key': self.api_key,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        url = f"{self.base_url}{endpoint}"
        try:
            r = requests.get(url, headers=headers, params=params, timeout=Config.REQUEST_TIMEOUT)
            self.last_request_time = time.time()
            if r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 30))
                time.sleep(retry_after)
                raise APIErrorRetry("Rate limit")
            if r.status_code == 403:
                raise APIErrorFatal("Недействительный API ключ")
            if r.status_code != 200:
                if r.status_code >= 500:
                    raise APIErrorRetry(f"Серверная ошибка {r.status_code}")
                raise APIErrorFatal(f"Ошибка API {r.status_code}")
            data = r.json()
            if data.get('errors'):
                err_str = str(data['errors']).lower()
                if 'rate limit' in err_str:
                    raise APIErrorRetry("Rate limit")
                if 'api key' in err_str or 'token' in err_str:
                    raise APIErrorFatal(f"Ошибка ключа: {data['errors']}")
                return None
            return data
        except requests.exceptions.Timeout:
            raise APIErrorRetry("Таймаут")
        except requests.exceptions.ConnectionError:
            raise APIErrorRetry("Ошибка соединения")
        except json.JSONDecodeError as e:
            raise APIErrorFatal(f"Ошибка парсинга JSON: {e}")

    @timing_decorator()
    def get_matches(self, league_id, date):
        cache_key = f"matches_{league_id}_{date}"
        cached = self.cache.get(cache_key, data_type='matches')
        if cached is not None:
            return cached
        data = self._make_request('/fixtures', {
            'league': league_id, 'season': Config.USE_SEASON, 'date': date
        })
        if data and 'response' in data:
            self.cache.set(cache_key, data['response'])
            return data['response']
        return []

    @timing_decorator()
    def get_form(self, team_id):
        stats_enabled = getattr(Config, 'STATS_ENABLED', True)
        cache_key = f"form_{team_id}"
        cached = self.cache.get(cache_key, data_type='form')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/fixtures', {'team': team_id, 'last': 5, 'status': 'FT'})
            if data and 'response' in data:
                matches = data['response']
                if matches:
                    xg_scored = []
                    xg_conceded = []
                    w = d = l = 0
                    for m in matches:
                        goals = m.get('goals', {})
                        teams = m.get('teams', {})
                        fid = m.get('fixture', {}).get('id')
                        stats = self.get_match_statistics(fid) if (fid and stats_enabled) else None
                        is_home = teams.get('home', {}).get('id') == team_id
                        if is_home:
                            s, c = goals.get('home', 0) or 0, goals.get('away', 0) or 0
                        else:
                            s, c = goals.get('away', 0) or 0, goals.get('home', 0) or 0
                        xg_val = None
                        if stats:
                            for tn, tstats in stats.items():
                                xg_entry = tstats.get('Expected Goals', 0)
                                if tn == teams.get('home', {}).get('name') and is_home:
                                    xg_val = xg_entry
                                elif tn == teams.get('away', {}).get('name') and not is_home:
                                    xg_val = xg_entry
                        xg_scored.append(xg_val if xg_val is not None else s)
                        xg_conceded.append(c)
                        if s > c: w += 1
                        elif s == c: d += 1
                        else: l += 1
                    result = {
                        'goals_avg': round(sum(xg_scored) / len(xg_scored), 2),
                        'conceded_avg': round(sum(xg_conceded) / len(xg_conceded), 2),
                        'wins': w, 'draws': d, 'losses': l,
                        'matches': len(matches),
                        'form': self._calculate_form(matches, team_id)
                    }
                    self.cache.set(cache_key, result)
                    return result
        except Exception as e:
            logger.error(f"Ошибка формы {team_id}: {e}")
        return None

    def _calculate_form(self, matches, team_id):
        form = []
        for m in matches:
            teams = m.get('teams', {})
            goals = m.get('goals', {})
            hs = goals.get('home', 0) or 0
            aws = goals.get('away', 0) or 0
            if teams.get('home', {}).get('id') == team_id:
                form.append('W' if hs > aws else ('D' if hs == aws else 'L'))
            else:
                form.append('W' if aws > hs else ('D' if aws == hs else 'L'))
        return ''.join(form)

    @timing_decorator()
    def get_match_statistics(self, fixture_id):
        cache_key = f"stats_{fixture_id}"
        cached = self.cache.get(cache_key, data_type='statistics')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/fixtures/statistics', {'fixture': fixture_id})
            if data and 'response' in data:
                statistics = {}
                for ts in data['response']:
                    tn = ts.get('team', {}).get('name', 'Unknown')
                    stats = {}
                    for stat in ts.get('statistics', []):
                        k = stat.get('type', '')
                        v = stat.get('value', 0)
                        if v is None:
                            v = 0
                        elif isinstance(v, str):
                            v = float(v.replace('%', '')) if '%' in v else (float(v) if v.replace('.', '').isdigit() else 0)
                        stats[k] = float(v) if isinstance(v, (int, float)) else 0
                    statistics[tn] = stats
                self.cache.set(cache_key, statistics)
                return statistics
        except Exception as e:
            logger.error(f"Ошибка статистики {fixture_id}: {e}")
        return None

    @timing_decorator()
    def get_standings(self, league_id):
        cache_key = f"standings_{league_id}"
        cached = self.cache.get(cache_key, data_type='standings')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/standings', {'league': league_id, 'season': Config.USE_SEASON})
            if data and 'response' in data:
                standings = {}
                for league in data['response']:
                    for standing in league.get('league', {}).get('standings', []):
                        for team in standing:
                            tn = team.get('team', {}).get('name', '')
                            standings[tn] = {
                                'position': team.get('rank', 0),
                                'points': team.get('points', 0),
                                'form': team.get('form', ''),
                                'goals_diff': team.get('goalsDiff', 0)
                            }
                self.cache.set(cache_key, standings)
                return standings
        except Exception as e:
            logger.error(f"Ошибка таблицы {league_id}: {e}")
        return None

    def get_injuries(self, team_id):
        cache_key = f"injuries_{team_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            data = self._make_request('/injuries', {'team': team_id, 'season': Config.USE_SEASON})
            if data and 'response' in data:
                self.cache.set(cache_key, data['response'])
                return data['response']
        except Exception as e:
            logger.error(f"Ошибка травм {team_id}: {e}")
        return []

    @timing_decorator()
    def get_match_result(self, fixture_id):
        cache_key = f"result_{fixture_id}"
        cached = self.cache.get(cache_key, data_type='result')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/fixtures', {'id': fixture_id})
            if not data or not data.get('response'):
                return None
            f = data['response'][0]
            score = f.get('score', {})
            halftime = score.get('halftime', {})
            status = f.get('status', {})
            result = {
                'goals': {
                    'home': f.get('goals', {}).get('home'),
                    'away': f.get('goals', {}).get('away')
                },
                'halftime': {
                    'home': halftime.get('home'),
                    'away': halftime.get('away')
                },
                'status': status.get('short', 'NS'),
                'status_long': status.get('long', ''),
                'minute': status.get('elapsed', 0),
                'is_final': status.get('short') in FINAL_STATUSES,
                'is_live': status.get('short') in LIVE_STATUSES,
            }
            self.cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Ошибка результата {fixture_id}: {e}")
        return None

    @timing_decorator()
    def get_head_to_head(self, home_team, away_team):
        cache_key = f"h2h_{home_team}_{away_team}"
        cached = self.cache.get(cache_key, data_type='h2h')
        if cached is not None:
            return cached
        try:
            hid = self.get_team_id(home_team)
            aid = self.get_team_id(away_team)
            if hid and aid:
                data = self._make_request('/fixtures/headtohead', {'h2h': f"{hid}-{aid}", 'last': 5})
                if data and 'response' in data:
                    fixtures = data['response']
                    if fixtures:
                        result = {'matches': [], 'home_wins': 0, 'away_wins': 0,
                                  'draws': 0, 'goals_scored': 0, 'goals_conceded': 0}
                        for f in fixtures:
                            t = f.get('teams', {})
                            g = f.get('goals', {})
                            hs = g.get('home', 0) or 0
                            aws = g.get('away', 0) or 0
                            result['matches'].append({
                                'home': t.get('home', {}).get('name', ''),
                                'away': t.get('away', {}).get('name', ''),
                                'home_score': hs, 'away_score': aws
                            })
                            if hs > aws: result['home_wins'] += 1
                            elif hs < aws: result['away_wins'] += 1
                            else: result['draws'] += 1
                            result['goals_scored'] += hs
                            result['goals_conceded'] += aws
                        total = len(result['matches'])
                        result['avg_goals'] = round((result['goals_scored'] + result['goals_conceded']) / total, 2)
                        result['home_win_rate'] = round((result['home_wins'] / total) * 100, 1)
                        result['total_matches'] = total
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"Ошибка H2H: {e}")
        return None

    def get_team_id(self, team_name):
        cache_key = f"team_id_{team_name}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            data = self._make_request('/teams', {'name': team_name})
            if data and 'response' in data:
                for t in data['response']:
                    td = t.get('team', {})
                    if td.get('name', '').lower() == team_name.lower():
                        self.cache.set(cache_key, td.get('id'))
                        return td.get('id')
        except Exception as e:
            logger.error(f"Ошибка ID команды {team_name}: {e}")
        return None

    @timing_decorator()
    def get_match_odds(self, fixture_id):
        cache_key = f"odds_{fixture_id}"
        cached = self.cache.get(cache_key, data_type='odds')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/odds', {'fixture': fixture_id})
            if data and 'response' in data:
                result = self._extract_best_odds(data['response'])
                if result.get('best_odds', 0) > 0:
                    self.cache.set(cache_key, result)
                    return result
        except Exception as e:
            logger.error(f"Ошибка кэфов {fixture_id}: {e}")
        return None

    @timing_decorator()
    def get_odds_batch_for_league(self, league_id, date):
        cache_key = f"odds_batch_{league_id}_{date}"
        cached = self.cache.get(cache_key, data_type='odds')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/odds', {
                'league': league_id,
                'season': Config.USE_SEASON,
                'date': date,
            })
            if not data or 'response' not in data:
                return {}
            result = {}
            for item in data['response']:
                fid = item.get('fixture', {}).get('id')
                if not fid:
                    continue
                bookmakers = item.get('bookmakers', [])
                if bookmakers:
                    result[fid] = self._extract_best_odds(bookmakers)
            self.cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Ошибка batch-кэфов {league_id}: {e}")
            return {}

    @timing_decorator()
    def get_predictions_batch_for_league(self, league_id, date):
        cache_key = f"pred_batch_{league_id}_{date}"
        cached = self.cache.get(cache_key, data_type='predictions')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/predictions', {
                'league': league_id,
                'season': Config.USE_SEASON,
                'date': date,
            })
            if not data or 'response' not in data:
                return {}
            result = {}
            for item in data['response']:
                fid = item.get('fixture', {}).get('id')
                if not fid:
                    continue
                pred = item.get('predictions', {})
                percent = pred.get('percent', {})
                result[fid] = {
                    'home_win': self._parse_percent(percent.get('home', '0%')),
                    'draw': self._parse_percent(percent.get('draw', '0%')),
                    'away_win': self._parse_percent(percent.get('away', '0%')),
                }
            self.cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Ошибка batch-прогнозов {league_id}: {e}")
            return {}

    @timing_decorator()
    def get_predictions(self, fixture_id):
        cache_key = f"pred_{fixture_id}"
        cached = self.cache.get(cache_key, data_type='predictions')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/predictions', {'fixture': fixture_id})
            if data and 'response' in data and data['response']:
                pred = data['response'][0].get('predictions', {})
                percent = pred.get('percent', {})
                result = {
                    'home_win': self._parse_percent(percent.get('home', '0%')),
                    'draw': self._parse_percent(percent.get('draw', '0%')),
                    'away_win': self._parse_percent(percent.get('away', '0%')),
                }
                self.cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Ошибка predictions {fixture_id}: {e}")
        return None

    def _parse_percent(self, s):
        try:
            return float(str(s).replace('%', '').strip()) / 100.0
        except (ValueError, TypeError):
            return 0.0

    # ============================================================
    # ★★★ ИСПРАВЛЕННАЯ ВЕРСИЯ (с _to_float)
    # ============================================================
    def _extract_best_odds(self, odds_data):
        result = {'best_odds': 0, 'bookmaker': '—', 'home_odds': 0,
                  'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0,
                  'btts_yes': 0, 'btts_no': 0, 'x2_odds': 0, '1x_odds': 0,
                  'all_bookmakers': {}}

        def _to_float(x):
            try:
                return float(x) if x is not None else 0.0
            except (ValueError, TypeError):
                return 0.0

        for bm in odds_data:
            bm_name = bm.get('bookmaker', {}).get('name', '—') if 'bookmaker' in bm else bm.get('name', '—')
            bm_data = {'home': 0, 'draw': 0, 'away': 0, '1x': 0, 'x2': 0}

            bets_list = bm.get('bets', [])
            for bet in bets_list:
                bn = bet.get('name', '').lower()
                values = bet.get('values', [])
                if not values:
                    continue

                if 'match' in bn or 'побед' in bn or '1x2' in bn or 'winner' in bn:
                    for v in values:
                        vn = str(v.get('value', '')).lower()
                        odd = _to_float(v.get('odd', 0))
                        if odd <= 0: continue
                        if 'home' in vn or vn == '1':
                            result['home_odds'] = max(result['home_odds'], odd)
                            bm_data['home'] = max(bm_data['home'], odd)
                        elif 'away' in vn or vn == '2':
                            result['away_odds'] = max(result['away_odds'], odd)
                            bm_data['away'] = max(bm_data['away'], odd)
                        elif 'draw' in vn or vn == 'x':
                            result['draw_odds'] = max(result['draw_odds'], odd)
                            bm_data['draw'] = max(bm_data['draw'], odd)
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bm_name

                if 'double chance' in bn or 'двойной шанс' in bn:
                    for v in values:
                        vn = str(v.get('value', '')).lower()
                        odd = _to_float(v.get('odd', 0))
                        if odd <= 0: continue
                        if 'home/draw' in vn or vn == '1x':
                            result['1x_odds'] = max(result['1x_odds'], odd)
                            bm_data['1x'] = max(bm_data['1x'], odd)
                        elif 'draw/away' in vn or vn == 'x2':
                            result['x2_odds'] = max(result['x2_odds'], odd)
                            bm_data['x2'] = max(bm_data['x2'], odd)

                if 'total' in bn or 'over/under' in bn or 'тотал' in bn:
                    for v in values:
                        vn = str(v.get('value', '')).lower()
                        odd = _to_float(v.get('odd', 0))
                        if odd <= 0: continue
                        if 'under' in vn or 'меньше' in vn:
                            result['under_odds'] = max(result['under_odds'], odd)
                        elif 'over' in vn or 'больше' in vn:
                            result['over_odds'] = max(result['over_odds'], odd)

                if 'both teams' in bn or 'btts' in bn or 'обе забьют' in bn:
                    for v in values:
                        vn = str(v.get('value', '')).lower()
                        odd = _to_float(v.get('odd', 0))
                        if odd <= 0: continue
                        if vn == 'yes' or 'да' in vn:
                            result['btts_yes'] = max(result['btts_yes'], odd)
                        elif vn == 'no' or 'нет' in vn:
                            result['btts_no'] = max(result['btts_no'], odd)

            if any(bm_data.get(k, 0) > 0 for k in bm_data):
                result['all_bookmakers'][bm_name] = bm_data

        # DC из 1X2 если нет прямых
        if result['x2_odds'] == 0 and result['draw_odds'] > 0 and result['away_odds'] > 0:
            result['x2_odds'] = round(1 / (1/result['draw_odds'] + 1/result['away_odds']), 2)
            result['dc_computed'] = True
        if result['1x_odds'] == 0 and result['draw_odds'] > 0 and result['home_odds'] > 0:
            result['1x_odds'] = round(1 / (1/result['draw_odds'] + 1/result['home_odds']), 2)
            result['dc_computed'] = True

        return result

    def clear_cache(self):
        self.cache.clear()

    def find_fixture_by_teams(self, home_team, away_team):
        try:
            for day_offset in [0, -1]:
                check_date = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET, days=day_offset)).strftime('%Y-%m-%d')
                data = self._make_request('/fixtures', {'date': check_date})
                if not data or 'response' not in data:
                    continue
                for f in data['response']:
                    t = f.get('teams', {})
                    h = (t.get('home', {}).get('name', '') or '').lower()
                    a = (t.get('away', {}).get('name', '') or '').lower()
                    home_l = home_team.lower()
                    away_l = away_team.lower()
                    h_match = (home_l == h) or (home_l in h) or (h in home_l)
                    a_match = (away_l == a) or (away_l in a) or (a in away_l)
                    if h_match and a_match:
                        return f.get('fixture', {}).get('id')
        except Exception as e:
            logger.error(f"Ошибка поиска матча: {e}")
        return None


football_api = FootballAPI()


# ============================================================
# ODDS API (отключён)
# ============================================================
class OddsAPIClient:
    def __init__(self, api_key=None):
        self.api_key = None
        self.base_url = None
        logger.info("⚠️ Odds API ОТКЛЮЧЁН")

    def get_odds_for_match(self, home_team, away_team, league):
        return None


odds_api = OddsAPIClient()


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
                             'Football API (X2)', 'Football API (1X)')
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
                        match_dt = match_dt - timedelta(hours=1)
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


# === КОНЕЦ ЧАСТИ 1/3 ===


# ============================================================
# main.py — ЧАСТЬ 2/3 (v4.3)
# Стратегии, 3 потока поиска, обновление результатов
# ★ Snapshots c home/away/league
# ★ Исключение для сборных в find_top_matches
# ============================================================

# ============================================================
# СИМУЛЯТОР
# ============================================================
class StrategySimulator:
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
                'min_ev': [5, 8, 10, 15, 20],
                'min_prob': [45, 50, 52, 55, 60],
                'min_odds': [1.4, 1.5, 1.6, 1.7],
                'max_odds': [3.0, 4.0, 5.0, 6.0, 8.0],
                'stake_pct': [1.5, 2.0, 2.5, 3.0],
            }
            results = []
            count = 0
            keys = list(grid.keys())
            values = [grid[k] for k in keys]
            for combo in itertools.product(*values):
                if count >= max_combinations: break
                params = dict(zip(keys, combo))
                params.update({'max_ev': 500, 'max_prob': 100,
                               'min_xg': 0.8, 'max_xg': 4.0,
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


# ============================================================
# УТИЛИТЫ
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
    """★ Возвращает (country_name, flag_emoji) для league_id."""
    try:
        lid = int(league_id) if league_id else None
    except (ValueError, TypeError):
        lid = None
    if lid is None:
        return ("", "")
    return Config.LEAGUE_COUNTRY.get(lid, ("", ""))


def _is_international_league(league_id, league_name):
    """★ Проверяет, относится ли матч к турнирам сборных."""
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
# POISSON / ENSEMBLE
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
                          is_international=False):
    engine = getattr(Config, 'PREDICTION_ENGINE', 'heuristic')
    poisson = calculate_poisson_probability(home_xg, away_xg)
    form_prob = calculate_form_probability(home_form, away_form)
    h2h_prob = calculate_h2h_probability(h2h_data)

    if is_international:
        # ★ Для сборных форма клуба/H2H менее показательны — урезаем их вес
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
    return final


def _apply_llm_to_match(match: dict, llm: dict, alpha: float = 0.7):
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
                b['ev'] = round((b['prob'] / 100 * b['odds'] - 1) * 100, 1)
    match['bets'].sort(key=lambda x: x['ev'], reverse=True)
    if match['bets']:
        match['best_bet'] = match['bets'][0]


# ============================================================
# РУЧНОЕ ОБНОВЛЕНИЕ
# ============================================================
def update_manual_result(match_name, score):
    try:
        hg = ag = None
        if score and '-' in score:
            parts = score.split('-')
            hg = int(parts[0].strip()); ag = int(parts[1].strip())
        history = storage.load_history()
        found = False
        result = 'pending'
        for bet in history:
            if bet.get('result') in ('pending', None):
                full = f"{bet.get('home', '')} vs {bet.get('away', '')}"
                if match_name.lower() in full.lower() or full.lower() in match_name.lower():
                    bet['home_goals'] = hg
                    bet['away_goals'] = ag
                    result = determine_bet_result(bet.get('bet', ''), hg, ag)
                    bet['result'] = result
                    if result == 'win':
                        bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                    elif result == 'loss':
                        bet['profit'] = -bet['stake']
                    else:
                        bet['profit'] = 0
                    found = True
                    break
        if found:
            storage.save_history(history)
            recalc_stats()
            return f"✅ {match_name} | {hg}-{ag} | {result}"
        return f"❌ '{match_name}' не найден"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def analyze_match(match_name):
    try:
        cache = storage.load_cache()
        matches = cache.get('top_matches', [])
        for m in matches:
            full = f"{m.get('home', '')} vs {m.get('away', '')}"
            if match_name.lower() in full.lower() or full.lower() in match_name.lower():
                src = m.get('source', '70_percent')
                src_label = {
                    'value': '💎 VALUE',
                    'tm25_premium': '🔥 PREMIUM ТМ 2.5',
                    'tm25_standard': '⭐ STANDARD ТМ 2.5',
                    '70_percent': '🎯 70%+',
                }.get(src, '🎯')
                country_str = ''
                if m.get('country'):
                    country_str = f" • {m.get('country_flag', '')} {m.get('country')}"
                r = (f"📊 <b>АНАЛИЗ</b>\n"
                     f"🏟️ {full}\n"
                     f"🏆 {m.get('league', '?')}{country_str}\n"
                     f"📅 {m.get('match_time', '?')}\n"
                     f"{src_label}\n\n")
                best = m.get('best_bet', {})
                r += f"🎯 <b>{best.get('label', '—')}</b>\n"
                r += f"📈 EV: {best.get('ev', 0)}% | Prob: {best.get('prob', 0)}%\n"
                r += f"💰 Кэф: {best.get('odds', 0)}\n\n"
                for i, b in enumerate(m.get('bets', [])[:7], 1):
                    emoji = "🟢" if b.get('ev', 0) > 10 else "🟡" if b.get('ev', 0) > 5 else "🔴"
                    r += f"{emoji} {i}. {b.get('label')} | EV: {b.get('ev')}% | КЭФ: {b.get('odds')}\n"
                r += f"\n⚽ XG: {m.get('total_xg', 0):.2f}\n"
                r += f"📈 Форма: {m.get('home_form')} vs {m.get('away_form')}"
                if m.get('weather_reason'):
                    r += f"\n{m['weather_reason']}"
                return r
        return f"❌ '{match_name}' не найден"
    except Exception as e:
        return f"❌ {e}"


# ============================================================
# ОБНОВЛЕНИЕ КЭФОВ
# ============================================================
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
    for idx, md in enumerate(matches, 1):
        if idx % 10 == 0:
            send_telegram(f"💓 <b>ОБНОВЛЕНИЕ КЭФОВ</b> | {idx}/{total}")
        try:
            home = md.get('home'); away = md.get('away')
            fid = md.get('fixture_id')
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
                if bm_list:
                    if bt == 'X2': target = 'x2'
                    elif bt == '1X': target = '1x'
                    elif bt in ('П1', '1'): target = 'home'
                    elif bt in ('П2', '2'): target = 'away'
                    elif bt == 'draw': target = 'draw'
                    else: target = 'home'
                    target_odds = {bm: data.get(target, 0)
                                   for bm, data in bm_list.items()
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
                            anomaly_bonus = min(anomaly_pct / 100, 0.10)
                            boosted = min(prob + anomaly_bonus, 0.95)
                            best_bet['prob'] = round(boosted * 100, 1)
                            best_bet['anomaly_bonus'] = round(anomaly_bonus * 100, 1)
                if not new_odds:
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
                    continue
                prob = best_bet.get('prob', 0) / 100
                best_bet['odds'] = round(new_odds, 2)
                best_bet['ev'] = round((prob * new_odds - 1) * 100, 1)
                best_bet['bookmaker'] = bookmaker
                best_bet['odds_source'] = source
                best_bet['odds_updated'] = True
                md['best_bet'] = best_bet
                md['odds_updated'] = True
                try:
                    market_map = {
                        'draw': ('1X2', 'X'), 'btts': ('BTTS', 'BTTS'),
                        'over25': ('O/U 2.5', 'Over'), 'under25': ('O/U 2.5', 'Under'),
                        'over': ('O/U 2.5', 'Over'), 'under': ('O/U 2.5', 'Under'),
                        'underdog': ('1X2', 'Underdog'),
                        'П1': ('1X2', '1'), 'П2': ('1X2', '2'),
                        '1X': ('DC', '1X'), 'X2': ('DC', 'X2'),
                    }
                    mkt, sel = market_map.get(bt, (bt, 'unknown'))
                    # ★ v4.3: передаём home/away/league в БД
                    storage.save_odds_snapshot(
                        fixture_id=fid, market=mkt,
                        selection=sel, odds=new_odds, bookmaker=bookmaker,
                        home=home or '', away=away or '',
                        league=md.get('league', '') or ''
                    )
                except Exception as e:
                    logger.error(f"Ошибка записи снимка: {e}")
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
# ПОИСК МАТЧЕЙ + ФАКТОРЫ
# ============================================================
def get_matches_with_factors():
    all_matches = []
    today = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d')
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
# ★ ПОТОК 1: 70%+
# ============================================================
@timing_decorator()
def find_top_matches(matches):
    bank = storage.load_bank()
    max_bets = getattr(Config, 'MAX_BETS_PER_RUN', 30)
    total_matches = len(matches)
    logger.info(f"🔍 [70%+] Анализ {total_matches} матчей...")
    blacklist = getattr(Config, 'BLACKLIST_LEAGUES', [])
    best_matches = []
    bet_type_count = {}
    league_count = {}
    x2_saved_count = 0

    X2_ENABLED = getattr(Config, 'X2_ENABLED', True)
    X2_MIN_POSITION_DIFF = getattr(Config, 'X2_MIN_POSITION_DIFF', 3)
    X2_MAX_POSITION = getattr(Config, 'X2_MAX_POSITION', 20)
    X2_MIN_EV = getattr(Config, 'X2_MIN_EV', 5)
    X2_MIN_PROB = getattr(Config, 'X2_MIN_PROB', 55)
    X2_BOTH_SIDES = getattr(Config, 'X2_BOTH_SIDES', True)

    for match_idx, match in enumerate(matches):
        if not match or not isinstance(match, dict): continue
        if (match_idx + 1) % 30 == 0:
            send_telegram(f"💓 <b>АНАЛИЗ 70%+</b> | {match_idx + 1}/{total_matches}\n"
                          f"🎯 Кандидатов: {len(best_matches)} | X2: {x2_saved_count}")
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

            # ★ v4.3: проверяем, турнир сборных
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

            # ★ v4.3: сборные играют на нейтральных полях
            if is_international:
                home_adv = 1.03
            else:
                home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            total_xg = home_xg + away_xg

            w = match.get('weather')
            if w:
                rain = w.get('rain', 0) or 0
                wind = w.get('wind', 0) or 0
                if rain > 2:
                    total_xg *= 0.92; home_xg *= 0.95; away_xg *= 0.95
                elif rain > 0.5:
                    total_xg *= 0.96
                if wind > 10:
                    total_xg *= 0.95
                elif wind > 7:
                    total_xg *= 0.98

            XG_MIN = getattr(Config, 'XG_MIN_70', 1.2)
            XG_MAX = getattr(Config, 'XG_MAX_70', 3.8)
            POS_MAX = getattr(Config, 'POSITION_MAX_70', 18)
            if total_xg < XG_MIN or total_xg > XG_MAX: continue

            standings = football_api.get_standings(league_id) if league_id else None
            hp = standings.get(home, {}).get('position', 99) if standings else 99
            ap = standings.get(away, {}).get('position', 99) if standings else 99

            # ★ v4.3: для сборных фильтры по позициям/мотивации не применяем
            if is_international:
                hm = am = 'international'
            else:
                hm = get_motivation(hp); am = get_motivation(ap)
                if getattr(Config, 'SKIP_MID_TABLE_70', False) and hm == 'mid_table' and am == 'mid_table':
                    continue
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

            if hm == 'relegation' and am == 'mid_table':
                probs['home_win'] = probs.get('home_win', 0) + 0.05
            elif am == 'relegation' and hm == 'mid_table':
                probs['away_win'] = probs.get('away_win', 0) + 0.05

            stake = round(bank * 0.02, 2) if bank > 0 else 10.0
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
                bets.append({
                    'type': bt, 'label': label,
                    'prob': round(p * 100, 1),
                    'ev': round((p * odds_template[key] - 1) * 100, 1),
                    'odds': odds_template[key], 'stake': stake,
                    'odds_updated': False,
                })
            if not bets: continue
            bets.sort(key=lambda x: x['ev'], reverse=True)
            best_bet = bets[0]

            EV_MIN_70 = getattr(Config, 'EV_MIN_70', 8)
            PROB_MIN_70 = getattr(Config, 'PROB_MIN_70', 52)
            if best_bet['ev'] < EV_MIN_70: continue
            if best_bet['prob'] < PROB_MIN_70: continue

            bt = best_bet['type']
            LIMIT_BT = getattr(Config, 'LIMIT_BET_TYPE_70', 15)
            LIMIT_LG = getattr(Config, 'LIMIT_LEAGUE_70', 5)
            bet_type_count[bt] = bet_type_count.get(bt, 0) + 1
            if bet_type_count[bt] > LIMIT_BT: continue
            league_count[league_name] = league_count.get(league_name, 0) + 1
            if league_count[league_name] > LIMIT_LG: continue

            # ★★ X2-СОХРАНЕНИЕ с entry_odds
            # v4.3: для сборных X2 не применяем — позиции нерелевантны
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
                            logger.info(f"💾 X2: {home} vs {away} | {x2_side} @ {entry_odds}")
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
    logger.info(f"📊 [70%+] Итого: {len(top)}, X2-сохранено: {x2_saved_count}")

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
        except Exception as e:
            logger.error(f"❌ LLM ошибка: {e}")
    return top


# ============================================================
# ★ ПОТОК 2: ТМ 2.5
# ============================================================
@timing_decorator()
def find_tm25_matches(matches):
    tm25_candidates = []
    MAX_TM25_BETS = getattr(Config, 'MAX_TM25_BETS', 5)
    PREMIUM_MIN_EV = getattr(Config, 'PREMIUM_MIN_EV', 25) / 100
    PREMIUM_MIN_PROB = getattr(Config, 'PREMIUM_MIN_PROB', 58) / 100
    PREMIUM_XG_MIN = getattr(Config, 'PREMIUM_XG_MIN', 1.0)
    PREMIUM_XG_MAX = getattr(Config, 'PREMIUM_XG_MAX', 2.8)
    STANDARD_MIN_EV = getattr(Config, 'STANDARD_MIN_EV', 15) / 100
    STANDARD_MIN_PROB = getattr(Config, 'STANDARD_MIN_PROB', 52) / 100
    STANDARD_XG_MIN = getattr(Config, 'TM25_XG_MIN', 0.8)
    STANDARD_XG_MAX = getattr(Config, 'TM25_XG_MAX', 3.0)

    logger.info("🔍 [ТМ 2.5] Единый поиск...")
    stats = {'premium_found': 0, 'standard_found': 0}
    seen_keys = set()

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

            standings = football_api.get_standings(league_id) if league_id else None
            hp = standings.get(home, {}).get('position', 99) if standings else 99
            ap = standings.get(away, {}).get('position', 99) if standings else 99

            h2h = football_api.get_head_to_head(home, away)
            probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h)
            p_under = probs.get('under25', probs.get('under_2_5', 0))
            odds_tm25 = 1.95
            ev_under = (p_under * odds_tm25) - 1

            country_name, country_flag = _get_country_flag(league_id)

            if (PREMIUM_XG_MIN <= total_xg <= PREMIUM_XG_MAX
                and ev_under >= PREMIUM_MIN_EV and p_under >= PREMIUM_MIN_PROB):
                if league_name in TOP_LEAGUES and ev_under < 0.35: continue
                best_bet = {'type': 'under', 'label': 'ТМ 2.5 🔥',
                            'prob': round(p_under * 100, 1),
                            'ev': round(ev_under * 100, 1),
                            'odds': odds_tm25, 'stake': round(42.87, 2),
                            'level': 'PREMIUM', 'odds_updated': False}
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
                continue

            if (STANDARD_XG_MIN <= total_xg <= STANDARD_XG_MAX
                and ev_under >= STANDARD_MIN_EV and p_under >= STANDARD_MIN_PROB):
                if league_name in TOP_LEAGUES and ev_under < 0.20: continue
                best_bet = {'type': 'under', 'label': 'ТМ 2.5',
                            'prob': round(p_under * 100, 1),
                            'ev': round(ev_under * 100, 1),
                            'odds': odds_tm25, 'stake': round(42.87, 2),
                            'level': 'STANDARD', 'odds_updated': False}
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
        except Exception as e:
            logger.error(f"❌ [ТМ2.5] {e}")
            continue

    logger.info(f"📊 [ТМ2.5] PREMIUM: {stats['premium_found']}, STANDARD: {stats['standard_found']}")
    tm25_candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    return tm25_candidates


# ============================================================
# ★ ПОТОК 3: VALUE
# ============================================================
@timing_decorator()
def find_value_matches(matches, max_bets=2):
    VALUE_MIN_ODDS = getattr(Config, 'VALUE_MIN_ODDS', 2.50)
    VALUE_MIN_EV = getattr(Config, 'VALUE_MIN_EV', 25)
    VALUE_MIN_PROB = getattr(Config, 'VALUE_MIN_PROB', 50)
    VALUE_MIN_XG_DIFF = getattr(Config, 'VALUE_MIN_XG_DIFF', 0.3)
    VALUE_MAX_RESULTS = max_bets

    logger.info(f"💎 [VALUE] Поиск: кэф>={VALUE_MIN_ODDS}, EV>={VALUE_MIN_EV}%, Prob>={VALUE_MIN_PROB}%")

    value_candidates = []
    blacklist = getattr(Config, 'BLACKLIST_LEAGUES', [])

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
            home_xg = (hga + aca) / 2
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
            if not fo:
                continue

            def _compute_value(model_prob, odds):
                if model_prob <= 0 or odds <= 1.01:
                    return None
                if model_prob * 100 > getattr(Config, 'VALUE_MAX_PROB', 80):
                    return None
                market_prob = 1.0 / odds
                ratio = model_prob / market_prob if market_prob > 0 else 0
                if ratio > getattr(Config, 'VALUE_MAX_RATIO', 2.2):
                    return None
                blended = model_prob * 0.35 + market_prob * 0.65
                ev = (blended * odds - 1) * 100
                return (ev, blended)

            candidates_bc = []

            p_1x = probs.get('1X', 0)
            odds_1x = fo.get('1x_odds', 0) or 0
            if odds_1x >= VALUE_MIN_ODDS:
                res = _compute_value(p_1x, odds_1x)
                if res:
                    ev, bp = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': '1X', 'label': '1X 💎',
                            'prob': round(bp * 100, 1),
                            'model_prob': round(p_1x * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_1x,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            p_x2 = probs.get('X2', 0)
            odds_x2 = fo.get('x2_odds', 0) or 0
            if odds_x2 >= VALUE_MIN_ODDS:
                res = _compute_value(p_x2, odds_x2)
                if res:
                    ev, bp = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': 'X2', 'label': 'X2 💎',
                            'prob': round(bp * 100, 1),
                            'model_prob': round(p_x2 * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_x2,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            p_home = probs.get('home_win', 0)
            odds_home = fo.get('home_odds', 0) or 0
            if odds_home >= VALUE_MIN_ODDS:
                res = _compute_value(p_home, odds_home)
                if res:
                    ev, bp = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': 'П1', 'label': 'П1 💎',
                            'prob': round(bp * 100, 1),
                            'model_prob': round(p_home * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_home,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            p_away = probs.get('away_win', 0)
            odds_away = fo.get('away_odds', 0) or 0
            if odds_away >= VALUE_MIN_ODDS:
                res = _compute_value(p_away, odds_away)
                if res:
                    ev, bp = res
                    if ev >= VALUE_MIN_EV:
                        candidates_bc.append({
                            'type': 'П2', 'label': 'П2 💎',
                            'prob': round(bp * 100, 1),
                            'model_prob': round(p_away * 100, 1),
                            'ev': round(ev, 1), 'odds': odds_away,
                            'bookmaker': fo.get('bookmaker', '—'),
                        })

            if not candidates_bc:
                continue

            candidates_bc.sort(key=lambda x: x['ev'], reverse=True)
            best_bet = candidates_bc[0]

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
                f"Prob: {best_bet['prob']}%"
            )

        except Exception as e:
            logger.error(f"❌ [VALUE] {e}")
            continue

    value_candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top = value_candidates[:VALUE_MAX_RESULTS]
    logger.info(f"💎 [VALUE] Найдено: {len(value_candidates)}, взято: {len(top)}")
    return top


# ============================================================
# КОМБИНИРОВАННЫЙ ПОИСК
# ============================================================
@timing_decorator()
def find_top_matches_with_tm25(matches):
    logger.info("=" * 60)
    logger.info("📊 ПОТОК 1: 70%+")
    logger.info("=" * 60)
    top_matches_70 = find_top_matches(matches)

    logger.info("=" * 60)
    logger.info("📊 ПОТОК 2: ТМ 2.5")
    logger.info("=" * 60)
    tm25_matches = find_tm25_matches(matches)

    logger.info("=" * 60)
    logger.info("📊 ПОТОК 3: VALUE 💎")
    logger.info("=" * 60)
    value_matches = find_value_matches(matches, max_bets=2)

    combined = []
    keys = set()

    for m in value_matches:
        key = f"{m['home']}_{m['away']}"
        if key not in keys:
            combined.append(m); keys.add(key)

    for m in top_matches_70:
        key = f"{m['home']}_{m['away']}"
        if key not in keys:
            combined.append(m); keys.add(key)

    for m in tm25_matches:
        key = f"{m['home']}_{m['away']}"
        if key not in keys:
            combined.append(m); keys.add(key)

    combined.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    all_before_odds_filter = copy.deepcopy(combined)

    if combined:
        logger.info(f"📡 Обновление кэфов для {len(combined)} матчей...")
        combined = update_odds_for_matches(combined)

    if not combined:
        with cache_lock:
            cache = storage.load_cache()
            cache['top_matches'] = []
            cache['all_analyzed'] = all_before_odds_filter
            storage.save_cache(cache)
        return []

    for m in combined:
        bets = [b for b in m.get('bets', []) if b.get('odds', 0) > 1.01]
        if not bets: continue
        bets.sort(key=lambda x: x.get('ev', 0), reverse=True)
        m['bets'] = bets
        m['best_bet'] = bets[0]
        if not m.get('fixture_id'):
            logger.warning(f"⚠️ Потерян fixture_id для {m.get('home')} vs {m.get('away')}")

    EV_MIN = getattr(Config, 'EV_FINAL_MIN', -15)
    EV_MAX = getattr(Config, 'EV_FINAL_MAX', 150)
    PROB_MIN = getattr(Config, 'PROB_FINAL_MIN', 40)
    filtered = []
    for m in combined:
        bb = m.get('best_bet', {})
        ev = bb.get('ev', 0)
        prob = bb.get('prob', 0)
        if m.get('source') == 'value':
            if ev < EV_MIN: continue
            if prob < PROB_MIN: continue
        else:
            if ev < EV_MIN or ev > EV_MAX: continue
            if prob < PROB_MIN: continue
        if not bb.get('odds_updated'):
            bb['odds_source'] = 'template'
            bb['odds_note'] = '⚠️ кэф не найден'
        m.pop('_preloaded_odds', None)
        m.pop('_preloaded_preds', None)
        filtered.append(m)

    logger.info(f"📊 После фильтра: {len(filtered)} из {len(combined)}")

    with cache_lock:
        cache = storage.load_cache()
        cache['top_matches'] = filtered
        cache['all_analyzed'] = all_before_odds_filter
        storage.save_cache(cache)

    history = storage.load_history()
    today_str = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d')
    existing = {(h.get('home'), h.get('away'), h.get('date', '').split()[0])
                for h in history}
    added = 0
    for md in filtered:
        bb = md.get('best_bet', {})
        key = (md.get('home'), md.get('away'), today_str)
        if key in existing: continue
        existing.add(key)
        if not md.get('fixture_id'): continue
        history.append({
            'home': md.get('home'), 'away': md.get('away'),
            'league': md.get('league'),
            'bet': bb.get('label', '—'),
            'odds': bb.get('odds', 0),
            'stake': bb.get('stake', 0),
            'ev': bb.get('ev', 0), 'prob': bb.get('prob', 0),
            'result': 'pending', 'profit': 0,
            'date': (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d %H:%M'),
            'fixture_id': md.get('fixture_id'),
            'bookmaker': bb.get('bookmaker', '—'),
            'engine': Config.PREDICTION_ENGINE,
            'weather_reason': md.get('weather_reason', ''),
            'source': md.get('source', '70_percent'),
        })
        added += 1
    storage.save_history(history)
    logger.info(f"📝 Добавлено ставок: {added}")

    try:
        placed = autobet_manager.place_bets_from_cache()
        if placed > 0:
            logger.info(f"💸 Автоставок размещено: {placed}")
    except Exception as e:
        logger.error(f"Ошибка автоставок: {e}")

    logger.info("=" * 60)
    return filtered


# ============================================================
# ОБНОВЛЕНИЕ PENDING
# ============================================================
@timing_decorator()
def update_pending_bets():
    history = storage.load_history()
    updated = 0
    live_updated = 0
    for bet in history:
        if bet.get('result') in ('pending', None):
            fid = bet.get('fixture_id')
            if not fid:
                fid = football_api.find_fixture_by_teams(bet.get('home', ''), bet.get('away', ''))
                if fid:
                    bet['fixture_id'] = fid
            if fid:
                md = football_api.get_match_result(fid)
                if md:
                    hg = md['goals']['home']; ag = md['goals']['away']
                    if hg is None or ag is None:
                        continue
                    status = md.get('status', 'NS')
                    date_str = bet.get('date', '')
                    match_time_str = ''
                    if date_str and ' ' in date_str:
                        parts = date_str.split()
                        if len(parts) >= 2:
                            try:
                                d = datetime.strptime(parts[0], '%Y-%m-%d')
                                match_time_str = d.strftime('%d.%m.%Y') + ' ' + parts[1]
                            except Exception:
                                pass
                    force_final = is_force_final(match_time_str, status)
                    if not md.get('is_final', False) and not force_final:
                        if md.get('is_live', False):
                            bet['live_score'] = f"{hg}-{ag}"
                            bet['live_status'] = status
                            bet['live_minute'] = md.get('minute', 0)
                            ht = md.get('halftime', {}) or {}
                            if ht.get('home') is not None:
                                bet['live_halftime'] = f"{ht.get('home')}-{ht.get('away')}"
                            live_updated += 1
                        continue
                    result = determine_bet_result(bet.get('bet', ''), hg, ag)
                    if result != 'pending':
                        bet['result'] = result
                        bet['home_goals'] = hg
                        bet['away_goals'] = ag
                        if md.get('halftime'):
                            bet['halftime_home'] = md['halftime'].get('home')
                            bet['halftime_away'] = md['halftime'].get('away')
                        if result == 'win':
                            bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                        elif result == 'loss':
                            bet['profit'] = -bet['stake']
                        else:
                            bet['profit'] = 0
                        bet.pop('live_score', None)
                        bet.pop('live_status', None)
                        bet.pop('live_minute', None)
                        bet.pop('live_halftime', None)
                        updated += 1
    if updated > 0 or live_updated > 0:
        storage.save_history(history)
        if updated > 0:
            recalc_stats()
    logger.info(f"🔄 update_pending_bets: FT={updated}, LIVE={live_updated}")
    return {'ft': updated, 'live': live_updated}


def recalc_stats():
    history = storage.load_history()
    stats = storage.load_stats()
    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    pushes = sum(1 for b in history if b.get('result') == 'push')
    profit = sum(b.get('profit', 0) for b in history)
    stake_sum = sum(b.get('stake', 0) for b in history)
    stats.update({
        'total': total, 'wins': wins, 'losses': losses, 'pushes': pushes,
        'total_profit': round(profit, 2),
        'winrate': round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0,
        'roi': round(profit / stake_sum * 100, 1) if stake_sum else 0,
    })
    storage.save_stats(stats)


# ============================================================
# СНИМКИ КЭФОВ (★ v4.3 с home/away/league)
# ============================================================
def snapshot_odds_for_upcoming():
    logger.info("🔍 snapshot: НАЧАЛО")
    try:
        with cache_lock:
            cache = storage.load_cache()
            matches = cache.get('all_analyzed') or cache.get('top_matches', [])
        if not matches:
            return 0
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)

        groups = defaultdict(list)
        single = []
        for md in matches:
            match_time_str = md.get('match_time', '')
            if not match_time_str or match_time_str == '?':
                continue
            try:
                match_dt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")
            except ValueError:
                continue
            hours_to_match = (match_dt - now_msk).total_seconds() / 3600
            if hours_to_match < -24:
                continue
            if not (0 < hours_to_match <= 12):
                continue
            fid = md.get('fixture_id')
            if not fid: continue
            league_name = md.get('league', '')
            league_id = None
            for lid, lname in Config.LEAGUE_NAMES.items():
                if lname == league_name:
                    league_id = lid
                    break
            if league_id:
                date_str = match_dt.strftime('%Y-%m-%d')
                groups[(league_id, date_str)].append(md)
            else:
                single.append(md)

        total_snapshots = 0
        for (league_id, date_str), group in groups.items():
            try:
                batch = football_api.get_odds_batch_for_league(league_id, date_str)
                for md in group:
                    fid = md.get('fixture_id')
                    fo = batch.get(fid)
                    if not fo: continue
                    # ★ v4.3: передаём home/away/league
                    saved = _save_snapshot_from_odds(
                        fo, fid,
                        home=md.get('home', ''),
                        away=md.get('away', ''),
                        league=md.get('league', ''),
                    )
                    total_snapshots += saved
            except Exception as e:
                logger.error(f"snapshot batch {league_id}: {e}")

        for md in single:
            try:
                fid = md.get('fixture_id')
                if not fid: continue
                fo = football_api.get_match_odds(fid)
                if not fo: continue
                # ★ v4.3: передаём home/away/league
                saved = _save_snapshot_from_odds(
                    fo, fid,
                    home=md.get('home', ''),
                    away=md.get('away', ''),
                    league=md.get('league', ''),
                )
                total_snapshots += saved
            except Exception as e:
                logger.error(f"snapshot single: {e}")

        logger.info(f"📸 Снимков: {total_snapshots}")
        return total_snapshots
    except Exception as e:
        logger.exception(f"❌ snapshot: {e}")
        return 0


def _save_snapshot_from_odds(fo, fid, home='', away='', league=''):
    """
    ★ Сохраняет снимки: 1X2 + DC (X2 и 1X).
    ★ v4.3: принимает home/away/league для хранения в БД.
    """
    try:
        if not fo:
            return 0
        bookmaker = fo.get('bookmaker', 'Football API')
        saved = 0

        # ── 1X2 ──
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

        # ── ★ DC (X2 и 1X) ──
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

        return saved
    except Exception as e:
        logger.error(f"_save_snapshot_from_odds: {e}")
        return 0


# === КОНЕЦ ЧАСТИ 2/3 (v4.3) ===


# ============================================================
# main.py — ЧАСТЬ 3/3 (v4.3)
# Schedulers, Webhook, API, __main__
# ★ Snapshots API без fallback'ов — работают напрямую из SQLite
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
    scheduler.add_job(
        func=safe_job(auto_update_results, "auto_update_results"),
        trigger='interval', hours=6, id='auto_update',
        replace_existing=True, misfire_grace_time=300,
        coalesce=True, max_instances=1
    )
    scheduler.start()
    logger.info("⏰ Авто-обновление: 6ч")


def update_x2_results():
    """Обновляет X2-кандидатов после завершения матчей.
    Fallback: если API залип на NS, но матч был >2.5ч назад — закрываем по времени."""
    try:
        candidates = storage.get_x2_candidates(limit=200)
        updated = 0
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)

        for c in candidates:
            if c.get('result') in ('win', 'loss', 'push'):
                continue

            fid = c.get('fixture_id')
            if not fid:
                continue

            md = football_api.get_match_result(fid)
            if not md:
                continue

            hg = md['goals']['home']
            ag = md['goals']['away']
            if hg is None or ag is None:
                continue

            status = md.get('status', 'NS')
            is_final = md.get('is_final', False)

            force_final = False
            hours_ago = 0
            if not is_final:
                match_time_str = c.get('match_time', '')
                if match_time_str and match_time_str != '?':
                    try:
                        mt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")
                        hours_ago = (now_msk - mt).total_seconds() / 3600
                        if hours_ago > 2.5:
                            force_final = True
                    except Exception:
                        pass
                if not force_final:
                    continue
                logger.info(f"🔧 X2 FORCE-FINAL: {c.get('home')} vs {c.get('away')} "
                            f"(был {status}, {hours_ago:.1f}ч назад)")

            side = c.get('x2_side', 'X2')
            if side == 'X2':
                result = 'win' if ag >= hg else 'loss'
            else:
                result = 'win' if hg >= ag else 'loss'

            odds = float(c.get('entry_odds', 0) or 0)
            if odds < 1.01:
                odds = 1.85

            stake = 20.0
            if result == 'win':
                profit = round(stake * (odds - 1), 2)
            elif result == 'loss':
                profit = -stake
            else:
                profit = 0

            ok = storage.update_x2_result(
                candidate_id=c['id'],
                result=result,
                profit=profit,
                home_goals=hg,
                away_goals=ag,
            )
            if ok:
                updated += 1
                logger.info(f"🎯 X2: {c.get('home')} vs {c.get('away')} "
                            f"→ {result.upper()} ({hg}:{ag}) | ${profit:+.2f}")

        if updated > 0:
            logger.info(f"✅ X2-результатов обновлено: {updated}")
        return updated
    except Exception as e:
        logger.exception(f"update_x2_results: {e}")
        return 0


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
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=safe_job(autobet_manager.place_bets_from_cache, "autobet_place"),
        trigger='interval', minutes=30, id='autobet_place',
        replace_existing=True, max_instances=1,
        misfire_grace_time=60, coalesce=True
    )
    scheduler.add_job(
        func=safe_job(autobet_manager.settle_pending, "autobet_settle"),
        trigger='interval', hours=2, id='autobet_settle',
        replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    scheduler.add_job(
        func=safe_job(autobet_manager.compute_clv_for_settled, "autobet_clv"),
        trigger='interval', hours=6, id='autobet_clv',
        replace_existing=True, max_instances=1,
        misfire_grace_time=300, coalesce=True
    )
    scheduler.start()


MAX_BACKUPS = 7


def cleanup_old_backups():
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        files = sorted([f for f in os.listdir(BACKUP_DIR)
                        if f.startswith('backup_') and f.endswith('.zip')], reverse=True)
        for old in files[MAX_BACKUPS:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception as e:
                logger.error(f"Ошибка удаления {old}: {e}")
    except Exception as e:
        logger.error(f"❌ cleanup: {e}")


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
                '/data/matches_log.txt',
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
        trigger='cron', hour=0, minute=0, id='auto_backup',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(trim_matches_log, "trim_matches_log"),
        trigger='cron', hour=2, minute=0, id='trim_log',
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
        }

    def _classify(self, bet_label, source=None):
        if source == 'value':
            return 'value'
        if source == 'tm25_premium':
            return 'tm25_premium'
        if source == 'tm25_standard':
            return 'tm25_standard'
        if not bet_label:
            return '70_percent'
        l = bet_label.lower()
        if '💎' in bet_label:
            return 'value'
        if '🔥' in bet_label or 'premium' in l:
            return 'tm25_premium'
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


# ============================================================
# WEBHOOK RATE-LIMIT
# ============================================================
_webhook_hits = defaultdict(list)
_webhook_lock = Lock()
WEBHOOK_MAX_PER_MINUTE = 30


def _check_webhook_rate_limit(chat_id):
    try:
        with _webhook_lock:
            now = time.time()
            _webhook_hits[chat_id] = [t for t in _webhook_hits[chat_id] if now - t < 60]
            if len(_webhook_hits[chat_id]) >= WEBHOOK_MAX_PER_MINUTE:
                return False
            _webhook_hits[chat_id].append(now)
            return True
    except Exception:
        return True


# ============================================================
# WEBHOOK
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running, search_state
    try:
        data = request.get_json()
        if not data:
            return "ok", 200

        if 'callback_query' in data:
            cb = data['callback_query']
            try:
                requests.post(
                    f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cb.get('id', ''), "text": "✅ Принято!"}
                )
            except Exception as e:
                logger.error(f"Ответ: {e}")
            return "ok", 200

        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            if str(chat_id) != str(Config.ADMIN_CHAT_ID):
                return "ok", 200
            if not _check_webhook_rate_limit(chat_id):
                send_telegram("⚠️ Слишком много команд.")
                return "ok", 200

            if text == '/start':
                send_telegram(handlers.handle_start())
            elif text == '/help':
                send_telegram(handlers.handle_help())

            elif text == '/analyze':
                send_telegram("⚠️ <code>/analyze Fulham vs Chelsea</code>")
            elif text.startswith('/analyze '):
                send_telegram(analyze_match(text[9:].strip()))

            elif text == '/team':
                send_telegram("⚠️ <code>/team Arsenal</code>")
            elif text.startswith('/team '):
                send_telegram(handlers.handle_team(text[6:].strip()))

            elif text == '/result':
                send_telegram("⚠️ <code>/result Fulham vs Chelsea 2-1</code>")
            elif text.startswith('/result '):
                parts = text[8:].strip()
                if ' vs ' in parts:
                    sp = parts.split(' vs ')
                    home = sp[0].strip()
                    rest = sp[1].split()
                    if len(rest) >= 2:
                        send_telegram(update_manual_result(f"{home} vs {rest[0]}", rest[1]))
                else:
                    send_telegram("⚠️ <code>/result Fulham vs Chelsea 2-1</code>")

            elif text == '/update':
                if search_running:
                    send_telegram("⚠️ Поиск уже запущен")
                    return "ok", 200
                search_running = True
                search_state = {'start_time': datetime.now()}
                send_telegram("🔎 Запущен анализ. Ждите...")

                def run_search():
                    global search_running
                    try:
                        matches = get_matches_with_factors()
                        if matches:
                            top = find_top_matches_with_tm25(matches)
                            if top:
                                value_list = [m for m in top if m.get('source') == 'value']
                                other_list = [m for m in top if m.get('source') != 'value']

                                msg = f"✅ <b>НАЙДЕНО: {len(top)}</b>\n"

                                if value_list:
                                    msg += f"\n💎 <b>VALUE ({len(value_list)}):</b>\n\n"
                                    for i, m in enumerate(value_list, 1):
                                        b = m['best_bet']
                                        msg += (f"{i}. <b>{m['home']} vs {m['away']}</b> 💎\n"
                                                f"🏆 {m.get('league', '?')}\n"
                                                f"📅 {m.get('match_time', '?')}\n"
                                                f"🎯 {b['label']} | КЭФ: {b['odds']} | EV: {b['ev']}%\n"
                                                f"📊 Prob: {b['prob']}% | XG: {m.get('total_xg', 0):.2f}\n"
                                                f"🏷️ {b.get('bookmaker', '—')}\n\n")

                                if other_list:
                                    msg += f"\n🎯 <b>ОСТАЛЬНЫЕ ({len(other_list)}):</b>\n\n"
                                    for i, m in enumerate(other_list[:15], 1):
                                        b = m['best_bet']
                                        bonus = b.get('anomaly_bonus', 0)
                                        bonus_str = f" (+{bonus}% аномалия)" if bonus else ""
                                        src = m.get('source', '')
                                        lv = (" 🔥 PREMIUM" if src == 'tm25_premium'
                                              else (" ⭐ STANDARD" if src == 'tm25_standard' else ""))
                                        template_note = (" ⚠️ кэф шаблонный"
                                                         if b.get('odds_source') == 'template' else "")
                                        msg += (f"{i}. <b>{m['home']} vs {m['away']}</b>{lv}\n"
                                                f"🏆 {m.get('league', '?')}\n"
                                                f"📅 {m.get('match_time', '?')}\n"
                                                f"🎯 {b['label']} | КЭФ: {b['odds']} | EV: {b['ev']}%{bonus_str}{template_note}\n"
                                                f"📊 Prob: {b['prob']}% | XG: {m.get('total_xg', 0):.2f}\n"
                                                f"🏷️ {b.get('bookmaker', '—')}\n\n")
                                send_telegram(msg)
                            else:
                                send_telegram("❌ Ничего не найдено")
                        else:
                            send_telegram("❌ Матчей нет")
                    finally:
                        search_running = False

                Thread(target=run_search, daemon=True).start()

            elif text == '/reset_search':
                search_running = False
                send_telegram("✅ Сброшено")
            elif text == '/stop':
                search_running = False
                send_telegram("⏹️ Остановлено")

            elif text == '/today':
                send_telegram(handlers.handle_today())
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            elif text == '/report':
                send_telegram(handlers.handle_report())
            elif text == '/bettypes':
                send_telegram(handlers.handle_bettypes())
            elif text == '/timestats':
                send_telegram(handlers.handle_timestats())
            elif text == '/strategies':
                send_telegram(strategy_tester.get_comparison_report())

            elif text == '/x2_info':
                try:
                    candidates = storage.get_x2_candidates(limit=500)
                    msg = f"🎯 <b>X2-КАНДИДАТЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += f"📊 Всего: <b>{len(candidates)}</b>\n\n"
                    if candidates:
                        msg += "🎯 <b>Последние 5:</b>\n"
                        for c in candidates[-5:][::-1]:
                            side = c.get('x2_side', 'X2')
                            ev = c.get('x2_ev', 0)
                            prob = c.get('x2_prob', 0)
                            entry = c.get('entry_odds', 0) or 0
                            res = c.get('result', 'pending')
                            emoji = '✅' if res == 'win' else '❌' if res == 'loss' else '⏳'
                            msg += (f"  {emoji} <b>{c.get('home')} vs {c.get('away')}</b>\n"
                                    f"    {side} @ {entry} | EV: {ev}% | Prob: {prob}%\n\n")
                    else:
                        msg += "📭 Пока нет кандидатов\n"
                    send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/update_results':
                res = update_pending_bets()
                x2 = update_x2_results()
                ft = res.get('ft', 0); live = res.get('live', 0)
                if ft == 0 and live == 0 and x2 == 0:
                    send_telegram("📭 <b>Нет обновлений</b>")
                else:
                    msg = "🔄 <b>ОБНОВЛЕНО</b>\n\n"
                    if ft > 0: msg += f"✅ Завершено матчей: <b>{ft}</b>\n"
                    if live > 0: msg += f"⚽ Live-счёт: <b>{live}</b>\n"
                    if x2 > 0: msg += f"🎯 X2-результатов: <b>{x2}</b>\n"
                    send_telegram(msg)

            elif text == '/live':
                try:
                    bets = storage.autobet_load_all()
                    pending = [b for b in bets if b.get('result') == 'pending']
                    live_bets = [b for b in pending if b.get('live_score')]
                    no_live = [b for b in pending if not b.get('live_score')]
                    if not live_bets and not no_live:
                        send_telegram("📭 Нет активных матчей")
                    else:
                        status_map = {'1H': '1-й тайм', 'HT': 'Перерыв ⏸️',
                                      '2H': '2-й тайм', 'ET': 'Доп. время',
                                      'P': 'Пенальти', 'BT': 'Перерыв',
                                      'SUSP': 'Приостановлен', 'LIVE': 'LIVE'}
                        msg = f"⚽ <b>LIVE ({len(live_bets)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        for b in live_bets:
                            status = status_map.get(b.get('live_status', ''), 'LIVE')
                            minute = b.get('live_minute') or 0
                            ms = f" <b>{minute}'</b>" if minute else ""
                            msg += (f"🏟️ <b>{b.get('home')} vs {b.get('away')}</b>\n"
                                    f"⚽ <b>{b.get('live_score')}</b>{ms} • {status}\n"
                                    f"🎯 {b.get('bet_label', '—')} @ {b.get('odds', 0):.2f}\n\n")
                        if no_live:
                            msg += f"\n⏳ Ожидают: <b>{len(no_live)}</b>\n"
                        send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/force_settle':
                send_telegram("🔧 Принудительное обновление...")
                try:
                    res = update_pending_bets()
                    x2 = update_x2_results()
                    settled = autobet_manager.settle_pending()
                    clv = autobet_manager.compute_clv_for_settled()
                    send_telegram(f"✅ <b>ГОТОВО</b>\n\n"
                                  f"📜 История: FT={res.get('ft', 0)}, LIVE={res.get('live', 0)}\n"
                                  f"🎯 X2 закрыто: <b>{x2}</b>\n"
                                  f"💸 Автоставки: <b>{settled}</b>\n"
                                  f"📊 CLV: <b>{clv}</b>")
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/debug_pending':
                try:
                    bets = storage.autobet_load_all()
                    pending = [b for b in bets if b.get('result') == 'pending']
                    if not pending:
                        send_telegram("📭 Нет pending")
                    else:
                        msg = f"🔍 <b>DEBUG ({len(pending)})</b>\n\n"
                        for b in pending[:10]:
                            fid = b.get('fixture_id')
                            if fid:
                                md = football_api.get_match_result(fid)
                                if md:
                                    goals = md.get('goals', {})
                                    status = md.get('status', '?')
                                    is_final = ('✅FT' if md.get('is_final') else ('⚽' if md.get('is_live') else '⏳'))
                                    msg += f"<b>{b.get('home')} vs {b.get('away')}</b>\n  {is_final} {status} | {goals.get('home')}-{goals.get('away')}\n\n"
                        send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/snapshots':
                try:
                    stats = storage.get_odds_history_size()
                    x2_count = storage.x2_count()
                    send_telegram(f"📸 <b>СНИМКИ</b>\n\n"
                                  f"🎯 Матчей: <b>{stats['matches']}</b>\n"
                                  f"📊 Снимков: <b>{stats['snapshots']}</b>\n"
                                  f"💾 Размер: <b>{stats['size_kb']} КБ</b>\n"
                                  f"🎯 X2-кандидатов: <b>{x2_count}</b>")
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/snapshot':
                send_telegram("📸 Делаю снимки...")
                try:
                    n = snapshot_odds_for_upcoming()
                    send_telegram(f"✅ Создано: <b>{n}</b>" if n > 0 else "📭 Нечего снимать")
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/export':
                file, message = export_to_excel()
                send_telegram(message)
                if file:
                    try:
                        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                        requests.post(url,
                            files={'document': ('history.xlsx', file,
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                            data={'chat_id': Config.ADMIN_CHAT_ID, 'caption': '📊 История'},
                            timeout=30)
                    except Exception as e:
                        logger.error(f"Ошибка отправки: {e}")

            elif text == '/backup':
                send_telegram("💾 Создаю бэкап...")
                result = send_auto_backup()
                send_telegram("✅ Отправлен!" if result else "❌ Ошибка")

            elif text == '/autobet':
                autobet_manager.enabled = not autobet_manager.enabled
                status = "включены" if autobet_manager.enabled else "выключены"
                send_telegram(f"💸 Автоставки {status}")

            elif text == '/autobet_state':
                st = autobet_manager.get_state()
                live_count = st.get('live_count', 0)
                msg = (f"💸 <b>АВТОСТАВКИ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"💰 Банк: <b>${st['bank']:.2f}</b>\n"
                       f"📈 Прибыль: <b>${st['total_profit']:+.2f}</b>\n"
                       f"💎 ROI: <b>{st['roi']}%</b> • 🎯 Winrate: <b>{st['winrate']}%</b>\n"
                       f"🎲 Ставок: {st['total_bets']} (✅ {st['wins']} / ❌ {st['losses']})\n"
                       f"⏳ Pending: {st['pending']}")
                if live_count > 0:
                    msg += f" (⚽ <b>{live_count} live</b>)"
                msg += "\n"
                if st.get('clv_count', 0) > 0:
                    msg += f"📊 CLV: <b>{st.get('avg_clv', 0):+.2f}%</b> ({st.get('clv_count', 0)} шт.)\n"
                send_telegram(msg)

            elif text == '/clv':
                updated = autobet_manager.compute_clv_for_settled()
                st = autobet_manager.get_state()
                send_telegram(f"📊 <b>CLV</b>\n\nОбновлено: {updated}\n"
                              f"Средний CLV: <b>{st.get('avg_clv', 0):+.2f}%</b>\n"
                              f"Замеров: {st.get('clv_count', 0)}")

            elif text == '/grid_search':
                send_telegram("🎯 Запускаю Grid Search...")

                def run_grid():
                    try:
                        result = strategy_simulator.grid_search(max_combinations=200, min_bets=5)
                        if not result['top']:
                            send_telegram("❌ Не удалось найти стратегию")
                    except Exception as e:
                        send_telegram(f"❌ Ошибка: {e}")

                Thread(target=run_grid, daemon=True).start()

            elif text == '/status':
                report = bot_state.get_status_report()
                try:
                    oh_size = storage.get_odds_history_size()
                    x2_count = storage.x2_count()
                    report += (f"\n📊 Снимки: {oh_size['matches']} матчей, "
                               f"{oh_size['snapshots']} снимков, {oh_size['size_kb']} КБ")
                    report += f"\n🎯 X2-кандидатов: {x2_count}"
                    report += f"\n🌍 Geocoding: {len(_geo_cache)} городов"
                    report += f"\n📁 DATA: {DATA_DIR}"
                except Exception:
                    pass
                send_telegram(report)

            else:
                send_telegram("❌ Неизвестная команда. /help")
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook: {e}")
        send_error_to_telegram(f"Webhook error: {e}")
        return "ok", 200


# ============================================================
# PWA
# ============================================================
@app.route('/sw.js')
def serve_sw():
    try:
        return send_from_directory('.', 'sw.js', mimetype='application/javascript')
    except Exception:
        return "Service Worker не найден", 404


@app.route('/manifest.json')
def serve_manifest():
    try:
        return send_from_directory('.', 'manifest.json', mimetype='application/json')
    except Exception:
        return "Манифест не найден", 404


# ============================================================
# ★ API: LIVE — активные матчи + sparkline
# ============================================================
@app.route('/api/live', methods=['GET'])
def api_live():
    """Активные матчи (идущие + ближайшие 2 часа) с live-счётом
    и sparkline (мини-график движения кэфа)."""
    try:
        now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
        today_str = now_msk.strftime('%Y-%m-%d')

        with cache_lock:
            cache = storage.load_cache()
        all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
        if not all_matches:
            return jsonify({'status': 'ok', 'count': 0, 'matches': [],
                            'now': now_msk.strftime('%H:%M')})

        hours_before = getattr(Config, 'LIVE_HOURS_BEFORE', 2)
        minutes_after = getattr(Config, 'LIVE_MINUTES_AFTER', 120)
        max_matches = getattr(Config, 'LIVE_MAX_MATCHES', 30)

        in_window = []
        seen_fids = set()
        for m in all_matches:
            fid = m.get('fixture_id')
            if not fid or fid in seen_fids:
                continue
            mt_str = m.get('match_time', '')
            if not mt_str or mt_str == '?':
                continue
            try:
                match_dt = datetime.strptime(mt_str, "%d.%m.%Y %H:%M")
            except ValueError:
                continue
            delta_min = (match_dt - now_msk).total_seconds() / 60
            if -minutes_after <= delta_min <= hours_before * 60:
                in_window.append((m, match_dt, delta_min))
                seen_fids.add(fid)

        if not in_window:
            return jsonify({'status': 'ok', 'count': 0, 'matches': [],
                            'now': now_msk.strftime('%H:%M'),
                            'window': f"-{minutes_after}м .. +{hours_before}ч"})

        in_window.sort(key=lambda x: x[2])
        in_window = in_window[:max_matches]

        # Batch-запрос к API: 1 запрос на все матчи дня
        live_data = {}
        if getattr(Config, 'LIVE_BATCH_ENABLED', True):
            try:
                batch = football_api._make_request('/fixtures', {
                    'date': today_str,
                    'timezone': 'Europe/Moscow'
                })
                if batch and batch.get('response'):
                    for f in batch['response']:
                        fid = f.get('fixture', {}).get('id')
                        if fid:
                            live_data[fid] = f
                    logger.info(f"📡 Live batch: {len(live_data)} матчей на {today_str}")
            except Exception as e:
                logger.error(f"Live batch error: {e}")

        # ★ Batch sparkline
        sparkline_data = {}
        if getattr(Config, 'LIVE_SPARKLINE_ENABLED', True):
            try:
                all_fids = [m.get('fixture_id') for m, _, _ in in_window if m.get('fixture_id')]
                if all_fids:
                    sparkline_data = storage.get_odds_history_batch(
                        fixture_ids=all_fids,
                        market=getattr(Config, 'LIVE_SPARKLINE_MARKET', '1X2'),
                        selection=getattr(Config, 'LIVE_SPARKLINE_SELECTION', '1'),
                        limit=getattr(Config, 'LIVE_SPARKLINE_POINTS', 10),
                    )
                    logger.info(f"📈 Sparkline: {len(sparkline_data)} матчей")
            except Exception as e:
                logger.error(f"Sparkline batch error: {e}")

        # Формируем ответ
        result = []
        for m, match_dt, delta_min in in_window:
            fid = m.get('fixture_id')

            best_bet = m.get('best_bet', {})
            bet_label = best_bet.get('label', '—')
            bet_odds = best_bet.get('odds', 0)
            bet_ev = best_bet.get('ev', 0)
            bet_prob = best_bet.get('prob', 0)

            live_status = None
            live_minute = 0
            live_score = None
            live_halftime = None
            is_live = False
            is_final = False
            status_short = 'NS'

            if fid and fid in live_data:
                f = live_data[fid]
                status = f.get('fixture', {}).get('status', {})
                goals = f.get('goals', {})
                score = f.get('score', {})
                status_short = status.get('short', 'NS')
                live_minute = status.get('elapsed', 0) or 0

                ht = score.get('halftime', {}) or {}
                if ht.get('home') is not None and ht.get('away') is not None:
                    live_halftime = f"{ht['home']}-{ht['away']}"

                if status_short in FINAL_STATUSES:
                    is_final = True
                    hg = goals.get('home')
                    ag = goals.get('away')
                    if hg is not None and ag is not None:
                        live_score = f"{hg}:{ag}"
                elif status_short in LIVE_STATUSES:
                    is_live = True
                    hg = goals.get('home')
                    ag = goals.get('away')
                    if hg is not None and ag is not None:
                        live_score = f"{hg}:{ag}"

            odds_trend = 0
            try:
                if fid and bet_label:
                    bt_lower = bet_label.lower()
                    if 'x2' in bt_lower:
                        dc_hist = storage.get_odds_history(fid, 'DC', 'X2')
                    elif '1x' in bt_lower:
                        dc_hist = storage.get_odds_history(fid, 'DC', '1X')
                    else:
                        dc_hist = []
                    if dc_hist and len(dc_hist) >= 2:
                        f0 = float(dc_hist[0].get('odds', 0))
                        f1 = float(dc_hist[-1].get('odds', 0))
                        if f0 > 0:
                            odds_trend = round(((f1 / f0) - 1) * 100, 1)
            except Exception:
                pass

            sparkline_points = []
            raw_spark = sparkline_data.get(fid, [])
            if raw_spark:
                sparkline_points = [
                    {'odds': p.get('odds', 0), 'ts': p.get('ts', '')}
                    for p in raw_spark
                ]

            result.append({
                'fixture_id': fid,
                'home': m.get('home', '?'),
                'away': m.get('away', '?'),
                'league': m.get('league', '?'),
                'country': m.get('country', ''),
                'country_flag': m.get('country_flag', ''),
                'match_time': m.get('match_time', ''),
                'match_time_iso': match_dt.isoformat(),
                'minutes_to_match': int(delta_min),
                'is_live': is_live,
                'is_final': is_final,
                'status': status_short,
                'minute': live_minute,
                'score': live_score,
                'halftime': live_halftime,
                'best_bet': {
                    'label': bet_label,
                    'odds': bet_odds,
                    'ev': bet_ev,
                    'prob': bet_prob,
                },
                'odds_trend': odds_trend,
                'sparkline': sparkline_points,
                'source': m.get('source', '70_percent'),
                'total_xg': m.get('total_xg', 0),
            })

        logger.info(f"⚡ Live: {len(result)} матчей в окне")
        return jsonify({
            'status': 'ok',
            'count': len(result),
            'now': now_msk.strftime('%H:%M'),
            'window': f"-{minutes_after}м .. +{hours_before}ч",
            'matches': result,
        })
    except Exception as e:
        logger.exception(f"api_live error: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'matches': []}), 500


# ============================================================
# API: X2 — АВТОМАТИЧЕСКИЕ КАНДИДАТЫ
# ============================================================
@app.route('/api/x2_auto', methods=['GET'])
def api_x2_auto():
    try:
        candidates = storage.get_x2_candidates(limit=100)
        if not candidates:
            return jsonify({'status': 'ok', 'count': 0, 'candidates': []})

        enriched = []
        for c in candidates:
            fid = c.get('fixture_id')
            league_id = None
            for lid, lname in Config.LEAGUE_NAMES.items():
                if lname == c.get('league'):
                    league_id = lid
                    break

            country_name, country_flag = ("", "")
            if league_id:
                country_name, country_flag = Config.LEAGUE_COUNTRY.get(
                    league_id, ("", "")
                )

            current_odds = float(c.get('entry_odds', 0) or 0)
            current_1x_odds = float(c.get('entry_1x_odds', 0) or 0)
            odds_trend = 0
            try:
                if fid:
                    md = football_api.get_match_result(fid)
                    if md and not md.get('is_final') and not md.get('is_live'):
                        odds_data = football_api.get_match_odds(fid)
                        if odds_data:
                            fresh_x2 = odds_data.get('x2_odds', 0) or 0
                            fresh_1x = odds_data.get('1x_odds', 0) or 0
                            if fresh_x2 > 0:
                                current_odds = fresh_x2
                            if fresh_1x > 0:
                                current_1x_odds = fresh_1x

                    if c.get('x2_side') == 'X2':
                        dc_hist = storage.get_odds_history(fid, 'DC', 'X2')
                    else:
                        dc_hist = storage.get_odds_history(fid, 'DC', '1X')

                    if dc_hist and len(dc_hist) >= 2:
                        first_odd = float(dc_hist[0].get('odds', 0))
                        last_odd = float(dc_hist[-1].get('odds', 0))
                        if first_odd > 0:
                            odds_trend = round(((last_odd / first_odd) - 1) * 100, 1)
                        if current_odds <= 0 and first_odd > 0:
                            current_odds = first_odd
            except Exception as e:
                logger.debug(f"x2_auto enrich {fid}: {e}")

            if current_odds <= 0 and c.get('x2_prob', 0) > 0:
                p = c.get('x2_prob', 0) / 100
                if p > 0:
                    current_odds = round((1 / p) * 0.95, 2)

            enriched.append({
                'id': c.get('id'),
                'home': c.get('home'),
                'away': c.get('away'),
                'match': f"{c.get('home')} vs {c.get('away')}",
                'favorite': c.get('favorite'),
                'underdog': c.get('underdog'),
                'league': c.get('league'),
                'country': country_name,
                'country_flag': country_flag,
                'match_time': c.get('match_time'),
                'fixture_id': fid,
                'x2_side': c.get('x2_side', 'X2'),
                'x2_ev': c.get('x2_ev', 0),
                'x2_prob': c.get('x2_prob', 0),
                'home_position': c.get('home_position'),
                'away_position': c.get('away_position'),
                'home_form': c.get('home_form'),
                'away_form': c.get('away_form'),
                'total_xg': c.get('total_xg'),
                'entry_odds': c.get('entry_odds', 0),
                'entry_1x_odds': c.get('entry_1x_odds', 0),
                'current_odds': current_odds,
                'current_1x_odds': current_1x_odds,
                'odds_trend': odds_trend,
                'result': c.get('result', 'pending'),
                'profit': c.get('profit', 0),
                'home_goals': c.get('home_goals'),
                'away_goals': c.get('away_goals'),
                'settled_at': c.get('settled_at'),
                'created_at': c.get('created_at'),
                'source': 'auto',
            })

        return jsonify({
            'status': 'ok',
            'count': len(enriched),
            'candidates': enriched,
        })
    except Exception as e:
        logger.exception(f"api_x2_auto error: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'candidates': []}), 500


# ============================================================
# API: X2 — старые endpoints
# ============================================================
@app.route('/api/x2_candidates', methods=['GET'])
def api_x2_candidates():
    try:
        candidates = storage.get_x2_candidates(limit=500)
        return jsonify({'status': 'ok', 'count': len(candidates), 'candidates': candidates})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e), 'candidates': []}), 500


@app.route('/api/x2_candidates/clear', methods=['POST'])
def api_x2_candidates_clear():
    try:
        ok = storage.clear_x2_candidates()
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/x2_data', methods=['GET'])
def api_x2_data_get():
    try:
        data = []
        if os.path.exists(X2_FILE):
            with open(X2_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        return jsonify({'status': 'ok', 'data': data or []})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/x2_data', methods=['POST'])
def api_x2_data_post():
    try:
        data = request.json
        if not data or 'data' not in data:
            return jsonify({'error': 'No data'}), 400
        try:
            os.makedirs(os.path.dirname(X2_FILE) or '.', exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(X2_FILE) or '.', suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data['data'], f, indent=2, ensure_ascii=False)
            os.replace(tmp, X2_FILE)
            ok = True
        except Exception:
            ok = False
        return jsonify({'status': 'ok' if ok else 'error', 'count': len(data['data'])})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: АВТОСТАВКИ
# ============================================================
@app.route('/api/autobets/state', methods=['GET'])
def api_autobets_state():
    try:
        return jsonify(autobet_manager.get_state())
    except Exception as e:
        return jsonify({'bank': 1000, 'start_bank': 1000, 'total_profit': 0,
                        'total_bets': 0, 'wins': 0, 'losses': 0, 'pending': 0,
                        'live_count': 0, 'roi': 0, 'winrate': 0, 'stake_pct': 2,
                        'avg_clv': 0, 'clv_count': 0}), 200


@app.route('/api/autobets/history', methods=['GET'])
def api_autobets_history():
    try:
        limit = int(request.args.get('limit', 100))
        return jsonify(storage.autobet_get_history(limit))
    except Exception as e:
        return jsonify([])


@app.route('/api/autobets/place', methods=['POST'])
def api_autobets_place():
    try:
        placed = autobet_manager.place_bets_from_cache()
        return jsonify({'status': 'ok', 'placed': placed})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/settle', methods=['POST'])
def api_autobets_settle():
    try:
        updated = autobet_manager.settle_pending()
        return jsonify({'status': 'ok', 'updated': updated})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/live', methods=['POST'])
def api_autobets_live():
    try:
        updated = autobet_manager.update_live_scores()
        return jsonify({'status': 'ok', 'updated': updated})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/reset', methods=['POST'])
def api_autobets_reset():
    try:
        ok = autobet_manager.reset()
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/clv/compute', methods=['POST'])
def api_autobets_clv_compute():
    try:
        updated = autobet_manager.compute_clv_for_settled()
        return jsonify({'status': 'ok', 'updated': updated})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/autobets/clv/stats', methods=['GET'])
def api_autobets_clv_stats():
    try:
        bets = storage.autobet_load_all()
        clv_values = [b['clv'] for b in bets if b.get('clv') is not None]
        if not clv_values:
            return jsonify({'status': 'ok', 'count': 0, 'avg_clv': 0,
                            'positive_count': 0, 'negative_count': 0, 'positive_rate': 0})
        positive = [c for c in clv_values if c > 0]
        negative = [c for c in clv_values if c < 0]
        return jsonify({
            'status': 'ok', 'count': len(clv_values),
            'avg_clv': round(sum(clv_values) / len(clv_values), 2),
            'positive_count': len(positive),
            'negative_count': len(negative),
            'positive_rate': round(len(positive) / len(clv_values) * 100, 1),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: СИМУЛЯТОР
# ============================================================
@app.route('/api/simulator/run', methods=['POST'])
def api_simulator_run():
    try:
        params = request.json or {}
        result = strategy_simulator.simulate(params)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/save', methods=['POST'])
def api_simulator_save():
    try:
        data = request.json or {}
        name = data.get('name', 'Без названия')
        result = data.get('result', {})
        params = data.get('result', {}).get('params', {})
        if not result:
            return jsonify({'error': 'No result'}), 400
        ok = storage.save_simulation(name, params, result)
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/simulator/presets', methods=['GET'])
def api_simulator_presets():
    presets = {
        'conservative': {'name': '🛡️ Осторожная', 'params': {
            'min_ev': 15, 'max_ev': 100, 'min_prob': 60, 'max_prob': 100,
            'min_odds': 1.5, 'max_odds': 3.5, 'min_xg': 1.5, 'max_xg': 3.0,
            'bet_types': ['under', '1x', 'x2'], 'leagues': [],
            'stake_pct': 1.5, 'start_bank': 1000}},
        'balanced': {'name': '⚖️ Сбалансированная', 'params': {
            'min_ev': 10, 'max_ev': 100, 'min_prob': 52, 'max_prob': 100,
            'min_odds': 1.4, 'max_odds': 5.0, 'min_xg': 1.2, 'max_xg': 3.5,
            'bet_types': [], 'leagues': [], 'stake_pct': 2.0, 'start_bank': 1000}},
        'aggressive': {'name': '🔥 Агрессивная', 'params': {
            'min_ev': 5, 'max_ev': 200, 'min_prob': 45, 'max_prob': 100,
            'min_odds': 1.4, 'max_odds': 8.0, 'min_xg': 0.8, 'max_xg': 4.0,
            'bet_types': [], 'leagues': [], 'stake_pct': 3.0, 'start_bank': 1000}},
        'value_only': {'name': '💎 Только VALUE', 'params': {
            'min_ev': 50, 'max_ev': 500, 'min_prob': 60, 'max_prob': 100,
            'min_odds': 2.5, 'max_odds': 6.0, 'min_xg': 1.0, 'max_xg': 3.5,
            'bet_types': ['1X', 'X2', 'П1', 'П2'], 'leagues': [],
            'stake_pct': 2.0, 'start_bank': 1000}},
    }
    return jsonify(presets)


@app.route('/api/simulator/grid_search', methods=['POST'])
def api_simulator_grid_search():
    try:
        data = request.json or {}
        max_combinations = int(data.get('max_combinations', 200))
        min_bets = int(data.get('min_bets', 5))
        result = strategy_simulator.grid_search(max_combinations=max_combinations, min_bets=min_bets)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: ОСНОВНЫЕ
# ============================================================
@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = storage.load_stats()
    bank = storage.load_bank()
    return jsonify({'bank': bank, **stats})


@app.route('/api/history', methods=['GET'])
def api_history():
    return jsonify(storage.load_history())


@app.route('/api/matches', methods=['GET'])
def api_matches():
    cache = storage.load_cache()
    return jsonify(cache.get('top_matches', []))


@app.route('/api/all_data', methods=['GET'])
def all_data():
    try:
        stats = storage.load_stats()
        bank = storage.load_bank()
        history = storage.load_history()
        cache = storage.load_cache()
        profit_data = get_profit_data(history)
        return jsonify({
            'stats': {'bank': bank, 'total_bets': stats.get('total', 0),
                      'wins': stats.get('wins', 0), 'losses': stats.get('losses', 0),
                      'profit': stats.get('total_profit', 0),
                      'winrate': stats.get('winrate', 0),
                      'roi': stats.get('roi', 0), 'avg_stake': stats.get('avg_stake', 0)},
            'history': history, 'profit_data': profit_data,
            'matches': cache.get('top_matches', [])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        if 'bank' in data:
            storage.save_bank(data['bank'])
            return jsonify({'success': True, 'bank': data['bank']})
        return jsonify({'error': 'No bank value'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keepalive', methods=['GET'])
def keepalive():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


@app.route('/api/matches_log', methods=['GET'])
def api_matches_log():
    try:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return jsonify({'log': content[-100000:], 'status': 'ok', 'size': len(content)})
        return jsonify({'log': '', 'status': 'empty'})
    except Exception as e:
        return jsonify({'log': '', 'error': str(e)}), 500


@app.route('/api/snapshot', methods=['GET'])
def api_snapshot():
    try:
        n = snapshot_odds_for_upcoming()
        return jsonify({'status': 'ok', 'snapshots': n})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# ★ API: СНИМКИ — список (v4.3 — без fallback'ов)
# ============================================================
@app.route('/api/snapshots', methods=['GET'])
def api_snapshots_list():
    try:
        days = int(request.args.get('days', 7))
        only_anomaly = request.args.get('only_anomaly', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 50))
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        matches_raw = storage.get_snapshots_since(cutoff)

        grouped = {}
        for row in matches_raw:
            fid = row.get('fixture_id')
            if not fid: continue
            if fid not in grouped:
                grouped[fid] = {
                    'fixture_id': fid,
                    'snapshots': [],
                    'home': row.get('home', ''),
                    'away': row.get('away', ''),
                    'league': row.get('league', ''),
                    'first_time': None,
                    'last_time': None,
                }
            grouped[fid]['snapshots'].append(row)
            # Берём названия из самой свежей записи, где они не пустые
            if row.get('home') and not grouped[fid]['home']:
                grouped[fid]['home'] = row['home']
            if row.get('away') and not grouped[fid]['away']:
                grouped[fid]['away'] = row['away']
            if row.get('league') and not grouped[fid]['league']:
                grouped[fid]['league'] = row['league']

            t = row.get('created_at')
            if t:
                if not grouped[fid]['first_time'] or t < grouped[fid]['first_time']:
                    grouped[fid]['first_time'] = t
                if not grouped[fid]['last_time'] or t > grouped[fid]['last_time']:
                    grouped[fid]['last_time'] = t

        # Подтягиваем match_time из кэша (match_time не хранится в snapshots)
        cache = storage.load_cache()
        all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
        match_time_lookup = {}
        for m in all_matches:
            fid = m.get('fixture_id')
            if fid and fid not in match_time_lookup:
                match_time_lookup[fid] = m.get('match_time', '?')

        result = []
        for fid, info in grouped.items():
            snaps = info['snapshots']
            if not snaps: continue

            first_odds = {'1': 0, 'X': 0, '2': 0, '1X': 0, 'X2': 0}
            last_odds = {'1': 0, 'X': 0, '2': 0, '1X': 0, 'X2': 0}
            anomalies = []

            for s in snaps:
                sel = s.get('selection', '')
                odd = s.get('odds', 0)
                if sel in first_odds:
                    if not first_odds[sel]: first_odds[sel] = odd
                    last_odds[sel] = odd

            for sel in ['1', 'X', '2', '1X', 'X2']:
                if first_odds[sel] > 0 and last_odds[sel] > 0:
                    trend = ((last_odds[sel] / first_odds[sel]) - 1) * 100
                    if abs(trend) > 5:
                        anomalies.append({
                            'selection': sel, 'first': first_odds[sel],
                            'last': last_odds[sel], 'trend': round(trend, 1)
                        })
            if only_anomaly and not anomalies:
                continue

            result.append({
                'fixture_id': fid,
                'home': info['home'] or '?',
                'away': info['away'] or '?',
                'league': info['league'] or '?',
                'match_time': match_time_lookup.get(fid, '?'),
                'snapshot_count': len(snaps),
                'first_time': info['first_time'],
                'last_time': info['last_time'],
                'first': first_odds,
                'last': last_odds,
                'anomalies': anomalies,
            })

        result.sort(key=lambda x: x.get('last_time', ''), reverse=True)
        result = result[:limit]
        return jsonify({
            'status': 'ok', 'count': len(result), 'days': days,
            'only_anomaly': only_anomaly, 'matches': result,
        })
    except Exception as e:
        logger.exception(f"api_snapshots_list error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ API: СНИМКИ — детали (v4.3 — без fallback'ов)
# ============================================================
@app.route('/api/snapshots/<int:fixture_id>', methods=['GET'])
def api_snapshots_detail(fixture_id):
    try:
        rows = storage.get_snapshots_by_fixture(fixture_id)
        if not rows:
            return jsonify({'status': 'ok', 'fixture_id': fixture_id, 'history': []})

        # ★ Названия берём напрямую из БД — не нужен fallback на cache/history
        m_info = storage.get_snapshot_match_info(fixture_id) or {}
        # match_time — из кэша (в snapshots не хранится)
        match_time = '?'
        try:
            cache = storage.load_cache()
            all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
            for m in all_matches:
                if m.get('fixture_id') == fixture_id:
                    match_time = m.get('match_time', '?')
                    break
        except Exception:
            pass

        history_map = {}
        for r in rows:
            t = r.get('created_at')
            sel = r.get('selection', '')
            odd = r.get('odds', 0)
            bm = r.get('bookmaker', '—')
            if not t: continue
            if t not in history_map:
                history_map[t] = {
                    'created_at': t,
                    'odds': {'1': 0, 'X': 0, '2': 0, '1X': 0, 'X2': 0},
                    'bookmaker': bm,
                }
            if sel in history_map[t]['odds']:
                history_map[t]['odds'][sel] = odd
            history_map[t]['bookmaker'] = bm

        history = sorted(history_map.values(), key=lambda x: x['created_at'])
        return jsonify({
            'status': 'ok',
            'fixture_id': fixture_id,
            'match': {
                'home': m_info.get('home', '?'),
                'away': m_info.get('away', '?'),
                'league': m_info.get('league', '?'),
                'match_time': match_time,
            },
            'history': history,
        })
    except Exception as e:
        logger.exception(f"api_snapshots_detail error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ API: АНОМАЛИИ (v4.3 — без fallback'ов)
# ============================================================
@app.route('/api/snapshot_anomalies', methods=['GET'])
def api_snapshot_anomalies():
    try:
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        matches_raw = storage.get_snapshots_since(cutoff)

        grouped = {}
        for row in matches_raw:
            fid = row.get('fixture_id')
            if not fid: continue
            if fid not in grouped:
                grouped[fid] = {
                    'snapshots': [],
                    'home': row.get('home', '') or '?',
                    'away': row.get('away', '') or '?',
                    'league': row.get('league', '') or '?',
                }
            grouped[fid]['snapshots'].append(row)
            if row.get('home') and grouped[fid]['home'] == '?':
                grouped[fid]['home'] = row['home']
            if row.get('away') and grouped[fid]['away'] == '?':
                grouped[fid]['away'] = row['away']
            if row.get('league') and grouped[fid]['league'] == '?':
                grouped[fid]['league'] = row['league']

        # match_time — из кэша
        match_time_lookup = {}
        try:
            cache = storage.load_cache()
            all_matches = cache.get('all_analyzed', []) + cache.get('top_matches', [])
            for m in all_matches:
                fid = m.get('fixture_id')
                if fid and fid not in match_time_lookup:
                    match_time_lookup[fid] = m.get('match_time', '?')
        except Exception:
            pass

        result = []
        for fid, info in grouped.items():
            snaps = info['snapshots']
            odds_by_time = {}
            for s in snaps:
                t = s.get('created_at')
                sel = s.get('selection')
                odd = s.get('odds', 0)
                if not t or sel not in ['1', 'X', '2']: continue
                odds_by_time.setdefault(t, {'1': 0, 'X': 0, '2': 0})[sel] = odd

            sorted_times = sorted(odds_by_time.keys())
            for sel in ['1', 'X', '2']:
                values = [odds_by_time[t][sel] for t in sorted_times if odds_by_time[t][sel] > 0]
                if len(values) < 2: continue
                first_odd = values[0]
                max_odd = max(values)
                anomaly_pct = ((max_odd / first_odd) - 1) * 100 if first_odd > 0 else 0
                if anomaly_pct > 5:
                    result.append({
                        'fixture_id': fid,
                        'home': info['home'],
                        'away': info['away'],
                        'league': info['league'],
                        'match_time': match_time_lookup.get(fid, '?'),
                        'selection': sel,
                        'first_odds': first_odd,
                        'max_odds': max_odd,
                        'anomaly_pct': round(anomaly_pct, 1),
                        'snapshots_count': len(values),
                    })
        result.sort(key=lambda x: x['anomaly_pct'], reverse=True)
        result = result[:limit]
        return jsonify({'status': 'ok', 'count': len(result), 'anomalies': result})
    except Exception as e:
        logger.exception(f"api_snapshot_anomalies error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ★ API: СТАТИСТИКА АНОМАЛИЙ (v4.3 — без fallback'ов)
# ============================================================
@app.route('/api/snapshot_anomalies/stats', methods=['GET'])
def api_snapshot_anomalies_stats():
    """Статистика аномалий: сколько сбылось / не сбылось."""
    try:
        days = int(request.args.get('days', 7))
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        matches_raw = storage.get_snapshots_since(cutoff)

        grouped = {}
        for row in matches_raw:
            fid = row.get('fixture_id')
            if not fid: continue
            if fid not in grouped:
                grouped[fid] = {
                    'snapshots': [],
                    'home': row.get('home', '') or '?',
                    'away': row.get('away', '') or '?',
                    'league': row.get('league', '') or '?',
                }
            grouped[fid]['snapshots'].append(row)
            if row.get('home') and grouped[fid]['home'] == '?':
                grouped[fid]['home'] = row['home']
            if row.get('away') and grouped[fid]['away'] == '?':
                grouped[fid]['away'] = row['away']
            if row.get('league') and grouped[fid]['league'] == '?':
                grouped[fid]['league'] = row['league']

        # Результаты матчей — из истории (home_goals/away_goals)
        history = storage.load_history()
        results_lookup = {}
        for h in history:
            fid = h.get('fixture_id')
            if fid:
                results_lookup[fid] = {
                    'result': h.get('result'),
                    'home_goals': h.get('home_goals'),
                    'away_goals': h.get('away_goals'),
                }

        total_matches = len(grouped)
        total_snapshots = len(matches_raw)
        total_anomalies = 0
        correct_anomalies = 0
        wrong_anomalies = 0
        unknown_anomalies = 0
        sum_growth = 0

        top_good = []
        top_bad = []

        for fid, info in grouped.items():
            snaps = info['snapshots']
            odds_by_time = {}
            for s in snaps:
                t = s.get('created_at')
                sel = s.get('selection')
                odd = s.get('odds', 0)
                if not t or sel not in ['1', 'X', '2']:
                    continue
                odds_by_time.setdefault(t, {'1': 0, 'X': 0, '2': 0})[sel] = odd

            sorted_times = sorted(odds_by_time.keys())

            for sel in ['1', 'X', '2']:
                values = [odds_by_time[t][sel] for t in sorted_times if odds_by_time[t][sel] > 0]
                if len(values) < 2:
                    continue
                first_odd = values[0]
                max_odd = max(values)
                anomaly_pct = ((max_odd / first_odd) - 1) * 100 if first_odd > 0 else 0

                if anomaly_pct < 5:
                    continue

                total_anomalies += 1
                sum_growth += anomaly_pct

                match_res = results_lookup.get(fid)
                is_correct = None
                if match_res and match_res.get('result') in ('win', 'loss'):
                    hg = match_res.get('home_goals')
                    ag = match_res.get('away_goals')
                    if hg is not None and ag is not None:
                        if sel == '1':
                            is_correct = hg > ag
                        elif sel == '2':
                            is_correct = ag > hg
                        elif sel == 'X':
                            is_correct = hg == ag

                if is_correct is True:
                    correct_anomalies += 1
                    top_good.append({
                        'fixture_id': fid, 'selection': sel,
                        'first_odds': first_odd, 'max_odds': max_odd,
                        'anomaly_pct': round(anomaly_pct, 1),
                        'home': info['home'], 'away': info['away'],
                        'league': info['league'],
                    })
                elif is_correct is False:
                    wrong_anomalies += 1
                    top_bad.append({
                        'fixture_id': fid, 'selection': sel,
                        'first_odds': first_odd, 'max_odds': max_odd,
                        'anomaly_pct': round(anomaly_pct, 1),
                        'home': info['home'], 'away': info['away'],
                        'league': info['league'],
                    })
                else:
                    unknown_anomalies += 1

        top_good_sorted = sorted(top_good, key=lambda x: x['anomaly_pct'], reverse=True)[:5]
        top_bad_sorted = sorted(top_bad, key=lambda x: x['anomaly_pct'])[:5]

        total_resolved = correct_anomalies + wrong_anomalies
        hit_rate = round(correct_anomalies / total_resolved * 100, 1) if total_resolved > 0 else 0
        avg_growth = round(sum_growth / total_anomalies, 1) if total_anomalies > 0 else 0

        return jsonify({
            'status': 'ok',
            'days': days,
            'total_matches': total_matches,
            'total_snapshots': total_snapshots,
            'total_anomalies': total_anomalies,
            'correct_anomalies': correct_anomalies,
            'wrong_anomalies': wrong_anomalies,
            'unknown_anomalies': unknown_anomalies,
            'hit_rate': hit_rate,
            'avg_growth': avg_growth,
            'top_good': top_good_sorted,
            'top_bad': top_bad_sorted,
        })
    except Exception as e:
        logger.exception(f"api_snapshot_anomalies_stats error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# API: РЕДАКТИРОВАНИЕ СТАВОК
# ============================================================
@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        if index is None or index >= len(history):
            return jsonify({'error': 'Не найдено'}), 404
        for field in ['home', 'away', 'bet', 'odds', 'stake', 'ev', 'prob',
                      'result', 'bookmaker', 'halftime_home', 'halftime_away',
                      'home_goals', 'away_goals', 'date', 'league', 'source']:
            if field in data:
                history[index][field] = data[field]
        if history[index].get('result') == 'win':
            history[index]['profit'] = round(history[index].get('stake', 0) * (history[index].get('odds', 1) - 1), 2)
        elif history[index].get('result') == 'loss':
            history[index]['profit'] = -history[index].get('stake', 0)
        else:
            history[index]['profit'] = 0
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        if index is None or index >= len(history):
            return jsonify({'error': 'Не найдено'}), 404
        history.pop(index)
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        match_name = data.get('match', '')
        score = data.get('score', '-')
        result = data.get('result', 'win')
        stake = float(data.get('stake', 0))
        bet_type = data.get('bet', '')
        odds = float(data.get('odds', 1.85))
        bookmaker = data.get('bookmaker', 'Ручное добавление')
        if not match_name:
            return jsonify({'error': 'Название обязательно'}), 400
        hg = ag = None
        if score and '-' in score:
            p = score.split('-')
            try:
                hg = int(p[0].strip()); ag = int(p[1].strip())
            except Exception:
                pass
        home = away = 'Unknown'
        if ' vs ' in match_name:
            p = match_name.split(' vs ')
            home, away = p[0].strip(), p[1].strip()
        elif ' - ' in match_name:
            p = match_name.split(' - ')
            home, away = p[0].strip(), p[1].strip()
        if result == 'win': profit = round(stake * (odds - 1), 2)
        elif result == 'loss': profit = -stake
        else: profit = 0
        history = storage.load_history()
        history.append({
            'home': home or 'Unknown',
            'away': away or 'Unknown',
            'league': 'Ручное добавление',
            'bet': bet_type, 'odds': odds, 'stake': stake,
            'ev': 0, 'prob': 0, 'result': result, 'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': hg, 'away_goals': ag,
            'manual': True, 'bookmaker': bookmaker,
            'source': 'manual',
        })
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True, 'count': 1})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    try:
        data = request.json
        os.makedirs(os.path.dirname(SETTINGS_PATH) or '.', exist_ok=True)
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        for key in ['EV_MIN_70', 'PROB_MIN_70', 'XG_MIN_70', 'XG_MAX_70',
                    'POSITION_MAX_70', 'PREMIUM_MIN_EV', 'STANDARD_MIN_EV',
                    'TM25_XG_MIN', 'TM25_XG_MAX', 'MAX_TM25_BETS',
                    'VALUE_MIN_ODDS', 'VALUE_MIN_EV', 'VALUE_MIN_PROB',
                    'VALUE_MIN_XG_DIFF', 'VALUE_MAX_RESULTS',
                    'X2_MIN_EV', 'X2_MIN_PROB',
                    'LIVE_HOURS_BEFORE', 'LIVE_MINUTES_AFTER',
                    'LIVE_REFRESH_SEC', 'LIVE_MAX_MATCHES',
                    'LIVE_SPARKLINE_ENABLED', 'LIVE_SPARKLINE_POINTS']:
            if key.lower() in data:
                setattr(Config, key, data[key.lower()])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        history = data.get('history', [])
        stats = data.get('stats', {})
        if not history:
            return jsonify({'error': 'Нет данных'}), 400
        current = storage.load_history()
        keys = {f"{b.get('date', '')}_{b.get('home', '')}_{b.get('away', '')}" for b in current}
        imported = 0
        for bet in history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            if key not in keys:
                current.append(bet); imported += 1; keys.add(key)
        if stats and 'bank' in stats:
            storage.save_bank(stats['bank'])
        storage.save_history(current)
        recalc_stats()
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/void_old', methods=['GET'])
def void_old_endpoint():
    bets = storage.autobet_load_all()
    now_msk = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    voided = 0
    for b in bets:
        if b.get('result') != 'pending': continue
        mt = b.get('match_time', '')
        if not mt or mt == '?': continue
        try:
            m = datetime.strptime(mt, '%d.%m.%Y %H:%M')
            hours = (now_msk - m).total_seconds() / 3600
            if hours > 6:
                b['result'] = 'void'
                b['profit'] = 0
                b['note'] = 'Voided (stale)'
                for k in ['live_score', 'live_status', 'live_minute', 'live_halftime']:
                    b.pop(k, None)
                voided += 1
        except Exception:
            pass
    storage.autobet_save_all(bets)
    return jsonify({'status': 'ok', 'voided': voided})


@app.route('/health', methods=['GET'])
def health():
    try:
        bank = storage.load_bank()
        history = storage.load_history()
        state = bot_state.state
        try:
            start_dt = datetime.fromisoformat(state.get('start_time', datetime.now().isoformat()))
            uptime_sec = (datetime.now() - start_dt).total_seconds()
            uptime_hours = round(uptime_sec / 3600, 2)
        except Exception:
            uptime_sec = 0; uptime_hours = 0
        try:
            autobets_state = storage.autobet_get_state(default_bank=1000.0)
        except Exception:
            autobets_state = {}
        try:
            odds_size = storage.get_odds_history_size()
        except Exception:
            odds_size = {'matches': 0, 'snapshots': 0}
        try:
            x2_count = storage.x2_count()
        except Exception:
            x2_count = 0
        return {
            'status': 'ok', 'time': datetime.now().isoformat(),
            'uptime_hours': uptime_hours, 'uptime_sec': int(uptime_sec),
            'bank': bank, 'total_bets': len(history),
            'search_running': state.get('search_running', False),
            'geocoding_cache_size': len(_geo_cache),
            'data_dir': DATA_DIR,
            'x2_candidates': x2_count,
            'autobets': {
                'count': autobets_state.get('total_bets', 0),
                'bank': autobets_state.get('bank', 1000),
                'profit': autobets_state.get('total_profit', 0),
                'roi': autobets_state.get('roi', 0),
                'winrate': autobets_state.get('winrate', 0),
                'pending': autobets_state.get('pending', 0),
                'live_count': autobets_state.get('live_count', 0),
                'avg_clv': autobets_state.get('avg_clv', 0),
                'clv_count': autobets_state.get('clv_count', 0),
            },
            'odds_history': {
                'matches': odds_size.get('matches', 0),
                'snapshots': odds_size.get('snapshots', 0),
            },
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}, 500


@app.route('/', methods=['GET'])
def index():
    try:
        return render_template('index.html')
    except Exception:
        return f"🤖 Quantum Bet Bot PRO | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def register_bot_commands():
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/setMyCommands"
        commands = [
            {"command": "update", "description": "🔍 Полный поиск (70%+ / ТМ 2.5 / 💎 VALUE)"},
            {"command": "today", "description": "🎯 ТОП-5 матчей"},
            {"command": "live", "description": "⚽ Активные live-матчи"},
            {"command": "snapshots", "description": "📸 Статистика снимков"},
            {"command": "snapshot", "description": "📸 Создать снимки"},
            {"command": "x2_info", "description": "🎯 X2-кандидаты"},
            {"command": "update_results", "description": "🔄 Обновить результаты"},
            {"command": "force_settle", "description": "🔧 Принудительное обновление"},
            {"command": "debug_pending", "description": "🔍 Диагностика pending"},
            {"command": "analyze", "description": "📊 Анализ матча"},
            {"command": "status", "description": "🤖 Статус бота"},
            {"command": "stop", "description": "🛑 Остановить поиск"},
            {"command": "reset_search", "description": "🔄 Сбросить поиск"},
            {"command": "bank", "description": "💰 Текущий банк"},
            {"command": "stats", "description": "📊 Общая статистика"},
            {"command": "report", "description": "📅 Отчёт за 7 дней"},
            {"command": "bettypes", "description": "🎲 По типам ставок"},
            {"command": "timestats", "description": "🕐 По времени"},
            {"command": "strategies", "description": "📈 Сравнение стратегий"},
            {"command": "team", "description": "🏟️ По команде"},
            {"command": "autobet", "description": "💸 Вкл/выкл автоставки"},
            {"command": "autobet_state", "description": "📊 Состояние автоставок"},
            {"command": "clv", "description": "📊 Средний CLV"},
            {"command": "grid_search", "description": "🎯 Автопоиск стратегии"},
            {"command": "result", "description": "✏️ Ручной результат"},
            {"command": "export", "description": "📥 Экспорт в Excel"},
            {"command": "backup", "description": "💾 Создать бэкап"},
            {"command": "help", "description": "ℹ️ Справка"},
        ]
        r = requests.post(url, json={"commands": commands}, timeout=10)
        if r.status_code == 200 and r.json().get('ok'):
            logger.info(f"✅ Команды зарегистрированы: {len(commands)}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ register_bot_commands: {e}")
        return False


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

    start_scheduler()
    schedule_updates()
    schedule_notifications()
    schedule_performance_report()
    schedule_auto_backup()
    schedule_autobet()

    try:
        register_bot_commands()
    except Exception as e:
        logger.error(f"⚠️ Команды: {e}")

    try:
        WEBHOOK_URL = (os.getenv('RENDER_EXTERNAL_URL', 'https://quantumbet-bot-pro.onrender.com') + '/webhook')
        r = requests.get(
            f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/setWebhook",
            params={'url': WEBHOOK_URL}, timeout=10
        )
        resp = r.json()
        if resp.get('ok'):
            logger.info(f"✅ Webhook: {WEBHOOK_URL}")
        else:
            logger.error(f"❌ Webhook error: {resp}")
    except Exception as e:
        logger.error(f"❌ Webhook: {e}")

    odds_scheduler = BackgroundScheduler()
    odds_scheduler.add_job(
        func=safe_job(snapshot_odds_for_upcoming, "snapshot_odds"),
        trigger='interval', minutes=30, id='odds_snapshot',
        replace_existing=True, max_instances=1,
        misfire_grace_time=60, coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(lambda: storage.cleanup_old_odds_history(days=30), "cleanup_odds"),
        trigger='cron', hour=4, minute=0, id='odds_cleanup',
        replace_existing=True, misfire_grace_time=1800, coalesce=True
    )
    odds_scheduler.add_job(
        func=safe_job(autobet_manager.update_live_scores, "autobet_live"),
        trigger='interval', minutes=10, id='autobet_live',
        replace_existing=True, max_instances=1,
        misfire_grace_time=60, coalesce=True
    )
    odds_scheduler.start()

    logger.info("=" * 60)
    logger.info("🚀 QUANTUM BET BOT PRO ЗАПУЩЕН (v4.3)")
    logger.info("=" * 60)
    logger.info(f"📊 Лиг: {len(Config.LEAGUES)} | Кубков: {len(Config.CUP_LEAGUES)}")
    logger.info(f"🧠 ENGINE: {Config.PREDICTION_ENGINE}")
    logger.info(f"💎 VALUE: кэф>={getattr(Config, 'VALUE_MIN_ODDS', 2.5)} | "
                f"EV>={getattr(Config, 'VALUE_MIN_EV', 50)}% | "
                f"Prob>={getattr(Config, 'VALUE_MIN_PROB', 60)}%")
    logger.info(f"⚡ LIVE: окно -{getattr(Config, 'LIVE_MINUTES_AFTER', 120)}м .. "
                f"+{getattr(Config, 'LIVE_HOURS_BEFORE', 2)}ч | "
                f"sparkline={getattr(Config, 'LIVE_SPARKLINE_ENABLED', True)}")
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
