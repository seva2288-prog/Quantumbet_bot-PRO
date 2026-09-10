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
# X2 ЛОГ
# ============================================================
def log_x2_match(home, away, favorite, underdog, odds, xg, note=""):
    """Пишет X2 матч в matches_log.txt"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        line = f"X2_MATCH: {home} vs {away} | favorite: {favorite} | underdog: {underdog} | odds: {odds} | xg: {xg} | note: {note} | date: {timestamp}\n"
        with open(X2_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line)
        logger.info(f"📝 X2 матч записан: {home} vs {away}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи X2: {e}")


def clear_x2_log():
    """Очищает лог X2"""
    try:
        with open(X2_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("")
        logger.info("🧹 X2 лог очищен")
    except Exception as e:
        logger.error(f"❌ Ошибка очистки: {e}")


# ============================================================
# МОНИТОРИНГ
# ============================================================
class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(lambda: {'calls': 0, 'total_time': 0, 'max_time': 0, 'min_time': float('inf'), 'errors': 0})
        self.lock = Lock()
    
    def record(self, func_name, elapsed, error=False):
        with self.lock:
            m = self.metrics[func_name]
            m['calls'] += 1
            m['total_time'] += elapsed
            m['max_time'] = max(m['max_time'], elapsed)
            m['min_time'] = min(m['min_time'], elapsed)
            if error: m['errors'] += 1
    
    def get_report(self):
        report = []
        for func_name, m in sorted(self.metrics.items()):
            avg = m['total_time'] / m['calls'] if m['calls'] > 0 else 0
            err = m['errors'] / m['calls'] * 100 if m['calls'] > 0 else 0
            report.append({'function': func_name, 'calls': m['calls'], 'avg_time': round(avg, 3),
                          'max_time': round(m['max_time'], 3), 'min_time': round(m['min_time'], 3),
                          'error_rate': round(err, 1), 'total_time': round(m['total_time'], 3)})
        return report
    
    def print_report(self):
        for item in self.get_report():
            status = "✅" if item['error_rate'] < 5 else "⚠️"
            logger.info(f"{status} {item['function']}: {item['calls']} выз, ср {item['avg_time']}с")

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
                if elapsed > 5.0:
                    logger.error(f"🐌 {fn}: {elapsed:.2f}с")
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
        self.ttl_by_type = {'form': 300, 'odds': 60, 'statistics': 300, 'standings': 1800, 'matches': 3600, 'h2h': 7200}
    
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
                self.hit_count.pop(key, None)
                self.last_access.pop(key, None)
        return None
    
    def set(self, key, value):
        if len(self.cache) >= self.max_size:
            to_remove = min(self.cache.keys(), key=lambda k: (self.hit_count.get(k, 0), self.last_access.get(k, 0)))
            del self.cache[to_remove]
            for d in [self.hit_count, self.last_access, self.cache_timestamps]:
                d.pop(to_remove, None)
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
                st = self.time_window - (now - self.requests[0])
                if st > 0:
                    time.sleep(st + 1)
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
                    raise APIErrorFatal(f"Превышено попыток: {e}")
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                time.sleep(delay + random.uniform(0, delay * 0.1))
            except APIErrorFatal:
                raise
            except Exception as e:
                raise APIErrorFatal(f"Ошибка: {e}")


# ============================================================
# FOOTBALL API
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
    
    def _make_request(self, endpoint, params=None):
        try:
            self.rate_limiter.wait_if_needed()
            return self.retry_manager.retry(self._make_request_impl, endpoint, params)
        except APIErrorFatal as e:
            logger.error(f"❌ API fatal: {e}")
            self.error_stats['fatal'] += 1
            return None
        except Exception as e:
            logger.error(f"❌ API: {e}")
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
                time.sleep(int(response.headers.get('Retry-After', 60)))
                raise APIErrorRetry("Rate limit")
            if response.status_code == 403:
                raise APIErrorFatal("Неверный ключ")
            if response.status_code != 200:
                if response.status_code >= 500:
                    raise APIErrorRetry(f"Сервер {response.status_code}")
                raise APIErrorFatal(f"API {response.status_code}")
            data = response.json()
            if data.get('errors'):
                em = data['errors']
                if 'rate limit' in str(em).lower():
                    raise APIErrorRetry("Rate limit в ответе")
                elif 'api key' in str(em).lower():
                    raise APIErrorFatal(f"Ключ: {em}")
                return None
            return data
        except requests.exceptions.Timeout:
            raise APIErrorRetry("Timeout")
        except requests.exceptions.ConnectionError:
            raise APIErrorRetry("Connection")
        except json.JSONDecodeError as e:
            raise APIErrorFatal(f"JSON: {e}")
    
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
                    gs, gc = [], []
                    w = d = l = 0
                    for match in matches:
                        goals = match.get('goals', {})
                        teams = match.get('teams', {})
                        if teams.get('home', {}).get('id') == team_id:
                            scored = goals.get('home', 0) or 0
                            conceded = goals.get('away', 0) or 0
                        else:
                            scored = goals.get('away', 0) or 0
                            conceded = goals.get('home', 0) or 0
                        gs.append(scored)
                        gc.append(conceded)
                        if scored > conceded: w += 1
                        elif scored == conceded: d += 1
                        else: l += 1
                    if gs:
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
        for match in matches:
            teams = match.get('teams', {})
            goals = match.get('goals', {})
            hs = goals.get('home', 0) or 0
            aws = goals.get('away', 0) or 0
            if teams.get('home', {}).get('id') == team_id:
                if hs > aws: form.append('W')
                elif hs == aws: form.append('D')
                else: form.append('L')
            else:
                if aws > hs: form.append('W')
                elif aws == hs: form.append('D')
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
        cached = self.cache.get(cache_key, data_type='default')
        if cached is not None: return cached
        try:
            params = {'team': team_id, 'season': datetime.now().year}
            data = self._make_request('/injuries', params)
            if data and 'response' in data:
                self.cache.set(cache_key, data['response'])
                return data['response']
        except:
            pass
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
                result = {'goals': {'home': goals.get('home'), 'away': goals.get('away')},
                         'status': fixture.get('status', {}).get('short', 'FT')}
                self.cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Ошибка результата {fixture_id}: {e}")
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
                        hs = goals.get('home', 0) or 0
                        aws = goals.get('away', 0) or 0
                        result['matches'].append({'home': teams.get('home', {}).get('name', ''),
                                                  'away': teams.get('away', {}).get('name', ''),
                                                  'home_score': hs, 'away_score': aws})
                        if hs > aws: result['home_wins'] += 1
                        elif hs < aws: result['away_wins'] += 1
                        else: result['draws'] += 1
                        result['goals_scored'] += hs
                        result['goals_conceded'] += aws
                    if result['matches']:
                        tm = len(result['matches'])
                        result['avg_goals'] = round((result['goals_scored'] + result['goals_conceded']) / tm, 2)
                        result['home_win_rate'] = round((result['home_wins'] / tm) * 100, 1)
                        result['total_matches'] = tm
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"Ошибка H2H: {e}")
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
                    td = team.get('team', {})
                    if td.get('name', '').lower() == team_name.lower():
                        tid = td.get('id')
                        self.cache.set(cache_key, tid)
                        return tid
        except:
            pass
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
            logger.error(f"Ошибка кэфов {fixture_id}: {e}")
        return None
    
    def _extract_best_odds(self, odds_data):
        result = {'best_odds': 0, 'bookmaker': '—', 'home_odds': 0, 'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0}
        for bm in odds_data:
            bm_name = bm.get('bookmaker', {}).get('name', '—')
            for bet in bm.get('bets', []):
                bn = bet.get('name', '').lower()
                vals = bet.get('values', [])
                if not vals: continue
                if 'матч' in bn or 'match' in bn or 'побед' in bn:
                    for v in vals:
                        vn = v.get('value', '').lower()
                        odd = v.get('odd', 0)
                        if odd <= 0: continue
                        if '1' in vn or 'home' in vn:
                            result['home_odds'] = max(result['home_odds'], odd)
                        elif '2' in vn or 'away' in vn:
                            result['away_odds'] = max(result['away_odds'], odd)
                        elif 'x' in vn or 'draw' in vn:
                            result['draw_odds'] = max(result['draw_odds'], odd)
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bm_name
        return result
    
    def find_fixture_by_teams(self, home_team, away_team):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            data = self._make_request('/fixtures', {'date': today, 'status': 'FT'})
            if data and 'response' in data:
                for fx in data['response']:
                    teams = fx.get('teams', {})
                    h = teams.get('home', {}).get('name', '')
                    a = teams.get('away', {}).get('name', '')
                    if home_team.lower() in h.lower() and away_team.lower() in a.lower():
                        return fx.get('fixture', {}).get('id')
        except:
            pass
        return None


football_api = FootballAPI()


# ============================================================
# ODDS API
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
    
    def _make_request(self, endpoint, params=None):
        try:
            self.rate_limiter.wait_if_needed()
            return self.retry_manager.retry(self._make_request_impl, endpoint, params)
        except:
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
            raise APIErrorRetry("Odds rate limit")
        return None
    
    @timing_decorator()
    def get_odds_for_match(self, home_team, away_team, league):
        cache_key = f"odds_{home_team}_{away_team}_{league}"
        cached = self.cache.get(cache_key, data_type='odds')
        if cached is not None: return cached
        try:
            sm = {'Premier League': 'soccer_epl', 'La Liga': 'soccer_spain_la_liga',
                  'Bundesliga': 'soccer_germany_bundesliga', 'Serie A': 'soccer_italy_serie_a',
                  'Ligue 1': 'soccer_france_ligue_one'}
            sk = sm.get(league, 'soccer_epl')
            data = self._make_request(f"/sports/{sk}/events", {'region': 'eu', 'markets': 'h2h,totals'})
            if data:
                for event in data:
                    eh = event.get('home_team', '').lower()
                    ea = event.get('away_team', '').lower()
                    if (home_team.lower() in eh or eh in home_team.lower()) and \
                       (away_team.lower() in ea or ea in away_team.lower()):
                        result = self._extract_odds(event)
                        self.cache.set(cache_key, result)
                        return result
        except Exception as e:
            logger.error(f"❌ Odds API: {e}")
        return None
    
    def _extract_odds(self, event):
        result = {'best_odds': 0, 'bookmaker_name': '—', 'home_odds': 0, 'draw_odds': 0,
                  'away_odds': 0, 'under_odds': 0, 'over_odds': 0}
        for bm in event.get('bookmakers', []):
            bk = bm.get('key', '')
            for market in bm.get('markets', []):
                mk = market.get('key', '')
                for oc in market.get('outcomes', []):
                    name = oc.get('name', '')
                    price = oc.get('price', 0)
                    if mk == 'h2h':
                        if name == event.get('home_team'): result['home_odds'] = max(result['home_odds'], price)
                        elif name == event.get('away_team'): result['away_odds'] = max(result['away_odds'], price)
                        elif name == 'Draw': result['draw_odds'] = max(result['draw_odds'], price)
                    elif mk == 'totals' and '2.5' in name:
                        if 'Over' in name: result['over_odds'] = max(result['over_odds'], price)
                        elif 'Under' in name: result['under_odds'] = max(result['under_odds'], price)
                    if price > result['best_odds']:
                        result['best_odds'] = price
                        result['bookmaker_name'] = bk
        return result


odds_api = OddsAPIClient()


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ
# ============================================================
def send_telegram(text: str, parse_mode: str = 'HTML'):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': Config.ADMIN_CHAT_ID, 'text': text, 'parse_mode': parse_mode}, timeout=10)
    except Exception as e:
        logger.error(f"❌ Send: {e}")


def get_profit_data(history):
    profits = []
    days = 7
    for i in range(days - 1, -1, -1):
        dp = 0
        day = datetime.now() - timedelta(days=i)
        for bet in history:
            try:
                bd = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bd.date() == day.date():
                    stake = float(bet.get('stake', 0) or 0)
                    odds = float(bet.get('odds', 1) or 1)
                    if bet.get('result') == 'win':
                        dp += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        dp -= stake
            except:
                pass
        profits.append(round(dp, 2))
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}


# ============================================================
# АНАЛИЗ
# ============================================================
def get_motivation(position):
    if position <= 4: return 'champions_league'
    elif position <= 6: return 'europa_league'
    elif position <= 17: return 'mid_table'
    else: return 'relegation'


def analyze_form(form_string):
    if not form_string: return 'average'
    w = form_string.count('W')
    if w >= 4: return 'excellent'
    elif w >= 3: return 'good'
    elif w >= 2: return 'average'
    else: return 'poor'


def calculate_poisson_probability(home_xg, away_xg):
    def pp(avg, goals):
        return (math.exp(-avg) * avg ** goals) / math.factorial(goals)
    hgp = [pp(home_xg, i) for i in range(6)]
    agp = [pp(away_xg, i) for i in range(6)]
    phw = paw = pd = p1x = px2 = po = pu = pb = 0
    for hg in range(6):
        for ag in range(6):
            p = hgp[hg] * agp[ag]
            tg = hg + ag
            if hg > ag: phw += p
            elif hg < ag: paw += p
            else: pd += p
            if hg >= ag: p1x += p
            if ag >= hg: px2 += p
            if tg > 2.5: po += p
            else: pu += p
            if hg > 0 and ag > 0: pb += p
    return {'home_win': phw, 'away_win': paw, 'draw': pd, '1X': p1x, 'X2': px2,
            'over_2_5': po, 'under_2_5': pu, 'btts': pb}


def calculate_form_probability(home_form, away_form):
    hq = analyze_form(home_form)
    aq = analyze_form(away_form)
    prob = {'home_win': 0.35, 'away_win': 0.30, 'draw': 0.35, '1X': 0.70, 'X2': 0.65,
            'over_2_5': 0.45, 'under_2_5': 0.55, 'btts': 0.45}
    if hq == 'excellent' and aq == 'poor':
        prob['home_win'] += 0.15
        prob['1X'] += 0.10
        prob['away_win'] -= 0.10
        prob['X2'] -= 0.10
    elif hq == 'poor' and aq == 'excellent':
        prob['away_win'] += 0.15
        prob['X2'] += 0.10
        prob['home_win'] -= 0.10
        prob['1X'] -= 0.10
    return prob


def calculate_h2h_probability(h2h_data):
    prob = {'home_win': 0.33, 'away_win': 0.33, 'draw': 0.34, '1X': 0.67, 'X2': 0.67,
            'over_2_5': 0.50, 'under_2_5': 0.50, 'btts': 0.50}
    if h2h_data:
        total = h2h_data.get('total_matches', 0)
        if total > 0:
            hw = h2h_data.get('home_wins', 0) / total
            aw = h2h_data.get('away_wins', 0) / total
            d = h2h_data.get('draws', 0) / total
            prob['home_win'] = hw * 0.5 + 0.25
            prob['away_win'] = aw * 0.5 + 0.25
            prob['draw'] = d * 0.5 + 0.25
            prob['1X'] = prob['home_win'] + prob['draw']
            prob['X2'] = prob['away_win'] + prob['draw']
            ag = h2h_data.get('avg_goals', 2.5)
            if ag > 2.5:
                prob['over_2_5'] = 0.55
                prob['under_2_5'] = 0.45
            else:
                prob['over_2_5'] = 0.45
                prob['under_2_5'] = 0.55
    return prob


def ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data):
    p = calculate_poisson_probability(home_xg, away_xg)
    f = calculate_form_probability(home_form, away_form)
    h = calculate_h2h_probability(h2h_data)
    fp = {
        'home_win': p['home_win'] * 0.5 + f['home_win'] * 0.3 + h['home_win'] * 0.2,
        'away_win': p['away_win'] * 0.5 + f['away_win'] * 0.3 + h['away_win'] * 0.2,
        'draw': p['draw'] * 0.5 + f['draw'] * 0.3 + h['draw'] * 0.2,
        '1X': p['1X'] * 0.5 + f['1X'] * 0.3 + h['1X'] * 0.2,
        'X2': p['X2'] * 0.5 + f['X2'] * 0.3 + h['X2'] * 0.2,
        'over_2_5': p['over_2_5'] * 0.5 + f['over_2_5'] * 0.3 + h['over_2_5'] * 0.2,
        'under_2_5': p['under_2_5'] * 0.5 + f['under_2_5'] * 0.3 + h['under_2_5'] * 0.2,
        'btts': p['btts'] * 0.5 + f['btts'] * 0.3 + h['btts'] * 0.2
    }
    tw = fp['home_win'] + fp['draw'] + fp['away_win']
    if tw > 0:
        fp['home_win'] /= tw
        fp['away_win'] /= tw
        fp['draw'] /= tw
        fp['1X'] = fp['home_win'] + fp['draw']
        fp['X2'] = fp['away_win'] + fp['draw']
    return fp


# ============================================================
# ПОИСК МАТЧЕЙ
# ============================================================
def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"🔍 Поиск матчей на: {today}")
    all_leagues = Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])
    for league_id in all_leagues:
        try:
            matches = football_api.get_matches(league_id, today)
            league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
            if not matches or not isinstance(matches, list): continue
            for match in matches:
                if not isinstance(match, dict): continue
                fixture = match.get("fixture")
                if not fixture or not isinstance(fixture, dict): continue
                status = fixture.get("status", {})
                if not isinstance(status, dict): continue
                if status.get("short") == "NS":
                    mid = fixture.get("id")
                    if not mid: continue
                    existing = [m.get("fixture", {}).get("id") for m in all_matches if isinstance(m, dict)]
                    if mid in existing: continue
                    teams = match.get("teams", {})
                    if not isinstance(teams, dict): continue
                    ht = teams.get("home", {})
                    at = teams.get("away", {})
                    if not isinstance(ht, dict) or not isinstance(at, dict): continue
                    hid = ht.get("id")
                    aid = at.get("id")
                    if not hid or not aid: continue
                    match["factors"] = {
                        "home_form": football_api.get_form(hid),
                        "away_form": football_api.get_form(aid),
                        "home_injuries_list": football_api.get_injuries(hid),
                        "away_injuries_list": football_api.get_injuries(aid),
                        "home_id": hid, "away_id": aid,
                        "referee": fixture.get("referee")
                    }
                    match["weather"] = None
                    ld = match.get("league", {})
                    if isinstance(ld, dict): ld["name"] = league_name
                    all_matches.append(match)
        except Exception as e:
            logger.error(f"❌ Ошибка {league_id}: {e}")
        time.sleep(0.1)
    logger.info(f"📊 Найдено матчей: {len(all_matches)}")
    return all_matches


# ============================================================
# ПОТОК 1: 70%+ МАТЧИ
# ============================================================
@timing_decorator()
def find_top_matches(matches):
    bank = storage.load_bank()
    max_bets = Config.MAX_BETS_PER_RUN
    logger.info(f"🔍 Анализ {len(matches)} матчей (70%+)...")
    best_matches = []
    bet_type_count = {}
    league_count = {}
    
    for match in matches:
        if not match or not isinstance(match, dict): continue
        try:
            fixture = match.get("fixture")
            if not fixture or not isinstance(fixture, dict): continue
            fixture_id = fixture.get("id")
            if not fixture_id: continue
            teams = match.get("teams")
            if not teams or not isinstance(teams, dict): continue
            home_team = teams.get("home")
            away_team = teams.get("away")
            if not isinstance(home_team, dict) or not isinstance(away_team, dict): continue
            home = home_team.get("name", "Unknown")
            away = away_team.get("name", "Unknown")
            ld = match.get("league")
            league_name = ld.get('name', 'Unknown') if isinstance(ld, dict) else "Unknown"
            if league_name == 'Unknown':
                lid = ld.get('id') if isinstance(ld, dict) else None
                if lid and lid in Config.LEAGUE_NAMES:
                    league_name = Config.LEAGUE_NAMES[lid]
            league_id = ld.get('id') if isinstance(ld, dict) else None
            mt = fixture.get("date", "")
            if mt:
                try:
                    dt = datetime.fromisoformat(mt.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    mt = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    mt = "Время не указано"
            
            hfd = football_api.get_form(home_team.get("id"))
            afd = football_api.get_form(away_team.get("id"))
            home_form = hfd.get('form', '') if hfd else ''
            away_form = afd.get('form', '') if afd else ''
            hga = hfd.get('goals_avg', 1.2) if hfd else 1.2
            aga = afd.get('goals_avg', 1.0) if afd else 1.0
            hca = hfd.get('conceded_avg', 1.0) if hfd else 1.0
            aca = afd.get('conceded_avg', 1.2) if afd else 1.2
            hxg = (hga + aca) / 2
            axg = (aga + hca) / 2
            
            hi = len(match['factors'].get('home_injuries_list', []))
            ai = len(match['factors'].get('away_injuries_list', []))
            if hi > 3: hxg *= 0.8
            if ai > 3: axg *= 0.8
            
            ha = HOME_ADVANTAGE.get(league_name, 1.10)
            hxg *= ha
            axg /= ha
            txg = hxg + axg
            
            ev_min = getattr(Config, 'EV_MIN_70', 20)
            prob_min = getattr(Config, 'PROB_MIN_70', 60)
            xg_min = getattr(Config, 'XG_MIN_70', 1.8)
            xg_max = getattr(Config, 'XG_MAX_70', 3.0)
            pos_max = getattr(Config, 'POSITION_MAX_70', 15)
            if txg < xg_min or txg > xg_max: continue
            
            standings = football_api.get_standings(league_id) if league_id else None
            hp = 99
            ap = 99
            if standings:
                if home in standings: hp = standings[home].get('position', 99)
                if away in standings: ap = standings[away].get('position', 99)
            hm = get_motivation(hp)
            am = get_motivation(ap)
            if hm == 'mid_table' and am == 'mid_table': continue
            if hp > pos_max or ap > pos_max: continue
            
            hwp = 0.55 + (hxg - axg) * 0.2 - (hi - ai) * 0.02
            dp = 0.25
            awp = 0.20 - (hxg - axg) * 0.2
            if hxg > axg + 0.5:
                hwp += 0.08
                awp -= 0.08
            elif hxg < axg - 0.5:
                awp += 0.08
                hwp -= 0.08
            tp = hwp + dp + awp
            if tp > 0:
                hwp /= tp
                dp /= tp
                awp /= tp
            
            odds = {'1X': 1.85, 'X2': 1.85, 'П1': 2.10, 'П2': 2.10, 'ТМ 2.5': 1.95, 'ТБ 2.5': 1.95, 'ОБЗ': 1.90}
            
            h2h = football_api.get_head_to_head(home, away)
            probs = ensemble_probability(hxg, axg, home_form, away_form, h2h)
            p_hw = probs['home_win']
            p_aw = probs['away_win']
            p_d = probs['draw']
            p_1x = probs['1X']
            p_x2 = probs['X2']
            p_o = probs['over_2_5']
            p_u = probs['under_2_5']
            p_b = probs['btts']
            
            if hm == 'relegation' and am == 'mid_table':
                p_hw += 0.10
                p_1x += 0.08
            elif am == 'relegation' and hm == 'mid_table':
                p_aw += 0.10
                p_x2 += 0.08
            elif hm == 'champions_league' and am == 'mid_table':
                p_hw += 0.08
                p_1x += 0.05
            elif am == 'champions_league' and hm == 'mid_table':
                p_aw += 0.08
                p_x2 += 0.05
            
            bets = []
            bets.append({'type': '1X', 'label': '1X', 'prob': round(p_1x*100,1), 'ev': round((p_1x*odds['1X']-1)*100,1), 'odds': odds['1X'], 'stake': 42.87})
            bets.append({'type': 'X2', 'label': 'X2', 'prob': round(p_x2*100,1), 'ev': round((p_x2*odds['X2']-1)*100,1), 'odds': odds['X2'], 'stake': 42.87})
            bets.append({'type': 'П1', 'label': 'П1', 'prob': round(p_hw*100,1), 'ev': round((p_hw*odds['П1']-1)*100,1), 'odds': odds['П1'], 'stake': 42.87})
            bets.append({'type': 'П2', 'label': 'П2', 'prob': round(p_aw*100,1), 'ev': round((p_aw*odds['П2']-1)*100,1), 'odds': odds['П2'], 'stake': 42.87})
            bets.append({'type': 'under', 'label': 'ТМ 2.5', 'prob': round(p_u*100,1), 'ev': round((p_u*odds['ТМ 2.5']-1)*100,1), 'odds': odds['ТМ 2.5'], 'stake': 42.87})
            bets.append({'type': 'over', 'label': 'ТБ 2.5', 'prob': round(p_o*100,1), 'ev': round((p_o*odds['ТБ 2.5']-1)*100,1), 'odds': odds['ТБ 2.5'], 'stake': 42.87})
            bets.append({'type': 'btts', 'label': 'ОБЗ', 'prob': round(p_b*100,1), 'ev': round((p_b*odds['ОБЗ']-1)*100,1), 'odds': odds['ОБЗ'], 'stake': 42.87})
            bets.sort(key=lambda x: x['ev'], reverse=True)
            best_bet = bets[0]
            
            if best_bet['ev'] < ev_min: continue
            if best_bet['prob'] < prob_min: continue
            
            bt = best_bet['type']
            bet_type_count[bt] = bet_type_count.get(bt, 0) + 1
            if bet_type_count[bt] > 3: continue
            league_count[league_name] = league_count.get(league_name, 0) + 1
            if league_count[league_name] > 2: continue
            
            best_matches.append({
                "home": home, "away": away, "league": league_name, "fixture_id": fixture_id,
                "match_time": mt, "home_xg": round(hxg, 2), "away_xg": round(axg, 2),
                "total_xg": round(txg, 2), "home_form": home_form, "away_form": away_form,
                "standings": {"home_position": hp, "away_position": ap,
                              "home_motivation": hm, "away_motivation": am},
                "bets": bets, "best_bet": best_bet,
                "source": "70_percent"
            })
            logger.info(f"✅ 70%+: {home} vs {away} | {best_bet['label']} | EV: {best_bet['ev']}%")
        except Exception as e:
            logger.error(f"❌ Ошибка 70%: {e}")
            continue
    
    best_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top = best_matches[:max_bets]
    logger.info(f"📊 70%+: {len(top)} матчей")
    return top


# ============================================================
# ПОТОК 2: X2 МАТЧИ
# ============================================================
@timing_decorator()
def find_x2_matches(matches):
    """Ищет X2: фаворит mid_table + аутсайдер relegation"""
    logger.info("🎯 Поиск X2 матчей...")
    x2_candidates = []
    
    for match in matches:
        if not match or not isinstance(match, dict): continue
        try:
            fixture = match.get("fixture")
            if not fixture or not isinstance(fixture, dict): continue
            fixture_id = fixture.get("id")
            teams = match.get("teams")
            if not teams or not isinstance(teams, dict): continue
            ht = teams.get("home")
            at = teams.get("away")
            if not isinstance(ht, dict) or not isinstance(at, dict): continue
            home = ht.get("name", "Unknown")
            away = at.get("name", "Unknown")
            ld = match.get("league")
            league_name = ld.get('name', 'Unknown') if isinstance(ld, dict) else "Unknown"
            league_id = ld.get('id') if isinstance(ld, dict) else None
            mt = fixture.get("date", "")
            if mt:
                try:
                    dt = datetime.fromisoformat(mt.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    mt = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    mt = "Время не указано"
            
            standings = football_api.get_standings(league_id) if league_id else None
            hp = 99
            ap = 99
            if standings:
                if home in standings: hp = standings[home].get('position', 99)
                if away in standings: ap = standings[away].get('position', 99)
            hm = get_motivation(hp)
            am = get_motivation(ap)
            
            is_x2 = False
            fav = und = None
            if hm == 'mid_table' and am == 'relegation':
                is_x2 = True
                fav = home
                und = away
            elif am == 'mid_table' and hm == 'relegation':
                is_x2 = True
                fav = away
                und = home
            
            if not is_x2: continue
            
            hfd = football_api.get_form(ht.get("id"))
            afd = football_api.get_form(at.get("id"))
            hga = hfd.get('goals_avg', 1.2) if hfd else 1.2
            aga = afd.get('goals_avg', 1.0) if afd else 1.0
            hca = hfd.get('conceded_avg', 1.0) if hfd else 1.0
            aca = afd.get('conceded_avg', 1.2) if afd else 1.2
            hxg = (hga + aca) / 2
            axg = (aga + hca) / 2
            ha = HOME_ADVANTAGE.get(league_name, 1.10)
            hxg *= ha
            axg /= ha
            txg = hxg + axg
            
            odds_x2 = 1.85
            try:
                od = football_api.get_match_odds(fixture_id)
                if od:
                    if fav == home and od.get('away_odds', 0) > 0: odds_x2 = od['away_odds']
                    elif fav == away and od.get('home_odds', 0) > 0: odds_x2 = od['home_odds']
            except: pass
            
            note = f"Фаворит {fav} — нет мотивации (#{hp if fav == home else ap}), аутсайдер {und} борется (#{ap if fav == home else hp})"
            
            log_x2_match(home, away, fav, und, odds_x2, round(txg, 2), note)
            
            x2_candidates.append({
                'home': home, 'away': away, 'favorite': fav, 'underdog': und,
                'odds': odds_x2, 'total_xg': round(txg, 2),
                'league': league_name, 'match_time': mt, 'note': note
            })
            logger.info(f"🎯 X2: {home} vs {away} | Фав: {fav} | Аут: {und}")
        except Exception as e:
            logger.error(f"❌ Ошибка X2: {e}")
            continue
    
    logger.info(f"📊 X2: {len(x2_candidates)} матчей")
    return x2_candidates


# ============================================================
# ОБЪЕДИНЁННЫЙ ПОИСК
# ============================================================
@timing_decorator()
def run_search(matches):
    """Запускает оба потока: 70%+ и X2"""
    
    # Очищаем X2 лог перед новым поиском
    clear_x2_log()
    
    logger.info("=" * 50)
    logger.info("📊 ПОТОК 1: 70%+ матчи")
    logger.info("=" * 50)
    top_matches = find_top_matches(matches)
    
    logger.info("=" * 50)
    logger.info("📊 ПОТОК 2: X2 матчи")
    logger.info("=" * 50)
    x2_matches = find_x2_matches(matches)
    
    # Сохраняем top_matches в кэш (для главной)
    if top_matches:
        cache = storage.load_cache()
        cache['top_matches'] = top_matches
        storage.save_cache(cache)
        
        # Добавляем в историю
        history = storage.load_history()
        for md in top_matches:
            bb = md.get('best_bet', {})
            history.append({
                'home': md.get('home', 'Unknown'),
                'away': md.get('away', 'Unknown'),
                'league': md.get('league', 'Unknown'),
                'bet': bb.get('label', '—'),
                'odds': bb.get('odds', 0),
                'stake': bb.get('stake', 42.87),
                'ev': bb.get('ev', 0),
                'result': 'pending',
                'profit': 0,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'fixture_id': md.get('fixture_id'),
                'bookmaker': bb.get('bookmaker', '—')
            })
        storage.save_history(history)
    
    logger.info("=" * 50)
    logger.info(f"📊 ИТОГО: 70%+ = {len(top_matches)}, X2 = {len(x2_matches)}")
    logger.info("=" * 50)
    
    return top_matches, x2_matches


# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================
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
            fid = bet.get('fixture_id')
            if not fid:
                h = bet.get('home', '')
                a = bet.get('away', '')
                if h and a:
                    fid = football_api.find_fixture_by_teams(h, a)
                    if fid: bet['fixture_id'] = fid
            if fid:
                md = football_api.get_match_result(fid)
                if md:
                    hg = md['goals']['home']
                    ag = md['goals']['away']
                    if hg is not None and ag is not None:
                        r = determine_bet_result(bet.get('bet', ''), hg, ag)
                        if r != 'pending':
                            bet['result'] = r
                            bet['home_goals'] = hg
                            bet['away_goals'] = ag
                            if r == 'win': bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                            elif r == 'loss': bet['profit'] = -bet['stake']
                            else: bet['profit'] = 0
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
    tp = sum(b.get('profit', 0) for b in history)
    ts = sum(b.get('stake', 0) for b in history)
    stats.update({
        'total': total, 'wins': wins, 'losses': losses, 'pushes': pushes,
        'total_profit': round(tp, 2),
        'winrate': round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
        'roi': round((tp / ts * 100), 1) if ts > 0 else 0
    })
    storage.save_stats(stats)


# ============================================================
# ПЛАНИРОВЩИК
# ============================================================
def schedule_updates():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=auto_update_results, trigger='interval', hours=6, id='au', replace_existing=True)
    scheduler.start()
    logger.info("⏰ Авто-обновление запущено")


def auto_update_results():
    try:
        u = update_pending_bets()
        if u > 0:
            send_telegram(f"🔄 Обновлено {u} результатов!")
    except Exception as e:
        logger.error(f"❌ Авто: {e}")


# ============================================================
# WEBHOOK
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
        msg = data['message']
        text = msg.get('text', '')
        chat_id = msg.get('chat', {}).get('id')
        
        if str(chat_id) != str(Config.ADMIN_CHAT_ID):
            return "ok", 200
        
        if text == '/start':
            send_telegram(handlers.handle_start())
        elif text == '/help':
            send_telegram(handlers.handle_help())
        elif text == '/update':
            if search_running:
                send_telegram("⚠️ Уже запущен!")
                return "ok", 200
            search_running = True
            search_state = {'start_time': datetime.now()}
            send_telegram("🔎 Поиск 70%+ и X2 матчей. Это займёт 10-20 минут...")
            
            def run():
                global search_running, search_state
                try:
                    start = datetime.now()
                    matches = get_matches_with_factors()
                    if not matches:
                        send_telegram("❌ Матчей не найдено.")
                        return
                    
                    send_telegram(f"📊 Найдено {len(matches)} матчей. Анализирую...")
                    top, x2 = run_search(matches)
                    
                    elapsed = (datetime.now() - start).seconds
                    m = elapsed // 60
                    s = elapsed % 60
                    
                    out = f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                    out += f"⏱️ Время: {m} мин {s} сек.\n\n"
                    out += f"📊 <b>70%+ матчей: {len(top)}</b>\n"
                    out += f"🎯 <b>X2 матчей: {len(x2)}</b>\n\n"
                    
                    if top:
                        out += "📋 <b>70%+ ставки:</b>\n"
                        for i, t in enumerate(top[:5], 1):
                            b = t['best_bet']
                            out += f"{i}. {t['home']} vs {t['away']}\n"
                            out += f"   🎯 {b['label']} | EV: {b['ev']}%\n"
                        out += "\n"
                    
                    if x2:
                        out += "🎯 <b>X2 матчи:</b>\n"
                        for i, x in enumerate(x2[:5], 1):
                            out += f"{i}. {x['home']} vs {x['away']}\n"
                            out += f"   Фав: {x['favorite']} | Аут: {x['underdog']}\n"
                    
                    send_telegram(out)
                except Exception as e:
                    logger.error(f"❌ {e}", exc_info=True)
                    send_telegram(f"❌ Ошибка: {e}")
                finally:
                    search_running = False
                    search_state = {}
            
            t = Thread(target=run)
            t.daemon = True
            t.start()
        
        elif text == '/stats':
            stats = storage.load_stats()
            bank = storage.load_bank()
            out = f"📊 <b>СТАТИСТИКА</b>\n\n💰 Банк: ${bank:.2f}\n"
            out += f"📊 Всего: {stats.get('total', 0)}\n✅ Побед: {stats.get('wins', 0)}\n"
            out += f"❌ Поражений: {stats.get('losses', 0)}\n📈 Винрейт: {stats.get('winrate', 0)}%\n"
            out += f"💰 Прибыль: ${stats.get('total_profit', 0):.2f}\n📊 ROI: {stats.get('roi', 0)}%"
            send_telegram(out)
        
        elif text == '/stop':
            search_running = False
            search_state = {}
            send_telegram("⏹️ Остановлено")
        
        else:
            send_telegram("❌ Неизвестная команда")
        
        return "ok", 200
    except Exception as e:
        logger.error(f"❌ Webhook: {e}")
        return "ok", 200


# ============================================================
# API
# ============================================================
@app.route('/api/x2_matches', methods=['GET'])
def api_x2_matches():
    try:
        x2_matches = []
        seen = set()
        if os.path.exists(X2_LOG_FILE):
            with open(X2_LOG_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            for line in content.split('\n'):
                if not line.startswith('X2_MATCH:'): continue
                try:
                    parts = line.replace('X2_MATCH:', '').strip().split('|')
                    mp = parts[0].strip()
                    if ' vs ' not in mp: continue
                    home, away = [x.strip() for x in mp.split(' vs ', 1)]
                    fav = und = note = dr = ''
                    odds = xg = 0.0
                    for p in parts[1:]:
                        if ':' not in p: continue
                        k, v = p.split(':', 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k == 'favorite': fav = v
                        elif k == 'underdog': und = v
                        elif k == 'odds':
                            try: odds = float(v)
                            except: pass
                        elif k == 'xg':
                            try: xg = float(v)
                            except: pass
                        elif k == 'note': note = v
                        elif k == 'date': dr = v
                    key = f"{mp}_{dr}"
                    if key in seen: continue
                    seen.add(key)
                    ds = datetime.now().strftime('%Y-%m-%d')
                    if dr:
                        try:
                            dt = datetime.strptime(dr, '%Y-%m-%d %H:%M')
                            ds = dt.strftime('%Y-%m-%d')
                        except: pass
                    x2_matches.append({
                        'date': ds, 'match': mp,
                        'favorite': fav or home, 'underdog': und or away,
                        'odds': odds, 'stake': 42.87, 'score': '-',
                        'result': 'pending', 'note': note or f"XG: {xg}"
                    })
                except Exception as e:
                    logger.error(f"Parse: {e}")
        x2_matches.sort(key=lambda m: m['date'], reverse=True)
        return jsonify({'success': True, 'log': '', 'x2_matches': x2_matches, 'count': len(x2_matches), 'timestamp': datetime.now().isoformat()})
    except Exception as e:
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
            'stats': {'bank': bank, 'total_bets': stats.get('total', 0),
                     'wins': stats.get('wins', 0), 'losses': stats.get('losses', 0),
                     'profit': stats.get('total_profit', 0), 'winrate': stats.get('winrate', 0),
                     'roi': stats.get('roi', 0), 'avg_stake': stats.get('avg_stake', 0)},
            'history': history, 'profit_data': get_profit_data(history),
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
            if k in data: history[index][k] = data[k]
        if history[index]['result'] == 'win': history[index]['profit'] = round(history[index]['stake'] * (history[index]['odds'] - 1), 2)
        elif history[index]['result'] == 'loss': history[index]['profit'] = -history[index]['stake']
        else: history[index]['profit'] = 0
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
        mn = data.get('match', '')
        if not mn: return jsonify({'error': 'No match'}), 400
        score = data.get('score', '-')
        result = data.get('result', 'win')
        stake = data.get('stake', 0)
        odds = data.get('odds', 1.85)
        home, away = 'Unknown', 'Unknown'
        if ' vs ' in mn: home, away = [x.strip() for x in mn.split(' vs ', 1)]
        if result == 'win': profit = round(stake * (odds - 1), 2)
        elif result == 'loss': profit = -stake
        else: profit = 0
        history = storage.load_history()
        history.append({'home': home, 'away': away, 'bet': data.get('bet', ''), 'odds': odds,
                       'stake': stake, 'result': result, 'profit': profit,
                       'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                       'bookmaker': data.get('bookmaker', 'Manual')})
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
    logger.info("📊 70%+ → /api/all_data")
    logger.info("🎯 X2 → /api/x2_matches")
    app.run(host='0.0.0.0', port=port)
