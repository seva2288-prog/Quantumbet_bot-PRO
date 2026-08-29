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
        self.min_request_interval = 0.5  # 500ms между запросами
        
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
            # Получаем последние матчи команды
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
                        
                        # Определяем, играла ли команда дома или в гостях
                        if teams.get('home', {}).get('id') == team_id:
                            scored = goals.get('home', 0)
                            conceded = goals.get('away', 0)
                        else:
                            scored = goals.get('away', 0)
                            conceded = goals.get('home', 0)
                        
                        goals_scored.append(scored)
                        goals_conceded.append(conceded)
                        
                        # Результат матча
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
            params = {
                'id': fixture_id
            }
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
            # Ищем матч на сегодня
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
