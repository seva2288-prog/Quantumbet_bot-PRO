"""Конфигурация бота"""
import os
import sqlite3
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


class Config:
    # === ТЕЛЕГРАМ ===
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
    CHANNEL_ID = os.getenv("CHANNEL_ID", "")

    # === API ===
    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")
    FOOTBALL_API_URL = os.getenv("FOOTBALL_API_URL", "https://v3.football.api-sports.io")

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
    WEATHER_API_URL = os.getenv("WEATHER_API_URL", "https://api.openweathermap.org/data/2.5")
    WEATHER_ENABLED = bool(WEATHER_API_KEY)

    # === ODDS API ===
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
    ODDS_API_URL = os.getenv("ODDS_API_URL", "https://api.the-odds-api.com/v4")
    BACKUP_ODDS_KEYS = [k.strip() for k in os.getenv("BACKUP_ODDS_KEYS", "").split(",") if k.strip()]

    # === LLM ===
    # === LLM ===
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-7a3401ec6b5f4f9fa33aede55a00f427")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-reasoner")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", LLM_API_KEY)   # ← НОВАЯ
    LLM_ENABLED = bool(LLM_API_KEY)

    # === ИНФРАСТРУКТУРА ===
    DATABASE_URL = os.getenv("DATABASE_URL", "bot.db")
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
    USE_SEASON = int(os.getenv("USE_SEASON", str(datetime.now().year)))
    CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))

    # === PREDICTION ENGINE ===
    PREDICTION_ENGINE = os.getenv("PREDICTION_ENGINE", "heuristic")
    MIN_ODDS = 1.50
    MAX_ODDS = 3.50
    MIN_CONFIDENCE = 0.60

    # === СТАВКИ ===
    MAX_BETS_PER_RUN = 30

    # === 70%+ ===
    XG_MIN_70 = 1.8
    XG_MAX_70 = 3.0
    EV_MIN_70 = 15
    PROB_MIN_70 = 55
    POSITION_MAX_70 = 15
    FORM_REQUIRED_70 = ['excellent', 'good']
    SKIP_MID_TABLE_70 = True
    LIMIT_BET_TYPE_70 = 15
    LIMIT_LEAGUE_70 = 2
    MIN_ODD_70 = 1.65

    # === ТМ 2.5 (мертвые, но совместимые с bot_settings.json) ===
    MAX_TM25_BETS = 0
    MIN_TM25_EV = 99
    MIN_TM25_PROB = 99
    TM25_XG_MIN = 0.99
    TM25_XG_MAX = 0.99
    PREMIUM_MIN_EV = 99
    PREMIUM_MIN_PROB = 99
    PREMIUM_XG_MIN = 0.99
    PREMIUM_XG_MAX = 0.99
    STANDARD_MIN_EV = 99
    STANDARD_MIN_PROB = 99
    STANDARD_XG_MIN = 0.99
    STANDARD_XG_MAX = 0.99
    TM25_TOP_LEAGUE_EV = 35

    TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

    # ============================================================
    # МАППИНГ ЛИГ ДЛЯ ODDS API
    # ============================================================
    ODDS_SPORT_MAP = {
        'АПЛ': 'soccer_epl', 'Premier League': 'soccer_epl',
        'Чемпионшип': 'soccer_efl_champ', 'Championship': 'soccer_efl_champ',
        'Лига 1': 'soccer_england_league1', 'League 1': 'soccer_england_league1',
        'Лига 2': 'soccer_england_league2', 'League 2': 'soccer_england_league2',
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
        'Супер Лига': 'soccer_turkey_super_league', 'Super Lig': 'soccer_turkey_super_league',
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
        'Бразилия Серия А': 'soccer_brazil_campeonato', 'Brasileirão': 'soccer_brazil_campeonato',
        'Аргентина Примера': 'soccer_argentina_primera_division',
        'MLS': 'soccer_usa_mls', 'МЛС': 'soccer_usa_mls',
        'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
        'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
        'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
        'Япония J1 Лига': 'soccer_japan_j_league', 'J1 League': 'soccer_japan_j_league',
        'Южная Корея K Лига 1': 'soccer_korea_kleague1', 'K League 1': 'soccer_korea_kleague1',
        'Австралия А-Лига': 'soccer_australia_a_league',
        'Китай Супер Лига': 'soccer_china_super_league',
    }

    # ============================================================
    # СТРАНЫ ДЛЯ АВТОМАТИЧЕСКОГО ПОСТРОЕНИЯ СПИСКА ЛИГ
    # ============================================================
    LEAGUE_COUNTRIES = [
        'England', 'Spain', 'Germany', 'Italy', 'France',
        'Netherlands', 'Portugal', 'Belgium', 'Turkey',
        'Scotland', 'Denmark', 'Norway', 'Sweden', 'Poland',
        'Ukraine', 'Russia', 'Croatia', 'Austria', 'Switzerland',
        'Slovenia', 'Serbia', 'Bulgaria', 'Romania', 'Slovakia',
        'Hungary', 'Greece', 'Czech-Republic',
        'Brazil', 'Argentina', 'Uruguay', 'Colombia', 'Chile',
        'Ecuador', 'Paraguay', 'Peru', 'Venezuela', 'Mexico',
        'USA',
        'Saudi-Arabia', 'Japan', 'South-Korea', 'Australia',
        'China', 'UAE', 'Qatar', 'Iraq',
        'South-Africa', 'Morocco', 'Egypt', 'Algeria', 'Tunisia',
        'Nigeria', 'Ghana',
    ]

    # ============================================================
    # ЛИГИ И НАЗВАНИЯ (резерв; заменяются из API)
    # ============================================================
    LEAGUES = [
        39, 40, 41, 140, 141, 142, 78, 79, 80, 135, 136, 137,
        61, 62, 63, 88, 89, 94, 203, 204, 197, 198, 144, 145,
        119, 120, 164, 165, 106, 107, 95, 96, 187, 206, 207,
        166, 167, 260, 261, 250, 256, 258, 171, 179, 180, 181,
        182, 2, 3, 848, 71, 128, 148, 158, 168, 178, 253, 307,
        150, 151, 154, 155, 183, 169, 276, 278, 279,
    ]

    CUP_LEAGUES = [45, 46, 143, 81, 66, 13, 14, 15]

    LEAGUE_NAMES = {
        39: "Premier League", 40: "Championship", 41: "League One",
        140: "La Liga", 141: "La Liga 2", 142: "Primera Federación",
        78: "Bundesliga", 79: "2. Bundesliga", 80: "3. Liga",
        135: "Serie A", 136: "Serie B", 137: "Serie C",
        61: "Ligue 1", 62: "Ligue 2", 63: "National",
        88: "Eredivisie", 89: "Eerste Divisie", 94: "Primeira Liga",
        203: "Süper Lig", 204: "TFF 1. Lig",
        197: "Super League", 198: "Super League 2",
        144: "Pro League", 145: "Challenger Pro League",
        119: "Superliga", 120: "1. Division",
        164: "Eliteserien", 165: "OBOS-ligaen",
        106: "Ekstraklasa", 107: "I Liga",
        95: "Premier League", 96: "Persha Liga",
        187: "Bundesliga", 206: "Super League", 207: "Challenge League",
        166: "HNL", 167: "2. HNL",
        260: "Prva Liga", 261: "2. Liga",
        250: "Super Liga", 256: "Liga 1", 258: "Super Liga", 171: "NB I",
        179: "РПЛ", 180: "Первая Лига", 181: "Вторая Лига А", 182: "Вторая Лига Б",
        2: "Champions League", 3: "Europa League", 848: "Conference League",
        71: "Brasileirão", 128: "Argentina Primera", 148: "Uruguay Primera",
        158: "Colombia Primera A", 168: "Chile Primera", 178: "Ecuador Serie A",
        253: "MLS",
        307: "Saudi Pro League", 150: "J1 League", 151: "J2 League",
        154: "K League 1", 155: "K League 2", 183: "A-League",
        169: "Chinese Super League",
        276: "South Africa Premier", 278: "Botola Pro", 279: "Egyptian Premier",
    }

    # ============================================================
    # КООРДИНАТЫ ГОРОДОВ ДЛЯ ПОГОДЫ
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
    # API-МЕТОДЫ
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

        # Стоп-слова: женские, юношеские, региональные, низшие дивизионы
        EXCLUDE_WORDS = [
            'women', 'womens', 'u19', 'u20', 'u21', 'u23', 'u18', 'u17',
            'youth', 'reserve', 'academy', 'amateur',
            'regionalliga', 'oberliga', 'landesliga', 'verbandsliga',
            'k4', 'k5', 'k6', 'k7',
            'npl', 'nsw', 'victoria', 'queensland', 'south australia',
            'primera federación', 'segunda federación', 'tercera federación',
            'serie d', 'serie c',
            'división profesional', 'liga premier', 'liga de expansión',
            'besta deild karla', '1. deild karla', '2. deild karla',
            'ekstraklasa ii', 'i liga ii', 'ii liga', 'iii liga',
            'lpf', 'prim b', 'prim c', 'prim d',
            'national league', 'national 2', 'national 3',
            'championnat national', 'cfa',
            'allsvenskan norra', 'allsvenskan södra',
            'division 2', 'division 3',
            'ykkösliiga', 'kakkonen',
            'superettan norra', 'superettan södra',
            '2. deild', '3. deild', '4. deild',
            'treća hnl', 'druga hnl',
            'virsliga women',
        ]

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
                    if lg.get('type') == 'Cup':
                        continue
                    lid, lname = lg.get('id'), lg.get('name')
                    if not lid or not lname:
                        continue

                    lname_lower = lname.lower()
                    if any(w in lname_lower for w in EXCLUDE_WORDS):
                        continue

                    leagues.append(lid)
                    names[lid] = lname

                print(f"✅ {country}: OK")
            except Exception as e:
                print(f"❌ {country}: {e}")

        if leagues:
            cls.LEAGUES = sorted(set(leagues))
            cls.LEAGUE_NAMES = names
            print(f"🔄 Из API: {len(cls.LEAGUES)} лиг")
            return True
        print("⚠️ API пусто — резервный список.")
        return False

    @classmethod
    def fetch_league_ids(cls):
        cls.build_leagues_from_api()
        return cls.LEAGUE_NAMES

    @classmethod
    def init_db(cls):
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
        if not cls.ODDS_API_KEY: missing.append("ODDS_API_KEY")

        if missing:
            print(f"⚠️ Отсутствуют: {', '.join(missing)}")
        else:
            print("✅ Все ключи загружены!")

        print(f"🌦️ Погода: {'вкл' if cls.WEATHER_ENABLED else 'выкл'} | городов: {len(cls.CITY_COORDS)}")
        print(f"🧠 PREDICTION_ENGINE: {cls.PREDICTION_ENGINE}")
        print(f"🤖 LLM: {'вкл' if cls.LLM_ENABLED else 'выкл'} ({cls.LLM_PROVIDER})")
        print(f"🔑 Резервных Odds-ключей: {len(cls.BACKUP_ODDS_KEYS)}")
        print(f"📢 CHANNEL_ID: {'задан' if cls.CHANNEL_ID else 'не задан'}")
        print(f"📅 Сезон: {cls.USE_SEASON}")
        print(f"🗄️ БД: {cls.DATABASE_URL}")

        cls.init_db()
        cls.build_leagues_from_api()

        print(f"📊 Лиг: {len(set(cls.LEAGUES))}")
        print(f"🏆 Кубков: {len(set(cls.CUP_LEAGUES))}")
        return True


if __name__ == "__main__":
    Config.check()
