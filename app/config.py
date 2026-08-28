"""Конфигурация бота"""
import os

class Config:
    # === ТЕЛЕГРАМ ===
    TELEGRAM_TOKEN = "8884017743:AAHE5WikM-ywDQ50nv-_nQajYkLSLQB2g3I"
    ADMIN_CHAT_ID = 228801334  # ← ЭТО ЧИСЛО, БЕЗ КАВЫЧЕК!
    
    # === API ===
    FOOTBALL_API_KEY = "fa6a81c18feae6769a0fa3baefd9e476"
    FOOTBALL_API_URL = "https://v3.football.api-sports.io"
    WEATHER_API_KEY = "7f0cfaced346b0fe364815ab65d627af"
    WEATHER_API_URL = "https://api.openweathermap.org/data/2.5"
    
    # === ЛИГИ ===
    LEAGUES = [
        39,   # АПЛ
        140,  # Ла Лига
        78,   # Бундеслига
        135,  # Серия А
        61,   # Лига 1
        2,    # УЕФА
    ]
    
    LEAGUE_NAMES = {
        39: "АПЛ",
        140: "Ла Лига",
        78: "Бундеслига",
        135: "Серия А",
        61: "Лига 1",
        2: "Лига Чемпионов",
    }
    
    # === СТАВКИ ===
    MAX_BETS_PER_RUN = 10

    @classmethod
    def check(cls):
        """Проверка наличия ключей"""
        missing = []
        if not cls.TELEGRAM_TOKEN:
            missing.append("TELEGRAM_TOKEN")
        if not cls.ADMIN_CHAT_ID:
            missing.append("ADMIN_CHAT_ID")
        if not cls.FOOTBALL_API_KEY:
            missing.append("FOOTBALL_API_KEY")
        
        if missing:
            raise ValueError(f"Отсутствуют: {', '.join(missing)}")
        print("✅ Все ключи загружены!")

# Проверка при загрузке
Config.check()
