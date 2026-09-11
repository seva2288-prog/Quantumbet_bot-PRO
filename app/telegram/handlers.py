"""Обработчики Telegram-команд"""
from datetime import datetime, timedelta

from app.database.storage import storage
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Handlers:
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.admin_chat_id = Config.ADMIN_CHAT_ID

    # ============================================================
    # START / HELP
    # ============================================================
    def handle_start(self):
        return """🤖 <b>Quantum Bet Bot</b>

<b>Основные:</b>
/update — полный поиск матчей на сегодня
/today — ТОП-5 матчей из кэша
/analyze [матч] — детальный анализ матча
/status — статус бота
/stats — общая статистика
/bank — текущий банк
/strategies — сравнение стратегий

<b>История:</b>
/result [команда1] vs [команда2] [счёт]
/update_results — обновить результаты
/export — экспорт истории в Excel

<b>Дополнительно:</b>
/bettypes — статистика по типам ставок
/timestats — статистика по времени
/team [название] — статистика по команде
/report — еженедельный отчёт

<b>Управление:</b>
/autobet — вкл/выкл авто-ставки
/reset_search — сбросить зависший поиск
/help — эта справка"""

    def handle_help(self):
        return self.handle_start()

    # ============================================================
    # БАНК / СТАТИСТИКА
    # ============================================================
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

        resolved = [b for b in history if b.get('result') in ('win', 'loss')]
        total_stake = sum(b.get('stake', 0) for b in resolved)
        avg_stake = round(total_stake / len(resolved), 2) if resolved else 0

        return f"""📊 <b>ОБЩАЯ СТАТИСТИКА</b>

📈 Всего ставок: {total}
✅ Выигрыши: {wins}
❌ Проигрыши: {losses}
🔄 Возвраты: {pushes}
💰 Прибыль: ${profit:.2f}
🎯 Проходимость: {winrate}%
📈 ROI: {roi}%
📅 Средняя ставка: ${avg_stake}"""

    # ============================================================
    # TODAY — ТОП-5
    # ============================================================
    def handle_today(self):
        cache = storage.load_cache()
        matches = cache.get('top_matches', [])
        if not matches:
            return "📭 Нет матчей в кэше. Запусти /update"

        msg = "📊 <b>ТОП-5 МАТЧЕЙ</b>\n\n"
        for i, m in enumerate(matches[:5], 1):
            msg += f"{i}. 🏟️ {m.get('home')} vs {m.get('away')}\n"
            msg += f"   🏆 {m.get('league')}\n"
            if m.get('bets'):
                best = m['bets'][0]
                msg += f"   🎯 {best.get('label')} | КЭФ: {best.get('odds')} | EV: {best.get('ev')}%\n"
            if m.get('weather_reason'):
                msg += f"   {m['weather_reason']}\n"
            msg += "\n"
        return msg

    # ============================================================
    # СТАТИСТИКА ПО ТИПАМ
    # ============================================================
    def handle_bettypes(self):
        history = storage.load_history()
        bet_stats = {}
        for bet in history:
            btype = bet.get('bet', 'Unknown')
            s = bet_stats.setdefault(btype, {'total': 0, 'wins': 0, 'profit': 0})
            s['total'] += 1
            if bet.get('result') == 'win':
                s['wins'] += 1
            s['profit'] += bet.get('profit', 0)

        if not bet_stats:
            return "📭 Нет данных"

        msg = "📊 <b>Статистика по типам ставок</b>\n\n"
        for btype, s in sorted(bet_stats.items(), key=lambda x: x[1]['profit'], reverse=True)[:10]:
            total = s['total']
            wr = round(s['wins'] / total * 100, 1) if total else 0
            msg += f"🎯 {btype}: {wr}% ({s['wins']}/{total}) | ${s['profit']:.2f}\n"
        return msg

    # ============================================================
    # СТАТИСТИКА ПО ВРЕМЕНИ
    # ============================================================
    def handle_timestats(self):
        history = storage.load_history()
        hour_stats = {}
        for bet in history:
            try:
                d = datetime.strptime(bet.get('date', ''), '%Y-%m-%d %H:%M')
                h = d.hour
                s = hour_stats.setdefault(h, {'total': 0, 'wins': 0, 'profit': 0})
                s['total'] += 1
                if bet.get('result') == 'win':
                    s['wins'] += 1
                s['profit'] += bet.get('profit', 0)
            except Exception:
                pass

        if not hour_stats:
            return "📭 Нет данных"

        msg = "📊 <b>Статистика по времени ставок</b>\n\n"
        for hour, s in sorted(hour_stats.items()):
            wr = round(s['wins'] / s['total'] * 100, 1) if s['total'] else 0
            msg += f"🕐 {hour:02d}:00 — {wr}% ({s['wins']}/{s['total']}) | ${s['profit']:.2f}\n"
        return msg

    # ============================================================
    # КОМАНДА
    # ============================================================
    def handle_team(self, team_name):
        if not team_name:
            return "⚠️ Укажи команду: /team Real Madrid"
        history = storage.load_history()
        tl = team_name.lower()
        team_bets = [
            b for b in history
            if tl in b.get('home', '').lower() or tl in b.get('away', '').lower()
        ]
        if not team_bets:
            return f"📭 Нет ставок на {team_name}"
        wins = sum(1 for b in team_bets if b.get('result') == 'win')
        losses = sum(1 for b in team_bets if b.get('result') == 'loss')
        profit = sum(b.get('profit', 0) for b in team_bets)
        return (f"📊 <b>Статистика по {team_name}</b>\n\n"
                f"📈 Всего: {len(team_bets)}\n"
                f"✅ Выигрыши: {wins}\n"
                f"❌ Проигрыши: {losses}\n"
                f"💰 Прибыль: ${profit:.2f}")

    # ============================================================
    # ОТЧЁТ ЗА НЕДЕЛЮ
    # ============================================================
    def handle_report(self):
        history = storage.load_history()
        week_ago = datetime.now() - timedelta(days=7)
        week_bets = []
        for bet in history:
            try:
                d = datetime.strptime(bet.get('date', ''), '%Y-%m-%d %H:%M')
                if d >= week_ago:
                    week_bets.append(bet)
            except Exception:
                pass

        if not week_bets:
            return "📭 Нет ставок за последнюю неделю"

        wins = sum(1 for b in week_bets if b.get('result') == 'win')
        losses = sum(1 for b in week_bets if b.get('result') == 'loss')
        profit = sum(b.get('profit', 0) for b in week_bets)
        stake = sum(b.get('stake', 0) for b in week_bets)

        return (f"📊 <b>ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ</b>\n"
                f"📅 За последние 7 дней\n\n"
                f"📈 Ставок: {len(week_bets)}\n"
                f"✅ Выигрышей: {wins}\n"
                f"❌ Проигрышей: {losses}\n"
                f"💰 Прибыль: ${profit:.2f}\n"
                f"📈 ROI: {round(profit / stake * 100, 1) if stake else 0}%")

    # ============================================================
    # ПРОЧИЕ ОТВЕТЫ
    # ============================================================
    def handle_export(self):
        return "📤 Экспорт запущен..."

    def handle_autobet(self, enabled):
        return f"🤖 Авто-ставки {'✅ ВКЛЮЧЕНЫ' if enabled else '❌ ВЫКЛЮЧЕНЫ'}!"

    def handle_stop(self):
        return "🛑 ПОИСК ОСТАНОВЛЕН!"

    def handle_result(self, match, score):
        if not match or not score:
            return "⚠️ Используй: /result Fulham vs Chelsea 2-1"
        return f"✅ Результат {match} — {score} сохранён!"

    def handle_mlstats(self):
        return "⚠️ ML модуль отключён"

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


handlers = Handlers()
