"""Конфигурация бота — Quantum Bet Bot PRO
Обновлено под тариф Ultra (75 000 req/day, 450 req/min)
★ ВЕРСИЯ 3.11 — оптимизировано под 75k запросов, исправлен риск-менеджмент
"""
import os
import sys
import sqlite3
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


class Config:
    # ============================================================
    # === ТЕЛЕГРАМ ===
    # ============================================================
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
    CHANNEL_ID = os.getenv("CHANNEL_ID", "")

    # ============================================================
    # === FOOTBALL API (Ultra 75k) ===
    # ============================================================
    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "").strip()
    FOOTBALL_API_URL = os.getenv("FOOTBALL_API_URL", "https://v3.football.api-sports.io").rstrip("/")
    
    # ★ Максимальная скорость (Rate Limit), Ultra обычно дает 450/мин
    FOOTBALL_API_MAX_RPM = 400 

    # ============================================================
    # === WEATHER API ===
    # ============================================================
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
    WEATHER_API_URL = os.getenv("WEATHER_API_URL", "https://api.openweathermap.org/data/2.5")
    WEATHER_ENABLED = bool(WEATHER_API_KEY)

    WEATHER_SKIP_RAIN_MM = 4.0
    WEATHER_SKIP_WIND_MS = 15.0
    WEATHER_SKIP_SNOW = True
    WEATHER_SKIP_TEMP_MIN = -10
    WEATHER_SKIP_TEMP_MAX = 40

    WEATHER_RAIN_XG_PENALTY = 0.90
    WEATHER_HEAVY_RAIN_XG_PENALTY = 0.80
    WEATHER_WIND_XG_PENALTY = 0.92
    WEATHER_HEAT_XG_PENALTY = 0.95
    WEATHER_COLD_XG_PENALTY = 0.93

    # ============================================================
    # === ODDS API (ОТКЛЮЧЕНО) ===
    # ============================================================
    # ★ С 75k запросов API-Football нам не нужен Odds API. 
    # Оставляем пустым, чтобы бот даже не пытался его дергать.
    ODDS_API_KEY = ""
    ODDS_API_URL = "https://api.the-odds-api.com/v4"
    BACKUP_ODDS_KEYS = []
    ODDS_API_DAILY_LIMIT = 0  

    # ============================================================
    # === LLM ===
    # ============================================================
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", LLM_API_KEY or "")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_ENABLED = bool(DEEPSEEK_API_KEY or LLM_API_KEY)

    # ============================================================
    # === ИНФРАСТРУКТУРА ===
    # ============================================================
    DATABASE_URL = os.getenv("DATABASE_URL", "/data/bot.db")
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
    USE_SEASON = int(os.getenv("USE_SEASON", str(datetime.now().year)))
    CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))

    # ★ С 75k запросов можно включить, чтобы бот сам собрал все доступные лиги
    USE_API_LEAGUES = True  

    # ============================================================
    # === PREDICTION ENGINE ===
    # ============================================================
    PREDICTION_ENGINE = os.getenv("PREDICTION_ENGINE", "heuristic")
    MIN_ODDS = 1.40
    MAX_ODDS = 8.00

    # ============================================================
    # === СТАВКИ ===
    # ============================================================
    MAX_BETS_PER_RUN = 30

    # ============================================================
    # === 70%+ ===
    # ============================================================
    XG_MIN_70 = 1.2
    XG_MAX_70 = 3.8
    EV_MIN_70 = 10
    PROB_MIN_70 = 50
    PROB_MAX_70 = 85.0
    POSITION_MAX_70 = 18
    SKIP_MID_TABLE_70 = False
    LIMIT_BET_TYPE_70 = 15
    LIMIT_LEAGUE_70 = 5
    MIN_ODD_70 = 1.40
    MAX_ODD_70 = 8.00

    # ============================================================
    # === КАЛИБРОВКА ===
    # ============================================================
    CALIBRATION_FACTOR = 0.91
    CALIBRATION_BY_BUCKET = {
        (0, 50):   1.00,
        (50, 65):  1.00,
        (65, 70):  1.00,
        (70, 75):  0.98,
        (75, 80):  0.90,
        (80, 85):  0.75,
        (85, 90):  0.65,
        (90, 100): 0.60,
    }

    # ============================================================
    # === ФИНАЛЬНЫЙ ФИЛЬТР ===
    # ============================================================
    # ★ ФИКС: EV_FINAL_MIN = -15, чтобы не отсекать VALUE и BTTS
    EV_FINAL_MIN = -15
    EV_FINAL_MAX = 150
    PROB_FINAL_MIN = 42

    # ============================================================
    # === X2 ===
    # ============================================================
    X2_ENABLED = True
    X2_MIN_POSITION_DIFF = 3
    X2_MAX_POSITION = 20
    X2_MIN_EV = 10
    X2_MIN_PROB = 52
    X2_BOTH_SIDES = False
    X2_MAX_PCT_OF_BETS = 0.40
    X2_HOME_BONUS = 3.0
    X2_AWAY_PENALTY = 2.0

    MIN_ODDS_1X = 1.70

    # ============================================================
    # ★ BTTS (Обе Забьют)
    # ============================================================
    BTTS_ENABLED = True
    BTTS_MAX_BETS = 3
    BTTS_MIN_ODDS = 1.60
    BTTS_MAX_ODDS = 2.20
    BTTS_MIN_EV = 8
    BTTS_MIN_PROB = 50
    BTTS_MIN_XG_EACH = 0.9
    BTTS_MIN_TOTAL_XG = 2.0

    BTTS_LEAGUE_WHITELIST = [
        'Bundesliga', '2. Bundesliga', '3. Liga',
        'Eredivisie', 'Eerste Divisie',
        'Championship', 'League One',
        'Süper Lig', 'Super League',
        'Eliteserien', 'OBOS-ligaen',
        'Superliga', '1. Division',
        'Brasileirão', 'Argentina Primera',
        'MLS', 'J1 League', 'Chinese Super League',
        'South Africa Premier', 'A-League',
    ]
    BTTS_LEAGUE_BONUS = 5

    BTTS_LEAGUE_BLACKLIST = [
        'Serie A', 'Serie B', 'Ligue 2', 'La Liga 2',
        'Ekstraklasa', 'I Liga', 'HNL', '2. HNL',
        'РПЛ', 'Первая Лига', 'Вторая Лига Б',
        'Persha Liga', 'Premier League Ukraine',
    ]

    BTTS_FORM_FILTER = True
    BTTS_FORM_MIN_SCORING = 3
    BTTS_H2H_FILTER = False
    BTTS_H2H_MIN_MATCHES = 4
    BTTS_H2H_MIN_PCT = 60
    BTTS_MAX_LEAGUE_BETS = 1
    BTTS_INCLUDE_INTERNATIONAL = False

    # ============================================================
    # ★ СТАТИСТИКА: УГЛОВЫЕ И КАРТОЧКИ
    # ============================================================
    STATS_ENABLED = True
    STATS_MIN_EV = 12           
    STATS_MIN_PROB = 55         
    STATS_CORNERS_MIN_AVG = 8.5 
    STATS_CARDS_MIN_AVG = 3.5   
    
    # ============================================================
    # ★ LINE MOVEMENT (Аномалии кэфов)
    # ============================================================
    LINE_MOVEMENT_ENABLED = True

    LINE_MOVEMENT_MIN_DROP_PCT = -6.0
    LINE_MOVEMENT_MAX_DROP_PCT = -15.0
    LINE_MOVEMENT_MIN_RISE_PCT = 8.0
    LINE_MOVEMENT_MAX_RISE_PCT = 20.0

    LINE_MOVEMENT_HOURS_BEFORE = 6
    LINE_MOVEMENT_MIN_SNAPSHOTS = 3
    LINE_MOVEMENT_MAX_SNAPSHOTS = 20

    LINE_MOVEMENT_TRADE_DROPS = True
    LINE_MOVEMENT_TRADE_RISES = False

    LINE_MOVEMENT_BET_TYPES = ['1', 'X', '2', '1X', 'X2']

    LINE_MOVEMENT_MAX_BETS = 2
    LINE_MOVEMENT_MAX_LEAGUE_BETS = 1

    LINE_MOVEMENT_MIN_ODDS = 1.40
    LINE_MOVEMENT_MAX_ODDS = 3.50

    LINE_MOVEMENT_STAKE_PCT = 0.015

    LINE_MOVEMENT_LEAGUE_BLACKLIST = [
        'Primera Federación', 'Serie C', '3. Liga', 'National',
        'Eerste Divisie', 'Challenger Pro League',
        'TFF 1. Lig', 'Persha Liga', 'I Liga', '2. HNL',
        'OBOS-ligaen', '2. Liga', 'Вторая Лига Б',
    ]

    LINE_MOVEMENT_LEAGUE_WHITELIST = [
        'Premier League', 'Championship', 'League One',
        'La Liga', 'La Liga 2',
        'Bundesliga', '2. Bundesliga',
        'Serie A', 'Serie B',
        'Ligue 1', 'Ligue 2',
        'Eredivisie',
        'Primeira Liga',
        'Pro League',
        'Süper Lig',
        'Superliga', '1. Division',
        'Eliteserien',
        'Ekstraklasa',
        'HNL',
        'Brasileirão',
        'Argentina Primera',
        'MLS',
        'J1 League',
        'Saudi Pro League',
        'A-League',
    ]

    # ============================================================
    # === VALUE ===
    # ============================================================
    VALUE_MIN_ODDS = 2.50
    VALUE_MIN_EV = 12
    VALUE_MIN_PROB = 42
    VALUE_MIN_XG_DIFF = 0.3
    VALUE_MAX_RESULTS = 5   
    VALUE_MAX_PROB = 80
    VALUE_MAX_RATIO = 2.2

    # ============================================================
    # ★ KELLY CRITERION (Защита банка)
    # ============================================================
    KELLY_ENABLED = True
    KELLY_FRACTION = 0.20      # ★ Безопасное значение (было 0.35)
    KELLY_MAX_PCT = 0.05       # Не более 5% банка на ставку
    KELLY_MIN_PCT = 0.02
    KELLY_MIN_STAKE = 1.0

    KELLY_BUCKET_FACTORS = {
        (0, 75):   1.0,
        (75, 80):  0.85,
        (80, 85):  0.65,
        (85, 100): 0.45, # Сильно режем на завышенных вероятностях
    }

    @classmethod
    def get_kelly_bucket_factor(cls, prob_pct):
        for (lo, hi), factor in cls.KELLY_BUCKET_FACTORS.items():
            if lo <= prob_pct < hi:
                return factor
        return 1.0

    # ============================================================
    # ★ CLV-ФИЛЬТР
    # ============================================================
    CLV_FILTER_ENABLED = True
    CLV_LOOKBACK_DAYS = 30
    CLV_MIN_SAMPLES = 20
    CLV_CACHE_TTL = 600

    CLV_EXCELLENT_THRESHOLD = 2.0
    CLV_GOOD_THRESHOLD = 0.0
    CLV_WEAK_THRESHOLD = -3.0

    CLV_MULT_EXCELLENT = 1.5
    CLV_MULT_NORMAL = 1.0
    CLV_MULT_WEAK = 0.5
    CLV_SKIP_CRITICAL = False

    # ============================================================
    # ★ LIVE-СТРАНИЦА (⚡) - Оптимизировано под 75k
    # ============================================================
    LIVE_HOURS_BEFORE = 2
    LIVE_MINUTES_AFTER = 120
    LIVE_REFRESH_SEC = 10        # ★ Ускорено (было 20)
    LIVE_BATCH_ENABLED = True
    LIVE_CACHE_TTL_LIVE = 30
    LIVE_CACHE_TTL_SOON = 300
    LIVE_CACHE_TTL_FINAL = 3600
    LIVE_MAX_MATCHES = 50        # ★ Увеличено (было 30)

    LIVE_SPARKLINE_ENABLED = True
    LIVE_SPARKLINE_POINTS = 10
    LIVE_SPARKLINE_MARKET = '1X2'
    LIVE_SPARKLINE_SELECTION = '1'

    # ============================================================
    # === WHITELIST ===
    # ============================================================
    WHITELIST_LEAGUES = [
        'premier league', 'championship',
        'efl league one', 'league one',
        'league two',
        'la liga', 'laliga',
        'segunda división', 'segunda division', 'la liga 2',
        'primera federación', 'primera federacion',
        'bundesliga', '2. bundesliga', '3. liga',
        'serie a', 'serie b', 'serie c',
        'ligue 1', 'ligue 2', 'national',
        'eredivisie', 'eerste divisie',
        'primeira liga', 'liga portugal',
        'segunda liga',
        'pro league', 'challenger pro league',
        'süper lig', 'super lig', 'tff 1. lig',
        'superliga', '1. division',
        'eliteserien', 'obos-ligaen',
        'ekstraklasa', 'i liga',
        'hnl', '2. hnl',
        'premier league ukraine', 'persha liga',
        'рпл', 'первая лига', 'вторая лига б',
        'super league', 'challenge league',
        'bundesliga austria',
        'brasileirão', 'brasileirao',
        'argentina primera', 'liga profesional',
        'liga mx', 'mls', 'major league soccer',
        'saudi pro league', 'j1 league',
        'chinese super league',
        'south africa premier', 'botola pro',
        'a-league',
        'champions league', 'uefa champions',
        'europa league', 'uefa europa',
        'conference league', 'uefa europa conference',
        'nations league', 'uefa nations',
        'world cup', 'wc qualification',
        'euro championship', 'euro qualification',
        'friendlies', 'international',
    ]

    # ============================================================
    # === BLACKLIST ===
    # ============================================================
    BLACKLIST_LEAGUES = [
        'isthmian', 'northern premier', 'southern league',
        'county league', 'combined counties',
        'united counties', 'premier division',
        'division one', 'division two',
        'championship north', 'championship south',
        'east counties', 'wessex league', 'western league',
        'northern counties east', 'northern counties west',
        'essex senior', 'hellenic league', 'midland league',
        'north west counties', 'spartan south midlands',
        'southern counties east', 'southern combination',
        'wessex football league', 'yorkshire league',
        ' ii', ' b ', 'reserve', 'reserves',
        'mls next pro', 'usl league', 'usl championship', 'next pro',
        'u19', 'u20', 'u21', 'u23', 'u18', 'u17',
        'youth', 'academy', 'junior', 'primavera',
        'women', 'womens', 'femenina', 'feminine', 'female', 'frauen',
        'primera b', 'primera c', 'primera d',
        'serie d',
        'regionalliga', 'oberliga', 'landesliga', 'verbandsliga',
        'torneo federal', 'torneo argentino',
        'prim b', 'prim c', 'prim d',
        'lpf', 'primera nacional',
        'segunda federación', 'tercera federación',
        'national 2', 'national 3', 'championnat national',
        'ii liga', 'iii liga',
        'copa paulista', 'carioca', 'gaúcho', 'mineiro',
        'baiano', 'pernambucano', 'cearense', 'paranaense',
        'capixaba', 'catarinense', 'potiguar', 'goiano',
        'amazonense', 'matogrossense', 'paraibano',
        'piauiense', 'sergipano', 'maranhense', 'acreano',
        'tocantinense', 'rondoniense', 'sul-matogrossense',
        'amapaense', 'brasiliense', 'candango', 'paraense',
        'persha liga', 'j2 league', 'j3 league',
        'k league 1', 'k league 2',
        'colombia primera a', 'chile primera', 'nb i',
        'ecuador serie a', 'вторая лига а', 'super league 2',
        'prva liga', 'egyptian premier',
        'uruguay primera', 'northern ireland', 'welsh premier',
        'irish premier', 'first division', # ★ Исправлено
    ]

    # ============================================================
    # ★ ТМ 2.5
    # ============================================================
    MAX_TM25_BETS = 5
    TM25_XG_MIN = 0.8
    TM25_XG_MAX = 3.0
    TM25_TOP_LEAGUE_EV = 35

    PREMIUM_MIN_EV = 25
    PREMIUM_MIN_PROB = 58
    PREMIUM_XG_MIN = 1.0
    PREMIUM_XG_MAX = 2.8

    STANDARD_MIN_EV = 20
    STANDARD_MIN_PROB = 56
    STANDARD_XG_MIN = 1.2
    STANDARD_XG_MAX = 2.8

    TM25_USE_KELLY = True
    TM25_INCLUDE_INTERNATIONAL = False
    TM25_FORM_FILTER = True
    TM25_H2H_FILTER = True
    TM25_MIN_H2H_MATCHES = 3
    TM25_H2H_AVG_MAX = 2.8
    TM25_LEAGUE_WHITELIST = [
        'Serie A', 'Serie B', 'La Liga 2', 'Primera Federación',
        'Ligue 2', 'Championship', 'League One',
        'Ekstraklasa', 'I Liga', 'Superliga', '1. Division',
        'Eliteserien', 'OBOS-ligaen',
        'HNL', '2. HNL', 'Super League', 'Challenge League',
        'РПЛ', 'Первая Лига', 'Вторая Лига Б',
    ]
    TM25_LEAGUE_BONUS = 5
    TM25_MAX_LEAGUE_BETS = 2
    TM25_FORM_UNDER_REQUIRED = False
    
    TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

    # ============================================================
    # === МАППИНГ ЛИГ ДЛЯ ODDS API (Оставлено на случай, если понадобится)
    # ============================================================
    ODDS_SPORT_MAP = {}

    # ============================================================
    # === СТРАНЫ ДЛЯ АВТОПОСТРОЕНИЯ СПИСКА ЛИГ ===
    # ============================================================
    LEAGUE_COUNTRIES = [
        'England', 'Spain', 'Germany', 'Italy', 'France',
        'Netherlands', 'Portugal', 'Belgium', 'Turkey',
        'Brazil', 'Argentina', 'Mexico', 'USA',
        'Saudi-Arabia', 'Japan',
        'World',
    ]

    # ============================================================
    # ★ СТРАНА + ФЛАГ ПО LEAGUE_ID (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ, ОЧЕНЬ ХОРОШО СДЕЛАНО)
    # ============================================================
    LEAGUE_COUNTRY = {
        2:   ("Европа", "🇪🇺"), 3:   ("Европа", "🇪🇺"), 848: ("Европа", "🇪🇺"),
        39:  ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"), 40:  ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"), 41:  ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        42:  ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        140: ("Испания", "🇪🇸"), 141: ("Испания", "🇪🇸"), 142: ("Испания", "🇪🇸"),
        78:  ("Германия", "🇩🇪"), 79:  ("Германия", "🇩🇪"), 80:  ("Германия", "🇩🇪"),
        135: ("Италия", "🇮🇹"), 136: ("Италия", "🇮🇹"), 137: ("Италия", "🇮🇹"),
        61:  ("Франция", "🇫🇷"), 62:  ("Франция", "🇫🇷"), 63:  ("Франция", "🇫🇷"),
        88:  ("Нидерланды", "🇳🇱"), 89:  ("Нидерланды", "🇳🇱"),
        94:  ("Португалия", "🇵🇹"), 95:  ("Португалия", "🇵🇹"),
        144: ("Бельгия", "🇧🇪"), 145: ("Бельгия", "🇧🇪"),
        203: ("Турция", "🇹🇷"), 204: ("Турция", "🇹🇷"),
        333: ("Украина", "🇺🇦"), 334: ("Украина", "🇺🇦"),
        106: ("Польша", "🇵🇱"), 107: ("Польша", "🇵🇱"),
        119: ("Дания", "🇩🇰"), 120: ("Дания", "🇩🇰"),
        164: ("Норвегия", "🇳🇴"), 165: ("Норвегия", "🇳🇴"),
        166: ("Хорватия", "🇭🇷"), 167: ("Хорватия", "🇭🇷"),
        206: ("Швейцария", "🇨🇭"), 207: ("Швейцария", "🇨🇭"),
        187: ("Австрия", "🇦🇹"),
        197: ("Греция", "🇬🇷"), 198: ("Греция", "🇬🇷"),
        261: ("Чехия", "🇨🇿"), 345: ("Чехия", "🇨🇿"),
        113: ("Швеция", "🇸🇪"),
        71:  ("Бразилия", "🇧🇷"), 128: ("Аргентина", "🇦🇷"), 253: ("США", "🇺🇸"),
        262: ("Мексика", "🇲🇽"),
        150: ("Япония", "🇯🇵"), 169: ("Китай", "🇨🇳"), 307: ("Саудовская Аравия", "🇸🇦"),
        276: ("ЮАР", "🇿🇦"), 278: ("Марокко", "🇲🇦"),
        183: ("Австралия", "🇦🇺"), 189: ("Австралия", "🇦🇺"),
        235: ("Россия", "🇷🇺"), 236: ("Россия", "🇷🇺"), 238: ("Россия", "🇷🇺"),
        179: ("Шотландия", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
        180: ("Шотландия", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
        182: ("Шотландия", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
        5:   ("Европа", "🇪🇺"),
        29:  ("Мир", "🌍"), 30:  ("Азия", "🌏"), 31:  ("Африка", "🌍"),
        32:  ("Европа", "🇪🇺"), 33:  ("Ю. Америка", "🌎"), 34:  ("Океания", "🌏"),
        35:  ("С. Америка", "🌎"),
        960: ("Европа", "🇪🇺"), 10:  ("Мир", "🌍"), 1:   ("Мир", "🏆"), 4:   ("Европа", "🏆"),
        45:  ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"), 48:  ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        143: ("Испания", "🇪🇸"), 81:  ("Германия", "🇩🇪"), 66:  ("Франция", "🇫🇷"),
        188: ("Австралия", "🇦🇺"), 286: ("Сербия", "🇷🇸"), 283: ("Румыния", "🇷🇴"),
        172: ("Болгария", "🇧🇬"), 272: ("Венгрия", "🇭🇺"), 332: ("Словакия", "🇸🇰"),
        373: ("Словения", "🇸🇮"), 239: ("Колумбия", "🇨🇴"), 240: ("Колумбия", "🇨🇴"),
        265: ("Чили", "🇨🇱"), 266: ("Чили", "🇨🇱"), 299: ("Эквадор", "🇪🇨"),
        301: ("Перу", "🇵🇪"), 370: ("Парагвай", "🇵🇾"), 339: ("Коста-Рика", "🇨🇷"),
        342: ("Уругвай", "🇺🇾"), 131: ("Аргентина", "🇦🇷"), 132: ("Аргентина", "🇦🇷"),
        151: ("Япония", "🇯🇵"), 170: ("Китай", "🇨🇳"), 308: ("Саудовская Аравия", "🇸🇦"),
        292: ("Ю. Корея", "🇰🇷"), 296: ("Таиланд", "🇹🇭"), 323: ("Индия", "🇮🇳"),
        233: ("Египет", "🇪🇬"), 98:  ("Япония", "🇯🇵"), 99:  ("Япония", "🇯🇵"),
        9:   ("Ю. Америка", "🌎"), 11:  ("С. Америка", "🌎"),
    }

    # ============================================================
    # ★ ТУРНИРЫ СБОРНЫХ
    # ============================================================
    INTERNATIONAL_LEAGUES = [5, 29, 30, 31, 32, 33, 34, 35, 960, 10, 1, 4]

    # ============================================================
    # ★ ЛИГИ (Резервный список, если USE_API_LEAGUES = False)
    # ============================================================
    LEAGUES = [
        2, 3, 848, 45, 48, 143, 81, 137, 66,
        39, 40, 41, 42, 140, 141, 78, 79, 135, 136, 61, 62,
        88, 89, 94, 95, 144, 145, 203, 204, 
        235, 236, 333, 334, 179, 180, 187, 188, 206, 207, 198, 197, 
        261, 345, 106, 107, 119, 120, 164, 165, 113, 114, 166, 167, 
        286, 283, 172, 272, 332, 373, 71, 128, 253, 262, 239, 265, 299, 301, 370, 339, 342, 131, 132,
        150, 151, 169, 307, 292, 296, 323, 98, 99, 276, 278, 233, 189,
        5, 1, 4, 29, 30, 31, 32, 33, 34, 35, 960, 10, 9, 11,
    ]

    CUP_LEAGUES = [2, 3, 848]

    # ============================================================
    # ★ LEAGUE_NAMES (Резервный список)
    # ============================================================
    LEAGUE_NAMES = {
        39: "Premier League", 40: "Championship", 41: "League One", 42: "League Two", 45: "FA Cup", 48: "League Cup",
        140: "La Liga", 141: "La Liga 2", 143: "Copa del Rey",
        78: "Bundesliga", 79: "2. Bundesliga", 81: "DFB Pokal",
        135: "Serie A", 136: "Serie B", 137: "Coppa Italia",
        61: "Ligue 1", 62: "Ligue 2", 66: "Coupe de France",
        88: "Eredivisie", 89: "Eerste Divisie", 94: "Primeira Liga", 95: "Segunda Liga",
        144: "Pro League", 145: "Challenger Pro League", 203: "Süper Lig", 204: "TFF 1. Lig",
        235: "РПЛ", 236: "Первая Лига", 333: "Premier League Ukraine", 334: "Persha Liga",
        179: "Premiership", 180: "Championship", 187: "Bundesliga Austria", 188: "Australia Cup",
        206: "Super League", 207: "Challenge League", 198: "Super League", 197: "Super League 2",
        261: "National Division", 345: "FNL", 106: "Ekstraklasa", 107: "I Liga",
        119: "Superliga", 120: "1. Division", 164: "Eliteserien", 165: "OBOS-ligaen",
        113: "Allsvenskan", 114: "Superettan", 166: "HNL", 167: "2. HNL",
        286: "Super Liga", 283: "Liga 1", 172: "First League", 272: "NB I",
        332: "Super Liga", 373: "Prva Liga",
        71: "Serie A", 128: "Primera Division", 253: "MLS", 254: "USL League One", 255: "USL Championship", 262: "Liga MX",
        239: "Primera A", 265: "Primera Division", 299: "Primera Division", 301: "Pro League",
        370: "Primera Division", 339: "Liga Nacional", 342: "Primera Division",
        131: "Primera B Metropolitana", 132: "Primera C",
        150: "J1 League", 151: "J2 League", 169: "Super League", 307: "Pro League", 292: "K League 1", 296: "Thai League 1", 323: "Indian Super League",
        98: "J1 League", 99: "J2 League",
        276: "Premier League", 278: "Botola Pro", 233: "Premier League",
        189: "A-League",
        5: "UEFA Nations League", 1: "World Cup", 4: "Euro Championship",
        29: "WC Qualification", 30: "WC Qualification Asia", 31: "WC Qualification Africa",
        32: "WC Qualification Europe", 33: "WC Qualification South America",
        34: "WC Qualification Oceania", 35: "WC Qualification CONCACAF",
        960: "Euro Qualification", 10: "Friendlies", 9: "Copa America", 11: "Gold Cup",
    }

    CITY_COORDS = { ... } # Оставляем как было

    # ============================================================
    # === API-МЕТОДЫ ===
    # ============================================================
    @classmethod
    def build_leagues_from_api(cls, season=None):
        if not cls.FOOTBALL_API_KEY:
            print("⚠️ Нет FOOTBALL_API_KEY — резервный список.")
            return False
        headers = {
            'x-apisports-key': cls.FOOTBALL_API_KEY,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        season = season or cls.USE_SEASON
        leagues, names = [], {}

        EXCLUDE_WORDS = [
            'women', 'womens', 'femenina', 'feminine', 'female', 'frauen',
            'u19', 'u20', 'u21', 'u23', 'u18', 'u17',
            'youth', 'reserve', 'academy', 'junior', 'primavera',
            'isthmian', 'northern premier', 'southern league',
            'county league', 'combined counties',
            'premier division', 'division one', 'division two',
            'championship north', 'championship south',
            'east counties', 'wessex league', 'western league',
            'northern counties east', 'northern counties west',
            'essex senior', 'hellenic league', 'midland league',
            'north west counties', 'spartan south midlands',
            'southern counties east', 'southern combination',
            'yorkshire league',
            'primera b', 'primera c', 'primera d',
            'serie d',
            'regionalliga', 'oberliga', 'landesliga', 'verbandsliga',
            'torneo federal', 'torneo argentino',
            'prim b', 'prim c', 'prim d',
            'lpf', 'primera nacional',
            'segunda federación', 'tercera federación',
            'amateur', 'npl', 'nsw', 'victoria', 'queensland',
            'south australia',
            'k4', 'k5', 'k6', 'k7',
            'copa paulista', 'carioca', 'gaúcho', 'mineiro',
            'baiano', 'pernambucano', 'cearense', 'paranaense',
            'national 2', 'national 3',
            'championnat national', 'cfa',
            'ii liga', 'iii liga',
        ]

        whitelist = cls.WHITELIST_LEAGUES

        for country in cls.LEAGUE_COUNTRIES:
            try:
                r = requests.get(
                    f"{cls.FOOTBALL_API_URL}/leagues",
                    headers=headers,
                    params={'country': country, 'season': season},
                    timeout=cls.REQUEST_TIMEOUT
                )
                if r.status_code != 200:
                    print(f"⚠️ {country}: HTTP {r.status_code}")
                    continue

                for item in r.json().get('response', []):
                    lg = item.get('league', {})
                    lid, lname = lg.get('id'), lg.get('name')
                    if not lid or not lname:
                        continue

                    lname_lower = lname.lower()

                    if lg.get('type') == 'Cup':
                        if not any(x in lname_lower for x in [
                            'champions league', 'europa league', 'conference league'
                        ]):
                            continue

                    if any(w in lname_lower for w in EXCLUDE_WORDS):
                        continue

                    if not any(good in lname_lower for good in whitelist):
                        continue

                    leagues.append(lid)
                    names[lid] = lname

                print(f"✅ {country}: OK")
            except Exception as e:
                print(f"❌ {country}: {e}")

        if leagues:
            cls.LEAGUES = sorted(set(leagues))
            cls.LEAGUE_NAMES = names
            print(f"🔄 Из API: {len(cls.LEAGUES)} лиг (после whitelist)")
            return True
        print("⚠️ API пусто — резервный список.")
        return False

    @classmethod
    def init_db(cls):
        db_dir = os.path.dirname(cls.DATABASE_URL)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(cls.DATABASE_URL)
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT, league TEXT, home TEXT, away TEXT,
                market TEXT, pick TEXT, odds REAL, confidence REAL,
                engine TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result TEXT
            );
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY, value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
        print(f"🗄️ БД: {cls.DATABASE_URL}")

    # ... остальные методы (get_weather, get_clv_multiplier и т.д.) оставляем без изменений
