"""Управление данными бота (банк, история, статистика, кэш)"""
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime

from app.utils.logger import get_logger

logger = get_logger(__name__)


class Storage:
    """
    Хранилище JSON с защитой от конкурентной записи и битых файлов.
    Атомарная запись через tempfile + os.replace().
    """

    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        # Блокировки на каждый файл — Flask + APScheduler + фоновые потоки
        self._locks = {
            'bank': threading.Lock(),
            'history': threading.Lock(),
            'stats': threading.Lock(),
            'cache': threading.Lock(),
        }

        self._default_stats = {
            'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0,
            'total_profit': 0, 'winrate': 0, 'roi': 0
        }

    # ============================================================
    # ВНУТРЕННИЕ ХЕЛПЕРЫ
    # ============================================================
    def _path(self, name):
        return os.path.join(self.data_dir, f'{name}.json')

    def _atomic_write(self, name, data):
        """Пишет JSON во временный файл и атомарно подменяет целевой."""
        target = self._path(name)
        fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, target)
        except Exception as e:
            logger.error(f"❌ Ошибка записи {name}.json: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def _read(self, name, default):
        """Читает JSON, при ошибке — возвращает default и логирует."""
        path = self._path(name)
        if not os.path.exists(path):
            return default
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Битый JSON в {name}.json: {e}")
            backup = f"{path}.bak"
            if os.path.exists(backup):
                try:
                    with open(backup, 'r', encoding='utf-8') as f:
                        logger.warning(f"♻️ Восстановлено из {backup}")
                        return json.load(f)
                except Exception:
                    pass
            return default
        except Exception as e:
            logger.error(f"❌ Ошибка чтения {name}.json: {e}")
            return default

    def _backup(self, name):
        """Создаёт .bak-копию перед перезаписью."""
        path = self._path(name)
        if os.path.exists(path):
            try:
                shutil.copy2(path, f"{path}.bak")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось создать бэкап {name}: {e}")

    # ============================================================
    # БАНК
    # ============================================================
    def load_bank(self):
        data = self._read('bank', {})
        return data.get('bank', 1000.0)

    def save_bank(self, bank):
        with self._locks['bank']:
            self._backup('bank')
            self._atomic_write('bank', {
                'bank': float(bank),
                'updated': datetime.now().isoformat()
            })

    # ============================================================
    # ИСТОРИЯ
    # ============================================================
    def load_history(self):
        history = self._read('history', [])
        if not isinstance(history, list):
            logger.error("❌ history.json — не список, возвращаю []")
            return []
        # Нормализация — добавляем недостающие поля
        normalized = []
        for bet in history:
            if not isinstance(bet, dict):
                continue
            bet.setdefault('bet', '—')
            bet.setdefault('odds', 0)
            bet.setdefault('stake', 0)
            bet.setdefault('ev', 0)
            bet.setdefault('result', 'pending')
            bet.setdefault('profit', 0)
            bet.setdefault('bookmaker', '—')
            bet.setdefault('engine', None)
            bet.setdefault('weather_reason', None)
            normalized.append(bet)
        return normalized

    def save_history(self, history):
        with self._locks['history']:
            if not isinstance(history, list):
                logger.error("❌ save_history: не список, пропускаю")
                return
            self._backup('history')
            self._atomic_write('history', history)

    # ============================================================
    # СТАТИСТИКА
    # ============================================================
    def load_stats(self):
        data = self._read('stats', {})
        stats = dict(self._default_stats)
        stats.update(data or {})
        return stats

    def save_stats(self, stats):
        with self._locks['stats']:
            self._backup('stats')
            self._atomic_write('stats', stats)

    # ============================================================
    # КЭШ
    # ============================================================
    def load_cache(self):
        data = self._read('cache', {})
        return data if isinstance(data, dict) else {}

    def save_cache(self, cache):
        with self._locks['cache']:
            if not isinstance(cache, dict):
                logger.error("❌ save_cache: не словарь, пропускаю")
                return
            self._atomic_write('cache', cache)

    # ============================================================
    # ПОЛНЫЙ БЭКАП
    # ============================================================
    def backup_all(self, backup_dir='backups'):
        """Полный бэкап всех JSON-файлов с таймштампом."""
        try:
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(backup_dir, f'backup_{ts}')
            os.makedirs(dst, exist_ok=True)
            for name in ('bank', 'history', 'stats', 'cache'):
                src = self._path(name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dst, f'{name}.json'))
            logger.info(f"💾 Бэкап: {dst}")
            return dst
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа: {e}")
            return None


# ============================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ============================================================
storage = Storage()
