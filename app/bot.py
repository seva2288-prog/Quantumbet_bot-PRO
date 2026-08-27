import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
import time
import os
import json
from datetime import datetime, timedelta
import signal
import requests
import sqlite3
from functools import lru_cache
import re
import threading
from queue import Queue
import hashlib

from app.config import Config
from app.database.storage import storage
from app.api.football import football_api
from app.api.weather import weather_api
from app.analytics.xg import xg_analyzer
from app.analytics.probability import calculate_probabilities, calculate_ev, get_bet_types, predict_half_goals, predict_exact_score, predict_corners, predict_yellow_cards
from app.analytics.arbitrage import arbitrage_analyzer
from app.analytics.anomalies import anomaly_detector
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.ml.predictor import ml_predictor
from app.betting.auto_bet import auto_bet
from app.scheduler import start_scheduler
from app.security.auth import security

logger = get_logger(__name__)
app = Flask(__name__)

# ===== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====
search_running = False
last_update_time = None
last_update_lock = threading.Lock()
request_cache = {}
cache_lock = threading.Lock()

# ===== КОНСТАНТЫ =====
TIMEZONE_OFFSET = Config.TIMEZONE_OFFSET if hasattr(Config, 'TIMEZONE_OFFSET') else 3
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
CACHE_TTL = 300  # 5 минут

# ===== КЛАСС ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ =====
class Database:
    def __init__(self, db_path='data/bot.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица ставок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER,
                home TEXT,
                away TEXT,
                league TEXT,
                bet_type TEXT,
                odds REAL,
                stake REAL,
                ev REAL,
                result TEXT,
                profit REAL,
                date TEXT,
                home_goals INTEGER,
                away_goals INTEGER,
                match_time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица статистики
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Таблица кэша
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at TIMESTAMP
            )
        ''')
        
        # Индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_date ON bets(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_result ON bets(result)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_fixture ON bets(fixture_id)')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
    
    def save_bet(self, bet_data):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bets (
                fixture_id, home, away, league, bet_type, odds, stake, ev, 
                result, profit, date, home_goals, away_goals, match_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            bet_data.get('fixture_id'),
            bet_data.get('home'),
            bet_data.get('away'),
            bet_data.get('league'),
            bet_data.get('bet_type'),
            bet_data.get('odds'),
            bet_data.get('stake'),
            bet_data.get('ev'),
            bet_data.get('result', 'pending'),
            bet_data.get('profit', 0),
            bet_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M')),
            bet_data.get('home_goals'),
            bet_data.get('away_goals'),
            bet_data.get('match_time')
        ))
        
        conn.commit()
        bet_id = cursor.lastrowid
        conn.close()
        return bet_id
    
    def get_all_bets(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bets ORDER BY id DESC')
        bets = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return bets
    
    def get_stats(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
                COALESCE(SUM(profit), 0) as total_profit,
                COALESCE(SUM(stake), 0) as total_stake
            FROM bets
        ''')
        
        stats = dict(cursor.fetchone())
        conn.close()
        
        stats['winrate'] = round(
            stats['wins'] / (stats['wins'] + stats['losses']) * 100, 1
        ) if (stats['wins'] + stats['losses']) > 0 else 0
        
        stats['roi'] = round(
            (stats['total_profit'] / stats['total_stake'] * 100), 1
        ) if stats['total_stake'] > 0 else 0
        
        return stats
    
    def update_bet_result(self, bet_id, result, profit, home_goals=None, away_goals=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE bets 
            SET result = ?, profit = ?, home_goals = ?, away_goals = ?
            WHERE id = ?
        ''', (result, profit, home_goals, away_goals, bet_id))
        
        conn.commit()
        conn.close()
    
    def get_cached(self, key):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value, expires_at FROM cache WHERE key = ?
        ''', (key,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            expires_at = datetime.fromisoformat(row['expires_at'])
            if datetime.now() < expires_at:
                return json.loads(row['value'])
        return None
    
    def set_cached(self, key, value, ttl=CACHE_TTL):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        expires_at = (datetime.now() + timedelta(seconds=ttl)).isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO cache (key, value, expires_at)
            VALUES (?, ?, ?)
        ''', (key, json.dumps(value), expires_at))
        
        conn.commit()
        conn.close()

# ===== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ =====
db = Database()

# ===== ДЕКОРАТОР ДЛЯ ТАЙМАУТОВ =====
class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError()

def with_timeout(seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator

# ===== БЕЗОПАСНОЕ ПОЛУЧЕНИЕ ODDS С RETRY =====
def safe_get_odds(fixture_id, retries=MAX_RETRIES):
    cache_key = f"odds_{fixture_id}"
    
    # Проверяем кэш
    cached = db.get_cached(cache_key)
    if cached:
        logger.debug(f"📦 Кэш odds для {fixture_id}")
        return cached
    
    for attempt in range(retries):
        try:
            odds_data = football_api.get_match_odds(fixture_id)
            if odds_data and isinstance(odds_data, dict):
                # Сохраняем в кэш
                db.set_cached(cache_key, odds_data, ttl=CACHE_TTL)
                return odds_data
        except Exception as e:
            logger.warning(f"⚠️ Попытка {attempt+1}/{retries} для odds {fixture_id}: {e}")
            time.sleep(1 * (attempt + 1))  # Экспоненциальная задержка
    
    logger.error(f"❌ Не удалось получить odds для {fixture_id} после {retries} попыток")
    return {}

# ===== ПАКЕТНАЯ ОБРАБОТКА MATCHES =====
def process_matches_batch(matches, batch_size=10):
    """Обрабатывает матчи пачками для улучшения производительности"""
    results = []
    
    for i in range(0, len(matches), batch_size):
        batch = matches[i:i+batch_size]
        logger.info(f"📦 Обработка пачки {i//batch_size + 1}/{len(matches)//batch_size + 1}")
        
        # Параллельная обработка пачки
        threads = []
        batch_results = [None] * len(batch)
        
        def process_match(index, match):
            try:
                batch_results[index] = process_single_match(match)
            except Exception as e:
                logger.error(f"Ошибка обработки матча {index}: {e}")
        
        for idx, match in enumerate(batch):
            thread = threading.Thread(target=process_match, args=(idx, match))
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
        
        # Добавляем результаты
        for result in batch_results:
            if result:
                results.append(result)
        
        # Задержка между пачками
        time.sleep(0.5)
    
    return results

# ===== ОБРАБОТКА ОДНОГО МАТЧА =====
def process_single_match(match):
    """Обрабатывает один матч и возвращает данные для ставки"""
    if not match or not isinstance(match, dict):
        return None
    
    try:
        fixture = match.get("fixture")
        if not fixture or not isinstance(fixture, dict):
            return None
        
        fixture_id = fixture.get("id")
        if not fixture_id:
            return None
        
        teams = match.get("teams")
        if not teams or not isinstance(teams, dict):
            return None
        
        home_team = teams.get("home")
        away_team = teams.get("away")
        
        if not isinstance(home_team, dict) or not isinstance(away_team, dict):
            return None
        
        home = home_team.get("name", "Unknown")
        away = away_team.get("name", "Unknown")
        
        league_data = match.get("league")
        league = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"

        factors = match.get("factors", {})
        if not isinstance(factors, dict):
            factors = {}

        match_time = fixture.get("date", "")
        if match_time:
            try:
                dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                match_time = dt.strftime("%d.%m.%Y %H:%M")
            except:
                match_time = "Время не указано"

        # ===== xG с fallback =====
        try:
            home_xg, away_xg, reasons = xg_analyzer.calculate_xg(match, fixture_id)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка xG {home} vs {away}: {e}")
            home_xg, away_xg, reasons = 1.2, 1.0, ["fallback"]

        try:
            ml_home_xg, ml_away_xg = ml_predictor.predict_xg(factors)
            home_xg = (home_xg + ml_home_xg) / 2
            away_xg = (away_xg + ml_away_xg) / 2
        except Exception as e:
            logger.warning(f"⚠️ Ошибка ML {home} vs {away}: {e}")

        probs = calculate_probabilities(home_xg, away_xg)
        if not isinstance(probs, dict):
            logger.warning(f"⚠️ probs не словарь для {home} vs {away}")
            return None

        # ===== БЕЗОПАСНОЕ ПОЛУЧЕНИЕ ODDS =====
        odds_data = safe_get_odds(fixture_id)
        
        if not odds_data or not isinstance(odds_data, dict):
            logger.warning(f"⚠️ Нет odds для {home} vs {away} ({fixture_id})")
            return None

        bet_types = get_bet_types(odds_data)
        if not bet_types:
            return None

        match_data = {
            "home": home,
            "away": away,
            "league": league,
            "fixture_id": fixture_id,
            "match_time": match_time,
            "home_xg": round(home_xg, 2),
            "away_xg": round(away_xg, 2),
            "weather_reason": match.get("weather_reason", "🌤️ Погода отключена"),
            "factors": factors,
            "intuition": reasons,
            "bets": []
        }

        bank = storage.load_bank()
        
        for bet_type, odds, label in bet_types:
            prob = probs.get(bet_type, 0)
            if prob < 0.05 or prob > 0.99:
                continue

            ev = calculate_ev(prob, odds)
            
            # Улучшенный расчет ставки с учетом банка
            if ev > Config.MIN_EV:
                # Адаптивный процент от банка
                stake_percent = min(
                    (ev / 100) * 0.3,  # Kelly Criterion
                    Config.MAX_STAKE_PERCENT if hasattr(Config, 'MAX_STAKE_PERCENT') else 0.05
                )
                stake = min(
                    bank * stake_percent,
                    Config.MAX_BET_SIZE if hasattr(Config, 'MAX_BET_SIZE') else bank * 0.1
                )
                
                match_data["bets"].append({
                    "bet_type": bet_type,
                    "label": label,
                    "odds": odds,
                    "prob": round(prob * 100, 1),
                    "ev": round(ev, 1),
                    "stake": round(max(stake, 1.0), 2),  # Минимум $1
                })

        if match_data["bets"]:
            match_data["bets"].sort(key=lambda x: x['ev'], reverse=True)
            return match_data
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка в process_single_match: {e}")
        return None

# ===== ПОИСК МАТЧЕЙ С УЛУЧШЕНИЯМИ =====
@with_timeout(REQUEST_TIMEOUT)
def get_matches_with_factors():
    all_matches = []
    
    today = datetime.now().strftime('%Y-%m-%d')
    dates_to_search = [today]
    
    logger.info(f"🔍 Поиск матчей на: {today}")
    
    for league_id in Config.LEAGUES:
        for search_date in dates_to_search:
            try:
                matches = football_api.get_matches(league_id, search_date)
                league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
                
                if not matches or not isinstance(matches, list):
                    logger.info(f"ℹ️ Нет матчей в {league_name} на {search_date}")
                    continue
                
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                    
                    fixture = match.get("fixture")
                    if not fixture or not isinstance(fixture, dict):
                        continue
                    
                    status = fixture.get("status", {})
                    if not isinstance(status, dict):
                        continue
                    
                    if status.get("short") == "NS":
                        match_id = fixture.get("id")
                        if not match_id:
                            continue
                        
                        # Проверка на дубликат
                        existing_ids = set()
                        for m in all_matches:
                            if isinstance(m, dict):
                                fixture_id = m.get("fixture", {}).get("id")
                                if fixture_id:
                                    existing_ids.add(fixture_id)
                        
                        if match_id in existing_ids:
                            continue
                        
                        teams = match.get("teams", {})
                        if not isinstance(teams, dict):
                            continue
                        
                        home_team = teams.get("home", {})
                        away_team = teams.get("away", {})
                        
                        if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                            continue
                        
                        home_id = home_team.get("id")
                        away_id = away_team.get("id")
                        
                        if not home_id or not away_id:
                            continue
                        
                        match["factors"] = {
                            "home_form": football_api.get_form(home_id) if home_id else None,
                            "away_form": football_api.get_form(away_id) if away_id else None,
                            "home_injuries_list": football_api.get_injuries(home_id) if home_id else [],
                            "away_injuries_list": football_api.get_injuries(away_id) if away_id else [],
                            "home_id": home_id,
                            "away_id": away_id,
                            "referee": fixture.get("referee")
                        }
                        
                        match["weather"] = None
                        match["weather_reason"] = "🌤️ Погода отключена"
                        
                        league_data = match.get("league", {})
                        if isinstance(league_data, dict):
                            league_data["name"] = league_name
                        
                        all_matches.append(match)
                        
            except TimeoutError:
                logger.error(f"⏰ Таймаут при получении матчей {league_name}")
                send_error_to_telegram(f"Таймаут при получении матчей {league_name}")
            except Exception as e:
                error_msg = f"Ошибка {league_name} на {search_date}: {e}"
                logger.error(f"❌ {error_msg}")
                send_error_to_telegram(error_msg)
            
            time.sleep(0.1)
    
    logger.info(f"📊 ВСЕГО найдено матчей: {len(all_matches)}")
    return all_matches

# ===== ТОП МАТЧЕЙ С АВТО-СТАВКАМИ =====
def find_top_matches(matches):
    bank = storage.load_bank()
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN
    
    # Обрабатываем матчи пачками
    all_matches_data = process_matches_batch(matches, batch_size=5)
    
    # Сортируем по EV
    all_matches_data.sort(key=lambda x: x['bets'][0]['ev'] if x['bets'] else 0, reverse=True)
    top_matches = all_matches_data[:20]
    
    # Размещаем авто-ставки
    for match_data in top_matches:
        if bets_placed >= max_bets:
            logger.info(f"⚠️ Достигнут лимит ставок: {max_bets}")
            break
        
        try:
            # Проверяем, не была ли уже сделана ставка на этот матч
            existing_bets = db.get_all_bets()
            already_bet = any(
                bet.get('fixture_id') == match_data.get('fixture_id') 
                for bet in existing_bets
            )
            
            if already_bet:
                logger.info(f"ℹ️ Пропускаем {match_data['home']} vs {match_data['away']} - уже есть ставка")
                continue
            
            bet_result = auto_bet.check_and_bet(match_data)
            if bet_result:
                bets_placed += 1
                
                # Сохраняем в БД
                bet_record = {
                    'fixture_id': match_data.get('fixture_id'),
                    'home': match_data.get('home'),
                    'away': match_data.get('away'),
                    'league': match_data.get('league'),
                    'bet_type': bet_result.get('bet'),
                    'odds': bet_result.get('odds'),
                    'stake': bet_result.get('stake'),
                    'ev': bet_result.get('ev'),
                    'result': 'pending',
                    'profit': 0,
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'match_time': match_data.get('match_time'),
                    'home_goals': None,
                    'away_goals': None
                }
                db.save_bet(bet_record)
                
                msg = f"🤖 <b>АВТО-СТАВКА #{bets_placed}</b>\n"
                msg += f"🏟️ {bet_result['match']}\n"
                if bet_result.get('match_time'):
                    msg += f"📅 {bet_result['match_time']}\n"
                msg += f"📊 {bet_result['bet']} | КЭФ: {bet_result['odds']}\n"
                msg += f"💰 Сумма: ${bet_result['stake']}\n"
                msg += f"📈 EV: {bet_result['ev']}%"
                if bet_result.get('marker_stake'):
                    msg += f"\n🎯 Маркер: ${bet_result['marker_stake']}"
                send_telegram(msg)
                logger.info(f"✅ АВТО-СТАВКА #{bets_placed} на {match_data['home']} vs {match_data['away']}")
                
        except Exception as e:
            error_msg = f"Ошибка авто-ставки: {e}"
            logger.error(f"❌ {error_msg}")
            send_error_to_telegram(error_msg)
            continue
    
    logger.info(f"📊 Найдено {len(top_matches)} матчей, сделано {bets_placed} ставок")
    return top_matches

# ===== ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА СТАВКИ (УЛУЧШЕННОЕ) =====
def determine_bet_result(bet_type, home_goals, away_goals):
    """Определяет результат ставки по счёту с поддержкой всех типов"""
    total = home_goals + away_goals
    bet_type_lower = bet_type.lower()
    
    # Обе забьют
    if 'оз - да' in bet_type_lower or 'обз' in bet_type_lower or 'обе забьют' in bet_type_lower:
        if home_goals > 0 and away_goals > 0:
            return 'win'
        else:
            return 'loss'
    
    # Тоталы
    if 'тотал' in bet_type_lower or 'тб' in bet_type_lower or 'тм' in bet_type_lower:
        numbers = re.findall(r'\d+\.?\d*', bet_type_lower)
        if numbers:
            threshold = float(numbers[0])
            
            # Тотал больше
            if 'тб' in bet_type_lower or 'больше' in bet_type_lower:
                if total > threshold:
                    return 'win'
                elif abs(total - threshold) < 0.01:
                    return 'push'
                else:
                    return 'loss'
            
            # Тотал меньше
            elif 'тм' in bet_type_lower or 'меньше' in bet_type_lower:
                if total < threshold:
                    return 'win'
                elif abs(total - threshold) < 0.01:
                    return 'push'
                else:
                    return 'loss'
    
    # Азиатские форы
    if 'фора' in bet_type_lower or 'фор' in bet_type_lower:
        numbers = re.findall(r'[-+]?\d+\.?\d*', bet_type_lower)
        if numbers:
            handicap = float(numbers[0])
            
            # Фора на хозяев
            if 'хозя' in bet_type_lower or 'home' in bet_type_lower:
                result = home_goals + handicap - away_goals
                if result > 0:
                    return 'win'
                elif abs(result) < 0.01:
                    return 'push'
                else:
                    return 'loss'
            
            # Фора на гостей
            elif 'гост' in bet_type_lower or 'away' in bet_type_lower:
                result = away_goals + handicap - home_goals
                if result > 0:
                    return 'win'
                elif abs(result) < 0.01:
                    return 'push'
                else:
                    return 'loss'
    
    # Комбинированные
    if '1x' in bet_type_lower:
        if home_goals >= away_goals:
            return 'win'
        else:
            return 'loss'
    
    if 'x2' in bet_type_lower:
        if away_goals >= home_goals:
            return 'win'
        else:
            return 'loss'
    
    # Исходы
    if 'п1' in bet_type_lower or 'победа хозяев' in bet_type_lower:
        if home_goals > away_goals:
            return 'win'
        elif home_goals == away_goals:
            return 'push'
        else:
            return 'loss'
    
    if 'п2' in bet_type_lower or 'победа гостей' in bet_type_lower:
        if away_goals > home_goals:
            return 'win'
        elif home_goals == away_goals:
            return 'push'
        else:
            return 'loss'
    
    if 'x' in bet_type_lower or 'ничь' in bet_type_lower:
        if home_goals == away_goals:
            return 'win'
        else:
            return 'loss'
    
    return 'pending'

# ===== АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ =====
def update_pending_bets():
    """Автоматическое обновление результатов PENDING ставок"""
    bets = db.get_all_bets()
    updated = 0
    
    for bet in bets:
        if bet.get('result') in ['pending', None, '']:
            fixture_id = bet.get('fixture_id')
            
            if not fixture_id:
                home = bet.get('home', '')
                away = bet.get('away', '')
                if home and away and home != 'Unknown' and away != 'Unknown':
                    fixture_id = football_api.find_fixture_by_teams(home, away)
                    if fixture_id:
                        bet['fixture_id'] = fixture_id
                        # Обновляем в БД
                        conn = db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE bets SET fixture_id = ? WHERE id = ?', 
                                     (fixture_id, bet['id']))
                        conn.commit()
                        conn.close()
            
            if fixture_id:
                match_data = football_api.get_match_result(fixture_id)
                if match_data:
                    home_goals = match_data['goals']['home']
                    away_goals = match_data['goals']['away']
                    
                    if home_goals is not None and away_goals is not None:
                        bet_type = bet.get('bet_type', '')
                        result = determine_bet_result(bet_type, home_goals, away_goals)
                        
                        if result != 'pending':
                            if result == 'win':
                                profit = round(bet['stake'] * (bet['odds'] - 1), 2)
                            elif result == 'loss':
                                profit = -bet['stake']
                            else:
                                profit = 0
                            
                            db.update_bet_result(
                                bet['id'], 
                                result, 
                                profit, 
                                home_goals, 
                                away_goals
                            )
                            
                            updated += 1
                            logger.info(f"✅ Обновлена ставка: {bet['home']} vs {bet['away']} → {result} ({home_goals}-{away_goals})")
    
    if updated > 0:
        send_telegram(f"✅ Автоматически обновлено {updated} результатов!")
    
    return updated

# ===== ОТПРАВКА ОШИБОК В TELEGRAM =====
def send_error_to_telegram(error_text: str):
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        if len(error_text) > 4000:
            error_text = error_text[:4000] + "...(обрезано)"
        data = {
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': f"❌ <b>ОШИБКА БОТА</b>\n\n{error_text}",
            'parse_mode': 'HTML'
        }
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Не удалось отправить ошибку в Telegram: {e}")

def send_telegram(text: str, parse_mode: str = 'HTML'):
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id': Config.ADMIN_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Send error: {e}")
        send_error_to_telegram(f"Ошибка отправки в Telegram: {e}")

# ===== ЭКСПОРТ В EXCEL =====
def export_to_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    import io
    
    history = db.get_all_bets()
    
    if not history:
        return None, "📭 Нет данных для экспорта"
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Ставки"
    
    headers = ["ID", "Дата", "Матч", "Счёт", "Ставка", "Коэф", "EV%", "Сумма", "Результат", "Прибыль"]
    ws.append(headers)
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    
    total_profit = 0
    for bet in history:
        date = bet.get('date', '')
        home = bet.get('home', '')
        away = bet.get('away', '')
        home_goals = bet.get('home_goals', '')
        away_goals = bet.get('away_goals', '')
        score = f"{home_goals}-{away_goals}" if home_goals is not None and away_goals is not None else "-"
        bet_type = bet.get('bet_type', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', 0)
        stake = bet.get('stake', 0)
        result = bet.get('result', 'pending')
        profit = bet.get('profit', 0)
        
        total_profit += profit
        
        ws.append([bet['id'], date, f"{home} vs {away}", score, bet_type, odds, ev, stake, result, profit])
    
    ws.append([])
    ws.append(["ИТОГО", "", "", "", "", "", "", "", "", round(total_profit, 2)])
    
    for col in range(1, len(headers) + 1):
        column_letter = chr(64 + col)
        ws.column_dimensions[column_letter].width = 15
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output, f"✅ Экспорт завершен! Всего ставок: {len(history)}, Прибыль: ${round(total_profit, 2)}"

# ===== WEBHOOK =====
@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running, last_update_time
    
    try:
        data = request.get_json()
        if not data:
            return "ok", 200
        
        if 'callback_query' in data:
            callback = data['callback_query']
            callback_data = callback.get('data', '')
            
            logger.info(f"📨 Нажата кнопка: {callback_data}")
            
            answer_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"
            try:
                requests.post(answer_url, json={
                    "callback_query_id": callback.get('id', ''),
                    "text": "✅ Результат сохранён!"
                })
            except Exception as e:
                logger.error(f"Ошибка ответа: {e}")
            
            if callback_data.startswith('result_'):
                parts = callback_data.split('_')
                if len(parts) >= 3:
                    result_type = parts[1]
                    bet_id = parts[2]
                    
                    if result_type != 'skip':
                        bet = None
                        for b in db.get_all_bets():
                            if str(b['id']) == bet_id:
                                bet = b
                                break
                        
                        if bet:
                            if result_type == 'win':
                                result = 'win'
                                profit = round(bet['stake'] * (bet['odds'] - 1), 2)
                            elif result_type == 'loss':
                                result = 'loss'
                                profit = -bet['stake']
                            elif result_type == 'push':
                                result = 'push'
                                profit = 0
                            else:
                                result = 'loss'
                                profit = -bet['stake']
                            
                            db.update_bet_result(bet['id'], result, profit)
                            
                            msg = f"✅ Результат сохранён!\n{bet['home']} vs {bet['away']} → {result}"
                            if result == 'win':
                                msg += f"\n💰 Прибыль: +${profit}"
                            elif result == 'loss':
                                msg += f"\n💰 Проигрыш: -${bet['stake']}"
                            send_telegram(msg)
            
            return "ok", 200
        
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            if str(chat_id) != Config.ADMIN_CHAT_ID:
                send_telegram("⛔ Нет доступа")
                return "ok", 200
            
            if text == '/start':
                send_telegram(handlers.handle_start())
            
            elif text == '/update':
                if search_running:
                    send_telegram("⚠️ Поиск уже запущен!")
                else:
                    search_running = True
                    start_time = datetime.now()
                    send_telegram(f"🔄 Поиск матчей в {len(Config.LEAGUES)} лигах...")

                    with last_update_lock:
                        last_update_time = datetime.now()
                    
                    matches = get_matches_with_factors()
                    if matches:
                        send_telegram(f"📊 Найдено {len(matches)} матчей. Анализирую...")

                        top_matches = find_top_matches(matches)
                        if top_matches:
                            elapsed = (datetime.now() - start_time).seconds
                            stats = db.get_stats()
                            send_telegram(
                                f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                                f"📊 Найдено матчей: {len(matches)}\n"
                                f"🎯 Топ-матчей: {len(top_matches)}\n"
                                f"🤖 Всего ставок: {stats['total']}\n"
                                f"📈 Winrate: {stats['winrate']}%\n"
                                f"💰 Прибыль: ${stats['total_profit']}\n"
                                f"⏱️ Время: {elapsed} сек."
                            )
                        else:
                            send_telegram("❌ Ставок не найдено")
                    else:
                        send_telegram("❌ Матчей не найдено")

                    search_running = False
            
            elif text == '/stop':
                search_running = False
                send_telegram("🛑 ПОИСК ОСТАНОВЛЕН!")
            
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            
            elif text == '/stats':
                stats = db.get_stats()
                bank = storage.load_bank()
                msg = f"📊 <b>СТАТИСТИКА</b>\n\n"
                msg += f"💰 Банк: ${bank}\n"
                msg += f"📈 Всего ставок: {stats['total']}\n"
                msg += f"✅ Выигрышей: {stats['wins']}\n"
                msg += f"❌ Проигрышей: {stats['losses']}\n"
                msg += f"➖ Возвратов: {stats['pushes']}\n"
                msg += f"📊 Winrate: {stats['winrate']}%\n"
                msg += f"💰 Прибыль: ${stats['total_profit']}\n"
                msg += f"📈 ROI: {stats['roi']}%"
                send_telegram(msg)
            
            elif text == '/help':
                send_telegram(handlers.handle_start())
            
            elif text == '/autobet':
                auto_bet.enabled = not getattr(auto_bet, 'enabled', True)
                status = "ВКЛЮЧЕНЫ" if auto_bet.enabled else "ВЫКЛЮЧЕНЫ"
                send_telegram(f"🤖 Авто-ставки {status}!")
            
            elif text == '/export':
                file, message = export_to_excel()
                if file:
                    send_telegram(message)
                    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                    files = {'document': ('history.xlsx', file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                    data = {'chat_id': Config.ADMIN_CHAT_ID, 'caption': '📊 История ставок'}
                    try:
                        requests.post(url, files=files, data=data, timeout=30)
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла: {e}")
                else:
                    send_telegram(message)
            
            elif text == '/update_results':
                send_telegram("🔄 Проверка результатов матчей...")
                updated = update_pending_bets()
                if updated > 0:
                    send_telegram(f"✅ Обновлено {updated} результатов!")
                else:
                    send_telegram("📭 Нет завершённых матчей для обновления")
            
            elif text == '/status':
                with last_update_lock:
                    last_update = last_update_time.strftime("%Y-%m-%d %H:%M:%S") if last_update_time else "Никогда"
                
                stats = db.get_stats()
                msg = f"🤖 <b>СТАТУС БОТА</b>\n\n"
                msg += f"🟢 Статус: {'Работает' if not search_running else 'Сканирует'}\n"
                msg += f"🔄 Последнее обновление: {last_update}\n"
                msg += f"📊 Активных лиг: {len(Config.LEAGUES)}\n"
                msg += f"💰 Банк: ${storage.load_bank()}\n"
                msg += f"📈 Всего ставок: {stats['total']}\n"
                msg += f"📊 Winrate: {stats['winrate']}%\n"
                msg += f"💰 Прибыль: ${stats['total_profit']}\n"
                msg += f"🤖 Авто-ставки: {'ВКЛ' if auto_bet.enabled else 'ВЫКЛ'}"
                send_telegram(msg)
            
            else:
                send_telegram("❌ Неизвестная команда. Используйте /help")
        
        return "ok", 200
    except Exception as e:
        error_msg = f"Webhook error: {e}"
        logger.error(f"❌ {error_msg}")
        send_error_to_telegram(error_msg)
        return "ok", 200

# ===== API ЭНДПОИНТЫ =====
@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = db.get_stats()
    bank = storage.load_bank()
    
    return jsonify({
        'bank': bank,
        'total_bets': stats['total'],
        'wins': stats['wins'],
        'losses': stats['losses'],
        'pushes': stats['pushes'],
        'profit': round(stats['total_profit'], 2),
        'winrate': stats['winrate'],
        'roi': stats['roi']
    })

@app.route('/api/history', methods=['GET'])
def api_history():
    limit = request.args.get('limit', 100, type=int)
    bets = db.get_all_bets()[:limit]
    
    for bet in bets:
        if bet.get('result') == 'win':
            bet['profit'] = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
        elif bet.get('result') == 'loss':
            bet['profit'] = -round(bet.get('stake', 0), 2)
        else:
            bet['profit'] = 0
        bet['match'] = f"{bet.get('home', '')} vs {bet.get('away', '')}"
    
    return jsonify(bets)

@app.route('/api/bank', methods=['POST'])
def api_update_bank():
    data = request.json
    if 'bank' in data:
        storage.save_bank(data['bank'])
        return jsonify({'success': True, 'bank': data['bank']})
    return jsonify({'error': 'No bank value'}), 400

@app.route('/api/status', methods=['GET'])
def api_status():
    with last_update_lock:
        last_update = last_update_time.isoformat() if last_update_time else None
    
    stats = db.get_stats()
    
    return jsonify({
        'running': search_running,
        'last_update': last_update,
        'bets_today': len([b for b in db.get_all_bets() if b.get('date', '').startswith(datetime.now().strftime('%Y-%m-%d'))]),
        'total_bets': stats['total'],
        'winrate': stats['winrate'],
        'profit': stats['total_profit'],
        'bank': storage.load_bank(),
        'auto_bet_enabled': getattr(auto_bet, 'enabled', True),
        'active_leagues': len(Config.LEAGUES)
    })

@app.route('/api/clear_cache', methods=['POST'])
def clear_cache():
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cache')
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cache cleared'})

@app.route('/', methods=['GET'])
def index():
    stats = db.get_stats()
    return f"🤖 Quantum Bot v13 PRO | Ставок: {stats['total']} | Прибыль: ${stats['total_profit']} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/health', methods=['GET'])
def health():
    try:
        # Проверяем БД
        db.get_stats()
        return {"status": "ok", "time": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500

# ===== ПЕРИОДИЧЕСКОЕ ОБНОВЛЕНИЕ =====
def scheduled_update():
    """Запускается по расписанию для автоматического обновления"""
    global search_running
    
    if not search_running:
        logger.info("🔄 Запуск планового обновления...")
        search_running = True
        try:
            matches = get_matches_with_factors()
            if matches:
                top_matches = find_top_matches(matches)
                logger.info(f"✅ Плановое обновление: найдено {len(top_matches)} матчей")
            search_running = False
        except Exception as e:
            logger.error(f"❌ Ошибка планового обновления: {e}")
            search_running = False

# ===== ЗАПУСК =====
if __name__ == "__main__":
    setup_logging()
    
    # Запускаем планировщик
    start_scheduler()
    
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    logger.info(f"📦 База данных: data/bot.db")
    logger.info("✅ Мониторинг ошибок включен")
    logger.info("✅ Кэширование включено")
    logger.info("✅ Авто-обновление результатов включено")
    
    app.run(host='0.0.0.0', port=port, debug=False)
