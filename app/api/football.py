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
        logger.info(f"🔑 API KEY загружен: {self.api_key[:10]}...")

    def _get_headers(self):
        return self.headers

    def get_matches(self, league_id, date):
        """Получение матчей по лиге и дате"""
        try:
            url = f"{self.base_url}/fixtures"
            params = {
                'league': league_id,
                'date': date,
                'season': datetime.now().year
            }
            
            logger.info(f"📡 Запрос матчей: лига {league_id}, дата {date}")
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                logger.error(f"❌ API ошибка: {response.status_code} - {response.text[:200]}")
                return []
            
            data = response.json()
            
            if data.get('errors') and data['errors']:
                logger.error(f"❌ API ошибка: {data['errors']}")
                return []
            
            matches = data.get('response', [])
            logger.info(f"✅ Найдено матчей: {len(matches)}")
            return matches
        except Exception as e:
            logger.error(f"❌ Ошибка get_matches: {e}")
            return []

    def get_match_odds(self, fixture_id):
        """Получение коэффициентов для матча"""
        try:
            url = f"{self.base_url}/odds"
            params = {'fixture': fixture_id}
            
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ Odds API ошибка {response.status_code} для fixture {fixture_id}")
                return None
            
            data = response.json()
            
            if data.get('errors'):
                logger.warning(f"⚠️ Odds ошибка: {data['errors']}")
                return None
            
            if data.get('response') and len(data['response']) > 0:
                odds_data = data['response'][0]
                logger.info(f"✅ Коэффициенты получены для fixture {fixture_id}")
                return odds_data
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка get_match_odds: {e}")
            return None

    def get_team_stats(self, team_id):
        """Получение статистики команды"""
        try:
            url = f"{self.base_url}/teams/statistics"
            params = {'team': team_id, 'season': datetime.now().year}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                return {}
            
            data = response.json()
            if data.get('errors'):
                return {}
            
            return data.get('response', {})
        except Exception as e:
            logger.error(f"❌ Ошибка get_team_stats: {e}")
            return {}

    def get_form(self, team_id):
        """Получение формы команды (последние 5 матчей)"""
        try:
            url = f"{self.base_url}/fixtures"
            params = {'team': team_id, 'last': 5, 'season': datetime.now().year}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            if data.get('errors'):
                return None
            
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
            logger.error(f"❌ Ошибка get_form: {e}")
            return None

    def get_injuries(self, team_id):
        """Получение травм команды"""
        try:
            url = f"{self.base_url}/injuries"
            params = {'team': team_id}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            if data.get('errors'):
                return []
            
            injuries = data.get('response', [])
            if injuries:
                result = []
                for i in injuries[:5]:
                    result.append({
                        'player': i['player']['name'],
                        'reason': i.get('reason', 'Травма')
                    })
                return result
            return []
        except Exception as e:
            logger.error(f"❌ Ошибка get_injuries: {e}")
            return []

    def get_team_cards_stats(self, team_id):
        """Получение статистики карточек команды"""
        try:
            url = f"{self.base_url}/teams/statistics"
            params = {'team': team_id, 'season': datetime.now().year}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                return {'yellow_avg': 0, 'red_avg': 0}
            
            data = response.json()
            if data.get('errors'):
                return {'yellow_avg': 0, 'red_avg': 0}
            
            stats = data.get('response', {})
            cards = stats.get('cards', {})
            return {
                'yellow_avg': cards.get('yellow', {}).get('average', 0),
                'red_avg': cards.get('red', {}).get('average', 0)
            }
        except Exception as e:
            logger.error(f"❌ Ошибка get_team_cards_stats: {e}")
            return {'yellow_avg': 0, 'red_avg': 0}

    def get_referee_stats(self, referee_name):
        """Получение статистики судьи (заглушка)"""
        return {'cards_avg': 3.5}

    def get_match_result(self, fixture_id):
        """Получение результата матча по fixture_id"""
        try:
            url = f"{self.base_url}/fixtures"
            params = {'id': fixture_id}
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            if data.get('errors'):
                return None
            
            if data.get('response') and len(data['response']) > 0:
                match = data['response'][0]
                status = match['fixture']['status']['short']
                
                if status in ['FT', 'AET', 'PEN']:
                    home_goals = match['goals']['home'] or 0
                    away_goals = match['goals']['away'] or 0
                    
                    return {
                        'status': status,
                        'goals': {'home': home_goals, 'away': away_goals},
                        'home_team': match['teams']['home']['name'],
                        'away_team': match['teams']['away']['name']
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка get_match_result: {e}")
            return None

    def find_fixture_by_teams(self,И home_team, away_team):
        """Поиск Б fixture_id по названиям команд"""
        try:
            today =У datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            for date in [today, yesterday]:
                url = f"{self.base_url}/fixtures"
                params = {'date': date}
                response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
                
                if response.status_code != 200:
                    continue
                
                data = response.json()
                if data.get('errors'):
                    continue
                
                if data.get('response'):
                    for match in data['response']:
                        home = match['teams']['home']['name'].lower()
                        away = match['teams']['away']['name'].lower()
                        
                        if (home_team.lower() in home or home in home_team.lower()) and \
                           (away_team.lower() in away or away in away_team.lower()):
                            return match['fixture']['id']
                        
                        if (home_team.lower() in away or away in home_team.lower()) and \
                           (away_team.lower() in home or home in away_team.lower()):
                            return match['fixture']['id']
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка find_fixture_by_teams: {e}")
            return None


# Создаем экземпляр для использования
football_api = FootballAPI()
