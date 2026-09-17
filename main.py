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
from datetime import datetime, timedelta, timezone  
from threading import Lock, Thread  
from collections import defaultdict  
from flask import Flask, request, jsonify, send_from_directory, render_template  
from apscheduler.schedulers.background import BackgroundScheduler  
  
# ============================================================  
# ИМПОРТЫ ИЗ ПРОЕКТА  
# ============================================================  
from app.config import Config  
from app.database.storage import storage  
from app.telegram.handlers import handlers  
from app.utils.logger import setup_logging, get_logger  
from app.scheduler import start_scheduler  
from app.llm import llm_analyze_match, llm_analyze_batch  
  
# ============================================================  
# ИНИЦИАЛИЗАЦИЯ  
# ============================================================  
logger = get_logger(__name__)  
app = Flask(__name__, template_folder='templates', static_folder='static')  
  
search_running = False  
search_state = {}  
TIMEZONE_OFFSET = 3  
  
cache_lock = Lock()  
  
# X2 файл для серверного хранилища  
X2_FILE = '/data/x2_data.json' if os.path.exists('/data') else 'x2_data.json'  
  
# ============================================================  
# МАРКЕРЫ  
# ============================================================  
MARKERS = {  
    42.86875000000006: ('under', 1.95, 'ТМ 2.5'),  
}  
  
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
  
# ============================================================  
# ПАРСИНГ ВРЕМЕНИ МАТЧА → МСК  
# ============================================================  
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
        logger.warning(f"⚠️ Не удалось распарсить дату '{date_str}': {e}")  
        try:  
            return str(date_str)[:16]  
        except Exception:  
            return "?"  
  
  
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
    def __init__(self, max_size=2000):  
        self.cache = {}  
        self.cache_timestamps = {}  
        self.hit_count = {}  
        self.last_access = {}  
        self.max_size = max_size  
        self.default_ttl = 3600  
        self.ttl_by_type = {  
            'form': 43200, 'odds': 60, 'statistics': 86400,  
            'standings': 86400, 'matches': 43200, 'h2h': 604800,  
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
# ОБРАБОТКА ОШИБОК  
# ============================================================  
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
# MATCHES LOG (для X2 авто-импорта)  
# ============================================================  
def log_no_motivation_match(home, away, hp, ap, total_xg, league_name=''):  
    """Записывает матч без мотивации в matches_log.txt (для X2-стратегии)."""  
    try:  
        log_path = 'matches_log.txt'  
        with open(log_path, 'a', encoding='utf-8') as f:  
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | {home} vs {away} | "  
                    f"нет мотивации | H: #{hp}, A: #{ap} | XG: {total_xg:.2f} | {league_name}\n")  
    except Exception as e:  
        logger.error(f"Ошибка записи matches_log: {e}")  
  
  
def trim_matches_log():  
    """Обрезает matches_log.txt, если он больше 500 KB."""  
    try:  
        log_path = 'matches_log.txt'  
        if os.path.exists(log_path):  
            size = os.path.getsize(log_path)  
            if size > 500 * 1024:  
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:  
                    lines = f.readlines()  
                with open(log_path, 'w', encoding='utf-8') as f:  
                    f.writelines(lines[-1000:])  
                logger.info(f"🧹 matches_log обрезан: {size // 1024} KB → {os.path.getsize(log_path) // 1024} KB")  
    except Exception as e:  
        logger.error(f"Ошибка trim_matches_log: {e}")  
  
  
# ============================================================  
# FOOTBALL API (Ultra)  
# ============================================================  
class FootballAPI:  
    def __init__(self, api_key=None, base_url=None):  
        self.api_key = api_key or Config.FOOTBALL_API_KEY  
        self.base_url = base_url or Config.FOOTBALL_API_URL  
        self.cache = SmartCache(max_size=2000)  
        self.last_request_time = 0  
        self.min_request_interval = 0.2  
        self.rate_limiter = APIRateLimiter(max_requests=250, time_window=60)  
        self.retry_manager = RetryManager(max_retries=3, base_delay=1)  
        self.error_stats = defaultdict(int)  
        logger.info(f"🔑 Football API ключ: {self.api_key[:8]}..." if self.api_key else "❌ FOOTBALL API КЛЮЧ НЕ НАЙДЕН!")  
  
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
    def get_predictions(self, fixture_id):  
        cache_key = f"pred_{fixture_id}"  
        cached = self.cache.get(cache_key)  
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
  
    def _extract_best_odds(self, odds_data):  
        result = {'best_odds': 0, 'bookmaker': '—', 'home_odds': 0,  
                  'draw_odds': 0, 'away_odds': 0, 'under_odds': 0, 'over_odds': 0,  
                  'btts_yes': 0, 'btts_no': 0, 'x2_odds': 0, '1x_odds': 0,  
                  'all_bookmakers': {}}  
  
        for bm in odds_data:  
            bm_name = bm.get('bookmaker', {}).get('name', '—')  
            bm_data = {'home': 0, 'draw': 0, 'away': 0, '1x': 0, 'x2': 0}  
  
            for bet in bm.get('bets', []):  
                bn = bet.get('name', '').lower()  
                values = bet.get('values', [])  
                if not values:  
                    continue  
  
                if 'match' in bn or 'побед' in bn or '1x2' in bn or 'winner' in bn:  
                    for v in values:  
                        vn = v.get('value', '').lower()  
                        odd = v.get('odd', 0)  
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
                        vn = v.get('value', '').lower()  
                        odd = v.get('odd', 0)  
                        if odd <= 0: continue  
                        if 'home/draw' in vn or vn == '1x':  
                            result['1x_odds'] = max(result['1x_odds'], odd)  
                            bm_data['1x'] = max(bm_data['1x'], odd)  
                        elif 'draw/away' in vn or vn == 'x2':  
                            result['x2_odds'] = max(result['x2_odds'], odd)  
                            bm_data['x2'] = max(bm_data['x2'], odd)  
  
                if 'total' in bn or 'over/under' in bn or 'тотал' in bn:  
                    for v in values:  
                        vn = v.get('value', '').lower()  
                        odd = v.get('odd', 0)  
                        if odd <= 0: continue  
                        if 'under' in vn or 'меньше' in vn:  
                            result['under_odds'] = max(result['under_odds'], odd)  
                        elif 'over' in vn or 'больше' in vn:  
                            result['over_odds'] = max(result['over_odds'], odd)  
  
                if 'both teams' in bn or 'btts' in bn or 'обе забьют' in bn:  
                    for v in values:  
                        vn = v.get('value', '').lower()  
                        odd = v.get('odd', 0)  
                        if odd <= 0: continue  
                        if vn == 'yes' or 'да' in vn:  
                            result['btts_yes'] = max(result['btts_yes'], odd)  
                        elif vn == 'no' or 'нет' in vn:  
                            result['btts_no'] = max(result['btts_no'], odd)  
  
            if any(bm_data.get(k, 0) > 0 for k in bm_data):  
                result['all_bookmakers'][bm_name] = bm_data  
  
        return result  
  
    def clear_cache(self):  
        self.cache.clear()  
  
    def find_fixture_by_teams(self, home_team, away_team):  
        try:  
            today = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d')  
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
# ODDS API (резервный источник)  
# ============================================================  
class OddsAPIClient:  
    def __init__(self, api_key=None):  
        self.api_key = api_key or Config.ODDS_API_KEY  
        self.base_url = Config.ODDS_API_URL  
        self.cache = {}  
        self.last_request_time = 0  
        self.min_request_interval = 0.5  
        logger.info(f"🎯 Odds API: {self.api_key[:8]}..." if self.api_key else "⚠️ Odds API не задан")  
  
    def _make_request(self, endpoint, params=None):  
        if not self.api_key:  
            return None  
        try:  
            now = time.time()  
            if now - self.last_request_time < self.min_request_interval:  
                time.sleep(self.min_request_interval - (now - self.last_request_time))  
            url = f"{self.base_url}{endpoint}"  
            params = params or {}  
            params['apiKey'] = self.api_key  
            r = requests.get(url, params=params, timeout=10)  
            self.last_request_time = time.time()  
            if r.status_code == 200:  
                return r.json()  
            logger.error(f"❌ Odds API {r.status_code}: {r.text[:200]}")  
            return None  
        except Exception as e:  
            logger.error(f"❌ Odds API error: {e}")  
            return None  
  
    def get_odds_for_match(self, home_team, away_team, league):  
        if not self.api_key:  
            return None  
        cache_key = f"{home_team}_{away_team}_{league}"  
        if cache_key in self.cache:  
            return self.cache[cache_key]  
        try:  
            sport_map = {  
                'Premier League': 'soccer_epl',  
                'La Liga': 'soccer_spain_la_liga',  
                'Bundesliga': 'soccer_germany_bundesliga',  
                'Serie A': 'soccer_italy_serie_a',  
                'Ligue 1': 'soccer_france_ligue_one',  
                'Championship': 'soccer_efl_champ',  
                'Eredivisie': 'soccer_netherlands_eredivisie',  
                'Primeira Liga': 'soccer_portugal_primeira_liga',  
                'Süper Lig': 'soccer_turkey_super_league',  
                'UEFA Champions League': 'soccer_uefa_champs_league',  
                'Champions League': 'soccer_uefa_champs_league',  
                'UEFA Europa League': 'soccer_uefa_europa_league',  
                'Europa League': 'soccer_uefa_europa_league',  
                'MLS': 'soccer_usa_mls',  
                'Brasileirão': 'soccer_brazil_campeonato',  
                'Argentina Primera': 'soccer_argentina_primera_division',  
            }  
            sport_key = sport_map.get(league)  
            if not sport_key:  
                return None  
            endpoint = f"/sports/{sport_key}/odds"  
            params = {'regions': 'eu', 'markets': 'h2h,totals', 'oddsFormat': 'decimal'}  
            data = self._make_request(endpoint, params)  
            if not data:  
                return None  
            for event in data:  
                event_home = event.get('home_team', '').lower()  
                event_away = event.get('away_team', '').lower()  
                home_lower = home_team.lower()  
                away_lower = away_team.lower()  
                # ✅ ИСПРАВЛЕНО: используем скобки вместо `\`  
                if ((home_lower in event_home or event_home in home_lower)  
                    and (away_lower in event_away or event_away in away_lower)):  
                    result = self._extract_odds(event)  
                    self.cache[cache_key] = result  
                    return result  
            return None  
        except Exception as e:  
            logger.error(f"❌ Odds API get_odds: {e}")  
            return None  
  
    def _extract_odds(self, event):  
        result = {  
            'best_odds': 0, 'bookmaker_name': '—',  
            'home_odds': 0, 'draw_odds': 0, 'away_odds': 0,  
            'under_odds': 0, 'over_odds': 0  
        }  
        for bm in event.get('bookmakers', []):  
            bm_key = bm.get('key', '—')  
            for market in bm.get('markets', []):  
                if market.get('key') == 'h2h':  
                    for outcome in market.get('outcomes', []):  
                        name = outcome.get('name', '')  
                        price = outcome.get('price', 0)  
                        if name == event.get('home_team'):  
                            result['home_odds'] = max(result['home_odds'], price)  
                        elif name == event.get('away_team'):  
                            result['away_odds'] = max(result['away_odds'], price)  
                        elif name == 'Draw':  
                            result['draw_odds'] = max(result['draw_odds'], price)  
                        if price > result['best_odds']:  
                            result['best_odds'] = price  
                            result['bookmaker_name'] = bm_key  
                elif market.get('key') == 'totals':  
                    for outcome in market.get('outcomes', []):  
                        name = outcome.get('name', '').lower()  
                        price = outcome.get('price', 0)  
                        if outcome.get('point') == 2.5:  
                            if name == 'over':  
                                result['over_odds'] = max(result['over_odds'], price)  
                            elif name == 'under':  
                                result['under_odds'] = max(result['under_odds'], price)  
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
            'bookmaker': best_bet.get('bookmaker', '—'),  
            'bet_type': best_bet.get('type', 'under'),  
            'source': match_data.get('source', '70_percent')  
        }  
  
  
auto_bet = AutoBet()  
  
  
# ============================================================  
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ  
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
  
  
def is_quality_match(home_xg, away_xg, home_position, away_position, home_form, away_form):  
    try:  
        total_xg = home_xg + away_xg  
        return all([  
            total_xg > 1.5, total_xg < 3.5,  
            home_position < 20, away_position < 20,  
            len(home_form) >= 3, len(away_form) >= 3,  
        ])  
    except Exception:  
        return False  
  
  
# ============================================================  
# ЭКСПОРТ В EXCEL  
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
  
        ws.append([  
            bet.get('date', ''),  
            f"{bet.get('home', '')} vs {bet.get('away', '')}",  
            score,  
            bet.get('bet', ''),  
            bet.get('odds', 0),  
            bet.get('ev', 0),  
            bet.get('stake', 0),  
            result,  
            profit,  
            bet.get('bookmaker', '—')  
        ])  
  
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
# ВЕРОЯТНОСТИ  
# ============================================================  
def calculate_poisson_probability(home_xg, away_xg):  
    def poisson(avg, g):  
        return (math.exp(-avg) * avg ** g) / math.factorial(g)  
  
    hgp = [poisson(home_xg, i) for i in range(6)]  
    agp = [poisson(away_xg, i) for i in range(6)]  
  
    prob = {'home_win': 0, 'away_win': 0, 'draw': 0,  
            '1X': 0, 'X2': 0, 'btts': 0,  
            'over25': 0, 'under25': 0,  
            'over_2_5': 0, 'under_2_5': 0}  
  
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
                prob['over25'] += p  
                prob['over_2_5'] += p  
            else:  
                prob['under25'] += p  
                prob['under_2_5'] += p  
  
    return prob  
  
  
def calculate_form_probability(home_form, away_form):  
    hq = analyze_form(home_form)  
    aq = analyze_form(away_form)  
    prob = {'home_win': 0.35, 'away_win': 0.30, 'draw': 0.35,  
            '1X': 0.70, 'X2': 0.65, 'btts': 0.45,  
            'over25': 0.5, 'under25': 0.5,  
            'over_2_5': 0.45, 'under_2_5': 0.55}  
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
            'over25': 0.5, 'under25': 0.5,  
            'over_2_5': 0.50, 'under_2_5': 0.50}  
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
                          match_data=None, api_predictions=None):  
    engine = getattr(Config, 'PREDICTION_ENGINE', 'heuristic')  
    poisson = calculate_poisson_probability(home_xg, away_xg)  
    form_prob = calculate_form_probability(home_form, away_form)  
    h2h_prob = calculate_h2h_probability(h2h_data)  
  
    if engine == 'hybrid':  
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
    key_map = {  
        'draw': 'draw', 'underdog': None, 'btts': 'btts',  
        'П1': 'home_win', 'П2': 'away_win',  
        'over25': 'over_2_5', 'under25': None,  
        '1X': None, 'X2': None,  
    }  
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
# ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА  
# ============================================================  
def determine_bet_result(bet_type, home_goals, away_goals):  
    total = home_goals + away_goals  
    bt = bet_type.lower()  
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
    total = len(matches)  
  
    for idx, md in enumerate(matches, 1):  
        if idx % 10 == 0:  
            send_telegram(f"💓 <b>ОБНОВЛЕНИЕ КЭФОВ</b> | {idx}/{total}")  
            logger.info(f"💓 Heartbeat кэфов: {idx}/{total}")  
  
        try:  
            home = md.get('home'); away = md.get('away'); league = md.get('league')  
            fid = md.get('fixture_id')  
            best_bet = md.get('best_bet', {})  
            bt = best_bet.get('type', 'under')  
            new_odds = None  
            bookmaker = '—'  
            source = None  
  
            # ЭТАП 1: Odds API  
            odds_data = odds_api.get_odds_for_match(home, away, league)  
            if odds_data and odds_data.get('best_odds', 0) > 0:  
                if bt == 'under' and odds_data.get('under_odds', 0) > 0:  
                    new_odds = odds_data['under_odds']  
                elif bt == 'over' and odds_data.get('over_odds', 0) > 0:  
                    new_odds = odds_data['over_odds']  
                elif bt in ['1X', 'П1'] and odds_data.get('home_odds', 0) > 0:  
                    new_odds = odds_data['home_odds']  
                elif bt in ['X2', 'П2'] and odds_data.get('away_odds', 0) > 0:  
                    new_odds = odds_data['away_odds']  
                else:  
                    new_odds = odds_data.get('best_odds', 0)  
                if new_odds and new_odds > 0:  
                    bookmaker = odds_data.get('bookmaker_name', 'Odds API')  
                    source = 'Odds API'  
  
            # ЭТАП 2: Football API Ultra  
            if not new_odds or new_odds <= 0:  
                if fid:  
                    fo = football_api.get_match_odds(fid)  
                    if fo:  
                        bm_list = fo.get('all_bookmakers', {})  
                        if bm_list and len(bm_list) >= 2:  
                            if bt == 'X2': target = 'x2'  
                            elif bt == '1X': target = '1x'  
                            elif bt in ('П1', '1'): target = 'home'  
                            elif bt in ('П2', '2'): target = 'away'  
                            elif bt == 'draw': target = 'draw'  
                            else: target = 'home'  
  
                            target_odds = {  
                                bm: data.get(target, 0)  
                                for bm, data in bm_list.items()  
                                if data.get(target, 0) > 0  
                            }  
                            if target_odds:  
                                best_bm = max(target_odds, key=target_odds.get)  
                                best_odds = target_odds[best_bm]  
                                avg_odds = sum(target_odds.values()) / len(target_odds)  
                                anomaly_pct = ((best_odds / avg_odds) - 1) * 100 if avg_odds > 0 else 0  
                                new_odds = best_odds  
                                bookmaker = f"{best_bm} (+{anomaly_pct:.1f}%)"  
                                source = 'Line Analysis'  
                                if anomaly_pct > 5:  
                                    logger.info(f"🎯 АНОМАЛИЯ: {home} vs {away} | {best_bm} = {best_odds} (+{anomaly_pct:.1f}%)")  
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
  
            # ЭТАП 3: Fair Odds  
            if not new_odds:  
                prob = best_bet.get('prob', 0) / 100  
                if prob > 0:  
                    new_odds = round((1 / prob) * 0.95, 2)  
                    bookmaker = 'Fair Odds'  
                    source = 'Calculated'  
  
            if new_odds and new_odds > 0:  
                MIN_ODDS = getattr(Config, 'MIN_ODDS', 1.40)  
                MAX_ODDS = getattr(Config, 'MAX_ODDS', 8.00)  
                if new_odds < MIN_ODDS or new_odds > MAX_ODDS:  
                    logger.info(f"⏭️ Кэф {new_odds} вне [{MIN_ODDS}, {MAX_ODDS}]: {home} vs {away}")  
                    updated.append(md)  
                    continue  
  
                prob = best_bet.get('prob', 0) / 100  
                best_bet['odds'] = round(new_odds, 2)  
                best_bet['ev'] = round((prob * new_odds - 1) * 100, 1)  
                best_bet['bookmaker'] = bookmaker  
                best_bet['odds_source'] = source  
                md['best_bet'] = best_bet  
                md['odds_updated'] = True  
  
                try:  
                    market_map = {  
                        'draw': ('1X2', 'X'), 'draw_boosted': ('1X2', 'X'),  
                        'btts': ('BTTS', 'BTTS'),  
                        'over25': ('O/U 2.5', 'Over'), 'under25': ('O/U 2.5', 'Under'),  
                        'over': ('O/U 2.5', 'Over'), 'under': ('O/U 2.5', 'Under'),  
                        'underdog': ('1X2', 'Underdog'),  
                        'П1': ('1X2', '1'), 'П2': ('1X2', '2'),  
                        '1X': ('DC', '1X'), 'X2': ('DC', 'X2'),  
                    }  
                    mkt, sel = market_map.get(bt, (bt, 'unknown'))  
                    storage.save_odds_snapshot(  
                        fixture_id=fid, market=mkt,  
                        selection=sel, odds=new_odds, bookmaker=bookmaker  
                    )  
                except Exception as e:  
                    logger.error(f"Ошибка записи снимка: {e}")  
  
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
    today = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d')  
    all_leagues = Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])  
    total_leagues = len(all_leagues)  
  
    logger.info(f"🔍 Поиск: {today}, лиг: {total_leagues}")  
    send_telegram(  
        f"🔎 <b>СТАРТ ПОИСКА</b>\n"  
        f"📅 Дата: {today}\n"  
        f"📊 Лиг: {total_leagues}\n"  
        f"⏱️ Время: 5-10 минут"  
    )  
  
    start_time = time.time()  
    processed = 0  
    found_total = 0  
    empty_leagues = 0  
    leagues_with_matches = 0  
    progress_step = 25  
    seen_fixtures = set()  
  
    for league_id in all_leagues:  
        try:  
            matches = football_api.get_matches(league_id, today)  
            league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))  
            processed += 1  
  
            if not matches:  
                empty_leagues += 1  
            else:  
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
                        'referee': fixture.get('referee')  
                    }  
  
                    weather = None  
                    venue = fixture.get('venue', {})  
                    city = venue.get('city') if isinstance(venue, dict) else None  
                    if city and Config.WEATHER_ENABLED:  
                        weather = Config.get_weather_for_city(city)  
                    m['weather'] = weather  
                    if weather:  
                        m['weather_reason'] = f"🌤️ {weather['desc']}, {weather['temp']}°C, ветер {weather['wind']} м/с, дождь {weather['rain']} мм"  
                    else:  
                        m['weather_reason'] = "🌤️ Нет данных"  
  
                    ld = m.get('league', {})  
                    if isinstance(ld, dict):  
                        ld['name'] = league_name  
  
                    all_matches.append(m)  
                    new_matches += 1  
  
                if new_matches > 0:  
                    found_total += new_matches  
                    leagues_with_matches += 1  
                else:  
                    empty_leagues += 1  
  
            if processed % progress_step == 0:  
                elapsed = (time.time() - start_time) / 60  
                remaining = total_leagues - processed  
                eta = (elapsed / processed) * remaining if processed > 0 else 0  
                send_telegram(  
                    f"💓 <b>HEARTBEAT</b> | {processed}/{total_leagues}\n"  
                    f"🎯 Матчей: {found_total}\n"  
                    f"⏱️ Осталось: ~{eta:.1f} мин"  
                )  
        except Exception as e:  
            logger.error(f"❌ {league_id}: {e}")  
  
        time.sleep(0.01)  
  
    elapsed_total = (time.time() - start_time) / 60  
    send_telegram(  
        f"✅ <b>ПОИСК ЗАВЕРШЁН</b>\n"  
        f"📊 Лиг: {processed}/{total_leagues}\n"  
        f"🎯 Матчей: {found_total}\n"  
        f"⏱️ Время: {elapsed_total:.1f} мин"  
    )  
    logger.info(f"📊 Найдено матчей: {len(all_matches)}")  
    return all_matches  
  
  
# ============================================================  
# ПОТОК 1: 70%+ МАТЧИ  
# ============================================================  
@timing_decorator()  
def find_top_matches(matches):  
    find_start_time = time.time()  
    bank = storage.load_bank()  
    max_bets = getattr(Config, 'MAX_BETS_PER_RUN', 30)  
    total_matches = len(matches)  
    logger.info(f"🔍 [70%+] Анализ {total_matches} матчей...")  
  
    blacklist = getattr(Config, 'BLACKLIST_LEAGUES', [])  
    best_matches = []  
    bet_type_count = {}  
    league_count = {}  
    heartbeat_interval = 30  
  
    for match_idx, match in enumerate(matches):  
        if not match or not isinstance(match, dict): continue  
        if (match_idx + 1) % heartbeat_interval == 0:  
            elapsed = time.time() - find_start_time  
            send_telegram(f"💓 <b>АНАЛИЗ 70%+</b> | {match_idx + 1}/{total_matches}\n🎯 Кандидатов: {len(best_matches)}")  
  
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
  
            league_lower = league_name.lower()  
            if any(bad in league_lower for bad in blacklist):  
                logger.info(f"⏭️ [70%+] ЧС: {home} vs {away} ({league_name})")  
                continue  
  
            match_time = parse_match_time_to_msk(fixture.get('date', ''))  
  
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
                    total_xg *= 0.92; home_xg *= 0.95; away_xg *= 0.95  
                elif rain > 0.5:  
                    total_xg *= 0.96  
                if wind > 10: total_xg *= 0.95  
                elif wind > 7: total_xg *= 0.98  
  
            XG_MIN = getattr(Config, 'XG_MIN_70', 1.8)  
            XG_MAX = getattr(Config, 'XG_MAX_70', 3.0)  
            POS_MAX = getattr(Config, 'POSITION_MAX_70', 15)  
  
            if total_xg < XG_MIN or total_xg > XG_MAX:  
                continue  
  
            standings = football_api.get_standings(league_id) if league_id else None  
            hp = standings.get(home, {}).get('position', 99) if standings else 99  
            ap = standings.get(away, {}).get('position', 99) if standings else 99  
            hm = get_motivation(hp); am = get_motivation(ap)  
  
            if hm == 'mid_table' and am == 'mid_table':  
                # ✅ ЛОГ ДЛЯ X2 СТРАТЕГИИ  
                log_no_motivation_match(home, away, hp, ap, total_xg, league_name)  
                continue  
  
            if hp > POS_MAX or ap > POS_MAX:  
                continue  
  
            if league_name in TOP_TEAMS_LEAGUES and hp <= 6 and ap <= 6:  
                logger.info(f"⏭️ Топ-матч: {home} vs {away}")  
                continue  
  
            home_data = standings.get(home, {}) if standings else {}  
            away_data = standings.get(away, {}) if standings else {}  
  
            h2h = football_api.get_head_to_head(home, away)  
            api_predictions = football_api.get_predictions(fid) if fid else None  
  
            probs = ensemble_probability(  
                home_xg, away_xg, home_form, away_form, h2h,  
                match_data=None, api_predictions=api_predictions  
            )  
  
            if hm == 'relegation' and am == 'mid_table':  
                probs['home_win'] = probs.get('home_win', 0) + 0.05  
            elif am == 'relegation' and hm == 'mid_table':  
                probs['away_win'] = probs.get('away_win', 0) + 0.05  
  
            stake = round(bank * 0.02, 2) if bank > 0 else 10.0  
            bets = []  
            odds_template = {  
                '1X': 1.85, 'X2': 1.85, 'П1': 2.10, 'П2': 2.10,  
                'ТМ 2.5': 1.95, 'ТБ 2.5': 1.95, 'ОБЗ': 1.90,  
            }  
  
            for bt, label, pk in [  
                ('1X', '1X', '1X'), ('X2', 'X2', 'X2'),  
                ('П1', 'П1', 'home_win'), ('П2', 'П2', 'away_win'),  
                ('under', 'ТМ 2.5', 'under25'), ('over', 'ТБ 2.5', 'over25'),  
                ('btts', 'ОБЗ', 'btts'),  
            ]:  
                p = probs.get(pk, probs.get(pk.replace('25', '_2_5'), 0))  
                if p <= 0: continue  
                key = 'ТМ 2.5' if bt == 'under' else ('ТБ 2.5' if bt == 'over' else ('ОБЗ' if bt == 'btts' else label))  
                bets.append({  
                    'type': bt, 'label': label,  
                    'prob': round(p * 100, 1),  
                    'ev': round((p * odds_template[key] - 1) * 100, 1),  
                    'odds': odds_template[key], 'stake': stake  
                })  
  
            if not bets: continue  
            bets.sort(key=lambda x: x['ev'], reverse=True)  
            best_bet = bets[0]  
  
            EV_MIN_70 = getattr(Config, 'EV_MIN_70', 15)  
            PROB_MIN_70 = getattr(Config, 'PROB_MIN_70', 55)  
  
            if best_bet['ev'] < EV_MIN_70: continue  
            if best_bet['prob'] < PROB_MIN_70: continue  
  
            bt = best_bet['type']  
            LIMIT_BT = getattr(Config, 'LIMIT_BET_TYPE_70', 15)  
            LIMIT_LG = getattr(Config, 'LIMIT_LEAGUE_70', 5)  
            bet_type_count[bt] = bet_type_count.get(bt, 0) + 1  
            if bet_type_count[bt] > LIMIT_BT: continue  
            league_count[league_name] = league_count.get(league_name, 0) + 1  
            if league_count[league_name] > LIMIT_LG: continue  
  
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
                "api_predictions": api_predictions,  
                "factors": {}, "source": "70_percent"  
            })  
            logger.info(f"✅ [70%+] {home} vs {away} | {best_bet['label']} | EV: {best_bet['ev']}%")  
        except Exception as e:  
            logger.error(f"❌ [70%+] {e}")  
            continue  
  
    best_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)  
    top = best_matches[:max_bets]  
  
    if Config.LLM_ENABLED and top and Config.PREDICTION_ENGINE in ('llm', 'hybrid'):  
        try:  
            llm_payload = [  
                {'home': m['home'], 'away': m['away'], 'league': m['league'],  
                 'home_xg': m['home_xg'], 'away_xg': m['away_xg'], 'total_xg': m['total_xg'],  
                 'home_form': m['home_form'], 'away_form': m['away_form'],  
                 'standings': m['standings'],  
                 'weather_reason': m.get('weather_reason', ''),  
                 'home_injuries': [], 'away_injuries': []}  
                for m in top[:20]  
            ]  
            logger.info(f"🤖 LLM батч: {len(llm_payload)} матчей...")  
            t0 = time.time()  
            llm_results = llm_analyze_batch(llm_payload)  
            logger.info(f"🤖 LLM за {time.time() - t0:.1f}с")  
            for m, llm in zip(top[:20], llm_results):  
                if llm:  
                    _apply_llm_to_match(m, llm, alpha=0.7)  
        except Exception as e:  
            logger.error(f"❌ LLM ошибка: {e}")  
  
    return top  
  
  
# ============================================================  
# ПОТОК 2: ТМ 2.5 (ЕДИНЫЙ ЦИКЛ)  
# ============================================================  
@timing_decorator()  
def find_tm25_matches(matches):  
    tm25_candidates = []  
    MAX_TM25_BETS = getattr(Config, 'MAX_TM25_BETS', 5)  
    PREMIUM_MIN_EV = getattr(Config, 'PREMIUM_MIN_EV', 30) / 100  
    PREMIUM_MIN_PROB = getattr(Config, 'PREMIUM_MIN_PROB', 60) / 100  
    PREMIUM_XG_MIN = getattr(Config, 'PREMIUM_XG_MIN', 1.0)  
    PREMIUM_XG_MAX = getattr(Config, 'PREMIUM_XG_MAX', 2.8)  
    STANDARD_MIN_EV = getattr(Config, 'STANDARD_MIN_EV', 15) / 100  
    STANDARD_MIN_PROB = getattr(Config, 'STANDARD_MIN_PROB', 50) / 100  
    STANDARD_XG_MIN = getattr(Config, 'TM25_XG_MIN', 0.8)  
    STANDARD_XG_MAX = getattr(Config, 'TM25_XG_MAX', 3.0)  
  
    logger.info("🔍 [ТМ 2.5] Единый поиск...")  
    stats = {'premium_found': 0, 'standard_found': 0}  
    seen_keys = set()  
  
    for match in matches:  
        if len(tm25_candidates) >= MAX_TM25_BETS:  
            break  
        if not match or not isinstance(match, dict):  
            continue  
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
  
            hfd = football_api.get_form(ht.get('id'))  
            afd = football_api.get_form(at.get('id'))  
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
  
            # PREMIUM  
            if (PREMIUM_XG_MIN <= total_xg <= PREMIUM_XG_MAX  
                and ev_under >= PREMIUM_MIN_EV  
                and p_under >= PREMIUM_MIN_PROB):  
                if league_name in TOP_LEAGUES and ev_under < 0.35:  
                    continue  
                best_bet = {  
                    'type': 'under', 'label': 'ТМ 2.5 🔥',  
                    'prob': round(p_under * 100, 1),  
                    'ev': round(ev_under * 100, 1),  
                    'odds': odds_tm25, 'stake': round(42.87, 2),  
                    'level': 'PREMIUM'  
                }  
                tm25_candidates.append({  
                    "home": home, "away": away, "league": league_name,  
                    "fixture_id": fid, "match_time": match_time,  
                    "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),  
                    "total_xg": round(total_xg, 2),  
                    "home_form": home_form, "away_form": away_form,  
                    "standings": {"home_position": hp, "away_position": ap},  
                    "bets": [best_bet], "best_bet": best_bet,  
                    "source": "tm25_premium", "weather_reason": "🌤️"  
                })  
                stats['premium_found'] += 1  
                logger.info(f"🔥 PREMIUM: {home} vs {away} | EV: {ev_under*100:.1f}%")  
                continue  
  
            # STANDARD  
            if (STANDARD_XG_MIN <= total_xg <= STANDARD_XG_MAX  
                and ev_under >= STANDARD_MIN_EV  
                and p_under >= STANDARD_MIN_PROB):  
                if league_name in TOP_LEAGUES and ev_under < 0.20:  
                    continue  
                best_bet = {  
                    'type': 'under', 'label': 'ТМ 2.5',  
                    'prob': round(p_under * 100, 1),  
                    'ev': round(ev_under * 100, 1),  
                    'odds': odds_tm25, 'stake': round(42.87, 2),  
                    'level': 'STANDARD'  
                }  
                tm25_candidates.append({  
                    "home": home, "away": away, "league": league_name,  
                    "fixture_id": fid, "match_time": match_time,  
                    "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),  
                    "total_xg": round(total_xg, 2),  
                    "home_form": home_form, "away_form": away_form,  
                    "standings": {"home_position": hp, "away_position": ap},  
                    "bets": [best_bet], "best_bet": best_bet,  
                    "source": "tm25_standard", "weather_reason": "🌤️"  
                })  
                stats['standard_found'] += 1  
                logger.info(f"⭐ STANDARD: {home} vs {away} | EV: {ev_under*100:.1f}%")  
        except Exception as e:  
            logger.error(f"❌ [ТМ2.5] {e}")  
            continue  
  
    logger.info(f"📊 [ТМ2.5] PREMIUM: {stats['premium_found']}, STANDARD: {stats['standard_found']}")  
    tm25_candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)  
    return tm25_candidates  
  
  
# ============================================================  
# ОБЪЕДИНЕНИЕ  
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
  
    combined = []  
    keys = set()  
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
  
    for m in combined:  
        bets = [b for b in m.get('bets', []) if b.get('odds', 0) > 1.01]  
        if not bets: continue  
        bets.sort(key=lambda x: x.get('ev', 0), reverse=True)  
        m['bets'] = bets  
        m['best_bet'] = bets[0]  
  
    EV_MIN = getattr(Config, 'EV_FINAL_MIN', -6)  
    EV_MAX = getattr(Config, 'EV_FINAL_MAX', 100)  
    PROB_MIN = getattr(Config, 'PROB_FINAL_MIN', 45)  
  
    filtered = []  
    for m in combined:  
        bb = m.get('best_bet', {})  
        ev = bb.get('ev', 0)  
        prob = bb.get('prob', 0)  
        if ev < EV_MIN or ev > EV_MAX: continue  
        if prob < PROB_MIN: continue  
        filtered.append(m)  
  
    logger.info(f"📊 После фильтра: {len(filtered)} из {len(combined)}")  
  
    with cache_lock:  
        cache = storage.load_cache()  
        cache['top_matches'] = filtered  
        cache['all_analyzed'] = all_before_odds_filter  
        storage.save_cache(cache)  
  
    history = storage.load_history()  
    today_str = (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d')  
    existing = {(h.get('home'), h.get('away'), h.get('date', '').split()[0]) for h in history}  
    added = 0  
    for md in filtered:  
        bb = md.get('best_bet', {})  
        key = (md.get('home'), md.get('away'), today_str)  
        if key in existing: continue  
        existing.add(key)  
        history.append({  
            'home': md.get('home'), 'away': md.get('away'),  
            'league': md.get('league'), 'bet': bb.get('label', '—'),  
            'odds': bb.get('odds', 0), 'stake': bb.get('stake', 0),  
            'ev': bb.get('ev', 0), 'result': 'pending', 'profit': 0,  
            'date': (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d %H:%M'),  
            'fixture_id': md.get('fixture_id'),  
            'bookmaker': bb.get('bookmaker', '—'),  
            'engine': Config.PREDICTION_ENGINE,  
            'weather_reason': md.get('weather_reason', '')  
        })  
        added += 1  
    storage.save_history(history)  
    logger.info(f"📝 Добавлено ставок: {added}")  
    logger.info("=" * 60)  
  
    return filtered  
  
  
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
                if fid: bet['fixture_id'] = fid  
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
# СНИМКИ КЭФОВ  
# ============================================================  
def snapshot_odds_for_upcoming():  
    logger.info("🔍 snapshot: НАЧАЛО")  
    try:  
        with cache_lock:  
            cache = storage.load_cache()  
            matches = cache.get('all_analyzed') or cache.get('top_matches', [])  
        logger.info(f"🔍 snapshot: матчей в кэше: {len(matches)}")  
        if not matches:  
            return 0  
  
        now = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)  
        in_window = 0  
        total_snapshots = 0  
  
        for md in matches:  
            try:  
                home = md.get('home', '?')  
                away = md.get('away', '?')  
                match_time_str = md.get('match_time', '')  
                if not match_time_str or match_time_str == '?':  
                    continue  
                try:  
                    match_dt = datetime.strptime(match_time_str, "%d.%m.%Y %H:%M")  
                except ValueError:  
                    continue  
                hours_to_match = (match_dt - now).total_seconds() / 3600  
                if not (0 < hours_to_match <= 2):  
                    continue  
                in_window += 1  
                fid = md.get('fixture_id')  
                if not fid: continue  
                fo = football_api.get_match_odds(fid)  
                if not fo: continue  
                for mkt, sel, key in [  
                    ('1X2', '1', 'home_odds'),  
                    ('1X2', 'X', 'draw_odds'),  
                    ('1X2', '2', 'away_odds'),  
                ]:  
                    odd = fo.get(key, 0)  
                    if odd and odd > 1.01:  
                        ok = storage.save_odds_snapshot(  
                            fixture_id=fid, market=mkt,  
                            selection=sel, odds=odd,  
                            bookmaker=fo.get('bookmaker', '—')  
                        )  
                        if ok: total_snapshots += 1  
            except Exception as e:  
                logger.error(f"🔍 snapshot error: {e}")  
                continue  
  
        logger.info(f"📸 Снимков: {total_snapshots} | в окне: {in_window}/{len(matches)}")  
        return total_snapshots  
    except Exception as e:  
        logger.exception(f"❌ snapshot: {e}")  
        return 0  
  
  
# ============================================================  
# РАСПИСАНИЯ  
# ============================================================  
def schedule_updates():  
    scheduler = BackgroundScheduler()  
    scheduler.add_job(func=auto_update_results, trigger='interval',  
                      hours=6, id='auto_update', replace_existing=True)  
    scheduler.start()  
    logger.info("⏰ Авто-обновление: 6ч")  
  
  
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
    logger.info("🔔 Уведомления: 1ч")  
  
  
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
# АВТОБЭКАП  
# ============================================================  
BACKUP_DIR = 'backups'  
MAX_BACKUPS = 7  
  
  
def cleanup_old_backups():  
    try:  
        os.makedirs(BACKUP_DIR, exist_ok=True)  
        files = sorted(  
            [f for f in os.listdir(BACKUP_DIR)  
             if f.startswith('backup_') and f.endswith('.zip')],  
            reverse=True  
        )  
        for old in files[MAX_BACKUPS:]:  
            try: os.remove(os.path.join(BACKUP_DIR, old))  
            except Exception as e: logger.error(f"Ошибка удаления {old}: {e}")  
    except Exception as e:  
        logger.error(f"❌ cleanup: {e}")  
  
  
def send_auto_backup():  
    try:  
        os.makedirs(BACKUP_DIR, exist_ok=True)  
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')  
        zip_path = os.path.join(BACKUP_DIR, f'backup_{ts}.zip')  
        items_to_backup = ['data', 'bot.db', 'bot_state.json', 'matches_log.txt']  
  
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:  
            for item in items_to_backup:  
                if os.path.exists(item):  
                    if os.path.isdir(item):  
                        for root, _, files in os.walk(item):  
                            for f in files:  
                                full = os.path.join(root, f)  
                                arcname = os.path.relpath(full, '.')  
                                zf.write(full, arcname)  
                    else:  
                        zf.write(item, item)  
  
        size_kb = os.path.getsize(zip_path) / 1024  
        history = storage.load_history()  
        bank = storage.load_bank()  
        total_bets = len(history)  
        wins = sum(1 for b in history if b.get('result') == 'win')  
  
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"  
        with open(zip_path, 'rb') as f:  
            r = requests.post(url,  
                files={'document': (os.path.basename(zip_path), f, 'application/zip')},  
                data={  
                    'chat_id': Config.ADMIN_CHAT_ID,  
                    'caption': (  
                        f"💾 <b>АВТОБЭКАП</b>\n"  
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"  
                        f"📦 Размер: {size_kb:.1f} КБ\n"  
                        f"📊 Ставок: {total_bets} | Побед: {wins}\n"  
                        f"💰 Банк: ${bank:.2f}"  
                    ),  
                    'parse_mode': 'HTML'  
                }, timeout=60)  
  
        if r.status_code == 200:  
            logger.info(f"💾 Бэкап: {zip_path} ({size_kb:.1f} КБ)")  
            cleanup_old_backups()  
            return zip_path  
        logger.error(f"❌ Ошибка бэкапа: {r.text}")  
        return None  
    except Exception as e:  
        logger.error(f"❌ backup: {e}")  
        return None  
  
  
def schedule_auto_backup():  
    scheduler = BackgroundScheduler()  
    scheduler.add_job(func=send_auto_backup, trigger='cron',  
                      hour=0, minute=0, id='auto_backup', replace_existing=True)  
    scheduler.add_job(func=trim_matches_log, trigger='cron',  
                      hour=2, minute=0, id='trim_log', replace_existing=True)  
    scheduler.start()  
    logger.info("⏰ Бэкап: 3:00 МСК | Очистка лога: 5:00 МСК")  
  
  
# ============================================================  
# ВЕРИФИКАЦИЯ / УВЕДОМЛЕНИЯ / СТРАТЕГИИ  
# ============================================================  
class BetVerificationSystem:  
    def __init__(self):  
        self.thresholds = {'min_odds': 1.40, 'max_odds': 8.00,  
                           'min_ev': 0, 'min_prob': 50,  
                           'max_stake_percent': 10}  
        self.warnings = []  
  
    def verify(self, bet_data):  
        self.warnings = []  
        o = bet_data.get('odds', 0)  
        if o < self.thresholds['min_odds']: self.warnings.append(f"Низкий кэф: {o}")  
        if o > self.thresholds['max_odds']: self.warnings.append(f"Высокий кэф: {o}")  
        if bet_data.get('ev', 0) < self.thresholds['min_ev']: self.warnings.append(f"Низкий EV")  
        if bet_data.get('prob', 0) < self.thresholds['min_prob']: self.warnings.append(f"Низкая Prob")  
        stake = bet_data.get('stake', 0)  
        bank = storage.load_bank()  
        if bank > 0 and (stake / bank) * 100 > self.thresholds['max_stake_percent']:  
            self.warnings.append(f"Ставка > 10% банка")  
        if not self.warnings:  
            return {'status': '✅', 'message': 'OK'}  
        return {'status': '⚠️', 'warnings': self.warnings}  
  
  
verification_system = BetVerificationSystem()  
  
  
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
            if pct > 20: self.send_if_needed('bank_dd', f"🔴 Просадка ${dd:.2f} ({pct:.1f}%)")  
            elif pct > 10: self.send_if_needed('bank_dd_mid', f"⚠️ Просадка ${dd:.2f} ({pct:.1f}%)")  
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
        if roi > 20: self.send_if_needed('roi_high', f"📈 ROI: {roi}%")  
        elif roi < -10: self.send_if_needed('roi_low', f"📉 ROI: {roi}%")  
  
    def run_all_checks(self):  
        try:  
            self.check_bank_status()  
            self.check_streaks()  
            self.check_roi()  
        except Exception as e:  
            logger.error(f"Ошибка уведомлений: {e}")  
  
  
notification_system = NotificationSystem()  
  
  
class StrategyTester:  
    def __init__(self):  
        self.strategies = {  
            '70_percent': {'name': '70%+ матчи', 'bets': [], 'profit': 0,  
                           'wins': 0, 'losses': 0, 'total_stake': 0},  
            'tm25_premium': {'name': 'ТМ 2.5 PREMIUM', 'bets': [], 'profit': 0,  
                             'wins': 0, 'losses': 0, 'total_stake': 0},  
            'tm25_standard': {'name': 'ТМ 2.5 STANDARD', 'bets': [], 'profit': 0,  
                              'wins': 0, 'losses': 0, 'total_stake': 0},  
        }  
  
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
  
  
class BotState:  
    def __init__(self):  
        self.state_file = 'bot_state.json'  
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
        except Exception: pass  
        return default  
  
    def save_state(self):  
        try:  
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
        settings_file = 'bot_settings.json'  
        if os.path.exists(settings_file):  
            with open(settings_file, 'r') as f:  
                s = json.load(f)  
            for key, default in [  
                ('EV_MIN_70', 15), ('PROB_MIN_70', 55),  
                ('XG_MIN_70', 1.8), ('XG_MAX_70', 3.0),  
                ('POSITION_MAX_70', 15), ('PREMIUM_MIN_EV', 30),  
                ('STANDARD_MIN_EV', 15), ('TM25_XG_MIN', 0.8),  
                ('TM25_XG_MAX', 3.0), ('MAX_TM25_BETS', 5),  
                ('TM25_TOP_LEAGUE_EV', 35),  
            ]:  
                if key.lower() in s:  
                    setattr(Config, key, s[key.lower()])  
            logger.info("✅ Настройки загружены")  
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
        if not data: return "ok", 200  
  
        if 'callback_query' in data:  
            cb = data['callback_query']  
            answer_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"  
            try:  
                requests.post(answer_url, json={  
                    "callback_query_id": cb.get('id', ''),  
                    "text": "✅ Принято!"  
                })  
            except Exception as e:  
                logger.error(f"Ответ: {e}")  
            return "ok", 200  
  
        if 'message' in data:  
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
                                msg = f"✅ <b>НАЙДЕНО: {len(top)}</b>\n\n"  
                                for i, m in enumerate(top[:15], 1):  
                                    b = m['best_bet']  
                                    bonus = b.get('anomaly_bonus', 0)  
                                    bonus_str = f" (+{bonus}% аномалия)" if bonus else ""  
                                    level = m.get('source', '')  
                                    lv = " 🔥 PREMIUM" if level == 'tm25_premium' else (" ⭐ STANDARD" if level == 'tm25_standard' else "")  
                                    msg += (f"{i}. <b>{m['home']} vs {m['away']}</b>{lv}\n"  
                                            f"🏆 {m.get('league', '?')}\n"  
                                            f"📅 {m.get('match_time', '?')}\n"  
                                            f"🎯 {b['label']} | КЭФ: {b['odds']} | EV: {b['ev']}%{bonus_str}\n"  
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
            elif text.startswith('/analyze '):  
                send_telegram(analyze_match(text[9:].strip()))  
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
                auto_bet.enabled = not auto_bet.enabled  
                send_telegram(handlers.handle_autobet(auto_bet.enabled))  
            elif text == '/status':  
                report = bot_state.get_status_report()  
                try:  
                    oh_size = storage.get_odds_history_size()  
                    report += (f"\n📊 История кэфов: {oh_size['matches']} матчей, "  
                               f"{oh_size['snapshots']} снимков, {oh_size['size_kb']} КБ")  
                except Exception as e:  
                    logger.error(f"Ошибка статуса: {e}")  
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
# API ЭНДПОИНТЫ  
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
        logger.error(f"❌ /api/all_data: {e}")  
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
  
  
@app.route('/api/snapshot', methods=['GET'])  
def api_snapshot():  
    try:  
        n = snapshot_odds_for_upcoming()  
        return jsonify({'status': 'ok', 'snapshots': n})  
    except Exception as e:  
        logger.exception("❌ /api/snapshot")  
        return jsonify({'status': 'error', 'message': str(e)}), 500  
  
  
@app.route('/api/keepalive', methods=['GET'])  
def keepalive():  
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})  
  
  
# ★★★ НОВЫЙ ЭНДПОИНТ: matches_log для авто-импорта X2 ★★★  
@app.route('/api/matches_log', methods=['GET'])  
def api_matches_log():  
    """Возвращает matches_log.txt для авто-импорта X2."""  
    try:  
        possible_paths = [  
            'matches_log.txt',  
            'data/matches_log.txt',  
            '/data/matches_log.txt',  
        ]  
        log_content = ''  
        for path in possible_paths:  
            if os.path.exists(path):  
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:  
                    log_content = f.read()  
                logger.info(f"📄 matches_log: {path} ({len(log_content)} символов)")  
                break  
  
        if not log_content:  
            return jsonify({'log': '', 'status': 'empty'})  
  
        return jsonify({  
            'log': log_content[-100000:],  
            'status': 'ok',  
            'size': len(log_content)  
        })  
    except Exception as e:  
        logger.error(f"❌ /api/matches_log: {e}")  
        return jsonify({'log': '', 'error': str(e)}), 500  
  
  
# ★★★ НОВЫЙ ЭНДПОИНТ: серверное хранилище X2 ★★★  
@app.route('/api/x2_data', methods=['GET'])  
def api_x2_data_get():  
    try:  
        if os.path.exists(X2_FILE):  
            with open(X2_FILE, 'r', encoding='utf-8') as f:  
                data = json.load(f)  
            return jsonify({'status': 'ok', 'data': data})  
        return jsonify({'status': 'ok', 'data': []})  
    except Exception as e:  
        logger.error(f"❌ Чтение X2: {e}")  
        return jsonify({'status': 'error', 'error': str(e)}), 500  
  
  
@app.route('/api/x2_data', methods=['POST'])  
def api_x2_data_post():  
    try:  
        data = request.json  
        if not data or 'data' not in data:  
            return jsonify({'error': 'No data'}), 400  
        os.makedirs(os.path.dirname(X2_FILE) or '.', exist_ok=True)  
        with open(X2_FILE, 'w', encoding='utf-8') as f:  
            json.dump(data['data'], f, ensure_ascii=False, indent=2)  
        logger.info(f"💾 X2 сохранено: {len(data['data'])} записей")  
        return jsonify({'status': 'ok', 'count': len(data['data'])})  
    except Exception as e:  
        logger.error(f"❌ Запись X2: {e}")  
        return jsonify({'status': 'error', 'error': str(e)}), 500  
  
  
# Импорт Excel / проекта  
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
                p = str(score).split('-')  
                try:  
                    hg = int(p[0].strip()); ag = int(p[1].strip())  
                except Exception: pass  
            history.append({  
                'home': home or 'Unknown', 'away': away or 'Unknown',  
                'league': 'Импорт Excel',  
                'bet': row.get('Ставка', '') or row.get('Bet', ''),  
                'odds': float(row.get('Коэф', 1.85)),  
                'stake': float(row.get('Сумма', 0)),  
                'ev': float(row.get('EV%', 0)),  
                'result': row.get('Результат', 'pending'),  
                'profit': float(row.get('Прибыль', 0)),  
                'date': row.get('Дата', '') or datetime.now().strftime('%Y-%m-%d %H:%M'),  
                'home_goals': hg, 'away_goals': ag,  
                'bookmaker': row.get('Букмекер', '—')  
            })  
            imported += 1  
        storage.save_history(history)  
        recalc_stats()  
        return jsonify({'success': True, 'count': imported})  
    except Exception as e:  
        logger.error(f"Ошибка импорта: {e}")  
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
        logger.error(f"Ошибка импорта: {e}")  
        return jsonify({'error': str(e)}), 500  
  
  
@app.route('/api/edit_bet', methods=['POST'])  
def edit_bet():  
    try:  
        data = request.json  
        index = data.get('index')  
        history = storage.load_history()  
        if index >= len(history):  
            return jsonify({'error': 'Не найдено'}), 404  
        for field in ['home', 'away', 'bet', 'odds', 'stake', 'ev', 'result', 'bookmaker']:  
            if field in data:  
                history[index][field] = data[field]  
        history[index]['home_goals'] = data.get('home_goals')  
        history[index]['away_goals'] = data.get('away_goals')  
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
        if index >= len(history):  
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
            except Exception: pass  
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
            'home': home or 'Unknown', 'away': away or 'Unknown',  
            'league': 'Ручное добавление',  
            'bet': bet_type, 'odds': odds, 'stake': stake, 'ev': 0,  
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
  
  
@app.route('/api/update_settings', methods=['POST'])  
def update_settings():  
    try:  
        data = request.json  
        with open('bot_settings.json', 'w') as f:  
            json.dump(data, f, indent=2)  
        for key, default in [  
            ('EV_MIN_70', 15), ('PROB_MIN_70', 55),  
            ('XG_MIN_70', 1.8), ('XG_MAX_70', 3.0),  
            ('POSITION_MAX_70', 15), ('PREMIUM_MIN_EV', 30),  
            ('STANDARD_MIN_EV', 15), ('TM25_XG_MIN', 0.8),  
            ('TM25_XG_MAX', 3.0), ('MAX_TM25_BETS', 5),  
        ]:  
            if key.lower() in data:  
                setattr(Config, key, data[key.lower()])  
        return jsonify({'success': True})  
    except Exception as e:  
        return jsonify({'error': str(e)}), 500  
  
  
@app.route('/health', methods=['GET'])  
def health():  
    return {"status": "ok", "time": datetime.now().isoformat()}  
  
  
@app.route('/', methods=['GET'])  
def index():  
    try:  
        return render_template('index.html')  
    except Exception:  
        return (f"🤖 Quantum Bet Bot PRO | "  
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")  
  
  
# ============================================================  
# ЗАПУСК  
# ============================================================  
if __name__ == "__main__":  
    os.makedirs('data', exist_ok=True)  
  
    setup_logging()  
    load_bot_settings()  
    Config.init_db()  
    start_scheduler()  
  
    schedule_updates()  
    schedule_notifications()  
    schedule_performance_report()  
    schedule_auto_backup()  
  
    odds_scheduler = BackgroundScheduler()  
    odds_scheduler.add_job(  
        func=snapshot_odds_for_upcoming,  
        trigger='interval', minutes=30,  
        id='odds_snapshot', replace_existing=True, max_instances=1  
    )  
    odds_scheduler.add_job(  
        func=lambda: storage.cleanup_old_odds_history(days=30),  
        trigger='cron', hour=4, minute=0,  
        id='odds_cleanup', replace_existing=True  
    )  
    odds_scheduler.start()  
    logger.info("📸 Снимки: 30 мин | Очистка: 4:00 МСК")  
  
    port = int(os.environ.get("PORT", 10000))  
  
    logger.info("=" * 60)  
    logger.info("🚀 QUANTUM BET BOT PRO ЗАПУЩЕН")  
    logger.info("=" * 60)  
    logger.info(f"📊 Лиг: {len(Config.LEAGUES)}")  
    logger.info(f"🧠 ENGINE: {Config.PREDICTION_ENGINE}")  
    logger.info(f"🤖 LLM: {'вкл' if Config.LLM_ENABLED else 'выкл'}")  
    logger.info(f"🚫 Blacklist: {len(Config.BLACKLIST_LEAGUES)}")  
    logger.info(f"🌦️ Погода: {'вкл' if Config.WEATHER_ENABLED else 'выкл'}")  
    logger.info(f"📈 Stats: {'вкл' if getattr(Config, 'STATS_ENABLED', True) else 'выкл'}")  
    logger.info(f"✅ Новые эндпоинты: /api/matches_log, /api/x2_data")  
    logger.info(f"📄 matches_log пишется при 'нет мотивации'")  
    logger.info("=" * 60)  
  
    app.run(host='0.0.0.0', port=port)
