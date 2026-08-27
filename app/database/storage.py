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
        self._migrate_if_needed()

    def _ensure_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _migrate_if_needed(self):
        json_path = self._get_file_path('history.json')
        if os.path.exists(json_path):
            existing = db.load_history()
            if not existing:
                count = db.migrate_from_json()
                if count > 0:
                    backup_path = self._get_file_path('history_backup.json')
                    os.rename(json_path, backup_path)
                    logger.info(f"📦 JSON файл переименован в history_backup.json")

    def _get_file_path(self, filename):
        return os.path.join(self.data_dir, filename)

    def load_history(self):
        return db.load_history()

    def save_history(self, history):
        db.save_bets(history)

    def load_stats(self):
        stats = db.get_stats()
        try:
            with open(self._get_file_path('stats.json'), 'r') as f:
                file_stats = json.load(f)
                if 'bank' in file_stats:
                    stats['bank'] = file_stats['bank']
        except:
            stats['bank'] = 1000
        return stats

    def save_stats(self, stats):
        try:
            with open(self._get_file_path('stats.json'), 'w') as f:
                json.dump({'bank': stats.get('bank', 1000)}, f, indent=2)
        except:
            pass

    def load_cache(self):
        try:
            with open(self._get_file_path('cache.json'), 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_cache(self, cache):
        with open(self._get_file_path('cache.json'), 'w') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    def load_bank(self):
        try:
            stats = self.load_stats()
            return stats.get('bank', 1000)
        except Exception:
            return 1000

    def save_bank(self, bank):
        try:
            stats = self.load_stats()
            stats['bank'] = bank
            self.save_stats(stats)
            return True
        except Exception:
            return False

    def get_bets_by_date(self, date):
        return db.get_bets_by_date(date)

    def get_bets_by_result(self, result):
        return db.get_bets_by_result(result)

    def get_bets_by_stake(self, stake):
        return db.get_bets_by_stake(stake)

    def get_dates_with_bets(self):
        return db.get_dates_with_bets()


storage = Storage()
