from flask import Flask, request
import time
import os
from datetime import datetime

from config import Config
from app.database.storage import storage
from app.api.football import football_api
from app.api.weather import weather_api
from app.analytics.xg import xg_analyzer
from app.analytics.probability import calculate_probabilities, calculate_ev, get_bet_types
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger

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
            
            match_time = match.get("fixture", {}).get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            home_xg, away_xg, reasons = xg_analyzer.calculate_xg(match, fixture_id)
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
            
            elif text == '/help':
                send_telegram(handlers.handle_start())
            
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
    from app.scheduler import start_scheduler
    
    setup_logging()
    start_scheduler()  # <-- ДОБАВЛЯЕМ АВТО-ОБНОВЛЕНИЕ
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН С ВСЕМИ УЛУЧШЕНИЯМИ!")
    app.run(host='0.0.0.0', port=port)
