import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from app.config import Config

class TwoFactorAuth:
    """Двухфакторная авторизация"""
    
    def __init__(self):
        self.codes = {}  # chat_id -> {code, expires}
    
    def generate_code(self, chat_id: str) -> str:
        """Генерирует код подтверждения"""
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        expires = datetime.now() + timedelta(minutes=5)
        self.codes[chat_id] = {'code': code, 'expires': expires}
        return code
    
    def verify_code(self, chat_id: str, code: str) -> bool:
        """Проверяет код"""
        if chat_id not in self.codes:
            return False
        
        data = self.codes[chat_id]
        if datetime.now() > data['expires']:
            del self.codes[chat_id]
            return False
        
        if data['code'] == code:
            del self.codes[chat_id]
            return True
        
        return False
    
    def verify_hmac(self, data: str, signature: str) -> bool:
        """Проверяет HMAC подпись"""
        secret = Config.SESSION_SECRET.encode()
        expected = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

# Создаём глобальный экземпляр
security = TwoFactorAuth()
