"""Управление данными бота (банк, история, статистика, кэш, история кэфов,
   ★ автоставки, ★ симуляции стратегий, ★ X2 матчи, ★ CLV-анализ, ★ LIVE-счёт)"""
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

    ★ Версия 4.0:
      - autobets.json     — виртуальные автоставки (с CLV и live-счётом)
      - simulations.json  — сохранённые симуляции стратегий
      - x2_matches.json   — X2 матчи
      - ★ NEW: live-счёт сохраняется отдельно от финального результата
    """

    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        self._locks = {
            'bank': threading.Lock(),
            'history': threading.Lock(),
            'stats': threading.Lock(),
            'cache': threading.Lock(),
            'odds_history': threading.Lock(),
            'autobets': threading.Lock(),
            'simulations': threading.Lock(),
            'x2_matches': threading.Lock(),
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
    # ИСТОРИЯ ★ ДОБАВЛЕНЫ LIVE-ПОЛЯ
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
            # ★ NEW: live-поля
            bet.setdefault('live_score', None)
            bet.setdefault('live_status', None)
            bet.setdefault('live_minute', None)
            bet.setdefault('live_halftime', None)
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
    # ИСТОРИЯ КЭФОВ
    # ============================================================
    def _odds_history_path(self):
        return self._path('odds_history')

    def save_odds_snapshot(self, fixture_id, market, selection, odds, bookmaker='—'):
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

                if snapshots:
                    last = snapshots[-1]
                    try:
                        last_ts = datetime.fromisoformat(last.get('ts', ''))
                        if (datetime.now() - last_ts).total_seconds() < 60:
                            return False
                    except Exception:
                        pass
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
        try:
            data = self._read('odds_history', {})
            fid_key = str(fixture_id)
            if fid_key not in data:
                return []
            entry = data[fid_key]
            if market and selection:
                return list(entry.get(str(market), {}).get(str(selection), []))
            if market:
                return {sel: list(vals) for sel, vals in entry.get(str(market), {}).items()}
            return entry
        except Exception as e:
            logger.error(f"❌ get_odds_history: {e}")
            return []

    def get_latest_odds_before(self, fixture_id, market, selection, before_iso):
        """★ CLV: последний снимок до указанного времени."""
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
                        break
                except Exception:
                    continue
            return latest
        except Exception as e:
            logger.error(f"❌ get_latest_odds_before: {e}")
            return None

    def get_entry_odds(self, fixture_id, market, selection):
        try:
            snapshots = self.get_odds_history(fixture_id, market, selection)
            return snapshots[0] if snapshots else None
        except Exception as e:
            logger.error(f"❌ get_entry_odds: {e}")
            return None

    def cleanup_old_odds_history(self, days=None):
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
    # СНИМКИ (плоский вид)
    # ============================================================
    def get_all_snapshots(self):
        try:
            data = self._read('odds_history', {})
            if not isinstance(data, dict):
                return []

            flat = []
            for fid_str, markets in data.items():
                try:
                    fid = int(fid_str)
                except (ValueError, TypeError):
                    fid = fid_str
                for market, selections in markets.items():
                    for selection, snapshots in selections.items():
                        for s in snapshots:
                            flat.append({
                                'fixture_id': fid,
                                'market': market,
                                'selection': selection,
                                'odds': s.get('odds', 0),
                                'bookmaker': s.get('bookmaker', '—'),
                                'created_at': s.get('ts', '')
                            })
            flat.sort(key=lambda x: x['created_at'], reverse=True)
            return flat
        except Exception as e:
            logger.error(f"❌ get_all_snapshots: {e}")
            return []

    def get_snapshots_since(self, cutoff_iso):
        try:
            all_snaps = self.get_all_snapshots()
            cutoff_clean = str(cutoff_iso).strip().replace(' ', 'T')
            if 'T' not in cutoff_clean:
                cutoff_clean += 'T00:00:00'

            result = []
            for s in all_snaps:
                created = str(s.get('created_at', '')).strip().replace(' ', 'T')
                if created and created >= cutoff_clean:
                    result.append(s)
            return result
        except Exception as e:
            logger.error(f"❌ get_snapshots_since: {e}")
            return []

    def get_snapshots_by_fixture(self, fixture_id):
        try:
            data = self._read('odds_history', {})
            if not isinstance(data, dict):
                return []

            fid_key = str(fixture_id)
            if fid_key not in data:
                return []

            flat = []
            for market, selections in data[fid_key].items():
                for selection, snapshots in selections.items():
                    for s in snapshots:
                        flat.append({
                            'fixture_id': fixture_id,
                            'market': market,
                            'selection': selection,
                            'odds': s.get('odds', 0),
                            'bookmaker': s.get('bookmaker', '—'),
                            'created_at': s.get('ts', '')
                        })
            flat.sort(key=lambda x: x['created_at'], reverse=False)
            return flat
        except Exception as e:
            logger.error(f"❌ get_snapshots_by_fixture: {e}")
            return []

    def get_unique_fixtures_with_snapshots(self, days=7):
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            snaps = self.get_snapshots_since(cutoff)
            return sorted(set(s['fixture_id'] for s in snaps), reverse=True)
        except Exception as e:
            logger.error(f"❌ get_unique_fixtures_with_snapshots: {e}")
            return []

    # ============================================================
    # ★ АВТОСТАВКИ (с CLV и LIVE-счётом)
    # ============================================================
    def autobet_load_all(self):
        data = self._read('autobets', [])
        return data if isinstance(data, list) else []

    def autobet_save_all(self, bets):
        with self._locks['autobets']:
            if not isinstance(bets, list):
                logger.error("❌ autobet_save_all: не список")
                return False
            self._backup('autobets')
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
                    'home': home,
                    'away': away,
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
                    # ★ CLV-поля
                    'closing_odds': None,
                    'clv': None,
                    'clv_updated': False,
                    # ★ NEW: LIVE-поля
                    'live_score': None,
                    'live_status': None,
                    'live_minute': None,
                    'live_home_goals': None,
                    'live_away_goals': None,
                    'live_halftime_home': None,
                    'live_halftime_away': None,
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
            wins = losses = pending = 0
            live_count = 0
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
                # ★ CLV
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
                'wins': wins,
                'losses': losses,
                'pending': pending,
                'live_count': live_count,   # ★ NEW: сколько матчей идёт прямо сейчас
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
            bets = self.autobet_load_all()
            return [b for b in bets if b.get('result') == 'pending']
        except Exception as e:
            logger.error(f"❌ autobet_get_pending: {e}")
            return []

    def autobet_get_pending_clv(self):
        """★ Возвращает автоставки, где результат уже есть, но CLV ещё не посчитан."""
        try:
            bets = self.autobet_load_all()
            return [b for b in bets if not b.get('clv_updated') and b.get('fixture_id')]
        except Exception as e:
            logger.error(f"❌ autobet_get_pending_clv: {e}")
            return []

    # ★★★ NEW: обновление LIVE-счёта (без финализации)
    def autobet_update_live(self, match_key, home_goals, away_goals,
                            status, minute, halftime_home=None, halftime_away=None):
        """
        Обновляет live-счёт автоставки БЕЗ финализации результата.
        Финальный result/profit НЕ трогаем.
        """
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
                        b['live_home_goals'] = home_goals
                        b['live_away_goals'] = away_goals
                        if halftime_home is not None:
                            b['live_halftime_home'] = halftime_home
                            b['live_halftime_away'] = halftime_away
                        updated = True
                        break

                if updated:
                    self._atomic_write('autobets', bets)
                return updated
            except Exception as e:
                logger.error(f"❌ autobet_update_live: {e}")
                return False

    def autobet_settle(self, match_key, result, profit,
                       home_goals=None, away_goals=None,
                       halftime_home=None, halftime_away=None):
        """Финализирует автоставку (после FT) и очищает live-поля."""
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
                        # ★ очищаем live-поля после финализации
                        b.pop('live_score', None)
                        b.pop('live_status', None)
                        b.pop('live_minute', None)
                        b.pop('live_home_goals', None)
                        b.pop('live_away_goals', None)
                        b.pop('live_halftime_home', None)
                        b.pop('live_halftime_away', None)
                        updated = True
                        break

                if updated:
                    self._atomic_write('autobets', bets)
                return updated
            except Exception as e:
                logger.error(f"❌ autobet_settle: {e}")
                return False

    def autobet_update_clv(self, match_key, closing_odds, clv):
        """★ Обновляет CLV для автоставки."""
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
                self._backup('autobets')
                self._atomic_write('autobets', [])
                return True
            except Exception as e:
                logger.error(f"❌ autobet_reset: {e}")
                return False

    # ============================================================
    # ★ СИМУЛЯЦИИ
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
    # X2 МАТЧИ
    # ============================================================
    def x2_load(self):
        data = self._read('x2_matches', [])
        return data if isinstance(data, list) else []

    def x2_save_all(self, matches):
        with self._locks['x2_matches']:
            if not isinstance(matches, list):
                logger.error("❌ x2_save_all: не список")
                return False
            self._backup('x2_matches')
            try:
                self._atomic_write('x2_matches', matches)
                return True
            except Exception as e:
                logger.error(f"❌ x2_save_all: {e}")
                return False

    def x2_count(self):
        try:
            return len(self.x2_load())
        except Exception as e:
            logger.error(f"❌ x2_count: {e}")
            return 0

    # ============================================================
    # БЭКАП
    # ============================================================
    def backup_all(self, backup_dir='backups'):
        try:
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(backup_dir, f'backup_{ts}')
            os.makedirs(dst, exist_ok=True)

            files = ('bank', 'history', 'stats', 'cache', 'odds_history',
                     'autobets', 'simulations', 'x2_matches')
            for name in files:
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
