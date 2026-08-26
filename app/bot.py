import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
import time
import os
import json
from datetime import datetime, timedelta

from app.config import Config
from app.database.storage import storage
from app.api.football import football_api
from app.api.weather import weather_api
from app.analytics.xg import xg_analyzer
from app.analytics.probability import calculate_probabilities, calculate_ev, get_bet_types, predict_half_goals, predict_exact_score, predict_corners, predict_yellow_cards
from app.analytics.arbitrage import arbitrage_analyzer
from app.analytics.anomalies import anomaly_detector
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.ml.predictor import ml_predictor
# from app.ml.neural_network import neural_net  # Временно отключена
from app.betting.auto_bet import auto_bet
from app.scheduler import start_scheduler
from app.security.auth import security

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
    
    headers = ["Дата", "Матч", "Счёт", "Ставка", "Коэф", "EV%", "Сумма", "Результат", "Прибыль"]
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
        home_goals = bet.get('home_goals', '')
        away_goals = bet.get('away_goals', '')
        score = f"{home_goals}-{away_goals}" if home_goals is not None and away_goals is not None else "-"
        bet_type = bet.get('bet', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', 0)
        stake = bet.get('stake', 0)
        result = bet.get('result', 'pending')
        profit = bet.get('profit', 0)
        
        if result == 'win':
            profit = round(stake * (odds - 1), 2) if profit == 0 else profit
            total_profit += profit
        elif result == 'loss':
            profit = -round(stake, 2) if profit == 0 else profit
            total_profit += profit
        else:
            profit = 0
        
        ws.append([date, f"{home} vs {away}", score, bet_type, odds, ev, stake, result, profit])
    
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
    
    # ===== ЧУТЬЁ (ИНТУИЦИЯ) =====
    intuition = match.get('intuition', [])
    if intuition:
        msg += "\n🧠 <b>Чутьё:</b>\n"
        for reason in intuition[:5]:
            msg += f"   {reason}\n"
    
    if is_weak:
        msg += "\n⚠️ <b>СЛАБАЯ ЛИГА!</b> Бот может ошибаться на ОЗ - ДА."
    
    msg += "\n\n📌 <b>Выбери результат матча (для обучения):</b>"
    
    match_id = f"{match['fixture_id']}_{int(time.time())}"
    
    # ===== СОХРАНЯЕМ МАТЧ В КЭШ =====
    try:
        cache = storage.load_cache()
        if not cache:
            cache = {}
        cache[f"match_{match_id}"] = match
        storage.save_cache(cache)
        logger.info(f"💾 Сохранён матч в кэш: {match_id}")
        logger.info(f"📋 Матч: {match['home']} vs {match['away']}")
        
        # Дублируем сохранение в отдельный файл
        try:
            with open(f"data/match_{match_id}.json", 'w') as f:
                json.dump(match, f)
            logger.info(f"💾 Сохранён матч в файл: match_{match_id}.json")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в файл: {e}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения в кэш: {e}")
    
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

# ============================================================
# ИСПРАВЛЕННАЯ ФУНКЦИЯ: ПОИСК МАТЧЕЙ НА 3 ДНЯ ВПЕРЕД
# ============================================================

def get_matches_with_factors():
    all_matches = []
    # ===== ИЩЕМ НА 3 ДНЯ ВПЕРЕД =====
    today = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
    logger.info(f"🔍 Поиск матчей до: {today}")
    
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
                logger.info(f"🔥 Нет матчей в {league_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка {league_name}: {e}")
        
        time.sleep(0.3)
    
    logger.info(f"📊 Найдено матчей: {len(all_matches)}")
    return all_matches

# ============================================================
# КОНЕЦ ИСПРАВЛЕННОЙ ФУНКЦИИ
# ============================================================

# ============================================================
# ФУНКЦИЯ find_top_matches (20 СТАВОК)
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN

    for match in matches:
        if bets_placed >= max_bets:
            logger.info(f"⚠️ Достигнут лимит ставок за запуск ({max_bets})")
            break

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

            try:
                home_xg, away_xg = ml_predictor.predict_xg(factors)
                logger.info("📊 Используем ML для прогноза")
            except Exception as e:
                logger.warning(f"Ошибка ML: {e}")

            probs = calculate_probabilities(home_xg, away_xg)

            odds_data = football_api.get_match_odds(fixture_id)
            if odds_data:
                logger.info(f"📊 Реальные коэфы: {odds_data}")
            else:
                logger.info("⚠️ Коэфы не получены, используем средние")

            bet_types = get_bet_types(odds_data)

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
                "intuition": reasons,
                "bets": []
            }

            for bet_type, odds, label in bet_types:
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

                try:
                    bet_result = auto_bet.check_and_bet(match_data)
                    if bet_result:
                        bets_placed += 1
                        msg = f"🤖 <b>АВТО-СТАВКА #{bets_placed}</b>\n"
                        msg += f"🏟️ {bet_result['match']}\n"
                        msg += f"📊 {bet_result['bet']} | КЭФ: {bet_result['odds']}\n"
                        msg += f"💰 Сумма: ${bet_result['stake']}\n"
                        msg += f"📈 EV: {bet_result['ev']}%"
                        if bet_result.get('marker_stake'):
                            msg += f"\n🎯 Маркер: ${bet_result['marker_stake']} ({bet_result.get('marker_type', 'unknown')})"
                        send_telegram(msg)
                        logger.info(f"✅ АВТО-СТАВКА #{bets_placed}: {bet_result['bet']} на {bet_result['match']}")
                except Exception as e:
                    logger.error(f"Ошибка авто-ставки: {e}")

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            continue

    all_matches_data.sort(key=lambda x: x['bets'][0]['ev'] if x['bets'] else 0, reverse=True)
    logger.info(f"📊 Найдено {len(all_matches_data)} матчей, сделано {bets_placed} ставок")
    return all_matches_data[:20]

# ============================================================
# КОНЕЦ ФУНКЦИИ find_top_matches
# ============================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running
    
    try:
        data = request.get_json()
        if not data:
            return "ok", 200
        
        if 'callback_query' in data:
            callback = data['callback_query']
            callback_data = callback.get('data', '')
            
            logger.info(f"📨 Нажата кнопка: {callback_data}")
            
            import requests
            answer_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"
            try:
                requests.post(answer_url, json={
                    "callback_query_id": callback.get('id', ''),
                    "text": "✅ Результат сохранён!"
                })
            except Exception as e:
                logger.error(f"Ошибка ответа: {e}")
            
            if callback_data.startswith('result_'):
                logger.info(f"🔍 Обработка результата: {callback_data}")
                
                parts = callback_data.split('_')
                if len(parts) >= 3:
                    result_type = parts[1]
                    match_id = parts[2]
                    
                    logger.info(f"🔍 Тип: {result_type}, ID: {match_id}")
                    
                    match = None
                    
                    cache = storage.load_cache()
                    match = cache.get(f"match_{match_id}")
                    
                    if not match:
                        try:
                            with open(f"data/match_{match_id}.json", 'r') as f:
                                match = json.load(f)
                            logger.info(f"📋 Матч найден в файле: {match_id}")
                        except:
                            pass
                    
                    logger.info(f"🔍 Матч найден: {match is not None}")
                    
                    if match:
                        logger.info(f"📋 Матч: {match.get('home')} vs {match.get('away')}")
                        
                        if result_type != 'skip':
                            bets = match.get('bets', [])
                            if bets:
                                best_bet = bets[0]
                                logger.info(f"📊 Ставка: {best_bet.get('label')}")
                                
                                if result_type == 'home':
                                    result = 'win' if 'Победа хозяев' in best_bet['label'] else 'loss'
                                elif result_type == 'away':
                                    result = 'win' if 'Победа гостей' in best_bet['label'] else 'loss'
                                elif result_type == 'draw':
                                    if '1Х' in best_bet['label'] or '2Х' in best_bet['label']:
                                        result = 'win'
                                    else:
                                        result = 'loss'
                                else:
                                    result = 'loss'
                                
                                logger.info(f"📊 Результат: {result}")
                                
                                try:
                                    history = storage.load_history()
                                    logger.info(f"📋 История до сохранения: {len(history)} записей")
                                    
                                    stake = best_bet.get('stake', 0)
                                    odds = best_bet.get('odds', 1)
                                    
                                    if result == 'win':
                                        profit = round(stake * (odds - 1), 2)
                                    elif result == 'loss':
                                        profit = -stake
                                    else:
                                        profit = 0
                                    
                                    bet_record = {
                                        'home': match.get('home', ''),
                                        'away': match.get('away', ''),
                                        'league': match.get('league', ''),
                                        'bet': best_bet.get('label', ''),
                                        'odds': odds,
                                        'stake': stake,
                                        'ev': best_bet.get('ev', 0),
                                        'result': result,
                                        'profit': profit,
                                        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                        'home_goals': None,
                                        'away_goals': None
                                    }
                                    history.append(bet_record)
                                    storage.save_history(history)
                                    logger.info(f"✅ СОХРАНЕНО В ИСТОРИЮ: {bet_record}")
                                    
                                    check = storage.load_history()
                                    logger.info(f"📋 История после сохранения: {len(check)} записей")
                                    
                                    stats = storage.load_stats()
                                    stats['total'] = stats.get('total', 0) + 1
                                    if result == 'win':
                                        stats['wins'] = stats.get('wins', 0) + 1
                                        stats['total_profit'] = stats.get('total_profit', 0) + profit
                                    elif result == 'loss':
                                        stats['losses'] = stats.get('losses', 0) + 1
                                        stats['total_profit'] = stats.get('total_profit', 0) - stake
                                    else:
                                        stats['pushes'] = stats.get('pushes', 0) + 1
                                    storage.save_stats(stats)
                                    logger.info(f"✅ СТАТИСТИКА: {stats}")
                                    
                                    cache.pop(f"match_{match_id}", None)
                                    storage.save_cache(cache)
                                    try:
                                        os.remove(f"data/match_{match_id}.json")
                                    except:
                                        pass
                                    
                                    msg = f"✅ Результат сохранён!\n{match.get('home')} vs {match.get('away')} → {result}"
                                    if result == 'win':
                                        msg += f"\n💰 Прибыль: +${profit}"
                                    elif result == 'loss':
                                        msg += f"\n💰 Проигрыш: -${stake}"
                                    send_telegram(msg)
                                    
                                except Exception as e:
                                    logger.error(f"❌ Ошибка сохранения: {e}")
                            else:
                                logger.warning(f"⚠️ Нет ставок в матче")
                        else:
                            logger.info(f"⏭️ Пропущен матч")
                            cache.pop(f"match_{match_id}", None)
                            storage.save_cache(cache)
                            try:
                                os.remove(f"data/match_{match_id}.json")
                            except:
                                pass
                    else:
                        logger.warning(f"⚠️ Матч не найден в кэше: {match_id}")
            
            return "ok", 200
        
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            if str(chat_id) != Config.ADMIN_CHAT_ID:
                send_telegram("⛔ Нет доступа")
                return "ok", 200
            
            if text == '/start':
                send_telegram(handlers.handle_start())
            
            elif text == '/update':
                if search_running:
                    send_telegram("⚠️ Поиск уже запущен!")
                else:
                    search_running = True
                    start_time = datetime.now()
                    send_telegram(f"🔄 Поиск матчей в {len(Config.LEAGUES)} лигах...")

                    matches = get_matches_with_factors()
                    if matches:
                        send_telegram(f"📊 Найдено {len(matches)} матчей. Анализирую...")

                        top_matches = find_top_matches(matches)
                        if top_matches:
                            for i, match in enumerate(top_matches[:5], 1):
                                send_match_with_buttons(match, i)
                                time.sleep(0.5)

                            elapsed = (datetime.now() - start_time).seconds
                            send_telegram(
                                f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                                f"📊 Найдено матчей: {len(matches)}\n"
                                f"🎯 Топ-5 матчей отправлено\n"
                                f"🤖 Авто-ставок: {auto_bet.bets_today}\n"
                                f"⏱️ Время: {elapsed} сек."
                            )
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
                    if False:
                        send_telegram(f"✅ Нейросеть обучена на {len(history)} матчах!")
                    else:
                        send_telegram("❌ Ошибка обучения нейросети (временно отключено)")
            
            elif text == '/report':
                from app.scheduler import send_weekly_report
                send_weekly_report()
            
            elif text == '/arb':
                try:
                    send_telegram("🔍 Поиск вилок...")
                    
                    matches = get_matches_with_factors()
                    if not matches:
                        send_telegram("❌ Матчей не найдено")
                        return "ok", 200
                    
                    found_arbs = 0
                    for match in matches:
                        fixture_id = match["fixture"]["id"]
                        odds_data = football_api.get_match_odds(fixture_id)
                        
                        if odds_data:
                            arb_opps = arbitrage_analyzer.find_arbitrage(odds_data)
                            if arb_opps:
                                match_data = {
                                    'home': match["teams"]["home"]["name"],
                                    'away': match["teams"]["away"]["name"],
                                    'league': match["league"]["name"]
                                }
                                msg = arbitrage_analyzer.format_arb_message(match_data, arb_opps)
                                send_telegram(msg)
                                found_arbs += 1
                                time.sleep(0.5)
                    
                    if found_arbs == 0:
                        send_telegram("❌ Вилок не найдено в сегодняшних матчах")
                    else:
                        send_telegram(f"✅ Найдено вилок в {found_arbs} матчах")
                        
                except Exception as e:
                    logger.error(f"Ошибка /arb: {e}")
                    send_telegram("❌ Ошибка поиска вилок")
            
            elif text == '/anomalies':
                try:
                    send_telegram("🔍 Поиск аномалий в коэффициентах...")
                    
                    matches = get_matches_with_factors()
                    if not matches:
                        send_telegram("❌ Матчей не найдено")
                        return "ok", 200
                    
                    found = 0
                    for match in matches:
                        fixture_id = match["fixture"]["id"]
                        odds_data = football_api.get_match_odds(fixture_id)
                        
                        if odds_data:
                            match_data = {
                                'home': match["teams"]["home"]["name"],
                                'away': match["teams"]["away"]["name"],
                                'league': match["league"]["name"]
                            }
                            anomalies = anomaly_detector.find_anomalies(match_data, odds_data)
                            if anomalies:
                                msg = anomaly_detector.format_anomalies_message(match_data, anomalies)
                                send_telegram(msg)
                                found += 1
                                time.sleep(0.5)
                    
                    if found == 0:
                        send_telegram("✅ Аномалий не найдено в сегодняшних матчах")
                    else:
                        send_telegram(f"✅ Найдено аномалий в {found} матчах")
                        
                except Exception as e:
                    logger.error(f"Ошибка /anomalies: {e}")
                    send_telegram("❌ Ошибка поиска аномалий")
            
            elif text == '/security':
                stats = security.get_security_stats()
                msg = f"""🔒 <b>СТАТИСТИКА БЕЗОПАСНОСТИ</b>

🛡️ Заблокированных IP: {stats['blocked_ips']}
🔑 Активных токенов: {stats['active_tokens']}
⚠️ Неудачных попыток: {stats['total_attempts']}
📊 Активных попыток: {stats['failed_attempts']}

✅ Система защищена!
"""
                send_telegram(msg)
            
            elif text.startswith('/unblock'):
                try:
                    parts = text.split()
                    if len(parts) > 1:
                        ip = parts[1]
                        if security.unblock_ip(ip):
                            send_telegram(f"✅ IP {ip} разблокирован")
                        else:
                            send_telegram(f"❌ IP {ip} не найден в блокировках")
                    else:
                        send_telegram("📝 Напишите: /unblock <IP>\n\nПример: /unblock 192.168.1.1")
                except Exception as e:
                    logger.error(f"Ошибка /unblock: {e}")
                    send_telegram("❌ Ошибка разблокировки")
            
            elif text.startswith('/result'):
                try:
                    parts = text.split()
                    
                    if len(parts) >= 4:
                        home = parts[1]
                        away = parts[2]
                        score = parts[3]
                        
                        stake = 0
                        if len(parts) >= 5:
                            try:
                                stake = float(parts[4])
                            except:
                                stake = 0
                        
                        try:
                            home_goals, away_goals = score.split('-')
                            home_goals = int(home_goals)
                            away_goals = int(away_goals)
                            
                            if home_goals > away_goals:
                                result = 'win'
                                profit = round(stake * 0.85, 2) if stake > 0 else 0
                            elif home_goals < away_goals:
                                result = 'loss'
                                profit = -stake if stake > 0 else 0
                            else:
                                result = 'push'
                                profit = 0
                        except:
                            send_telegram("❌ Неправильный формат счёта. Используйте: 2-1")
                            return "ok", 200
                        
                        try:
                            history = storage.load_history()
                            logger.info(f"📋 История до сохранения: {len(history)} записей")
                            
                            bet_record = {
                                'home': home,
                                'away': away,
                                'league': 'Ручной ввод',
                                'bet': 'Ручная ставка',
                                'odds': 1.85 if stake > 0 else 0,
                                'stake': stake,
                                'ev': 0,
                                'result': result,
                                'profit': profit,
                                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                'home_goals': home_goals,
                                'away_goals': away_goals
                            }
                            history.append(bet_record)
                            storage.save_history(history)
                            logger.info(f"✅ СОХРАНЕНО В ИСТОРИЮ: {bet_record}")
                            
                            check = storage.load_history()
                            logger.info(f"📋 История после сохранения: {len(check)} записей")
                            
                            stats = storage.load_stats()
                            stats['total'] = stats.get('total', 0) + 1
                            if result == 'win':
                                stats['wins'] = stats.get('wins', 0) + 1
                                stats['total_profit'] = stats.get('total_profit', 0) + profit
                            elif result == 'loss':
                                stats['losses'] = stats.get('losses', 0) + 1
                                stats['total_profit'] = stats.get('total_profit', 0) - stake
                            else:
                                stats['pushes'] = stats.get('pushes', 0) + 1
                            storage.save_stats(stats)
                            logger.info(f"✅ СТАТИСТИКА: {stats}")
                            
                            msg = f"✅ Результат сохранён!\n{home} vs {away} → {score}\n📊 Результат: {result}"
                            if stake > 0:
                                if result == 'win':
                                    msg += f"\n💰 Прибыль: +${profit}"
                                elif result == 'loss':
                                    msg += f"\n💰 Проигрыш: -${stake}"
                                else:
                                    msg += f"\n💰 Возврат: $0"
                            send_telegram(msg)
                            
                        except Exception as e:
                            logger.error(f"❌ ОШИБКА СОХРАНЕНИЯ: {e}")
                            send_telegram(f"❌ Ошибка сохранения: {e}")
                        
                    else:
                        send_telegram("📝 Формат: /result <команда1> <команда2> <счёт> [сумма]\n\nПримеры:\n/result Fulham Chelsea 2-1\n/result Fulham Chelsea 2-1 50")
                        
                except Exception as e:
                    logger.error(f"Ошибка /result: {e}")
                    send_telegram(f"❌ Ошибка: {e}")
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "ok", 200

# ============================================================
# API ЭНДПОИНТЫ ДЛЯ ВЕБ-ПРИЛОЖЕНИЯ
# ============================================================

@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = storage.load_stats()
    bank = storage.load_bank()
    history = storage.load_history()
    
    total_bets = len(history)
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    pushes = stats.get('pushes', 0)
    total_profit = stats.get('total_profit', 0)
    
    winrate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
    total_stake = sum(bet.get('stake', 0) for bet in history)
    roi = round((total_profit / total_stake) * 100, 1) if total_stake > 0 else 0
    avg_stake = round(total_stake / total_bets, 2) if total_bets > 0 else 0
    
    return jsonify({
        'bank': bank,
        'total_bets': total_bets,
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'profit': round(total_profit, 2),
        'winrate': winrate,
        'roi': roi,
        'avg_stake': avg_stake
    })

@app.route('/api/history', methods=['GET'])
def api_history():
    history = storage.load_history()
    
    for bet in history:
        if bet.get('result') == 'win':
            bet['profit'] = round(bet.get('stake', 0) * (bet.get('odds', 1) - 1), 2)
        elif bet.get('result') == 'loss':
            bet['profit'] = -round(bet.get('stake', 0), 2)
        else:
            bet['profit'] = 0
        bet['match'] = f"{bet.get('home', '')} vs {bet.get('away', '')}"
    
    return jsonify(history)

@app.route('/api/bank', methods=['POST'])
def api_update_bank():
    data = request.json
    if 'bank' in data:
        storage.save_bank(data['bank'])
        return jsonify({'success': True, 'bank': data['bank']})
    return jsonify({'error': 'No bank value'}), 400

@app.route('/api/update_history', methods=['POST'])
def update_history():
    try:
        data = request.json
        history = data.get('history', [])
        
        if not history:
            return jsonify({'error': 'Нет данных'}), 400
        
        storage.save_history(history)
        logger.info(f"✅ История обновлена из веб-приложения: {len(history)} записей")
        
        total = len(history)
        wins = sum(1 for b in history if b.get('result') == 'win')
        losses = sum(1 for b in history if b.get('result') == 'loss')
        pushes = sum(1 for b in history if b.get('result') == 'push')
        total_profit = sum(float(b.get('profit', 0)) for b in history)
        
        stats = storage.load_stats()
        stats['total'] = total
        stats['wins'] = wins
        stats['losses'] = losses
        stats['pushes'] = pushes
        stats['total_profit'] = round(total_profit, 2)
        storage.save_stats(stats)
        
        logger.info(f"✅ Статистика пересчитана: {stats}")
        
        return jsonify({
            'success': True,
            'total': total,
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'profit': round(total_profit, 2)
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления истории: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_manual_match', methods=['POST'])
def add_manual_match():
    try:
        data = request.json
        match_name = data.get('match', '')
        score = data.get('score', '-')
        result = data.get('result', 'win')
        stake = data.get('stake', 0)
        bet_type = data.get('bet', '')
        odds = data.get('odds', 1.85)
        
        if not match_name:
            return jsonify({'error': 'Название матча обязательно'}), 400
        
        home_goals = None
        away_goals = None
        if score and '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0].strip())
                away_goals = int(parts[1].strip())
            except:
                pass
        
        home = 'Unknown'
        away = 'Unknown'
        if ' vs ' in match_name:
            parts = match_name.split(' vs ')
            home = parts[0].strip()
            away = parts[1].strip()
        elif ' - ' in match_name:
            parts = match_name.split(' - ')
            home = parts[0].strip()
            away = parts[1].strip()
        
        if result == 'win':
            profit = round(stake * (odds - 1), 2)
        elif result == 'loss':
            profit = -stake
        else:
            profit = 0
        
        _, history = get_data_from_bot()
        
        bet_record = {
            'home': home,
            'away': away,
            'league': 'Ручное добавление',
            'bet': bet_type,
            'odds': odds,
            'stake': stake,
            'ev': 0,
            'result': result,
            'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': home_goals,
            'away_goals': away_goals,
            'manual': True
        }
        history.append(bet_record)
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'count': 1})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        history = data.get('history', [])
        stats = data.get('stats', {})
        
        if not history:
            return jsonify({'error': 'Нет данных для импорта'}), 400
        
        _, current_history = get_data_from_bot()
        
        if stats and 'bank' in stats:
            requests.post(f'{BOT_URL}/api/bank', json={'bank': stats['bank']}, timeout=10)
        
        existing_keys = set()
        for bet in current_history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            existing_keys.add(key)
        
        imported = 0
        for bet in history:
            key = f"{bet.get('date', '')}_{bet.get('home', '')}_{bet.get('away', '')}"
            if key not in existing_keys:
                current_history.append(bet)
                imported += 1
                existing_keys.add(key)
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': current_history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'count': imported})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        count = data.get('count', 1000)
        
        _, history = get_data_from_bot()
        
        if len(history) < 5:
            return jsonify({'error': 'Нужно минимум 5 ставок для симуляции'}), 400
        
        wins = sum(1 for b in history if b.get('result') == 'win')
        total = len(history)
        winrate = wins / total if total > 0 else 0
        
        avg_stake = sum(float(b.get('stake', 0)) for b in history) / total if total > 0 else 10
        
        results = []
        profit_history = []
        total_profit = 0
        
        for i in range(count):
            if random.random() < winrate:
                profit = avg_stake * random.uniform(0.5, 1.5)
                total_profit += profit
                results.append('win')
            else:
                profit = -avg_stake
                total_profit += profit
                results.append('loss')
            
            profit_history.append(round(total_profit, 2))
        
        wins_sim = results.count('win')
        losses_sim = results.count('loss')
        max_profit = max(profit_history) if profit_history else 0
        min_profit = min(profit_history) if profit_history else 0
        
        return jsonify({
            'total': count,
            'wins': wins_sim,
            'losses': losses_sim,
            'profit': round(total_profit, 2),
            'winrate': round(wins_sim / count * 100, 1),
            'roi': round((total_profit / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'risk': round((abs(min_profit) / (avg_stake * count)) * 100, 2) if avg_stake > 0 else 0,
            'max_profit': round(max_profit, 2),
            'min_profit': round(min_profit, 2),
            'avg_stake': round(avg_stake, 2),
            'history': profit_history[:100],
            'labels': list(range(1, min(count, 100) + 1))
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        excel_data = data.get('data', [])
        
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        
        _, history = get_data_from_bot()
        
        imported = 0
        for row in excel_data:
            match = row.get('Матч', '') or row.get('Match', '')
            home = ''
            away = ''
            
            if ' vs ' in match:
                parts = match.split(' vs ')
                home = parts[0].strip()
                away = parts[1].strip()
            elif ' - ' in match:
                parts = match.split(' - ')
                home = parts[0].strip()
                away = parts[1].strip()
            
            score = row.get('Счёт', '') or row.get('Scht', '') or row.get('Score', '')
            home_goals = None
            away_goals = None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
            
            bet = row.get('Ставка', '') or row.get('Stanka', '') or 'Ручная ставка'
            
            odds = 1.85
            try:
                odds = float(row.get('Коэф', 1.85) or row.get('Kofy', 1.85) or 1.85)
            except:
                odds = 1.85
            
            stake = 0
            try:
                stake = float(row.get('Сумма', 0) or row.get('Stake', 0) or 0)
            except:
                stake = 0
            
            ev = 0
            try:
                ev = float(row.get('EV%', 0) or row.get('Ev', 0) or 0)
            except:
                ev = 0
            
            result = row.get('Результат', 'pending') or row.get('Result', 'pending')
            if result.lower() in ['win', 'выигрыш']:
                result = 'win'
            elif result.lower() in ['loss', 'проигрыш']:
                result = 'loss'
            elif result.lower() in ['push', 'возврат']:
                result = 'push'
            else:
                result = 'pending'
            
            profit = 0
            try:
                profit = float(row.get('Прибыль', 0) or row.get('Profit', 0) or 0)
            except:
                profit = 0
            
            date = row.get('Дата', '') or row.get('Data', '') or datetime.now().strftime('%Y-%m-%d %H:%M')
            if not date or date == '':
                date = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            bet_record = {
                'home': home or 'Unknown',
                'away': away or 'Unknown',
                'league': 'Импорт из Excel',
                'bet': bet,
                'odds': odds,
                'stake': stake,
                'ev': ev,
                'result': result,
                'profit': profit,
                'date': date,
                'home_goals': home_goals,
                'away_goals': away_goals
            }
            history.append(bet_record)
            imported += 1
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'count': imported})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        index = data.get('index')
        
        _, history = get_data_from_bot()
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        history[index]['home'] = data.get('home', history[index]['home'])
        history[index]['away'] = data.get('away', history[index]['away'])
        history[index]['home_goals'] = data.get('home_goals')
        history[index]['away_goals'] = data.get('away_goals')
        history[index]['bet'] = data.get('bet', history[index]['bet'])
        history[index]['odds'] = data.get('odds', history[index]['odds'])
        history[index]['stake'] = data.get('stake', history[index]['stake'])
        history[index]['ev'] = data.get('ev', history[index]['ev'])
        history[index]['result'] = data.get('result', history[index]['result'])
        
        if history[index]['result'] == 'win':
            history[index]['profit'] = round(history[index]['stake'] * (history[index]['odds'] - 1), 2)
        elif history[index]['result'] == 'loss':
            history[index]['profit'] = -history[index]['stake']
        else:
            history[index]['profit'] = 0
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        index = data.get('index')
        
        _, history = get_data_from_bot()
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        deleted = history.pop(index)
        
        response = requests.post(f'{BOT_URL}/api/update_history', json={'history': history}, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'deleted': deleted})
        else:
            return jsonify({'error': 'Ошибка сохранения'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        if 'bank' in data:
            response = requests.post(f'{BOT_URL}/api/bank', json={'bank': data['bank']}, timeout=10)
            return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'No bank value'}), 400

@app.route('/export')
def export_data():
    try:
        response = requests.get(f'{BOT_URL}/export', timeout=30)
        if response.status_code == 200:
            return response.content, 200, {'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
    except:
        pass
    return "Нет данных для экспорта", 404

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
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    app.run(host='0.0.0.0', port=port)
