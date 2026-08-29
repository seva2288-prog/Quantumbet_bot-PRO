import requests
import logging
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        from app.config import Config
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 секунда между запросами (для избежания лимитов)
        
    def _make_request(self, endpoint, params=None):
        """Выполняет запрос к API с кэшированием"""
        try:
            # Ограничение частоты запросов
            now = time.time()
            if now - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (now - self.last_request_time))
            
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=headers, params=params, timeout=10)
            self.last_request_time = time.time()
            
            if response.status_code == 200:
                data = response.json()
                if data.get('errors'):
                    logger.error(f"API ошибка: {data['errors']}")
                    return None
                return data
            else:
                logger.error(f"API ошибка {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка запроса к API: {e}")
            return None
    
    def get_matches(self, league_id, date):
        """Получает матчи по лиге и дате"""
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
            self.cache[cache_key] = data['response']
            return data['response']
        
        return []
    
    def get_form(self, team_id):
        """Получает форму команды (последние 5 матчей)"""
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
                            scored = goals.get('home', 0)
                            conceded = goals.get('away', 0)
                        else:
                            scored = goals.get('away', 0)
                            conceded = goals.get('home', 0)
                        
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
        """Рассчитывает форму команды (последние 5 матчей)"""
        form = []
        for match in matches:
            teams = match.get('teams', {})
            if teams.get('home', {}).get('id') == team_id:
                if match.get('goals', {}).get('home', 0) > match.get('goals', {}).get('away', 0):
                    form.append('W')
                elif match.get('goals', {}).get('home', 0) == match.get('goals', {}).get('away', 0):
                    form.append('D')
                else:
                    form.append('L')
            else:
                if match.get('goals', {}).get('away', 0) > match.get('goals', {}).get('home', 0):
                    form.append('W')
                elif match.get('goals', {}).get('away', 0) == match.get('goals', {}).get('home', 0):
                    form.append('D')
                else:
                    form.append('L')
        return ''.join(form)
    
    def get_match_statistics(self, fixture_id):
        """Получает расширенную статистику матча (xG, удары, владение и т.д.)"""
        cache_key = f"stats_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'fixture': fixture_id}
            data = self._make_request('/fixtures/statistics', params)
            
            if data and 'response' in data:
                statistics = {}
                for team_stats in data['response']:
                    team_name = team_stats.get('team', {}).get('name', '')
                    stats = {}
                    
                    for stat in team_stats.get('statistics', []):
                        key = stat.get('type', '')
                        value = stat.get('value', 0)
                        
                        # Преобразуем проценты в числа
                        if isinstance(value, str) and '%' in value:
                            try:
                                value = float(value.replace('%', ''))
                            except:
                                value = 0
                        elif isinstance(value, str):
                            try:
                                value = float(value)
                            except:
                                value = 0
                        
                        stats[key] = value
                    
                    statistics[team_name] = stats
                
                self.cache[cache_key] = statistics
                return statistics
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики матча {fixture_id}: {e}")
        
        return None
    
    def get_head_to_head(self, home_team, away_team):
        """Получает историю личных встреч"""
        cache_key = f"h2h_{home_team}_{away_team}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Находим ID команд по названиям
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
                        
                        home_score = goals.get('home', 0)
                        away_score = goals.get('away', 0)
                        
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
                        result['avg_goals'] = round((result['goals_scored'] + result['goals_conceded']) / len(result['matches']), 2)
                        result['home_win_rate'] = round((result['home_wins'] / len(result['matches'])) * 100, 1)
                    
                    self.cache[cache_key] = result
                    return result
                    
        except Exception as e:
            logger.error(f"Ошибка получения H2H {home_team} vs {away_team}: {e}")
        
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
                    if team.get('name', '').lower() == team_name.lower():
                        team_id = team.get('team', {}).get('id')
                        self.cache[cache_key] = team_id
                        return team_id
                        
        except Exception as e:
            logger.error(f"Ошибка получения ID команды {team_name}: {e}")
        
        return None
    
    def get_standings(self, league_id):
        """Получает турнирную таблицу"""
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
        """Получает травмированных игроков команды"""
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
        """Получает результат матча по ID"""
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
        """Находит ID матча по названиям команд"""
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
    
    def clear_cache(self):
        """Очищает кэш"""
        self.cache = {}
        logger.info("🧹 Кэш очищен")

# Создаем глобальный экземпляр
football_api = FootballAPI()
