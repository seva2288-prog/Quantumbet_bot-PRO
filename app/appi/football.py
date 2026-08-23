import requests
import time
from typing import Dict, List, Optional
from config import Config
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

football_api = FootballAPI()
