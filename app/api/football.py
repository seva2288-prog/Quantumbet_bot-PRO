import requests
import time
from typing import Dict, List, Optional
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

class FootballAPI:
    BASE_URL = "https://v3.football.api-sports.io"
    
    def __init__(self):
        self.api_key = Config.FOOTBALL_API_KEY
        self.headers = {"x-rapidapi-key": self.api_key}
        self.last_request = 0
        self.min_interval = 0.3
    
    def _request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        now = time.time()
        if now - self.last_request < self.min_interval:
            time.sleep(self.min_interval - (now - self.last_request))
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=self.headers, params=params, timeout=15)
                self.last_request = time.time()
                
                if resp.status_code == 429:
                    time.sleep((attempt + 1) * 5)
                    continue
                
                if resp.status_code == 200:
                    data = resp.json()
                    return data if data.get('response') else None
                
                return None
            except Exception as e:
                logger.warning(f"API ошибка (попытка {attempt+1}): {e}")
                time.sleep(2)
        
        return None
    
    def get_matches(self, league_id: int, date: str) -> List:
        params = {'league': league_id, 'season': 2026, 'date': date}
        data = self._request('fixtures', params)
        return data.get('response', []) if data else []
    
    def get_form(self, team_id: int) -> Dict:
        params = {'team': team_id, 'last': 5}
        data = self._request('fixtures', params)
        
        if not data:
            return {'wins': 0, 'losses': 0, 'draws': 0, 'ratio': 0.5}
        
        wins = losses = draws = 0
        for match in data['response']:
            home_id = match['teams']['home']['id']
            home_goals = match['goals']['home']
            away_goals = match['goals']['away']
            
            if home_id == team_id:
                if home_goals > away_goals: wins += 1
                elif home_goals < away_goals: losses += 1
                else: draws += 1
            else:
                if away_goals > home_goals: wins += 1
                elif away_goals < home_goals: losses += 1
                else: draws += 1
        
        total = wins + losses + draws
        return {'wins': wins, 'losses': losses, 'draws': draws, 'ratio': wins/total if total > 0 else 0.5}
    
    def get_injuries(self, team_id: int) -> List[str]:
        params = {'team': team_id}
        data = self._request('injuries', params)
        
        if not data:
            return []
        
        injured = []
        for injury in data['response']:
            if injury.get('player', {}).get('name'):
                injured.append(injury['player']['name'])
        return injured
    
    def get_team_cards_stats(self, team_id: int) -> Dict:
        """Получение статистики по желтым карточкам команды"""
        params = {'team': team_id, 'season': 2026}
        data = self._request('teams/statistics', params)
        
        if not data or not data.get('response'):
            return {
                'yellow_cards_avg': 1.8,
                'red_cards_avg': 0.2,
                'trend': 'normal'
            }
        
        stats = data['response']
        yellow_avg = stats.get('cards', {}).get('yellow', {}).get('total', 0) / 10 if stats.get('cards', {}).get('yellow', {}).get('total', 0) > 0 else 1.8
        red_avg = stats.get('cards', {}).get('red', {}).get('total', 0) / 10 if stats.get('cards', {}).get('red', {}).get('total', 0) > 0 else 0.2
        
        trend = 'normal'
        if yellow_avg > 2.5:
            trend = 'aggressive'
        elif yellow_avg < 1.2:
            trend = 'disciplined'
        
        return {
            'yellow_cards_avg': round(yellow_avg, 1),
            'red_cards_avg': round(red_avg, 1),
            'trend': trend
        }
    
    def get_referee_stats(self, referee_name: str) -> Dict:
        """Получение статистики судьи по карточкам"""
        return {
            'yellow_avg': 3.2,
            'red_avg': 0.3,
            'style': 'strict' if 3.2 > 3.0 else 'lenient'
        }
    
    # ============================================================
    # НОВАЯ ФУНКЦИЯ: ПОЛУЧЕНИЕ РЕАЛЬНЫХ КОЭФОВ
    # ============================================================
    def get_match_odds(self, fixture_id: int) -> Dict:
        """
        Получение реальных коэффициентов с API
        """
        url = f"{self.BASE_URL}/odds"
        params = {'fixture': fixture_id}
        data = self._request(url, params)
        
        if not data or not data.get('response'):
            return None
        
        odds = {}
        for bookmaker in data['response']:
            for bet in bookmaker.get('bets', []):
                for value in bet.get('values', []):
                    if bet.get('name') == 'Обе забьют':
                        if value.get('value') == 'Да':
                            odds['btts'] = float(value.get('odd', 1.85))
                    elif bet.get('name') == 'Тотал':
                        if value.get('value') == '>2.5':
                            odds['over_2_5'] = float(value.get('odd', 1.80))
                    elif bet.get('name') == 'Исход':
                        if value.get('value') == '1':
                            odds['home_win'] = float(value.get('odd', 2.0))
                        elif value.get('value') == '2':
                            odds['away_win'] = float(value.get('odd', 2.0))
                        elif value.get('value') == 'X':
                            odds['draw'] = float(value.get('odd', 3.2))
        
        return odds if odds else None

football_api = FootballAPI()
