import hashlib
import secrets
import json
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from app.utils.logger import get_logger
from app.database.storage import storage

logger = get_logger(__name__)

class SecurityManager:
    def __init__(self):
        self.failed_attempts = {}
        self.blocked_ips = set()
        self.max_attempts = 5
        self.block_duration = 3600  # 1 час
        self.tokens = {}
        self.load_blocked_ips()
    
    def load_blocked_ips(self):
        """Загрузка заблокированных IP"""
        try:
            with open('data/blocked_ips.json', 'r') as f:
                data = json.load(f)
                self.blocked_ips = set(data.get('ips', []))
        except:
            self.blocked_ips = set()
    
    def save_blocked_ips(self):
        """Сохранение заблокированных IP"""
        try:
            with open('data/blocked_ips.json', 'w') as f:
                json.dump({'ips': list(self.blocked_ips)}, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения блокировок: {e}")
    
    def hash_password(self, password: str) -> str:
        """Хэширование пароля"""
        salt = secrets.token_hex(16)
        return hashlib.sha256((password + salt).encode()).hexdigest() + ':' + salt
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Проверка пароля"""
        try:
            stored_hash, salt = hashed.split(':')
            return stored_hash == hashlib.sha256((password + salt).encode()).hexdigest()
        except:
            return False
    
    def generate_token(self, user_id: int, expires_in: int = 86400) -> str:
        """Генерация токена (24 часа)"""
        token = secrets.token_urlsafe(32)
        self.tokens[token] = {
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(seconds=expires_in)).isoformat()
        }
        return token
    
    def verify_token(self, token: str) -> dict:
        """Проверка токена"""
        if token not in self.tokens:
            return None
        
        token_data = self.tokens[token]
        expires_at = datetime.fromisoformat(token_data['expires_at'])
        
        if datetime.now() > expires_at:
            del self.tokens[token]
            return None
        
        return token_data
    
    def rate_limit(self, func):
        """Декоратор для ограничения запросов"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or 'unknown'
            
            # Проверка блокировки
            if ip in self.blocked_ips:
                return jsonify({'error': 'IP заблокирован за нарушения'}), 403
            
            # Обновление попыток
            now = time.time()
            if ip not in self.failed_attempts:
                self.failed_attempts[ip] = {'count': 0, 'first_attempt': now}
            
            # Сброс старых попыток (через 10 минут)
            if now - self.failed_attempts[ip]['first_attempt'] > 600:
                self.failed_attempts[ip] = {'count': 0, 'first_attempt': now}
            
            # Блокировка при превышении
            if self.failed_attempts[ip]['count'] >= self.max_attempts:
                self.blocked_ips.add(ip)
                self.save_blocked_ips()
                return jsonify({'error': 'Слишком много попыток. IP заблокирован'}), 429
            
            # Вызов функции
            result = func(*args, **kwargs)
            
            # Если ошибка авторизации - увеличиваем счётчик
            if isinstance(result, tuple) and result[1] in [401, 403]:
                self.failed_attempts[ip]['count'] += 1
            
            return result
        return wrapper
    
    def require_auth(self, func):
        """Декоратор для проверки авторизации"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            
            if not token:
                return jsonify({'error': 'Требуется авторизация'}), 401
            
            token_data = self.verify_token(token)
            if not token_data:
                return jsonify({'error': 'Недействительный токен'}), 401
            
            # Передаём user_id в функцию
            kwargs['user_id'] = token_data['user_id']
            return func(*args, **kwargs)
        return wrapper
    
    def log_action(self, user_id: int, action: str, details: dict = None):
        """Логирование действий"""
        log_entry = {
            'user_id': user_id,
            'action': action,
            'ip': request.remote_addr,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        
        try:
            with open('logs/security.log', 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Ошибка логирования: {e}")
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Проверка блокировки IP"""
        return ip in self.blocked_ips
    
    def unblock_ip(self, ip: str):
        """Разблокировка IP"""
        if ip in self.blocked_ips:
            self.blocked_ips.remove(ip)
            self.save_blocked_ips()
            logger.info(f"✅ IP {ip} разблокирован")
            return True
        return False
    
    def get_security_stats(self) -> dict:
        """Статистика безопасности"""
        return {
            'blocked_ips': len(self.blocked_ips),
            'active_tokens': len(self.tokens),
            'failed_attempts': len(self.failed_attempts),
            'total_attempts': sum(data['count'] for data in self.failed_attempts.values())
        }

security = SecurityManager()
