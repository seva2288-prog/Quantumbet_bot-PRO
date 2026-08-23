import json
from datetime import datetime
from typing import Dict, List, Any
import os

class Storage:
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.files = {
            'bank': 'bank.json',
            'history': 'history.json',
            'weights': 'weights.json',
            'stats': 'stats_total.json',
            'cache': 'cache.json'
        }
    
    def _get_path(self, name: str) -> str:
        return os.path.join(self.data_dir, self.files.get(name, f'{name}.json'))
    
    def load(self, name: str, default=None) -> Any:
        try:
            with open(self._get_path(name), 'r') as f:
                return json.load(f)
        except:
            return default if default is not None else {}
    
    def save(self, name: str, data: Any):
        try:
            with open(self._get_path(name), 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения {name}: {e}")
    
    def load_bank(self) -> float:
        data = self.load('bank', {'bank': 1000})
        return data.get('bank', 1000)
    
    def save_bank(self, bank: float):
        self.save('bank', {'bank': bank, 'updated': datetime.now().isoformat()})
    
    def load_history(self) -> List:
        return self.load('history', [])
    
    def save_history(self, history: List):
        self.save('history', history)
    
    def load_weights(self) -> Dict:
        return self.load('weights', {})
    
    def save_weights(self, weights: Dict):
        self.save('weights', weights)
    
    def load_stats(self) -> Dict:
        return self.load('stats', {'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0, 'history': []})
    
    def save_stats(self, stats: Dict):
        self.save('stats', stats)
    
    def load_cache(self) -> Dict:
        return self.load('cache', {})
    
    def save_cache(self, cache: Dict):
        cache['last_update'] = datetime.now().isoformat()
        self.save('cache', cache)

storage = Storage()
