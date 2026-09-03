"""Конфигурация бота"""
import os
import requests

class Config:
    # === ТЕЛЕГРАМ ===
    TELEGRAM_TOKEN = "8884017743:AAEDsDQEV5NZe2x9-XTlZHrsBJ99UtgLHj8"
    ADMIN_CHAT_ID = 228801334  
    
    # === API ===
    FOOTBALL_API_KEY = "2c34b71a9086c34f9a59f30c814283f5"
    FOOTBALL_API_URL = "https://v3.football.api-sports.io"
    WEATHER_API_KEY = "7f0cfaced346b0fe364815ab65d627af"
    WEATHER_API_URL = "https://api.openweathermap.org/data/2.5"
    
    # === ODD API ===
    ODDS_API_KEY = "1a65316b9cba21b39cf5e6e008a3839e"
    ODDS_API_URL = "https://api.the-odds-api.com/v4"
    
    # ============================================================
    # НАСТРОЙКИ СТАВОК
    # ============================================================
    
    MAX_BETS_PER_RUN = 20
    
    # ============================================================
    # НАСТРОЙКИ 70%+ (ОСНОВНОЙ ПОИСК)
    # ============================================================
    
    XG_MIN_70 = 1.8
    XG_MAX_70 = 3.0
    EV_MIN_70 = 20
    PROB_MIN_70 = 60
    POSITION_MAX_70 = 15
    FORM_REQUIRED_70 = ['excellent', 'good']
    SKIP_MID_TABLE_70 = True
    LIMIT_BET_TYPE_70 = 10
    LIMIT_LEAGUE_70 = 2
    
    # ============================================================
    # НАСТРОЙКИ ТМ 2.5
    # ============================================================
    
    MAX_TM25_BETS = 5
    MIN_TM25_EV = 10
    MIN_TM25_PROB = 50
    TM25_XG_MIN = 1.0
    TM25_XG_MAX = 3.0
    
    # PREMIUM (EV > 30%)
    PREMIUM_MIN_EV = 30
    PREMIUM_MIN_PROB = 60
    PREMIUM_XG_MIN = 1.0
    PREMIUM_XG_MAX = 2.8
    
    # STANDARD (EV > 15%)
    STANDARD_MIN_EV = 15
    STANDARD_MIN_PROB = 50
    STANDARD_XG_MIN = 0.8
    STANDARD_XG_MAX = 3.0
    
    TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']
    TM25_TOP_LEAGUE_EV = 35
    
    # ============================================================
    # MAPПИНГ ЛИГ ДЛЯ ODDS API
    # ============================================================
    
    ODDS_SPORT_MAP = {
        'АПЛ': 'soccer_epl',
        'Premier League': 'soccer_epl',
        'Чемпионшип': 'soccer_efl_champ',
        'Championship': 'soccer_efl_champ',
        'Лига 1': 'soccer_england_league1',
        'League 1': 'soccer_england_league1',
        'Лига 2': 'soccer_england_league2',
        'League 2': 'soccer_england_league2',
        'Ла Лига': 'soccer_spain_la_liga',
        'La Liga': 'soccer_spain_la_liga',
        'Сегунда': 'soccer_spain_segunda_division',
        'La Liga 2': 'soccer_spain_segunda_division',
        'Бундеслига': 'soccer_germany_bundesliga',
        'Bundesliga': 'soccer_germany_bundesliga',
        'Вторая Бундеслига': 'soccer_germany_bundesliga2',
        '2. Bundesliga': 'soccer_germany_bundesliga2',
        'Серия А': 'soccer_italy_serie_a',
        'Serie A': 'soccer_italy_serie_a',
        'Серия B': 'soccer_italy_serie_b',
        'Serie B': 'soccer_italy_serie_b',
        'Ligue 1': 'soccer_france_ligue_one',
        'Ligue 2': 'soccer_france_ligue_two',
        'Эредивизи': 'soccer_netherlands_eredivisie',
        'Eredivisie': 'soccer_netherlands_eredivisie',
        'Примейра Лига': 'soccer_portugal_primeira_liga',
        'Primeira Liga': 'soccer_portugal_primeira_liga',
        'Про Лига': 'soccer_belgium_first_div',
        'Супер Лига': 'soccer_turkey_super_league',
        'Super Lig': 'soccer_turkey_super_league',
        'Премьершип': 'soccer_spl',
        'Суперлига': 'soccer_denmark_superliga',
        'Элитсериен': 'soccer_norway_eliteserien',
        'Аллсвенскан': 'soccer_sweden_allsvenskan',
        'Экстракласа': 'soccer_poland_ekstraklasa',
        'Премьер-Лига': 'soccer_ukraine_premier_league',
        'РПЛ': 'soccer_russia_premier_league',
        'HNL': 'soccer_croatia_hnl',
        'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
        'UEFA Champions League': 'soccer_uefa_champs_league',
        'Лига Европы УЕФА': 'soccer_uefa_europa_league',
        'UEFA Europa League': 'soccer_uefa_europa_league',
        'Бразилия Серия А': 'soccer_brazil_campeonato',
        'Brasileirão': 'soccer_brazil_campeonato',
        'Аргентина Примера': 'soccer_argentina_primera_division',
        'MLS': 'soccer_usa_mls',
        'МЛС': 'soccer_usa_mls',
        'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
        'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
        'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
        'Япония J1 Лига': 'soccer_japan_j_league',
        'J1 League': 'soccer_japan_j_league',
        'Южная Корея K Лига 1': 'soccer_korea_kleague1',
        'K League 1': 'soccer_korea_kleague1',
        'Австралия А-Лига': 'soccer_australia_a_league',
        'Китай Супер Лига': 'soccer_china_super_league',
    }
    
    # ============================================================
    # ЛИГИ (ОСНОВНЫЕ ID)
    # ============================================================
    
    LEAGUES = [
        39,   # Premier League
        40,   # Championship
        140,  # La Liga
        141,  # La Liga 2
        78,   # Bundesliga
        79,   # 2. Bundesliga
        135,  # Serie A
        136,  # Serie B
        61,   # Ligue 1
        62,   # Ligue 2
        88,   # Eredivisie
        94,   # Primeira Liga
        203,  # Süper Lig
        2,    # Champions League
        3,    # Europa League
        71,   # Brasileirão
        128,  # Argentina Primera
        253,  # MLS
    ]
    
    # ============================================================
    # КУБКИ (ОПЦИОНАЛЬНО)
    # ============================================================
    
    CUP_LEAGUES = [
        45,   # FA Cup
        46,   # EFL Cup
        143,  # Copa del Rey
        81,   # DFB-Pokal
        137,  # Coppa Italia
        66,   # Coupe de France
        13,   # Copa Libertadores
        14,   # Copa Sudamericana
    ]
    
    # ============================================================
    # НАЗВАНИЯ ЛИГ
    # ============================================================
    
    LEAGUE_NAMES = {
        39: "АПЛ",
        40: "Чемпионшип",
        140: "Ла Лига",
        141: "Сегунда",
        78: "Бундеслига",
        79: "Вторая Бундеслига",
        135: "Серия А",
        136: "Серия B",
        61: "Лига 1",
        62: "Лига 2",
        88: "Эредивизи",
        94: "Примейра Лига",
        203: "Супер Лига",
        2: "Лига Чемпионов УЕФА",
        3: "Лига Европы УЕФА",
        71: "Бразилия Серия А",
        128: "Аргентина Примера",
        253: "MLS",
    }
    
    # ============================================================
    # АВТОМАТИЧЕСКАЯ ПОДГРУЗКА ID ЛИГ ПО НАЗВАНИЯМ
    # ============================================================
    
    @classmethod
    def fetch_league_ids(cls):
        """Получает ID лиг по названиям из API"""
        if not cls.FOOTBALL_API_KEY:
            print("❌ Нет API ключа! Не могу загрузить ID лиг.")
            return {}
        
        league_ids = {}
        headers = {
            'x-apisports-key': cls.FOOTBALL_API_KEY,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        
        try:
            response = requests.get(
                f"{cls.FOOTBALL_API_URL}/leagues",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('response'):
                    for league in data['response']:
                        league_data = league.get('league', {})
                        name = league_data.get('name', '')
                        if name:
                            league_ids[name] = league_data.get('id')
                            
                            # Добавляем русские названия
                            if name == 'Premier League':
                                league_ids['АПЛ'] = league_data.get('id')
                            elif name == 'La Liga':
                                league_ids['Ла Лига'] = league_data.get('id')
                            elif name == 'Bundesliga':
                                league_ids['Бундеслига'] = league_data.get('id')
                            elif name == 'Serie A':
                                league_ids['Серия А'] = league_data.get('id')
                            elif name == 'Ligue 1':
                                league_ids['Лига 1'] = league_data.get('id')
                            elif name == 'UEFA Champions League':
                                league_ids['Лига Чемпионов УЕФА'] = league_data.get('id')
                            elif name == 'UEFA Europa League':
                                league_ids['Лига Европы УЕФА'] = league_data.get('id')
                            elif name == 'MLS':
                                league_ids['МЛС'] = league_data.get('id')
                
                print(f"✅ Загружено {len(league_ids)} лиг из API")
                return league_ids
            else:
                print(f"❌ Ошибка API: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"❌ Ошибка загрузки лиг: {e}")
            return {}
    
    # ============================================================
    # ПРОВЕРКА КОНФИГУРАЦИИ
    # ============================================================
    
    @classmethod
    def check(cls):
        missing = []
        if not cls.TELEGRAM_TOKEN:
            missing.append("TELEGRAM_TOKEN")
        if not cls.ADMIN_CHAT_ID:
            missing.append("ADMIN_CHAT_ID")
        if not cls.FOOTBALL_API_KEY:
            missing.append("FOOTBALL_API_KEY")
        if not cls.ODDS_API_KEY:
            missing.append("ODDS_API_KEY")
        
        if missing:
            print(f"⚠️ ВНИМАНИЕ: Отсутствуют: {', '.join(missing)}")
        else:
            print("✅ Все ключи загружены!")
        
        print(f"📊 Лиг: {len(cls.LEAGUES)}")
        print(f"🏆 Кубков: {len(cls.CUP_LEAGUES)}")
        print(f"📋 Всего: {len(cls.LEAGUES) + len(cls.CUP_LEAGUES)}")
        print(f"🎯 Odds API маппинг: {len(cls.ODDS_SPORT_MAP)} лиг")
        
        return True

# ============================================================
# АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПРИ ЗАПУСКЕ
# ============================================================

Config.check()
