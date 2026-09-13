"""Управление данными бота (банк, история, статистика, кэш, история кэфов)"""
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timedelta

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
            'odds_history': threading.Lock(),
        }

        self._default_stats = {
            'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0,
            'total_profit': 0, 'winrate': 0, 'roi': 0
        }

        self.ODDS_HISTORY_RETENTION_DAYS = 30

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
    # ★ NEW: ИСТОРИЯ КЭФОВ (для line movement и CLV)
    # ============================================================
    def _odds_history_path(self):
        return self._path('odds_history')

    def save_odds_snapshot(self, fixture_id, market, selection, odds, bookmaker='—'):
        """
        Сохраняет снимок кэфа в odds_history.json.
        Структура файла:
        {
          "fixture_id": {
             "1X2": {
                "1": [{"odds": 1.80, "bookmaker": "Pinnacle", "ts": "2026-09-13T14:30:00"}, ...],
                "X": [...],
                "2": [...]
             },
             "BTTS": { ... }
          }
        }
        """
        if not fixture_id or not odds or odds <= 1.01:
            return False

        with self._locks['odds_history']:
            try:
                data = self._read('odds_history', {})
                if not isinstance(data, dict):
                    data = {}

                fid_key = str(fixture_id)
                market_key = str(market)
                selection_key = str(selection)

                data.setdefault(fid_key, {})
                data[fid_key].setdefault(market_key, {})
                data[fid_key][market_key].setdefault(selection_key, [])

                snapshots = data[fid_key][market_key][selection_key]
                ts_now = datetime.now().isoformat(timespec='seconds')

                # Не пишем дубли в течение 60 секунд (защита от двойных вызовов)
                if snapshots:
                    last = snapshots[-1]
                    try:
                        last_ts = datetime.fromisoformat(last.get('ts', ''))
                        if (datetime.now() - last_ts).total_seconds() < 60:
                            return False
                    except Exception:
                        pass
                    # Если кэф не изменился с последнего раза — тоже не пишем
                    if abs(last.get('odds', 0) - odds) < 0.001:
                        return False

                snapshots.append({
                    'odds': round(float(odds), 3),
                    'bookmaker': bookmaker,
                    'ts': ts_now
                })

                self._atomic_write('odds_history', data)
                return True
            except Exception as e:
                logger.error(f"❌ save_odds_snapshot: {e}")
                return False

    def get_odds_history(self, fixture_id, market=None, selection=None):
        """Возвращает список снимков кэфа (в порядке времени)."""
        try:
            data = self._read('odds_history', {})
            fid_key = str(fixture_id)
            if fid_key not in data:
                return []

            entry = data[fid_key]

            # Фильтр по market/selection, если заданы
            if market and selection:
                return list(entry.get(str(market), {}).get(str(selection), []))
            if market:
                return {sel: list(vals) for sel, vals in entry.get(str(market), {}).items()}

            # Всё по матчу
            return entry
        except Exception as e:
            logger.error(f"❌ get_odds_history: {e}")
            return []

    def get_latest_odds_before(self, fixture_id, market, selection, before_iso):
        """
        Последний снимок кэфа ДО указанного времени.
        Используется для CLV — берём кэф за 10-15 минут до старта.
        """
        try:
            snapshots = self.get_odds_history(fixture_id, market, selection)
            if not snapshots:
                return None

            try:
                before_dt = datetime.fromisoformat(before_iso)
            except Exception:
                return None

            latest = None
            for s in snapshots:
                try:
                    ts = datetime.fromisoformat(s.get('ts', ''))
                    if ts <= before_dt:
                        latest = s
                    else:
                        break  # снимки отсортированы по времени
                except Exception:
                    continue
            return latest
        except Exception as e:
            logger.error(f"❌ get_latest_odds_before: {e}")
            return None

    def get_entry_odds(self, fixture_id, market, selection):
        """Первый снимок кэфа — то, что «взяли» изначально."""
        try:
            snapshots = self.get_odds_history(fixture_id, market, selection)
            return snapshots[0] if snapshots else None
        except Exception as e:
            logger.error(f"❌ get_entry_odds: {e}")
            return None

    def cleanup_old_odds_history(self, days=None):
        """Удаляет снимки старше N дней. Также чистит пустые матчи."""
        days = days or self.ODDS_HISTORY_RETENTION_DAYS
        cutoff = datetime.now() - timedelta(days=days)

        with self._locks['odds_history']:
            try:
                data = self._read('odds_history', {})
                if not isinstance(data, dict):
                    return 0

                removed = 0
                cleaned = {}

                for fid, markets in data.items():
                    new_markets = {}
                    for market, selections in markets.items():
                        new_selections = {}
                        for sel, snapshots in selections.items():
                            kept = []
                            for s in snapshots:
                                try:
                                    ts = datetime.fromisoformat(s.get('ts', ''))
                                    if ts >= cutoff:
                                        kept.append(s)
                                    else:
                                        removed += 1
                                except Exception:
                                    kept.append(s)
                            if kept:
                                new_selections[sel] = kept
                        if new_selections:
                            new_markets[market] = new_selections
                    if new_markets:
                        cleaned[fid] = new_markets

                self._atomic_write('odds_history', cleaned)

                if removed > 0:
                    logger.info(f"🧹 Удалено {removed} устаревших снимков кэфов")
                return removed
            except Exception as e:
                logger.error(f"❌ cleanup_old_odds_history: {e}")
                return 0

    def get_odds_history_size(self):
        """Размер истории — сколько матчей, сколько снимков."""
        try:
            data = self._read('odds_history', {})
            if not isinstance(data, dict):
                return {'matches': 0, 'snapshots': 0, 'size_kb': 0}

            matches = len(data)
            snapshots = 0
            for markets in data.values():
                for selections in markets.values():
                    for snaps in selections.values():
                        snapshots += len(snaps)

            path = self._odds_history_path()
            size_kb = os.path.getsize(path) / 1024 if os.path.exists(path) else 0

            return {
                'matches': matches,
                'snapshots': snapshots,
                'size_kb': round(size_kb, 1)
            }
        except Exception as e:
            logger.error(f"❌ get_odds_history_size: {e}")
            return {'matches': 0, 'snapshots': 0, 'size_kb': 0}

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
            for name in ('bank', 'history', 'stats', 'cache', 'odds_history'):
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
