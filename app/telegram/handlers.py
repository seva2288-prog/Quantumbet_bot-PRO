from app.database.storage import storage

class CommandHandlers:
    def handle_start(self) -> str:
        return """🚀 QUANTUM BETTING BOT v12 PRO

✅ ВСЕ УЛУЧШЕНИЯ:
📊 Poisson распределение
⏰ Учет времени матча
📈 Прогноз по таймам

⚠️ ПОИСК ТОЛЬКО ПО КОМАНДЕ /update

📋 КОМАНДЫ:
/today - ТОП-5 из кеша
/update - РУЧНОЙ поиск ТОП-5
/stop - ОСТАНОВИТЬ поиск
/bank - Банк
/stats - Статистика
/learn - Статистика обучения
/help - Помощь"""
    
    def handle_bank(self) -> str:
        bank = storage.load_bank()
        return f"💰 БАНК\n${bank:.2f}"
    
    def handle_stats(self) -> str:
        stats = storage.load_stats()
        total = stats.get('total', 0)
        wins = stats.get('wins', 0)
        losses = stats.get('losses', 0)
        pushes = stats.get('pushes', 0)
        
        if total == 0:
            return "📭 Нет данных по ставкам"
        
        winrate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        profit = 0
        for b in stats.get('history', []):
            if b.get('result') == 'win':
                profit += b.get('stake', 0) * (b.get('odds', 1) - 1)
            elif b.get('result') == 'loss':
                profit -= b.get('stake', 0)
        
        msg = f"""📊 <b>ОБЩАЯ СТАТИСТИКА СТАВОК</b>

Всего ставок: {total}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
↩️ Возвратов: {pushes}
🎯 Проходимость: {round(winrate, 1)}%
💰 Прибыль: ${round(profit, 2)}"""
        return msg

handlers = CommandHandlers()
