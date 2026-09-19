"""Конфигурация бота — Quantum Bet Bot PRO
Обновлено под тариф Ultra (450 req/min, /odds, /predictions, /injuries)
★ ВЕРСИЯ 3.3 — Odds API отключён, расширенный CITY_COORDS (220+ городов)
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
    # === ODDS API — ★ ОТКЛЮЧЁН ===
    # ============================================================
    ODDS_API_KEY = ""
    ODDS_API_URL = os.getenv("ODDS_API_URL", "https://api.the-odds-api.com/v4")
    ODDS_API_ENABLED = False
    BACKUP_ODDS_KEYS = []

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
    # ★ СКОРОСТЬ ПОИСКА
    # ============================================================
    STATS_ENABLED = False
    USE_H2H = True
    USE_PREDICTIONS = True

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
    # ★ X2 СТРАТЕГИЯ
    # ============================================================
    X2_ENABLED = True
    X2_MIN_EV = 5
    X2_MIN_PROB = 55
    X2_MIN_POSITION_DIFF = 3
    X2_MAX_POSITION = 20
    X2_BOTH_SIDES = True

    # ============================================================
    # ★ WHITELIST
    # ============================================================
    WHITELIST_LEAGUES = [
        'premier league', 'championship', 'efl league one', 'league one',
        'la liga', 'laliga', 'segunda división', 'segunda division', 'la liga 2',
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
        'saudi pro league', 'j1 league', 'chinese super league',
        'south africa premier', 'botola pro',
        'a-league',
        'champions league', 'uefa champions',
        'europa league', 'uefa europa',
        'conference league', 'uefa europa conference',
    ]

    # ============================================================
    # ★ BLACKLIST
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
    # === МАППИНГ ДЛЯ ODDS API (не используется) ===
    # ============================================================
    ODDS_SPORT_MAP = {
        'Premier League': 'soccer_epl',
        'Championship': 'soccer_efl_champ',
        'La Liga': 'soccer_spain_la_liga',
        'Bundesliga': 'soccer_germany_bundesliga',
        'Serie A': 'soccer_italy_serie_a',
        'Ligue 1': 'soccer_france_ligue_one',
        'Eredivisie': 'soccer_netherlands_eredivisie',
        'Primeira Liga': 'soccer_portugal_primeira_liga',
        'Süper Lig': 'soccer_turkey_super_league',
        'UEFA Champions League': 'soccer_uefa_champs_league',
        'UEFA Europa League': 'soccer_uefa_europa_league',
        'MLS': 'soccer_usa_mls',
        'Brasileirão': 'soccer_brazil_campeonato',
        'Argentina Primera': 'soccer_argentina_primera_division',
    }

    # ============================================================
    # === СТРАНЫ ===
    # ============================================================
    LEAGUE_COUNTRIES = [
        'England', 'Spain', 'Germany', 'Italy', 'France',
        'Netherlands', 'Portugal', 'Belgium', 'Turkey',
        'Brazil', 'Argentina', 'Mexico', 'USA',
        'Saudi-Arabia', 'Japan',
        'World',
    ]

    # ============================================================
    # ★ ЛИГИ С КЭФАМИ
    # ============================================================
    LEAGUES = [
        39, 40, 41,
        140, 141, 142,
        78, 79, 80,
        135, 136, 137,
        61, 62, 63,
        88, 89,
        94,
        144, 145,
        203, 204,
        95, 96,
        106, 107,
        119, 120,
        164, 165,
        166, 167,
        206, 207,
        187,
        197,
        261,
        71,
        128,
        253,
        150,
        169,
        307,
        276,
        278,
        183,
        179, 180, 182,
        2, 3, 848,
    ]

    CUP_LEAGUES = [2, 3, 848]

    LEAGUE_NAMES = {
        2: "UEFA Champions League", 3: "UEFA Europa League", 848: "UEFA Conference League",
        39: "Premier League", 40: "Championship", 41: "League One",
        140: "La Liga", 141: "La Liga 2", 142: "Primera Federación",
        78: "Bundesliga", 79: "2. Bundesliga", 80: "3. Liga",
        135: "Serie A", 136: "Serie B", 137: "Serie C",
        61: "Ligue 1", 62: "Ligue 2", 63: "National",
        88: "Eredivisie", 89: "Eerste Divisie",
        94: "Primeira Liga",
        144: "Pro League", 145: "Challenger Pro League",
        203: "Süper Lig", 204: "TFF 1. Lig",
        95: "Premier League", 96: "Persha Liga",
        106: "Ekstraklasa", 107: "I Liga",
        119: "Superliga", 120: "1. Division",
        164: "Eliteserien", 165: "OBOS-ligaen",
        166: "HNL", 167: "2. HNL",
        206: "Super League", 207: "Challenge League",
        187: "Bundesliga",
        197: "Super League",
        261: "2. Liga",
        71: "Brasileirão", 128: "Argentina Primera", 253: "MLS",
        150: "J1 League", 169: "Chinese Super League", 307: "Saudi Pro League",
        276: "South Africa Premier", 278: "Botola Pro",
        183: "A-League",
        179: "РПЛ", 180: "Первая Лига", 182: "Вторая Лига Б",
    }

    # ============================================================
    # ★ КООРДИНАТЫ ГОРОДОВ ДЛЯ ПОГОДЫ (220+)
    # ============================================================
    CITY_COORDS = {
        # ── АНГЛИЯ ──
        "London": (51.5074, -0.1278),
        "Manchester": (53.4808, -2.2426),
        "Liverpool": (53.4084, -2.9916),
        "Birmingham": (52.4862, -1.8904),
        "Leeds": (53.8008, -1.5491),
        "Newcastle": (54.9783, -1.6178),
        "Sheffield": (53.3811, -1.4701),
        "Nottingham": (52.9548, -1.1581),
        "Leicester": (52.6369, -1.1398),
        "Southampton": (50.9097, -1.4044),
        "Brighton": (50.8225, -0.1372),
        "Bristol": (51.4545, -2.5879),
        "Stoke": (53.0027, -2.1794),
        "Stoke-on-Trent": (53.0027, -2.1794),
        "Wolverhampton": (52.5870, -2.1288),
        "Everton": (53.4386, -2.9663),
        "Sunderland": (54.9069, -1.3838),
        "Middlesbrough": (54.5742, -1.2350),
        "Hull": (53.7457, -0.3367),
        "Blackburn": (53.7480, -2.4820),
        "Bolton": (53.5768, -2.4282),
        "Reading": (51.4543, -0.9781),
        "Ipswich": (52.0567, 1.1482),
        "Norwich": (52.6309, 1.2974),
        "Watford": (51.6565, -0.3903),
        "Coventry": (52.4068, -1.5197),
        "Derby": (52.9225, -1.4746),
        "Millwall": (51.4850, -0.0510),
        "Luton": (51.8787, -0.4200),
        "Burnley": (53.7890, -2.2482),
        "Bournemouth": (50.7192, -1.8808),
        "Swansea": (51.6214, -3.9436),
        "Cardiff": (51.4816, -3.1791),
        "Wrexham": (53.0430, -2.9925),
        "Plymouth": (50.3755, -4.1427),
        "Portsmouth": (50.8198, -1.0877),
        "Blackpool": (53.8175, -3.0357),
        "Preston": (53.7632, -2.7031),
        "Oxford": (51.7520, -1.2577),
        "Cambridge": (52.2053, 0.1218),
        "Peterborough": (52.5695, -0.2405),

        # ── ИСПАНИЯ ──
        "Madrid": (40.4168, -3.7038),
        "Barcelona": (41.3851, 2.1734),
        "Seville": (37.3891, -5.9845),
        "Valencia": (39.4699, -0.3763),
        "Bilbao": (43.2630, -2.9350),
        "Vigo": (42.2406, -8.7207),
        "Villareal": (39.9384, -0.1018),
        "Villarreal": (39.9384, -0.1018),
        "Alicante": (38.3452, -0.4810),
        "Malaga": (36.7213, -4.4214),
        "Granada": (37.1773, -3.5986),
        "Zaragoza": (41.6488, -0.8891),
        "Pamplona": (42.8125, -1.6458),
        "Valladolid": (41.6521, -4.7245),
        "Santander": (43.4623, -3.8100),
        "Eibar": (43.1843, -2.4714),
        "Getafe": (40.3083, -3.7325),
        "Leganes": (40.3282, -3.7635),
        "Girona": (41.9794, 2.8214),
        "Osasuna": (42.8125, -1.6458),
        "Las Palmas": (28.1248, -15.4300),

        # ── ГЕРМАНИЯ ──
        "Munich": (48.1351, 11.5820),
        "München": (48.1351, 11.5820),
        "Berlin": (52.5200, 13.4050),
        "Dortmund": (51.5136, 7.4653),
        "Hamburg": (53.5511, 9.9937),
        "Frankfurt": (50.1109, 8.6821),
        "Cologne": (50.9375, 6.9603),
        "Köln": (50.9375, 6.9603),
        "Stuttgart": (48.7758, 9.1829),
        "Düsseldorf": (51.2277, 6.7735),
        "Dusseldorf": (51.2277, 6.7735),
        "Leipzig": (51.3397, 12.3731),
        "Bremen": (53.0793, 8.8017),
        "Hannover": (52.3759, 9.7320),
        "Nürnberg": (49.4521, 11.0767),
        "Nuremberg": (49.4521, 11.0767),
        "Bochum": (51.4818, 7.2197),
        "Gelsenkirchen": (51.5177, 7.0857),
        "Mönchengladbach": (51.1805, 6.4428),
        "Leverkusen": (51.0459, 7.0192),
        "Wolfsburg": (52.4227, 10.7865),
        "Augsburg": (48.3705, 10.8978),
        "Hoffenheim": (49.2725, 8.8722),
        "Sinsheim": (49.2521, 8.8768),
        "Mainz": (49.9929, 8.2473),
        "Freiburg": (47.9990, 7.8421),
        "Union Berlin": (52.4575, 13.5308),
        "Kaiserslautern": (49.4430, 7.7706),
        "Karlsruhe": (49.0069, 8.4037),
        "Dresden": (51.0504, 13.7373),
        "Bielefeld": (52.0302, 8.5325),
        "Darmstadt": (49.8728, 8.6512),
        "Heidenheim": (48.6761, 10.1520),
        "Regensburg": (49.0134, 12.1016),
        "Paderborn": (51.7189, 8.7575),
        "Osnabrück": (52.2799, 8.0472),
        "Osnabruck": (52.2799, 8.0472),
        "Saarbrücken": (49.2330, 6.9980),
        "Saarbrucken": (49.2330, 6.9980),

        # ── ИТАЛИЯ ──
        "Milan": (45.4642, 9.1900),
        "Milano": (45.4642, 9.1900),
        "Rome": (41.9028, 12.4964),
        "Roma": (41.9028, 12.4964),
        "Turin": (45.0703, 7.6869),
        "Torino": (45.0703, 7.6869),
        "Naples": (40.8518, 14.2681),
        "Napoli": (40.8518, 14.2681),
        "Florence": (43.7696, 11.2558),
        "Firenze": (43.7696, 11.2558),
        "Bologna": (44.4949, 11.3426),
        "Genoa": (44.4056, 8.9463),
        "Verona": (45.4384, 10.9916),
        "Bergamo": (45.6983, 9.6773),
        "Udine": (46.0711, 13.2346),
        "Cagliari": (39.2238, 9.1217),
        "Palermo": (38.1157, 13.3615),
        "Bari": (41.1171, 16.8719),
        "Lecce": (40.3515, 18.1750),
        "Empoli": (43.7179, 10.9474),
        "Salerno": (40.6824, 14.7681),
        "Monza": (45.5845, 9.2744),
        "Como": (45.8081, 9.0852),
        "Parma": (44.8015, 10.3279),
        "Modena": (44.6471, 10.9252),
        "Venezia": (45.4408, 12.3155),
        "Cesena": (44.1391, 12.2437),
        "Stabia": (40.7006, 14.4850),

        # ── ФРАНЦИЯ ──
        "Paris": (48.8566, 2.3522),
        "Marseille": (43.2965, 5.3698),
        "Lyon": (45.7640, 4.8357),
        "Lille": (50.6292, 3.0573),
        "Bordeaux": (44.8378, -0.5792),
        "Toulouse": (43.6047, 1.4442),
        "Nice": (43.7102, 7.2620),
        "Nantes": (47.2184, -1.5536),
        "Strasbourg": (48.5734, 7.7521),
        "Montpellier": (43.6108, 3.8767),
        "Rennes": (48.1173, -1.6778),
        "Reims": (49.2583, 4.0317),
        "Lens": (50.4283, 2.8333),
        "Monaco": (43.7384, 7.4246),
        "Saint-Etienne": (45.4397, 4.3872),
        "Le Havre": (49.4944, 0.1079),
        "Metz": (49.1193, 6.1757),
        "Angers": (47.4784, -0.5632),
        "Brest": (48.3904, -4.4861),
        "Clermont": (45.7772, 3.0870),
        "Le Mans": (48.0061, 0.1996),
        "Dijon": (47.3220, 5.0415),
        "Lorient": (47.7484, -3.3702),
        "Auxerre": (47.7981, 3.5673),
        "Troyes": (48.2973, 4.0744),
        "Bastia": (42.7022, 9.4509),
        "Guingamp": (48.5627, -3.1513),
        "Caen": (49.1829, -0.3707),
        "Nancy": (48.6921, 6.1844),
        "Rodez": (44.3505, 2.5730),
        "Annecy": (45.8992, 6.1294),

        # ── НИДЕРЛАНДЫ ──
        "Amsterdam": (52.3676, 4.9041),
        "Rotterdam": (51.9244, 4.4777),
        "Eindhoven": (51.4416, 5.4697),
        "Utrecht": (52.0907, 5.1214),
        "Alkmaar": (52.6324, 4.7534),
        "Heerenveen": (52.9606, 5.9197),
        "Arnhem": (51.9851, 5.8987),
        "Nijmegen": (51.8426, 5.8540),
        "Enschede": (52.2215, 6.8937),
        "Groningen": (53.2194, 6.5665),
        "Tilburg": (51.5606, 5.0913),
        "Breda": (51.5719, 4.7683),
        "Zwolle": (52.5168, 6.0830),
        "Sittard": (50.9989, 5.8694),
        "Almelo": (52.3607, 6.6555),
        "Waalwijk": (51.6857, 5.0709),

        # ── ПОРТУГАЛИЯ ──
        "Lisbon": (38.7223, -9.1393),
        "Lisboa": (38.7223, -9.1393),
        "Porto": (41.1579, -8.6291),
        "Braga": (41.5454, -8.4265),
        "Guimaraes": (41.4425, -8.2918),
        "Guimarães": (41.4425, -8.2918),
        "Coimbra": (40.2033, -8.4103),
        "Setubal": (38.5243, -8.8882),
        "Setúbal": (38.5243, -8.8882),
        "Faro": (37.0193, -7.9304),
        "Funchal": (32.6669, -16.9241),

        # ── БЕЛЬГИЯ ──
        "Brussels": (50.8503, 4.3517),
        "Bruges": (51.2093, 3.2247),
        "Brugge": (51.2093, 3.2247),
        "Antwerp": (51.2194, 4.4025),
        "Antwerpen": (51.2194, 4.4025),
        "Gent": (51.0543, 3.7174),
        "Ghent": (51.0543, 3.7174),
        "Liege": (50.6326, 5.5797),
        "Liège": (50.6326, 5.5797),
        "Charleroi": (50.4114, 4.4446),
        "Anderlecht": (50.8361, 4.3086),

        # ── ТУРЦИЯ ──
        "Istanbul": (41.0082, 28.9784),
        "Ankara": (39.9334, 32.8597),
        "Izmir": (38.4237, 27.1428),
        "Bursa": (40.1885, 29.0610),
        "Antalya": (36.8969, 30.7133),
        "Trabzon": (41.0027, 39.7168),
        "Konya": (37.8746, 32.4932),
        "Adana": (37.0000, 35.3213),
        "Kayseri": (38.7346, 35.4674),
        "Gaziantep": (37.0662, 37.3833),

        # ── СКАНДИНАВИЯ ──
        "Copenhagen": (55.6761, 12.5683),
        "Kobenhavn": (55.6761, 12.5683),
        "Aarhus": (56.1629, 10.2039),
        "Odense": (55.4038, 10.4024),
        "Brondby": (55.6480, 12.4182),
        "Oslo": (59.9139, 10.7522),
        "Bergen": (60.3913, 5.3221),
        "Trondheim": (63.4305, 10.3951),
        "Stavanger": (58.9700, 5.7331),
        "Stockholm": (59.3293, 18.0686),
        "Gothenburg": (57.7089, 11.9746),
        "Malmo": (55.6050, 13.0038),
        "Helsinki": (60.1699, 24.9384),

        # ── ВОСТОЧНАЯ ЕВРОПА ──
        "Warsaw": (52.2297, 21.0122),
        "Krakow": (50.0647, 19.9450),
        "Gdansk": (54.3520, 18.6466),
        "Wroclaw": (51.1079, 17.0385),
        "Poznan": (52.4064, 16.9252),
        "Kyiv": (50.4501, 30.5234),
        "Lviv": (49.8397, 24.0297),
        "Kharkiv": (49.9935, 36.2304),
        "Odessa": (46.4825, 30.7233),
        "Moscow": (55.7558, 37.6173),
        "Saint Petersburg": (59.9311, 30.3609),
        "Kazan": (55.8304, 49.0661),
        "Zagreb": (45.8150, 15.9819),
        "Split": (43.5081, 16.4402),
        "Belgrade": (44.7866, 20.4489),
        "Prague": (50.0755, 14.4378),
        "Brno": (49.1951, 16.6068),
        "Vienna": (48.2082, 16.3738),
        "Salzburg": (47.8095, 13.0550),
        "Budapest": (47.4979, 19.0402),
        "Bucharest": (44.4268, 26.1025),
        "Sofia": (42.6977, 23.3219),
        "Athens": (37.9838, 23.7275),
        "Thessaloniki": (40.6401, 22.9444),

        # ── ШВЕЙЦАРИЯ / АВСТРИЯ ──
        "Zurich": (47.3769, 8.5417),
        "Geneva": (46.2044, 6.1432),
        "Basel": (47.5596, 7.5886),
        "Bern": (46.9480, 7.4474),
        "Lugano": (46.0037, 8.9511),
        "St. Gallen": (47.4245, 9.3767),

        # ── АМЕРИКА ──        "Rio de Janeiro": (-22.9068, -43.1729),
        "Sao Paulo": (-23.5505, -46.6333),
        "São Paulo": (-23.5505, -46.6333),
        "Belo Horizonte": (-19.9167, -43.9345),
        "Porto Alegre": (-30.0346, -51.2177),
        "Salvador": (-12.9777, -38.5016),
        "Brasilia": (-15.7942, -47.8825),
        "Buenos Aires": (-34.6037, -58.3816),
        "Rosario": (-32.9468, -60.6393),
        "Cordoba": (-31.4201, -64.1888),
        "Montevideo": (-34.9011, -56.1645),
        "Santiago": (-33.4489, -70.6693),
        "Bogota": (4.7110, -74.0721),
        "Lima": (-12.0464, -77.0428),
        "Quito": (-0.1807, -78.4678),
        "Mexico City": (19.4326, -99.1332),
        "Guadalajara": (20.6597, -103.3496),
        "Monterrey": (25.6866, -100.3161),
        "New York": (40.7128, -74.0060),
        "Los Angeles": (34.0522, -118.2437),
        "Chicago": (41.8781, -87.6298),
        "Miami": (25.7617, -80.1918),
        "Seattle": (47.6062, -122.3321),
        "Atlanta": (33.7490, -84.3880),
        "Houston": (29.7604, -95.3698),
        "Portland": (45.5152, -122.6784),
        "Toronto": (43.6532, -79.3832),
        "Vancouver": (49.2827, -123.1207),
        "Montreal": (45.5017, -73.5673),

        # ── АЗИЯ / АВСТРАЛИЯ ──
        "Tokyo": (35.6762, 139.6503),
        "Osaka": (34.6937, 135.5023),
        "Seoul": (37.5665, 126.9780),
        "Beijing": (39.9042, 116.4074),
        "Shanghai": (31.2304, 121.4737),
        "Guangzhou": (23.1291, 113.2644),
        "Riyadh": (24.7136, 46.6753),
        "Jeddah": (21.4858, 39.1925),
        "Dammam": (26.3927, 49.9777),
        "Doha": (25.2854, 51.5310),
        "Dubai": (25.2048, 55.2708),
        "Abu Dhabi": (24.4539, 54.3773),
        "Cairo": (30.0444, 31.2357),
        "Johannesburg": (-26.2041, 28.0473),
        "Cape Town": (-33.9249, 18.4241),
        "Casablanca": (33.5731, -7.5898),
        "Rabat": (34.0209, -6.8416),
        "Sydney": (-33.8688, 151.2093),
        "Melbourne": (-37.8136, 144.9631),
        "Brisbane": (-27.4698, 153.0251),
        "Perth": (-31.9505, 115.8605),
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
            'serie d', 'regionalliga', 'oberliga', 'landesliga', 'verbandsliga',
            'torneo federal', 'torneo argentino',
            'prim b', 'prim c', 'prim d',
            'lpf', 'primera nacional',
            'segunda federación', 'tercera federación',
            'amateur', 'npl', 'nsw', 'victoria', 'queensland',
            'south australia', 'k4', 'k5', 'k6', 'k7',
            'copa paulista', 'carioca', 'gaúcho', 'mineiro',
            'baiano', 'pernambucano', 'cearense', 'paranaense',
            'national 2', 'national 3', 'championnat national', 'cfa',
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
    def check_leagues_odds(cls):
        if not cls.FOOTBALL_API_KEY:
            print("❌ FOOTBALL_API_KEY не задан")
            return
        headers = {
            'x-apisports-key': cls.FOOTBALL_API_KEY,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        all_leagues = sorted(set(cls.LEAGUES))
        print(f"🔍 Проверяю {len(all_leagues)} лиг на наличие кэфов...")
        print(f"📅 Сезон: {cls.USE_SEASON}")
        print("=" * 70)
        with_odds, without_odds, errors = [], [], []
        for i, lid in enumerate(all_leagues, 1):
            name = cls.LEAGUE_NAMES.get(lid, f"ID:{lid}")
            try:
                r = requests.get(
                    f"{cls.FOOTBALL_API_URL}/odds",
                    headers=headers,
                    params={'league': lid, 'season': cls.USE_SEASON},
                    timeout=20,
                )
                if r.status_code == 429:
                    print(f"⚠️ Rate limit — пауза 60 сек")
                    time.sleep(60)
                    continue
                if r.status_code != 200:
                    errors.append((lid, name, f"HTTP {r.status_code}"))
                    print(f"❌ [{i}/{len(all_leagues)}] {name} — HTTP {r.status_code}")
                    continue
                data = r.json()
                results = data.get('results', 0)
                api_errors = data.get('errors', {})
                if api_errors:
                    err_text = str(api_errors)[:80]
                    errors.append((lid, name, err_text))
                    print(f"⚠️ [{i}/{len(all_leagues)}] {name} — {err_text}")
                elif results > 0:
                    with_odds.append((lid, name))
                    print(f"✅ [{i}/{len(all_leagues)}] {name} — {results} матчей")
                else:
                    without_odds.append((lid, name))
                    print(f"❌ [{i}/{len(all_leagues)}] {name} — 0 матчей")
            except Exception as e:
                errors.append((lid, name, str(e)))
                print(f"❌ [{i}/{len(all_leagues)}] {name} — {e}")
            time.sleep(0.15)
        print("=" * 70)
        print(f"\n📊 РЕЗУЛЬТАТ:")
        print(f"✅ С кэфами:  {len(with_odds)}")
        print(f"❌ Без кэфов: {len(without_odds)}")
        print(f"⚠️ Ошибки:    {len(errors)}")
        if with_odds:
            print("\n✅ ЛИГИ С КЭФАМИ:")
            for lid, name in with_odds:
                print(f"  {lid}: {name}")
        if without_odds:
            print("\n❌ ЛИГИ БЕЗ КЭФОВ (убрать из whitelist):")
            for lid, name in without_odds:
                print(f"  {lid}: {name}")
        try:
            out_dir = os.path.dirname(cls.DATABASE_URL) or '.'
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, "leagues_with_odds.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("# Лиги с кэфами\n")
                for lid, name in with_odds:
                    f.write(f"{lid}\t{name}\n")
                f.write("\n# Лиги без кэфов\n")
                for lid, name in without_odds:
                    f.write(f"{lid}\t{name}\n")
            print(f"\n💾 Сохранено в {out_path}")
        except Exception as e:
            print(f"⚠️ Не удалось сохранить файл: {e}")
        return with_odds, without_odds

    @classmethod
    def check_whitelist_odds(cls):
        if not cls.FOOTBALL_API_KEY:
            print("❌ FOOTBALL_API_KEY не задан")
            return
        headers = {
            'x-apisports-key': cls.FOOTBALL_API_KEY,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        print(f"🔍 Проверяю whitelist ({len(cls.WHITELIST_LEAGUES)} записей)")
        print(f"📅 Сезон: {cls.USE_SEASON}")
        print("=" * 70)
        all_found_leagues = {}
        for country in cls.LEAGUE_COUNTRIES:
            try:
                r = requests.get(
                    f"{cls.FOOTBALL_API_URL}/leagues",
                    headers=headers,
                    params={'country': country, 'season': cls.USE_SEASON},
                    timeout=20,
                )
                if r.status_code != 200:
                    continue
                for item in r.json().get('response', []):
                    lg = item.get('league', {})
                    lid, lname = lg.get('id'), lg.get('name')
                    if lid and lname:
                        all_found_leagues[lid] = lname
            except Exception as e:
                print(f"❌ {country}: {e}")
        print(f"📊 Найдено {len(all_found_leagues)} лиг через /leagues")
        matched = [
            (lid, lname) for lid, lname in all_found_leagues.items()
            if any(good in lname.lower() for good in cls.WHITELIST_LEAGUES)
        ]
        print(f"✅ Совпало с whitelist: {len(matched)}")
        print("=" * 70)
        with_odds, without_odds = [], []
        for i, (lid, lname) in enumerate(matched, 1):
            try:
                r = requests.get(
                    f"{cls.FOOTBALL_API_URL}/odds",
                    headers=headers,
                    params={'league': lid, 'season': cls.USE_SEASON},
                    timeout=20,
                )
                if r.status_code == 429:
                    time.sleep(60)
                    continue
                data = r.json()
                results = data.get('results', 0)
                if results > 0:
                    with_odds.append((lid, lname))
                    print(f"✅ [{i}/{len(matched)}] {lname} — {results} матчей")
                else:
                    without_odds.append((lid, lname))
                    print(f"❌ [{i}/{len(matched)}] {lname} — 0 матчей")
            except Exception as e:
                print(f"❌ [{i}/{len(matched)}] {lname} — {e}")
            time.sleep(0.15)
        print("=" * 70)
        print(f"✅ С кэфами:  {len(with_odds)}")
        print(f"❌ Без кэфов: {len(without_odds)}")
        if with_odds:
            print("\n✅ ЛИГИ С КЭФАМИ:")
            for lid, name in with_odds:
                print(f"  {lid}: {name}")
        if without_odds:
            print("\n❌ ЛИГИ БЕЗ КЭФОВ:")
            for lid, name in without_odds:
                print(f"  {lid}: {name}")
        return with_odds, without_odds

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
        print(f"🌍 Городов в CITY_COORDS: {len(cls.CITY_COORDS)}")
        print(f"🧠 PREDICTION_ENGINE: {cls.PREDICTION_ENGINE}")
        print(f"🤖 LLM: {'вкл' if cls.LLM_ENABLED else 'выкл'} ({cls.LLM_PROVIDER}) | модель: {cls.LLM_MODEL}")
        print(f"📅 Сезон: {cls.USE_SEASON}")
        print(f"🗄️ БД: {cls.DATABASE_URL}")
        print(f"🚫 Чёрный список лиг: {len(cls.BLACKLIST_LEAGUES)}")
        print(f"✅ Белый список лиг: {len(cls.WHITELIST_LEAGUES)}")
        print(f"🌍 Стран: {len(cls.LEAGUE_COUNTRIES)}")
        print(f"⚡ СКОРОСТЬ: STATS_ENABLED={cls.STATS_ENABLED} | H2H={cls.USE_H2H} | Predictions={cls.USE_PREDICTIONS}")
        print(f"🎯 X2: {'вкл' if cls.X2_ENABLED else 'выкл'} | EV>={cls.X2_MIN_EV}% | Prob>={cls.X2_MIN_PROB}%")
        print(f"🎯 ODDS API: {'вкл' if cls.ODDS_API_ENABLED else '❌ ОТКЛЮЧЁН (исчерпан лимит)'}")
        cls.init_db()
        print(f"📊 Лиг: {len(set(cls.LEAGUES))}")
        print(f"🏆 Кубков: {len(set(cls.CUP_LEAGUES))}")
        return True


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "check"
    if arg == "check":
        Config.check()
    elif arg == "leagues":
        Config.check_leagues_odds()
    elif arg == "whitelist":
        Config.check_whitelist_odds()
    else:
        print("Использование:")
        print("  python3 -m app.config check      — общая проверка")
        print("  python3 -m app.config leagues    — проверить кэфы по Config.LEAGUES")
        print("  python3 -m app.config whitelist  — проверить кэфы по WHITELIST")
