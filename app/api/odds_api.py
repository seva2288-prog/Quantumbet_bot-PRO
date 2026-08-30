# app/api/odds_api.py
import requests
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

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
        
        # ✅ ПРАВИЛЬНЫЙ URL
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
                
        except Exception as e:
            logger.error(f"❌ Ошибка запроса Odds API: {e}")
            return None
    
    def get_odds_for_match(self, home_team, away_team, league):
        """Получает коэффициенты для конкретного матча"""
        cache_key = f"{home_team}_{away_team}_{league}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Маппинг лиг на названия спорта в Odds API
            sport_map = {
    # Англия
    'АПЛ': 'soccer_epl',
    'Premier League': 'soccer_epl',
    'Чемпионшип': 'soccer_efl_champ',
    'Championship': 'soccer_efl_champ',
    'League 1': 'soccer_england_league1',
    'League 2': 'soccer_england_league2',
    
    # Испания
    'Ла Лига': 'soccer_spain_la_liga',
    'La Liga': 'soccer_spain_la_liga',
    'Сегунда': 'soccer_spain_segunda_division',
    
    # Германия
    'Бундеслига': 'soccer_germany_bundesliga',
    'Bundesliga': 'soccer_germany_bundesliga',
    'Вторая Бундеслига': 'soccer_germany_bundesliga2',
    
    # Италия
    'Серия А': 'soccer_italy_serie_a',
    'Serie A': 'soccer_italy_serie_a',
    'Серия B': 'soccer_italy_serie_b',
    
    # Франция
    'Лига 1': 'soccer_france_ligue_one',
    'Ligue 1': 'soccer_france_ligue_one',
    'Лига 2': 'soccer_france_ligue_two',
    
    # Другие
    'MLS': 'soccer_usa_mls',
    'МЛС': 'soccer_usa_mls',
    'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
    'Лига Европы УЕФА': 'soccer_uefa_europa_league',
    'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
    'Копа Судамерикана': 'soccer_conmebol_copa_sudamericana',
    'Эредивизи': 'soccer_netherlands_eredivisie',
    'Примейра Лига': 'soccer_portugal_primeira_liga',
    'Супер Лига': 'soccer_turkey_super_league',
    'РПЛ': 'soccer_russia_premier_league',
    'Бразилия Серия А': 'soccer_brazil_campeonato',
    'Аргентина Примера': 'soccer_argentina_primera_division',
    'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
    'Япония J1 Лига': 'soccer_japan_j_league',
    'Корея K Лига 1': 'soccer_korea_kleague1',
    'Мексика Liga MX': 'soccer_mexico_ligamx',
}
            
            sport_key = sport_map.get(league, 'soccer_epl')
            region = 'us' if 'MLS' in league or 'МЛС' in league else 'eu'
            
            params = {
                'sport': sport_key,
                'region': region,
                'markets': 'h2h'
            }
            
            logger.info(f"📡 Поиск коэффициентов для {home_team} vs {away_team} в {league}")
            data = self._make_request('/events', params)
            
            if data:
                for event in data:
                    if (event.get('home_team', '').lower() in home_team.lower() or home_team.lower() in event.get('home_team', '').lower()) and \
                       (event.get('away_team', '').lower() in away_team.lower() or away_team.lower() in event.get('away_team', '').lower()):
                        
                        result = self._extract_odds(event)
                        self.cache[cache_key] = result
                        logger.info(f"✅ Найдены коэффициенты для {home_team} vs {away_team}")
                        return result
            
            logger.info(f"⚠️ Матч {home_team} vs {away_team} не найден в Odds API")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения коэффициентов: {e}")
            return None
    
    def _extract_odds(self, event):
        """Извлекает коэффициенты из события"""
        result = {
            'best_odds': 0,
            'bookmaker': None,
            'bookmaker_name': '—'
        }
        
        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                if market.get('key') == 'h2h':
                    for outcome in market.get('outcomes', []):
                        price = outcome.get('price', 0)
                        if price > result['best_odds']:
                            result['best_odds'] = price
                            result['bookmaker'] = bookmaker.get('key')
                            result['bookmaker_name'] = self._get_bookmaker_name(bookmaker.get('key'))
        
        return result
    
    def _get_bookmaker_name(self, key):
        names = {
            'bet365': 'bet365',
            'pinnacle': 'Pinnacle',
            'betfair': 'Betfair',
            'draftkings': 'DraftKings',
            'fanduel': 'FanDuel',
            '1xbet': '1xBet',
            'bwin': 'Bwin',
            'williamhill': 'William Hill',
        }
        return names.get(key, key)
