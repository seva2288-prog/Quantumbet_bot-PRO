"""Ротация ключей Odds API при исчерпании лимита"""
from itertools import cycle

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OddsKeyRotator:
    """
    Переключает ключи Odds API при 429/401.

    Порядок ключей:
      1. Config.ODDS_API_KEY (основной)
      2. Config.BACKUP_ODDS_KEYS (резервные)

    Если все ключи исчерпаны — rotate() вернёт None.
    """

    def __init__(self):
        keys = [Config.ODDS_API_KEY] + list(Config.BACKUP_ODDS_KEYS)
        keys = [k for k in keys if k]  # убираем пустые

        if not keys:
            raise ValueError("Нет ни одного Odds API ключа")

        self._keys = keys
        self._cycle = cycle(keys)
        self.current = next(self._cycle)
        self.exhausted = set()

        logger.info(f"🔑 Odds-ключей загружено: {len(keys)}")

    def get(self) -> str:
        """Текущий активный ключ."""
        return self.current

    def rotate(self) -> str | None:
        """
        Переключает на следующий неисчерпанный ключ.
        Возвращает новый ключ или None, если все исчерпаны.
        """
        self.exhausted.add(self.current)

        # Ищем следующий неисчерпанный ключ
        for _ in range(len(self._keys)):
            nxt = next(self._cycle)
            if nxt not in self.exhausted:
                self.current = nxt
                logger.warning(
                    f"🔄 Odds-ключ переключён: ...{nxt[-6:]} "
                    f"(исчерпано: {len(self.exhausted)}/{len(self._keys)})"
                )
                return nxt

        logger.error("❌ Все Odds API ключи исчерпаны")
        return None

    def reset(self):
        """Сбрасывает список исчерпанных ключей."""
        self.exhausted.clear()
        logger.info("♻️ Odds-ключи сброшены")

    def status(self) -> dict:
        """Информация о состоянии ротатора."""
        return {
            'total': len(self._keys),
            'exhausted': len(self.exhausted),
            'available': len(self._keys) - len(self.exhausted),
            'current': f"...{self.current[-6:]}" if self.current else None,
        }
