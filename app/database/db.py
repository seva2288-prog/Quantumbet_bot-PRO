# app/database/db.py
import sqlite3
import json
from datetime import datetime
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = 'data/bets.db'

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
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
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id FROM bets 
            WHERE home = ? AND away = ? AND date = ?
        ''', (bet.get('home', ''), bet.get('away', ''), bet.get('date', '')))
        
        existing = cursor.fetchone()
        if existing:
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
        for bet in bets:
            self.save_bet(bet)
        logger.info(f"✅ Сохранено {len(bets)} ставок в БД")
    
    def load_history(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bets ORDER BY date DESC')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_bets_by_date(self, date):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bets WHERE date LIKE ? ORDER BY date DESC', (f'{date}%',))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_bets_by_result(self, result):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bets WHERE result = ? ORDER BY date DESC', (result,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_bets_by_stake(self, stake):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bets WHERE stake = ? ORDER BY date DESC', (stake,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_stats(self):
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as total FROM bets')
        total = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as wins FROM bets WHERE result = "win"')
        wins = cursor.fetchone()['wins']
        
        cursor.execute('SELECT COUNT(*) as losses FROM bets WHERE result = "loss"')
        losses = cursor.fetchone()['losses']
        
        cursor.execute('SELECT COUNT(*) as pushes FROM bets WHERE result = "push"')
        pushes = cursor.fetchone()['pushes']
        
        cursor.execute('SELECT SUM(profit) as profit FROM bets')
        profit = cursor.fetchone()['profit'] or 0
        
        conn.close()
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'profit': round(profit, 2),
            'bank': 1000
        }
    
    def clear_all(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM bets')
        conn.commit()
        conn.close()
        logger.warning("🗑️ Все ставки удалены из БД")


db = BetDB()
