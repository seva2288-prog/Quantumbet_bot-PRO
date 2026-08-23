import requests
from typing import Optional, Dict
from config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

class WeatherAPI:
    def __init__(self):
        self.api_key = Config.WEATHER_API_KEY
    
    def get_weather(self, city: str) -> Optional[Dict]:
        try:
            # Получаем координаты
            geo_url = "http://api.openweathermap.org/geo/1.0/direct"
            geo_params = {'q': city, 'limit': 1, 'appid': self.api_key}
            geo_resp = requests.get(geo_url, params=geo_params, timeout=5)
            
            if geo_resp.status_code != 200:
                return None
            
            geo_data = geo_resp.json()
            if not geo_data:
                return None
            
            lat, lon = geo_data[0]['lat'], geo_data[0]['lon']
            
            # Получаем погоду
            weather_url = "https://api.openweathermap.org/data/4.0/onecall"
            weather_params = {
                'lat': lat,
                'lon': lon,
                'units': 'metric',
                'appid': self.api_key
            }
            weather_resp = requests.get(weather_url, params=weather_params, timeout=5)
            
            if weather_resp.status_code != 200:
                return None
            
            data = weather_resp.json()
            if not data.get('data') or len(data['data']) == 0:
                return None
            
            current = data['data'][0]
            weather = current.get('weather', [{}])[0].get('main', 'Clear')
            temp = current.get('temp', {}).get('day', 20)
            wind = current.get('wind_speed', 0)
            
            return {'weather': weather, 'temp': round(temp), 'wind_speed': wind}
        except Exception as e:
            logger.warning(f"Ошибка погоды: {e}")
            return None
    
    def get_impact(self, weather_data: Dict) -> tuple:
        if not weather_data:
            return 1.0, "☀️ Погода неизвестна"
        
        weather = weather_data.get('weather', '')
        temp = weather_data.get('temp', 20)
        wind = weather_data.get('wind_speed', 0)
        
        impact = 1.0
        reason = "☀️ Хорошая погода"
        
        if weather in ['Rain', 'Drizzle', 'Thunderstorm']:
            impact = 0.92
            reason = "🌧️ Дождь (-8%)"
        elif weather == 'Snow':
            impact = 0.85
            reason = "❄️ Снег (-15%)"
        elif weather in ['Mist', 'Fog', 'Haze']:
            impact = 0.90
            reason = "🌫️ Туман (-10%)"
        elif wind > 10:
            impact = 0.93
            reason = f"💨 Ветер (-7%)"
        elif temp > 30:
            impact = 1.05
            reason = f"🔥 Жара (+5%)"
        elif temp < 0:
            impact = 0.95
            reason = f"🥶 Холод (-5%)"
        
        return impact, reason

weather_api = WeatherAPI()
