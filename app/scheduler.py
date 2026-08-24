import schedule
import time
from threading import Thread
from datetime import datetime, timedelta
from app.database.storage import storage
from app.utils.logger import get_logger

logger = get_logger(__name__)

def send_weekly_report():
    """Отправка еженедельного отчёта"""
    from app.bot import send_telegram
    
    history = storage.load_history()
    
    if not history:
        send_telegram("📊 Нет данных для отчёта за неделю")
        return
    
    # Фильтруем за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    week_history = []
    
    for bet in history:
        try:
            date_str = bet.get('date', '')
            if date_str:
                bet_date = datetime.strptime(date_str.split()[0], '%Y-%m-%d')
                if bet_date >= week_ago:
                    week_history.append(bet)
        except:
            pass
    
    if not week_history:
        send_telegram("📊 За неделю не было ставок")
        return
    
    # Считаем статистику
    total = len(week_history)
    wins = sum(1 for b in week_history if b.get('result') == 'win')
    losses = sum(1 for b in week_history if b.get('result') == 'loss')
    pushes = sum(1 for b in week_history if b.get('result') == 'push')
    
    profit = 0
    for bet in week_history:
        if bet.get('result') == 'win':
            profit += bet.get('stake', 0) * (bet.get('odds', 1) - 1)
        elif bet.get('result') == 'loss':
            profit -= bet.get('stake', 0)
    
    winrate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    
    # Лучшая лига за неделю
    league_stats = {}
    for bet in week_history:
        league = bet.get('league', 'Unknown')
        if league not in league_stats:
            league_stats[league] = {'wins': 0, 'total': 0}
        league_stats[league]['total'] += 1
        if bet.get('result') == 'win':
            league_stats[league]['wins'] += 1
    
    best_league = 'Нет данных'
    best_winrate = 0
    for league, stats in league_stats.items():
        if stats['total'] >= 3:
            lr = stats['wins'] / stats['total'] * 100
            if lr > best_winrate:
                best_winrate = lr
                best_league = league
    
    # Формируем сообщение
    msg = f"""📊 <b>ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ</b>
📅 {week_ago.strftime('%d.%m')} - {datetime.now().strftime('%d.%m')}

━━━━━━━━━━━━━━━━━━━
📈 <b>СТАТИСТИКА</b>
Всего ставок: {total}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
↩️ Возвратов: {pushes}
🎯 Проходимость: {round(winrate, 1)}%
💰 Прибыль: ${round(profit, 2)}

━━━━━━━━━━━━━━━━━━━
🏆 <b>ЛУЧШАЯ ЛИГА</b>
{best_league} — {round(best_winrate, 1)}%

━━━━━━━━━━━━━━━━━━━
💡 <b>СОВЕТ</b>
{f'💰 Прибыль положительная — продолжайте!' if profit > 0 else '📉 Есть над чем работать — анализируйте ошибки.'}
"""
    
    send_telegram(msg)
    logger.info("✅ Еженедельный отчёт отправлен")


def start_scheduler():
    """Запуск планировщика"""
    # Отправка отчёта каждое воскресенье в 20:00
    schedule.every().sunday.at("20:00").do(send_weekly_report)
    
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    thread = Thread(target=run_schedule, daemon=True)
    thread.start()
    logger.info("✅ Планировщик запущен (отчёт по воскресеньям в 20:00)")
