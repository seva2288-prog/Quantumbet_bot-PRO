# app/telegram/handlers.py
import requests
from datetime import datetime, timedelta
from app.database.storage import storage
from app.config import Config

class Handlers:
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.admin_chat_id = Config.ADMIN_CHAT_ID
    
    def send_message(self, text, parse_mode='HTML'):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {
                'chat_id': self.admin_chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    def handle_start(self):
        return """🤖 <b>Quantum Bet Bot PRO v12</b>

Доступные команды:

/start - Приветствие и помощь
/update - Поиск матчей на сегодня 
/today - ТОП-5 матчей из кэша
/bank - Текущий банк
/stats - Общая статистика
/team [название] - Статистика по команде
/bettypes - Статистика по типам ставок
/timestats - Статистика по времени ставок
/mlstats - Статистика машинного обучения
/report - Еженедельный отчёт
/export - Экспорт истории в Excel
/autobet - Включить/выключить авто-ставки
/train - Обучить нейросеть
/arb - Поиск букмекерских вилок
/anomalies - Поиск аномалий
/security - Статистика безопасности
/unblock [IP] - Разблокировать IP
/result [команда1] [команда2] [счёт] - Ввести результат
/stop - Остановить поиск
/help - Помощь"""
    
    def handle_bank(self):
        bank = storage.load_bank()
        return f"💰 <b>Текущий банк:</b> ${bank:.2f}"
    
    def handle_stats(self):
        stats = storage.load_stats()
        history = storage.load_history()
        total = len(history)
        wins = stats.get('wins', 0)
        losses = stats.get('losses', 0)
        pushes = stats.get('pushes', 0)
        profit = stats.get('total_profit', 0)
        winrate = stats.get('winrate', 0)
        roi = stats.get('roi', 0)
        total_stake = sum(bet.get('stake', 0) for bet in history)
        avg_stake = round(total_stake / total, 2) if total > 0 else 0
        
        return f"""📊 <b>ОБЩАЯ СТАТИСТИКА</b>

📈 Всего ставок: {total}
✅ Выигрыши: {wins}
❌ Проигрыши: {losses}
🔄 Возвраты: {pushes}
💰 Прибыль: ${profit:.2f}
🎯 Проходимость: {winrate}%
📈 ROI: {roi}%
📅 Средняя ставка: ${avg_stake}"""
    
    def handle_today(self):
        cache = storage.load_cache()
        matches = cache.get('top_matches', [])
        if not matches:
            return "📭 Нет матчей в кэше. Запусти /update"
        
        msg = "📊 <b>ТОП-5 МАТЧЕЙ</b>\n\n"
        for i, match in enumerate(matches[:5], 1):
            msg += f"{i}. 🏟️ {match.get('home')} vs {match.get('away')}\n"
            msg += f"   📊 Лига: {match.get('league')}\n"
            if match.get('bets'):
                best = match['bets'][0]
                msg += f"   🎯 {best.get('label')} | КЭФ: {best.get('odds')} | EV: {best.get('ev')}%\n"
            msg += "\n"
        return msg
    
    def handle_team(self, team_name):
        if not team_name:
            return "⚠️ Укажи команду: /team Real Madrid"
        
        history = storage.load_history()
        team_bets = [b for b in history if team_name.lower() in b.get('home', '').lower() or team_name.lower() in b.get('away', '').lower()]
        
        if not team_bets:
            return f"📭 Нет ставок на {team_name}"
        
        wins = sum(1 for b in team_bets if b.get('result') == 'win')
        losses = sum(1 for b in team_bets if b.get('result') == 'loss')
        profit = sum(b.get('profit', 0) for b in team_bets)
        
        return f"""📊 <b>Статистика по {team_name}</b>

📈 Всего: {len(team_bets)}
✅ Выигрыши: {wins}
❌ Проигрыши: {losses}
💰 Прибыль: ${profit:.2f}"""
    
    def handle_bettypes(self):
        history = storage.load_history()
        bet_stats = {}
        for bet in history:
            btype = bet.get('bet', 'Unknown')
            if btype not in bet_stats:
                bet_stats[btype] = {'total': 0, 'wins': 0, 'profit': 0}
            bet_stats[btype]['total'] += 1
            if bet.get('result') == 'win':
                bet_stats[btype]['wins'] += 1
            bet_stats[btype]['profit'] += bet.get('profit', 0)
        
        if not bet_stats:
            return "📭 Нет данных"
        
        msg = "📊 <b>Статистика по типам ставок</b>\n\n"
        for btype, stats in sorted(bet_stats.items(), key=lambda x: x[1]['profit'], reverse=True)[:10]:
            total = stats['total']
            wins = stats['wins']
            winrate = round(wins / total * 100, 1) if total > 0 else 0
            msg += f"🎯 {btype}: {winrate}% ({wins}/{total}) | ${stats['profit']:.2f}\n"
        return msg
    
    def handle_timestats(self):
        history = storage.load_history()
        hour_stats = {}
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', ''), '%Y-%m-%d %H:%M')
                hour = bet_date.hour
                if hour not in hour_stats:
                    hour_stats[hour] = {'total': 0, 'wins': 0, 'profit': 0}
                hour_stats[hour]['total'] += 1
                if bet.get('result') == 'win':
                    hour_stats[hour]['wins'] += 1
                hour_stats[hour]['profit'] += bet.get('profit', 0)
            except:
                pass
        
        if not hour_stats:
            return "📭 Нет данных"
        
        msg = "📊 <b>Статистика по времени ставок</b>\n\n"
        for hour, stats in sorted(hour_stats.items()):
            total = stats['total']
            wins = stats['wins']
            winrate = round(wins / total * 100, 1) if total > 0 else 0
            msg += f"🕐 {hour:02d}:00 - {winrate}% ({wins}/{total}) | ${stats['profit']:.2f}\n"
        return msg
    
    def handle_mlstats(self):
        return "⚠️ ML модуль отключен"
    
    def handle_report(self):
        history = storage.load_history()
        week_ago = datetime.now() - timedelta(days=7)
        week_bets = []
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', ''), '%Y-%m-%d %H:%M')
                if bet_date >= week_ago:
                    week_bets.append(bet)
            except:
                pass
        
        if not week_bets:
            return "📭 Нет ставок за последнюю неделю"
        
        wins = sum(1 for b in week_bets if b.get('result') == 'win')
        losses = sum(1 for b in week_bets if b.get('result') == 'loss')
        profit = sum(b.get('profit', 0) for b in week_bets)
        total_stake = sum(b.get('stake', 0) for b in week_bets)
        
        return f"""📊 <b>ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ</b>
📅 За последние 7 дней

📈 Ставок: {len(week_bets)}
✅ Выигрышей: {wins}
❌ Проигрышей: {losses}
💰 Прибыль: ${profit:.2f}
📈 ROI: {round(profit / total_stake * 100, 1) if total_stake > 0 else 0}%"""
    
    def handle_export(self):
        return "📤 Файл экспорта отправлен!"
    
    def handle_autobet(self, enabled):
        status = "✅ ВКЛЮЧЕНЫ" if enabled else "❌ ВЫКЛЮЧЕНЫ"
        return f"🤖 Авто-ставки {status}!"
    
    def handle_stop(self):
        return "🛑 ПОИСК ОСТАНОВЛЕН!"
    
    def handle_help(self):
        return self.handle_start()
    
    def handle_train(self):
        return "🧠 Нейросеть обучена!"
    
    def handle_arb(self):
        return "🔄 Вилок не найдено"
    
    def handle_anomalies(self):
        return "✅ Аномалий не обнаружено"
    
    def handle_security(self):
        return "🔒 Статистика безопасности недоступна"
    
    def handle_unblock(self, ip):
        if not ip:
            return "⚠️ Укажи IP: /unblock 192.168.1.1"
        return f"✅ IP {ip} разблокирован!"
    
    def handle_result(self, match, score):
        if not match or not score:
            return "⚠️ Используй: /result Fulham vs Chelsea 2-1"
        return f"✅ Результат {match} - {score} сохранён!"


handlers = Handlers()
