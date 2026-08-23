class BettingStrategy:
    def __init__(self, bank=1000, max_stake_percent=5):
        self.bank = bank
        self.max_stake_percent = max_stake_percent
    
    def kelly_criterion(self, probability, odds):
        b = odds - 1
        q = 1 - probability
        
        if b <= 0 or probability <= 0:
            return 0
        
        f = (probability * b - q) / b
        f = max(0, min(f, self.max_stake_percent / 100))
        stake = self.bank * f
        
        return round(stake, 2)
    
    def fractional_kelly(self, probability, odds, fraction=0.5):
        full_kelly = self.kelly_criterion(probability, odds)
        return round(full_kelly * fraction, 2)
    
    def set_bank(self, new_bank):
        self.bank = new_bank
