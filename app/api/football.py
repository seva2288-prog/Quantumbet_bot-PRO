# app/api/football.py
import requests
import time
from datetime import datetime, timedelta
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FootballAPI:
    def __init__(self):
        self.base_url = Config.FOOTBALL_API_URL
        self.api_key = Config.FOOTBALL_API_KEY
        self.headers = {
            'x-rapidapi-key': self.api_key,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }

    def _get_headers(self):
        return self.headers

    def get_matches(self, league_id, date):
        """Получает матчи по лиге и дате"""
        try:
            url = f"{self.base_url}/fixtures"
            params = {
                'league': league_id,
                'date': date,
                'season': datetime.now().year
            }
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', [])
            else:
                logger.warning(f"Ошибка API: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Ошибка get_matches: {e}")
            return []

    def get_match_odds(self, fixture_id):
        """Получает коэффициенты на матч"""
        try:
            url = f"{self.base_url}/odds"
            params = {'fixture': fixture_id}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('response'):
                    return data['response'][0]
            return None
        except Exception as e:
            logger.error(f"Ошибка get_match_odds: {e}")
            return None

    def get_team_stats(self, team_id):
        """Получает статистику команды"""
        try:
            url = f"{self.base_url}/teams/statistics"
            params = {'team': team_id, 'season': datetime.now().year}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', {})
            return {}
        except Exception as e:
            logger.error(f"Ошибка get_team_stats: {e}")
            return {}

    def get_form(self, team_id):
        """Получает форму команды (последние матчи)"""
        try:
            url = f"{self.base_url}/fixtures"
            params = {
                'team': team_id,
                'last': 5,
                'season': datetime.now().year
            }
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                matches = data.get('response', [])
                if matches:
                    form = []
                    for match in matches:
                        if match['fixture']['status']['short'] in ['FT', 'AET', 'PEN']:
                            home_goals = match['goals']['home']
                            away_goals = match['goals']['away']
                            if match['teams']['home']['id'] == team_id:
                                if home_goals > away_goals:
                                    form.append('W')
                                elif home_goals < away_goals:
                                    form.append('L')
                                else:
                                    form.append('D')
                            else:
                                if away_goals > home_goals:
                                    form.append('W')
                                elif away_goals < home_goals:
                                    form.append('L')
                                else:
                                    form.append('D')
                    return ''.join(form[-5:]) if form else None
            return None
        except Exception as e:
            logger.error(f"Ошибка get_form: {e}")
            return None

    def get_injuries(self, team_id):
        """Получает травмы команды"""
        try:
            url = f"{self.base_url}/injuries"
            params = {'team': team_id}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                injuries = data.get('response', [])
                if injuries:
                    return [{
                        'player': i['player']['name'],
                        'reason': i.get('reason', 'Травма')
                    } for i in injuries[:5]]
            return []
        except Exception as e:
            logger.error(f"Ошибка get_injuries: {e}")
            return []

    def get_team_cards_stats(self, team_id):
        """Получает статистику карточек команды"""
        try:
            url = f"{self.base_url}/teams/statistics"
            params = {'team': team_id, 'season': datetime.now().year}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                stats = data.get('response', {})
                cards = stats.get('cards', {})
                return {
                    'yellow_avg': cards.get('yellow', {}).get('average', 0),
                    'red_avg': cards.get('red', {}).get('average', 0)
                }
            return {'yellow_avg': 0, 'red_avg': 0}
        except Exception as e:
            logger.error(f"Ошибка get_team_cards_stats: {e}")
            return {'yellow_avg': 0, 'red_avg': 0}

    def get_referee_stats(self, referee_name):
        """Получает статистику судьи"""
        # Упрощённая версия
        return {'cards_avg': 3.5}

    def get_match_result(self, fixture_id):
        """Получает результат матча по fixture_id"""
        try:
            url = f"{self.base_url}/fixtures"
            params = {'id': fixture_id}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('response') and len(data['response']) > 0:
                    match = data['response'][0]
                    status = match['fixture']['status']['short']
                    
                    # Если матч завершён
                    if status in ['FT', 'AET', 'PEN']:
                        home_goals = match['goals']['home']
                        away_goals = match['goals']['away']
                        
                        # Если голы None (не было голов)
                        if home_goals is None:
                            home_goals = 0
                        if away_goals is None:
                            away_goals = 0
                        
                        return {
                            'status': status,
                            'goals': {
                                'home': home_goals,
                                'away': away_goals
                            },
                            'home_team': match['teams']['home']['name'],
                            'away_team': match['teams']['away']['name']
                        }
            return None
        except Exception as e:
            logger.error(f"Ошибка get_match_result: {e}")
            return None

    def find_fixture_by_teams(self, home_team, away_team):
        """Ищет fixture_id по названиям команд"""
        try:
            # Ищем сегодняшние матчи
            today = datetime.now().strftime('%Y-%m-%d')
            # Ищем также вчерашние (для завершённых)
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            for date in [today, yesterday]:
                url = f"{self.base_url}/fixtures"
                params = {'date': date}
                response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('response'):
                        for match in data['response']:
                            home = match['teams']['home']['name'].lower()
                            away = match['teams']['away']['name'].lower()
                            
                            # Проверяем совпадение
                            if (home_team.lower() in home or home in home_team.lower()) and \
                               (away_team.lower() in away or away in away_team.lower()):
                                return match['fixture']['id']
                            
                            # Проверяем обратный порядок
                            if (home_team.lower() in away or away in home_team.lower()) and \
                               (away_team.lower() in home or home in away_team.lower()):
                                return match['fixture']['id']
            return None
        except Exception as e:
            logger.error(f"Ошибка find_fixture_by_teams: {e}")
            return None


# Создаем глобальный экземпляр
football_api = FootballAPI()
