"""Персонализация: анализ истории ставок пользователя"""
from collections import defaultdict
from datetime import datetime, timedelta

from app.database.storage import storage
from app.utils.logger import get_logger

logger = get_logger(__name__)


def analyze_history() -> dict:
    """Анализ истории ставок по лигам, типам, дням."""
    history = storage.load_history()
    
    if len(history) < 5:
        return {'error': 'Слишком мало данных (нужно ≥ 5 ставок)'}
    
    # Фильтруем только завершённые
    resolved = [b for b in history if b.get('result') in ('win', 'loss')]
    
    if len(resolved) < 3:
        return {'error': 'Мало завершённых ставок (нужно ≥ 3)'}
    
    # === По лигам ===
    leagues = defaultdict(lambda: {'total': 0, 'wins': 0, 'profit': 0.0})
    for b in resolved:
        lg = b.get('league', 'Unknown')
        leagues[lg]['total'] += 1
        if b.get('result') == 'win':
            leagues[lg]['wins'] += 1
        leagues[lg]['profit'] += b.get('profit', 0)
    
    league_stats = []
    for lg, d in leagues.items():
        wr = (d['wins'] / d['total'] * 100) if d['total'] > 0 else 0
        league_stats.append({
            'league': lg,
            'total': d['total'],
            'wins': d['wins'],
            'winrate': round(wr, 1),
            'profit': round(d['profit'], 2)
        })
    
    league_stats.sort(key=lambda x: x['profit'], reverse=True)
    
    # === По типам ставок ===
    bet_types = defaultdict(lambda: {'total': 0, 'wins': 0, 'profit': 0.0})
    for b in resolved:
        bt = b.get('bet', 'Unknown')
        bet_types[bt]['total'] += 1
        if b.get('result') == 'win':
            bet_types[bt]['wins'] += 1
        bet_types[bt]['profit'] += b.get('profit', 0)
    
    type_stats = []
    for bt, d in bet_types.items():
        wr = (d['wins'] / d['total'] * 100) if d['total'] > 0 else 0
        type_stats.append({
            'bet_type': bt,
            'total': d['total'],
            'wins': d['wins'],
            'winrate': round(wr, 1),
            'profit': round(d['profit'], 2)
        })
    
    type_stats.sort(key=lambda x: x['profit'], reverse=True)
    
    # === По дням ===
    daily = defaultdict(lambda: {'bets': 0, 'profit': 0.0})
    for b in resolved:
        try:
            d = b.get('date', '').split()[0]
            daily[d]['bets'] += 1
            daily[d]['profit'] += b.get('profit', 0)
        except Exception:
            pass
    
    daily_stats = sorted(
        [{'date': d, 'bets': s['bets'], 'profit': round(s['profit'], 2)}
         for d, s in daily.items()],
        key=lambda x: x['date']
    )
    
    # === Общая статистика ===
    total = len(resolved)
    wins = sum(1 for b in resolved if b.get('result') == 'win')
    total_profit = sum(b.get('profit', 0) for b in resolved)
    total_stake = sum(b.get('stake', 0) for b in resolved)
    avg_stake = total_stake / total if total > 0 else 0
    
    # Лучший и худший день
    best_day = max(daily_stats, key=lambda x: x['profit']) if daily_stats else None
    worst_day = min(daily_stats, key=lambda x: x['profit']) if daily_stats else None
    
    return {
        'total': total,
        'wins': wins,
        'losses': total - wins,
        'winrate': round(wins / total * 100, 1) if total > 0 else 0,
        'total_profit': round(total_profit, 2),
        'avg_stake': round(avg_stake, 2),
        'roi': round(total_profit / total_stake * 100, 1) if total_stake > 0 else 0,
        'leagues': league_stats,
        'bet_types': type_stats,
        'daily': daily_stats[-14:],  # последние 14 дней
        'best_day': best_day,
        'worst_day': worst_day,
    }


def build_personal_report() -> str:
    """Формирует текстовый отчёт для Telegram."""
    data = analyze_history()
    
    if 'error' in data:
        return f"📊 <b>ПЕРСОНАЛЬНАЯ СТАТИСТИКА</b>\n\n⚠️ {data['error']}"
    
    msg = "📊 <b>ПЕРСОНАЛЬНАЯ СТАТИСТИКА</b>\n\n"
    
    # Общая статистика
    msg += f"<b>💰 ОБЩЕЕ:</b>\n"
    msg += f"📈 Всего ставок: {data['total']}\n"
    msg += f"✅ Побед: {data['wins']}\n"
    msg += f"❌ Проигрышей: {data['losses']}\n"
    msg += f"🎯 Winrate: {data['winrate']}%\n"
    msg += f"💵 Прибыль: ${data['total_profit']}\n"
    msg += f"📊 ROI: {data['roi']}%\n"
    msg += f"💸 Средняя ставка: ${data['avg_stake']}\n\n"
    
    # Топ-3 лиги
    leagues = data.get('leagues', [])
    if leagues:
        msg += "<b>🏆 ЛУЧШИЕ ЛИГИ:</b>\n"
        for lg in leagues[:3]:
            if lg['profit'] > 0:
                msg += f"✅ {lg['league']}: {lg['total']} ставок, WR {lg['winrate']}%, +${lg['profit']}\n"
        msg += "\n"
        
        msg += "<b>❌ ХУДШИЕ ЛИГИ:</b>\n"
        for lg in leagues[-3:]:
            if lg['profit'] < 0:
                msg += f"⚠️ {lg['league']}: {lg['total']} ставок, WR {lg['winrate']}%, ${lg['profit']}\n"
        msg += "\n"
    
    # Топ-3 типа ставок
    types = data.get('bet_types', [])
    if types:
        msg += "<b>🎯 ЛУЧШИЕ ТИПЫ:</b>\n"
        for t in types[:3]:
            if t['profit'] > 0:
                msg += f"✅ {t['bet_type']}: {t['total']} ставок, WR {t['winrate']}%, +${t['profit']}\n"
        msg += "\n"
        
        msg += "<b>⚠️ ХУДШИЕ ТИПЫ:</b>\n"
        for t in types[-3:]:
            if t['profit'] < 0:
                msg += f"❌ {t['bet_type']}: {t['total']} ставок, WR {t['winrate']}%, ${t['profit']}\n"
        msg += "\n"
    
    # Лучший/худший день
    if data.get('best_day'):
        bd = data['best_day']
        msg += f"🟢 Лучший день: {bd['date']} (+${bd['profit']})\n"
    if data.get('worst_day'):
        wd = data['worst_day']
        msg += f"🔴 Худший день: {wd['date']} (${wd['profit']})\n"
    
    return msg


def get_personal_recommendations() -> str:
    """Рекомендации на основе истории (через DeepSeek)."""
    data = analyze_history()
    
    if 'error' in data:
        return f"⚠️ {data['error']}"
    
    leagues = data.get('leagues', [])
    types = data.get('bet_types', [])
    
    # Формируем промпт для DeepSeek
    from app.llm import _get_client
    from app.config import Config
    
    if not Config.LLM_ENABLED:
        return "⚠️ LLM отключён — рекомендации недоступны"
    
    league_text = "\n".join([
        f"- {lg['league']}: {lg['total']} ставок, WR {lg['winrate']}%, profit ${lg['profit']}"
        for lg in leagues[:10]
    ])
    
    type_text = "\n".join([
        f"- {t['bet_type']}: {t['total']} ставок, WR {t['winrate']}%, profit ${t['profit']}"
        for t in types[:10]
    ])
    
    prompt = f"""Ты — аналитик ставок. Проанализируй мою историю и дай 3-5 конкретных рекомендаций.

Статистика:
Всего ставок: {data['total']}
Winrate: {data['winrate']}%
ROI: {data['roi']}%
Прибыль: ${data['total_profit']}

По лигам:
{league_text}

По типам ставок:
{type_text}

Дай КОНКРЕТНЫЕ рекомендации:
1. На какие лиги ставить (WR > 55% и profit > 0)
2. Какие лиги избегать (WR < 40% или profit < 0)
3. Какие типы ставок работают
4. Какие типы ставок не работают

Отвечай кратко, 5-10 строк. Без JSON, просто текст."""

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка рекомендаций: {e}")
        return f"⚠️ Ошибка DeepSeek: {e}"


def schedule_weekly_personal_report():
    """Раз в неделю отправляет персональный отчёт."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.database.storage import storage
    
    def send_report():
        try:
            from main import send_telegram
            report = build_personal_report()
            send_telegram(report)
            logger.info("📊 Персональный отчёт отправлен")
        except Exception as e:
            logger.error(f"Ошибка персонального отчёта: {e}")
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=send_report,
        trigger='cron',
        day_of_week='mon',
        hour=10,
        minute=0,
        id='weekly_personal_report',
        replace_existing=True
    )
    scheduler.start()
    logger.info("⏰ Персональный отчёт: каждый понедельник в 10:00")
