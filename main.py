import sys
import os
import requests
import time
import json
import logging
import random
import math
import functools
from datetime import datetime, timedelta
from threading import Lock, Thread
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

# ============================================================
# ИМПОРТЫ ИЗ ПРОЕКТА
# ============================================================
from app.config import Config
from app.database.storage import storage
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler
from app.llm import llm_analyze_match
from app.odds_rotator import OddsKeyRotator

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
logger = get_logger(__name__)
app = Flask(__name__)

search_running = False
search_state = {}
TIMEZONE_OFFSET = 3

TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

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

# ============================================================
# МОНИТОРИНГ ПРОИЗВОДИТЕЛЬНОСТИ
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
# УМНОЕ КЭШИРОВАНИЕ
# ============================================================
class SmartCache:
    def __init__(self, max_size=500):
        self.cache = {}
        self.cache_timestamps = {}
        self.hit_count = {}
        self.last_access = {}
        self.max_size = max_size
        self.default_ttl = 3600
        self.ttl_by_type = {
            'form': 300, 'odds': 60, 'statistics': 300,
            'standings': 1800, 'matches': 3600, 'h2h': 7200
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


# ============================================================
# ОБРАБОТКА ОШИБОК И РЕТРАИ
# ============================================================
class APIError(Exception): pass
class APIErrorRetry(Exception): pass
class APIErrorFatal(Exception): pass


class APIRateLimiter:
    def __init__(self, max_requests=30, time_window=60):
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
                logger.warning(f"🔄 Попытка {attempt + 1}/{self.max_retries + 1} через {delay + jitter:.1f}с: {e}")
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
    """Отправка в ADMIN_CHAT_ID и, если задан, в CHANNEL_ID."""
    targets = [Config.ADMIN_CHAT_ID]
    if Config.CHANNEL_ID and str(Config.CHANNEL_ID) != str(Config.ADMIN_CHAT_ID):
        targets.append(Config.CHANNEL_ID)
    for chat_id in targets:
        try:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
            r = requests.post(url, json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }, timeout=10)
            if r.status_code != 200:
                logger.error(f"❌ Ошибка отправки в {chat_id}: {r.text}")
        except Exception as e:
            logger.error(f"❌ Send error → {chat_id}: {e}")


# ============================================================
# FOOTBALL API
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or Config.FOOTBALL_API_URL
        self.cache = SmartCache(max_size=500)
        self.last_request_time = 0
        self.min_request_interval = 0.2
        self.rate_limiter = APIRateLimiter(max_requests=250, time_window=60)
        self.retry_manager = RetryManager(max_retries=3, base_delay=1)
        self.error_stats = defaultdict(int)
        logger.info(f"🔑 API ключ: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")

    def _make_request(self, endpoint, params=None):
        try:
            self.rate_limiter.wait_if_needed()
            return self.retry_manager.retry(self._make_request_impl, endpoint, params)
        except APIErrorFatal as e:
            logger.error(f"❌ Фатальная ошибка API: {e}")
            self.error_stats['fatal'] += 1
            return None
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка: {e}")
            self.error_stats['unknown'] += 1
            return None

    def _make_request_impl(self, endpoint, params=None):
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval - (now - self.last_request_time))
        headers = {
            'x-apisports-key': self.api_key,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        url = f"{self.base_url}{endpoint}"
        try:
            r = requests.get(url, headers=headers, params=params, timeout=Config.REQUEST_TIMEOUT)
            self.last_request_time = time.time()
            if r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 60))
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
                if 'rate limit' in str(data['errors']).lower():
                    raise APIErrorRetry("Rate limit")
                if 'api key' in str(data['errors']).lower():
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
            'league': league_id,
            'season': Config.USE_SEASON,
            'date': date
        })
        if data and 'response' in data:
            self.cache.set(cache_key, data['response'])
            return data['response']
        return []

    @timing_decorator()
    def get_form(self, team_id):
        cache_key = f"form_{team_id}"
        cached = self.cache.get(cache_key, data_type='form')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/fixtures', {'team': team_id, 'last': 5, 'status': 'FT'})
            if data and 'response' in data:
                matches = data['response']
                if matches:
                    gs, gc = [], []
                    w = d = l = 0
                    for m in matches:
                        goals = m.get('goals', {})
                        teams = m.get('teams', {})
                        if teams.get('home', {}).get('id') == team_id:
                            s, c = goals.get('home', 0) or 0, goals.get('away', 0) or 0
                        else:
                            s, c = goals.get('away', 0) or 0, goals.get('home', 0) or 0
                        gs.append(s); gc.append(c)
                        if s > c: w += 1
                        elif s == c: d += 1
                        else: l += 1
                    result = {
                        'goals_avg': round(sum(gs) / len(gs), 2),
                        'conceded_avg': round(sum(gc) / len(gc), 2),
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
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            data = self._make_request('/fixtures', {'id': fixture_id})
            if data and 'response' in data:
                f = data['response'][0]
                result = {
                    'goals': {'home': f.get('goals', {}).get('home'),
                              'away': f.get('goals', {}).get('away')},
                    'status': f.get('status', {}).get('short', 'FT')
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
            data = self._make_request('/fixtures/odds', {'fixture': fixture_id})
            if data and 'response' in data:
                result = self._extract_best_odds(data['response'])
                if result.get('best_odds', 0) > 0:
                    self.cache.set(cache_key, result)
                    return result
        except Exception as e:
            logger.error(f"Ошибка кэфов {fixture_id}: {e}")
        return None

    def _extract_best_odds(self, odds_data):
        result = {'best_odds': 0, 'bookmaker': '—', 'home_odds': 0,
                  'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0}
        for bm in odds_data:
            bm_name = bm.get('bookmaker', {}).get('name', '—')
            for bet in bm.get('bets', []):
                bn = bet.get('name', '').lower()
                values = bet.get('values', [])
                if not values:
                    continue
                if 'match' in bn or 'побед' in bn:
                    for v in values:
                        vn = v.get('value', '').lower()
                        odd = v.get('odd', 0)
                        if odd <= 0:
                            continue
                        if 'home' in vn or vn == '1':
                            result['home_odds'] = max(result['home_odds'], odd)
                        elif 'away' in vn or vn == '2':
                            result['away_odds'] = max(result['away_odds'], odd)
                        elif 'draw' in vn or vn == 'x':
                            result['draw_odds'] = max(result['draw_odds'], odd)
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bm_name
                if 'total' in bn:
                    for v in values:
                        vn = v.get('value', '').lower()
                        odd = v.get('odd', 0)
                        if odd <= 0:
                            continue
                        if 'under' in vn:
                            result['under_odds'] = max(result['under_odds'], odd)
                        elif 'over' in vn:
                            result['over_odds'] = max(result['over_odds'], odd)
        return result

    def clear_cache(self):
        self.cache.clear()

    def find_fixture_by_teams(self, home_team, away_team):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            data = self._make_request('/fixtures', {'date': today, 'status': 'FT'})
            if data and 'response' in data:
                for f in data['response']:
                    t = f.get('teams', {})
                    h = t.get('home', {}).get('name', '')
                    a = t.get('away', {}).get('name', '')
                    if home_team.lower() in h.lower() and away_team.lower() in a.lower():
                        return f.get('fixture', {}).get('id')
        except Exception as e:
            logger.error(f"Ошибка поиска матча: {e}")
        return None


football_api = FootballAPI()


# ============================================================
# ODDS API С РОТАЦИЕЙ КЛЮЧЕЙ
# ============================================================
class OddsAPIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or Config.ODDS_API_KEY
        self.base_url = Config.ODDS_API_URL
        self.cache = SmartCache(max_size=200)
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self.rate_limiter = APIRateLimiter(max_requests=50, time_window=60)
        self.retry_manager = RetryManager(max_retries=2, base_delay=0.5)
        try:
            self.rotator = OddsKeyRotator()
        except ValueError:
            self.rotator = None
            logger.warning("⚠️ Ротатор ключей Odds API не инициализирован (нет ключей)")
        logger.info(f"🎯 Odds API ключ: {self.api_key[:8]}..." if self.api_key else "❌ Odds API КЛЮЧ НЕ НАЙДЕН!")

    def _make_request(self, endpoint, params=None):
        try:
            self.rate_limiter.wait_if_needed()
            return self.retry_manager.retry(self._make_request_impl, endpoint, params)
        except Exception as e:
            logger.error(f"❌ Ошибка Odds API: {e}")
            return None

    def _make_request_impl(self, endpoint, params=None):
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval - (now - self.last_request_time))
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params['apiKey'] = self.api_key
        r = requests.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
        self.last_request_time = time.time()
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            logger.warning("⏳ Odds API: 429, ротация ключа")
            new_key = self.rotator.rotate() if self.rotator else None
            if new_key:
                self.api_key = new_key
                raise APIErrorRetry("Odds API 429 → смена ключа")
            retry_after = int(r.headers.get('Retry-After', 60))
            time.sleep(retry_after)
            raise APIErrorRetry("Odds API rate limit")
        if r.status_code == 401:
            logger.error("❌ Odds API: 401 — ключ невалиден")
            new_key = self.rotator.rotate() if self.rotator else None
            if new_key:
                self.api_key = new_key
                raise APIErrorRetry("Odds API 401 → смена ключа")
        logger.error(f"❌ Odds API {r.status_code}")
        return None

    @timing_decorator()
    def get_odds_for_match(self, home_team, away_team, league):
        cache_key = f"odds_{home_team}_{away_team}_{league}"
        cached = self.cache.get(cache_key, data_type='odds')
        if cached is not None:
            return cached
        try:
            sport_key = Config.ODDS_SPORT_MAP.get(league, 'soccer_epl')
            data = self._make_request(f"/sports/{sport_key}/odds", {
                'regions': 'eu', 'markets': 'h2h,totals', 'oddsFormat': 'decimal'
            })
            if data:
                for event in data:
                    eh = event.get('home_team', '').lower()
                    ea = event.get('away_team', '').lower()
                    hl, al = home_team.lower(), away_team.lower()
                    if (hl in eh or eh in hl) and (al in ea or ea in al):
                        result = self._extract_odds(event)
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"❌ Ошибка Odds API: {e}")
        return None

    def _extract_odds(self, event):
        result = {'best_odds': 0, 'bookmaker_name': '—', 'home_odds': 0,
                  'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0}
        for bm in event.get('bookmakers', []):
            bmk = bm.get('key', '')
            for market in bm.get('markets', []):
                mk = market.get('key', '')
                for o in market.get('outcomes', []):
                    name = o.get('name', '')
                    price = o.get('price', 0)
                    if mk == 'h2h':
                        if name == event.get('home_team'):
                            result['home_odds'] = max(result['home_odds'], price)
                        elif name == event.get('away_team'):
                            result['away_odds'] = max(result['away_odds'], price)
                        elif name == 'Draw':
                            result['draw_odds'] = max(result['draw_odds'], price)
                    if price > result['best_odds']:
                        result['best_odds'] = price
                        result['bookmaker_name'] = bmk
        return result


odds_api = OddsAPIClient()


# ============================================================
# AUTOBET
# ============================================================
class AutoBet:
    def __init__(self):
        self.enabled = True
        self.bets_today = 0
        self.max_bets_per_day = 10

    def check_and_bet(self, match_data):
        if not self.enabled:
            return None
        bets = match_data.get('bets', [])
        if not bets:
            return None
        best_bet = max(bets, key=lambda x: x.get('ev', 0))
        if best_bet.get('ev', 0) <= 0:
            return None
        if best_bet.get('odds', 0) < 1.5:
            return None
        bank = storage.load_bank()
        stake = best_bet.get('stake', 0)
        max_stake = bank * 0.1
        if stake > max_stake:
            stake = max_stake
            best_bet['stake'] = stake
        self.bets_today += 1
        return {
            'match': f"{match_data.get('home', '')} vs {match_data.get('away', '')}",
            'match_time': match_data.get('match_time', ''),
            'bet': best_bet.get('label', ''),
            'odds': best_bet.get('odds', 0),
            'stake': stake,
            'ev': best_bet.get('ev', 0),
            'prob': best_bet.get('prob', 0),
            'home_form': match_data.get('home_form', ''),
            'away_form': match_data.get('away_form', ''),
            'home_position': match_data.get('standings', {}).get('home_position', '?'),
            'away_position': match_data.get('standings', {}).get('away_position', '?'),
            'bookmaker': best_bet.get('bookmaker', '—'),
            'bet_type': best_bet.get('type', 'under'),
            'source': match_data.get('source', '70_percent')
        }


auto_bet = AutoBet()


# ============================================================
# ЭКСПОРТ EXCEL
# ============================================================
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
    headers = ["Дата", "Матч", "Счёт", "Ставка", "Коэф", "EV%", "Сумма",
               "Результат", "Прибыль", "Букмекер"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        c.alignment = Alignment(horizontal="center")
    total_profit = 0
    for bet in history:
        score = f"{bet.get('home_goals', '-')}-{bet.get('away_goals', '-')}"
        result = bet.get('result', 'pending')
        profit = bet.get('profit', 0)
        if result == 'win' and profit == 0:
            profit = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
        elif result == 'loss' and profit == 0:
            profit = -bet.get('stake', 0)
        if result in ('win', 'loss'):
            total_profit += profit
        ws.append([bet.get('date', ''), f"{bet.get('home', '')} vs {bet.get('away', '')}",
                   score, bet.get('bet', ''), bet.get('odds', 0), bet.get('ev', 0),
                   bet.get('stake', 0), result, profit, bet.get('bookmaker', '—')])
    ws.append([])
    ws.append(["ИТОГО", "", "", "", "", "", "", "", round(total_profit, 2), ""])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output, f"✅ Экспорт! Ставок: {len(history)}, Прибыль: ${round(total_profit, 2)}"


def get_profit_data(history):
    profits = []
    days = 7
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
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}


# ============================================================
# АНАЛИЗ
# ============================================================
def get_motivation(position):
    if position <= 4: return 'champions_league'
    if position <= 6: return 'europa_league'
    if position <= 17: return 'mid_table'
    return 'relegation'


def analyze_form(form_string):
    if not form_string: return 'average'
    wins = form_string.count('W')
    if wins >= 4: return 'excellent'
    if wins >= 3: return 'good'
    if wins >= 2: return 'average'
    return 'poor'


def calculate_poisson_probability(home_xg, away_xg):
    def poisson(avg, g):
        return (math.exp(-avg) * avg ** g) / math.factorial(g)
    hgp = [poisson(home_xg, i) for i in range(6)]
    agp = [poisson(away_xg, i) for i in range(6)]
    prob = {'home_win': 0, 'away_win': 0, 'draw': 0, '1X': 0, 'X2': 0, 'btts': 0}
    for h in range(6):
        for a in range(6):
            p = hgp[h] * agp[a]
            if h > a: prob['home_win'] += p
            elif h < a: prob['away_win'] += p
            else: prob['draw'] += p
            if h >= a: prob['1X'] += p
            if a >= h: prob['X2'] += p
            if h > 0 and a > 0: prob['btts'] += p
    return prob


def calculate_form_probability(home_form, away_form):
    hq = analyze_form(home_form)
    aq = analyze_form(away_form)
    prob = {'home_win': 0.35, 'away_win': 0.30, 'draw': 0.35,
            '1X': 0.70, 'X2': 0.65, 'btts': 0.45}
    if hq == 'excellent' and aq == 'poor':
        prob['home_win'] += 0.15; prob['1X'] += 0.10
        prob['away_win'] -= 0.10; prob['X2'] -= 0.10
    elif hq == 'poor' and aq == 'excellent':
        prob['away_win'] += 0.15; prob['X2'] += 0.10
        prob['home_win'] -= 0.10; prob['1X'] -= 0.10
    return prob


def calculate_h2h_probability(h2h_data):
    prob = {'home_win': 0.33, 'away_win': 0.33, 'draw': 0.34,
            '1X': 0.67, 'X2': 0.67, 'btts': 0.50}
    if h2h_data and h2h_data.get('total_matches', 0) > 0:
        total = h2h_data['total_matches']
        prob['home_win'] = (h2h_data.get('home_wins', 0) / total) * 0.5 + 0.25
        prob['away_win'] = (h2h_data.get('away_wins', 0) / total) * 0.5 + 0.25
        prob['draw'] = (h2h_data.get('draws', 0) / total) * 0.5 + 0.25
        prob['1X'] = prob['home_win'] + prob['draw']
        prob['X2'] = prob['away_win'] + prob['draw']
    return prob


def ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data, match_data=None):
    engine = getattr(Config, 'PREDICTION_ENGINE', 'heuristic')
    poisson = calculate_poisson_probability(home_xg, away_xg)
    form_prob = calculate_form_probability(home_form, away_form)
    h2h_prob = calculate_h2h_probability(h2h_data)

    if engine == 'hybrid':
        w_p, w_f, w_h = 0.45, 0.35, 0.20
    else:
        w_p, w_f, w_h = 0.5, 0.3, 0.2

    final = {}
    for k in poisson:
        final[k] = poisson[k] * w_p + form_prob.get(k, 0) * w_f + h2h_prob.get(k, 0) * w_h

    total = final['home_win'] + final['draw'] + final['away_win']
    if total > 0:
        final['home_win'] /= total
        final['away_win'] /= total
        final['draw'] /= total
        final['1X'] = final['home_win'] + final['draw']
        final['X2'] = final['away_win'] + final['draw']

    if engine == 'llm' and Config.LLM_ENABLED and match_data:
        llm = llm_analyze_match(match_data)
        if llm:
            alpha = 0.6
            for k in ('home_win', 'draw', 'away_win'):
                final[k] = final[k] * (1 - alpha) + llm[k] * alpha
            final['1X'] = final['home_win'] + final['draw']
            final['X2'] = final['away_win'] + final['draw']
            if 'btts' in llm:
                final['btts'] = final['btts'] * (1 - alpha) + llm['btts'] * alpha
            logger.info(f"🤖 LLM: H={final['home_win']:.2f} D={final['draw']:.2f} A={final['away_win']:.2f}")

    return final


def determine_bet_result(bet_type, home_goals, away_goals):
    bt = bet_type.lower()
    if 'п1' in bt:
        return 'win' if home_goals > away_goals else ('push' if home_goals == away_goals else 'loss')
    if 'п2' in bt:
        return 'win' if away_goals > home_goals else ('push' if home_goals == away_goals else 'loss')
    if '1x' in bt:
        return 'win' if home_goals >= away_goals else 'loss'
    if 'x2' in bt:
        return 'win' if away_goals >= home_goals else 'loss'
    if 'обз' in bt or 'btts' in bt:
        return 'win' if home_goals > 0 and away_goals > 0 else 'loss'
    return 'pending'


def update_manual_result(match_name, score):
    try:
        hg = ag = None
        if score and '-' in score:
            parts = score.split('-')
            hg = int(parts[0].strip())
            ag = int(parts[1].strip())
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
                r = f"📊 <b>АНАЛИЗ</b>\n🏟️ {full}\n🏆 {m.get('league', '?')}\n📅 {m.get('match_time', '?')}\n\n"
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
# ОБНОВЛЕНИЕ КОЭФФИЦИЕНТОВ
# ============================================================
def update_odds_for_matches(matches):
    updated = []
    for md in matches:
        try:
            home = md.get('home'); away = md.get('away'); league = md.get('league')
            fid = md.get('fixture_id')
            best_bet = md.get('best_bet', {})
            bt = best_bet.get('type', 'under')
            new_odds = None
            bookmaker = '—'
            source = None

            od = odds_api.get_odds_for_match(home, away, league)
            if od and od.get('best_odds', 0) > 0:
                if bt in ('1X', 'П1') and od.get('home_odds', 0) > 0:
                    new_odds = od['home_odds']
                elif bt in ('X2', 'П2') and od.get('away_odds', 0) > 0:
                    new_odds = od['away_odds']
                else:
                    new_odds = od.get('best_odds', 0)
                if new_odds:
                    bookmaker = od.get('bookmaker_name', 'Odds API')
                    source = 'Odds API'

            if not new_odds and fid:
                fo = football_api.get_match_odds(fid)
                if fo:
                    if bt in ('1X', 'П1') and fo.get('home_odds', 0) > 0:
                        new_odds = fo['home_odds']
                    elif bt in ('X2', 'П2') and fo.get('away_odds', 0) > 0:
                        new_odds = fo['away_odds']
                    else:
                        new_odds = fo.get('best_odds', 0)
                    if new_odds:
                        bookmaker = fo.get('bookmaker', 'Football API')
                        source = 'Football API'

            if not new_odds:
                prob = best_bet.get('prob', 0) / 100
                if prob > 0:
                    new_odds = round((1 / prob) * 0.95, 2)
                    bookmaker = 'Fair Odds'
                    source = 'Calculated'

            if new_odds and new_odds > 0:
                prob = best_bet.get('prob', 0) / 100
                best_bet['odds'] = round(new_odds, 2)
                best_bet['ev'] = round((prob * new_odds - 1) * 100, 1)
                best_bet['bookmaker'] = bookmaker
                best_bet['odds_source'] = source
                md['best_bet'] = best_bet
                md['odds_updated'] = True
            updated.append(md)
        except Exception as e:
            logger.error(f"Ошибка кэфов: {e}")
            updated.append(md)
    return updated


# ============================================================
# ПОИСК МАТЧЕЙ
# ============================================================
def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    all_leagues = Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])
    logger.info(f"🔍 Поиск матчей: {today}, лиг: {len(all_leagues)}")
    for league_id in all_leagues:
        try:
            matches = football_api.get_matches(league_id, today)
            league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
            if not matches:
                continue
            for m in matches:
                if not isinstance(m, dict):
                    continue
                fixture = m.get('fixture')
                if not fixture or not isinstance(fixture, dict):
                    continue
                if fixture.get('status', {}).get('short') != 'NS':
                    continue
                mid = fixture.get('id')
                if not mid:
                    continue
                if any(x.get('fixture', {}).get('id') == mid for x in all_matches if isinstance(x, dict)):
                    continue
                teams = m.get('teams', {})
                hid = teams.get('home', {}).get('id')
                aid = teams.get('away', {}).get('id')
                if not hid or not aid:
                    continue

                m['factors'] = {
                    'home_form': football_api.get_form(hid),
                    'away_form': football_api.get_form(aid),
                    'home_injuries_list': football_api.get_injuries(hid),
                    'away_injuries_list': football_api.get_injuries(aid),
                    'home_id': hid, 'away_id': aid,
                    'referee': fixture.get('referee')
                }

                weather = None
                venue = fixture.get('venue', {})
                city = venue.get('city') if isinstance(venue, dict) else None
                if city and Config.WEATHER_ENABLED:
                    weather = Config.get_weather_for_city(city)
                m['weather'] = weather
                if weather:
                    m['weather_reason'] = (
                        f"🌤️ {weather['desc']}, {weather['temp']}°C, "
                        f"ветер {weather['wind']} м/с, дождь {weather['rain']} мм"
                    )
                else:
                    m['weather_reason'] = "🌤️ Нет данных"

                ld = m.get('league', {})
                if isinstance(ld, dict):
                    ld['name'] = league_name
                all_matches.append(m)
        except Exception as e:
            logger.error(f"❌ {league_id}: {e}")
        time.sleep(0.1)
    logger.info(f"📊 Найдено матчей: {len(all_matches)}")
    return all_matches


# ============================================================
# ПОИСК ТОП-МАТЧЕЙ
# ============================================================
@timing_decorator()
def find_top_matches(matches):
    bank = storage.load_bank()
    max_bets = getattr(Config, 'MAX_BETS_PER_RUN', 10)
    logger.info(f"🔍 Анализ {len(matches)} матчей...")
    best_matches = []
    bet_type_count = {}
    league_count = {}

    for match in matches:
        if not match or not isinstance(match, dict):
            continue
        try:
            fixture = match.get('fixture')
            teams = match.get('teams')
            if not fixture or not teams:
                continue
            fid = fixture.get('id')
            ht = teams.get('home', {}); at = teams.get('away', {})
            home = ht.get('name', 'Unknown'); away = at.get('name', 'Unknown')
            ld = match.get('league', {})
            league_name = ld.get('name', 'Unknown')
            league_id = ld.get('id')
            match_time = fixture.get('date', '')
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00")) + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    match_time = "?"

            hfd = football_api.get_form(ht.get('id'))
            afd = football_api.get_form(at.get('id'))
            home_form = hfd.get('form', '') if hfd else ''
            away_form = afd.get('form', '') if afd else ''

            hga = hfd.get('goals_avg', 1.2) if hfd else 1.2
            aga = afd.get('goals_avg', 1.0) if afd else 1.0
            hca = hfd.get('conceded_avg', 1.0) if hfd else 1.0
            aca = afd.get('conceded_avg', 1.2) if afd else 1.2

            home_xg = (hga + aca) / 2
            away_xg = (aga + hca) / 2

            h_inj = len(match.get('factors', {}).get('home_injuries_list', []))
            a_inj = len(match.get('factors', {}).get('away_injuries_list', []))
            if h_inj > 3: home_xg *= 0.8
            if a_inj > 3: away_xg *= 0.8

            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            total_xg = home_xg + away_xg

            w = match.get('weather')
            if w:
                rain = w.get('rain', 0) or 0
                wind = w.get('wind', 0) or 0
                if rain > 2:
                    total_xg *= 0.92
                    home_xg *= 0.95
                    away_xg *= 0.95
                elif rain > 0.5:
                    total_xg *= 0.96
                if wind > 10:
                    total_xg *= 0.95
                elif wind > 7:
                    total_xg *= 0.98

            ev_min = getattr(Config, 'EV_MIN_70', 20)
            prob_min = getattr(Config, 'PROB_MIN_70', 60)
            xg_min = getattr(Config, 'XG_MIN_70', 1.8)
            xg_max = getattr(Config, 'XG_MAX_70', 3.0)
            pos_max = getattr(Config, 'POSITION_MAX_70', 15)
            if total_xg < xg_min or total_xg > xg_max:
                continue

            standings = football_api.get_standings(league_id) if league_id else None
            hp = standings.get(home, {}).get('position', 99) if standings else 99
            ap = standings.get(away, {}).get('position', 99) if standings else 99
            hm = get_motivation(hp); am = get_motivation(ap)
            if hm == 'mid_table' and am == 'mid_table':
                continue
            if hp > pos_max or ap > pos_max:
                continue

            h2h = football_api.get_head_to_head(home, away)
            probs = ensemble_probability(
                home_xg, away_xg, home_form, away_form, h2h,
                match_data={
                    'home': home, 'away': away, 'league': league_name,
                    'home_xg': round(home_xg, 2), 'away_xg': round(away_xg, 2),
                    'total_xg': round(total_xg, 2),
                    'home_form': home_form, 'away_form': away_form,
                    'standings': {'home_position': hp, 'away_position': ap},
                    'weather_reason': match.get('weather_reason', 'нет')
                }
            )

            odds = {
                '1X': 1.85 if probs['1X'] > 0.70 else 1.75,
                'X2': 1.85 if probs['X2'] > 0.70 else 1.75,
                'П1': 2.10,
                'П2': 2.10,
                'ОБЗ': 1.90,
            }

            if hm == 'relegation' and am == 'mid_table':
                probs['1X'] += 0.08
            elif am == 'relegation' and hm == 'mid_table':
                probs['X2'] += 0.08

            stake = round(bank * 0.02, 2) if bank > 0 else 10.0
            bets = []
            for bet_type, label, prob_key, odd in [
                ('1X', '1X', '1X', odds['1X']),
                ('X2', 'X2', 'X2', odds['X2']),
                ('П1', 'П1', 'home_win', odds['П1']),
                ('П2', 'П2', 'away_win', odds['П2']),
                ('btts', 'ОБЗ', 'btts', odds['ОБЗ']),
            ]:
                p = probs.get(prob_key, 0)
                bets.append({
                    'type': bet_type, 'label': label,
                    'prob': round(p * 100, 1),
                    'ev': round((p * odd - 1) * 100, 1),
                    'odds': odd, 'stake': stake
                })

            bets.sort(key=lambda x: x['ev'], reverse=True)
            best_bet = bets[0]
            if best_bet['ev'] < ev_min or best_bet['prob'] < prob_min:
                continue

            bt = best_bet['type']
            bet_type_count[bt] = bet_type_count.get(bt, 0) + 1
            if bet_type_count[bt] > 3:
                continue
            league_count[league_name] = league_count.get(league_name, 0) + 1
            if league_count[league_name] > 2:
                continue

            best_matches.append({
                "home": home, "away": away, "league": league_name,
                "fixture_id": fid, "match_time": match_time,
                "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
                "total_xg": round(total_xg, 2),
                "home_form": home_form, "away_form": away_form,
                "standings": {"home_position": hp, "away_position": ap,
                              "home_motivation": hm, "away_motivation": am},
                "bets": bets, "best_bet": best_bet,
                "weather_reason": match.get('weather_reason', ''),
                "factors": {}, "source": "70_percent"
            })
            logger.info(f"✅ {home} vs {away} | {best_bet['label']} | EV: {best_bet['ev']}%")
        except Exception as e:
            logger.error(f"❌ {e}")
            continue

    best_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    return best_matches[:max_bets]


@timing_decorator()
def find_top_matches_with_tm25(matches):
    """Историческое имя — теперь только 70%+ поток."""
    result = find_top_matches(matches)
    if result:
        result = update_odds_for_matches(result)
        cache = storage.load_cache()
        cache['top_matches'] = result
        storage.save_cache(cache)

        history = storage.load_history()
        for md in result:
            bb = md.get('best_bet', {})
            history.append({
                'home': md.get('home'), 'away': md.get('away'),
                'league': md.get('league'), 'bet': bb.get('label', '—'),
                'odds': bb.get('odds', 0), 'stake': bb.get('stake', 0),
                'ev': bb.get('ev', 0), 'result': 'pending', 'profit': 0,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'fixture_id': md.get('fixture_id'),
                'bookmaker': bb.get('bookmaker', '—'),
                'engine': Config.PREDICTION_ENGINE,
                'weather_reason': md.get('weather_reason', '')
            })
        storage.save_history(history)
    return result


# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================
@timing_decorator()
def update_pending_bets():
    history = storage.load_history()
    updated = 0
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
                    if hg is not None and ag is not None:
                        result = determine_bet_result(bet.get('bet', ''), hg, ag)
                        if result != 'pending':
                            bet['result'] = result
                            bet['home_goals'] = hg
                            bet['away_goals'] = ag
                            if result == 'win':
                                bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                            elif result == 'loss':
                                bet['profit'] = -bet['stake']
                            else:
                                bet['profit'] = 0
                            updated += 1
    if updated > 0:
        storage.save_history(history)
        recalc_stats()
    return updated


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
        'roi': round(profit / stake_sum * 100, 1) if stake_sum else 0
    })
    storage.save_stats(stats)


# ============================================================
# РАСПИСАНИЯ
# ============================================================
def schedule_updates():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=auto_update_results, trigger='interval',
                      hours=6, id='auto_update', replace_existing=True)
    scheduler.start()
    logger.info("⏰ Авто-обновление: каждые 6 часов")


def auto_update_results():
    try:
        updated = update_pending_bets()
        if updated > 0:
            send_telegram(f"🔄 Авто-обновление: {updated} результатов")
    except Exception as e:
        logger.error(f"❌ Авто-обновление: {e}")


def schedule_notifications():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=lambda: notification_system.run_all_checks(),
                      trigger='interval', hours=1, id='notifications', replace_existing=True)
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
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=report, trigger='interval', hours=6,
                      id='perf_report', replace_existing=True)
    scheduler.start()


# ============================================================
# ВЕРИФИКАЦИЯ
# ============================================================
class BetVerificationSystem:
    def __init__(self):
        self.thresholds = {'min_odds': 1.50, 'max_odds': 3.00, 'min_ev': 15,
                           'min_prob': 50, 'max_stake_percent': 10, 'min_samples': 10}
        self.warnings = []

    def verify(self, bet_data):
        self.warnings = []
        self._check_odds(bet_data)
        self._check_ev_prob(bet_data)
        self._check_stake(bet_data)
        self._check_league(bet_data)
        self._check_form(bet_data)
        if not self.warnings:
            return {'status': '✅', 'message': 'OK'}
        if len(self.warnings) <= 2:
            return {'status': '⚠️', 'message': f'{len(self.warnings)} предупр.',
                    'warnings': self.warnings}
        return {'status': '❌', 'message': 'Отклонено', 'warnings': self.warnings}

    def _check_odds(self, bd):
        o = bd.get('odds', 0)
        if o < self.thresholds['min_odds']:
            self.warnings.append(f"Низкий кэф: {o}")
        if o > self.thresholds['max_odds']:
            self.warnings.append(f"Высокий кэф: {o}")

    def _check_ev_prob(self, bd):
        if bd.get('ev', 0) < self.thresholds['min_ev']:
            self.warnings.append(f"Низкий EV: {bd.get('ev')}%")
        if bd.get('prob', 0) < self.thresholds['min_prob']:
            self.warnings.append(f"Низкая Prob: {bd.get('prob')}%")

    def _check_stake(self, bd):
        stake = bd.get('stake', 0)
        bank = storage.load_bank()
        if bank > 0 and (stake / bank) * 100 > self.thresholds['max_stake_percent']:
            self.warnings.append(f"Ставка {stake:.2f} > 10% банка")

    def _check_league(self, bd):
        if bd.get('league') in TOP_LEAGUES and bd.get('ev', 0) < 25:
            self.warnings.append(f"Топ-лига, EV {bd.get('ev')}% < 25%")

    def _check_form(self, bd):
        if bd.get('home_form', '').endswith('LLL'):
            self.warnings.append("Хозяева: 3 поражения")
        if bd.get('away_form', '').endswith('LLL'):
            self.warnings.append("Гости: 3 поражения")


# ============================================================
# УВЕДОМЛЕНИЯ
# ============================================================
class NotificationSystem:
    def __init__(self):
        self.last_notification = {}
        self.min_interval = 3600

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
        if len(history) < 5:
            return
        recent = [b for b in history[-10:] if b.get('result') in ('win', 'loss')]
        if len(recent) < 5:
            return
        streak_type = recent[-1].get('result')
        streak = 0
        for b in reversed(recent):
            if b.get('result') == streak_type:
                streak += 1
            else:
                break
        if streak >= 5:
            emoji = "🟢" if streak_type == 'win' else "🔴"
            self.send_if_needed(f'streak_{streak_type}',
                                f"{emoji} {streak} подряд {streak_type}")

    def check_roi(self):
        stats = storage.load_stats()
        roi = stats.get('roi', 0)
        if roi > 20:
            self.send_if_needed('roi_high', f"📈 ROI: {roi}%")
        elif roi < -10:
            self.send_if_needed('roi_low', f"📉 ROI: {roi}%")

    def run_all_checks(self):
        try:
            self.check_bank_status()
            self.check_streaks()
            self.check_roi()
        except Exception as e:
            logger.error(f"Ошибка уведомлений: {e}")


notification_system = NotificationSystem()


# ============================================================
# СТРАТЕГИИ
# ============================================================
class StrategyTester:
    def __init__(self):
        self.strategies = {
            '70_percent': {
                'name': '70%+ матчи', 'bets': [], 'profit': 0,
                'wins': 0, 'losses': 0, 'total_stake': 0, 'active': True
            }
        }

    def add_bet(self, source, bet_data):
        if source in self.strategies:
            s = self.strategies[source]
            s['bets'].append(bet_data)
            if bet_data.get('result') == 'win':
                s['wins'] += 1
            elif bet_data.get('result') == 'loss':
                s['losses'] += 1
            s['profit'] += bet_data.get('profit', 0)
            s['total_stake'] += bet_data.get('stake', 0)

    def get_comparison_report(self):
        report = "📊 <b>СТРАТЕГИИ</b>\n\n"
        for name, data in self.strategies.items():
            total = len(data['bets'])
            wr = (data['wins'] / total * 100) if total else 0
            roi = (data['profit'] / data['total_stake'] * 100) if data['total_stake'] else 0
            report += (f"<b>{data['name']}</b>\n"
                       f"Ставок: {total} | WR: {wr:.1f}% | "
                       f"Прибыль: ${data['profit']:.2f} | ROI: {roi:.1f}%\n\n")
        return report


strategy_tester = StrategyTester()


# ============================================================
# СОСТОЯНИЕ БОТА
# ============================================================
class BotState:
    def __init__(self):
        self.state_file = 'bot_state.json'
        self.backup_dir = 'state_backups'
        self.state = self.load_state()
        os.makedirs(self.backup_dir, exist_ok=True)

    def load_state(self):
        default = {
            'start_time': datetime.now().isoformat(),
            'search_running': False,
            'stats': {'total_processed': 0, 'total_found': 0, 'total_bets': 0},
            'last_full_search': None, 'version': '1.0.0'
        }
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file) as f:
                    state = json.load(f)
                for k, v in default.items():
                    state.setdefault(k, v)
                return state
        except Exception:
            pass
        return default

    def save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Ошибка save_state: {e}")

    def update(self, **kwargs):
        self.state.update(kwargs)
        self.save_state()

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
        if os.path.exists('bot_settings.json'):
            with open('bot_settings.json') as f:
                s = json.load(f)
            Config.EV_MIN_70 = s.get('ev_min_70', getattr(Config, 'EV_MIN_70', 20))
            Config.PROB_MIN_70 = s.get('prob_min_70', getattr(Config, 'PROB_MIN_70', 60))
            Config.XG_MIN_70 = s.get('xg_min_70', getattr(Config, 'XG_MIN_70', 1.8))
            Config.XG_MAX_70 = s.get('xg_max_70', getattr(Config, 'XG_MAX_70', 3.0))
            Config.POSITION_MAX_70 = s.get('position_max_70', getattr(Config, 'POSITION_MAX_70', 15))
            logger.info("✅ Настройки загружены из bot_settings.json")
            return True
    except Exception as e:
        logger.error(f"Ошибка настроек: {e}")
    return False


# ============================================================
# WEBHOOK
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running, search_state
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return "ok", 200

        message = data['message']
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')

        if str(chat_id) != str(Config.ADMIN_CHAT_ID):
            logger.warning(f"⛔ Доступ запрещён для {chat_id}")
            return "ok", 200

        if text == '/start':
            send_telegram(handlers.handle_start())
        elif text == '/help':
            send_telegram(handlers.handle_help())

        elif text == '/update':
            if search_running:
                send_telegram("⚠️ Поиск уже запущен")
                return "ok", 200
            search_running = True
            search_state = {'start_time': datetime.now()}
            send_telegram("🔎 Запущен анализ матчей. Ждите...")

            def run_search():
                global search_running
                try:
                    matches = get_matches_with_factors()
                    if matches:
                        top = find_top_matches_with_tm25(matches)
                        if top:
                            msg = f"✅ <b>НАЙДЕНО: {len(top)}</b>\n\n"
                            for i, m in enumerate(top[:10], 1):
                                b = m['best_bet']
                                msg += (f"{i}. <b>{m['home']} vs {m['away']}</b>\n"
                                        f"🎯 {b['label']} | КЭФ: {b['odds']} | EV: {b['ev']}%\n\n")
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
            search_state = {}
            send_telegram("✅ Сброшено")

        elif text == '/today':
            send_telegram(handlers.handle_today())
        elif text == '/stats':
            send_telegram(handlers.handle_stats())
        elif text == '/bank':
            send_telegram(handlers.handle_bank())
        elif text == '/strategies':
            send_telegram(strategy_tester.get_comparison_report())
        elif text == '/report':
            send_telegram(handlers.handle_report())
        elif text == '/bettypes':
            send_telegram(handlers.handle_bettypes())
        elif text == '/timestats':
            send_telegram(handlers.handle_timestats())
        elif text.startswith('/team '):
            send_telegram(handlers.handle_team(text[6:].strip()))

        elif text == '/update_results':
            updated = update_pending_bets()
            send_telegram(f"✅ Обновлено: {updated}" if updated else "📭 Нет обновлений")
        elif text.startswith('/result '):
            parts = text[8:].strip()
            if ' vs ' in parts:
                sp = parts.split(' vs ')
                home = sp[0].strip()
                rest = sp[1].split()
                if len(rest) >= 2:
                    send_telegram(update_manual_result(f"{home} vs {rest[0]}", rest[1]))
                else:
                    send_telegram("⚠️ Используй: /result Fulham vs Chelsea 2-1")
            else:
                send_telegram("⚠️ Используй: /result Fulham vs Chelsea 2-1")

        elif text.startswith('/analyze '):
            send_telegram(analyze_match(text[9:].strip()))

        elif text == '/export':
            file, message = export_to_excel()
            send_telegram(message)
            if file:
                try:
                    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                    requests.post(
                        url,
                        files={'document': ('history.xlsx', file,
                               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                        data={'chat_id': Config.ADMIN_CHAT_ID, 'caption': '📊 История ставок'},
                        timeout=30
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки файла: {e}")

        elif text == '/autobet':
            auto_bet.enabled = not auto_bet.enabled
            send_telegram(handlers.handle_autobet(auto_bet.enabled))
        elif text == '/status':
            send_telegram(bot_state.get_status_report())
        elif text == '/stop':
            search_running = False
            search_state = {}
            send_telegram("⏹️ Поиск остановлен")

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
    except Exception as e:
        logger.error(f"Ошибка загрузки sw.js: {e}")
        return "Service Worker не найден", 404


@app.route('/manifest.json')
def serve_manifest():
    try:
        return send_from_directory('.', 'manifest.json', mimetype='application/json')
    except Exception as e:
        logger.error(f"Ошибка загрузки manifest.json: {e}")
        return "Манифест не найден", 404


# ============================================================
# ЛОГИ ДЛЯ X2
# ============================================================
LOG_FILE = 'matches_log.txt'


@app.route('/api/matches_log', methods=['GET'])
def get_matches_log():
    try:
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write("2026-09-09 10:00 - Blackburn vs Sheffield Utd | XG: 2.1 | нет мотивации у фаворита\n")
                f.write("2026-09-09 12:00 - Al-Ettifaq vs Al-Faisaly | XG: 1.8 | H: #5, A: #12 | no motivation\n")
                f.write("2026-09-09 14:00 - Real Madrid vs Barcelona | XG: 2.5 | H: #1, A: #3 | нет мотивации\n")
                f.write("2026-09-09 16:00 - Aris Thessalonikis vs OFI | XG: 1.9 | H: #7, A: #15 | no motivation\n")
                f.write("2026-09-09 18:00 - Panathinaikos vs PAOK | XG: 2.2 | H: #4, A: #2 | нет мотивации у гостей\n")
                f.write("2026-09-09 20:00 - AEK vs Olympiakos | XG: 1.7 | H: #6, A: #1 | no motivation\n")
            logger.info("✅ Создан тестовый файл логов")

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log_text = f.read()

        return jsonify({
            'success': True,
            'log': log_text,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ Ошибка получения логов: {e}")
        return jsonify({'success': False, 'error': str(e), 'log': ''}), 500


@app.route('/api/update_logs', methods=['POST'])
def update_logs():
    try:
        data = request.json
        log_text = data.get('log', '')
        if not log_text:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400

        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_text + '\n')

        return jsonify({'success': True, 'message': 'Логи обновлены'})
    except Exception as e:
        logger.error(f"❌ Ошибка обновления логов: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API
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
            'stats': {
                'bank': bank,
                'total_bets': stats.get('total', 0),
                'wins': stats.get('wins', 0),
                'losses': stats.get('losses', 0),
                'profit': stats.get('total_profit', 0),
                'winrate': stats.get('winrate', 0),
                'roi': stats.get('roi', 0),
                'avg_stake': stats.get('avg_stake', 0)
            },
            'history': history,
            'profit_data': profit_data,
            'matches': cache.get('top_matches', [])
        })
    except Exception as e:
        logger.error(f"❌ Ошибка в /api/all_data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        excel_data = data.get('data', [])
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400

        history = storage.load_history()
        imported = 0

        for row in excel_data:
            match = row.get('Матч', '') or row.get('Match', '')
            home = away = ''
            if ' vs ' in match:
                parts = match.split(' vs ')
                home, away = parts[0].strip(), parts[1].strip()
            elif ' - ' in match:
                parts = match.split(' - ')
                home, away = parts[0].strip(), parts[1].strip()

            score = row.get('Счёт', '') or row.get('Score', '')
            hg = ag = None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    hg = int(parts[0].strip())
                    ag = int(parts[1].strip())
                except Exception:
                    pass

            history.append({
                'home': home or 'Unknown',
                'away': away or 'Unknown',
                'league': 'Импорт из Excel',
                'bet': row.get('Ставка', '') or row.get('Bet', ''),
                'odds': float(row.get('Коэф', 1.85)),
                'stake': float(row.get('Сумма', 0)),
                'ev': float(row.get('EV%', 0)),
                'result': row.get('Результат', 'pending'),
                'profit': float(row.get('Прибыль', 0)),
                'date': row.get('Дата', '') or datetime.now().strftime('%Y-%m-%d %H:%M'),
                'home_goals': hg,
                'away_goals': ag,
                'bookmaker': row.get('Букмекер', '—')
            })
            imported += 1

        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        logger.error(f"Ошибка импорта Excel: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        history = data.get('history', [])
        stats = data.get('stats', {})
        if not history:
            return jsonify({'error': 'Нет данных для импорта'}), 400

        current = storage.load_history()
        existing = {f"{b.get('date', '')}_{b.get('home', '')}_{b.get('away', '')}" for b in current}

        imported = 0
        for bet in history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            if key not in existing:
                current.append(bet)
                imported += 1
                existing.add(key)

        if stats and 'bank' in stats:
            storage.save_bank(stats['bank'])

        storage.save_history(current)
        recalc_stats()
        return jsonify({'success': True, 'count': imported})
    except Exception as e:
        logger.error(f"Ошибка импорта проекта: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404

        b = history[index]
        b['home'] = data.get('home', b['home'])
        b['away'] = data.get('away', b['away'])
        b['home_goals'] = data.get('home_goals')
        b['away_goals'] = data.get('away_goals')
        b['bet'] = data.get('bet', b['bet'])
        b['odds'] = data.get('odds', b['odds'])
        b['stake'] = data.get('stake', b['stake'])
        b['ev'] = data.get('ev', b['ev'])
        b['result'] = data.get('result', b['result'])
        b['bookmaker'] = data.get('bookmaker', b.get('bookmaker', '—'))

        if b['result'] == 'win':
            b['profit'] = round(b['stake'] * (b['odds'] - 1), 2)
        elif b['result'] == 'loss':
            b['profit'] = -b['stake']
        else:
            b['profit'] = 0

        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        index = request.json.get('index')
        history = storage.load_history()
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        history.pop(index)
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True})
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


@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        count = data.get('count', 1000)
        history = storage.load_history()
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок'}), 400

        wins = sum(1 for b in history if b.get('result') == 'win')
        total = len(history)
        winrate = wins / total if total > 0 else 0
        avg_stake = sum(float(b.get('stake', 0)) for b in history) / total if total > 0 else 10

        results = []
        profit_history = []
        total_profit = 0
        for i in range(count):
            if random.random() < winrate:
                profit = avg_stake * random.uniform(0.5, 1.5)
                total_profit += profit
                results.append('win')
            else:
                profit = -avg_stake
                total_profit += profit
                results.append('loss')
            profit_history.append(round(total_profit, 2))

        wins_sim = results.count('win')
        losses_sim = results.count('loss')
        max_profit = max(profit_history) if profit_history else 0
        min_profit = min(profit_history) if profit_history else 0

        return jsonify({
            'total': count, 'wins': wins_sim, 'losses': losses_sim,
            'profit': round(total_profit, 2),
            'winrate': round(wins_sim / count * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'risk': round((abs(min_profit) / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'max_profit': round(max_profit, 2),
            'min_profit': round(min_profit, 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        match_name = data.get('match', '')
        score = data.get('score', '-')
        result = data.get('result', 'win')
        stake = data.get('stake', 0)
        bet_type = data.get('bet', '')
        odds = data.get('odds', 1.85)
        bookmaker = data.get('bookmaker', 'Ручное добавление')

        if not match_name:
            return jsonify({'error': 'Название матча обязательно'}), 400

        hg = ag = None
        if score and '-' in score:
            parts = score.split('-')
            try:
                hg = int(parts[0].strip())
                ag = int(parts[1].strip())
            except Exception:
                pass

        home = away = 'Unknown'
        if ' vs ' in match_name:
            parts = match_name.split(' vs ')
            home, away = parts[0].strip(), parts[1].strip()
        elif ' - ' in match_name:
            parts = match_name.split(' - ')
            home, away = parts[0].strip(), parts[1].strip()

        if result == 'win':
            profit = round(stake * (odds - 1), 2)
        elif result == 'loss':
            profit = -stake
        else:
            profit = 0

        history = storage.load_history()
        history.append({
            'home': home or 'Unknown', 'away': away or 'Unknown',
            'league': 'Ручное добавление', 'bet': bet_type,
            'odds': odds, 'stake': stake, 'ev': 0,
            'result': result, 'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': hg, 'away_goals': ag,
            'manual': True, 'bookmaker': bookmaker
        })
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True, 'count': 1})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies', methods=['GET'])
def api_strategies():
    return jsonify({
        'strategies': strategy_tester.strategies,
        'current_test': getattr(strategy_tester, 'current_test', None)
    })


@app.route('/api/keepalive', methods=['GET'])
def keepalive():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat(),
                    'message': 'Keep-Alive активен'})


@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.route('/', methods=['GET'])
def index():
    return f"🤖 Quantum Bot PRO | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    setup_logging()
    load_bot_settings()
    Config.init_db()
    start_scheduler()
    schedule_updates()
    schedule_notifications()
    schedule_performance_report()

    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН")
    logger.info(f"📊 Лиг: {len(Config.LEAGUES)}")
    logger.info(f"🧠 PREDICTION_ENGINE: {Config.PREDICTION_ENGINE}")
    logger.info(f"🤖 LLM: {'вкл' if Config.LLM_ENABLED else 'выкл'}")
    logger.info(f"🌦️ Погода: {'вкл' if Config.WEATHER_ENABLED else 'выкл'}")
    logger.info(f"📢 CHANNEL_ID: {'задан' if Config.CHANNEL_ID else 'не задан'}")
    logger.info(f"🗄️ БД: {Config.DATABASE_URL}")

    app.run(host='0.0.0.0', port=port)
