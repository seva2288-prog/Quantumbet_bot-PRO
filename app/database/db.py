# app/database/db.py
import sqlite3
import json
from datetime import datetime
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = 'data/bets.db'

def get_connection():
    """Создает подключение к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица ставок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            home TEXT,
            away TEXT,
            league TEXT,
            bet TEXT,
            odds REAL,
            stake REAL,
            ev REAL,
            result TEXT,
            profit REAL,
            date TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            auto INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_date ON bets(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_result ON bets(result)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_stake ON bets(stake)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_home ON bets(home)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_away ON bets(away)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_auto ON bets(auto)')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована с индексами")

class BetDB:
    def __init__(self):
        init_db()
    
    def save_bet(self, bet):
        """Сохраняет одну ставку"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже такая ставка
        cursor.execute('''
            SELECT id FROM bets 
            WHERE home = ? AND away = ? AND date = ?
        ''', (bet.get('home', ''), bet.get('away', ''), bet.get('date', '')))
        
        existing = cursor.fetchone()
        if existing:
            # Обновляем существующую
            cursor.execute('''
                UPDATE bets SET
                    league = ?,
                    bet = ?,
                    odds = ?,
                    stake = ?,
                    ev = ?,
                    result = ?,
                    profit = ?,
                    home_goals = ?,
                    away_goals = ?,
                    auto = ?
                WHERE id = ?
            ''', (
                bet.get('league', ''),
                bet.get('bet', ''),
                bet.get('odds', 0),
                bet.get('stake', 0),
                bet.get('ev', 0),
                bet.get('result', 'pending'),
                bet.get('profit', 0),
                bet.get('home_goals'),
                bet.get('away_goals'),
                1 if bet.get('auto') else 0,
                existing['id']
            ))
        else:
            # Вставляем новую
            cursor.execute('''
                INSERT INTO bets (
                    home, away, league, bet, odds, stake, ev, 
                    result, profit, date, home_goals, away_goals, auto
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                bet.get('home', ''),
                bet.get('away', ''),
                bet.get('league', ''),
                bet.get('bet', ''),
                bet.get('odds', 0),
                bet.get('stake', 0),
                bet.get('ev', 0),
                bet.get('result', 'pending'),
                bet.get('profit', 0),
                bet.get('date', datetime.now().strftime('%Y-%m-%d %H:%M')),
                bet.get('home_goals'),
                bet.get('away_goals'),
                1 if bet.get('auto') else 0
            ))
        
        conn.commit()
        conn.close()
        return True
    
    def save_bets(self, bets):
        """Сохраняет несколько ставок"""
        for bet in bets:
            self.save_bet(bet)
        logger.info(f"✅ Сохранено {len(bets)} ставок в БД")
    
    def load_history(self):
        """Загружает ВСЮ историю (для совместимости)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM bets ORDER BY date DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_bets_by_date(self, date):
        """Быстрый поиск по дате (использует индекс)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM bets WHERE date LIKE ? ORDER BY date DESC
        ''', (f'{date}%',))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_bets_by_result(self, result):
        """Быстрый поиск по результату (использует индекс)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM bets WHERE result = ? ORDER BY date DESC
        ''', (result,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_bets_by_stake(self, stake):
        """Быстрый поиск по сумме (использует индекс)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM bets WHERE stake = ? ORDER BY date DESC
        ''', (stake,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_stats(self):
        """Быстрая статистика (использует индексы)"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Всего ставок
        cursor.execute('SELECT COUNT(*) as total FROM bets')
        total = cursor.fetchone()['total']
        
        # Выигрыши
        cursor.execute('SELECT COUNT(*) as wins FROM bets WHERE result = "win"')
        wins = cursor.fetchone()['wins']
        
        # Проигрыши
        cursor.execute('SELECT COUNT(*) as losses FROM bets WHERE result = "loss"')
        losses = cursor.fetchone()['losses']
        
        # Возвраты
        cursor.execute('SELECT COUNT(*) as pushes FROM bets WHERE result = "push"')
        pushes = cursor.fetchone()['pushes']
        
        # Прибыль
        cursor.execute('SELECT SUM(profit) as profit FROM bets')
        profit = cursor.fetchone()['profit'] or 0
        
        # Банк (из последней ставки или по умолчанию)
        cursor.execute('SELECT stake FROM bets ORDER BY id DESC LIMIT 1')
        last = cursor.fetchone()
        bank = 1000  # стартовый банк
        
        conn.close()
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'profit': round(profit, 2),
            'bank': bank
        }
    
    def get_dates_with_bets(self):
        """Получает список дат, в которых есть ставки"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT date(date) as date FROM bets ORDER BY date DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [row['date'] for row in rows]
    
    def clear_all(self):
        """Очищает все ставки (осторожно!)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM bets')
        conn.commit()
        conn.close()
        logger.warning("🗑️ Все ставки удалены из БД")
    
    def migrate_from_json(self):
        """Миграция из JSON в БД"""
        from app.database.storage import storage
        history = storage.load_history()
        if history:
            self.save_bets(history)
            logger.info(f"✅ Мигрировано {len(history)} ставок из JSON в БД")
        return len(history)


# Создаем глобальный экземпляр
db = BetDB()
