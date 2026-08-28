import os
import json
from pathlib import Path

class Storage:
    """Хранение данных бота"""
    
    def __init__(self):
        # Определяем папку data в корне проекта
        base_dir = Path(__file__).parent.parent.parent
        self.data_dir = base_dir / 'data'
        
        # Создаём папку если её нет
        self.data_dir.mkdir(exist_ok=True)
        
        # Пути к файлам
        self.history_file = self.data_dir / 'history.json'
        self.bank_file = self.data_dir / 'bank.json'
        self.stats_file = self.data_dir / 'stats.json'
        self.cache_file = self.data_dir / 'cache.json'
        
        # Инициализация файлов
        self._init_files()
    
    def _init_files(self):
        """Создаёт файлы с пустыми данными если их нет"""
        default_data = {
            'history.json': [],
            'bank.json': 1000.0,
            'stats.json': {
                'total': 0,
                'wins': 0,
                'losses': 0,
                'pushes': 0,
                'total_profit': 0,
                'winrate': 0,
                'roi': 0
            },
            'cache.json': {}
        }
        
        for filename, default in default_data.items():
            file_path = self.data_dir / filename
            if not file_path.exists():
                with open(file_path, 'w') as f:
                    json.dump(default, f, indent=2)
    
    def load_history(self):
        """Загружает историю ставок"""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_history(self, data):
        """Сохраняет историю ставок"""
        with open(self.history_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_bank(self):
        """Загружает банк"""
        try:
            with open(self.bank_file, 'r') as f:
                return json.load(f)
        except:
            return 1000.0
    
    def save_bank(self, amount):
        """Сохраняет банк"""
        with open(self.bank_file, 'w') as f:
            json.dump(amount, f, indent=2)
    
    def load_stats(self):
        """Загружает статистику"""
        try:
            with open(self.stats_file, 'r') as f:
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
    
    def save_stats(self, data):
        """Сохраняет статистику"""
        with open(self.stats_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_cache(self):
        """Загружает кэш"""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def save_cache(self, data):
        """Сохраняет кэш"""
        with open(self.cache_file, 'w') as f:
            json.dump(data, f, indent=2)


# Создаём глобальный экземпляр
storage = Storage()
