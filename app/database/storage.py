# app/database/storage.py
import os
import json
from datetime import datetime
from app.config import Config
from app.utils.logger import get_logger
from app.database.db import db

logger = get_logger(__name__)


class Storage:
    def __init__(self):
        self.data_dir = Config.DATA_DIR
        self._ensure_dir()
        # Миграция данных из JSON в БД
        self._migrate_if_needed()

    def _ensure_dir(self):
        """Создает папку для данных, если её нет"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _migrate_if_needed(self):
        """Миграция из JSON в БД при первом запуске"""
        json_path = self._get_file_path('history.json')
        if os.path.exists(json_path):
            # Проверяем, есть ли данные в БД
            existing = db.load_history()
            if not existing:
                count = db.migrate_from_json()
                if count > 0:
                    # Переименовываем старый файл как бэкап
                    backup_path = self._get_file_path('history_backup.json')
                    os.rename(json_path, backup_path)
                    logger.info(f"📦 JSON файл переименован в history_backup.json")

    def _get_file_path(self, filename):
        """Возвращает полный путь к файлу"""
        return os.path.join(self.data_dir, filename)

    # ===== ИСТОРИЯ СТАВОК (использует БД) =====
    def load_history(self):
        """Загружает историю ставок из БД"""
        return db.load_history()

    def save_history(self, history):
        """Сохраняет историю ставок в БД"""
        db.save_bets(history)

    # ===== СТАТИСТИКА =====
    def load_stats(self):
        """Загружает статистику из БД"""
        stats = db.get_stats()
        # Добавляем банк из файла если есть
        try:
            with open(self._get_file_path('stats.json'), 'r') as f:
                file_stats = json.load(f)
                if 'bank' in file_stats:
                    stats['bank'] = file_stats['bank']
        except:
            stats['bank'] = 1000
        return stats

    def save_stats(self, stats):
        """Сохраняет статистику (только банк в файл)"""
        # Сохраняем только банк в JSON для совместимости
        try:
            with open(self._get_file_path('stats.json'), 'w') as f:
                json.dump({'bank': stats.get('bank', 1000)}, f, indent=2)
        except:
            pass

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

    # ===== БАНК =====
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

    # ===== НОВЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С БД =====
    def get_bets_by_date(self, date):
        """Быстрый поиск по дате"""
        return db.get_bets_by_date(date)

    def get_bets_by_result(self, result):
        """Быстрый поиск по результату"""
        return db.get_bets_by_result(result)

    def get_bets_by_stake(self, stake):
        """Быстрый поиск по сумме"""
        return db.get_bets_by_stake(stake)

    def get_dates_with_bets(self):
        """Получает список дат с ставками"""
        return db.get_dates_with_bets()


# Создаем глобальный экземпляр
storage = Storage()
