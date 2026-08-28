import logging
from datetime import datetime
from collections import defaultdict
from flask import request
from app.config import Config

class SecurityMonitor:
    """Мониторинг безопасности"""
    
    def __init__(self):
        self.attack_attempts = defaultdict(int)
        self.warning_log = []
        self.max_logs = 1000
        
        # Настройка логгера
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
        
        # Отправляем уведомление админу
        self._send_alert(f"⚠️ Обнаружена атака!\nТип: {attack_type}\nДетали: {details}")
        
        # Логируем в файл
        self.logger.warning(entry)
    
    def _send_alert(self, message: str):
        """Отправляет уведомление админу"""
        try:
            from app.utils.logger import send_telegram  # Используем твою функцию
            send_telegram(message)
        except:
            pass
    
    def get_recent_attacks(self, limit=10):
        """Возвращает последние атаки"""
        return self.warning_log[-limit:]

# Глобальный экземпляр
monitor = SecurityMonitor()
