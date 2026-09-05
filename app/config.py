"""Конфигурация бота"""
import os
import requests

class Config:
    # === ТЕЛЕГРАМ ===
    TELEGRAM_TOKEN = "8884017743:AAGD40tW3nHC5V9BtVM0lg-T6ix_WTckp9g"
    ADMIN_CHAT_ID = 228801334  
    
    # === API ===
    FOOTBALL_API_KEY = "a24b5e4f38e197977c773284022904ea"
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
    EV_MIN_70 = 30
    PROB_MIN_70 = 70
    POSITION_MAX_70 = 18
    FORM_REQUIRED_70 = ['excellent', 'good']
    SKIP_MID_TABLE_70 = True
    LIMIT_BET_TYPE_70 = 15
    LIMIT_LEAGUE_70 = 2
    
    # ============================================================
    # НАСТРОЙКИ ТМ 2.5
    # ============================================================
    
    MAX_TM25_BETS = 0
    MIN_TM25_EV = 99
    MIN_TM25_PROB = 99
    TM25_XG_MIN = 0.99
    TM25_XG_MAX = 0.99
    
    # PREMIUM (EV > 30%)
    PREMIUM_MIN_EV = 99
    PREMIUM_MIN_PROB = 99
    PREMIUM_XG_MIN = 0.99
    PREMIUM_XG_MAX = 0.99
    
    # STANDARD (EV > 15%)
    STANDARD_MIN_EV = 99
    STANDARD_MIN_PROB = 99
    STANDARD_XG_MIN = 0.99
    STANDARD_XG_MAX = 0.99
    
    TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']
    TM25_TOP_LEAGUE_EV = 35
    
    # ============================================================
    # MAPПИНГ ЛИГ ДЛЯ ODDS API
    # ============================================================
    
    ODDS_SPORT_MAP = {
        # === АНГЛИЯ ===
        'АПЛ': 'soccer_epl',
        'Premier League': 'soccer_epl',
        'Чемпионшип': 'soccer_efl_champ',
        'Championship': 'soccer_efl_champ',
        'Лига 1': 'soccer_england_league1',
        'League 1': 'soccer_england_league1',
        'Лига 2': 'soccer_england_league2',
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
        # === ИТАЛИЯ ===
        'Серия А': 'soccer_italy_serie_a',
        'Serie A': 'soccer_italy_serie_a',
        'Серия B': 'soccer_italy_serie_b',
        'Serie B': 'soccer_italy_serie_b',
        # === ФРАНЦИЯ ===
        'Ligue 1': 'soccer_france_ligue_one',
        'Ligue 2': 'soccer_france_ligue_two',
        # === НИДЕРЛАНДЫ ===
        'Эредивизи': 'soccer_netherlands_eredivisie',
        'Eredivisie': 'soccer_netherlands_eredivisie',
        # === ПОРТУГАЛИЯ ===
        'Примейра Лига': 'soccer_portugal_primeira_liga',
        'Primeira Liga': 'soccer_portugal_primeira_liga',
        # === БЕЛЬГИЯ ===
        'Про Лига': 'soccer_belgium_first_div',
        # === ТУРЦИЯ ===
        'Супер Лига': 'soccer_turkey_super_league',
        'Super Lig': 'soccer_turkey_super_league',
        # === ШОТЛАНДИЯ ===
        'Премьершип': 'soccer_spl',
        # === ДАНИЯ ===
        'Суперлига': 'soccer_denmark_superliga',
        # === НОРВЕГИЯ ===
        'Элитсериен': 'soccer_norway_eliteserien',
        # === ШВЕЦИЯ ===
        'Аллсвенскан': 'soccer_sweden_allsvenskan',
        # === ПОЛЬША ===
        'Экстракласа': 'soccer_poland_ekstraklasa',
        # === УКРАИНА ===
        'Премьер-Лига': 'soccer_ukraine_premier_league',
        # === РОССИЯ ===
        'РПЛ': 'soccer_russia_premier_league',
        # === ХОРВАТИЯ ===
        'HNL': 'soccer_croatia_hnl',
        # === ЕВРОПЕЙСКИЕ КУБКИ ===
        'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
        'UEFA Champions League': 'soccer_uefa_champs_league',
        'Лига Европы УЕФА': 'soccer_uefa_europa_league',
        'UEFA Europa League': 'soccer_uefa_europa_league',
        # === ЮЖНАЯ АМЕРИКА ===
        'Бразилия Серия А': 'soccer_brazil_campeonato',
        'Brasileirão': 'soccer_brazil_campeonato',
        'Аргентина Примера': 'soccer_argentina_primera_division',
        # === СЕВЕРНАЯ АМЕРИКА ===
        'MLS': 'soccer_usa_mls',
        'МЛС': 'soccer_usa_mls',
        # === МЕЖДУНАРОДНЫЕ ===
        'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
        'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
        # === АЗИЯ ===
        'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
        'Япония J1 Лига': 'soccer_japan_j_league',
        'J1 League': 'soccer_japan_j_league',
        'Южная Корея K Лига 1': 'soccer_korea_kleague1',
        'K League 1': 'soccer_korea_kleague1',
        'Австралия А-Лига': 'soccer_australia_a_league',
        'Китай Супер Лига': 'soccer_china_super_league',
    }
    
    # ============================================================
    # ЛИГИ (ПОЛНЫЙ СПИСОК - 76 ЛИГ)
    # ============================================================
    
    LEAGUES = [
        # === АНГЛИЯ ===
        39,   # Premier League
        40,   # Championship
        41,   # League One
        
        # === ИСПАНИЯ ===
        140,  # La Liga
        141,  # La Liga 2
        142,  # Primera Federación
        
        # === ГЕРМАНИЯ ===
        78,   # Bundesliga
        79,   # 2. Bundesliga
        80,   # 3. Liga
        
        # === ИТАЛИЯ ===
        135,  # Serie A
        136,  # Serie B
        137,  # Serie C
        
        # === ФРАНЦИЯ ===
        61,   # Ligue 1
        62,   # Ligue 2
        63,   # National
        
        # === НИДЕРЛАНДЫ ===
        88,   # Eredivisie
        89,   # Eerste Divisie
        
        # === ПОРТУГАЛИЯ ===
        94,   # Primeira Liga
        95,   # Segunda Liga
        
        # === ТУРЦИЯ ===
        203,  # Süper Lig
        204,  # TFF 1. Lig
        
        # === ГРЕЦИЯ ===
        197,  # Super League
        198,  # Super League 2
        
        # === ШОТЛАНДИЯ ===
        179,  # Premiership
        180,  # Championship
        
        # === БЕЛЬГИЯ ===
        144,  # Pro League
        145,  # Challenger Pro League
        
        # === ДАНИЯ ===
        119,  # Superliga
        120,  # 1. Division
        
        # === НОРВЕГИЯ ===
        164,  # Eliteserien
        165,  # OBOS-ligaen
        
        # === ШВЕЦИЯ ===
        188,  # Allsvenskan
        189,  # Superettan
        
        # === ПОЛЬША ===
        106,  # Ekstraklasa
        107,  # I Liga
        
        # === УКРАИНА ===
        95,   # Premier League
        96,   # Persha Liga
        
        # === АВСТРИЯ ===
        187,  # Bundesliga
        188,  # 2. Liga
        
        # === ШВЕЙЦАРИЯ ===
        206,  # Super League
        207,  # Challenge League
        
        # === ХОРВАТИЯ ===
        166,  # HNL
        167,  # 2. HNL
        
        # === СЛОВЕНИЯ ===
        260,  # Prva Liga
        261,  # 2. Liga
        
        # === СЕРБИЯ ===
        250,  # Super Liga
        
        # === БОЛГАРИЯ ===
        253,  # First League
        
        # === РУМЫНИЯ ===
        256,  # Liga 1
        
        # === СЛОВАКИЯ ===
        258,  # Super Liga
        
        # === ВЕНГРИЯ ===
        171,  # NB I
        
        # === РОССИЯ ===
        179,  # РПЛ
        180,  # Первая Лига
        181,  # Вторая Лига А
        182,  # Вторая Лига Б
        
        # === ЕВРОПЕЙСКИЕ КУБКИ ===
        2,    # Champions League
        3,    # Europa League
        848,  # Conference League
        
        # === ЮЖНАЯ АМЕРИКА ===
        71,   # Brasileirão
        128,  # Argentina Primera
        148,  # Uruguay Primera
        158,  # Colombia Primera A
        168,  # Chile Primera
        178,  # Ecuador Serie A
        180,  # Paraguay Primera
        182,  # Peru Liga 1
        
        # === СЕВЕРНАЯ АМЕРИКА ===
        253,  # MLS
        
        # === АЗИЯ ===
        307,  # Saudi Pro League
        150,  # J1 League
        151,  # J2 League
        154,  # K League 1
        155,  # K League 2
        183,  # A-League
        169,  # Chinese Super League
        
        # === АФРИКА ===
        276,  # South Africa Premier League
        278,  # Botola Pro (Марокко)
        279,  # Egyptian Premier League
    ]
    
    # ============================================================
    # КУБКИ
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
        15,   # Recopa Sudamericana
        848,  # Conference League
    ]
    
    # ============================================================
    # НАЗВАНИЯ ЛИГ (РАСШИРЕННЫЙ СПИСОК)
    # ============================================================
    
    LEAGUE_NAMES = {
        # === АНГЛИЯ ===
        39: "Premier League",
        40: "Championship",
        41: "League One",
        # === ИСПАНИЯ ===
        140: "La Liga",
        141: "La Liga 2",
        142: "Primera Federación",
        # === ГЕРМАНИЯ ===
        78: "Bundesliga",
        79: "2. Bundesliga",
        80: "3. Liga",
        # === ИТАЛИЯ ===
        135: "Serie A",
        136: "Serie B",
        137: "Serie C",
        # === ФРАНЦИЯ ===
        61: "Ligue 1",
        62: "Ligue 2",
        63: "National",
        # === НИДЕРЛАНДЫ ===
        88: "Eredivisie",
        89: "Eerste Divisie",
        # === ПОРТУГАЛИЯ ===
        94: "Primeira Liga",
        95: "Segunda Liga",
        # === ТУРЦИЯ ===
        203: "Süper Lig",
        204: "TFF 1. Lig",
        # === ГРЕЦИЯ ===
        197: "Super League",
        198: "Super League 2",
        # === ШОТЛАНДИЯ ===
        179: "Premiership",
        180: "Championship",
        # === БЕЛЬГИЯ ===
        144: "Pro League",
        145: "Challenger Pro League",
        # === ДАНИЯ ===
        119: "Superliga",
        120: "1. Division",
        # === НОРВЕГИЯ ===
        164: "Eliteserien",
        165: "OBOS-ligaen",
        # === ШВЕЦИЯ ===
        188: "Allsvenskan",
        189: "Superettan",
        # === ПОЛЬША ===
        106: "Ekstraklasa",
        107: "I Liga",
        # === УКРАИНА ===
        95: "Premier League",
        96: "Persha Liga",
        # === АВСТРИЯ ===
        187: "Bundesliga",
        188: "2. Liga",
        # === ШВЕЙЦАРИЯ ===
        206: "Super League",
        207: "Challenge League",
        # === ХОРВАТИЯ ===
        166: "HNL",
        167: "2. HNL",
        # === СЛОВЕНИЯ ===
        260: "Prva Liga",
        261: "2. Liga",
        # === СЕРБИЯ ===
        250: "Super Liga",
        # === БОЛГАРИЯ ===
        253: "First League",
        # === РУМЫНИЯ ===
        256: "Liga 1",
        # === СЛОВАКИЯ ===
        258: "Super Liga",
        # === ВЕНГРИЯ ===
        171: "NB I",
        # === РОССИЯ ===
        179: "РПЛ",
        180: "Первая Лига",
        181: "Вторая Лига А",
        182: "Вторая Лига Б",
        # === ЕВРОПЕЙСКИЕ КУБКИ ===
        2: "Champions League",
        3: "Europa League",
        848: "Conference League",
        # === ЮЖНАЯ АМЕРИКА ===
        71: "Brasileirão",
        128: "Argentina Primera",
        148: "Uruguay Primera",
        158: "Colombia Primera A",
        168: "Chile Primera",
        178: "Ecuador Serie A",
        180: "Paraguay Primera",
        182: "Peru Liga 1",
        # === СЕВЕРНАЯ АМЕРИКА ===
        253: "MLS",
        # === АЗИЯ ===
        307: "Saudi Pro League",
        150: "J1 League",
        151: "J2 League",
        154: "K League 1",
        155: "K League 2",
        183: "A-League",
        169: "Chinese Super League",
        # === АФРИКА ===
        276: "South Africa Premier",
        278: "Botola Pro",
        279: "Egyptian Premier",
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
        print(f"📋 Всего соревнований: {len(cls.LEAGUES) + len(cls.CUP_LEAGUES)}")
        print(f"🎯 Odds API маппинг: {len(cls.ODDS_SPORT_MAP)} лиг")
        
        return True

# ============================================================
# АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПРИ ЗАПУСКЕ
# ============================================================

Config.check()
