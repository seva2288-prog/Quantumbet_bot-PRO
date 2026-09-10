import sys
import os
import requests
import time
import json
import logging
import random
import math
import functools
import inspect
import traceback
from datetime import datetime, timedelta
from threading import Lock
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from threading import Thread
from datetime import datetime

# ============================================================
# ИМПОРТЫ ИЗ ПРОЕКТА
# ============================================================
from app.config import Config
from app.database.storage import storage
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
logger = get_logger(__name__)
app = Flask(__name__)

search_running = False
search_state = {}
TIMEZONE_OFFSET = 3

# ============================================================
# ФАЙЛ ДЛЯ X2 ЛОГОВ
# ============================================================
X2_LOG_FILE = 'matches_log.txt'

MARKERS = {
    42.86875000000006: ('under', 1.95, 'ТМ 2.5'),
}

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
# ФУНКЦИЯ ЗАПИСИ X2 МАТЧА В ЛОГ
# ============================================================
def log_x2_match(home, away, favorite, underdog, odds, xg, note=""):
    """
    Пишет X2 матч в файл matches_log.txt для последующего импорта.
    Формат: X2_MATCH: Home vs Away | favorite: X | underdog: Y | odds: 1.85 | xg: 2.5 | note: ... | date: 2026-09-10 14:30
    """
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        line = f"X2_MATCH: {home} vs {away} | favorite: {favorite} | underdog: {underdog} | odds: {odds} | xg: {xg} | note: {note} | date: {timestamp}\n"
        
        with open(X2_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line)
        
        logger.info(f"📝 X2 матч записан в лог: {home} vs {away} | Фаворит: {favorite}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи X2 матча в лог: {e}")


def clear_x2_log():
    """Очищает лог X2 (вызывается в начале /update)"""
    try:
        with open(X2_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("")
        logger.info("🧹 X2 лог очищен")
    except Exception as e:
        logger.error(f"❌ Ошибка очистки X2 лога: {e}")


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
            metric = self.metrics[func_name]
            metric['calls'] += 1
            metric['total_time'] += elapsed
            metric['max_time'] = max(metric['max_time'], elapsed)
            metric['min_time'] = min(metric['min_time'], elapsed)
            if error:
                metric['errors'] += 1
    
    def get_report(self):
        report = []
        for func_name, metric in sorted(self.metrics.items()):
            avg_time = metric['total_time'] / metric['calls'] if metric['calls'] > 0 else 0
            error_rate = metric['errors'] / metric['calls'] * 100 if metric['calls'] > 0 else 0
            report.append({
                'function': func_name, 'calls': metric['calls'],
                'avg_time': round(avg_time, 3), 'max_time': round(metric['max_time'], 3),
                'min_time': round(metric['min_time'], 3),
                'error_rate': round(error_rate, 1),
                'total_time': round(metric['total_time'], 3)
            })
        return report
    
    def print_report(self):
        report = self.get_report()
        logger.info("=" * 60)
        logger.info("📊 ОТЧЕТ О ПРОИЗВОДИТЕЛЬНОСТИ")
        logger.info("=" * 60)
        for item in report:
            status = "✅" if item['error_rate'] < 5 else "⚠️" if item['error_rate'] < 20 else "❌"
            logger.info(f"{status} {item['function']}: {item['calls']} вызовов, среднее {item['avg_time']}с, макс {item['max_time']}с, ошибки {item['error_rate']}%")

perf_monitor = PerformanceMonitor()

def timing_decorator(name=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = name or func.__name__
            start = time.time()
            error = False
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = True
                raise
            finally:
                elapsed = time.time() - start
                perf_monitor.record(func_name, elapsed, error)
                if elapsed > 5.0:
                    logger.error(f"🐌 {func_name} ОЧЕНЬ МЕДЛЕННО: {elapsed:.2f}с")
                elif elapsed > 2.0:
                    logger.warning(f"⏱️ {func_name} выполняется {elapsed:.2f}с (медленно)")
        return wrapper
    return decorator


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
            else:
                del self.cache[key]
                del self.cache_timestamps[key]
                if key in self.hit_count: del self.hit_count[key]
                if key in self.last_access: del self.last_access[key]
        return None
    
    def set(self, key, value):
        if len(self.cache) >= self.max_size:
            to_remove = min(self.cache.keys(), key=lambda k: (self.hit_count.get(k, 0), self.last_access.get(k, 0)))
            del self.cache[to_remove]
            for d in [self.hit_count, self.last_access, self.cache_timestamps]:
                if to_remove in d: del d[to_remove]
        self.cache[key] = value
        self.cache_timestamps[key] = time.time()
        self.hit_count[key] = 0
        self.last_access[key] = time.time()
    
    def clear(self):
        self.cache = {}
        self.cache_timestamps = {}
        self.hit_count = {}
        self.last_access = {}


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
                total_delay = delay + jitter
                logger.warning(f"🔄 Попытка {attempt + 1}/{self.max_retries + 1} через {total_delay:.1f}с: {e}")
                time.sleep(total_delay)
            except APIErrorFatal:
                raise
            except Exception as e:
                raise APIErrorFatal(f"Неожиданная ошибка: {e}")


# ============================================================
# КЛАСС FOOTBALL_API
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = SmartCache(max_size=500)
        self.last_request_time = 0
        self.min_request_interval = 0.2
        self.rate_limiter = APIRateLimiter(max_requests=250, time_window=60)
        self.retry_manager = RetryManager(max_retries=3, base_delay=1)
        self.error_stats = defaultdict(int)
        logger.info(f"🔑 API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")
    
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
            'x-rapidapi-key': self.api_key,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            self.last_request_time = time.time()
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                time.sleep(retry_after)
                raise APIErrorRetry("Rate limit превышен")
            if response.status_code == 403:
                raise APIErrorFatal("Недействительный API ключ")
            if response.status_code != 200:
                if response.status_code >= 500:
                    raise APIErrorRetry(f"Серверная ошибка {response.status_code}")
                else:
                    raise APIErrorFatal(f"Ошибка API {response.status_code}")
            data = response.json()
            if data.get('errors'):
                error_msg = data['errors']
                if 'rate limit' in str(error_msg).lower():
                    raise APIErrorRetry("Rate limit в ответе")
                elif 'api key' in str(error_msg).lower():
                    raise APIErrorFatal(f"Ошибка ключа: {error_msg}")
                else:
                    return None
            return data
        except requests.exceptions.Timeout:
            raise APIErrorRetry("Таймаут запроса")
        except requests.exceptions.ConnectionError:
            raise APIErrorRetry("Ошибка соединения")
        except json.JSONDecodeError as e:
            raise APIErrorFatal(f"Ошибка парсинга JSON: {e}")
    
    @timing_decorator()
    def get_matches(self, league_id, date):
        cache_key = f"matches_{league_id}_{date}"
        cached = self.cache.get(cache_key, data_type='matches')
        if cached is not None: return cached
        params = {'league': league_id, 'season': datetime.now().year, 'date': date}
        data = self._make_request('/fixtures', params)
        if data and 'response' in data:
            self.cache.set(cache_key, data['response'])
            return data['response']
        return []
    
    @timing_decorator()
    def get_form(self, team_id):
        cache_key = f"form_{team_id}"
        cached = self.cache.get(cache_key, data_type='form')
        if cached is not None: return cached
        try:
            params = {'team': team_id, 'last': 5, 'status': 'FT'}
            data = self._make_request('/fixtures', params)
            if data and 'response' in data:
                matches = data['response']
                if matches:
                    goals_scored, goals_conceded = [], []
                    wins = draws = losses = 0
                    for match in matches:
                        goals = match.get('goals', {})
                        teams = match.get('teams', {})
                        if teams.get('home', {}).get('id') == team_id:
                            scored = goals.get('home', 0) or 0
                            conceded = goals.get('away', 0) or 0
                        else:
                            scored = goals.get('away', 0) or 0
                            conceded = goals.get('home', 0) or 0
                        goals_scored.append(scored)
                        goals_conceded.append(conceded)
                        if scored > conceded: wins += 1
                        elif scored == conceded: draws += 1
                        else: losses += 1
                    if goals_scored:
                        result = {
                            'goals_avg': round(sum(goals_scored) / len(goals_scored), 2),
                            'conceded_avg': round(sum(goals_conceded) / len(goals_conceded), 2),
                            'wins': wins, 'draws': draws, 'losses': losses,
                            'matches': len(matches),
                            'form': self._calculate_form(matches, team_id)
                        }
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"Ошибка получения формы команды {team_id}: {e}")
        return None
    
    def _calculate_form(self, matches, team_id):
        form = []
        for match in matches:
            teams = match.get('teams', {})
            goals = match.get('goals', {})
            home_score = goals.get('home', 0) or 0
            away_score = goals.get('away', 0) or 0
            if teams.get('home', {}).get('id') == team_id:
                if home_score > away_score: form.append('W')
                elif home_score == away_score: form.append('D')
                else: form.append('L')
            else:
                if away_score > home_score: form.append('W')
                elif away_score == home_score: form.append('D')
                else: form.append('L')
        return ''.join(form)
    
    @timing_decorator()
    def get_standings(self, league_id):
        cache_key = f"standings_{league_id}"
        cached = self.cache.get(cache_key, data_type='standings')
        if cached is not None: return cached
        try:
            params = {'league': league_id, 'season': datetime.now().year}
            data = self._make_request('/standings', params)
            if data and 'response' in data:
                standings = {}
                for league in data['response']:
                    for standing in league.get('league', {}).get('standings', []):
                        for team in standing:
                            team_name = team.get('team', {}).get('name', '')
                            standings[team_name] = {
                                'position': team.get('rank', 0),
                                'points': team.get('points', 0),
                                'form': team.get('form', ''),
                                'goals_diff': team.get('goalsDiff', 0)
                            }
                self.cache.set(cache_key, standings)
                return standings
        except Exception as e:
            logger.error(f"Ошибка получения таблицы {league_id}: {e}")
        return None
    
    def get_injuries(self, team_id):
        cache_key = f"injuries_{team_id}"
        cached = self.cache.get(cache_key, data_type='default')
        if cached is not None: return cached
        try:
            params = {'team': team_id, 'season': datetime.now().year}
            data = self._make_request('/injuries', params)
            if data and 'response' in data:
                self.cache.set(cache_key, data['response'])
                return data['response']
        except Exception as e:
            logger.error(f"Ошибка получения травм {team_id}: {e}")
        return []
    
    @timing_decorator()
    def get_match_result(self, fixture_id):
        cache_key = f"result_{fixture_id}"
        cached = self.cache.get(cache_key, data_type='default')
        if cached is not None: return cached
        try:
            params = {'id': fixture_id}
            data = self._make_request('/fixtures', params)
            if data and 'response' in data and data['response']:
                fixture = data['response'][0]
                goals = fixture.get('goals', {})
                result = {
                    'goals': {'home': goals.get('home'), 'away': goals.get('away')},
                    'status': fixture.get('status', {}).get('short', 'FT')
                }
                self.cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Ошибка получения результата {fixture_id}: {e}")
        return None
    
    @timing_decorator()
    def get_head_to_head(self, home_team, away_team):
        cache_key = f"h2h_{home_team}_{away_team}"
        cached = self.cache.get(cache_key, data_type='h2h')
        if cached is not None: return cached
        try:
            home_id = self.get_team_id(home_team)
            away_id = self.get_team_id(away_team)
            if home_id and away_id:
                params = {'h2h': f"{home_id}-{away_id}", 'last': 5}
                data = self._make_request('/fixtures/headtohead', params)
                if data and 'response' in data and data['response']:
                    result = {'matches': [], 'home_wins': 0, 'away_wins': 0, 'draws': 0, 'goals_scored': 0, 'goals_conceded': 0}
                    for fixture in data['response']:
                        teams = fixture.get('teams', {})
                        goals = fixture.get('goals', {})
                        home_score = goals.get('home', 0) or 0
                        away_score = goals.get('away', 0) or 0
                        result['matches'].append({
                            'home': teams.get('home', {}).get('name', ''),
                            'away': teams.get('away', {}).get('name', ''),
                            'home_score': home_score, 'away_score': away_score
                        })
                        if home_score > away_score: result['home_wins'] += 1
                        elif home_score < away_score: result['away_wins'] += 1
                        else: result['draws'] += 1
                        result['goals_scored'] += home_score
                        result['goals_conceded'] += away_score
                    if result['matches']:
                        total = len(result['matches'])
                        result['avg_goals'] = round((result['goals_scored'] + result['goals_conceded']) / total, 2)
                        result['home_win_rate'] = round((result['home_wins'] / total) * 100, 1)
                        result['total_matches'] = total
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения H2H: {e}")
        return None
    
    def get_team_id(self, team_name):
        cache_key = f"team_id_{team_name}"
        cached = self.cache.get(cache_key, data_type='default')
        if cached is not None: return cached
        try:
            params = {'name': team_name}
            data = self._make_request('/teams', params)
            if data and 'response' in data:
                for team in data['response']:
                    team_data = team.get('team', {})
                    if team_data.get('name', '').lower() == team_name.lower():
                        team_id = team_data.get('id')
                        self.cache.set(cache_key, team_id)
                        return team_id
        except Exception as e:
            logger.error(f"Ошибка получения ID команды {team_name}: {e}")
        return None
    
    @timing_decorator()
    def get_match_odds(self, fixture_id):
        cache_key = f"odds_{fixture_id}"
        cached = self.cache.get(cache_key, data_type='odds')
        if cached is not None: return cached
        try:
            params = {'fixture': fixture_id}
            data = self._make_request('/fixtures/odds', params)
            if data and 'response' in data and data['response']:
                result = self._extract_best_odds(data['response'])
                self.cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения кэфов {fixture_id}: {e}")
        return None
    
    def _extract_best_odds(self, odds_data):
        result = {'best_odds': 0, 'bookmaker': '—', 'home_odds': 0, 'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0}
        for bookmaker in odds_data:
            bookmaker_name = bookmaker.get('bookmaker', {}).get('name', '—')
            for bet in bookmaker.get('bets', []):
                bet_name = bet.get('name', '').lower()
                values = bet.get('values', [])
                if not values: continue
                if 'матч' in bet_name or 'match' in bet_name or 'побед' in bet_name:
                    for value in values:
                        value_name = value.get('value', '').lower()
                        odd = value.get('odd', 0)
                        if odd <= 0: continue
                        if '1' in value_name or 'home' in value_name:
                            if odd > result['home_odds']: result['home_odds'] = odd
                        elif '2' in value_name or 'away' in value_name:
                            if odd > result['away_odds']: result['away_odds'] = odd
                        elif 'x' in value_name or 'draw' in value_name:
                            if odd > result['draw_odds']: result['draw_odds'] = odd
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bookmaker_name
                if 'тотал' in bet_name or 'total' in bet_name:
                    is_2_5 = any('2.5' in v.get('value', '') for v in values)
                    if not is_2_5: continue
                    for value in values:
                        value_name = value.get('value', '').lower()
                        odd = value.get('odd', 0)
                        if odd <= 0: continue
                        if 'меньше' in value_name or 'under' in value_name:
                            if odd > result['under_odds']: result['under_odds'] = odd
                        elif 'больше' in value_name or 'over' in value_name:
                            if odd > result['over_odds']: result['over_odds'] = odd
        return result
    
    def clear_cache(self):
        self.cache.clear()
        logger.info("🧹 Кэш очищен")
    
    def find_fixture_by_teams(self, home_team, away_team):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            data = self._make_request('/fixtures', {'date': today, 'status': 'FT'})
            if data and 'response' in data:
                for fixture in data['response']:
                    teams = fixture.get('teams', {})
                    home = teams.get('home', {}).get('name', '')
                    away = teams.get('away', {}).get('name', '')
                    if home_team.lower() in home.lower() and away_team.lower() in away.lower():
                        return fixture.get('fixture', {}).get('id')
        except Exception as e:
            logger.error(f"Ошибка поиска матча {home_team} vs {away_team}: {e}")
        return None


football_api = FootballAPI()


# ============================================================
# КЛАСС ODDS API
# ============================================================
class OddsAPIClient:
    def __init__(self, api_key=None):
        from app.config import Config
        self.api_key = api_key or Config.ODDS_API_KEY
        self.base_url = Config.ODDS_API_URL
        self.cache = SmartCache(max_size=200)
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self.rate_limiter = APIRateLimiter(max_requests=50, time_window=60)
        self.retry_manager = RetryManager(max_retries=2, base_delay=0.5)
        logger.info(f"🎯 Odds API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ Odds API КЛЮЧ НЕ НАЙДЕН!")
    
    def _make_request(self, endpoint, params=None):
        try:
            self.rate_limiter.wait_if_needed()
            return self.retry_manager.retry(self._make_request_impl, endpoint, params)
        except Exception as e:
            logger.error(f"❌ Ошибка запроса Odds API: {e}")
            return None
    
    def _make_request_impl(self, endpoint, params=None):
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval - (now - self.last_request_time))
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params['apiKey'] = self.api_key
        response = requests.get(url, params=params, timeout=10)
        self.last_request_time = time.time()
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            time.sleep(int(response.headers.get('Retry-After', 60)))
            raise APIErrorRetry("Odds API rate limit")
        return None
    
    @timing_decorator()
    def get_odds_for_match(self, home_team, away_team, league):
        cache_key = f"odds_{home_team}_{away_team}_{league}"
        cached = self.cache.get(cache_key, data_type='odds')
        if cached is not None: return cached
        try:
            sport_map = {
                'Premier League': 'soccer_epl', 'La Liga': 'soccer_spain_la_liga',
                'Bundesliga': 'soccer_germany_bundesliga', 'Serie A': 'soccer_italy_serie_a',
                'Ligue 1': 'soccer_france_ligue_one',
            }
            sport_key = sport_map.get(league, 'soccer_epl')
            data = self._make_request(f"/sports/{sport_key}/events", {'region': 'eu', 'markets': 'h2h,totals'})
            if data:
                for event in data:
                    event_home = event.get('home_team', '').lower()
                    event_away = event.get('away_team', '').lower()
                    if (home_team.lower() in event_home or event_home in home_team.lower()) and \
                       (away_team.lower() in event_away or event_away in away_team.lower()):
                        result = self._extract_odds(event)
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения коэффициентов: {e}")
        return None
    
    def _extract_odds(self, event):
        result = {'best_odds': 0, 'bookmaker_name': '—', 'home_odds': 0, 'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0}
        for bookmaker in event.get('bookmakers', []):
            bookmaker_key = bookmaker.get('key', '')
            for market in bookmaker.get('markets', []):
                market_key = market.get('key', '')
                for outcome in market.get('outcomes', []):
                    name = outcome.get('name', '')
                    price = outcome.get('price', 0)
                    if market_key == 'h2h':
                        if name == event.get('home_team'): result['home_odds'] = max(result['home_odds'], price)
                        elif name == event.get('away_team'): result['away_odds'] = max(result['away_odds'], price)
                        elif name == 'Draw': result['draw_odds'] = max(result['draw_odds'], price)
                    elif market_key == 'totals' and '2.5' in name:
                        if 'Over' in name: result['over_odds'] = max(result['over_odds'], price)
                        elif 'Under' in name: result['under_odds'] = max(result['under_odds'], price)
                    if price > result['best_odds']:
                        result['best_odds'] = price
                        result['bookmaker_name'] = bookmaker_key
        return result


odds_api = OddsAPIClient()


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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
        logger.error(f"Не удалось отправить ошибку в Telegram: {e}")


def send_telegram(text: str, parse_mode: str = 'HTML'):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': text,
            'parse_mode': parse_mode
        }, timeout=10)
        if response.status_code != 200:
            logger.error(f"❌ Ошибка отправки: {response.text}")
    except Exception as e:
        logger.error(f"❌ Send error: {e}")


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
    headers = ["Дата", "Матч", "Счёт", "Ставка", "Коэф", "EV%", "Сумма", "Результат", "Прибыль", "Букмекер"]
    ws.append(headers)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    total_profit = 0
    for bet in history:
        date = bet.get('date', '')
        home = bet.get('home', '')
        away = bet.get('away', '')
        home_goals = bet.get('home_goals', '')
        away_goals = bet.get('away_goals', '')
        score = f"{home_goals}-{away_goals}" if home_goals is not None and away_goals is not None else "-"
        bet_type = bet.get('bet', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', 0)
        stake = bet.get('stake', 0)
        result = bet.get('result', 'pending')
        profit = bet.get('profit', 0)
        bookmaker = bet.get('bookmaker', '—')
        if result == 'win':
            profit = round(stake * (odds - 1), 2) if profit == 0 else profit
            total_profit += profit
        elif result == 'loss':
            profit = -round(stake, 2) if profit == 0 else profit
            total_profit += profit
        else:
            profit = 0
        ws.append([date, f"{home} vs {away}", score, bet_type, odds, ev, stake, result, profit, bookmaker])
    ws.append([])
    ws.append(["ИТОГО", "", "", "", "", "", "", "", round(total_profit, 2), ""])
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + col)].width = 15
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output, f"✅ Экспорт завершен! Всего ставок: {len(history)}, Прибыль: ${round(total_profit, 2)}"


def get_profit_data(history):
    profits = []
    days = 7
    for i in range(days - 1, -1, -1):
        day_profit = 0
        day = datetime.now() - timedelta(days=i)
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bet_date.date() == day.date():
                    stake = float(bet.get('stake', 0) or 0)
                    odds = float(bet.get('odds', 1) or 1)
                    if bet.get('result') == 'win':
                        day_profit += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= stake
            except:
                pass
        profits.append(round(day_profit, 2))
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}


# ============================================================
# ОСНОВНЫЕ ФУНКЦИИ АНАЛИЗА
# ============================================================
def get_motivation(position):
    if position <= 4: return 'champions_league'
    elif position <= 6: return 'europa_league'
    elif position <= 17: return 'mid_table'
    else: return 'relegation'


def analyze_form(form_string):
    if not form_string: return 'average'
    wins = form_string.count('W')
    if wins >= 4: return 'excellent'
    elif wins >= 3: return 'good'
    elif wins >= 2: return 'average'
    else: return 'poor'


def calculate_poisson_probability(home_xg, away_xg):
    def poisson_prob(avg, goals):
        return (math.exp(-avg) * avg ** goals) / math.factorial(goals)
    home_goals_prob = [poisson_prob(home_xg, i) for i in range(6)]
    away_goals_prob = [poisson_prob(away_xg, i) for i in range(6)]
    prob_home_win = prob_away_win = prob_draw = 0
    prob_1X = prob_X2 = prob_over_2_5 = prob_under_2_5 = prob_btts = 0
    for h_g in range(6):
        for a_g in range(6):
            p = home_goals_prob[h_g] * away_goals_prob[a_g]
            total_goals = h_g + a_g
            if h_g > a_g: prob_home_win += p
            elif h_g < a_g: prob_away_win += p
            else: prob_draw += p
            if h_g >= a_g: prob_1X += p
            if a_g >= h_g: prob_X2 += p
            if total_goals > 2.5: prob_over_2_5 += p
            else: prob_under_2_5 += p
            if h_g > 0 and a_g > 0: prob_btts += p
    return {
        'home_win': prob_home_win, 'away_win': prob_away_win, 'draw': prob_draw,
        '1X': prob_1X, 'X2': prob_X2, 'over_2_5': prob_over_2_5,
        'under_2_5': prob_under_2_5, 'btts': prob_btts
    }


def calculate_form_probability(home_form, away_form):
    home_form_quality = analyze_form(home_form)
    away_form_quality = analyze_form(away_form)
    prob = {
        'home_win': 0.35, 'away_win': 0.30, 'draw': 0.35,
        '1X': 0.70, 'X2': 0.65, 'over_2_5': 0.45,
        'under_2_5': 0.55, 'btts': 0.45
    }
    if home_form_quality == 'excellent' and away_form_quality == 'poor':
        prob['home_win'] += 0.15
        prob['1X'] += 0.10
        prob['away_win'] -= 0.10
        prob['X2'] -= 0.10
    elif home_form_quality == 'poor' and away_form_quality == 'excellent':
        prob['away_win'] += 0.15
        prob['X2'] += 0.10
        prob['home_win'] -= 0.10
        prob['1X'] -= 0.10
    return prob


def calculate_h2h_probability(h2h_data):
    prob = {
        'home_win': 0.33, 'away_win': 0.33, 'draw': 0.34,
        '1X': 0.67, 'X2': 0.67, 'over_2_5': 0.50,
        'under_2_5': 0.50, 'btts': 0.50
    }
    if h2h_data:
        total = h2h_data.get('total_matches', 0)
        if total > 0:
            home_wins = h2h_data.get('home_wins', 0) / total
            away_wins = h2h_data.get('away_wins', 0) / total
            draws = h2h_data.get('draws', 0) / total
            prob['home_win'] = home_wins * 0.5 + 0.25
            prob['away_win'] = away_wins * 0.5 + 0.25
            prob['draw'] = draws * 0.5 + 0.25
            prob['1X'] = prob['home_win'] + prob['draw']
            prob['X2'] = prob['away_win'] + prob['draw']
            avg_goals = h2h_data.get('avg_goals', 2.5)
            if avg_goals > 2.5:
                prob['over_2_5'] = 0.55
                prob['under_2_5'] = 0.45
            else:
                prob['over_2_5'] = 0.45
                prob['under_2_5'] = 0.55
    return prob


def ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data):
    poisson = calculate_poisson_probability(home_xg, away_xg)
    form_prob = calculate_form_probability(home_form, away_form)
    h2h_prob = calculate_h2h_probability(h2h_data)
    final_prob = {
        'home_win': poisson['home_win'] * 0.5 + form_prob['home_win'] * 0.3 + h2h_prob['home_win'] * 0.2,
        'away_win': poisson['away_win'] * 0.5 + form_prob['away_win'] * 0.3 + h2h_prob['away_win'] * 0.2,
        'draw': poisson['draw'] * 0.5 + form_prob['draw'] * 0.3 + h2h_prob['draw'] * 0.2,
        '1X': poisson['1X'] * 0.5 + form_prob['1X'] * 0.3 + h2h_prob['1X'] * 0.2,
        'X2': poisson['X2'] * 0.5 + form_prob['X2'] * 0.3 + h2h_prob['X2'] * 0.2,
        'over_2_5': poisson['over_2_5'] * 0.5 + form_prob['over_2_5'] * 0.3 + h2h_prob['over_2_5'] * 0.2,
        'under_2_5': poisson['under_2_5'] * 0.5 + form_prob['under_2_5'] * 0.3 + h2h_prob['under_2_5'] * 0.2,
        'btts': poisson['btts'] * 0.5 + form_prob['btts'] * 0.3 + h2h_prob['btts'] * 0.2
    }
    total_win_prob = final_prob['home_win'] + final_prob['draw'] + final_prob['away_win']
    if total_win_prob > 0:
        final_prob['home_win'] /= total_win_prob
        final_prob['away_win'] /= total_win_prob
        final_prob['draw'] /= total_win_prob
        final_prob['1X'] = final_prob['home_win'] + final_prob['draw']
        final_prob['X2'] = final_prob['away_win'] + final_prob['draw']
    return final_prob


# ============================================================
# ПОИСК МАТЧЕЙ
# ============================================================
def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"🔍 Поиск матчей на: {today}")
    all_leagues = Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])
    logger.info(f"📊 Всего соревнований: {len(all_leagues)}")
    for league_id in all_leagues:
        try:
            matches = football_api.get_matches(league_id, today)
            league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
            if not matches or not isinstance(matches, list):
                continue
            for match in matches:
                if not isinstance(match, dict): continue
                fixture = match.get("fixture")
                if not fixture or not isinstance(fixture, dict): continue
                status = fixture.get("status", {})
                if not isinstance(status, dict): continue
                if status.get("short") == "NS":
                    match_id = fixture.get("id")
                    if not match_id: continue
                    existing_ids = [m.get("fixture", {}).get("id") for m in all_matches if isinstance(m, dict)]
                    if match_id in existing_ids: continue
                    teams = match.get("teams", {})
                    if not isinstance(teams, dict): continue
                    home_team = teams.get("home", {})
                    away_team = teams.get("away", {})
                    if not isinstance(home_team, dict) or not isinstance(away_team, dict): continue
                    home_id = home_team.get("id")
                    away_id = away_team.get("id")
                    if not home_id or not away_id: continue
                    match["factors"] = {
                        "home_form": football_api.get_form(home_id),
                        "away_form": football_api.get_form(away_id),
                        "home_injuries_list": football_api.get_injuries(home_id),
                        "away_injuries_list": football_api.get_injuries(away_id),
                        "home_id": home_id, "away_id": away_id,
                        "referee": fixture.get("referee")
                    }
                    match["weather"] = None
                    league_data = match.get("league", {})
                    if isinstance(league_data, dict):
                        league_data["name"] = league_name
                    all_matches.append(match)
        except Exception as e:
            logger.error(f"❌ Ошибка {league_id}: {e}")
        time.sleep(0.1)
    logger.info(f"📊 ВСЕГО найдено матчей: {len(all_matches)}")
    return all_matches


# ============================================================
# ПОИСК X2 МАТЧЕЙ (ГЛАВНОЕ!)
# ============================================================
def find_x2_matches(matches):
    """
    Ищет матчи для X2 стратегии:
    - Фаворит (mid_table, нет мотивации)
    - Аутсайдер (relegation, борется)
    
    Пишет результаты в matches_log.txt в формате X2_MATCH
    Возвращает список найденных X2 матчей
    """
    logger.info("=" * 60)
    logger.info("🎯 ПОИСК X2 МАТЧЕЙ (фаворит mid_table + аутсайдер relegation)")
    logger.info("=" * 60)
    
    x2_candidates = []
    
    for match in matches:
        if not match or not isinstance(match, dict): continue
        try:
            fixture = match.get("fixture")
            if not fixture or not isinstance(fixture, dict): continue
            fixture_id = fixture.get("id")
            teams = match.get("teams")
            if not teams or not isinstance(teams, dict): continue
            home_team = teams.get("home")
            away_team = teams.get("away")
            if not isinstance(home_team, dict) or not isinstance(away_team, dict): continue
            
            home = home_team.get("name", "Unknown")
            away = away_team.get("name", "Unknown")
            
            league_data = match.get("league")
            league_name = league_data.get('name', 'Unknown') if isinstance(league_data, dict) else "Unknown"
            league_id = league_data.get('id') if isinstance(league_data, dict) else None
            
            match_time = fixture.get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            # Получаем таблицу
            standings = football_api.get_standings(league_id) if league_id else None
            home_position = 99
            away_position = 99
            if standings:
                if home in standings: home_position = standings[home].get('position', 99)
                if away in standings: away_position = standings[away].get('position', 99)
            
            home_motivation = get_motivation(home_position)
            away_motivation = get_motivation(away_position)
            
            # === X2 УСЛОВИЕ ===
            is_x2 = False
            favorite = None
            underdog = None
            
            # Вариант 1: хозяева — фаворит (mid_table), гости — аутсайдер (relegation)
            if home_motivation == 'mid_table' and away_motivation == 'relegation':
                is_x2 = True
                favorite = home
                underdog = away
            # Вариант 2: гости — фаворит (mid_table), хозяева — аутсайдер (relegation)
            elif away_motivation == 'mid_table' and home_motivation == 'relegation':
                is_x2 = True
                favorite = away
                underdog = home
            
            if not is_x2:
                continue
            
            # Считаем XG
            home_form_data = football_api.get_form(home_team.get("id"))
            away_form_data = football_api.get_form(away_team.get("id"))
            home_goals_avg = home_form_data.get('goals_avg', 1.2) if home_form_data else 1.2
            away_goals_avg = away_form_data.get('goals_avg', 1.0) if away_form_data else 1.0
            home_conceded_avg = home_form_data.get('conceded_avg', 1.0) if home_form_data else 1.0
            away_conceded_avg = away_form_data.get('conceded_avg', 1.2) if away_form_data else 1.2
            home_xg = (home_goals_avg + away_conceded_avg) / 2
            away_xg = (away_goals_avg + home_conceded_avg) / 2
            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            total_xg = home_xg + away_xg
            
            # Получаем кэф X2 (ставим на аутсайдера X2)
            odds_x2 = 1.85  # заглушка
            try:
                odds_data = football_api.get_match_odds(fixture_id)
                if odds_data and odds_data.get('best_odds', 0) > 0:
                    if favorite == home and odds_data.get('away_odds', 0) > 0:
                        odds_x2 = odds_data['away_odds']
                    elif favorite == away and odds_data.get('home_odds', 0) > 0:
                        odds_x2 = odds_data['home_odds']
            except:
                pass
            
            note = f"Фаворит {favorite} — нет мотивации (#{home_position if favorite == home else away_position}), аутсайдер {underdog} борется (#{away_position if favorite == home else home_position})"
            
            # Пишем в лог
            log_x2_match(
                home=home,
                away=away,
                favorite=favorite,
                underdog=underdog,
                odds=odds_x2,
                xg=round(total_xg, 2),
                note=note
            )
            
            x2_candidates.append({
                'home': home, 'away': away,
                'favorite': favorite, 'underdog': underdog,
                'odds': odds_x2, 'total_xg': round(total_xg, 2),
                'league': league_name, 'match_time': match_time,
                'note': note
            })
            
            logger.info(f"🎯 X2 НАЙДЕН: {home} vs {away} | Фаворит: {favorite} | Аутсайдер: {underdog} | XG: {total_xg:.2f}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска X2: {e}")
            continue
    
    logger.info(f"📊 Найдено X2 матчей: {len(x2_candidates)}")
    return x2_candidates


# ============================================================
# ОСТАЛЬНЫЕ ФУНКЦИИ (упрощённые)
# ============================================================
def update_manual_result(match_name, score):
    try:
        home_goals = away_goals = None
        if score and '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0].strip())
                away_goals = int(parts[1].strip())
            except:
                return "❌ Неверный формат счета"
        history = storage.load_history()
        for bet in history:
            if bet.get('result') == 'pending':
                full_match = f"{bet.get('home', '')} vs {bet.get('away', '')}"
                if match_name.lower() in full_match.lower():
                    bet['home_goals'] = home_goals
                    bet['away_goals'] = away_goals
                    result = determine_bet_result(bet.get('bet', ''), home_goals, away_goals)
                    bet['result'] = result
                    if result == 'win':
                        bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                    elif result == 'loss':
                        bet['profit'] = -bet['stake']
                    else:
                        bet['profit'] = 0
                    storage.save_history(history)
                    recalc_stats()
                    return f"✅ Обновлено: {full_match} → {result}"
        return f"❌ Матч не найден"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def determine_bet_result(bet_type, home_goals, away_goals):
    total = home_goals + away_goals
    bt = bet_type.lower()
    if 'п1' in bt: return 'win' if home_goals > away_goals else ('push' if home_goals == away_goals else 'loss')
    elif 'п2' in bt: return 'win' if away_goals > home_goals else ('push' if home_goals == away_goals else 'loss')
    elif '1x' in bt: return 'win' if home_goals >= away_goals else 'loss'
    elif 'x2' in bt: return 'win' if away_goals >= home_goals else 'loss'
    elif 'обз' in bt or 'btts' in bt: return 'win' if home_goals > 0 and away_goals > 0 else 'loss'
    elif 'тм 2.5' in bt or 'under' in bt: return 'win' if total < 2.5 else 'loss'
    elif 'тб 2.5' in bt or 'over' in bt: return 'win' if total > 2.5 else 'loss'
    return 'pending'


def update_pending_bets():
    history = storage.load_history()
    updated = 0
    for bet in history:
        if bet.get('result') == 'pending':
            fixture_id = bet.get('fixture_id')
            if fixture_id:
                match_data = football_api.get_match_result(fixture_id)
                if match_data:
                    home_goals = match_data['goals']['home']
                    away_goals = match_data['goals']['away']
                    if home_goals is not None and away_goals is not None:
                        result = determine_bet_result(bet.get('bet', ''), home_goals, away_goals)
                        if result != 'pending':
                            bet['result'] = result
                            bet['home_goals'] = home_goals
                            bet['away_goals'] = away_goals
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
    total_profit = sum(b.get('profit', 0) for b in history)
    total_stake = sum(b.get('stake', 0) for b in history)
    stats.update({
        'total': total, 'wins': wins, 'losses': losses, 'pushes': pushes,
        'total_profit': round(total_profit, 2),
        'winrate': round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
        'roi': round((total_profit / total_stake * 100), 1) if total_stake > 0 else 0
    })
    storage.save_stats(stats)


FootballAPI.find_fixture_by_teams = FootballAPI.find_fixture_by_teams


# ============================================================
# ПЛАНИРОВЩИК
# ============================================================
def schedule_updates():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=auto_update_results, trigger='interval', hours=6, id='auto_update', replace_existing=True)
    scheduler.start()
    logger.info("⏰ Авто-обновление результатов запущено")


def auto_update_results():
    try:
        updated = update_pending_bets()
        if updated > 0:
            send_telegram(f"🔄 Обновлено {updated} результатов!")
    except Exception as e:
        logger.error(f"❌ Ошибка авто-обновления: {e}")


# ============================================================
# FLASK WEBHOOK
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running, search_state
    try:
        data = request.get_json()
        if not data: return "ok", 200
        
        if 'callback_query' in data:
            try:
                requests.post(f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery", 
                    json={"callback_query_id": data['callback_query'].get('id', ''), "text": "✅"})
            except: pass
            return "ok", 200
        
        if 'message' not in data: return "ok", 200
        message = data['message']
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        if str(chat_id) != str(Config.ADMIN_CHAT_ID):
            return "ok", 200
        
        if text == '/start':
            send_telegram(handlers.handle_start())
        elif text == '/help':
            send_telegram(handlers.handle_help())
        elif text == '/update':
            if search_running:
                send_telegram("⚠️ Поиск уже запущен!")
                return "ok", 200
            search_running = True
            search_state = {'start_time': datetime.now()}
            send_telegram("🔎 Запущен анализ. Это займёт 10-20 минут...")
            
            def run_full_search():
                global search_running, search_state
                try:
                    start_time = datetime.now()
                    
                    # Очищаем X2 лог перед новым поиском
                    clear_x2_log()
                    
                    # Ищем матчи
                    matches = get_matches_with_factors()
                    
                    if matches:
                        # Ищем X2 матчи
                        x2_matches = find_x2_matches(matches)
                        
                        if x2_matches:
                            elapsed = (datetime.now() - start_time).seconds
                            minutes = elapsed // 60
                            seconds = elapsed % 60
                            
                            msg = f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                            msg += f"🎯 X2 матчей: {len(x2_matches)}\n"
                            msg += f"⏱️ Время: {minutes} мин {seconds} сек.\n\n"
                            msg += "📋 <b>X2 МАТЧИ:</b>\n\n"
                            
                            for i, m in enumerate(x2_matches[:15], 1):
                                msg += f"{i}. <b>{m['home']} vs {m['away']}</b>\n"
                                msg += f"   🎯 Фаворит: {m['favorite']} | Аутсайдер: {m['underdog']}\n"
                                msg += f"   ⚽ XG: {m['total_xg']}\n\n"
                            
                            send_telegram(msg)
                        else:
                            send_telegram("❌ X2 матчей не найдено.")
                    else:
                        send_telegram("❌ Матчей не найдено.")
                except Exception as e:
                    logger.error(f"❌ Ошибка поиска: {e}", exc_info=True)
                finally:
                    search_running = False
                    search_state = {}
            
            t = Thread(target=run_full_search)
            t.daemon = True
            t.start()
        
        elif text == '/stats':
            stats = storage.load_stats()
            bank = storage.load_bank()
            msg = f"📊 <b>СТАТИСТИКА</b>\n\n💰 Банк: ${bank:.2f}\n"
            msg += f"📊 Всего: {stats.get('total', 0)}\n✅ Побед: {stats.get('wins', 0)}\n"
            msg += f"❌ Поражений: {stats.get('losses', 0)}\n📈 Винрейт: {stats.get('winrate', 0)}%\n"
            msg += f"💰 Прибыль: ${stats.get('total_profit', 0):.2f}"
            send_telegram(msg)
        
        elif text.startswith('/result'):
            parts = text.replace('/result', '').strip()
            if ' vs ' in parts and ' ' in parts.split(' vs ')[-1]:
                home_away = parts.rsplit(' ', 1)
                result = update_manual_result(home_away[0], home_away[1])
                send_telegram(result)
            else:
                send_telegram("⚠️ /result Home vs Away 2-1")
        
        elif text == '/stop':
            search_running = False
            search_state = {}
            send_telegram("⏹️ Остановлено")
        
        else:
            send_telegram("❌ Неизвестная команда")
        
        return "ok", 200
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return "ok", 200


# ============================================================
# API ЭНДПОИНТЫ
# ============================================================

@app.route('/api/x2_matches', methods=['GET'])
def api_x2_matches():
    """
    Читает matches_log.txt, парсит строки X2_MATCH, возвращает список матчей.
    """
    try:
        x2_matches = []
        seen = set()
        
        if os.path.exists(X2_LOG_FILE):
            with open(X2_LOG_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            logger.info(f"📖 Читаем {X2_LOG_FILE}: {len(content)} символов")
            
            for line in content.split('\n'):
                if not line.startswith('X2_MATCH:'): continue
                
                try:
                    parts = line.replace('X2_MATCH:', '').strip().split('|')
                    match_part = parts[0].strip()
                    if ' vs ' not in match_part: continue
                    
                    home, away = [x.strip() for x in match_part.split(' vs ', 1)]
                    
                    favorite = underdog = note = date_raw = ''
                    odds = xg = 0.0
                    
                    for part in parts[1:]:
                        if ':' not in part: continue
                        k, v = part.split(':', 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k == 'favorite': favorite = v
                        elif k == 'underdog': underdog = v
                        elif k == 'odds':
                            try: odds = float(v)
                            except: pass
                        elif k == 'xg':
                            try: xg = float(v)
                            except: pass
                        elif k == 'note': note = v
                        elif k == 'date': date_raw = v
                    
                    key = f"{match_part}_{date_raw}"
                    if key in seen: continue
                    seen.add(key)
                    
                    date_str = datetime.now().strftime('%Y-%m-%d')
                    if date_raw:
                        try:
                            dt = datetime.strptime(date_raw, '%Y-%m-%d %H:%M')
                            date_str = dt.strftime('%Y-%m-%d')
                        except: pass
                    
                    x2_matches.append({
                        'date': date_str,
                        'match': match_part,
                        'favorite': favorite or home,
                        'underdog': underdog or away,
                        'odds': odds,
                        'stake': 42.87,
                        'score': '-',
                        'result': 'pending',
                        'note': note or f"XG: {xg}"
                    })
                except Exception as e:
                    logger.error(f"Ошибка парсинга X2: {e}")
                    continue
        
        x2_matches.sort(key=lambda m: m['date'], reverse=True)
        
        logger.info(f"✅ X2 матчей в логе: {len(x2_matches)}")
        
        return jsonify({
            'success': True,
            'log': '',
            'x2_matches': x2_matches,
            'count': len(x2_matches),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ Ошибка /api/x2_matches: {e}")
        return jsonify({'success': False, 'error': str(e), 'x2_matches': []}), 500


@app.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify({'bank': storage.load_bank(), **storage.load_stats()})


@app.route('/api/history', methods=['GET'])
def api_history():
    return jsonify(storage.load_history())


@app.route('/api/matches', methods=['GET'])
def api_matches():
    return jsonify(storage.load_cache().get('top_matches', []))


@app.route('/api/all_data', methods=['GET'])
def all_data():
    try:
        stats = storage.load_stats()
        bank = storage.load_bank()
        history = storage.load_history()
        cache = storage.load_cache()
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
            'profit_data': get_profit_data(history),
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
        return jsonify({'error': 'No bank'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        if index >= len(history): return jsonify({'error': 'Not found'}), 404
        for k in ['home', 'away', 'home_goals', 'away_goals', 'bet', 'odds', 'stake', 'ev', 'result', 'bookmaker']:
            if k in data:
                history[index][k] = data[k]
        if history[index]['result'] == 'win':
            history[index]['profit'] = round(history[index]['stake'] * (history[index]['odds'] - 1), 2)
        elif history[index]['result'] == 'loss':
            history[index]['profit'] = -history[index]['stake']
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
        if index >= len(history): return jsonify({'error': 'Not found'}), 404
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
        if not match_name: return jsonify({'error': 'No match'}), 400
        score = data.get('score', '-')
        result = data.get('result', 'win')
        stake = data.get('stake', 0)
        odds = data.get('odds', 1.85)
        home, away = 'Unknown', 'Unknown'
        if ' vs ' in match_name:
            home, away = [x.strip() for x in match_name.split(' vs ', 1)]
        if result == 'win': profit = round(stake * (odds - 1), 2)
        elif result == 'loss': profit = -stake
        else: profit = 0
        history = storage.load_history()
        history.append({
            'home': home, 'away': away, 'bet': data.get('bet', ''),
            'odds': odds, 'stake': stake, 'result': result, 'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'bookmaker': data.get('bookmaker', 'Manual')
        })
        storage.save_history(history)
        recalc_stats()
        return jsonify({'success': True, 'count': 1})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    return jsonify({'success': True, 'count': 0})


@app.route('/api/import_project', methods=['POST'])
def import_project():
    return jsonify({'success': True, 'count': 0})


@app.route('/api/simulate', methods=['POST'])
def simulate():
    return jsonify({'error': 'Not available'}), 501


@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    try:
        data = request.json
        with open('bot_settings.json', 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keepalive', methods=['GET'])
def keepalive():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


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
    start_scheduler()
    schedule_updates()
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"📋 X2 матчи: /api/x2_matches")
    app.run(host='0.0.0.0', port=port)
