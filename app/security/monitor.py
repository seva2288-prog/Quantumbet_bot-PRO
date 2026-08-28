import logging
from datetime import datetime
from collections import defaultdict

class SecurityMonitor:
    """Мониторинг безопасности"""
    
    def __init__(self):
        self.attack_attempts = defaultdict(int)
        self.warning_log = []
        self.max_logs = 1000
        
        self.logger = logging.getLogger('security')
        handler = logging.FileHandler('logs/security.log')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_attack(self, attack_type: str, details: str):
        """Логирует попытку атаки"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"[{timestamp}] {attack_type}: {details}"
        
        self.warning_log.append(entry)
        if len(self.warning_log) > self.max_logs:
            self.warning_log = self.warning_log[-self.max_logs:]
        
        self.logger.warning(entry)
    
    def get_recent_attacks(self, limit=10):
        """Возвращает последние атаки"""
        return self.warning_log[-limit:]

# Глобальный экземпляр
monitor = SecurityMonitor()
