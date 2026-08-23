from typing import Dict, List, Tuple
from app.api.weather import weather_api
from app.utils.logger import get_logger

logger = get_logger(__name__)

class XGAnalyzer:
    def __init__(self):
        self.base_home_xg = 1.5
        self.base_away_xg = 1.3
        self.home_bonus = 1.08
    
    def calculate_xg(self, match_data: Dict, fixture_id: int) -> Tuple[float, float, List[str]]:
        reasons = []
        
        home_xg = self.base_home_xg
        away_xg = self.base_away_xg
        
        factors = match_data.get('factors', {})
        
        # 1. Домашнее поле
        home_xg *= self.home_bonus
        reasons.append("🏠 Домашнее поле (+8%)")
        
        # 2. Форма
        home_form = factors.get('home_form', {}).get('ratio', 0.5)
        away_form = factors.get('away_form', {}).get('ratio', 0.5)
        
        home_xg *= (home_form * 0.3 + 0.85)
        away_xg *= (away_form * 0.3 + 0.85)
        reasons.append(f"📈 Форма хозяев: +{round((home_form*0.3+0.85-1)*100)}%")
        reasons.append(f"📈 Форма гостей: +{round((away_form*0.3+0.85-1)*100)}%")
        
        # 3. Травмы
        home_injuries = factors.get('home_injuries_list', [])
        away_injuries = factors.get('away_injuries_list', [])
        
        home_xg *= (1 - len(home_injuries) * 0.04)
        away_xg *= (1 - len(away_injuries) * 0.04)
        if home_injuries:
            reasons.append(f"🏥 Травмы хозяев: {len(home_injuries)} игроков")
        if away_injuries:
            reasons.append(f"🏥 Травмы гостей: {len(away_injuries)} игроков")
        
        # 4. Погода
        weather = match_data.get('weather')
        if weather:
            impact, reason = weather_api.get_impact(weather)
            home_xg *= impact
            away_xg *= impact
            reasons.append(f"🌤️ {reason}")
        
        # Ограничение
        home_xg = max(0.3, min(home_xg, 4.5))
        away_xg = max(0.3, min(away_xg, 4.5))
        
        return home_xg, away_xg, reasons

xg_analyzer = XGAnalyzer()
