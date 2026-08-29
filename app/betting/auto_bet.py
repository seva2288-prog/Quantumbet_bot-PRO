import logging
from app.database.storage import storage

logger = logging.getLogger(__name__)

class AutoBet:
    """Класс для автоматического размещения ставок"""
    
    def __init__(self):
        self.enabled = True
        self.bets_today = 0
        self.max_bets_per_day = 10
        
    def check_and_bet(self, match_data):
        """
        Проверяет матч и размещает ставку если условия выполнены
        
        Args:
            match_data: dict с данными матча и ставками
            
        Returns:
            dict: информация о размещенной ставке или None
        """
        if not self.enabled:
            logger.warning("⚠️ AutoBet отключен")
            return None
            
        bets = match_data.get('bets', [])
        if not bets:
            return None
            
        # Берем лучшую ставку (с максимальным EV)
        best_bet = max(bets, key=lambda x: x.get('ev', 0))
        
        # Проверяем, что EV положительный
        if best_bet.get('ev', 0) <= 0:
            logger.info(f"❌ Ставка отклонена: EV = {best_bet.get('ev')}%")
            return None
            
        # Проверяем, что коэффициент приемлемый
        if best_bet.get('odds', 0) < 1.5:
            logger.info(f"❌ Ставка отклонена: слишком низкий коэффициент")
            return None
            
        # Проверяем, что сумма ставки не превышает банк
        bank = storage.load_bank()
        stake = best_bet.get('stake', 0)
        if stake > bank * 0.1:  # Не более 10% от банка
            logger.warning(f"⚠️ Ставка слишком большая: {stake} > {bank * 0.1}")
            return None
            
        # Возвращаем информацию о ставке
        self.bets_today += 1
        
        result = {
            'match': f"{match_data.get('home', '')} vs {match_data.get('away', '')}",
            'match_time': match_data.get('match_time', ''),
            'bet': best_bet.get('label', ''),
            'odds': best_bet.get('odds', 0),
            'stake': stake,
            'ev': best_bet.get('ev', 0),
            'marker_stake': best_bet.get('marker_stake', 0)
        }
        
        logger.info(f"✅ Ставка размещена: {result}")
        return result
