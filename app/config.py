"""Конфигурация бота"""
import os

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
    LIMIT_BET_TYPE_70 = 3
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
    '3. Лига': 'soccer_germany_liga3',
    '3. Liga': 'soccer_germany_liga3',

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

    # === НИДЕРЛАНДЫ ===
    'Эредивизи': 'soccer_netherlands_eredivisie',
    'Eredivisie': 'soccer_netherlands_eredivisie',
    'Эрсте Дивизи': 'soccer_netherlands_eredivisie',

    # === ПОРТУГАЛИЯ ===
    'Примейра Лига': 'soccer_portugal_primeira_liga',
    'Primeira Liga': 'soccer_portugal_primeira_liga',
    'Сегунда Лига': 'soccer_portugal_segunda_liga',

    # === БЕЛЬГИЯ ===
    'Про Лига': 'soccer_belgium_first_div',
    'Челленджер Про Лига': 'soccer_belgium_first_div',

    # === ТУРЦИЯ ===
    'Супер Лига': 'soccer_turkey_super_league',
    'Super Lig': 'soccer_turkey_super_league',

    # === ШОТЛАНДИЯ ===
    'Премьершип': 'soccer_spl',
    'Чемпионшип': 'soccer_spl',

    # === ГРЕЦИЯ ===
    'Супер Лига': 'soccer_greece_super_league',
    'Супер Лига 2': 'soccer_greece_super_league',

    # === ЧЕХИЯ ===
    'Первая Лига': 'soccer_czech_republic_1_liga',
    'Вторая Лига': 'soccer_czech_republic_1_liga',

    # === АВСТРИЯ ===
    'Бундеслига': 'soccer_austria_bundesliga',
    'Вторая Лига': 'soccer_austria_bundesliga',

    # === ШВЕЙЦАРИЯ ===
    'Супер Лига': 'soccer_switzerland_superleague',
    'Челлендж Лига': 'soccer_switzerland_superleague',

    # === ДАНИЯ ===
    'Суперлига': 'soccer_denmark_superliga',
    'Первая Дивизия': 'soccer_denmark_superliga',

    # === НОРВЕГИЯ ===
    'Элитсериен': 'soccer_norway_eliteserien',
    'Первая Дивизия': 'soccer_norway_eliteserien',

    # === ШВЕЦИЯ ===
    'Аллсвенскан': 'soccer_sweden_allsvenskan',
    'Суперэттан': 'soccer_sweden_allsvenskan',

    # === ПОЛЬША ===
    'Экстракласа': 'soccer_poland_ekstraklasa',
    'Первая Лига': 'soccer_poland_ekstraklasa',

    # === УКРАИНА ===
    'Премьер-Лига': 'soccer_ukraine_premier_league',
    'Первая Лига': 'soccer_ukraine_premier_league',

    # === РОССИЯ ===
    'РПЛ': 'soccer_russia_premier_league',
    'Первая Лига': 'soccer_russia_premier_league',

    # === ХОРВАТИЯ ===
    'HNL': 'soccer_croatia_hnl',
    'Вторая Лига': 'soccer_croatia_hnl',

    # === СЕРБИЯ ===
    'Супер Лига': 'soccer_serbia_super_liga',
    'Первая Лига': 'soccer_serbia_super_liga',

    # === БОЛГАРИЯ ===
    'Первая Лига': 'soccer_bulgaria_first_league',
    'Вторая Лига': 'soccer_bulgaria_first_league',

    # === РУМЫНИЯ ===
    'Лига 1': 'soccer_romania_liga1',
    'Лига 2': 'soccer_romania_liga1',

    # === СЛОВАКИЯ ===
    'Супер Лига': 'soccer_slovakia_super_liga',
    'Вторая Лига': 'soccer_slovakia_super_liga',

    # === СЛОВЕНИЯ ===
    'Первая Лига': 'soccer_slovenia_prva_liga',
    'Вторая Лига': 'soccer_slovenia_prva_liga',

    # === ВЕНГРИЯ ===
    'Немзети Байнокшаг': 'soccer_hungary_nb_i',
    'Вторая Лига': 'soccer_hungary_nb_i',

    # === ИРЛАНДИЯ ===
    'Премьер Дивизион': 'soccer_ireland_premier_division',
    'Первый Дивизион': 'soccer_ireland_premier_division',

    # === ФИНЛЯНДИЯ ===
    'Вейккауслиига': 'soccer_finland_veikkausliiga',
    'Юккёнен': 'soccer_finland_veikkausliiga',

    # === ИСЛАНДИЯ ===
    'Урвалсдейлд': 'soccer_iceland_urvalsdeild',
    'Первая Лига': 'soccer_iceland_urvalsdeild',

    # === ЕВРОПЕЙСКИЕ КУБКИ ===
    'Лига Чемпионов УЕФА': 'soccer_uefa_champs_league',
    'UEFA Champions League': 'soccer_uefa_champs_league',
    'Лига Европы УЕФА': 'soccer_uefa_europa_league',
    'UEFA Europa League': 'soccer_uefa_europa_league',
    'Лига Конференций УЕФА': 'soccer_uefa_europa_league',

    # === ЮЖНАЯ АМЕРИКА ===
    'Бразилия Серия А': 'soccer_brazil_campeonato',
    'Brasileirão': 'soccer_brazil_campeonato',
    'Аргентина Примера': 'soccer_argentina_primera_division',
    'Primera División': 'soccer_argentina_primera_division',
    'Уругвай Примера': 'soccer_uruguay_primera_division',
    'Колумбия Примера А': 'soccer_colombia_primera_a',
    'Чили Примера': 'soccer_chile_campeonato',
    'Эквадор Серия А': 'soccer_ecuador_serie_a',
    'Парагвай Примера': 'soccer_paraguay_primera_division',
    'Перу Лига 1': 'soccer_peru_liga_1',

    # === СЕВЕРНАЯ АМЕРИКА ===
    'MLS': 'soccer_usa_mls',
    'МЛС': 'soccer_usa_mls',
    'Leagues Cup': 'soccer_concacaf_leagues_cup',
    'Копа Либертадорес': 'soccer_conmebol_copa_libertadores',
    'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
    'Копа Судамерикана': 'soccer_conmebol_copa_sudamericana',
    'Copa Sudamericana': 'soccer_conmebol_copa_sudamericana',

    # === АЗИЯ ===
    'Саудовская Аравия Про Лига': 'soccer_saudi_arabia_pro_league',
    'Saudi Pro League': 'soccer_saudi_arabia_pro_league',
    'Япония J1 Лига': 'soccer_japan_j_league',
    'J1 League': 'soccer_japan_j_league',
    'Южная Корея K Лига 1': 'soccer_korea_kleague1',
    'K League 1': 'soccer_korea_kleague1',
    'Австралия А-Лига': 'soccer_australia_a_league',
    'Китай Супер Лига': 'soccer_china_super_league',
    'Иран Про Лига': 'soccer_iran_pro_league',
    'ОАЭ Про Лига': 'soccer_uae_pro_league',
    'Катар Звездная Лига': 'soccer_qatar_stars_league',
    'АФК Чемпионская Лига': 'soccer_afc_champions_league',

    # === НОВЫЕ ЛИГИ ===
    'Боливия Nacional B': 'soccer_bolivia_nacional_b',
    'Ботсвана Premier League': 'soccer_botswana_premier_league',
    'Гана Division One': 'soccer_ghana_division_one',
    'Кения FKF Premier': 'soccer_kenya_fkf_premier_league',
    'Замбия Super League': 'soccer_zambia_super_league',
    'CAF Super Cup': 'soccer_caf_super_cup',

    # === ДОПОЛНИТЕЛЬНЫЕ ЛИГИ ===
    'Косово Супер Лига': 'soccer_kosovo_super_league',
    'Косово Первая Лига': 'soccer_kosovo_super_league',
    'Латвия Высшая Лига': 'soccer_latvia_virsliga',
    'Латвия Первая Лига': 'soccer_latvia_virsliga',
    'Литва А Лига': 'soccer_lithuania_a_lyga',
    'Литва Первая Лига': 'soccer_lithuania_a_lyga',
    'Люксембург Национальная Лига': 'soccer_luxembourg_national_division',
    'Люксембург Первая Лига': 'soccer_luxembourg_national_division',
    'Северная Ирландия Премьершип': 'soccer_northern_ireland_premiership',
    'Северная Ирландия Чемпионшип': 'soccer_northern_ireland_premiership',
    'Мальта Премьер Лига': 'soccer_malta_premier_league',
    'Мальта Первая Лига': 'soccer_malta_premier_league',
    'Молдова Супер Лига': 'soccer_moldova_super_liga',
    'Молдова Первая Лига': 'soccer_moldova_super_liga',
    'Черногория Первая Лига': 'soccer_montenegro_first_league',
    'Черногория Вторая Лига': 'soccer_montenegro_first_league',
    'Албания Супер Лига': 'soccer_albania_super_league',
    'Албания Первая Лига': 'soccer_albania_super_league',
    'Армения Премьер Лига': 'soccer_armenia_premier_league',
    'Армения Первая Лига': 'soccer_armenia_premier_league',
    'Азербайджан Премьер Лига': 'soccer_azerbaijan_premier_league',
    'Азербайджан Первая Лига': 'soccer_azerbaijan_premier_league',
    'Беларусь Высшая Лига': 'soccer_belarus_premier_league',
    'Беларусь Первая Лига': 'soccer_belarus_premier_league',
    'Босния Премьер Лига': 'soccer_bosnia_premier_league',
    'Босния Первая Лига': 'soccer_bosnia_premier_league',
    'Эстония Мейстрилига': 'soccer_estonia_meistriliiga',
    'Эстония Эсилига': 'soccer_estonia_meistriliiga',
    'Грузия Эровнули Лига': 'soccer_georgia_erovnuli_liga',
    'Грузия Первая Лига': 'soccer_georgia_erovnuli_liga',
    'Казахстан Премьер Лига': 'soccer_kazakhstan_premier_league',
    'Казахстан Первая Лига': 'soccer_kazakhstan_premier_league',
}
    
    # ============================================================
    # ЛИГИ
    # ============================================================
    
    LEAGUES = [
        # === АНГЛИЯ ===
        39, 40,
        # === ИСПАНИЯ ===
        140, 141,
        # === ГЕРМАНИЯ ===
        78, 79,
        # === ИТАЛИЯ ===
        135, 136,
        # === ФРАНЦИЯ ===
        61, 62,
        # === НИДЕРЛ260АНДЫ ===
        88, 89,
        # === ПОР ТУГАЛИЯ ===
        94, 95,
        # === БЕЛЬГИЯ ===
        144, 145,
        # === ТУРЦИЯ ===
        203, 204,
        # === ШОТЛАНДИЯ ===
        179, 180,
        # === ГРЕЦИЯ ===
        197, 198,
        # === ЧЕХИЯ ===
        165, 166,
        # === АВСТРИЯ ===
        187, 188,
        # === ШВЕЙЦАРИЯ ===
        206, 207,
        # === ДАНИЯ ===
        119, 120,
        # === НОРВЕГИЯ ===
        164, 165,
        # === ШВЕЦИЯ ===
        188, 189,
        # === ПОЛЬША ===
        106, 107,
        # === УКРАИНА ===
        95, 96,
        # === РОССИЯ ===
        179, 180,
        # === ХОРВАТИЯ ===
        166, 167,
        # === СЕРБИЯ ===
        250, 251,
        # === БОЛГАРИЯ ===
        253, 254,
        # === РУМЫНИЯ ===
        256, 257,
        # === СЛОВАКИЯ ===
        258, 259,
        # === СЛОВЕНИЯ ===
        ,
        # === ВЕНГРИЯ ===
        171, 172,
        # === ИРЛАНДИЯ ===
        179, 180,
        # === ФИНЛЯНДИЯ ===
        113, 114,
        # === ИСЛАНДИЯ ===
        124, 125,
        # === ЕВРОПЕЙСКИЕ КУБКИ ===
        2, 3, 848,
        # === ЮЖНАЯ АМЕРИКА ===
        71, 128, 144, 148, 158, 168, 178, 180,
        # === АЗИЯ ===
        307, 150, 154, 183, 169, 209, 214, 216, 197,
        # === НОВЫЕ ЛИГИ ===
        710, 412, 1150, 1196, 276, 105, 1241, 1240, 400, 533,
        # === ДОПОЛНИТЕЛЬНЫЕ ЛИГИ ===
        113, 114, 124, 125, 126, 127, 129, 130, 131, 132, 133, 134,
        135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146,
        147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158,
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
        89: "Эрсте Дивизи",
        94: "Примейра Лига",
        95: "Сегунда Лига",
        144: "Про Лига",
        145: "Челленджер Про Лига",
        203: "Супер Лига",
        204: "Первая Лига",
        179: "Премьершип",
        180: "Чемпионшип",
        197: "Супер Лига",
        198: "Супер Лига 2",
        165: "Первая Лига",
        166: "Вторая Лига",
        187: "Бундеслига",
        188: "Вторая Лига",
        206: "Супер Лига",
        207: "Челлендж Лига",
        119: "Суперлига",
        120: "Первая Дивизия",
        164: "Элитсериен",
        165: "Первая Дивизия",
        188: "Аллсвенскан",
        189: "Суперэттан",
        106: "Экстракласа",
        107: "Первая Лига",
        95: "Премьер-Лига",
        96: "Первая Лига",
        166: "HNL",
        167: "Вторая Лига",
        250: "Супер Лига",
        251: "Первая Лига",
        253: "Первая Лига",
        254: "Вторая Лига",
        256: "Лига 1",
        257: "Лига 2",
        258: "Супер Лига",
        259: "Вторая Лига",
        260: "Первая Лига",
        261: "Вторая Лига",
        171: "Немзети Байнокшаг",
        172: "Вторая Лига",
        2: "Лига Чемпионов УЕФА",
        3: "Лига Европы УЕФА",
        848: "Лига Конференций УЕФА",
        71: "Бразилия Серия А",
        128: "Аргентина Примера",
        144: "Уругвай Примера",
        148: "Колумбия Примера А",
        158: "Чили Примера",
        168: "Эквадор Серия А",
        178: "Парагвай Примера",
        180: "Перу Лига 1",
        307: "Саудовская Аравия Про Лига",
        150: "Япония J1 Лига",
        154: "Южная Корея K Лига 1",
        183: "Австралия А-Лига",
        169: "Китай Супер Лига",
        209: "Иран Про Лига",
        214: "ОАЭ Про Лига",
        216: "Катар Звездная Лига",
        197: "АФК Чемпионская Лига",
        710: "Боливия Nacional B",
        412: "Ботсвана Premier League",
        1150: "Бразилия Gaúcho 3",
        1196: "Гана Division One",
        276: "Кения FKF Premier",
        105: "Норвегия NM Cupen",
        1241: "Сербия U19",
        1240: "Турция U19",
        400: "Замбия Super League",
        533: "CAF Super Cup",
        113: "Финляндия Вейккауслиига",
        114: "Финляндия Юккёнен",
        124: "Исландия Урвалсдейлд",
        125: "Исландия Первая Лига",
        126: "Косово Супер Лига",
        127: "Косово Первая Лига",
        129: "Латвия Высшая Лига",
        130: "Латвия Первая Лига",
        131: "Литва А Лига",
        132: "Литва Первая Лига",
        133: "Люксембург Национальная Лига",
        134: "Люксембург Первая Лига",
        135: "Северная Ирландия Премьершип",
        136: "Северная Ирландия Чемпионшип",
        137: "Мальта Премьер Лига",
        138: "Мальта Первая Лига",
        139: "Молдова Супер Лига",
        140: "Молдова Первая Лига",
        141: "Черногория Первая Лига",
        142: "Черногория Вторая Лига",
        143: "Албания Супер Лига",
        144: "Албания Первая Лига",
        145: "Армения Премьер Лига",
        146: "Армения Первая Лига",
        147: "Азербайджан Премьер Лига",
        148: "Азербайджан Первая Лига",
        149: "Беларусь Высшая Лига",
        150: "Беларусь Первая Лига",
        151: "Босния Премьер Лига",
        152: "Босния Первая Лига",
        153: "Эстония Мейстрилига",
        154: "Эстония Эсилига",
        155: "Грузия Эровнули Лига",
        156: "Грузия Первая Лига",
        157: "Казахстан Премьер Лига",
        158: "Казахстан Первая Лига",
    }
    
    # ============================================================
    # КУБКИ
    # ============================================================
    
    CUP_LEAGUES = [
        45, 46, 143, 81, 137, 66, 67, 90, 96, 146, 205, 182,
        199, 167, 189, 208, 121, 166, 190, 108, 97, 181, 168,
        252, 255, 258, 260, 262, 173, 181, 13, 14, 73, 130,
        146, 150, 160, 170, 180, 182, 309, 152, 156, 185, 171,
        211, 216, 218, 533,
    ]
    
    CUP_NAMES = {
        45: "Кубок Англии",
        46: "Кубок Лиги",
        143: "Кубок Испании",
        81: "Кубок Германии",
        137: "Кубок Италии",
        66: "Кубок Франции",
        67: "Кубок Лиги",
        90: "Кубок Нидерландов",
        96: "Кубок Португалии",
        146: "Кубок Бельгии",
        205: "Кубок Турции",
        182: "Кубок Шотландии",
        199: "Кубок Греции",
        167: "Кубок Чехии",
        189: "Кубок Австрии",
        208: "Кубок Швейцарии",
        121: "Кубок Дании",
        166: "Кубок Норвегии",
        190: "Кубок Швеции",
        108: "Кубок Польши",
        97: "Кубок Украины",
        181: "Кубок России",
        168: "Кубок Хорватии",
        252: "Кубок Сербии",
        255: "Кубок Болгарии",
        258: "Кубок Румынии",
        260: "Кубок Словакии",
        262: "Кубок Словении",
        173: "Кубок Венгрии",
        13: "Копа Либертадорес",
        14: "Копа Судамерикана",
        73: "Кубок Бразилии",
        130: "Кубок Аргентины",
        146: "Кубок Уругвая",
        150: "Кубок Колумбии",
        160: "Кубок Чили",
        170: "Кубок Эквадора",
        180: "Кубок Парагвая",
        182: "Кубок Перу",
        309: "Кубок Короля",
        152: "Кубок Императора",
        156: "Кубок Кореи",
        185: "Кубок Австралии",
        171: "Кубок Китая",
        211: "Кубок Ирана",
        216: "Президентский Кубок",
        218: "Кубок Эмира",
    }

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

Config.check()
