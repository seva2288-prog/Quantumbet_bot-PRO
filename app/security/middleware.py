from flask import request, jsonify, abort
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib
import hmac
from app.config import Config

class SecurityMiddleware:
    """Промежуточный слой безопасности"""
    
    def __init__(self):
        self.rate_limits = defaultdict(list)
        self.blocked_ips = set()
        self.whitelist_ips = set(Config.ALLOWED_IPS)
        
    def check_auth(self):
        """Проверяет авторизацию запроса"""
        # Проверяем, что запрос от админа
        if request.is_json:
            data = request.get_json()
            if data and 'message' in data:
                chat_id = data['message'].get('chat', {}).get('id')
                if str(chat_id) != Config.ADMIN_CHAT_ID:
                    return False
        
        # Проверяем IP
        client_ip = request.remote_addr
        if self.whitelist_ips and client_ip not in self.whitelist_ips:
            return False
        
        return True
    
    def rate_limit(self, key, limit=50, period=60):
        """Лимит запросов"""
        now = datetime.now()
        requests = self.rate_limits[key]
        
        # Очищаем старые запросы
        requests = [t for t in requests if now - t < timedelta(seconds=period)]
        self.rate_limits[key] = requests
        
        if len(requests) >= limit:
            return False
        
        requests.append(now)
        return True
    
    def block_ip(self, ip, duration=3600):
        """Блокировка IP"""
        self.blocked_ips.add(ip)
        # TODO: Добавить таймер для разблокировки
    
    def is_blocked(self, ip):
        """Проверка блокировки"""
        return ip in self.blocked_ips

# Глобальный экземпляр
security_middleware = SecurityMiddleware()

# Декораторы для защиты
def admin_only(f):
    """Декоратор: только для админа"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not security_middleware.check_auth():
            return jsonify({'error': '⛔ Доступ запрещён'}), 403
        return f(*args, **kwargs)
    return decorated_function

def rate_limit(limit=50, period=60):
    """Декоратор: лимит запросов"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            if security_middleware.is_blocked(client_ip):
                return jsonify({'error': '🚫 IP заблокирован'}), 403
            
            key = f"{client_ip}:{f.__name__}"
            if not security_middleware.rate_limit(key, limit, period):
                security_middleware.block_ip(client_ip)
                return jsonify({'error': f'⚠️ Слишком много запросов. IP заблокирован на час'}), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
