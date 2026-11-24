# ============================================================
# botcore/football_api.py — Клиенты API-Football и Odds API
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

__all__ = [
    'FootballAPI',
    'football_api',
    'OddsAPIClient',
    'odds_api',
]


# ============================================================
# FOOTBALL API
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or Config.FOOTBALL_API_URL
        self.cache = SmartCache(max_size=2000)
        self.last_request_time = 0
        self.min_request_interval = 0.4
        self.rate_limiter = APIRateLimiter(max_requests=400, time_window=60)
        self.retry_manager = RetryManager(max_retries=3, base_delay=1)
        self.error_stats = defaultdict(int)
        if self.api_key and len(self.api_key) > 10:
            logger.info(f"🔑 Football API: {self.api_key[:8]}...{self.api_key[-4:]}")
        else:
            logger.error("❌ FOOTBALL_API_KEY НЕ НАЙДЕН!")

    def _count_usage(self, endpoint):
        """Счётчик расхода API за сутки по задаче (имя функции-вызывающего) и адресу — для диагностики лимита."""
        try:
            import sys
            f = sys._getframe(2)
            caller = '?'
            while f is not None:
                mod = f.f_globals.get('__name__', '')
                if mod not in (__name__, 'botcore.football_api'):
                    caller = f"{mod.split('.')[-1]}.{f.f_code.co_name}"
                    break
                f = f.f_back
            day = time.strftime('%Y-%m-%d', time.gmtime())
            if getattr(self, '_usage_day', None) != day:
                self._usage_day = day
                self.usage = defaultdict(int)
            self.usage[f"{caller} {endpoint}"] += 1
        except Exception:
            pass

    def _make_request(self, endpoint, params=None):
        self._count_usage(endpoint)
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
            try:   # остаток лимита API-Football для вкладки «Состояние бота»
                self.quota = {'remaining': r.headers.get('x-ratelimit-requests-remaining'),
                              'limit': r.headers.get('x-ratelimit-requests-limit')}
            except Exception:
                pass
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
    def get_team_stats_avg(self, team_id):
        """Возвращает среднее кол-во угловых и карточек за последние 5 матчей."""
        cache_key = f"team_stats_avg_{team_id}"
        cached = self.cache.get(cache_key, data_type='statistics')
        if cached is not None:
            return cached
        
        try:
            # Берем последние 5 матчей
            data = self._make_request('/fixtures', {'team': team_id, 'last': 5, 'status': 'FT'})
            if not data or 'response' not in data:
                return None
            
            matches = data['response']
            if not matches:
                return None

            corners_list = []
            cards_list = []

            for m in matches:
                fid = m.get('fixture', {}).get('id')
                if not fid: continue
                
                # Запрашиваем статистику матча
                stats = self.get_match_statistics(fid)
                if not stats: continue

                # Находим статистику нужной команды
                team_stats = None
                for tn, ts in stats.items():
                    # Проверяем совпадение по ID или имени
                    if tn == m.get('teams', {}).get('home', {}).get('name') and m.get('teams', {}).get('home', {}).get('id') == team_id:
                        team_stats = ts
                        break
                    elif tn == m.get('teams', {}).get('away', {}).get('name') and m.get('teams', {}).get('away', {}).get('id') == team_id:
                        team_stats = ts
                        break
                
                if team_stats:
                    corners = team_stats.get('Corner Kicks', 0)
                    cards = team_stats.get('Yellow Cards', 0)
                    # Иногда API отдает карточки как 'Yellow Cards' или 'Yellow Card'
                    if cards == 0:
                        cards = team_stats.get('Yellow Card', 0)
                    
                    if corners > 0:
                        corners_list.append(float(corners))
                    if cards > 0:
                        cards_list.append(float(cards))

            if not corners_list and not cards_list:
                return None

            result = {
                'corners_avg': round(sum(corners_list) / len(corners_list), 1) if corners_list else 0,
                'cards_avg': round(sum(cards_list) / len(cards_list), 1) if cards_list else 0,
                'matches_count': len(matches)
            }
            
            self.cache.set(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Ошибка get_team_stats_avg {team_id}: {e}")
            return None

    @timing_decorator()
    def get_form(self, team_id):
        # ★ УСКОРЕНО: убрали лишние проверки xG, чтобы не тратить 3 секунды на команду
        cache_key = f"form_{team_id}"
        cached = self.cache.get(cache_key, data_type='form')
        if cached is not None:
            return cached
        try:
            data = self._make_request('/fixtures', {'team': team_id, 'last': 5, 'status': 'FT'})
            if data and 'response' in data:
                matches = data['response']
                if matches:
                    goals_scored = []
                    goals_conceded = []
                    w = d = l = 0
                    for m in matches:
                        goals = m.get('goals', {})
                        teams = m.get('teams', {})
                        is_home = teams.get('home', {}).get('id') == team_id
                        if is_home:
                            s, c = goals.get('home', 0) or 0, goals.get('away', 0) or 0
                        else:
                            s, c = goals.get('away', 0) or 0, goals.get('home', 0) or 0
                        goals_scored.append(s)
                        goals_conceded.append(c)
                        if s > c: w += 1
                        elif s == c: d += 1
                        else: l += 1
                    result = {
                        'goals_avg': round(sum(goals_scored) / len(goals_scored), 2),
                        'conceded_avg': round(sum(goals_conceded) / len(goals_conceded), 2),
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
            
           # ★ ДОБАВЛЕНО ДЛЯ ОТЛАДКИ:
            if len(data['response']) == 0:
                logger.warning(f"⚠️ API вернул 0 кэфов для лиги {league_id} на {date}")
            else:
                logger.info(f"✅ API вернул {len(data['response'])} матчей с кэфами для лиги {league_id} на {date}")
            # ★ КОНЕЦ ОТЛАДКИ

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

    def get_odds_fresh_for_league(self, league_id, date):
        """Свежие кэфы лиги на дату БЕЗ кэша и с пагинацией
        (/odds отдаёт ~10 матчей на страницу). -> {fixture_id: odds_dict}"""
        result = {}
        page = 1
        while page <= 10:
            data = self._make_request('/odds', {
                'league': league_id, 'season': Config.USE_SEASON,
                'date': date, 'page': page,
            })
            if not data or 'response' not in data:
                break
            for item in data['response']:
                fid = (item.get('fixture') or {}).get('id')
                bms = item.get('bookmakers') or []
                if fid and bms:
                    result[fid] = self._extract_best_odds(bms)
            try:
                total = int((data.get('paging') or {}).get('total', 1) or 1)
            except Exception:
                total = 1
            if page >= total:
                break
            page += 1
        return result

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
# ODDS API
# ============================================================
class OddsAPIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or getattr(Config, 'ODDS_API_KEY', None)
        self.base_url = getattr(Config, 'ODDS_API_URL', 'https://api.the-odds-api.com/v4')
        self.cache = {}
        self.remaining = None
        self.active = bool(self.api_key and len(self.api_key) > 10)
        self.daily_requests_made = 0
        self.last_reset_date = datetime.now().date()

        if self.active:
            logger.info(f"✅ Odds API: {self.api_key[:8]}...{self.api_key[-4:]}")
            try:
                r = requests.get(
                    f'{self.base_url}/sports',
                    params={'apiKey': self.api_key},
                    timeout=10
                )
                if r.status_code == 200:
                    self.remaining = r.headers.get('x-requests-remaining')
                    logger.info(f"📊 Odds API: осталось запросов {self.remaining}")
                else:
                    logger.warning(f"Odds API quota check HTTP {r.status_code}")
            except Exception as e:
                logger.warning(f"Odds API quota: {e}")
        else:
            logger.info("⚠️ Odds API: ключ не задан — fallback отключён")

    def get_odds_for_match(self, home_team, away_team, league, sport='soccer'):
        if not self.active:
            return None
        if self.remaining is not None and int(self.remaining) <= 0:
            self.active = False
            logger.warning("🛑 Odds API: запросы исчерпаны — отключён")
            return None

        try:
            cache_key = f"{home_team}_{away_team}"
            if cache_key in self.cache:
                return self.cache[cache_key]

            url = f'{self.base_url}/sports/{sport}/odds'
            params = {
                'apiKey': self.api_key,
                'regions': 'eu',
                'markets': 'h2h',
                'oddsFormat': 'decimal',
            }
            r = requests.get(url, params=params, timeout=15)

            remaining = r.headers.get('x-requests-remaining')
            if remaining is not None:
                self.remaining = remaining
                if int(remaining) <= 5:
                    logger.warning(f"⚠️ Odds API: осталось {remaining} — автоотключение")

            if r.status_code != 200:
                logger.error(f"Odds API HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code == 429:
                    self.active = False
                return None

            data = r.json()
            for match in data:
                if (match.get('home_team') == home_team and
                        match.get('away_team') == away_team):
                    best_home, best_draw, best_away = 0, 0, 0
                    for bm in match.get('bookmakers', []):
                        for market in bm.get('markets', []):
                            if market.get('key') == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    odd = outcome.get('price', 0)
                                    name = outcome.get('name', '')
                                    if name == home_team:
                                        best_home = max(best_home, odd)
                                    elif name == away_team:
                                        best_away = max(best_away, odd)
                                    elif name == 'Draw':
                                        best_draw = max(best_draw, odd)
                    result = {
                        'home_odds': best_home,
                        'draw_odds': best_draw,
                        'away_odds': best_away,
                        'best_odds': max(best_home, best_draw, best_away),
                        'bookmaker': 'Odds API',
                        'source': 'odds_api',
                    }
                    self.cache[cache_key] = result
                    return result
            return None
        except Exception as e:
            logger.error(f"Odds API error: {e}")
            return None

    def get_stats_odds_for_match(self, home_team, away_team, league, market_type='totals_corners'):
        if self.last_reset_date != datetime.now().date():
            self.daily_requests_made = 0
            self.last_reset_date = datetime.now().date()
        
        limit = getattr(Config, 'ODDS_API_DAILY_LIMIT', 15)
        if self.daily_requests_made >= limit:
            return None

        if not self.active:
            return None
        if self.remaining is not None and int(self.remaining) <= 0:
            self.active = False
            return None

        try:
            url = f'{self.base_url}/sports/soccer/odds'
            params = {
                'apiKey': self.api_key,
                'regions': 'eu',
                'markets': market_type,
                'oddsFormat': 'decimal',
            }
            r = requests.get(url, params=params, timeout=15)
            self.daily_requests_made += 1 
            
            if r.status_code != 200:
                return None

            data = r.json()
            for match in data:
                if (match.get('home_team') == home_team and match.get('away_team') == away_team):
                    best_over, best_under = 0, 0
                    for bm in match.get('bookmakers', []):
                        for market in bm.get('markets', []):
                            if market.get('key') == market_type:
                                for outcome in market.get('outcomes', []):
                                    odd = outcome.get('price', 0)
                                    name = outcome.get('name', '')
                                    point = outcome.get('point', 0)
                                    target_point = 9.5 if market_type == 'totals_corners' else 4.5
                                    
                                    if point == target_point:
                                        if name == 'Over':
                                            best_over = max(best_over, odd)
                                        elif name == 'Under':
                                            best_under = max(best_under, odd)
                    if best_over > 0 or best_under > 0:
                        return {
                            'over_odds': best_over,
                            'under_odds': best_under,
                            'bookmaker': 'Odds API',
                            'source': market_type
                        }
            return None
        except Exception as e:
            logger.error(f"Stats Odds API error: {e}")
            return None
       

    def should_use_as_fallback(self):
        return self.active and (self.remaining is None or int(self.remaining) > 0)


odds_api = OddsAPIClient()
