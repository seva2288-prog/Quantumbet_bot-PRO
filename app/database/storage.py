# app/database/storage.py
import json
import os
from datetime import datetime

class Storage:
    """Класс для управления данными (банк, история, кэш)"""
    
    def __init__(self):
        self.data_dir = 'data'
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_bank(self):
        """Загружает текущий банк"""
        try:
            with open(f'{self.data_dir}/bank.json', 'r') as f:
                data = json.load(f)
                return data.get('bank', 1000.0)
        except:
            return 1000.0
    
    def save_bank(self, bank):
        """Сохраняет банк"""
        with open(f'{self.data_dir}/bank.json', 'w') as f:
            json.dump({'bank': bank, 'updated': datetime.now().isoformat()}, f)
    
    def load_history(self):
        """Загружает историю ставок"""
        try:
            with open(f'{self.data_dir}/history.json', 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_history(self, history):
        """Сохраняет историю ставок"""
        with open(f'{self.data_dir}/history.json', 'w') as f:
            json.dump(history, f, indent=2)
    
    def load_stats(self):
        """Загружает статистику"""
        try:
            with open(f'{self.data_dir}/stats.json', 'r') as f:
                return json.load(f)
        except:
            return {
                'total': 0,
                'wins': 0,
                'losses': 0,
                'pushes': 0,
                'total_profit': 0,
                'winrate': 0,
                'roi': 0
            }
    
    def save_stats(self, stats):
        """Сохраняет статистику"""
        with open(f'{self.data_dir}/stats.json', 'w') as f:
            json.dump(stats, f, indent=2)
    
    def load_cache(self):
        """Загружает кэш"""
        try:
            with open(f'{self.data_dir}/cache.json', 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def save_cache(self, cache):
        """Сохраняет кэш"""
        with open(f'{self.data_dir}/cache.json', 'w') as f:
            json.dump(cache, f, indent=2)

# Создаем глобальный экземпляр
storage = Storage()
