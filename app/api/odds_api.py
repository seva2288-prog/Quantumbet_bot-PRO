import requests
import time
import logging
from app.config import Config

logger = logging.getLogger(__name__)

class OddsAPIClient:
    def __init__(self):
        self.api_key = Config.ODDS_API_KEY
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
            # ============================================================
            # ВСЕ 44 ФУТБОЛЬНЫЕ ЛИГИ ИЗ ODD API
            # ============================================================
            sport_map = {
                # === АНГЛИЯ ===
                'АПЛ': 'soccer_epl',
                'Premier League': 'soccer_epl',
                'Чемпионшип': 'soccer_efl_champ',
                'Championship': 'soccer_efl_champ',
                'League 1': 'soccer_england_league1',
                'League 2': 'soccer_england_league2',
                
                # === ИСПАНИЯ ===
                'Ла Лига': 'soccer_spain_la_liga',
                'La Liga': 'soccer_spain_la_liga',
                'Сегунда': 'soccer_spain_segunda_division',
                'La Liga 2': 'soccer_spain_segunda_division',
                
                # === ГЕРМАНИЯ ===
                'Бундеслига': 'soccer_germany_bundesliga',
                'Bundesliga': 'soccer_germany_bundesliga',
                'Вторая Бундеслига': 'soccer_germany_bundesliga2',
                '2. Bundesliga': 'soccer_germany_bundesliga2',
                '3. Лига': 'soccer_germany_liga3',
                '3. Liga': 'soccer_germany_liga3',
                'Кубок Германии': 'soccer_germany_dfb_pokal',
                'DFB-Pokal': 'soccer_germany_dfb_pokal',
                
                # === ИТАЛИЯ ===
                'Серия А': 'soccer_italy_serie_a',
                'Serie A': 'soccer_italy_serie_a',
                'Серия B': 'soccer_italy_serie_b',
                'Serie B': 'soccer_italy_serie_b',
                
                # === ФРАНЦИЯ ===
                'Лига 1': 'soccer_france_ligue_one',
                'Ligue 1': 'soccer_france_ligue_one',
                'Лига 2': 'soccer_france_ligue_two',
                'Ligue 2': 'soccer_france_ligue_two',
                
                # === США ===
                'MLS': 'soccer_usa_mls',
                'МЛС': 'soccer_usa_mls',
                
                # === ЕВРОКУБКИ ===
                'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
                'UEFA Champions League': 'soccer_uefa_champs_league',
                'Лига Европы УЕФА': 'soccer_uefa_europa_league',
                'UEFA Europa League': 'soccer_uefa_europa_league',
                'Лига Наций УЕФА': 'soccer_uefa_nations_league',
                'UEFA Nations League': 'soccer_uefa_nations_league',
                'Лига Конференций УЕФА': 'soccer_uefa_conference_league',
                
                # === ЮЖНАЯ АМЕРИКА ===
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
                
                # === ЕВРОПА (ДРУГИЕ ЛИГИ) ===
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
                
                # === АЗИЯ ===
                'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
                'Saudi Pro League': 'soccer_saudi_arabia_pro_league',
                'Япония J1 Лига': 'soccer_japan_j_league',
                'J1 League': 'soccer_japan_j_league',
                'Корея K Лига 1': 'soccer_korea_kleague1',
                'K League 1': 'soccer_korea_kleague1',
                'Мексика Liga MX': 'soccer_mexico_ligamx',
                'Liga MX': 'soccer_mexico_ligamx',
            }
            
            # Определяем спорт
            sport_key = sport_map.get(league, 'soccer_epl')
            
            # Определяем регион
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
            
            # Формируем запрос
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
        """Преобразует ключ букмекера в название"""
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
