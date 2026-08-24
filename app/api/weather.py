import requests
from typing import Optional, Dict
from config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

class WeatherAPI:
    def __init__(self):
        self.api_key = Config.WEATHER_API_KEY

    def get_weather(self, city: str) -> Optional[Dict]:
        """Получение погоды по городу (бесплатный эндпоинт)"""
        if not city:
            return None

        try:
            # ИСПОЛЬЗУЕМ БЕСПЛАТНЫЙ ЭНДПОИНТ
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'ru'
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Парсим нужные данные
                weather_main = data.get('weather', [{}])[0].get('main', 'Clear')
                weather_description = data.get('weather', [{}])[0].get('description', '')
                temp = data.get('main', {}).get('temp', 20)
                wind = data.get('wind', {}).get('speed', 0)
                humidity = data.get('main', {}).get('humidity', 0)
                pressure = data.get('main', {}).get('pressure', 0)

                return {
                    'weather': weather_main,
                    'description': weather_description,
                    'temp': round(temp),
                    'wind_speed': round(wind, 1),
                    'humidity': humidity,
                    'pressure': pressure,
                }

            else:
                logger.warning(f"⚠️ Ошибка погоды для {city}: {response.status_code}")
                return None

        except Exception as e:
            logger.warning(f"⚠️ Ошибка погоды: {e}")
            return None

    def get_impact(self, weather_data: Dict) -> tuple:
        """Расчет влияния погоды на матч"""
        if not weather_data:
            return 1.0, "☀️ Погода неизвестна"

        weather = weather_data.get('weather', '')
        temp = weather_data.get('temp', 20)
        wind = weather_data.get('wind_speed', 0)

        impact = 1.0
        reason = "☀️ Хорошая погода"

        if weather in ['Rain', 'Drizzle', 'Thunderstorm']:
            impact = 0.92
            reason = f"🌧️ Дождь (-8%)"
        elif weather == 'Snow':
            impact = 0.85
            reason = "❄️ Снег (-15%)"
        elif weather in ['Mist', 'Fog', 'Haze']:
            impact = 0.90
            reason = "🌫️ Туман (-10%)"
        elif wind > 10:
            impact = 0.93
            reason = f"💨 Сильный ветер ({wind:.0f} м/с) (-7%)"
        elif temp > 30:
            impact = 1.05
            reason = f"🔥 Жара ({temp:.0f}°C) (+5%)"
        elif temp < 0:
            impact = 0.95
            reason = f"🥶 Холод ({temp:.0f}°C) (-5%)"
        elif weather in ['Rain', 'Drizzle'] and wind > 8:
            impact = 0.88
            reason = "🌧️💨 Дождь + ветер (-12%)"

        return impact, reason

weather_api = WeatherAPI()
