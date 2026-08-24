from app.database.storage import storage
from app.betting.strategy import BettingStrategy
from app.utils.logger import get_logger

logger = get_logger(__name__)

class AutoBet:
    def __init__(self):
        self.bank = storage.load_bank()
        self.strategy = BettingStrategy(self.bank)
        self.min_ev = 50  # Минимальный EV для авто-ставки
        self.max_stake_percent = 5
        self.total_bet_today = 0
        self.max_bets_per_day = 5
    
    def check_and_bet(self, match_data):
        """Проверяет матч и делает ставку если нужно"""
        bets = match_data.get('bets', [])
        if not bets:
            return None
        
        # Берем лучшую ставку
        best_bet = bets[0]
        ev = best_bet.get('ev', 0)
        
        # Проверяем условия
        if ev < self.min_ev:
            logger.info(f"⚠️ EV太低 ({ev}% < {self.min_ev}%) - пропускаем")
            return None
        
        if self.total_bet_today >= self.max_bets_per_day:
            logger.info(f"⚠️ Лимит ставок на день ({self.max_bets_per_day}) достигнут")
            return None
        
        # Рассчитываем ставку
        odds = best_bet.get('odds', 0)
        prob = best_bet.get('prob', 0) / 100
        stake = self.strategy.kelly_criterion(prob, odds)
        
        if stake < 1:
            logger.info(f"⚠️ Ставка слишком маленькая (${stake}) - пропускаем")
            return None
        
        # Ограничиваем
        max_stake = self.bank * (self.max_stake_percent / 100)
        stake = min(stake, max_stake)
        
        # Сохраняем ставку
        self.total_bet_today += 1
        self.bank -= stake
        storage.save_bank(self.bank)
        
        # Логируем
        logger.info(f"✅ АВТО-СТАВКА: {match_data['home']} vs {match_data['away']}")
        logger.info(f"   Ставка: {best_bet['label']} за {odds}")
        logger.info(f"   Сумма: ${stake} | EV: {ev}%")
        
        return {
            'match': f"{match_data['home']} vs {match_data['away']}",
            'bet': best_bet['label'],
            'odds': odds,
            'stake': stake,
            'ev': ev
        }
    
    def reset_daily_limit(self):
        """Сброс дневного лимита"""
        self.total_bet_today = 0

auto_bet = AutoBet()
