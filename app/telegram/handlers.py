from app.database.storage import storage

class CommandHandlers:
    def handle_start(self) -> str:
        return """🚀 QUANTUM BETTING BOT v12 PRO

✅ ВСЕ УЛУЧШЕНИЯ:
📊 Poisson распределение
⏰ Учет времени матча
🧤 Учет вратарей
📈 Прогноз по таймам
🎯 Прогноз точного счета
💰 Критерий Келли

📋 КОМАНДЫ:
/today - ТОП-5 из кеша
/update - РУЧНОЙ поиск ТОП-5
/stop - ОСТАНОВИТЬ поиск
/bank - Банк
/stats - Статистика
/learn - Статистика обучения

📊 НОВЫЕ КОМАНДЫ:
/team <название> - Статистика по команде
/bettypes - Статистика по типам ставок
/timestats - Статистика по времени

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

    # ============ НОВЫЕ МЕТОДЫ ============

    def handle_team_stats(self, team_name: str) -> str:
        """Статистика по конкретной команде"""
        history = storage.load_history()
        
        wins = 0
        losses = 0
        total = 0
        profit = 0
        
        for bet in history:
            if team_name.lower() in bet.get('home', '').lower() or \
               team_name.lower() in bet.get('away', '').lower():
                total += 1
                if bet.get('result') == 'win':
                    wins += 1
                    profit += bet.get('stake', 0) * (bet.get('odds', 1) - 1)
                elif bet.get('result') == 'loss':
                    losses += 1
                    profit -= bet.get('stake', 0)
        
        if total == 0:
            return f"📭 Нет данных по команде {team_name}"
        
        winrate = wins / total * 100
        
        msg = f"📊 <b>Статистика по команде {team_name}</b>\n"
        msg += f"Всего ставок: {total}\n"
        msg += f"✅ Выигрышей: {wins}\n"
        msg += f"❌ Проигрышей: {losses}\n"
        msg += f"🎯 Проходимость: {round(winrate, 1)}%\n"
        msg += f"💰 Прибыль: ${round(profit, 2)}"
        
        return msg

    def handle_bet_type_stats(self) -> str:
        """Статистика по типам ставок"""
        history = storage.load_history()
        
        stats = {}
        for bet in history:
            bet_type = bet.get('bet', 'Unknown')
            if bet_type not in stats:
                stats[bet_type] = {'total': 0, 'wins': 0, 'profit': 0}
            
            stats[bet_type]['total'] += 1
            if bet.get('result') == 'win':
                stats[bet_type]['wins'] += 1
                stats[bet_type]['profit'] += bet.get('stake', 0) * (bet.get('odds', 1) - 1)
            elif bet.get('result') == 'loss':
                stats[bet_type]['profit'] -= bet.get('stake', 0)
        
        if not stats:
            return "📭 Нет данных по типам ставок"
        
        msg = "📊 <b>Статистика по типам ставок</b>\n\n"
        for bet_type, data in sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True):
            winrate = data['wins'] / data['total'] * 100 if data['total'] > 0 else 0
            msg += f"<b>{bet_type}</b>\n"
            msg += f"   📊 {data['wins']}/{data['total']} ({round(winrate, 1)}%)\n"
            msg += f"   💰 ${round(data['profit'], 2)}\n\n"
        
        return msg

    def handle_time_stats(self) -> str:
        """Статистика по времени ставок"""
        history = storage.load_history()
        
        time_stats = {
            'morning': {'total': 0, 'wins': 0, 'profit': 0},
            'day': {'total': 0, 'wins': 0, 'profit': 0},
            'evening': {'total': 0, 'wins': 0, 'profit': 0},
            'night': {'total': 0, 'wins': 0, 'profit': 0},
        }
        
        for bet in history:
            date_str = bet.get('date', '')
            if date_str:
                try:
                    hour = int(date_str.split()[1].split(':')[0])
                    if 6 <= hour < 12:
                        period = 'morning'
                    elif 12 <= hour < 18:
                        period = 'day'
                    elif 18 <= hour < 24:
                        period = 'evening'
                    else:
                        period = 'night'
                    
                    time_stats[period]['total'] += 1
                    if bet.get('result') == 'win':
                        time_stats[period]['wins'] += 1
                        time_stats[period]['profit'] += bet.get('stake', 0) * (bet.get('odds', 1) - 1)
                    elif bet.get('result') == 'loss':
                        time_stats[period]['profit'] -= bet.get('stake', 0)
                except:
                    pass
        
        names = {
            'morning': '🌅 Утро (6-12)',
            'day': '☀️ День (12-18)',
            'evening': '🌇 Вечер (18-24)',
            'night': '🌙 Ночь (0-6)'
        }
        
        msg = "📊 <b>Статистика по времени</b>\n\n"
        has_data = False
        for period, name in names.items():
            data = time_stats[period]
            if data['total'] > 0:
                has_data = True
                winrate = data['wins'] / data['total'] * 100
                msg += f"{name}\n"
                msg += f"   📊 {data['wins']}/{data['total']} ({round(winrate, 1)}%)\n"
                msg += f"   💰 ${round(data['profit'], 2)}\n\n"
        
        if not has_data:
            return "📭 Нет данных по времени ставок"
        
        return msg

handlers = CommandHandlers()
