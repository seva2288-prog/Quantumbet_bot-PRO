import schedule
import time
from threading import Thread
from app.utils.logger import get_logger

logger = get_logger(__name__)

def auto_update():
    """Автоматический поиск матчей каждые 4 часа"""
    logger.info("🔄 Автоматический поиск матчей...")
    try:
        from app.bot import get_matches_with_factors, find_top_matches
        from app.database.storage import storage
        
        matches = get_matches_with_factors()
        if matches:
            top_matches = find_top_matches(matches)
            if top_matches:
                # Сохраняем в кэш
                cache = storage.load_cache()
                cache['top_matches'] = top_matches
                storage.save_cache(cache)
                logger.info(f"✅ Авто-обновление: найдено {len(top_matches)} матчей")
            else:
                logger.info("⚠️ Авто-обновление: ставок не найдено")
        else:
            logger.warning("⚠️ Авто-обновление: матчей не найдено")
    except Exception as e:
        logger.error(f"❌ Ошибка автоматического обновления: {e}")

def start_scheduler():
    """Запуск планировщика"""
    # Первый запуск через 1 минуту после старта
    schedule.every(1).minutes.do(auto_update)
    # Затем каждые 4 часа
    schedule.every(4).hours.do(auto_update)
    
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    thread = Thread(target=run_schedule, daemon=True)
    thread.start()
    logger.info("✅ Планировщик запущен (обновление каждые 4 часа)")
