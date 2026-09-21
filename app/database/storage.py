"""Управление данными бота (банк, история, статистика, кэш,
   ★ SQLite для снимков кэфов и X2-кандидатов,
   ★ автоставки с CLV, ★ симуляции стратегий)

★ Версия 4.3 — snapshots с home/away/league + авто-миграция
"""
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta

from app.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# ★ ОПРЕДЕЛЕНИЕ ПУТИ К ДИСКУ RENDER
# ============================================================
def _get_data_dir():
    """Возвращает путь к персистентному диску или локальной папке."""
    if os.path.exists('/data'):
        return '/data/storage'
    return 'data'


class Storage:
    """
    Хранилище с защитой от конкурентной записи.
    - JSON для редко меняющихся файлов (bank, history, stats, cache, autobets, simulations)
    - SQLite для снимков кэфов и X2-кандидатов (быстро, много записей)
    """

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or _get_data_dir()
        os.makedirs(self.data_dir, exist_ok=True)

        self._locks = {
            'bank': threading.Lock(),
            'history': threading.Lock(),
            'stats': threading.Lock(),
            'cache': threading.Lock(),
            'autobets': threading.Lock(),
            'simulations': threading.Lock(),
            'x2': threading.Lock(),
        }

        self._default_stats = {
            'total': 0, 'wins': 0, 'losses': 0, 'pushes': 0,
            'total_profit': 0, 'winrate': 0, 'roi': 0
        }

        self.ODDS_HISTORY_RETENTION_DAYS = 30

        # ★ SQLite
        self._odds_db_path = os.path.join(self.data_dir, 'odds_snapshots.db')
        self._x2_db_path = os.path.join(self.data_dir, 'x2_candidates.db')
        self._init_odds_db()
        self._init_x2_db()
        self._migrate_x2_db()

        logger.info(f"🗄️ Storage: {self.data_dir}")

    # ============================================================
    # ВНУТРЕННИЕ ХЕЛПЕРЫ (JSON)
    # ============================================================
    def _path(self, name):
        return os.path.join(self.data_dir, f'{name}.json')

    def _atomic_write(self, name, data):
        target = self._path(name)
        if os.path.exists(target):
            try:
                shutil.copy2(target, f"{target}.bak")
            except Exception as e:
                logger.warning(f"⚠️ Backup {name}: {e}")

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
                        data = json.load(f)
                        logger.warning(f"♻️ Восстановлено из {backup}")
                        return data
                except Exception:
                    pass
            return default
        except Exception as e:
            logger.error(f"❌ Ошибка чтения {name}.json: {e}")
            return default

    # ============================================================
    # SQLITE: СНИМКИ КЭФОВ
    # ============================================================
    def _init_odds_db(self):
        try:
            conn = sqlite3.connect(self._odds_db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER NOT NULL,
                    market TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    odds REAL NOT NULL,
                    bookmaker TEXT,
                    home TEXT DEFAULT '',
                    away TEXT DEFAULT '',
                    league TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_fixture ON snapshots(fixture_id);
                CREATE INDEX IF NOT EXISTS idx_created ON snapshots(created_at);
                CREATE INDEX IF NOT EXISTS idx_fix_market_sel
                    ON snapshots(fixture_id, market, selection);
            """)
            conn.commit()
            conn.close()
            # ★ Авто-миграция для старых БД
            self._migrate_odds_db()
        except Exception as e:
            logger.error(f"❌ _init_odds_db: {e}")

    def _migrate_odds_db(self):
        """★ Добавляет колонки home/away/league, если их нет."""
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(snapshots)")
            existing = {row[1] for row in cur.fetchall()}

            new_cols = {
                'home':   "TEXT DEFAULT ''",
                'away':   "TEXT DEFAULT ''",
                'league': "TEXT DEFAULT ''",
            }
            for col, definition in new_cols.items():
                if col not in existing:
                    try:
                        cur.execute(f"ALTER TABLE snapshots ADD COLUMN {col} {definition}")
                        logger.info(f"✅ Migration: added column '{col}' to snapshots")
                    except Exception as e:
                        logger.warning(f"⚠️ Migration {col}: {e}")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ _migrate_odds_db: {e}")

    def save_odds_snapshot(self, fixture_id, market, selection, odds,
                            bookmaker='—', home='', away='', league=''):
        """★ Сохраняет снимок с названиями команд/лиги."""
        if not fixture_id or not odds or odds <= 1.01:
            return False
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            cur = conn.cursor()

            # Антидубликат: если последний снимок <60 сек назад или та же цена
            cur.execute("""
                SELECT odds, created_at FROM snapshots
                WHERE fixture_id = ? AND market = ? AND selection = ?
                ORDER BY id DESC LIMIT 1
            """, (int(fixture_id), str(market), str(selection)))
            row = cur.fetchone()

            if row:
                last_odds, last_ts = row
                try:
                    last_dt = datetime.fromisoformat(str(last_ts))
                    if (datetime.now() - last_dt).total_seconds() < 60:
                        conn.close()
                        return False
                except Exception:
                    pass
                if abs(float(last_odds) - float(odds)) < 0.001:
                    conn.close()
                    return False

            cur.execute("""
                INSERT INTO snapshots
                (fixture_id, market, selection, odds, bookmaker,
                 home, away, league)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (int(fixture_id), str(market), str(selection),
                  round(float(odds), 3), str(bookmaker),
                  str(home or ''), str(away or ''), str(league or '')))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ save_odds_snapshot: {e}")
            return False

    def get_odds_history(self, fixture_id, market=None, selection=None):
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            if market and selection:
                cur.execute("""
                    SELECT odds, bookmaker, created_at AS ts
                    FROM snapshots
                    WHERE fixture_id = ? AND market = ? AND selection = ?
                    ORDER BY id ASC
                """, (int(fixture_id), str(market), str(selection)))
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                return rows

            cur.execute("""
                SELECT market, selection, odds, bookmaker, created_at AS ts
                FROM snapshots
                WHERE fixture_id = ?
                ORDER BY id ASC
            """, (int(fixture_id),))
            rows = cur.fetchall()
            conn.close()

            result = {}
            for r in rows:
                m = r['market']
                s = r['selection']
                result.setdefault(m, {}).setdefault(s, []).append({
                    'odds': r['odds'],
                    'bookmaker': r['bookmaker'],
                    'ts': r['ts'],
                })
            return result
        except Exception as e:
            logger.error(f"❌ get_odds_history: {e}")
            return {} if not (market and selection) else []

    # ============================================================
    # ★ COMPACT ODDS HISTORY для sparkline (Live)
    # ============================================================
    def get_odds_history_compact(self, fixture_id, market='1X2', selection='1',
                                   limit=10):
        """Компактная история: последние N точек с интервалом."""
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT odds, created_at
                FROM snapshots
                WHERE fixture_id = ? AND market = ? AND selection = ?
                ORDER BY id DESC
                LIMIT ?
            """, (int(fixture_id), str(market), str(selection), int(limit * 3)))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            if not rows:
                return []

            rows = list(reversed(rows))

            if len(rows) > limit:
                step = len(rows) / limit
                sampled = []
                for i in range(limit):
                    idx = int(i * step)
                    sampled.append(rows[idx])
                sampled.append(rows[-1])
                rows = sampled

            return [{'odds': r['odds'], 'ts': r['created_at']} for r in rows]
        except Exception as e:
            logger.error(f"❌ get_odds_history_compact: {e}")
            return []

    def get_odds_history_batch(self, fixture_ids, market='1X2',
                                 selection='1', limit=10):
        """Batch: компактная история для нескольких матчей одним запросом."""
        if not fixture_ids:
            return {}
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            placeholders = ','.join(['?'] * len(fixture_ids))
            cur.execute(f"""
                SELECT fixture_id, odds, created_at
                FROM snapshots
                WHERE fixture_id IN ({placeholders}) AND market = ? AND selection = ?
                ORDER BY fixture_id, id ASC
            """, (*[int(f) for f in fixture_ids], str(market), str(selection)))

            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            grouped = {}
            for r in rows:
                fid = r['fixture_id']
                grouped.setdefault(fid, []).append({
                    'odds': r['odds'],
                    'ts': r['created_at']
                })

            result = {}
            for fid, points in grouped.items():
                if len(points) > limit:
                    step = len(points) / limit
                    sampled = []
                    for i in range(limit):
                        idx = int(i * step)
                        sampled.append(points[idx])
                    sampled.append(points[-1])
                    result[fid] = sampled
                else:
                    result[fid] = points
            return result
        except Exception as e:
            logger.error(f"❌ get_odds_history_batch: {e}")
            return {}

    def get_latest_odds_before(self, fixture_id, market, selection, before_iso):
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                SELECT odds, bookmaker, created_at
                FROM snapshots
                WHERE fixture_id = ? AND market = ? AND selection = ?
                  AND created_at <= ?
                ORDER BY id DESC LIMIT 1
            """, (int(fixture_id), str(market), str(selection), str(before_iso)))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            return {'odds': row[0], 'bookmaker': row[1], 'ts': row[2]}
        except Exception as e:
            logger.error(f"❌ get_latest_odds_before: {e}")
            return None

    def get_entry_odds(self, fixture_id, market, selection):
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                SELECT odds, bookmaker, created_at
                FROM snapshots
                WHERE fixture_id = ? AND market = ? AND selection = ?
                ORDER BY id ASC LIMIT 1
            """, (int(fixture_id), str(market), str(selection)))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            return {'odds': row[0], 'bookmaker': row[1], 'ts': row[2]}
        except Exception as e:
            logger.error(f"❌ get_entry_odds: {e}")
            return None

    def cleanup_old_odds_history(self, days=None):
        days = days or self.ODDS_HISTORY_RETENTION_DAYS
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=30)
            cur = conn.cursor()
            cur.execute("DELETE FROM snapshots WHERE created_at < ?", (cutoff,))
            removed = cur.rowcount
            conn.commit()
            conn.close()
            if removed > 0:
                logger.info(f"🧹 Удалено {removed} устаревших снимков")
            return removed
        except Exception as e:
            logger.error(f"❌ cleanup_old_odds_history: {e}")
            return 0

    def get_odds_history_size(self):
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(DISTINCT fixture_id) FROM snapshots")
            matches = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM snapshots")
            snapshots = cur.fetchone()[0] or 0
            conn.close()
            size_kb = os.path.getsize(self._odds_db_path) / 1024 if os.path.exists(self._odds_db_path) else 0
            return {
                'matches': matches,
                'snapshots': snapshots,
                'size_kb': round(size_kb, 1),
            }
        except Exception as e:
            logger.error(f"❌ get_odds_history_size: {e}")
            return {'matches': 0, 'snapshots': 0, 'size_kb': 0}

    def get_all_snapshots(self):
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT fixture_id, market, selection, odds, bookmaker,
                       home, away, league, created_at
                FROM snapshots
                ORDER BY id DESC
            """)
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"❌ get_all_snapshots: {e}")
            return []

    def get_snapshots_since(self, cutoff_iso):
        try:
            cutoff_clean = str(cutoff_iso).strip().replace(' ', 'T')
            if 'T' not in cutoff_clean:
                cutoff_clean += 'T00:00:00'
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT fixture_id, market, selection, odds, bookmaker,
                       home, away, league, created_at
                FROM snapshots
                WHERE created_at >= ?
                ORDER BY id DESC
            """, (cutoff_clean,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"❌ get_snapshots_since: {e}")
            return []

    def get_snapshots_by_fixture(self, fixture_id):
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT market, selection, odds, bookmaker,
                       home, away, league, created_at
                FROM snapshots
                WHERE fixture_id = ?
                ORDER BY id ASC
            """, (int(fixture_id),))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"❌ get_snapshots_by_fixture: {e}")
            return []

    def get_unique_fixtures_with_snapshots(self, days=7):
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT fixture_id FROM snapshots
                WHERE created_at >= ?
                ORDER BY fixture_id DESC
            """, (cutoff,))
            ids = [r[0] for r in cur.fetchall()]
            conn.close()
            return ids
        except Exception as e:
            logger.error(f"❌ get_unique_fixtures_with_snapshots: {e}")
            return []

    def get_snapshot_match_info(self, fixture_id):
        """★ Возвращает home/away/league для матча из снимков."""
        try:
            conn = sqlite3.connect(self._odds_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT home, away, league FROM snapshots
                WHERE fixture_id = ? AND (home != '' OR away != '' OR league != '')
                ORDER BY id DESC LIMIT 1
            """, (int(fixture_id),))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            return {
                'home': row['home'] or '',
                'away': row['away'] or '',
                'league': row['league'] or '',
            }
        except Exception as e:
            logger.error(f"❌ get_snapshot_match_info: {e}")
            return None

    # ============================================================
    # SQLITE: X2-КАНДИДАТЫ
    # ============================================================
    def _init_x2_db(self):
        try:
            conn = sqlite3.connect(self._x2_db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS x2_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    home TEXT NOT NULL,
                    away TEXT NOT NULL,
                    match_time TEXT NOT NULL,
                    favorite TEXT,
                    underdog TEXT,
                    x2_side TEXT,
                    x2_ev REAL,
                    x2_prob REAL,
                    home_position INTEGER,
                    away_position INTEGER,
                    league TEXT,
                    fixture_id INTEGER,
                    home_form TEXT,
                    away_form TEXT,
                    total_xg REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(home, away, match_time)
                );
                CREATE INDEX IF NOT EXISTS idx_x2_created
                    ON x2_candidates(created_at DESC);
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ _init_x2_db: {e}")

    def _migrate_x2_db(self):
        """★ Добавляет новые колонки если их нет."""
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(x2_candidates)")
            existing = {row[1] for row in cur.fetchall()}

            new_cols = {
                'entry_odds': 'REAL DEFAULT 0',
                'entry_1x_odds': 'REAL DEFAULT 0',
                'result': "TEXT DEFAULT 'pending'",
                'profit': 'REAL DEFAULT 0',
                'home_goals': 'INTEGER',
                'away_goals': 'INTEGER',
                'settled_at': 'TIMESTAMP',
            }
            for col, definition in new_cols.items():
                if col not in existing:
                    try:
                        cur.execute(f"ALTER TABLE x2_candidates ADD COLUMN {col} {definition}")
                        logger.info(f"✅ Migration: added column '{col}' to x2_candidates")
                    except Exception as e:
                        logger.warning(f"⚠️ Migration {col}: {e}")

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ _migrate_x2_db: {e}")

    def save_x2_candidate(self, home, away, hp, ap, league_name, match_time,
                          fixture_id, home_form='', away_form='', total_xg=0,
                          x2_side='X2', x2_ev=0, x2_prob=0,
                          entry_odds=0, entry_1x_odds=0):
        try:
            if hp < ap:
                favorite, underdog = home, away
            else:
                favorite, underdog = away, home

            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO x2_candidates
                    (home, away, match_time, favorite, underdog, x2_side,
                     x2_ev, x2_prob, home_position, away_position, league,
                     fixture_id, home_form, away_form, total_xg,
                     entry_odds, entry_1x_odds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (home, away, match_time, favorite, underdog, x2_side,
                      round(x2_ev, 1), round(x2_prob, 1), hp, ap,
                      league_name, fixture_id, home_form, away_form,
                      round(total_xg, 2) if total_xg else 0,
                      round(entry_odds, 3) if entry_odds else 0,
                      round(entry_1x_odds, 3) if entry_1x_odds else 0))
                conn.commit()
                conn.close()
                return True
            except sqlite3.IntegrityError:
                conn.close()
                return False
        except Exception as e:
            logger.error(f"❌ save_x2_candidate: {e}")
            return False

    def get_x2_candidates(self, limit=500):
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM x2_candidates
                ORDER BY id DESC LIMIT ?
            """, (int(limit),))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return list(reversed(rows))
        except Exception as e:
            logger.error(f"❌ get_x2_candidates: {e}")
            return []

    def get_x2_candidate_by_id(self, candidate_id):
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM x2_candidates WHERE id=?", (int(candidate_id),))
            row = cur.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ get_x2_candidate_by_id: {e}")
            return None

    def update_x2_result(self, candidate_id, result, profit, home_goals, away_goals):
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                UPDATE x2_candidates
                SET result=?, profit=?, home_goals=?, away_goals=?, settled_at=?
                WHERE id=?
            """, (result, float(profit), home_goals, away_goals,
                  datetime.now().isoformat(), int(candidate_id)))
            updated = cur.rowcount
            conn.commit()
            conn.close()
            return updated > 0
        except Exception as e:
            logger.error(f"❌ update_x2_result: {e}")
            return False

    def update_x2_entry_odds(self, candidate_id, entry_odds, entry_1x_odds=None):
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            cur = conn.cursor()
            if entry_1x_odds is not None:
                cur.execute("""
                    UPDATE x2_candidates
                    SET entry_odds=?, entry_1x_odds=?
                    WHERE id=? AND (entry_odds IS NULL OR entry_odds=0)
                """, (round(entry_odds, 3), round(entry_1x_odds, 3), int(candidate_id)))
            else:
                cur.execute("""
                    UPDATE x2_candidates
                    SET entry_odds=?
                    WHERE id=? AND (entry_odds IS NULL OR entry_odds=0)
                """, (round(entry_odds, 3), int(candidate_id)))
            updated = cur.rowcount
            conn.commit()
            conn.close()
            return updated > 0
        except Exception as e:
            logger.error(f"❌ update_x2_entry_odds: {e}")
            return False

    def clear_x2_candidates(self):
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("DELETE FROM x2_candidates")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ clear_x2_candidates: {e}")
            return False

    def x2_count(self):
        try:
            conn = sqlite3.connect(self._x2_db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM x2_candidates")
            n = cur.fetchone()[0] or 0
            conn.close()
            return n
        except Exception as e:
            logger.error(f"❌ x2_count: {e}")
            return 0

    # ============================================================
    # БАНК
    # ============================================================
    def load_bank(self):
        data = self._read('bank', {})
        return data.get('bank', 1000.0)

    def save_bank(self, bank):
        with self._locks['bank']:
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
            bet.setdefault('prob', 0)
            bet.setdefault('halftime_home', None)
            bet.setdefault('halftime_away', None)
            normalized.append(bet)
        return normalized

    def save_history(self, history):
        with self._locks['history']:
            if not isinstance(history, list):
                logger.error("❌ save_history: не список, пропускаю")
                return
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
    # АВТОСТАВКИ
    # ============================================================
    def autobet_load_all(self):
        data = self._read('autobets', [])
        return data if isinstance(data, list) else []

    def autobet_save_all(self, bets):
        with self._locks['autobets']:
            if not isinstance(bets, list):
                logger.error("❌ autobet_save_all: не список")
                return False
            try:
                self._atomic_write('autobets', bets)
                return True
            except Exception as e:
                logger.error(f"❌ autobet_save_all: {e}")
                return False

    def autobet_insert(self, match_key, home, away, league, match_time,
                       fixture_id, bet_label, bet_type, odds, stake,
                       ev, prob, bookmaker):
        with self._locks['autobets']:
            try:
                bets = self._read('autobets', [])
                if not isinstance(bets, list):
                    bets = []

                for b in bets:
                    if b.get('match_key') == match_key:
                        return False

                bets.append({
                    'id': len(bets) + 1,
                    'match_key': match_key,
                    'home': home, 'away': away,
                    'league': league,
                    'match_time': match_time,
                    'fixture_id': fixture_id,
                    'bet_label': bet_label,
                    'bet_type': bet_type,
                    'odds': float(odds),
                    'stake': float(stake),
                    'ev': float(ev),
                    'prob': float(prob),
                    'bookmaker': bookmaker,
                    'result': 'pending',
                    'profit': 0,
                    'home_goals': None,
                    'away_goals': None,
                    'halftime_home': None,
                    'halftime_away': None,
                    'closing_odds': None,
                    'clv': None,
                    'clv_updated': False,
                    'created_at': datetime.now().isoformat(timespec='seconds'),
                    'settled_at': None,
                })
                self._atomic_write('autobets', bets)
                return True
            except Exception as e:
                logger.error(f"❌ autobet_insert: {e}")
                return False

    def autobet_get_state(self, default_bank=1000.0):
        try:
            bets = self.autobet_load_all()
            total_staked = 0.0
            total_profit = 0.0
            wins = losses = pending = live_count = 0
            clv_values = []

            for b in bets:
                total_staked += float(b.get('stake', 0) or 0)
                total_profit += float(b.get('profit', 0) or 0)
                r = b.get('result', 'pending')
                if r == 'win':
                    wins += 1
                elif r == 'loss':
                    losses += 1
                elif r == 'pending':
                    pending += 1
                    if b.get('live_score'):
                        live_count += 1
                clv = b.get('clv')
                if clv is not None:
                    clv_values.append(clv)

            total_bets = len(bets)
            current_bank = default_bank + total_profit
            roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
            winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            avg_clv = (sum(clv_values) / len(clv_values)) if clv_values else 0

            return {
                'bank': round(current_bank, 2),
                'start_bank': default_bank,
                'total_profit': round(total_profit, 2),
                'total_staked': round(total_staked, 2),
                'total_bets': total_bets,
                'wins': wins, 'losses': losses,
                'pending': pending, 'live_count': live_count,
                'roi': round(roi, 1),
                'winrate': round(winrate, 1),
                'avg_clv': round(avg_clv, 2),
                'clv_count': len(clv_values),
            }
        except Exception as e:
            logger.error(f"❌ autobet_get_state: {e}")
            return {
                'bank': default_bank, 'start_bank': default_bank,
                'total_profit': 0, 'total_staked': 0, 'total_bets': 0,
                'wins': 0, 'losses': 0, 'pending': 0, 'live_count': 0,
                'roi': 0, 'winrate': 0, 'avg_clv': 0, 'clv_count': 0,
            }

    def autobet_get_history(self, limit=100):
        try:
            bets = self.autobet_load_all()
            bets_sorted = sorted(bets, key=lambda x: x.get('created_at', ''), reverse=True)
            return bets_sorted[:limit]
        except Exception as e:
            logger.error(f"❌ autobet_get_history: {e}")
            return []

    def autobet_get_pending(self):
        try:
            return [b for b in self.autobet_load_all() if b.get('result') == 'pending']
        except Exception as e:
            logger.error(f"❌ autobet_get_pending: {e}")
            return []

    def autobet_get_pending_clv(self):
        try:
            return [b for b in self.autobet_load_all()
                    if not b.get('clv_updated') and b.get('fixture_id')]
        except Exception as e:
            logger.error(f"❌ autobet_get_pending_clv: {e}")
            return []

    def autobet_settle(self, match_key, result, profit,
                       home_goals=None, away_goals=None,
                       halftime_home=None, halftime_away=None):
        with self._locks['autobets']:
            try:
                bets = self._read('autobets', [])
                if not isinstance(bets, list):
                    return False
                updated = False
                for b in bets:
                    if b.get('match_key') == match_key and b.get('result') == 'pending':
                        b['result'] = result
                        b['profit'] = float(profit)
                        b['home_goals'] = home_goals
                        b['away_goals'] = away_goals
                        b['halftime_home'] = halftime_home
                        b['halftime_away'] = halftime_away
                        b['settled_at'] = datetime.now().isoformat(timespec='seconds')
                        for k in ('live_score', 'live_status', 'live_minute', 'live_halftime'):
                            b.pop(k, None)
                        updated = True
                        break
                if updated:
                    self._atomic_write('autobets', bets)
                return updated
            except Exception as e:
                logger.error(f"❌ autobet_settle: {e}")
                return False

    def autobet_update_live(self, match_key, home_goals, away_goals,
                            status, minute, halftime_home=None, halftime_away=None):
        with self._locks['autobets']:
            try:
                bets = self._read('autobets', [])
                if not isinstance(bets, list):
                    return False
                updated = False
                for b in bets:
                    if b.get('match_key') == match_key and b.get('result') == 'pending':
                        b['live_score'] = f"{home_goals}-{away_goals}"
                        b['live_status'] = status
                        b['live_minute'] = minute
                        if halftime_home is not None and halftime_away is not None:
                            b['live_halftime'] = f"{halftime_home}-{halftime_away}"
                        updated = True
                        break
                if updated:
                    self._atomic_write('autobets', bets)
                return updated
            except Exception as e:
                logger.error(f"❌ autobet_update_live: {e}")
                return False

    def autobet_update_clv(self, match_key, closing_odds, clv):
        with self._locks['autobets']:
            try:
                bets = self._read('autobets', [])
                if not isinstance(bets, list):
                    return False
                updated = False
                for b in bets:
                    if b.get('match_key') == match_key:
                        b['closing_odds'] = float(closing_odds) if closing_odds else None
                        b['clv'] = float(clv) if clv is not None else None
                        b['clv_updated'] = True
                        updated = True
                        break
                if updated:
                    self._atomic_write('autobets', bets)
                return updated
            except Exception as e:
                logger.error(f"❌ autobet_update_clv: {e}")
                return False

    def autobet_reset(self):
        with self._locks['autobets']:
            try:
                self._atomic_write('autobets', [])
                return True
            except Exception as e:
                logger.error(f"❌ autobet_reset: {e}")
                return False

    # ============================================================
    # СИМУЛЯЦИИ
    # ============================================================
    def save_simulation(self, name, params, result):
        with self._locks['simulations']:
            try:
                sims = self._read('simulations', [])
                if not isinstance(sims, list):
                    sims = []
                sims.append({
                    'id': len(sims) + 1,
                    'name': name,
                    'params': params,
                    'total_bets': result.get('total_bets', 0),
                    'wins': result.get('wins', 0),
                    'losses': result.get('losses', 0),
                    'pushes': result.get('pushes', 0),
                    'profit': result.get('profit', 0),
                    'roi': result.get('roi', 0),
                    'winrate': result.get('winrate', 0),
                    'max_drawdown': result.get('max_drawdown', 0),
                    'created_at': datetime.now().isoformat(timespec='seconds'),
                })
                self._atomic_write('simulations', sims)
                return True
            except Exception as e:
                logger.error(f"❌ save_simulation: {e}")
                return False

    def get_simulations(self, limit=50):
        try:
            sims = self._read('simulations', [])
            if not isinstance(sims, list):
                return []
            sims_sorted = sorted(sims, key=lambda x: x.get('created_at', ''), reverse=True)
            return sims_sorted[:limit]
        except Exception as e:
            logger.error(f"❌ get_simulations: {e}")
            return []

    # ============================================================
    # БЭКАП
    # ============================================================
    def backup_all(self, backup_dir=None):
        try:
            backup_dir = backup_dir or (
                '/data/backups' if os.path.exists('/data') else 'backups'
            )
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(backup_dir, f'backup_{ts}')
            os.makedirs(dst, exist_ok=True)

            files = ('bank', 'history', 'stats', 'cache',
                     'autobets', 'simulations')
            for name in files:
                src = self._path(name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dst, f'{name}.json'))

            # ★ Безопасный бэкап SQLite через .backup()
            for db_path in (self._odds_db_path, self._x2_db_path):
                if os.path.exists(db_path):
                    try:
                        src_conn = sqlite3.connect(db_path)
                        dst_conn = sqlite3.connect(os.path.join(dst, os.path.basename(db_path)))
                        src_conn.backup(dst_conn)
                        dst_conn.close()
                        src_conn.close()
                    except Exception as e:
                        logger.warning(f"⚠️ Бэкап {db_path}: {e}")
                        # Fallback — обычное копирование
                        try:
                            shutil.copy2(db_path, os.path.join(dst, os.path.basename(db_path)))
                        except Exception:
                            pass

            logger.info(f"💾 Бэкап: {dst}")
            return dst
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа: {e}")
            return None


# ============================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ============================================================
storage = Storage()
