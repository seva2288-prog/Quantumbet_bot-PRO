# app/database/storage.py
import os
import json
from datetime import datetime
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Storage:
    def __init__(self):
        self.data_dir = Config.DATA_DIR
        self._ensure_dir()

    def _ensure_dir(self):
        """Создает папку для данных, если её нет"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _get_file_path(self, filename):
        """Возвращает полный путь к файлу"""
        return os.path.join(self.data_dir, filename)

    # ===== ИСТОРИЯ СТАВОК =====
    def load_history(self):
        """Загружает историю ставок"""
        try:
            with open(self._get_file_path('history.json'), 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_history(self, history):
        """Сохраняет историю ставок"""
        with open(self._get_file_path('history.json'), 'w') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    # ===== СТАТИСТИКА =====
    def load_stats(self):
        """Загружает статистику"""
        try:
            with open(self._get_file_path('stats.json'), 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                'total': 0,
                'wins': 0,
                'losses': 0,
                'pushes': 0,
                'total_profit': 0,
                'bank': 1000
            }

    def save_stats(self, stats):
        """Сохраняет статистику"""
        with open(self._get_file_path('stats.json'), 'w') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    # ===== КЭШ =====
    def load_cache(self):
        """Загружает кэш"""
        try:
            with open(self._get_file_path('cache.json'), 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_cache(self, cache):
        """Сохраняет кэш"""
        with open(self._get_file_path('cache.json'), 'w') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    # ===== БАНК (НОВЫЕ МЕТОДЫ) =====
    def load_bank(self):
        """Загружает текущий банк"""
        try:
            stats = self.load_stats()
            return stats.get('bank', 1000)
        except Exception:
            return 1000

    def save_bank(self, bank):
        """Сохраняет банк"""
        try:
            stats = self.load_stats()
            stats['bank'] = bank
            self.save_stats(stats)
            return True
        except Exception:
            return False


# Создаем глобальный экземпляр
storage = Storage()
