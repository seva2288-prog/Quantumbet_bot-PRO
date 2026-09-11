"""Логирование бота"""
import logging
import os
from logging.handlers import RotatingFileHandler


_LOGGER_NAME = 'betting_bot'


def setup_logging():
    """
    Инициализирует корневой логгер бота.
    Безопасно вызывать несколько раз — хендлеры не дублируются.
    """
    os.makedirs('logs', exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    # Защита от дублирования хендлеров
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    file_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=10 * 1024 * 1024,  # 10 МБ
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Чтобы логи не улетали в root
    logger.propagate = False

    return logger


def get_logger(name):
    """
    Возвращает дочерний логгер.
    'app.llm' → 'betting_bot.llm'
    """
    short = name.rsplit('.', 1)[-1] if name else 'root'
    return logging.getLogger(f'{_LOGGER_NAME}.{short}')


# Автоинициализация при импорте —
# чтобы get_logger() всегда возвращал рабочий логгер
setup_logging()
