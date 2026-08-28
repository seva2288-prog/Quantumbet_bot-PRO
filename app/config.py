import os
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict

# Загружаем .env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


class Config:
    """Конфигурация бота"""
    
    # === ТЕЛЕГРАМ ===
    TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN', '')
    ADMIN_CHAT_ID: str = os.getenv('ADMIN_CHAT_ID', '')
    
    # === API ===
    FOOTBALL_API_KEY: str = os.getenv('FOOTBALL_API_KEY', '')
    FOOTBALL_API_URL: str = os.getenv('FOOTBALL_API_URL', 'https://v3.football.api-sports.io')
    WEATHER_API_KEY: str = os.getenv('WEATHER_API_KEY', '')
    WEATHER_API_URL: str = os.getenv('WEATHER_API_URL', 'https://api.openweathermap.org/data/2.5')
    
    # === БЕЗОПАСНОСТЬ ===
    ENCRYPTION_KEY: bytes = os.getenv('ENCRYPTION_KEY', 'default-key').encode()
    SESSION_SECRET: str = os.getenv('SESSION_SECRET', 'default-secret')
    
    # === ПУТИ ===
    DATA_DIR: str = os.getenv('DATA_DIR', 'data')
    LOGS_DIR: str = os.getenv('LOGS_DIR', 'logs')
    
    # === НАСТРОЙКИ ===
    MAX_BETS_PER_RUN: int = int(os.getenv('MAX_BETS_PER_RUN', '5'))
    TIMEZONE_OFFSET: int = int(os.getenv('TIMEZONE_OFFSET', '3'))
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')
    
    # === ЛИГИ ===
    LEAGUES: List[int] = [39, 140, 78, 135, 61, 94, 144, 87, 2, 3]
    
    LEAGUE_NAMES: Dict[int, str] = {
        39: "Премьер-Лига (Англия)",
        140: "Ла Лига (Испания)",
        78: "Бундеслига (Германия)",
        135: "Серия А (Италия)",
        61: "Лига 1 (Франция)",
        94: "Премьер-Лига (Португалия)",
        144: "Чемпионшип (Англия)",
        87: "Эредивизи (Нидерланды)",
        2: "Лига Чемпионов УЕФА",
        3: "Лига Европы УЕФА",
    }
    
    @classmethod
    def check(cls) -> bool:
        """Проверка обязательных переменных"""
        required = ['TELEGRAM_TOKEN', 'ADMIN_CHAT_ID', 'FOOTBALL_API_KEY']
        missing = [r for r in required if not getattr(cls, r)]
        
        if missing:
            raise ValueError(f"❌ Отсутствуют: {', '.join(missing)}")
        
        # Создаём папки
        Path(cls.DATA_DIR).mkdir(exist_ok=True)
        Path(cls.LOGS_DIR).mkdir(exist_ok=True)
        
        print(f"✅ Конфигурация OK!")
        print(f"🤖 Токен: {cls.TELEGRAM_TOKEN[:5]}...{cls.TELEGRAM_TOKEN[-5:]}")
        print(f"📁 Данные: {cls.DATA_DIR}")
        return True


# Автопроверка
try:
    Config.check()
except ValueError as e:
    print(f"\n🚨 {e}\n")
    raise
