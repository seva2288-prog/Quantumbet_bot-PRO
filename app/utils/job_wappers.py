# app/utils/job_wrapper.py
from app.utils.logger import get_logger

logger = get_logger(__name__)


def safe_job(func, name):
    """Обёртка для планировщика с логированием ошибок."""
    def wrapper():
        try:
            logger.info(f"▶️ START: {name}")
            result = func()
            logger.info(f"✅ END: {name} | result={result}")
            return result
        except Exception as e:
            logger.exception(f"❌ FAIL: {name} | {e}")
            return None
    return wrapper
