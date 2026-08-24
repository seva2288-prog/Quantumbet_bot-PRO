from functools import wraps
from flask import request, jsonify
from app.security.auth import security
from app.utils.logger import get_logger

logger = get_logger(__name__)

def secure_endpoint(func):
    """Декоратор для защиты эндпоинтов"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Rate limiting
        ip = request.remote_addr or 'unknown'
        
        if security.is_ip_blocked(ip):
            logger.warning(f"⚠️ Заблокированный IP: {ip}")
            return jsonify({'error': 'Доступ запрещён'}), 403
        
        # Проверка авторизации для чувствительных эндпоинтов
        if request.method in ['POST', 'PUT', 'DELETE']:
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not token:
                return jsonify({'error': 'Требуется авторизация'}), 401
            
            token_data = security.verify_token(token)
            if not token_data:
                return jsonify({'error': 'Недействительный токен'}), 401
        
        # Логирование
        security.log_action(
            user_id=kwargs.get('user_id', 0),
            action=f"{request.method} {request.path}",
            details={'ip': ip, 'user_agent': request.headers.get('User-Agent', '')}
        )
        
        return func(*args, **kwargs)
    return wrapper

def sanitize_input(func):
    """Декоратор для очистки входных данных"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.is_json:
            data = request.get_json()
            # Очистка данных
            if data:
                for key, value in data.items():
                    if isinstance(value, str):
                        # Удаление потенциально опасных символов
                        data[key] = value.replace('<', '').replace('>', '').replace('script', '')
        return func(*args, **kwargs)
    return wrapper
