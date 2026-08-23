from typing import Dict, Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)

class BetfairAPI:
    def __init__(self, username=None, password=None, app_key=None):
        self.username = username
        self.password = password
        self.app_key = app_key
        self.session_token = None
        self.is_authenticated = False
    
    def login(self) -> bool:
        """Авторизация в Betfair"""
        try:
            # В реальном проекте здесь будет запрос к Betfair API
            # Для демонстрации используем заглушку
            if self.username and self.password:
                self.session_token = "demo_token_12345"
                self.is_authenticated = True
                logger.info("✅ Betfair авторизация успешна")
                return True
            else:
                # Демо-режим без авторизации
                self.is_authenticated = True
                logger.info("✅ Betfair демо-режим активирован")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации Betfair: {e}")
            return False
    
    def get_odds(self, market_id: str) -> Optional[Dict]:
        """Получение коэффициентов с биржи"""
        if not self.is_authenticated:
            self.login()
        
        try:
            # В реальном проекте здесь будет запрос к Betfair API
            # Для демонстрации возвращаем тестовые данные
            return {
                'home_win': 2.02,
                'draw': 3.45,
                'away_win': 3.78,
                'btts_yes': 1.87,
                'btts_no': 2.12,
                'over_2_5': 1.82,
                'under_2_5': 2.15,
            }
        except Exception as e:
            logger.error(f"Ошибка получения коэффициентов: {e}")
            return None
    
    def place_bet(self, market_id: str, selection_id: str, stake: float, odds: float) -> bool:
        """Размещение ставки через Betfair"""
        if not self.is_authenticated:
            self.login()
        
        try:
            # В реальном проекте здесь будет запрос к Betfair API
            logger.info(f"✅ Ставка размещена: {selection_id} за {odds} на ${stake}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка размещения ставки: {e}")
            return False


def compare_odds(betfair_odds, bookmaker_odds):
    """Сравнение коэффициентов букмекера и биржи"""
    comparison = {}
    mapping = {
        'home_win': 'Победа хозяев',
        'draw': 'Ничья',
        'away_win': 'Победа гостей',
        'btts_yes': 'ОЗ - ДА',
        'btts_no': 'ОЗ - НЕТ',
        'over_2_5': 'Тотал > 2.5',
        'under_2_5': 'Тотал < 2.5',
    }
    
    for market, bf_odds in betfair_odds.items():
        if market in mapping:
            bm_odds = bookmaker_odds.get(market, 0)
            if bm_odds > 0 and bf_odds > 0:
                diff = round(bm_odds - bf_odds, 2)
                comparison[mapping[market]] = {
                    'bookmaker': bm_odds,
                    'betfair': bf_odds,
                    'difference': diff,
                    'is_good': diff > 0.05  # Букмекер дает больше на 0.05+
                }
    
    return comparison


# Глобальный экземпляр для использования
betfair = BetfairAPI()
