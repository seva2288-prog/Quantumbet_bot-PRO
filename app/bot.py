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
from app.betting.auto_bet import auto_bet
from app.scheduler import start_scheduler
from app.security.auth import security

logger = get_logger(__name__)
app = Flask(__name__)

search_running = False

# ===== КОНСТАНТА ЧАСОВОГО ПОЯСА =====
TIMEZONE_OFFSET = 3  # UTC+3

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

# ============================================================
# ПОИСК МАТЧЕЙ (ТОЛЬКО НА СЕГОДНЯ, ПОГОДА ОТКЛЮЧЕНА)
# ============================================================

def get_matches_with_factors():
    all_matches = []
    
    # ===== ИЩЕМ ТОЛЬКО НА СЕГОДНЯ =====
    today = datetime.now().strftime('%Y-%m-%d')
    dates_to_search = [today]
    
    logger.info(f"🔍 Поиск матчей на: {today}")
    
    for league_id in Config.LEAGUES:
        for search_date in dates_to_search:
            try:
                matches = football_api.get_matches(league_id, search_date)
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
                                
                                # ===== ПОГОДА ОТКЛЮЧЕНА =====
                                match["weather"] = None
                                match["weather_reason"] = "🌤️ Погода отключена"
                                
                                match["league"]["name"] = league_name
                                all_matches.append(match)
                else:
                    logger.info(f"🔥 Нет матчей в {league_name} на {search_date}")
            except Exception as e:
                logger.error(f"❌ Ошибка {league_name} на {search_date}: {e}")
            
            time.sleep(0.3)
    
    logger.info(f"📊 Найдено матчей: {len(all_matches)}")
    return all_matches

# ============================================================
# ТОП-20 МАТЧЕЙ С АВТО-СТАВКАМИ
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN

    for match in matches:
        if bets_placed >= max_bets:
            logger.info(f"⚠️ Достигнут лимит ставок: {max_bets}")
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
                    # ===== ДОБАВЛЯЕМ СМЕЩЕНИЕ ЧАСОВОГО ПОЯСА =====
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"

            home_xg, away_xg, reasons = xg_analyzer.calculate_xg(match, fixture_id)

            try:
                home_xg, away_xg = ml_predictor.predict_xg(factors)
            except Exception as e:
                logger.warning(f"Ошибка ML: {e}")

            probs = calculate_probabilities(home_xg, away_xg)

            odds_data = football_api.get_match_odds(fixture_id)
            bet_types = get_bet_types(odds_data)

            match_data = {
                "home": home,
                "away": away,
                "league": league,
                "fixture_id": fixture_id,
                "match_time": match_time,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "weather_reason": match.get("weather_reason", "🌤️ Погода отключена"),
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

                # ===== АВТО-СТАВКА С ДАТОЙ И ВРЕМЕНЕМ =====
                try:
                    bet_result = auto_bet.check_and_bet(match_data)
                    if bet_result:
                        bets_placed += 1
                        msg = f"🤖 <b>АВТО-СТАВКА #{bets_placed}</b>\n"
                        msg += f"🏟️ {bet_result['match']}\n"
                        # ===== ДОБАВЛЯЕМ ДАТУ И ВРЕМЯ =====
                        if bet_result.get('match_time'):
                            msg += f"📅 {bet_result['match_time']}\n"
                        msg += f"📊 {bet_result['bet']} | КЭФ: {bet_result['odds']}\n"
                        msg += f"💰 Сумма: ${bet_result['stake']}\n"
                        msg += f"📈 EV: {bet_result['ev']}%"
                        if bet_result.get('marker_stake'):
                            msg += f"\n🎯 Маркер: ${bet_result['marker_stake']}"
                        send_telegram(msg)
                        logger.info(f"✅ АВТО-СТАВКА #{bets_placed}")
                except Exception as e:
                    logger.error(f"Ошибка авто-ставки: {e}")

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            continue

    all_matches_data.sort(key=lambda x: x['bets'][0]['ev'] if x['bets'] else 0, reverse=True)
    logger.info(f"📊 Найдено {len(all_matches_data)} матчей, сделано {bets_placed} ставок")
    return all_matches_data[:20]

# ============================================================
# WEBHOOK
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
                parts = callback_data.split('_')
                if len(parts) >= 3:
                    result_type = parts[1]
                    match_id = parts[2]
                    
                    match = None
                    cache = storage.load_cache()
                    match = cache.get(f"match_{match_id}")
                    
                    if not match:
                        try:
                            with open(f"data/match_{match_id}.json", 'r') as f:
                                match = json.load(f)
                        except:
                            pass
                    
                    if match:
                        if result_type != 'skip':
                            bets = match.get('bets', [])
                            if bets:
                                best_bet = bets[0]
                                
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
                                
                                try:
                                    history = storage.load_history()
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
                            cache.pop(f"match_{match_id}", None)
                            storage.save_cache(cache)
                            try:
                                os.remove(f"data/match_{match_id}.json")
                            except:
                                pass
            
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
                            # ===== КАРТОЧКИ МАТЧЕЙ ОТКЛЮЧЕНЫ =====
                            # for i, match in enumerate(top_matches[:20], 1):
                            #     send_match_with_buttons(match, i)
                            #     time.sleep(0.5)

                            elapsed = (datetime.now() - start_time).seconds
                            send_telegram(
                                f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                                f"📊 Найдено матчей: {len(matches)}\n"
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
            
            elif text == '/help':
                send_telegram(handlers.handle_start())
            
            elif text == '/autobet':
                auto_bet.enabled = not getattr(auto_bet, 'enabled', True)
                status = "ВКЛЮЧЕНЫ" if auto_bet.enabled else "ВЫКЛЮЧЕНЫ"
                send_telegram(f"🤖 Авто-ставки {status}!")
            
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
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "ok", 200

# ============================================================
# API ЭНДПОИНТЫ
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
        logger.info(f"✅ История обновлена: {len(history)} записей")
        
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
        
        return jsonify({
            'success': True,
            'total': total,
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'profit': round(total_profit, 2)
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return jsonify({'error': str(e)}), 500

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
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    app.run(host='0.0.0.0', port=port)
