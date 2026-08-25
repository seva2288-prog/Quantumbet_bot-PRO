import json
import os
from datetime import datetime
from typing import Dict, List, Any

class Storage:
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.files = {
            'bank': 'bank.json',
            'history': 'history.json',
            'weights': 'weights.json',
            'stats': 'stats_total.json',
            'cache': 'cache.json',
            'blocked_ips': 'blocked_ips.json'
        }
        
        # Автоматическое создание файлов с начальными данными
        default_data = {
            'bank': {'bank': 1000},
            'history': [],
            'stats': {'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0, 'total_profit': 0},
            'weights': {},
            'cache': {},
            'blocked_ips': {'ips': []}
        }
        
        for name, default in default_data.items():
            path = self._get_path(name)
            if not os.path.exists(path):
                try:
                    self.save(name, default)
                    print(f"✅ Создан файл: {path}")
                except Exception as e:
                    print(f"❌ Ошибка создания {path}: {e}")
    
    def _get_path(self, name: str) -> str:
        return os.path.join(self.data_dir, self.files.get(name, f'{name}.json'))
    
    def load(self, name: str, default=None) -> Any:
        try:
            path = self._get_path(name)
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Файл {name} не найден, создаю новый")
            return default if default is not None else {}
        except json.JSONDecodeError:
            print(f"⚠️ Ошибка чтения {name}, создаю новый")
            return default if default is not None else {}
        except Exception as e:
            print(f"❌ Ошибка загрузки {name}: {e}")
            return default if default is not None else {}
    
    def save(self, name: str, data: Any):
        try:
            path = self._get_path(name)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Сохранено: {path}")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения {name}: {e}")
            return False
    
    # ===== БАНК =====
    def load_bank(self) -> float:
        data = self.load('bank', {'bank': 1000})
        return data.get('bank', 1000)
    
    def save_bank(self, bank: float):
        self.save('bank', {'bank': bank, 'updated': datetime.now().isoformat()})
    
    # ===== ИСТОРИЯ =====
    def load_history(self) -> List:
        history = self.load('history', [])
        if not isinstance(history, list):
            print(f"⚠️ История не список, создаю новую")
            return []
        return history
    
    def save_history(self, history: List):
        if not isinstance(history, list):
            history = []
        self.save('history', history)
    
    # ===== ВЕСА =====
    def load_weights(self) -> Dict:
        weights = self.load('weights', {})
        if not isinstance(weights, dict):
            return {}
        return weights
    
    def save_weights(self, weights: Dict):
        if not isinstance(weights, dict):
            weights = {}
        self.save('weights', weights)
    
    # ===== СТАТИСТИКА =====
    def load_stats(self) -> Dict:
        stats = self.load('stats', {'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0, 'total_profit': 0})
        if not isinstance(stats, dict):
            return {'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0, 'total_profit': 0}
        
        # Проверяем наличие всех ключей
        required_keys = ['total', 'wins', 'losses', 'pushes', 'total_profit']
        for key in required_keys:
            if key not in stats:
                stats[key] = 0
        
        return stats
    
    def save_stats(self, stats: Dict):
        if not isinstance(stats, dict):
            stats = {'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0, 'total_profit': 0}
        self.save('stats', stats)
    
    # ===== КЭШ =====
    def load_cache(self) -> Dict:
        cache = self.load('cache', {})
        if not isinstance(cache, dict):
            return {}
        return cache
    
    def save_cache(self, cache: Dict):
        if not isinstance(cache, dict):
            cache = {}
        cache['last_update'] = datetime.now().isoformat()
        self.save('cache', cache)
    
    # ===== ЗАБЛОКИРОВАННЫЕ IP =====
    def load_blocked_ips(self) -> List:
        data = self.load('blocked_ips', {'ips': []})
        if not isinstance(data, dict):
            return []
        return data.get('ips', [])
    
    def save_blocked_ips(self, ips: List):
        if not isinstance(ips, list):
            ips = []
        self.save('blocked_ips', {'ips': ips})
    
    # ===== ВСПОМОГАТЕЛЬНЫЕ =====
    def get_all_data(self) -> Dict:
        """Получение всех данных для бэкапа"""
        return {
            'bank': self.load_bank(),
            'history': self.load_history(),
            'stats': self.load_stats(),
            'weights': self.load_weights(),
            'cache': self.load_cache()
        }
    
    def clear_all(self):
        """Очистка всех данных"""
        for name in self.files.keys():
            path = self._get_path(name)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"🗑️ Удалён: {path}")
                except Exception as e:
                    print(f"❌ Ошибка удаления {path}: {e}")
        
        # Пересоздаём файлы
        self.__init__(self.data_dir)
        print("✅ Все данные очищены")

# Глобальный экземпляр
storage = Storage()
