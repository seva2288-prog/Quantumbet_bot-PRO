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
    
    MAX_BETS_PER_RUN = 30
    
    # ============================================================
    # НАСТРОЙКИ 70%+ (ОСНОВНОЙ ПОИСК)
    # ============================================================
    
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
    # МАППИНГ ЛИГ ДЛЯ ODDS API
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
    # СТРАНЫ ДЛЯ АВТОМАТИЧЕСКОГО ПОСТРОЕНИЯ СПИСКА ЛИГ
    # (API-Football возвращает лиги по стране; список ниже —
    #  какие страны тянем. ID строятся автоматически.)
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
    # ЛИГИ И НАЗВАНИЯ (ЗАПОЛНЯЮТСЯ АВТОМАТИЧЕСКИ)
    # Значения ниже — резервные, используются, если API недоступно.
    # ============================================================

    LEAGUES = [
        39, 40, 41,            # Англия
        140, 141, 142,         # Испания
        78, 79, 80,            # Германия
        135, 136, 137,         # Италия
        61, 62, 63,            # Франция
        88, 89,                # Нидерланды
        94,                    # Португалия
        203, 204,              # Турция
        197, 198,              # Греция
        144, 145,              # Бельгия
        119, 120,              # Дания
        164, 165,              # Норвегия
        106, 107,              # Польша
        95, 96,                # Украина
        187,                   # Австрия
        206, 207,              # Швейцария
        166, 167,              # Хорватия
        260, 261,              # Словения
        250,                   # Сербия
        256,                   # Румыния
        258,                   # Словакия
        171,                   # Венгрия
        179, 180, 181, 182,    # Россия
        2, 3, 848,             # Еврокубки
        71, 128, 148, 158, 168, 178,  # Южная Америка
        253,                   # MLS
        307, 150, 151, 154, 155, 183, 169,  # Азия
        276, 278, 279,         # Африка
    ]

    CUP_LEAGUES = [
        45,    # FA Cup
        46,    # EFL Cup
        143,   # Copa del Rey
        81,    # DFB-Pokal
        66,    # Coupe de France
        13,    # Copa Libertadores
        14,    # Copa Sudamericana
        15,    # Recopa Sudamericana
    ]

    LEAGUE_NAMES = {
        39: "Premier League", 40: "Championship", 41: "League One",
        140: "La Liga", 141: "La Liga 2", 142: "Primera Federación",
        78: "Bundesliga", 79: "2. Bundesliga", 80: "3. Liga",
        135: "Serie A", 136: "Serie B", 137: "Serie C",
        61: "Ligue 1", 62: "Ligue 2", 63: "National",
        88: "Eredivisie", 89: "Eerste Divisie",
        94: "Primeira Liga",
        203: "Süper Lig", 204: "TFF 1. Lig",
        197: "Super League", 198: "Super League 2",
        144: "Pro League", 145: "Challenger Pro League",
        119: "Superliga", 120: "1. Division",
        164: "Eliteserien", 165: "OBOS-ligaen",
        106: "Ekstraklasa", 107: "I Liga",
        95: "Premier League", 96: "Persha Liga",
        187: "Bundesliga",
        206: "Super League", 207: "Challenge League",
        166: "HNL", 167: "2. HNL",
        260: "Prva Liga", 261: "2. Liga",
        250: "Super Liga",
        256: "Liga 1",
        258: "Super Liga",
        171: "NB I",
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
    # АВТОМАТИЧЕСКОЕ ПОСТРОЕНИЕ СПИСКА ЛИГ ИЗ API
    # ============================================================

    @classmethod
    def build_leagues_from_api(cls, season=None):
        """
        Подтягивает актуальные ID и названия лиг из API-Football
        по списку стран LEAGUE_COUNTRIES.

        Заменяет cls.LEAGUES и cls.LEAGUE_NAMES на актуальные.
        Если API недоступно — оставляет резервные значения.
        """
        if not cls.FOOTBALL_API_KEY:
            print("⚠️ Нет FOOTBALL_API_KEY — оставляю резервный список лиг.")
            return False

        headers = {
            'x-apisports-key': cls.FOOTBALL_API_KEY,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }

        leagues = []
        names = {}

        for country in cls.LEAGUE_COUNTRIES:
            try:
                params = {'country': country}
                if season:
                    params['season'] = season

                r = requests.get(
                    f"{cls.FOOTBALL_API_URL}/leagues",
                    headers=headers,
                    params=params,
                    timeout=20
                )

                if r.status_code != 200:
                    print(f"⚠️ {country}: HTTP {r.status_code}")
                    continue

                data = r.json().get('response', [])
                for item in data:
                    lid = item.get('league', {}).get('id')
                    lname = item.get('league', {}).get('name')
                    ltype = item.get('league', {}).get('type')  # 'League' или 'Cup'

                    if not lid or not lname:
                        continue

                    if ltype == 'Cup':
                        # Кубки складываем отдельно, не в основной список
                        continue

                    leagues.append(lid)
                    names[lid] = lname

                print(f"✅ {country}: {len(data)} записей")

            except Exception as e:
                print(f"❌ {country}: {e}")

        if leagues:
            cls.LEAGUES = sorted(set(leagues))
            cls.LEAGUE_NAMES = names
            print(f"🔄 Обновлено из API: {len(cls.LEAGUES)} лиг")
            return True
        else:
            print("⚠️ API вернуло пусто — оставляю резервный список.")
            return False

    # ============================================================
    # СОВМЕСТИМОСТЬ: старый метод fetch_league_ids()
    # ============================================================

    @classmethod
    def fetch_league_ids(cls):
        """Обратная совместимость — теперь вызывает build_leagues_from_api()."""
        cls.build_leagues_from_api()
        return cls.LEAGUE_NAMES

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

        # Автоматически тянем актуальные лиги из API
        cls.build_leagues_from_api()

        unique_leagues = len(set(cls.LEAGUES))
        unique_cups = len(set(cls.CUP_LEAGUES))
        all_competitions = len(set(cls.LEAGUES) | set(cls.CUP_LEAGUES))

        missing_names = set(cls.LEAGUES) - set(cls.LEAGUE_NAMES.keys())
        extra_names = set(cls.LEAGUE_NAMES.keys()) - set(cls.LEAGUES)

        print(f"📊 Лиг (уникальных): {unique_leagues}")
        print(f"🏆 Кубков (уникальных): {unique_cups}")
        print(f"📋 Всего соревнований: {all_competitions}")
        print(f"🎯 Odds API маппинг: {len(cls.ODDS_SPORT_MAP)} лиг")

        if missing_names:
            print(f"⚠️ Нет названий для ID: {sorted(missing_names)}")
        if extra_names:
            print(f"⚠️ Лишние названия (нет в LEAGUES): {len(extra_names)} шт. (не критично)")

        return True

# ============================================================
# АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПРИ ЗАПУСКЕ
# ============================================================

Config.check()
