# app/api/odds_api.py
"""
Модуль для работы с The Odds API
"""
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class OddsAPIClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        self.cache = {}
        
    def get_odds_for_match(self, home_team, away_team, league, sport="soccer"):
        """
        Получает коэффициенты для конкретного матча
        """
        cache_key = f"{home_team}_{away_team}_{league}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Формируем запрос
            params = {
                'apiKey': self.api_key,
                'sport': sport,
                'region': 'eu',
                'markets': 'h2h,spreads,totals'
            }
            
            url = f"{self.base_url}/events"
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Ищем нужный матч
                for event in data:
                    if event.get('home_team') == home_team and event.get('away_team') == away_team:
                        # Нашли матч
                        result = self._extract_odds(event)
                        self.cache[cache_key] = result
                        return result
            else:
                logger.error(f"Ошибка Odds API: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка запроса Odds API: {e}")
            return None
    
    def _extract_odds(self, event):
        """Извлекает коэффициенты из события"""
        result = {
            'bookmaker': None,
            'best_odds': 0,
            'all_odds': [],
            'bookmaker_name': '—'
        }
        
        # Получаем коэффициенты от всех букмекеров
        for bookmaker in event.get('bookmakers', []):
            bookmaker_name = bookmaker.get('key', '')
            for market in bookmaker.get('markets', []):
                if market.get('key') == 'h2h':
                    for outcome in market.get('outcomes', []):
                        if outcome.get('name') == '1X':
                            odds = outcome.get('price', 0)
                            if odds > result['best_odds']:
                                result['best_odds'] = odds
                                result['bookmaker'] = bookmaker_name
                                result['bookmaker_name'] = self._get_bookmaker_name(bookmaker_name)
        
        return result
    
    def _get_bookmaker_name(self, key):
        """Преобразует ключ букмекера в название"""
        names = {
            'bet365': 'bet365',
            'pinnacle': 'Pinnacle',
            'betfair': 'Betfair',
            'unibet': 'Unibet',
            'draftkings': 'DraftKings',
            'fanduel': 'FanDuel',
        }
        return names.get(key, key)
