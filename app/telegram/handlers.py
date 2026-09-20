def handle_start(self):
    return """🤖 <b>Quantum Bet Bot</b>

<b>🚀 Основные:</b>
/update — полный поиск матчей на сегодня
/today — ТОП-5 матчей из кэша
/analyze [матч] — детальный анализ матча
/status — статус бота
/stop — остановить зависший поиск
/reset_search — сбросить флаг поиска

<b>💰 Банк и статистика:</b>
/bank — текущий банк
/stats — общая статистика
/report — отчёт за 7 дней
/bettypes — статистика по типам ставок
/timestats — статистика по времени
/strategies — сравнение стратегий
/team [название] — статистика по команде

<b>💸 Автоставки:</b>
/autobet — вкл/выкл автоставки
/autobet_state — состояние автоставок (банк, ROI, CLV)

<b>📊 CLV-анализ:</b>
/clv — средний Closing Line Value

<b>🎯 Grid Search:</b>
/grid_search — автопоиск лучшей стратегии

<b>📝 История:</b>
/result [матч] [счёт] — ручной ввод результата
/update_results — обновить pending-ставки
/export — экспорт в Excel

<b>💾 Резервное копирование:</b>
/backup — создать бэкап в Telegram

<b>ℹ️ Прочее:</b>
/help — эта справка"""
