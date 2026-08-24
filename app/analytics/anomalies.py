from typing import Dict, List
from app.utils.logger import get_logger
from app.api.football import football_api

logger = get_logger(__name__)

class AnomalyDetector:
    def __init__(self):
        # Средние коэффициенты для разных лиг
        self.avg_odds = {
            'btts': 1.85,
            'over_2_5': 1.80,
            'home_win': 2.10,
            'away_win': 2.10,
            'draw': 3.20,
        }
    
    def get_average_odds(self, league: str = None) -> Dict:
        """Получение средних коэффициентов для лиги"""
        # В реальности нужно собирать статистику
        # Пока используем базовые значения
        return self.avg_odds
    
    def find_anomalies(self, match_data: Dict, odds_data: Dict) -> List[Dict]:
        """
        Поиск аномалий в коэффициентах
        """
        if not odds_data:
            return []
        
        anomalies = []
        avg_odds = self.get_average_odds(match_data.get('league'))
        
        # Проверяем каждый рынок
        for market, odd in odds_data.items():
            if odd <= 0:
                continue
            
            avg = avg_odds.get(market, 1.85)
            
            # Вычисляем отклонение
            deviation = round((odd - avg) / avg * 100, 1)
            
            # Аномалия если отклонение > 10%
            if abs(deviation) > 10:
                anomalies.append({
                    'market': market,
                    'odd': odd,
                    'avg': avg,
                    'deviation': deviation,
                    'type': 'overpriced' if deviation > 0 else 'underpriced',
                    'severity': 'high' if abs(deviation) > 20 else 'medium'
                })
        
        # Сортируем по силе аномалии
        anomalies.sort(key=lambda x: abs(x['deviation']), reverse=True)
        
        return anomalies
    
    def analyze_movement(self, fixture_id: int) -> Dict:
        """
        Анализ движения коэффициентов
        """
        # В реальности нужно хранить историю коэфов
        # Пока возвращаем заглушку
        return {
            'movement': 'stable',
            'changes': [],
            'significant': False
        }
    
    def check_news_impact(self, match_data: Dict) -> Dict:
        """
        Проверка влияния новостей
        """
        # Заглушка - в реальности нужен парсинг новостей
        return {
            'has_news': False,
            'impact': 'none',
            'teams_affected': []
        }
    
    def format_anomalies_message(self, match_data: Dict, anomalies: List[Dict]) -> str:
        """
        Форматирование сообщения об аномалиях
        """
        if not anomalies:
            return f"🔍 <b>Аномалии не найдены</b>\n🏟️ {match_data['home']} vs {match_data['away']}"
        
        msg = f"🔍 <b>АНАМАЛИИ НАЙДЕНЫ!</b>\n"
        msg += f"🏟️ {match_data['home']} vs {match_data['away']}\n"
        msg += f"🏆 {match_data['league']}\n\n"
        
        for anomaly in anomalies[:5]:
            emoji = "🔴" if anomaly['severity'] == 'high' else "🟡"
            direction = "⬆️ завышен" if anomaly['deviation'] > 0 else "⬇️ занижен"
            
            msg += f"{emoji} <b>{anomaly['market']}</b>\n"
            msg += f"   Кэф: {anomaly['odd']} (средний: {anomaly['avg']})\n"
            msg += f"   Отклонение: {anomaly['deviation']}% {direction}\n"
            
            if anomaly['deviation'] > 20:
                msg += f"   ⚠️ <b>СИЛЬНАЯ АНОМАЛИЯ!</b> Возможна валуйная ставка\n"
            elif anomaly['deviation'] > 10:
                msg += f"   ⚡ Умеренная аномалия\n"
            else:
                msg += f"   ℹ️ Незначительная аномалия\n"
            msg += "\n"
        
        # Общий вывод
        high_count = sum(1 for a in anomalies if a['severity'] == 'high')
        if high_count > 0:
            msg += f"⚠️ <b>Внимание!</b> Найдено {high_count} сильных аномалий\n"
            msg += "Рекомендуется проверить новости о командах"
        
        return msg

anomaly_detector = AnomalyDetector()
