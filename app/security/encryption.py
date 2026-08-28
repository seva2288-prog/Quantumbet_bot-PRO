import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.config import Config

class DataEncryption:
    def __init__(self):
        # Генерация ключа из ENCRYPTION_KEY
        if Config.ENCRYPTION_KEY:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'quantumbot_salt_2024',
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(Config.ENCRYPTION_KEY))
            self.cipher = Fernet(key)
        else:
            self.cipher = None
            print("⚠️ ENCRYPTION_KEY не задан — данные не шифруются!")
    
    def encrypt(self, data):
        if not self.cipher:
            return data
        json_str = json.dumps(data)
        encrypted = self.cipher.encrypt(json_str.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt(self, encrypted_data):
        if not self.cipher:
            return encrypted_data
        try:
            decoded = base64.b64decode(encrypted_data)
            decrypted = self.cipher.decrypt(decoded)
            return json.loads(decrypted)
        except:
            return None

encryption = DataEncryption()
