import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request
import time
import os
from datetime import datetime

from app.config import Config
from app.database.storage import storage
from app.api.football import football_api
from app.api.weather import weather_api
from app.analytics.xg import xg_analyzer
from app.analytics.probability import calculate_probabilities, calculate_ev, get_bet_types, predict_half_goals, predict_exact_score, predict_corners, predict_yellow_cards
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.ml.predictor import ml_predictor
from app.ml.neural_network import neural_net
from app.betting.auto_bet import auto_bet
from app.scheduler import start_scheduler

logger = get_logger(__name__)
app = Flask(__name__)

search_running = False

def send_telegram(text: str, parse_mode: str = 'HTML'):
    import requests
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id': Config.ADMIN_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Send error: {e}")

# ============ ЭКСПОРТ В EXCEL ============
def export_to_excel():
    """Экспорт истории ставок в Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    import io
    
    history = storage.load_history()
    
    if not history:
        return None, "📭 Нет данных для экспорта"
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Ставки"
    
    headers = ["Дата", "Матч", "Лига", "Ставка", "Коэф", "EV%", "Сумма", "Результат", "Прибыль"]
    ws.append(headers)
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    
    total_profit = 0
    for bet in history:
        date = bet.get('date', '')
        home = bet.get('home', '')
        away = bet.get('away', '')
        league = bet.get('league', '')
        bet_type = bet.get('bet', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', 0)
        stake = bet.get('stake', 0)
        result = bet.get('result', 'pending')
        
        if result == 'win':
            profit = round(stake * (odds - 1), 2)
            total_profit += profit
        elif result == 'loss':
            profit = -round(stake, 2)
            total_profit += profit
        else:
            profit = 0
        
        ws.append([date, f"{home} vs {away}", league, bet_type, odds, ev, stake, result, profit])
    
    ws.append([])
    ws.append(["ИТОГО", "", "", "", "", "", "", "", round(total_profit, 2)])
    
    for col in range(1, len(headers) + 1):
        column_letter = chr(64 + col)
        ws.column_dimensions[column_letter].width = 15
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output, f"✅ Экспорт завершен! Всего ставок: {len(history)}, Прибыль: ${round(total_profit, 2)}"
# ============ КОНЕЦ ЭКСПОРТА ============

def send_match_with_buttons(match, index):
    if not match:
        return
    
    league = match.get('league', 'Неизвестная лига')
    is_weak = any(weak in league for weak in Config.WEAK_LEAGUES)
    weak_tag = " ⚠️ СЛАБАЯ!" if is_weak else ""
    
    msg = f"🏟️ <b>{index}. {match['home']} vs {match['away']}</b>\n"
    msg += f"   🏆 {league}{weak_tag}\n"
    msg += f"   ⏰ {match.get('match_time', '⏰ Время не указано')}\n"
    msg += f"   📊 xG: {match['home_xg']} : {match['away_xg']}\n"
    msg += f"   🌤️ {match.get('weather_reason', '☀️ Без погоды')}\n\n"
    
    bets = match.get('bets', [])
    if bets:
        for j, bet in enumerate(bets[:3], 1):
            emoji = ["🥇", "🥈", "🥉"][j-1]
            ev_emoji = "✅" if bet['ev'] > 5 else "⚠️" if bet['ev'] > 0 else "❌"
            msg += f"   {emoji} {bet['label']} | КЭФ: {bet['odds']} | EV: {bet['ev']}% {ev_emoji}\n"
    
    # Прогноз по таймам
    half_goals = predict_half_goals(match['home_xg'], match['away_xg'])
    msg += f"\n📊 <b>По таймам:</b>\n"
    msg += f"   1-й тайм: {half_goals['first_half']['home_xg']}:{half_goals['first_half']['away_xg']} (гол {half_goals['first_half']['goal_probability']}%)\n"
    msg += f"   2-й тайм: {half_goals['second_half']['home_xg']}:{half_goals['second_half']['away_xg']} (гол {half_goals['second_half']['goal_probability']}%)\n"
    
    # Прогноз точного счета
    exact_scores = predict_exact_score(match['home_xg'], match['away_xg'])
    msg += f"\n🎯 <b>Точный счет (топ-5):</b>\n"
    for score, prob in exact_scores.items():
        msg += f"   {score} — {prob}%\n"
    
    # Прогноз угловых
    corners = predict_corners(match['home_xg'], match['away_xg'])
    msg += f"\n📐 <b>Угловые:</b>\n"
    msg += f"   Тотал: {corners['total']}\n"
    msg += f"   Тотал > 8.5: {corners['over_8_5']}%\n"
    msg += f"   Тотал > 10.5: {corners['over_10_5']}%\n"
    
    # ===== ЖЕЛТЫЕ КАРТОЧКИ =====
    try:
        home_id = match.get('factors', {}).get('home_id')
        away_id = match.get('factors', {}).get('away_id')
        
        if home_id and away_id:
            home_cards = football_api.get_team_cards_stats(home_id)
            away_cards = football_api.get_team_cards_stats(away_id)
            
            referee = match.get('factors', {}).get('referee')
            referee_stats = None
            if referee:
                referee_stats = football_api.get_referee_stats(referee)
            
            cards = predict_yellow_cards(home_cards, away_cards, referee_stats)
            
            msg += f"\n🟨 <b>Желтые карточки:</b>\n"
            msg += f"   Тотал: {cards['total']}\n"
            msg += f"   Тотал > 3.5: {cards['over_3_5']}%\n"
            msg += f"   Тотал > 4.5: {cards['over_4_5']}%\n"
            msg += f"   Тотал > 5.5: {cards['over_5_5']}%\n"
            msg += f"   Хозяева: {cards['home_avg']} | Гости: {cards['away_avg']}"
            
            if referee:
                msg += f"\n   🧑‍⚖️ Судья: {referee}"
    except Exception as e:
        logger.warning(f"Ошибка прогноза карточек: {e}")
    
    if is_weak:
        msg += "\n⚠️ <b>СЛАБАЯ ЛИГА!</b> Бот может ошибаться на ОЗ - ДА."
    
    msg += "\n\n📌 <b>Выбери результат матча (для обучения):</b>"
    
    match_id = f"{match['fixture_id']}_{int(time.time())}"
    
    keyboard = [
        [{"text": "🏠 Победа хозяев", "callback_data": f"result_home_{match_id}"}],
        [{"text": "✈️ Победа гостей", "callback_data": f"result_away_{match_id}"}],
        [{"text": "🤝 Ничья", "callback_data": f"result_draw_{match_id}"}],
        [{"text": "❌ Пропустить", "callback_data": f"result_skip_{match_id}"}]
    ]
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": Config.ADMIN_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": keyboard}
        }
        requests.post(url, json=data, timeout=10)
        logger.info(f"✅ ОТПРАВЛЕН МАТЧ {index}")
    except Exception as e:
        logger.error(f"Send error: {e}")

def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    for league_id in Config.LEAGUES:
        try:
            matches = football_api.get_matches(league_id, today)
            league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
            
            if matches:
                for match in matches:
                    if match["fixture"]["status"]["short"] == "NS":
                        match_id = match["fixture"]["id"]
                        if match_id not in [m["fixture"]["id"] for m in all_matches]:
                            home_id = match["teams"]["home"]["id"]
                            away_id = match["teams"]["away"]["id"]
                            
                            match["factors"] = {
                                "home_form": football_api.get_form(home_id),
                                "away_form": football_api.get_form(away_id),
                                "home_injuries_list": football_api.get_injuries(home_id),
                                "away_injuries_list": football_api.get_injuries(away_id),
                                "home_id": home_id,
                                "away_id": away_id,
                                "referee": match.get("fixture", {}).get("referee")
                            }
                            
                            city = match.get("fixture", {}).get("venue", {}).get("city", "")
                            if city:
                                weather = weather_api.get_weather(city)
                                if weather:
                                    impact, reason = weather_api.get_impact(weather)
                                    match["weather"] = weather
                                    match["weather_reason"] = reason
                            else:
                                match["weather"] = None
                                match["weather_reason"] = "☀️ Город неизвестен"
                            
                            match["league"]["name"] = league_name
                            all_matches.append(match)
            else:
                logger.info(f"⚠️ Нет матчей в {league_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка {league_name}: {e}")
        
        time.sleep(0.3)
    
    return all_matches

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    
    for match in matches:
        try:
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            league = match["league"]["name"]
            fixture_id = match["fixture"]["id"]
            factors = match.get("factors", {})
            
            match_time = match.get("fixture", {}).get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            home_xg, away_xg, reasons = xg_analyzer.calculate_xg(match, fixture_id)
            
            # Нейросеть или ML
            try:
                neural_home, neural_away = neural_net.predict_xg(factors)
                if neural_home and neural_away:
                    home_xg = neural_home
                    away_xg = neural_away
                    logger.info("🧠 Используем нейросеть для прогноза")
                else:
                    home_xg, away_xg = ml_predictor.predict_xg(factors)
                    logger.info("📊 Используем ML для прогноза")
            except Exception as e:
                logger.warning(f"Ошибка нейросети: {e}")
                home_xg, away_xg = ml_predictor.predict_xg(factors)
                logger.info("📊 Используем ML для прогноза")
            
            probs = calculate_probabilities(home_xg, away_xg)
            
            match_data = {
                "home": home,
                "away": away,
                "league": league,
                "fixture_id": fixture_id,
                "match_time": match_time,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "weather_reason": match.get("weather_reason", "☀️ Без погоды"),
                "factors": factors,
                "bets": []
            }
            
            for bet_type, odds, label in get_bet_types():
                prob = probs.get(bet_type, 0)
                if prob < 0.05 or prob > 0.99:
                    continue
                
                ev = calculate_ev(prob, odds)
                if ev > 5:
                    stake = min(bank * (ev/100) * 0.3, bank * 0.05)
                    match_data["bets"].append({
                        "bet_type": bet_type,
                        "label": label,
                        "odds": odds,
                        "prob": round(prob * 100, 1),
                        "ev": round(ev, 1),
                        "stake": round(stake, 2),
                    })
            
            if match_data["bets"]:
                match_data["bets"].sort(key=lambda x: x['ev'], reverse=True)
                all_matches_data.append(match_data)
                
                # Авто-ставка
                try:
                    bet_result = auto_bet.check_and_bet(match_data)
                    if bet_result:
                        msg = f"🤖 <b>АВТО-СТАВКА СДЕЛАНА!</b>\n"
                        msg += f"🏟️ {bet_result['match']}\n"
                        msg += f"📊 {bet_result['bet']} | КЭФ: {bet_result['odds']}\n"
                        msg += f"💰 Сумма: ${bet_result['stake']}\n"
                        msg += f"📈 EV: {bet_result['ev']}%"
                        send_telegram(msg)
                except Exception as e:
                    logger.error(f"Ошибка авто-ставки: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            continue
    
    all_matches_data.sort(key=lambda x: x['bets'][0]['ev'] if x['bets'] else 0, reverse=True)
    return all_matches_data[:5]

@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running
    
    try:
        data = request.get_json()
        if not data:
            return "ok", 200
        
        if 'callback_query' in data:
            return "ok", 200
        
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            if str(chat_id) != Config.ADMIN_CHAT_ID:
                send_telegram("⛔ Нет доступа")
                return "ok", 200
            
            # ============================================================
            # ОБРАБОТКА ВСЕХ КОМАНД
            # ============================================================
            
            if text == '/start':
                send_telegram(handlers.handle_start())
            
            elif text == '/update':
                if search_running:
                    send_telegram("⚠️ Поиск уже запущен!")
                else:
                    search_running = True
                    send_telegram("🔄 Поиск матчей...")
                    
                    matches = get_matches_with_factors()
                    if matches:
                        top_matches = find_top_matches(matches)
                        if top_matches:
                            for i, match in enumerate(top_matches, 1):
                                send_match_with_buttons(match, i)
                                time.sleep(0.5)
                            send_telegram(f"✅ Найдено {len(top_matches)} матчей!")
                        else:
                            send_telegram("❌ Ставок не найдено")
                    else:
                        send_telegram("❌ Матчей не найдено")
                    
                    search_running = False
            
            elif text == '/stop':
                search_running = False
                send_telegram("🛑 ПОИСК ОСТАНОВЛЕН!")
            
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            
            elif text == '/learn':
                send_telegram(handlers.handle_learn())
            
            elif text == '/help':
                send_telegram(handlers.handle_start())
            
            elif text == '/team':
                try:
                    parts = text.split()
                    if len(parts) > 1:
                        team_name = ' '.join(parts[1:])
                        send_telegram(handlers.handle_team_stats(team_name))
                    else:
                        send_telegram("📝 Напишите: /team <название команды>\n\nПример: /team Real Madrid")
                except Exception as e:
                    logger.error(f"Ошибка /team: {e}")
                    send_telegram("❌ Ошибка. Напишите: /team Real Madrid")
            
            elif text == '/bettypes':
                send_telegram(handlers.handle_bet_type_stats())
            
            elif text == '/timestats':
                send_telegram(handlers.handle_time_stats())
            
            elif text == '/mlstats':
                stats = ml_predictor.get_stats()
                if isinstance(stats, str):
                    send_telegram(stats)
                else:
                    msg = f"""🧠 <b>СТАТИСТИКА МАШИННОГО ОБУЧЕНИЯ</b>

📊 Обработано матчей: {stats['total_matches']}
🎯 Средняя ошибка xG: {stats['avg_home_error']} : {stats['avg_away_error']}
📈 Точность (последние 10): {stats['last_10_accuracy']}%"""
                    send_telegram(msg)
            
            elif text == '/export':
                file, message = export_to_excel()
                if file:
                    send_telegram(message)
                    import requests
                    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                    files = {'document': ('history.xlsx', file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                    data = {'chat_id': Config.ADMIN_CHAT_ID, 'caption': '📊 История ставок'}
                    try:
                        requests.post(url, files=files, data=data, timeout=30)
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла: {e}")
                else:
                    send_telegram(message)
            
            elif text == '/autobet':
                auto_bet.enabled = not getattr(auto_bet, 'enabled', True)
                status = "ВКЛЮЧЕНЫ" if auto_bet.enabled else "ВЫКЛЮЧЕНЫ"
                send_telegram(f"🤖 Авто-ставки {status}!")
            
            elif text == '/train':
                history = storage.load_history()
                if len(history) < 50:
                    send_telegram(f"⚠️ Недостаточно данных. Нужно 50+ матчей (есть {len(history)})")
                else:
                    send_telegram("🧠 Начинаю обучение нейросети...")
                    result = neural_net.train(history)
                    if result:
                        send_telegram(f"✅ Нейросеть обучена на {len(history)} матчах!")
                    else:
                        send_telegram("❌ Ошибка обучения нейросети")
            
            elif text == '/report':
                from app.scheduler import send_weekly_report
                send_weekly_report()
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "ok", 200

@app.route('/', methods=['GET'])
def index():
    return f"🤖 Quantum Bot v12 PRO | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    setup_logging()
    start_scheduler()
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН С ВСЕМИ УЛУЧШЕНИЯМИ!")
    app.run(host='0.0.0.0', port=port)
