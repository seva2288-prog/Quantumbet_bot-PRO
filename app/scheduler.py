# app/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from app.utils.logger import get_logger

logger = get_logger(__name__)

scheduler = BackgroundScheduler()

def check_results_job():
    """Проверка результатов матчей"""
    try:
        from app.bot import update_pending_bets
        updated = update_pending_bets()
        if updated > 0:
            logger.info(f"✅ Авто-обновление: {updated} результатов")
    except Exception as e:
        logger.error(f"❌ Ошибка проверки результатов: {e}")

def start_scheduler():
    """Запускает планировщик"""
    try:
        # Проверка результатов каждые 30 минут
        scheduler.add_job(
            check_results_job,
            trigger=IntervalTrigger(minutes=30),
            id='check_results',
            next_run_time=datetime.now()
        )
        
        scheduler.start()
        logger.info("✅ Планировщик запущен (проверка результатов каждые 30 минут)")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика: {e}")

def stop_scheduler():
    """Останавливает планировщик"""
    try:
        scheduler.shutdown()
        logger.info("🛑 Планировщик остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка остановки планировщика: {e}")
