"""Конфигурация бота — Quantum Bet Bot PRO
Обновлено под тариф Ultra (450 req/min, /odds, /predictions, /injuries)
★ ВЕРСИЯ 3.2 — с турнирами сборных (Лига наций, отборы ЧМ/ЧЕ)
"""
import os
import sys
import time
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
    # === FOOTBALL API (Ultra) ===
    # ============================================================
    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "").strip()
    FOOTBALL_API_URL = os.getenv("FOOTBALL_API_URL", "https://v3.football.api-sports.io").rstrip("/")

    # ============================================================
    # === WEATHER API ===
    # ============================================================
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
    WEATHER_API_URL = os.getenv("WEATHER_API_URL", "https://api.openweathermap.org/data/2.5")
    WEATHER_ENABLED = bool(WEATHER_API_KEY)

    # ============================================================
    # === ODDS API ===
    # ============================================================
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
    ODDS_API_URL = os.getenv("ODDS_API_URL", "https://api.the-odds-api.com/v4")
    BACKUP_ODDS_KEYS = [k.strip() for k in os.getenv("BACKUP_ODDS_KEYS", "").split(",") if k.strip()]

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

    # ============================================================
    # === PREDICTION ENGINE ===
    # ============================================================
    PREDICTION_ENGINE = os.getenv("PREDICTION_ENGINE", "heuristic")
    MIN_ODDS = 1.40
    MAX_ODDS = 8.00
    MAX_ODDS_SAFE = 3.50
    MIN_CONFIDENCE = 0.60

    # ============================================================
    # === СТАВКИ ===
    # ============================================================
    MAX_BETS_PER_RUN = 30

    # ============================================================
    # === 70%+ ===
    # ============================================================
    XG_MIN_70 = 1.2
    XG_MAX_70 = 3.8
    EV_MIN_70 = 8
    PROB_MIN_70 = 52
    POSITION_MAX_70 = 18
    FORM_REQUIRED_70 = ['excellent', 'good', 'average']
    SKIP_MID_TABLE_70 = False
    LIMIT_BET_TYPE_70 = 15
    LIMIT_LEAGUE_70 = 5
    MIN_ODD_70 = 1.40
    MAX_ODD_70 = 8.00

    # ============================================================
    # === ФИНАЛЬНЫЙ ФИЛЬТР ===
    # ============================================================
    EV_FINAL_MIN = -15
    EV_FINAL_MAX = 150
    PROB_FINAL_MIN = 40

    # ============================================================
    # === X2 ===
    # ============================================================
    X2_ENABLED = True
    X2_MIN_POSITION_DIFF = 3
    X2_MAX_POSITION = 20
    X2_MIN_EV = 5
    X2_MIN_PROB = 55
    X2_BOTH_SIDES = True

    # ============================================================
    # === VALUE (1 матч в день) ===
    # ============================================================
    VALUE_MIN_ODDS = 2.50
    VALUE_MIN_EV = 25
    VALUE_MIN_PROB = 50
    VALUE_MIN_XG_DIFF = 0.3
    VALUE_MAX_RESULTS = 3
    VALUE_MAX_PROB = 80
    VALUE_MAX_RATIO = 2.2

    # ============================================================
    # === WHITELIST (текстовый фильтр для /leagues API) ===
    # ============================================================
    WHITELIST_LEAGUES = [
        'premier league', 'championship',
        'efl league one', 'league one',
        'la liga', 'laliga',
        'segunda división', 'segunda division', 'la liga 2',
        'primera federación', 'primera federacion',
        'bundesliga', '2. bundesliga', '3. liga',
        'serie a', 'serie b', 'serie c',
        'ligue 1', 'ligue 2', 'national',
        'eredivisie', 'eerste divisie',
        'primeira liga', 'liga portugal',
        'pro league', 'challenger pro league',
        'süper lig', 'super lig', 'tff 1. lig',
        'superliga', '1. division',
        'eliteserien', 'obos-ligaen',
        'ekstraklasa', 'i liga',
        'hnl', '2. hnl',
        'premier league ukraine', 'persha liga',
        'рпл', 'первая лига',
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
        # ★ Турниры сборных
        'nations league', 'uefa nations',
        'world cup', 'wc qualification',
        'euro championship', 'euro qualification',
        'friendlies', 'international',
    ]

    # ============================================================
    # === BLACKLIST (текстовый фильтр) ===
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
        'irish premier', 'first division',
    ]

    # ============================================================
    # === ТМ 2.5 ===
    # ============================================================
    MAX_TM25_BETS = 5
    MIN_TM25_EV = 15
    MIN_TM25_PROB = 55
    TM25_XG_MIN = 0.8
    TM25_XG_MAX = 3.0
    PREMIUM_MIN_EV = 25
    PREMIUM_MIN_PROB = 58
    PREMIUM_XG_MIN = 1.0
    PREMIUM_XG_MAX = 2.8
    STANDARD_MIN_EV = 15
    STANDARD_MIN_PROB = 52
    STANDARD_XG_MIN = 0.8
    STANDARD_XG_MAX = 3.0
    TM25_TOP_LEAGUE_EV = 35

    TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

    # ============================================================
    # === МАППИНГ ЛИГ ДЛЯ ODDS API ===
    # ============================================================
    ODDS_SPORT_MAP = {
        'АПЛ': 'soccer_epl', 'Premier League': 'soccer_epl',
        'Чемпионшип': 'soccer_efl_champ', 'Championship': 'soccer_efl_champ',
        'Лига 1 Англия': 'soccer_england_league1', 'League One': 'soccer_england_league1',
        'Ла Лига': 'soccer_spain_la_liga', 'La Liga': 'soccer_spain_la_liga',
        'Сегунда': 'soccer_spain_segunda_division', 'La Liga 2': 'soccer_spain_segunda_division',
        'Бундеслига': 'soccer_germany_bundesliga', 'Bundesliga': 'soccer_germany_bundesliga',
        'Вторая Бундеслига': 'soccer_germany_bundesliga2', '2. Bundesliga': 'soccer_germany_bundesliga2',
        'Серия А': 'soccer_italy_serie_a', 'Serie A': 'soccer_italy_serie_a',
        'Серия B': 'soccer_italy_serie_b', 'Serie B': 'soccer_italy_serie_b',
        'Ligue 1': 'soccer_france_ligue_one', 'Ligue 2': 'soccer_france_ligue_two',
        'Эредивизи': 'soccer_netherlands_eredivisie', 'Eredivisie': 'soccer_netherlands_eredivisie',
        'Примейра Лига': 'soccer_portugal_primeira_liga', 'Primeira Liga': 'soccer_portugal_primeira_liga',
        'Про Лига': 'soccer_belgium_first_div',
        'Супер Лига': 'soccer_turkey_super_league', 'Süper Lig': 'soccer_turkey_super_league',
        'Премьершип': 'soccer_spl',
        'Суперлига': 'soccer_denmark_superliga', 'Superliga': 'soccer_denmark_superliga',
        'Элитсериен': 'soccer_norway_eliteserien', 'Eliteserien': 'soccer_norway_eliteserien',
        'Аллсвенскан': 'soccer_sweden_allsvenskan',
        'Экстракласа': 'soccer_poland_ekstraklasa', 'Ekstraklasa': 'soccer_poland_ekstraklasa',
        'Премьер-Лига Украина': 'soccer_ukraine_premier_league',
        'РПЛ': 'soccer_russia_premier_league',
        'HNL': 'soccer_croatia_hnl',
        'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
        'UEFA Champions League': 'soccer_uefa_champs_league',
        'Лига Европы УЕФА': 'soccer_uefa_europa_league',
        'UEFA Europa League': 'soccer_uefa_europa_league',
        'Бразилия Серия А': 'soccer_brazil_campeonato', 'Brasileirão': 'soccer_brazil_campeonato',
        'Аргентина Примера': 'soccer_argentina_primera_division',
        'MLS': 'soccer_usa_mls', 'МЛС': 'soccer_usa_mls',
        'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
        'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
        'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
        'Япония J1 Лига': 'soccer_japan_j_league', 'J1 League': 'soccer_japan_j_league',
        'Австралия А-Лига': 'soccer_australia_a_league',
        'Китай Супер Лига': 'soccer_china_super_league',
    }

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
    # ★ СТРАНА + ФЛАГ ПО LEAGUE_ID (для отображения в карточке)
    # ============================================================
    LEAGUE_COUNTRY = {
        # ── Европейские кубки ──
        2:   ("Европа", "🇪🇺"),
        3:   ("Европа", "🇪🇺"),
        848: ("Европа", "🇪🇺"),
        # ── Англия ──
        39:  ("Англия", "🇬🇧"),
        40:  ("Англия", "🇬🇧"),
        41:  ("Англия", "🇬🇧"),
        # ── Испания ──
        140: ("Испания", "🇪🇸"),
        141: ("Испания", "🇪🇸"),
        142: ("Испания", "🇪🇸"),
        # ── Германия ──
        78:  ("Германия", "🇩🇪"),
        79:  ("Германия", "🇩🇪"),
        80:  ("Германия", "🇩🇪"),
        # ── Италия ──
        135: ("Италия", "🇮🇹"),
        136: ("Италия", "🇮🇹"),
        137: ("Италия", "🇮🇹"),
        # ── Франция ──
        61:  ("Франция", "🇫🇷"),
        62:  ("Франция", "🇫🇷"),
        63:  ("Франция", "🇫🇷"),
        # ── Нидерланды ──
        88:  ("Нидерланды", "🇳🇱"),
        89:  ("Нидерланды", "🇳🇱"),
        # ── Португалия ──
        94:  ("Португалия", "🇵🇹"),
        # ── Бельгия ──
        144: ("Бельгия", "🇧🇪"),
        145: ("Бельгия", "🇧🇪"),
        # ── Турция ──
        203: ("Турция", "🇹🇷"),
        204: ("Турция", "🇹🇷"),
        # ── Украина ──
        95:  ("Украина", "🇺🇦"),
        96:  ("Украина", "🇺🇦"),
        # ── Польша ──
        106: ("Польша", "🇵🇱"),
        107: ("Польша", "🇵🇱"),
        # ── Дания ──
        119: ("Дания", "🇩🇰"),
        120: ("Дания", "🇩🇰"),
        # ── Норвегия ──
        164: ("Норвегия", "🇳🇴"),
        165: ("Норвегия", "🇳🇴"),
        # ── Хорватия ──
        166: ("Хорватия", "🇭🇷"),
        167: ("Хорватия", "🇭🇷"),
        # ── Швейцария ──
        206: ("Швейцария", "🇨🇭"),
        207: ("Швейцария", "🇨🇭"),
        # ── Австрия ──
        187: ("Австрия", "🇦🇹"),
        # ── Греция ──
        197: ("Греция", "🇬🇷"),
        # ── Чехия ──
        261: ("Чехия", "🇨🇿"),
        # ── Америка ──
        71:  ("Бразилия", "🇧🇷"),
        128: ("Аргентина", "🇦🇷"),
        253: ("США", "🇺🇸"),
        # ── Азия ──
        150: ("Япония", "🇯🇵"),
        169: ("Китай", "🇨🇳"),
        307: ("Саудовская Аравия", "🇸🇦"),
        # ── Африка ──
        276: ("ЮАР", "🇿🇦"),
        278: ("Марокко", "🇲🇦"),
        # ── Австралия ──
        183: ("Австралия", "🇦🇺"),
        # ── Россия ──
        179: ("Россия", "🇷🇺"),
        180: ("Россия", "🇷🇺"),
        182: ("Россия", "🇷🇺"),
        # ★ ── ТУРНИРЫ СБОРНЫХ ──
        5:   ("Европа", "🇪🇺"),      # UEFA Nations League
        29:  ("Мир", "🌍"),           # WC Qualification (general)
        30:  ("Азия", "🌏"),          # WC Qualification Asia
        31:  ("Африка", "🌍"),        # WC Qualification Africa
        32:  ("Европа", "🇪🇺"),       # WC Qualification Europe
        33:  ("Ю. Америка", "🌎"),    # WC Qualification South America
        34:  ("Океания", "🌏"),       # WC Qualification Oceania
        35:  ("С. Америка", "🌎"),    # WC Qualification CONCACAF
        960: ("Европа", "🇪🇺"),       # Euro Championship Qualification
        10:  ("Мир", "🌍"),           # Friendlies
        1:   ("Мир", "🏆"),           # World Cup
        4:   ("Европа", "🏆"),        # Euro Championship
    }

    # ============================================================
    # ★ ТУРНИРЫ СБОРНЫХ (отдельный список)
    # ============================================================
    INTERNATIONAL_LEAGUES = [
        5,    # UEFA Nations League
        29,   # WC Qualification (общий)
        30,   # WC Qualification Asia
        31,   # WC Qualification Africa
        32,   # WC Qualification Europe
        33,   # WC Qualification South America
        34,   # WC Qualification Oceania
        35,   # WC Qualification CONCACAF
        960,  # Euro Championship Qualification
        10,   # Friendlies (International)
        1,    # World Cup (финальная часть)
        4,    # Euro Championship (финальная часть)
    ]

    # ============================================================
    # ★ ЛИГИ С ПОДТВЕРЖДЁННЫМИ КЭФАМИ + ТУРНИРЫ СБОРНЫХ
    # ============================================================
    LEAGUES = [
        # ── Англия ──
        39, 40, 41,
        # ── Испания ──
        140, 141, 142,
        # ── Германия ──
        78, 79, 80,
        # ── Италия ──
        135, 136, 137,
        # ── Франция ──
        61, 62, 63,
        # ── Нидерланды ──
        88, 89,
        # ── Португалия ──
        94,
        # ── Бельгия ──
        144, 145,
        # ── Турция ──
        203, 204,
        # ── Украина ──
        95, 96,
        # ── Польша ──
        106, 107,
        # ── Дания ──
        119, 120,
        # ── Норвегия ──
        164, 165,
        # ── Хорватия ──
        166, 167,
        # ── Швейцария ──
        206, 207,
        # ── Австрия ──
        187,
        # ── Греция ──
        197,
        # ── Чехия ──
        261,
        # ── Америка ──
        71, 128, 253,
        # ── Азия ──
        150, 169, 307,
        # ── Африка ──
        276, 278,
        # ── Австралия ──
        183,
        # ── Россия ──
        179, 180, 182,
        # ── Кубки ──
        2, 3, 848,
        # ★ ── ТУРНИРЫ СБОРНЫХ ──
        5,    # UEFA Nations League
        29, 30, 31, 32, 33, 34, 35,  # WC Qualification
        960,  # Euro Championship Qualification
        10,   # Friendlies
        1,    # World Cup
        4,    # Euro Championship
    ]

    CUP_LEAGUES = [2, 3, 848]

    # ============================================================
    # ★ LEAGUE_NAMES
    # ============================================================
    LEAGUE_NAMES = {
        # Кубки
        2: "UEFA Champions League",
        3: "UEFA Europa League",
        848: "UEFA Conference League",
        # Англия
        39: "Premier League",
        40: "Championship",
        41: "League One",
        # Испания
        140: "La Liga",
        141: "La Liga 2",
        142: "Primera Federación",
        # Германия
        78: "Bundesliga",
        79: "2. Bundesliga",
        80: "3. Liga",
        # Италия
        135: "Serie A",
        136: "Serie B",
        137: "Serie C",
        # Франция
        61: "Ligue 1",
        62: "Ligue 2",
        63: "National",
        # Нидерланды
        88: "Eredivisie",
        89: "Eerste Divisie",
        # Португалия
        94: "Primeira Liga",
        # Бельгия
        144: "Pro League",
        145: "Challenger Pro League",
        # Турция
        203: "Süper Lig",
        204: "TFF 1. Lig",
        # Украина
        95: "Premier League",
        96: "Persha Liga",
        # Польша
        106: "Ekstraklasa",
        107: "I Liga",
        # Дания
        119: "Superliga",
        120: "1. Division",
        # Норвегия
        164: "Eliteserien",
        165: "OBOS-ligaen",
        # Хорватия
        166: "HNL",
        167: "2. HNL",
        # Швейцария
        206: "Super League",
        207: "Challenge League",
        # Австрия
        187: "Bundesliga",
        # Греция
        197: "Super League",
        # Чехия
        261: "2. Liga",
        # Америка
        71: "Brasileirão",
        128: "Argentina Primera",
        253: "MLS",
        # Азия
        150: "J1 League",
        169: "Chinese Super League",
        307: "Saudi Pro League",
        # Африка
        276: "South Africa Premier",
        278: "Botola Pro",
        # Австралия
        183: "A-League",
        # Россия
        179: "РПЛ",
        180: "Первая Лига",
        182: "Вторая Лига Б",
        # ★ Турниры сборных
        5:   "UEFA Nations League",
        29:  "World Cup Qualification",
        30:  "WC Qualification Asia",
        31:  "WC Qualification Africa",
        32:  "WC Qualification Europe",
        33:  "WC Qualification South America",
        34:  "WC Qualification Oceania",
        35:  "WC Qualification CONCACAF",
        960: "Euro Championship Qualification",
        10:  "Friendlies International",
        1:   "World Cup",
        4:   "Euro Championship",
    }

    # ============================================================
    # === КООРДИНАТЫ ГОРОДОВ ДЛЯ ПОГОДЫ ===
    # ============================================================
    CITY_COORDS = {
        "London": (51.5074, -0.1278), "Manchester": (53.4808, -2.2426),
        "Liverpool": (53.4084, -2.9916), "Birmingham": (52.4862, -1.8904),
        "Leeds": (53.8008, -1.5491), "Newcastle": (54.9783, -1.6178),
        "Madrid": (40.4168, -3.7038), "Barcelona": (41.3851, 2.1734),
        "Seville": (37.3891, -5.9845), "Valencia": (39.4699, -0.3763),
        "Bilbao": (43.2630, -2.9350),
        "Munich": (48.1351, 11.5820), "Berlin": (52.5200, 13.4050),
        "Dortmund": (51.5136, 7.4653), "Hamburg": (53.5511, 9.9937),
        "Frankfurt": (50.1109, 8.6821), "Cologne": (50.9375, 6.9603),
        "Milan": (45.4642, 9.1900), "Rome": (41.9028, 12.4964),
        "Turin": (45.0703, 7.6869), "Naples": (40.8518, 14.2681),
        "Florence": (43.7696, 11.2558),
        "Paris": (48.8566, 2.3522), "Marseille": (43.2965, 5.3698),
        "Lyon": (45.7640, 4.8357), "Lille": (50.6292, 3.0573),
        "Amsterdam": (52.3676, 4.9041), "Rotterdam": (51.9244, 4.4777),
        "Lisbon": (38.7223, -9.1393), "Porto": (41.1579, -8.6291),
        "Istanbul": (41.0082, 28.9784), "Ankara": (39.9334, 32.8597),
        "Glasgow": (55.8642, -4.2518), "Edinburgh": (55.9533, -3.1883),
        "Copenhagen": (55.6761, 12.5683), "Oslo": (59.9139, 10.7522),
        "Stockholm": (59.3293, 18.0686), "Warsaw": (52.2297, 21.0122),
        "Kyiv": (50.4501, 30.5234),
        "Moscow": (55.7558, 37.6173), "Saint Petersburg": (59.9311, 30.3609),
        "Zagreb": (45.8150, 15.9819), "Vienna": (48.2082, 16.3738),
        "Zurich": (47.3769, 8.5417), "Athens": (37.9838, 23.7275),
        "Prague": (50.0755, 14.4378),
        "Rio de Janeiro": (-22.9068, -43.1729), "Sao Paulo": (-23.5505, -46.6333),
        "Buenos Aires": (-34.6037, -58.3816),
        "Mexico City": (19.4326, -99.1332),
        "New York": (40.7128, -74.0060), "Los Angeles": (34.0522, -118.2437),
        "Tokyo": (35.6762, 139.6503),
        "Riyadh": (24.7136, 46.6753), "Jeddah": (21.4858, 39.1925),
        "Doha": (25.2854, 51.5310), "Dubai": (25.2048, 55.2708),
        "Johannesburg": (-26.2041, 28.0473), "Cape Town": (-33.9249, 18.4241),
        "Cairo": (30.0444, 31.2357),
    }

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
    def fetch_league_ids(cls):
        cls.build_leagues_from_api()
        return cls.LEAGUE_NAMES

    @classmethod
    def get_whitelist_ids(cls):
        return sorted(set(cls.LEAGUES))

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

    @classmethod
    def get_weather(cls, lat, lon):
        if not cls.WEATHER_ENABLED:
            return None
        try:
            r = requests.get(
                f"{cls.WEATHER_API_URL}/weather",
                params={'lat': lat, 'lon': lon, 'appid': cls.WEATHER_API_KEY, 'units': 'metric'},
                timeout=cls.REQUEST_TIMEOUT
            )
            if r.status_code == 200:
                d = r.json()
                return {
                    'temp': d['main']['temp'],
                    'wind': d['wind']['speed'],
                    'rain': d.get('rain', {}).get('1h', 0),
                    'desc': d['weather'][0]['description'],
                }
        except Exception as e:
            print(f"❌ Погода: {e}")
        return None

    @classmethod
    def get_weather_for_city(cls, city):
        if not cls.WEATHER_ENABLED or not city:
            return None
        coords = cls.CITY_COORDS.get(city)
        if not coords:
            return None
        return cls.get_weather(coords[0], coords[1])

    @classmethod
    def check(cls):
        missing = []
        if not cls.TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
        if not cls.ADMIN_CHAT_ID: missing.append("ADMIN_CHAT_ID")
        if not cls.FOOTBALL_API_KEY: missing.append("FOOTBALL_API_KEY")
        if missing:
            print(f"⚠️ Отсутствуют: {', '.join(missing)}")
        else:
            print("✅ Все ключи загружены!")
        print(f"🌦️ Погода: {'вкл' if cls.WEATHER_ENABLED else 'выкл'}")
        print(f"🧠 PREDICTION_ENGINE: {cls.PREDICTION_ENGINE}")
        print(f"🤖 LLM: {'вкл' if cls.LLM_ENABLED else 'выкл'} ({cls.LLM_PROVIDER}) | модель: {cls.LLM_MODEL}")
        print(f"📅 Сезон: {cls.USE_SEASON}")
        print(f"🗄️ БД: {cls.DATABASE_URL}")
        print(f"🚫 Чёрный список лиг: {len(cls.BLACKLIST_LEAGUES)} записей")
        print(f"✅ Белый список лиг: {len(cls.WHITELIST_LEAGUES)} записей")
        print(f"🌍 Стран для поиска: {len(cls.LEAGUE_COUNTRIES)}")
        print(f"🏳️ Стран в LEAGUE_COUNTRY: {len(cls.LEAGUE_COUNTRY)}")
        print(f"🌐 Турниров сборных: {len(cls.INTERNATIONAL_LEAGUES)}")
        cls.init_db()
        print(f"📊 Лиг: {len(set(cls.LEAGUES))}")
        print(f"🏆 Кубков: {len(set(cls.CUP_LEAGUES))}")
        return True


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "check"
    if arg == "check":
        Config.check()
    else:
        print("Использование:")
        print("  python3 -m app.config check — общая проверка")
