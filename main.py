import sys
import os
import requests
import time
import json
import logging
import random
import math
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ============================================================
# ИМПОРТЫ ИЗ ПРОЕКТА (С app.)
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
TIMEZONE_OFFSET = 3

# ============================================================
# МАРКЕРЫ (ТОЛЬКО ОДИН - 000006)
# ============================================================
MARKERS = {
    42.86875000000006: ('under', 1.95, 'ТМ 2.5'),
}

TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

# ============================================================
# ДОМАШНЕЕ ПРЕИМУЩЕСТВО ПО ЛИГАМ
# ============================================================
HOME_ADVANTAGE = {
    'Premier League': 1.15,
    'La Liga': 1.12,
    'Bundesliga': 1.18,
    'Serie A': 1.10,
    'Ligue 1': 1.13,
    'Championship': 1.12,
    '2. Bundesliga': 1.15,
    'Eredivisie': 1.14,
    'Primeira Liga': 1.11,
    'Süper Lig': 1.16,
}

# ============================================================
# ЗАПАСНЫЕ ЗНАЧЕНИЯ XG
# ============================================================
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
# КЛАСС FOOTBALL_API
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 0.3
        
        logger.info(f"🔑 API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")
        
    def _make_request(self, endpoint, params=None):
        try:
            now = time.time()
            if now - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (now - self.last_request_time))
            
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            
            url = f"{self.base_url}{endpoint}"
            logger.info(f"📡 Запрос: {endpoint}")
            logger.info(f"📡 Параметры: {params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            self.last_request_time = time.time()
            
            logger.info(f"📡 Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('errors'):
                    logger.error(f"❌ API ошибка: {data['errors']}")
                    return None
                if 'response' in data:
                    logger.info(f"📡 Получено записей: {len(data['response'])}")
                return data
            else:
                logger.error(f"❌ API ошибка {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка запроса к API: {e}")
            return None
    
    def get_matches(self, league_id, date):
        cache_key = f"matches_{league_id}_{date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        params = {
            'league': league_id,
            'season': datetime.now().year,
            'date': date
        }
        data = self._make_request('/fixtures', params)
        
        if data and 'response' in data:
            matches = data['response']
            self.cache[cache_key] = matches
            return matches
        
        return []
    
    def get_form(self, team_id):
        cache_key = f"form_{team_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {
                'team': team_id,
                'last': 5,
                'status': 'FT'
            }
            data = self._make_request('/fixtures', params)
            
            if data and 'response' in data:
                matches = data['response']
                if matches:
                    goals_scored = []
                    goals_conceded = []
                    wins = 0
                    draws = 0
                    losses = 0
                    
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
                        
                        if scored > conceded:
                            wins += 1
                        elif scored == conceded:
                            draws += 1
                        else:
                            losses += 1
                    
                    if goals_scored:
                        result = {
                            'goals_avg': round(sum(goals_scored) / len(goals_scored), 2),
                            'conceded_avg': round(sum(goals_conceded) / len(goals_conceded), 2),
                            'wins': wins,
                            'draws': draws,
                            'losses': losses,
                            'matches': len(matches),
                            'form': self._calculate_form(matches, team_id)
                        }
                        self.cache[cache_key] = result
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
                if home_score > away_score:
                    form.append('W')
                elif home_score == away_score:
                    form.append('D')
                else:
                    form.append('L')
            else:
                if away_score > home_score:
                    form.append('W')
                elif away_score == home_score:
                    form.append('D')
                else:
                    form.append('L')
        return ''.join(form)
    
    def get_match_statistics(self, fixture_id):
        cache_key = f"stats_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'fixture': fixture_id}
            data = self._make_request('/fixtures/statistics', params)
            
            if data and 'response' in data:
                statistics = {}
                for team_stats in data['response']:
                    team_name = team_stats.get('team', {}).get('name', 'Unknown')
                    stats = {}
                    
                    for stat in team_stats.get('statistics', []):
                        key = stat.get('type', '')
                        value = stat.get('value', 0)
                        
                        if value is None:
                            value = 0
                        elif isinstance(value, str):
                            if '%' in value:
                                try:
                                    value = float(value.replace('%', ''))
                                except:
                                    value = 0
                            else:
                                try:
                                    value = float(value)
                                except:
                                    value = 0
                        elif isinstance(value, (int, float)):
                            value = float(value)
                        else:
                            value = 0
                        
                        stats[key] = value
                    
                    statistics[team_name] = stats
                
                self.cache[cache_key] = statistics
                return statistics
            else:
                logger.warning(f"⚠️ API вернул пустой ответ для /fixtures/statistics")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики матча {fixture_id}: {e}")
        
        return None
    
    def get_standings(self, league_id):
        cache_key = f"standings_{league_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {
                'league': league_id,
                'season': datetime.now().year
            }
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
                self.cache[cache_key] = standings
                return standings
                
        except Exception as e:
            logger.error(f"Ошибка получения таблицы {league_id}: {e}")
        
        return None
    
    def get_injuries(self, team_id):
        cache_key = f"injuries_{team_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {
                'team': team_id,
                'season': datetime.now().year
            }
            data = self._make_request('/injuries', params)
            
            if data and 'response' in data:
                injuries = data['response']
                self.cache[cache_key] = injuries
                return injuries
                
        except Exception as e:
            logger.error(f"Ошибка получения травм команды {team_id}: {e}")
        
        return []
    
    def get_match_result(self, fixture_id):
        cache_key = f"result_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'id': fixture_id}
            data = self._make_request('/fixtures', params)
            
            if data and 'response' in data:
                fixtures = data['response']
                if fixtures:
                    fixture = fixtures[0]
                    goals = fixture.get('goals', {})
                    result = {
                        'goals': {
                            'home': goals.get('home'),
                            'away': goals.get('away')
                        },
                        'status': fixture.get('status', {}).get('short', 'FT')
                    }
                    self.cache[cache_key] = result
                    return result
                    
        except Exception as e:
            logger.error(f"Ошибка получения результата {fixture_id}: {e}")
        
        return None
    
    def find_fixture_by_teams(self, home_team, away_team):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            params = {
                'date': today,
                'status': 'FT'
            }
            data = self._make_request('/fixtures', params)
            
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
    
    def get_head_to_head(self, home_team, away_team):
        """Получает историю личных встреч"""
        cache_key = f"h2h_{home_team}_{away_team}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            home_id = self.get_team_id(home_team)
            away_id = self.get_team_id(away_team)
            
            if home_id and away_id:
                params = {
                    'h2h': f"{home_id}-{away_id}",
                    'last': 5
                }
                data = self._make_request('/fixtures/headtohead', params)
                
                if data and 'response' in data:
                    fixtures = data['response']
                    if fixtures:
                        result = {
                            'matches': [],
                            'home_wins': 0,
                            'away_wins': 0,
                            'draws': 0,
                            'goals_scored': 0,
                            'goals_conceded': 0
                        }
                        
                        for fixture in fixtures:
                            teams = fixture.get('teams', {})
                            goals = fixture.get('goals', {})
                            
                            home_score = goals.get('home', 0) or 0
                            away_score = goals.get('away', 0) or 0
                            
                            result['matches'].append({
                                'home': teams.get('home', {}).get('name', ''),
                                'away': teams.get('away', {}).get('name', ''),
                                'home_score': home_score,
                                'away_score': away_score
                            })
                            
                            if home_score > away_score:
                                result['home_wins'] += 1
                            elif home_score < away_score:
                                result['away_wins'] += 1
                            else:
                                result['draws'] += 1
                            
                            result['goals_scored'] += home_score
                            result['goals_conceded'] += away_score
                        
                        if result['matches']:
                            total_matches = len(result['matches'])
                            result['avg_goals'] = round((result['goals_scored'] + result['goals_conceded']) / total_matches, 2)
                            result['home_win_rate'] = round((result['home_wins'] / total_matches) * 100, 1)
                            result['total_matches'] = total_matches
                            
                            self.cache[cache_key] = result
                            return result
                    else:
                        logger.warning(f"⚠️ Нет данных H2H для {home_team} vs {away_team}")
            else:
                logger.warning(f"⚠️ Не найдены ID команд для H2H")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения H2H: {e}")
        
        return None
    
    def get_team_id(self, team_name):
        """Получает ID команды по названию"""
        cache_key = f"team_id_{team_name}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'name': team_name}
            data = self._make_request('/teams', params)
            
            if data and 'response' in data:
                for team in data['response']:
                    team_data = team.get('team', {})
                    if team_data.get('name', '').lower() == team_name.lower():
                        team_id = team_data.get('id')
                        self.cache[cache_key] = team_id
                        return team_id
                        
        except Exception as e:
            logger.error(f"Ошибка получения ID команды {team_name}: {e}")
        
        return None
    
    def clear_cache(self):
        self.cache = {}
        logger.info("🧹 Кэш очищен")

# ============================================================
# КЛАСС ODD_API
# ============================================================

class OddsAPIClient:
    def __init__(self, api_key=None):
        from app.config import Config
        self.api_key = api_key or Config.ODDS_API_KEY
        self.base_url = Config.ODDS_API_URL
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 0.5
        
        logger.info(f"🎯 Odds API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ Odds API КЛЮЧ НЕ НАЙДЕН!")
    
    def _make_request(self, endpoint, params=None):
        """Выполняет запрос к Odds API"""
        try:
            now = time.time()
            if now - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (now - self.last_request_time))
            
            url = f"{self.base_url}{endpoint}"
            params = params or {}
            params['apiKey'] = self.api_key
            
            logger.info(f"📡 Запрос Odds API: {url}")
            logger.info(f"📡 Параметры: {params}")
            
            response = requests.get(url, params=params, timeout=10)
            self.last_request_time = time.time()
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Odds API ошибка {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка запроса Odds API: {e}")
            return None
    
    def get_odds_for_match(self, home_team, away_team, league):
        """Получает коэффициенты для конкретного матча"""
        cache_key = f"{home_team}_{away_team}_{league}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            sport_map = {
                'АПЛ': 'soccer_epl',
                'Premier League': 'soccer_epl',
                'Чемпионшип': 'soccer_efl_champ',
                'Championship': 'soccer_efl_champ',
                'League 1': 'soccer_england_league1',
                'League 2': 'soccer_england_league2',
                'Ла Лига': 'soccer_spain_la_liga',
                'La Liga': 'soccer_spain_la_liga',
                'Сегунда': 'soccer_spain_segunda_division',
                'La Liga 2': 'soccer_spain_segunda_division',
                'Бундеслига': 'soccer_germany_bundesliga',
                'Bundesliga': 'soccer_germany_bundesliga',
                'Вторая Бундеслига': 'soccer_germany_bundesliga2',
                '2. Bundesliga': 'soccer_germany_bundesliga2',
                '3. Лига': 'soccer_germany_liga3',
                '3. Liga': 'soccer_germany_liga3',
                'Кубок Германии': 'soccer_germany_dfb_pokal',
                'DFB-Pokal': 'soccer_germany_dfb_pokal',
                'Серия А': 'soccer_italy_serie_a',
                'Serie A': 'soccer_italy_serie_a',
                'Серия B': 'soccer_italy_serie_b',
                'Serie B': 'soccer_italy_serie_b',
                'Лига 1': 'soccer_france_ligue_one',
                'Ligue 1': 'soccer_france_ligue_one',
                'Лига 2': 'soccer_france_ligue_two',
                'Ligue 2': 'soccer_france_ligue_two',
                'MLS': 'soccer_usa_mls',
                'МЛС': 'soccer_usa_mls',
                'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
                'UEFA Champions League': 'soccer_uefa_champs_league',
                'Лига Европы УЕФА': 'soccer_uefa_europa_league',
                'UEFA Europa League': 'soccer_uefa_europa_league',
                'Лига Наций УЕФА': 'soccer_uefa_nations_league',
                'UEFA Nations League': 'soccer_uefa_nations_league',
                'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
                'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
                'Копа Судамерикана': 'soccer_conmebol_copa_sudamericana',
                'Copa Sudamericana': 'soccer_conmebol_copa_sudamericana',
                'Бразилия Серия А': 'soccer_brazil_campeonato',
                'Brasileirão': 'soccer_brazil_campeonato',
                'Бразилия Серия B': 'soccer_brazil_serie_b',
                'Brasileirão Série B': 'soccer_brazil_serie_b',
                'Аргентина Примера': 'soccer_argentina_primera_division',
                'Primera División': 'soccer_argentina_primera_division',
                'Чили Примера': 'soccer_chile_campeonato',
                'Campeonato Chileno': 'soccer_chile_campeonato',
                'Leagues Cup': 'soccer_concacaf_leagues_cup',
                'Эредивизи': 'soccer_netherlands_eredivisie',
                'Eredivisie': 'soccer_netherlands_eredivisie',
                'Примейра Лига': 'soccer_portugal_primeira_liga',
                'Primeira Liga': 'soccer_portugal_primeira_liga',
                'Супер Лига': 'soccer_turkey_super_league',
                'Super Lig': 'soccer_turkey_super_league',
                'РПЛ': 'soccer_russia_premier_league',
                'Russian Premier League': 'soccer_russia_premier_league',
                'Австрия Бундеслига': 'soccer_austria_bundesliga',
                'Austrian Bundesliga': 'soccer_austria_bundesliga',
                'Бельгия Первый Дивизион': 'soccer_belgium_first_div',
                'Belgian First Division': 'soccer_belgium_first_div',
                'Дания Суперлига': 'soccer_denmark_superliga',
                'Danish Superliga': 'soccer_denmark_superliga',
                'Финляндия Вейккауслиига': 'soccer_finland_veikkausliiga',
                'Veikkausliiga': 'soccer_finland_veikkausliiga',
                'Греция Супер Лига': 'soccer_greece_super_league',
                'Greek Super League': 'soccer_greece_super_league',
                'Норвегия Элитсериен': 'soccer_norway_eliteserien',
                'Eliteserien': 'soccer_norway_eliteserien',
                'Польша Экстракласа': 'soccer_poland_ekstraklasa',
                'Ekstraklasa': 'soccer_poland_ekstraklasa',
                'Шотландия Премьершип': 'soccer_spl',
                'Scottish Premiership': 'soccer_spl',
                'Швеция Аллсвенскан': 'soccer_sweden_allsvenskan',
                'Allsvenskan': 'soccer_sweden_allsvenskan',
                'Швеция Суперэттан': 'soccer_sweden_superettan',
                'Superettan': 'soccer_sweden_superettan',
                'Швейцария Суперлига': 'soccer_switzerland_superleague',
                'Swiss Super League': 'soccer_switzerland_superleague',
                'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
                'Saudi Pro League': 'soccer_saudi_arabia_pro_league',
                'Япония J1 Лига': 'soccer_japan_j_league',
                'J1 League': 'soccer_japan_j_league',
                'Корея K Лига 1': 'soccer_korea_kleague1',
                'K League 1': 'soccer_korea_kleague1',
                'Мексика Liga MX': 'soccer_mexico_ligamx',
                'Liga MX': 'soccer_mexico_ligamx',
            }
            
            sport_key = sport_map.get(league, 'soccer_epl')
            
            if 'MLS' in league or 'МЛС' in league:
                region = 'us'
            elif 'Бразилия' in league or 'Brasileirão' in league:
                region = 'us'
            elif 'Аргентина' in league or 'Argentina' in league:
                region = 'us'
            elif 'Мексика' in league or 'Mexico' in league:
                region = 'us'
            else:
                region = 'eu'
            
            endpoint = f"/sports/{sport_key}/events"
            params = {
                'region': region,
                'markets': 'h2h'
            }
            
            logger.info(f"📡 Запрос Odds API: {endpoint}")
            logger.info(f"📡 Лига: {league} → {sport_key}, регион: {region}")
            
            data = self._make_request(endpoint, params)
            
            if data:
                logger.info(f"📡 Получено событий: {len(data)}")
                for event in data:
                    event_home = event.get('home_team', '').lower()
                    event_away = event.get('away_team', '').lower()
                    home_lower = home_team.lower()
                    away_lower = away_team.lower()
                    
                    if (home_lower in event_home or event_home in home_lower) and \
                       (away_lower in event_away or event_away in away_lower):
                        
                        result = self._extract_odds(event)
                        self.cache[cache_key] = result
                        logger.info(f"✅ Найдены коэффициенты для {home_team} vs {away_team}")
                        return result
                
                logger.info(f"⚠️ Матч {home_team} vs {away_team} не найден в Odds API")
            else:
                logger.info(f"⚠️ Нет данных от Odds API для {league}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения коэффициентов: {e}")
            return None
    
    def _extract_odds(self, event):
        """Извлекает коэффициенты из события"""
        result = {
            'best_odds': 0,
            'bookmaker': None,
            'bookmaker_name': '—',
            'home_odds': 0,
            'draw_odds': 0,
            'away_odds': 0
        }
        
        for bookmaker in event.get('bookmakers', []):
            bookmaker_key = bookmaker.get('key', '')
            
            for market in bookmaker.get('markets', []):
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
                            result['bookmaker'] = bookmaker_key
                            result['bookmaker_name'] = self._get_bookmaker_name(bookmaker_key)
        
        return result
    
    def _get_bookmaker_name(self, key):
        names = {
            'bet365': 'bet365',
            'pinnacle': 'Pinnacle',
            'betfair': 'Betfair',
            'unibet': 'Unibet',
            'draftkings': 'DraftKings',
            'fanduel': 'FanDuel',
            '1xbet': '1xBet',
            'bwin': 'Bwin',
            'williamhill': 'William Hill',
            'ladbrokes': 'Ladbrokes',
            'betway': 'Betway',
            '888sport': '888sport',
            'betsson': 'Betsson',
            'comeon': 'ComeOn',
            'marathonbet': 'Marathonbet',
        }
        return names.get(key, key)

# ============================================================
# СОЗДАЕМ ЭКЗЕМПЛЯРЫ
# ============================================================
football_api = FootballAPI()
odds_api = OddsAPIClient()

# ============================================================
# КЛАСС AUTOBET
# ============================================================
class AutoBet:
    def __init__(self):
        self.enabled = True
        self.bets_today = 0
        self.max_bets_per_day = 10
        
    def check_and_bet(self, match_data):
        if not self.enabled:
            logger.warning("⚠️ AutoBet отключен")
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
            'marker_stake': best_bet.get('marker_stake', 0),
            'xg_total': match_data.get('total_xg', 0),
            'prob': best_bet.get('prob', 0),
            'home_form': match_data.get('home_form', ''),
            'away_form': match_data.get('away_form', ''),
            'home_position': match_data.get('standings', {}).get('home_position', '?'),
            'away_position': match_data.get('standings', {}).get('away_position', '?'),
            'bookmaker': best_bet.get('bookmaker', '—'),
            'bet_type': best_bet.get('type', 'under'),
            'is_over': best_bet.get('is_over', False),
            'source': match_data.get('source', '70_percent')
        }

auto_bet = AutoBet()

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def send_error_to_telegram(error_text: str):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        if len(error_text) > 4000:
            error_text = error_text[:4000] + "...(обрезано)"
        data = {
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': f"❌ <b>ОШИБКА БОТА</b>\n\n{error_text}",
            'parse_mode': 'HTML'
        }
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Не удалось отправить ошибку в Telegram: {e}")

def send_telegram(text: str, parse_mode: str = 'HTML'):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': text,
            'parse_mode': parse_mode
        }
        response = requests.post(url, json=data, timeout=10)
        if response.status_code != 200:
            logger.error(f"❌ Ошибка отправки: {response.text}")
    except Exception as e:
        logger.error(f"❌ Send error: {e}")
        send_error_to_telegram(f"Ошибка отправки в Telegram: {e}")

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
        column_letter = chr(64 + col)
        ws.column_dimensions[column_letter].width = 15
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output, f"✅ Экспорт завершен! Всего ставок: {len(history)}, Прибыль: ${round(total_profit, 2)}"

def get_profit_data(history):
    """Формирует данные для графика прибыли"""
    profits = []
    days = 7
    
    for i in range(days - 1, -1, -1):
        day_profit = 0
        day = datetime.now() - timedelta(days=i)
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bet_date.date() == day.date():
                    stake = bet.get('stake', 0)
                    if isinstance(stake, str):
                        try:
                            stake = float(stake)
                        except:
                            stake = 0
                    odds = bet.get('odds', 1)
                    if isinstance(odds, str):
                        try:
                            odds = float(odds)
                        except:
                            odds = 1
                    
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
# НОВЫЕ ФУНКЦИИ ДЛЯ УЛУЧШЕНИЙ
# ============================================================

def get_motivation(position):
    """Определяет мотивацию команды по позиции в таблице"""
    if position <= 4:
        return 'champions_league'
    elif position <= 6:
        return 'europa_league'
    elif position <= 17:
        return 'mid_table'
    else:
        return 'relegation'

def analyze_form(form_string):
    """Анализирует форму команды (последние 5 матчей)"""
    if not form_string:
        return 'average'
    wins = form_string.count('W')
    if wins >= 4:
        return 'excellent'
    elif wins >= 3:
        return 'good'
    elif wins >= 2:
        return 'average'
    else:
        return 'poor'

def is_quality_match(home_xg, away_xg, home_position, away_position, home_form, away_form):
    """Проверяет, является ли матч качественным для ставки"""
    try:
        total_xg = home_xg + away_xg
        conditions = [
            total_xg > 1.5,
            total_xg < 3.5,
            home_position < 20,
            away_position < 20,
            len(home_form) >= 3,
            len(away_form) >= 3,
        ]
        return all(conditions)
    except:
        return False

def calculate_poisson_probability(home_xg, away_xg):
    """Рассчитывает вероятности по распределению Пуассона"""
    def poisson_prob(avg, goals):
        return (math.exp(-avg) * avg ** goals) / math.factorial(goals)
    
    home_goals_prob = [poisson_prob(home_xg, i) for i in range(6)]
    away_goals_prob = [poisson_prob(away_xg, i) for i in range(6)]
    
    prob_home_win = 0
    prob_away_win = 0
    prob_draw = 0
    prob_1X = 0
    prob_X2 = 0
    prob_over_2_5 = 0
    prob_under_2_5 = 0
    prob_btts = 0
    
    for h_g in range(6):
        for a_g in range(6):
            p = home_goals_prob[h_g] * away_goals_prob[a_g]
            total_goals = h_g + a_g
            
            if h_g > a_g:
                prob_home_win += p
            elif h_g < a_g:
                prob_away_win += p
            else:
                prob_draw += p
            
            if h_g >= a_g:
                prob_1X += p
            if a_g >= h_g:
                prob_X2 += p
            
            if total_goals > 2.5:
                prob_over_2_5 += p
            else:
                prob_under_2_5 += p
            
            if h_g > 0 and a_g > 0:
                prob_btts += p
    
    return {
        'home_win': prob_home_win,
        'away_win': prob_away_win,
        'draw': prob_draw,
        '1X': prob_1X,
        'X2': prob_X2,
        'over_2_5': prob_over_2_5,
        'under_2_5': prob_under_2_5,
        'btts': prob_btts
    }

def calculate_form_probability(home_form, away_form):
    """Рассчитывает вероятности на основе формы команд"""
    home_form_quality = analyze_form(home_form)
    away_form_quality = analyze_form(away_form)
    
    prob = {
        'home_win': 0.35,
        'away_win': 0.30,
        'draw': 0.35,
        '1X': 0.70,
        'X2': 0.65,
        'over_2_5': 0.45,
        'under_2_5': 0.55,
        'btts': 0.45
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
    """Рассчитывает вероятности на основе личных встреч"""
    prob = {
        'home_win': 0.33,
        'away_win': 0.33,
        'draw': 0.34,
        '1X': 0.67,
        'X2': 0.67,
        'over_2_5': 0.50,
        'under_2_5': 0.50,
        'btts': 0.50
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
    """Ансамбль моделей - комбинирует все методы"""
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
# ФУНКЦИЯ РУЧНОГО ОБНОВЛЕНИЯ РЕЗУЛЬТАТА
# ============================================================

def update_manual_result(match_name, score):
    """Ручное обновление результата матча"""
    try:
        home_goals = None
        away_goals = None
        if score and '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0].strip())
                away_goals = int(parts[1].strip())
            except:
                return "❌ Неверный формат счета. Используй: 2-1"
        
        history = storage.load_history()
        found = False
        result = 'pending'
        
        for bet in history:
            if bet.get('result') == 'pending' or bet.get('result') is None:
                home = bet.get('home', '')
                away = bet.get('away', '')
                full_match = f"{home} vs {away}"
                
                if match_name.lower() in full_match.lower() or full_match.lower() in match_name.lower():
                    bet['home_goals'] = home_goals
                    bet['away_goals'] = away_goals
                    
                    bet_type = bet.get('bet', '')
                    result = determine_bet_result(bet_type, home_goals, away_goals)
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
            
            msg = f"✅ Результат обновлен!\n"
            msg += f"🏟️ {match_name}\n"
            msg += f"⚽ Счет: {home_goals}-{away_goals}\n"
            msg += f"📊 Результат: {result}"
            return msg
        else:
            return f"❌ Матч '{match_name}' не найден в истории или уже завершен"
            
    except Exception as e:
        logger.error(f"Ошибка ручного обновления: {e}")
        return f"❌ Ошибка: {e}"

# ============================================================
# ФУНКЦИЯ АНАЛИЗА МАТЧА
# ============================================================

def analyze_match(match_name):
    """Анализирует конкретный матч и возвращает лучшую ставку"""
    try:
        cache = storage.load_cache()
        matches = cache.get('top_matches', [])
        
        for match in matches:
            home = match.get('home', '')
            away = match.get('away', '')
            full_match = f"{home} vs {away}"
            
            if match_name.lower() in full_match.lower() or full_match.lower() in match_name.lower():
                result = f"📊 <b>АНАЛИЗ МАТЧА</b>\n"
                result += f"🏟️ {full_match}\n"
                result += f"🏆 Лига: {match.get('league', 'Unknown')}\n"
                result += f"📅 Дата: {match.get('match_time', 'Unknown')}\n\n"
                
                best = match.get('best_bet', {})
                result += f"🎯 <b>ЛУЧШАЯ СТАВКА: {best.get('label', '—')}</b>\n"
                result += f"📈 EV: <b>{best.get('ev', 0)}%</b> | Вероятность: {best.get('prob', 0)}%\n"
                result += f"💰 Коэффициент: {best.get('odds', 0)}\n"
                if best.get('bookmaker'):
                    result += f"🏷️ Лучший коэффициент: {best.get('bookmaker')}\n"
                result += "\n"
                
                result += "📊 <b>ВСЕ СТАВКИ:</b>\n"
                bets = match.get('bets', [])
                for i, bet in enumerate(bets[:7], 1):
                    ev = bet.get('ev', 0)
                    emoji = "🟢" if ev > 10 else ("🟡" if ev > 5 else "🔴")
                    result += f"{emoji} {i}. {bet.get('label', '—')} | EV: {bet.get('ev', 0)}% | Prob: {bet.get('prob', 0)}% | КЭФ: {bet.get('odds', 0)}\n"
                
                result += f"\n⚽ XG: {match.get('total_xg', 0):.2f}"
                result += f" | Хозяева: {match.get('home_xg', 0):.2f}"
                result += f" | Гости: {match.get('away_xg', 0):.2f}\n"
                result += f"📈 Форма: {match.get('home_form', '—')} vs {match.get('away_form', '—')}\n"
                result += f"🏆 Позиция: #{match.get('standings', {}).get('home_position', '?')} vs #{match.get('standings', {}).get('away_position', '?')}\n\n"
                
                if best.get('ev', 0) > 10:
                    result += f"💡 <b>Рекомендация: {best.get('label', '—')}</b> (EV: {best.get('ev', 0)}%) ✅"
                elif best.get('ev', 0) > 5:
                    result += f"💡 <b>Рекомендация: {best.get('label', '—')}</b> (EV: {best.get('ev', 0)}%) ⚠️"
                else:
                    result += "⚠️ <b>Ставка с низким EV</b>. Рекомендуется пропустить."
                
                return result
        
        return f"❌ Матч '{match_name}' не найден в кэше. Запустите /update сначала."
        
    except Exception as e:
        logger.error(f"Ошибка анализа матча: {e}")
        return f"❌ Ошибка: {e}"

# ============================================================
# ОБНОВЛЕНИЕ КОЭФФИЦИЕНТОВ ИЗ ODD API
# ============================================================

def update_odds_for_matches(matches):
    """
    Обновляет коэффициенты для отобранных матчей из Odds API
    """
    updated_matches = []
    
    for match_data in matches:
        try:
            home = match_data.get('home')
            away = match_data.get('away')
            league = match_data.get('league')
            
            odds_data = odds_api.get_odds_for_match(home, away, league)
            
            if odds_data and odds_data.get('best_odds', 0) > 0:
                best_bet = match_data.get('best_bet', {})
                
                old_odds = best_bet.get('odds', 0)
                new_odds = odds_data['best_odds']
                
                prob = best_bet.get('prob', 0) / 100
                new_ev = (prob * new_odds) - 1
                
                best_bet['odds'] = new_odds
                best_bet['ev'] = round(new_ev * 100, 1)
                best_bet['bookmaker'] = odds_data.get('bookmaker_name', '—')
                best_bet['bookmaker_key'] = odds_data.get('bookmaker', '')
                
                match_data['best_bet'] = best_bet
                match_data['odds_updated'] = True
                
                logger.info(f"✅ Обновлены коэффициенты: {home} vs {away} | {new_odds} ({odds_data['bookmaker_name']}) | EV: {best_bet['ev']}%")
            else:
                logger.info(f"ℹ️ Коэффициенты не обновлены для {home} vs {away}")
            
            updated_matches.append(match_data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления коэффициентов {match_data.get('home')}: {e}")
            updated_matches.append(match_data)
    
    return updated_matches

# ============================================================
# ПОИСК МАТЧЕЙ
# ============================================================

def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    dates_to_search = [today]
    
    logger.info(f"🔍 Поиск матчей на: {today}")
    
    all_leagues = Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])
    logger.info(f"📊 Всего соревнований: {len(all_leagues)}")
    
    for league_id in all_leagues:
        for search_date in dates_to_search:
            try:
                matches = football_api.get_matches(league_id, search_date)
                league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
                
                if not matches or not isinstance(matches, list):
                    logger.info(f"🔥 Нет матчей в {league_name} на {search_date}")
                    continue
                
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                    
                    fixture = match.get("fixture")
                    if not fixture or not isinstance(fixture, dict):
                        continue
                    
                    status = fixture.get("status", {})
                    if not isinstance(status, dict):
                        continue
                    
                    if status.get("short") == "NS":
                        match_id = fixture.get("id")
                        if not match_id:
                            continue
                        
                        existing_ids = []
                        for m in all_matches:
                            if isinstance(m, dict):
                                existing_ids.append(m.get("fixture", {}).get("id"))
                        
                        if match_id in existing_ids:
                            continue
                        
                        teams = match.get("teams", {})
                        if not isinstance(teams, dict):
                            continue
                        
                        home_team = teams.get("home", {})
                        away_team = teams.get("away", {})
                        
                        if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                            continue
                        
                        home_id = home_team.get("id")
                        away_id = away_team.get("id")
                        
                        if not home_id or not away_id:
                            continue
                        
                        match["factors"] = {
                            "home_form": football_api.get_form(home_id) if home_id else None,
                            "away_form": football_api.get_form(away_id) if away_id else None,
                            "home_injuries_list": football_api.get_injuries(home_id) if home_id else [],
                            "away_injuries_list": football_api.get_injuries(away_id) if away_id else [],
                            "home_id": home_id,
                            "away_id": away_id,
                            "referee": fixture.get("referee")
                        }
                        
                        match["weather"] = None
                        match["weather_reason"] = "🌤️ Погода отключена"
                        
                        league_data = match.get("league", {})
                        if isinstance(league_data, dict):
                            league_data["name"] = league_name
                        
                        all_matches.append(match)
                        
            except Exception as e:
                error_msg = f"Ошибка {league_name} на {search_date}: {e}"
                logger.error(f"❌ {error_msg}")
                send_error_to_telegram(error_msg)
            
            time.sleep(0.1)
    
    logger.info(f"📊 ВСЕГО найдено матчей: {len(all_matches)}")
    return all_matches

# ============================================================
# ТОП МАТЧЕЙ - С ФИЛЬТРАМИ 70%+
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN

    logger.info(f"🔍 Анализ {len(matches)} матчей из всех лиг с фильтрами для 70%+...")
    
    best_matches = []
    bet_type_count = {}
    league_count = {}
    
    for match in matches:
        if not match or not isinstance(match, dict):
            continue

        try:
            fixture = match.get("fixture")
            if not fixture or not isinstance(fixture, dict):
                continue
            
            fixture_id = fixture.get("id")
            if not fixture_id:
                continue
            
            teams = match.get("teams")
            if not teams or not isinstance(teams, dict):
                continue
            
            home_team = teams.get("home")
            away_team = teams.get("away")
            
            if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                continue
            
            home = home_team.get("name", "Unknown")
            away = away_team.get("name", "Unknown")
            
            league_data = match.get("league")
            league_name = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"
            league_id = league_data.get("id") if isinstance(league_data, dict) else None

            match_time = fixture.get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            # ============================================================
            # 1. ПОЛУЧАЕМ XG
            # ============================================================
            
            statistics = football_api.get_match_statistics(fixture_id)
            
            home_xg = 1.2
            away_xg = 1.0
            
            if statistics:
                for team_name, stats in statistics.items():
                    if home.lower() in team_name.lower() or team_name.lower() in home.lower():
                        xg_val = stats.get('xG')
                        if xg_val is not None and xg_val > 0:
                            home_xg = float(xg_val)
                    elif away.lower() in team_name.lower() or team_name.lower() in away.lower():
                        xg_val = stats.get('xG')
                        if xg_val is not None and xg_val > 0:
                            away_xg = float(xg_val)
            
            if home_xg == 1.2 and away_xg == 1.0:
                if league_name in FALLBACK_XG:
                    home_xg = FALLBACK_XG[league_name]['home']
                    away_xg = FALLBACK_XG[league_name]['away']
                else:
                    home_xg = 1.3
                    away_xg = 1.0
                
                random.seed(fixture_id)
                home_xg *= (1 + random.uniform(-0.1, 0.1))
                away_xg *= (1 + random.uniform(-0.1, 0.1))
            
            # ============================================================
            # 2. ДОМАШНЕЕ ПРЕИМУЩЕСТВО
            # ============================================================
            
            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            
            total_xg = home_xg + away_xg
            
            # ============================================================
            # 3. ФИЛЬТР: КАЧЕСТВО XG (70%+)
            # ============================================================
            
            if total_xg < 1.8 or total_xg > 3.0:
                logger.info(f"⏭️ Пропускаем (XG вне диапазона 1.8-3.0): {home} vs {away} | XG: {total_xg:.2f}")
                continue
            
            # ============================================================
            # 4. ПОЛУЧАЕМ ФОРМУ КОМАНД
            # ============================================================
            
            home_form_data = football_api.get_form(home_team.get("id"))
            away_form_data = football_api.get_form(away_team.get("id"))
            
            home_form = home_form_data.get('form', '') if home_form_data else ''
            away_form = away_form_data.get('form', '') if away_form_data else ''
            
            home_goals_avg = home_form_data.get('goals_avg', 1.2) if home_form_data else 1.2
            away_goals_avg = away_form_data.get('goals_avg', 1.0) if away_form_data else 1.0
            home_conceded_avg = home_form_data.get('conceded_avg', 1.0) if home_form_data else 1.0
            away_conceded_avg = away_form_data.get('conceded_avg', 1.2) if away_form_data else 1.2
            
            # ============================================================
            # 5. ФИЛЬТР: ФОРМА КОМАНД (70%+)
            # ============================================================
            
            home_form_quality = analyze_form(home_form)
            away_form_quality = analyze_form(away_form)
            
            if home_form_quality not in ['excellent', 'good'] or away_form_quality not in ['excellent', 'good']:
                logger.info(f"⏭️ Пропускаем (плохая форма): {home} vs {away} | H: {home_form_quality}, A: {away_form_quality}")
                continue
            
            # ============================================================
            # 6. ПОЛУЧАЕМ ТУРНИРНУЮ ТАБЛИЦУ
            # ============================================================
            
            standings = football_api.get_standings(league_id) if league_id else None
            
            home_position = 99
            away_position = 99
            
            if standings:
                if home in standings:
                    home_position = standings[home].get('position', 99)
                if away in standings:
                    away_position = standings[away].get('position', 99)
            
            # ============================================================
            # 7. ФИЛЬТР: МОТИВАЦИЯ (70%+)
            # ============================================================
            
            home_motivation = get_motivation(home_position)
            away_motivation = get_motivation(away_position)
            
            if home_motivation == 'mid_table' and away_motivation == 'mid_table':
                logger.info(f"⏭️ Пропускаем (нет мотивации): {home} vs {away}")
                continue
            
            # ============================================================
            # 8. ФИЛЬТР: ПОЗИЦИЯ В ТАБЛИЦЕ
            # ============================================================
            
            if home_position > 15 or away_position > 15:
                logger.info(f"⏭️ Пропускаем (низкая позиция): {home} vs {away} | H: #{home_position}, A: #{away_position}")
                continue
            
            # ============================================================
            # 9. ЛИЧНЫЕ ВСТРЕЧИ (H2H)
            # ============================================================
            
            h2h_data = football_api.get_head_to_head(home, away)
            
            # ============================================================
            # 10. АНСАМБЛЬ ВЕРОЯТНОСТЕЙ
            # ============================================================
            
            probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data)
            
            prob_home_win = probs['home_win']
            prob_away_win = probs['away_win']
            prob_draw = probs['draw']
            prob_1X = probs['1X']
            prob_X2 = probs['X2']
            prob_over_2_5 = probs['over_2_5']
            prob_under_2_5 = probs['under_2_5']
            prob_btts = probs['btts']
            
            # ============================================================
            # 11. КОРРЕКТИРОВКА НА МОТИВАЦИЮ
            # ============================================================
            
            if home_motivation == 'relegation' and away_motivation == 'mid_table':
                prob_home_win += 0.10
                prob_1X += 0.08
            elif away_motivation == 'relegation' and home_motivation == 'mid_table':
                prob_away_win += 0.10
                prob_X2 += 0.08
            elif home_motivation == 'champions_league' and away_motivation == 'mid_table':
                prob_home_win += 0.08
                prob_1X += 0.05
            elif away_motivation == 'champions_league' and home_motivation == 'mid_table':
                prob_away_win += 0.08
                prob_X2 += 0.05
            
            # ============================================================
            # 12. КОЭФФИЦИЕНТЫ
            # ============================================================
            
            odds = {
                '1X': 1.85,
                'X2': 1.85,
                'П1': 2.10,
                'П2': 2.10,
                'ТМ 2.5': 1.95,
                'ТБ 2.5': 1.95,
                'ОБЗ': 1.90,
            }
            
            # ============================================================
            # 13. РАССЧИТЫВАЕМ EV
            # ============================================================
            
            bets = []
            
            ev_1x = (prob_1X * odds['1X']) - 1
            bets.append({
                'type': '1X',
                'label': '1X',
                'prob': round(prob_1X * 100, 1),
                'ev': round(ev_1x * 100, 1),
                'odds': odds['1X'],
                'stake': round(42.86875, 2)
            })
            
            ev_x2 = (prob_X2 * odds['X2']) - 1
            bets.append({
                'type': 'X2',
                'label': 'X2',
                'prob': round(prob_X2 * 100, 1),
                'ev': round(ev_x2 * 100, 1),
                'odds': odds['X2'],
                'stake': round(42.86875, 2)
            })
            
            ev_p1 = (prob_home_win * odds['П1']) - 1
            bets.append({
                'type': 'П1',
                'label': 'П1',
                'prob': round(prob_home_win * 100, 1),
                'ev': round(ev_p1 * 100, 1),
                'odds': odds['П1'],
                'stake': round(42.86875, 2)
            })
            
            ev_p2 = (prob_away_win * odds['П2']) - 1
            bets.append({
                'type': 'П2',
                'label': 'П2',
                'prob': round(prob_away_win * 100, 1),
                'ev': round(ev_p2 * 100, 1),
                'odds': odds['П2'],
                'stake': round(42.86875, 2)
            })
            
            ev_under = (prob_under_2_5 * odds['ТМ 2.5']) - 1
            bets.append({
                'type': 'under',
                'label': 'ТМ 2.5',
                'prob': round(prob_under_2_5 * 100, 1),
                'ev': round(ev_under * 100, 1),
                'odds': odds['ТМ 2.5'],
                'stake': round(42.86875, 2)
            })
            
            ev_over = (prob_over_2_5 * odds['ТБ 2.5']) - 1
            bets.append({
                'type': 'over',
                'label': 'ТБ 2.5',
                'prob': round(prob_over_2_5 * 100, 1),
                'ev': round(ev_over * 100, 1),
                'odds': odds['ТБ 2.5'],
                'stake': round(42.86875, 2)
            })
            
            ev_btts = (prob_btts * odds['ОБЗ']) - 1
            bets.append({
                'type': 'btts',
                'label': 'ОБЗ',
                'prob': round(prob_btts * 100, 1),
                'ev': round(ev_btts * 100, 1),
                'odds': odds['ОБЗ'],
                'stake': round(42.86875, 2)
            })
            
            bets.sort(key=lambda x: x['ev'], reverse=True)
            
            best_bet = bets[0]
            
            # ============================================================
            # 14. ФИЛЬТР: EV > 20% (70%+)
            # ============================================================
            
            if best_bet['ev'] < 20:
                logger.info(f"⏭️ Пропускаем (EV < 20%): {home} vs {away} | EV: {best_bet['ev']}%")
                continue
            
            # ============================================================
            # 15. ФИЛЬТР: ВЕРОЯТНОСТЬ > 60% (70%+)
            # ============================================================
            
            if best_bet['prob'] < 60:
                logger.info(f"⏭️ Пропускаем (Prob < 60%): {home} vs {away} | Prob: {best_bet['prob']}%")
                continue
            
            # ============================================================
            # 16. ФИЛЬТР: ЛИМИТ ПО ТИПАМ СТАВОК
            # ============================================================
            
            bet_type = best_bet['type']
            bet_type_count[bet_type] = bet_type_count.get(bet_type, 0) + 1
            
            if bet_type_count[bet_type] > 3:
                logger.info(f"⏭️ Пропускаем (лимит типа {bet_type}): {home} vs {away}")
                continue
            
            # ============================================================
            # 17. ФИЛЬТР: ЛИМИТ ПО ЛИГАМ
            # ============================================================
            
            league_count[league_name] = league_count.get(league_name, 0) + 1
            
            if league_count[league_name] > 2:
                logger.info(f"⏭️ Пропускаем (лимит лиги {league_name}): {home} vs {away}")
                continue
            
            # ============================================================
            # 18. СОХРАНЯЕМ МАТЧ
            # ============================================================
            
            match_data = {
                "home": home,
                "away": away,
                "league": league_name,
                "fixture_id": fixture_id,
                "match_time": match_time,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "total_xg": round(total_xg, 2),
                "home_form": home_form,
                "away_form": away_form,
                "home_form_quality": home_form_quality,
                "away_form_quality": away_form_quality,
                "home_goals_avg": home_goals_avg,
                "away_goals_avg": away_goals_avg,
                "home_conceded_avg": home_conceded_avg,
                "away_conceded_avg": away_conceded_avg,
                "standings": {
                    "home_position": home_position,
                    "away_position": away_position,
                    "home_motivation": home_motivation,
                    "away_motivation": away_motivation
                },
                "bets": bets,
                "best_bet": best_bet,
                "weather_reason": "🌤️",
                "factors": {},
                "source": "70_percent"
            }
            
            best_matches.append(match_data)
            
            logger.info(f"✅ КАНДИДАТ (70%+): {home} vs {away} | ЛУЧШАЯ СТАВКА: {best_bet['label']} | EV: {best_bet['ev']}% | Prob: {best_bet['prob']}%")
            
            for i, bet in enumerate(bets[:3], 1):
                logger.info(f"   {i}. {bet['label']} | EV: {bet['ev']}% | Prob: {bet['prob']}%")
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            continue
    
    # ============================================================
    # 19. СОРТИРОВКА И ВЫБОР ЛУЧШИХ
    # ============================================================
    
    best_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top_matches = best_matches[:max_bets]
    
    logger.info(f"📊 Найдено {len(best_matches)} кандидатов (70%+), выбрано {len(top_matches)} лучших")
    
    return top_matches


# ============================================================
# НОВАЯ ФУНКЦИЯ: ПОИСК ТМ 2.5 С ПРИОРИТЕТАМИ (EV>30, ПОТОМ EV>15)
# ============================================================

def find_tm25_matches(matches):
    """Специальный поиск для ТМ 2.5 с двухуровневым приоритетом EV"""
    tm25_candidates = []
    
    # Загружаем настройки из config.py
    from app.config import Config
    
    # Максимальное количество ставок
    MAX_TM25_BETS = Config.MAX_TM25_BETS
    
    # Параметры для УРОВНЯ 1 (PREMIUM) - EV > 30%
    PREMIUM_MIN_EV = 30 / 100  # 0.30
    PREMIUM_MIN_PROB = 60 / 100  # 0.60
    PREMIUM_XG_MIN = 1.0
    PREMIUM_XG_MAX = 2.8
    
    # Параметры для УРОВНЯ 2 (STANDARD) - EV > 15%
    STANDARD_MIN_EV = 15 / 100  # 0.15
    STANDARD_MIN_PROB = 50 / 100  # 0.50
    STANDARD_XG_MIN = 0.8
    STANDARD_XG_MAX = 3.0
    
    TOP_LEAGUES = Config.TOP_LEAGUES
    
    logger.info("🔍 Специальный поиск ТМ 2.5 (двухуровневый)...")
    logger.info(f"📊 УРОВЕНЬ 1 (PREMIUM): EV>30%, Prob>60%, XG 1.0-2.8")
    logger.info(f"📊 УРОВЕНЬ 2 (STANDARD): EV>15%, Prob>50%, XG 0.8-3.0")
    logger.info(f"📊 Всего матчей для анализа: {len(matches)}")
    
    # Счетчики для отладки
    stats = {
        'total': 0,
        'premium_found': 0,
        'standard_found': 0,
        'xg_fail': 0,
        'ev_fail': 0,
        'prob_fail': 0,
        'top_league_fail': 0
    }
    
    # Сначала проходим по всем матчам и ищем PREMIUM (EV > 30%)
    logger.info("🎯 ПОИСК УРОВНЯ 1 (PREMIUM EV>30%)...")
    
    for match in matches:
        if not match or not isinstance(match, dict):
            continue
        
        stats['total'] += 1
        
        try:
            fixture = match.get("fixture")
            if not fixture or not isinstance(fixture, dict):
                continue
            
            fixture_id = fixture.get("id")
            if not fixture_id:
                continue
            
            teams = match.get("teams")
            if not teams or not isinstance(teams, dict):
                continue
            
            home_team = teams.get("home")
            away_team = teams.get("away")
            
            if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                continue
            
            home = home_team.get("name", "Unknown")
            away = away_team.get("name", "Unknown")
            
            league_data = match.get("league")
            league_name = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"
            league_id = league_data.get("id") if isinstance(league_data, dict) else None
            
            match_time = fixture.get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            # ============================================================
            # ПОЛУЧАЕМ XG
            # ============================================================
            
            statistics = football_api.get_match_statistics(fixture_id)
            
            home_xg = 1.2
            away_xg = 1.0
            
            if statistics:
                for team_name, stats_dict in statistics.items():
                    if home.lower() in team_name.lower() or team_name.lower() in home.lower():
                        xg_val = stats_dict.get('xG')
                        if xg_val is not None and xg_val > 0:
                            home_xg = float(xg_val)
                    elif away.lower() in team_name.lower() or team_name.lower() in away.lower():
                        xg_val = stats_dict.get('xG')
                        if xg_val is not None and xg_val > 0:
                            away_xg = float(xg_val)
            
            if home_xg == 1.2 and away_xg == 1.0:
                if league_name in FALLBACK_XG:
                    home_xg = FALLBACK_XG[league_name]['home']
                    away_xg = FALLBACK_XG[league_name]['away']
                else:
                    home_xg = 1.3
                    away_xg = 1.0
                
                random.seed(fixture_id)
                home_xg *= (1 + random.uniform(-0.1, 0.1))
                away_xg *= (1 + random.uniform(-0.1, 0.1))
            
            # Домашнее преимущество
            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            
            total_xg = home_xg + away_xg
            
            # ============================================================
            # ПРОВЕРКА PREMIUM УРОВНЯ (EV > 30%)
            # ============================================================
            
            # Фильтр XG для PREMIUM
            if total_xg < PREMIUM_XG_MIN or total_xg > PREMIUM_XG_MAX:
                stats['xg_fail'] += 1
                continue
            
            # Получаем форму
            home_form_data = football_api.get_form(home_team.get("id"))
            away_form_data = football_api.get_form(away_team.get("id"))
            
            home_form = home_form_data.get('form', '') if home_form_data else ''
            away_form = away_form_data.get('form', '') if away_form_data else ''
            
            # Получаем таблицу
            standings = football_api.get_standings(league_id) if league_id else None
            
            home_position = 99
            away_position = 99
            
            if standings:
                if home in standings:
                    home_position = standings[home].get('position', 99)
                if away in standings:
                    away_position = standings[away].get('position', 99)
            
            # H2H
            h2h_data = football_api.get_head_to_head(home, away)
            
            # Ансамбль вероятностей
            probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data)
            prob_under_2_5 = probs['under_2_5']
            
            # Рассчитываем EV
            odds_tm25 = 1.95
            ev_under = (prob_under_2_5 * odds_tm25) - 1
            
            # ============================================================
            # ПРОВЕРКА PREMIUM: EV > 30% И Prob > 60%
            # ============================================================
            
            if ev_under >= PREMIUM_MIN_EV and prob_under_2_5 >= PREMIUM_MIN_PROB:
                # Проверка топ-лиг
                if league_name in TOP_LEAGUES and ev_under < 0.35:
                    stats['top_league_fail'] += 1
                    continue
                
                # Создаем матч PREMIUM уровня
                best_bet = {
                    'type': 'under',
                    'label': 'ТМ 2.5 🔥',
                    'prob': round(prob_under_2_5 * 100, 1),
                    'ev': round(ev_under * 100, 1),
                    'odds': odds_tm25,
                    'stake': round(42.86875, 2),
                    'level': 'PREMIUM'
                }
                
                match_data = {
                    "home": home,
                    "away": away,
                    "league": league_name,
                    "fixture_id": fixture_id,
                    "match_time": match_time,
                    "home_xg": round(home_xg, 2),
                    "away_xg": round(away_xg, 2),
                    "total_xg": round(total_xg, 2),
                    "home_form": home_form,
                    "away_form": away_form,
                    "standings": {
                        "home_position": home_position,
                        "away_position": away_position,
                    },
                    "bets": [best_bet],
                    "best_bet": best_bet,
                    "source": "tm25_premium",
                    "weather_reason": "🌤️",
                }
                
                tm25_candidates.append(match_data)
                stats['premium_found'] += 1
                
                logger.info(f"🔥 PREMIUM ТМ2.5: {home} vs {away} | EV: {ev_under*100:.1f}% | Prob: {prob_under_2_5*100:.1f}% | XG: {total_xg:.2f}")
                
                if len(tm25_candidates) >= MAX_TM25_BETS:
                    logger.info(f"⏹️ Достигнут лимит PREMIUM ({MAX_TM25_BETS}), остановка поиска")
                    break
                
        except Exception as e:
            logger.error(f"❌ Ошибка PREMIUM: {e}")
            continue
    
    # ============================================================
    # ЕСЛИ PREMIUM НЕ НАЙДЕНО - ИЩЕМ STANDARD (EV > 15%)
    # ============================================================
    
    if len(tm25_candidates) < MAX_TM25_BETS:
        logger.info(f"🎯 PREMIUM найдено: {len(tm25_candidates)}, ищем STANDARD (EV>15%)...")
        
        for match in matches:
            if not match or not isinstance(match, dict):
                continue
            
            # Пропускаем матчи, которые уже есть в PREMIUM
            existing_keys = [f"{m['home']}_{m['away']}" for m in tm25_candidates]
            if f"{match.get('teams', {}).get('home', {}).get('name', '')}_{match.get('teams', {}).get('away', {}).get('name', '')}" in existing_keys:
                continue
            
            try:
                fixture = match.get("fixture")
                if not fixture or not isinstance(fixture, dict):
                    continue
                
                fixture_id = fixture.get("id")
                if not fixture_id:
                    continue
                
                teams = match.get("teams")
                if not teams or not isinstance(teams, dict):
                    continue
                
                home_team = teams.get("home")
                away_team = teams.get("away")
                
                if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                    continue
                
                home = home_team.get("name", "Unknown")
                away = away_team.get("name", "Unknown")
                
                league_data = match.get("league")
                league_name = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"
                league_id = league_data.get("id") if isinstance(league_data, dict) else None
                
                match_time = fixture.get("date", "")
                if match_time:
                    try:
                        dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                        dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                        match_time = dt.strftime("%d.%m.%Y %H:%M")
                    except:
                        match_time = "Время не указано"
                
                # ============================================================
                # ПОЛУЧАЕМ XG
                # ============================================================
                
                statistics = football_api.get_match_statistics(fixture_id)
                
                home_xg = 1.2
                away_xg = 1.0
                
                if statistics:
                    for team_name, stats_dict in statistics.items():
                        if home.lower() in team_name.lower() or team_name.lower() in home.lower():
                            xg_val = stats_dict.get('xG')
                            if xg_val is not None and xg_val > 0:
                                home_xg = float(xg_val)
                        elif away.lower() in team_name.lower() or team_name.lower() in away.lower():
                            xg_val = stats_dict.get('xG')
                            if xg_val is not None and xg_val > 0:
                                away_xg = float(xg_val)
                
                if home_xg == 1.2 and away_xg == 1.0:
                    if league_name in FALLBACK_XG:
                        home_xg = FALLBACK_XG[league_name]['home']
                        away_xg = FALLBACK_XG[league_name]['away']
                    else:
                        home_xg = 1.3
                        away_xg = 1.0
                    
                    random.seed(fixture_id)
                    home_xg *= (1 + random.uniform(-0.1, 0.1))
                    away_xg *= (1 + random.uniform(-0.1, 0.1))
                
                # Домашнее преимущество
                home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
                home_xg *= home_adv
                away_xg /= home_adv
                
                total_xg = home_xg + away_xg
                
                # ============================================================
                # ПРОВЕРКА STANDARD УРОВНЯ (EV > 15%)
                # ============================================================
                
                # Фильтр XG для STANDARD (шире)
                if total_xg < STANDARD_XG_MIN or total_xg > STANDARD_XG_MAX:
                    stats['xg_fail'] += 1
                    continue
                
                # Получаем форму
                home_form_data = football_api.get_form(home_team.get("id"))
                away_form_data = football_api.get_form(away_team.get("id"))
                
                home_form = home_form_data.get('form', '') if home_form_data else ''
                away_form = away_form_data.get('form', '') if away_form_data else ''
                
                # Получаем таблицу
                standings = football_api.get_standings(league_id) if league_id else None
                
                home_position = 99
                away_position = 99
                
                if standings:
                    if home in standings:
                        home_position = standings[home].get('position', 99)
                    if away in standings:
                        away_position = standings[away].get('position', 99)
                
                # H2H
                h2h_data = football_api.get_head_to_head(home, away)
                
                # Ансамбль вероятностей
                probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data)
                prob_under_2_5 = probs['under_2_5']
                
                # Рассчитываем EV
                odds_tm25 = 1.95
                ev_under = (prob_under_2_5 * odds_tm25) - 1
                
                # ============================================================
                # ПРОВЕРКА STANDARD: EV > 15% И Prob > 50%
                # ============================================================
                
                if ev_under >= STANDARD_MIN_EV and prob_under_2_5 >= STANDARD_MIN_PROB:
                    # Проверка топ-лиг
                    if league_name in TOP_LEAGUES and ev_under < 0.20:
                        stats['top_league_fail'] += 1
                        continue
                    
                    # Создаем матч STANDARD уровня
                    best_bet = {
                        'type': 'under',
                        'label': 'ТМ 2.5',
                        'prob': round(prob_under_2_5 * 100, 1),
                        'ev': round(ev_under * 100, 1),
                        'odds': odds_tm25,
                        'stake': round(42.86875, 2),
                        'level': 'STANDARD'
                    }
                    
                    match_data = {
                        "home": home,
                        "away": away,
                        "league": league_name,
                        "fixture_id": fixture_id,
                        "match_time": match_time,
                        "home_xg": round(home_xg, 2),
                        "away_xg": round(away_xg, 2),
                        "total_xg": round(total_xg, 2),
                        "home_form": home_form,
                        "away_form": away_form,
                        "standings": {
                            "home_position": home_position,
                            "away_position": away_position,
                        },
                        "bets": [best_bet],
                        "best_bet": best_bet,
                        "source": "tm25_standard",
                        "weather_reason": "🌤️",
                    }
                    
                    tm25_candidates.append(match_data)
                    stats['standard_found'] += 1
                    
                    logger.info(f"✅ STANDARD ТМ2.5: {home} vs {away} | EV: {ev_under*100:.1f}% | Prob: {prob_under_2_5*100:.1f}% | XG: {total_xg:.2f}")
                    
                    if len(tm25_candidates) >= MAX_TM25_BETS:
                        logger.info(f"⏹️ Достигнут лимит STANDARD ({MAX_TM25_BETS}), остановка поиска")
                        break
                    
            except Exception as e:
                logger.error(f"❌ Ошибка STANDARD: {e}")
                continue
    
    # Логируем статистику
    logger.info(f"📊 СТАТИСТИКА ТМ2.5: Всего: {stats['total']}, PREMIUM: {stats['premium_found']}, STANDARD: {stats['standard_found']}")
    
    # Сортируем по EV (PREMIUM выше)
    tm25_candidates.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    
    logger.info(f"📊 Найдено ТМ2.5 кандидатов: {len(tm25_candidates)} (PREMIUM: {stats['premium_found']}, STANDARD: {stats['standard_found']})")
    
    return tm25_candidates


# ============================================================
# ОБЪЕДИНЕННЫЙ ПОИСК: 70%+ И ТМ 2.5
# ============================================================

def find_top_matches_with_tm25(matches):
    """Объединенный поиск: 70%+ и ТМ 2.5"""
    
    # 1. Обычный поиск 70%+
    logger.info("=" * 50)
    logger.info("📊 ПОТОК 1: Поиск 70%+ матчей")
    logger.info("=" * 50)
    top_matches_70 = find_top_matches(matches)
    
    # 2. Специальный поиск ТМ 2.5
    logger.info("=" * 50)
    logger.info("📊 ПОТОК 2: Поиск ТМ 2.5 матчей")
    logger.info("=" * 50)
    tm25_matches = find_tm25_matches(matches)
    
    # 3. Объединяем результаты
    combined_matches = []
    match_keys = set()
    
    # Добавляем 70%+ матчи
    for m in top_matches_70:
        key = f"{m['home']}_{m['away']}"
        if key not in match_keys:
            combined_matches.append(m)
            match_keys.add(key)
    
    # Добавляем ТМ 2.5 матчи (если нет дубликатов)
    for m in tm25_matches:
        key = f"{m['home']}_{m['away']}"
        if key not in match_keys:
            combined_matches.append(m)
            match_keys.add(key)
            logger.info(f"🔄 Добавлен ТМ2.5 матч (уникальный): {m['home']} vs {m['away']}")
        else:
            # Если матч уже есть, проверяем какой лучше
            existing = next((x for x in combined_matches if f"{x['home']}_{x['away']}" == key), None)
            if existing and m['best_bet']['ev'] > existing['best_bet']['ev']:
                # Заменяем на лучший
                combined_matches.remove(existing)
                combined_matches.append(m)
                logger.info(f"🔄 Заменен матч на ТМ2.5 (EV выше): {m['home']} vs {m['away']}")
    
    # 4. Сортируем по EV
    combined_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    
    # 5. Обновляем коэффициенты из Odds API
    if combined_matches:
        logger.info(f"📡 Запрос реальных коэффициентов для {len(combined_matches)} матчей из Odds API...")
        combined_matches = update_odds_for_matches(combined_matches)
    
    # 6. Ограничиваем общее количество
    max_total = Config.MAX_BETS_PER_RUN + Config.MAX_TM25_BETS
    combined_matches = combined_matches[:max_total]
    
    logger.info("=" * 50)
    logger.info(f"📊 ИТОГО: {len(combined_matches)} матчей (70%+: {len(top_matches_70)}, ТМ2.5: {len(tm25_matches)})")
    logger.info("=" * 50)
    
    return combined_matches


# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================

def determine_bet_result(bet_type, home_goals, away_goals):
    total = home_goals + away_goals
    bet_type_lower = bet_type.lower()
    
    if 'п1' in bet_type_lower:
        return 'win' if home_goals > away_goals else ('push' if home_goals == away_goals else 'loss')
    elif 'п2' in bet_type_lower:
        return 'win' if away_goals > home_goals else ('push' if home_goals == away_goals else 'loss')
    elif '1x' in bet_type_lower:
        return 'win' if home_goals >= away_goals else 'loss'
    elif 'x2' in bet_type_lower:
        return 'win' if away_goals >= home_goals else 'loss'
    elif 'обз' in bet_type_lower or 'btts' in bet_type_lower:
        return 'win' if home_goals > 0 and away_goals > 0 else 'loss'
    elif 'тм 2.5' in bet_type_lower or 'under' in bet_type_lower:
        return 'win' if total < 2.5 else 'loss'
    elif 'тб 2.5' in bet_type_lower or 'over' in bet_type_lower:
        return 'win' if total > 2.5 else 'loss'
    
    return 'pending'

def update_pending_bets():
    history = storage.load_history()
    updated = 0
    
    for bet in history:
        if bet.get('result') == 'pending' or bet.get('result') is None:
            fixture_id = bet.get('fixture_id')
            
            if not fixture_id:
                home = bet.get('home', '')
                away = bet.get('away', '')
                if home and away:
                    fixture_id = football_api.find_fixture_by_teams(home, away)
                    if fixture_id:
                        bet['fixture_id'] = fixture_id
            
            if fixture_id:
                match_data = football_api.get_match_result(fixture_id)
                if match_data:
                    home_goals = match_data['goals']['home']
                    away_goals = match_data['goals']['away']
                    
                    if home_goals is not None and away_goals is not None:
                        bet_type = bet.get('bet', '')
                        result = determine_bet_result(bet_type, home_goals, away_goals)
                        
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
                            logger.info(f"✅ Обновлена ставка: {bet['home']} vs {bet['away']} → {result} ({home_goals}-{away_goals})")
    
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
    
    stats['total'] = total
    stats['wins'] = wins
    stats['losses'] = losses
    stats['pushes'] = pushes
    stats['total_profit'] = round(total_profit, 2)
    stats['winrate'] = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
    stats['roi'] = round((total_profit / total_stake * 100), 1) if total_stake > 0 else 0
    
    storage.save_stats(stats)
    logger.info(f"📊 Статистика пересчитана: {stats}")

# ============================================================
# FLASK WEBHOOK
# ============================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running
    
    try:
        data = request.get_json()
        if not data:
            return "ok", 200
        
        logger.info("=" * 50)
        logger.info(f"📨 ПОЛУЧЕН ЗАПРОС ОТ TELEGRAM")
        logger.info("=" * 50)
        
        if 'callback_query' in data:
            callback = data['callback_query']
            callback_data = callback.get('data', '')
            logger.info(f"📨 Нажата кнопка: {callback_data}")
            
            answer_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"
            try:
                requests.post(answer_url, json={
                    "callback_query_id": callback.get('id', ''),
                    "text": "✅ Результат сохранён!"
                })
            except Exception as e:
                logger.error(f"Ошибка ответа: {e}")
            
            return "ok", 200
        
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            if str(chat_id) != str(Config.ADMIN_CHAT_ID):
                logger.warning(f"⛔ ДОСТУП ЗАПРЕЩЕН для {chat_id}")
                send_telegram("⛔ Нет доступа")
                return "ok", 200
            
            if text == '/start':
                send_telegram(handlers.handle_start())
            
            elif text == '/help':
                send_telegram(handlers.handle_help())
            
            elif text == '/update':
                if search_running:
                    send_telegram("⚠️ Поиск уже запущен!")
                else:
                    search_running = True
                    start_time = datetime.now()
                    send_telegram(f"🔄 Поиск матчей в {len(Config.LEAGUES)} лигах... (70%+ + ТМ 2.5)")
                    
                    matches = get_matches_with_factors()
                    if matches:
                        send_telegram(f"📊 Найдено {len(matches)} матчей. Анализирую...")
                        
                        # Используем новую объединенную функцию
                        top_matches = find_top_matches_with_tm25(matches)
                        
                        if top_matches:
                            elapsed = (datetime.now() - start_time).seconds
                            
                            # Подсчет типов ставок и источников
                            bet_types = {}
                            sources = {}
                            for m in top_matches:
                                bet_type = m['best_bet']['type']
                                bet_types[bet_type] = bet_types.get(bet_type, 0) + 1
                                source = m.get('source', 'unknown')
                                sources[source] = sources.get(source, 0) + 1
                            
                            type_stats = " | ".join([f"{k}: {v}" for k, v in bet_types.items()])
                            source_stats = " | ".join([f"{k}: {v}" for k, v in sources.items()])
                            
                            # Формируем сообщение с матчами
                            matches_text = ""
                            for i, m in enumerate(top_matches, 1):
                                best = m['best_bet']
                                matches_text += f"{i}. <b>{m['home']} vs {m['away']}</b>\n"
                                matches_text += f"   🏆 {m['league']}\n"
                                matches_text += f"   🎯 {best['label']} | КЭФ: {best['odds']}\n"
                                matches_text += f"   📈 EV: <b>{best['ev']}%</b> | Prob: {best['prob']}%\n"
                                matches_text += f"   ⚽ XG: {m['total_xg']:.2f}\n"
                                if best.get('bookmaker'):
                                    matches_text += f"   🏷️ Букмекер: {best['bookmaker']}\n"
                                
                                # Отображаем уровень
                                if m.get('source') == 'tm25_premium':
                                    matches_text += f"   🔥 PREMIUM (EV>30%)\n"
                                elif m.get('source') == 'tm25_standard':
                                    matches_text += f"   ⭐ STANDARD (EV>15%)\n"
                                elif m.get('source') == 'tm25_special':
                                    matches_text += f"   🔵 Спец.поиск ТМ2.5\n"
                                matches_text += "\n"
                            
                            send_telegram(
                                f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                                f"📊 Найдено матчей: {len(matches)}\n"
                                f"🎯 Кандидатов: {len(top_matches)}\n"
                                f"📈 Типы: {type_stats}\n"
                                f"📂 Источники: {source_stats}\n"
                                f"⏱️ Время: {elapsed} сек.\n\n"
                                f"📋 <b>СПИСОК СТАВОК:</b>\n\n"
                                f"{matches_text}"
                                f"🤖 Авто-ставок: {auto_bet.bets_today}"
                            )
                        else:
                            send_telegram("❌ Ставок не найдено (70%+ и ТМ2.5)")
                    else:
                        send_telegram("❌ Матчей не найдено")
                    
                    search_running = False
            
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            
            elif text == '/export':
                file, message = export_to_excel()
                if file:
                    send_telegram(message)
                    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                    files = {'document': ('history.xlsx', file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                    data = {'chat_id': Config.ADMIN_CHAT_ID, 'caption': '📊 История ставок'}
                    try:
                        requests.post(url, files=files, data=data, timeout=30)
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла: {e}")
                else:
                    send_telegram(message)
            
            elif text == '/autobet':
                auto_bet.enabled = not auto_bet.enabled
                send_telegram(f"🤖 AutoBet: {'ВКЛЮЧЕН' if auto_bet.enabled else 'ВЫКЛЮЧЕН'}")
            
            elif text == '/update_results':
                logger.info("🔄 Обработка /update_results")
                send_telegram("🔄 Проверка результатов матчей...")
                updated = update_pending_bets()
                if updated > 0:
                    send_telegram(f"✅ Обновлено {updated} результатов!")
                else:
                    send_telegram("📭 Нет завершённых матчей для обновления")
            
            elif text.startswith('/result'):
                logger.info("🔄 Обработка /result")
                parts = text.replace('/result', '').strip()
                if ' vs ' in parts:
                    match_part = parts.split(' vs ')
                    if len(match_part) == 2:
                        match_and_score = match_part[1].split(' ')
                        if len(match_and_score) >= 2:
                            away = match_and_score[0]
                            score = match_and_score[1] if len(match_and_score) > 1 else ''
                            home = match_part[0].strip()
                            match = f"{home} vs {away}"
                            send_telegram(f"🔄 Обновление результата: {match} {score}")
                            result = update_manual_result(match, score)
                            send_telegram(result)
                        else:
                            send_telegram("⚠️ Используй: /result Aris Thessalonikis vs OFI 2-1")
                    else:
                        send_telegram("⚠️ Используй: /result Aris Thessalonikis vs OFI 2-1")
                else:
                    send_telegram("⚠️ Используй: /result Aris Thessalonikis vs OFI 2-1")
            
            elif text.startswith('/analyze'):
                logger.info("🔄 Обработка /analyze")
                match_name = text.replace('/analyze', '').strip()
                if match_name:
                    send_telegram("🔍 Анализирую матч...")
                    result = analyze_match(match_name)
                    send_telegram(result)
                else:
                    send_telegram("⚠️ Используй: /analyze Aris Thessalonikis vs OFI")
            
            elif text == '/stop':
                search_running = False
                send_telegram("⏹️ Поиск остановлен")
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok", 200
    except Exception as e:
        error_msg = f"Webhook error: {e}"
        logger.error(f"❌ {error_msg}")
        send_error_to_telegram(error_msg)
        return "ok", 200

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
    history = storage.load_history()
    return jsonify(history)

@app.route('/api/matches', methods=['GET'])
def api_matches():
    cache = storage.load_cache()
    return jsonify(cache.get('top_matches', []))

@app.route('/api/all_data', methods=['GET'])
def all_data():
    try:
        logger.info("📡 Запрос всех данных для веб-приложения")
        
        stats = storage.load_stats()
        bank = storage.load_bank()
        history = storage.load_history()
        cache = storage.load_cache()
        
        profit_data = get_profit_data(history)
        
        result = {
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
        }
        
        logger.info(f"✅ Данные отправлены: {len(history)} ставок, {len(result['matches'])} матчей")
        return jsonify(result)
        
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
            home = ''
            away = ''
            
            if ' vs ' in match:
                parts = match.split(' vs ')
                home = parts[0].strip()
                away = parts[1].strip()
            elif ' - ' in match:
                parts = match.split(' - ')
                home = parts[0].strip()
                away = parts[1].strip()
            
            score = row.get('Счёт', '') or row.get('Score', '')
            home_goals = None
            away_goals = None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
            
            bet = row.get('Ставка', '') or row.get('Bet', '')
            odds = float(row.get('Коэф', 1.85))
            stake = float(row.get('Сумма', 0))
            ev = float(row.get('EV%', 0))
            result = row.get('Результат', 'pending')
            profit = float(row.get('Прибыль', 0))
            date = row.get('Дата', '') or datetime.now().strftime('%Y-%m-%d %H:%M')
            bookmaker = row.get('Букмекер', '—')
            
            bet_record = {
                'home': home or 'Unknown',
                'away': away or 'Unknown',
                'league': 'Импорт из Excel',
                'bet': bet,
                'odds': odds,
                'stake': stake,
                'ev': ev,
                'result': result,
                'profit': profit,
                'date': date,
                'home_goals': home_goals,
                'away_goals': away_goals,
                'bookmaker': bookmaker
            }
            history.append(bet_record)
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
        
        current_history = storage.load_history()
        existing_keys = set()
        
        for bet in current_history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            existing_keys.add(key)
        
        imported = 0
        for bet in history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            if key not in existing_keys:
                current_history.append(bet)
                imported += 1
                existing_keys.add(key)
        
        if stats and 'bank' in stats:
            storage.save_bank(stats['bank'])
        
        storage.save_history(current_history)
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
        
        history[index]['home'] = data.get('home', history[index]['home'])
        history[index]['away'] = data.get('away', history[index]['away'])
        history[index]['home_goals'] = data.get('home_goals')
        history[index]['away_goals'] = data.get('away_goals')
        history[index]['bet'] = data.get('bet', history[index]['bet'])
        history[index]['odds'] = data.get('odds', history[index]['odds'])
        history[index]['stake'] = data.get('stake', history[index]['stake'])
        history[index]['ev'] = data.get('ev', history[index]['ev'])
        history[index]['result'] = data.get('result', history[index]['result'])
        history[index]['bookmaker'] = data.get('bookmaker', history[index].get('bookmaker', '—'))
        
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
            return jsonify({'error': 'Нужно минимум 5 ставок для симуляции'}), 400
        
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
            'total': count,
            'wins': wins_sim,
            'losses': losses_sim,
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
        
        home_goals = None
        away_goals = None
        if score and '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0].strip())
                away_goals = int(parts[1].strip())
            except:
                pass
        
        home = 'Unknown'
        away = 'Unknown'
        if ' vs ' in match_name:
            parts = match_name.split(' vs ')
            home = parts[0].strip()
            away = parts[1].strip()
        elif ' - ' in match_name:
            parts = match_name.split(' - ')
            home = parts[0].strip()
            away = parts[1].strip()
        
        if result == 'win':
            profit = round(stake * (odds - 1), 2)
        elif result == 'loss':
            profit = -stake
        else:
            profit = 0
        
        history = storage.load_history()
        
        bet_record = {
            'home': home or 'Unknown',
            'away': away or 'Unknown',
            'league': 'Ручное добавление',
            'bet': bet_type,
            'odds': odds,
            'stake': stake,
            'ev': 0,
            'result': result,
            'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': home_goals,
            'away_goals': away_goals,
            'manual': True,
            'bookmaker': bookmaker
        }
        history.append(bet_record)
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True, 'count': 1})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@app.route('/', methods=['GET'])
def index():
    return f"🤖 Quantum Bot PRO (70%+ Target + ТМ 2.5 Special) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    setup_logging()
    start_scheduler()
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН (70%+ TARGET + ТМ 2.5 SPECIAL)!")
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    logger.info("🎯 ФИЛЬТРЫ ДЛЯ 70%+:")
    logger.info("   - Все лиги из config.py")
    logger.info("   - EV > 20%")
    logger.info("   - Prob > 60%")
    logger.info("   - XG 1.8-3.0")
    logger.info("   - Форма excellent/good")
    logger.info("   - Мотивация (не середняки)")
    logger.info("   - Лимит 3 ставки на тип")
    logger.info("   - Лимит 2 ставки на лигу")
    logger.info("🎯 ФИЛЬТРЫ ДЛЯ ТМ 2.5 (ДВУХУРОВНЕВЫЙ):")
    logger.info("   УРОВЕНЬ 1 (PREMIUM):")
    logger.info("   - EV > 30%")
    logger.info("   - Prob > 60%")
    logger.info("   - XG 1.0-2.8")
    logger.info("   УРОВЕНЬ 2 (STANDARD):")
    logger.info("   - EV > 15%")
    logger.info("   - Prob > 50%")
    logger.info("   - XG 0.8-3.0")
    logger.info(f"   - Лимит {Config.MAX_TM25_BETS} ставки")
    logger.info("🎯 ODD API:")
    logger.info("   - Реальные коэффициенты из 40+ БК")
    logger.info("   - Только один маркер: 42.86875000000006")
    logger.info("✅ Команды: /update_results, /result, /analyze")
    logger.info("✅ Кэш матчей сохраняется")
    app.run(host='0.0.0.0', port=port)
