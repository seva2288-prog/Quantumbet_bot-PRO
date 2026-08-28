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
from app.analytics.probability import calculate_probabilities, calculate_ev, get_bet_types
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

# ===== ÐÐÐÐ¡Ð¢ÐÐÐ¢Ð Ð§ÐÐ¡ÐÐÐÐÐ ÐÐÐ¯Ð¡Ð =====
TIMEZONE_OFFSET = 3  # UTC+3

def send_error_to_telegram(error_text: str):
    try:
        import requests
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        if len(error_text) > 4000:
            error_text = error_text[:4000] + "...(Ð¾Ð±ÑÐµÐ·Ð°Ð½Ð¾)"
        data = {
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': f"â <b>ÐÐ¨ÐÐÐÐ ÐÐÐ¢Ð</b>\n\n{error_text}",
            'parse_mode': 'HTML'
        }
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾ÑÐ¿ÑÐ°Ð²Ð¸ÑÑ Ð¾ÑÐ¸Ð±ÐºÑ Ð² Telegram: {e}")

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
        send_error_to_telegram(f"ÐÑÐ¸Ð±ÐºÐ° Ð¾ÑÐ¿ÑÐ°Ð²ÐºÐ¸ Ð² Telegram: {e}")

# ============ Ð­ÐÐ¡ÐÐÐ Ð¢ Ð EXCEL ============
def export_to_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    import io
    
    history = storage.load_history()
    
    if not history:
        return None, "ð­ ÐÐµÑ Ð´Ð°Ð½Ð½ÑÑ Ð´Ð»Ñ ÑÐºÑÐ¿Ð¾ÑÑÐ°"
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Ð¡ÑÐ°Ð²ÐºÐ¸"
    
    headers = ["ÐÐ°ÑÐ°", "ÐÐ°ÑÑ", "Ð¡ÑÑÑ", "Ð¡ÑÐ°Ð²ÐºÐ°", "ÐÐ¾ÑÑ", "EV%", "Ð¡ÑÐ¼Ð¼Ð°", "Ð ÐµÐ·ÑÐ»ÑÑÐ°Ñ", "ÐÑÐ¸Ð±ÑÐ»Ñ"]
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
    ws.append(["ÐÐ¢ÐÐÐ", "", "", "", "", "", "", "", round(total_profit, 2)])
    
    for col in range(1, len(headers) + 1):
        column_letter = chr(64 + col)
        ws.column_dimensions[column_letter].width = 15
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output, f"â Ð­ÐºÑÐ¿Ð¾ÑÑ Ð·Ð°Ð²ÐµÑÑÐµÐ½! ÐÑÐµÐ³Ð¾ ÑÑÐ°Ð²Ð¾Ðº: {len(history)}, ÐÑÐ¸Ð±ÑÐ»Ñ: ${round(total_profit, 2)}"

# ============================================================
# ÐÐÐÐ¡Ð ÐÐÐ¢Ð§ÐÐ (Ð¢ÐÐÐ¬ÐÐ ÐÐ Ð¡ÐÐÐÐÐÐ¯, ÐÐÐÐÐÐ ÐÐ¢ÐÐÐ®Ð§ÐÐÐ)
# ============================================================

def get_matches_with_factors():
    all_matches = []
    
    today = datetime.now().strftime('%Y-%m-%d')
    dates_to_search = [today]
    
    logger.info(f"ð ÐÐ¾Ð¸ÑÐº Ð¼Ð°ÑÑÐµÐ¹ Ð½Ð°: {today}")
    
    for league_id in Config.LEAGUES:
        for search_date in dates_to_search:
            try:
                matches = football_api.get_matches(league_id, search_date)
                league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
                
                # ===== ÐÐ ÐÐÐÐ Ð¯ÐÐ, Ð§Ð¢Ð matches - Ð¡ÐÐÐ¡ÐÐ =====
                if not matches or not isinstance(matches, list):
                    logger.info(f"ð¥ ÐÐµÑ Ð¼Ð°ÑÑÐµÐ¹ Ð² {league_name} Ð½Ð° {search_date}")
                    continue
                
                for match in matches:
                    # ===== ÐÐ ÐÐÐÐ ÐÐ: Ð­Ð¢Ð Ð¡ÐÐÐÐÐ Ð¬? =====
                    if not isinstance(match, dict):
                        continue
                    
                    # ===== ÐÐ ÐÐÐÐ ÐÐ: ÐÐ¡Ð¢Ð¬ ÐÐ fixture? =====
                    fixture = match.get("fixture")
                    if not fixture or not isinstance(fixture, dict):
                        continue
                    
                    # ===== ÐÐ ÐÐÐÐ ÐÐ: Ð¡Ð¢ÐÐ¢Ð£Ð¡ ÐÐÐ¢Ð§Ð =====
                    status = fixture.get("status", {})
                    if not isinstance(status, dict):
                        continue
                    
                    if status.get("short") == "NS":
                        match_id = fixture.get("id")
                        if not match_id:
                            continue
                        
                        # ===== ÐÐ ÐÐÐÐ ÐÐ ÐÐ ÐÐ£ÐÐÐÐÐÐ¢ =====
                        existing_ids = []
                        for m in all_matches:
                            if isinstance(m, dict):
                                existing_ids.append(m.get("fixture", {}).get("id"))
                        
                        if match_id in existing_ids:
                            continue
                        
                        teams = match.get("teams", {})
                        if not isinstance(teams, dict):
                            continue
                        
                        home_team = teams.get("home", {})
                        away_team = teams.get("away", {})
                        
                        if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                            continue
                        
                        home_id = home_team.get("id")
                        away_id = away_team.get("id")
                        
                        if not home_id or not away_id:
                            continue
                        
                        match["factors"] = {
                            "home_form": football_api.get_form(home_id) if home_id else None,
                            "away_form": football_api.get_form(away_id) if away_id else None,
                            "home_injuries_list": football_api.get_injuries(home_id) if home_id else [],
                            "away_injuries_list": football_api.get_injuries(away_id) if away_id else [],
                            "home_id": home_id,
                            "away_id": away_id,
                            "referee": fixture.get("referee")
                        }
                        
                        match["weather"] = None
                        match["weather_reason"] = "ð¤ï¸ ÐÐ¾Ð³Ð¾Ð´Ð° Ð¾ÑÐºÐ»ÑÑÐµÐ½Ð°"
                        
                        league_data = match.get("league", {})
                        if isinstance(league_data, dict):
                            league_data["name"] = league_name
                        
                        all_matches.append(match)
                        
            except Exception as e:
                error_msg = f"ÐÑÐ¸Ð±ÐºÐ° {league_name} Ð½Ð° {search_date}: {e}"
                logger.error(f"â {error_msg}")
                send_error_to_telegram(error_msg)
            
            time.sleep(0.1)
    
    logger.info(f"ð ÐÐ¡ÐÐÐ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾ Ð¼Ð°ÑÑÐµÐ¹: {len(all_matches)}")
    return all_matches

# ============================================================
# Ð¢ÐÐ-20 ÐÐÐ¢Ð§ÐÐ Ð¡ ÐÐÐ¢Ð-Ð¡Ð¢ÐÐÐÐÐÐ (ÐÐÐÐÐÐ¡Ð¢Ð¬Ð® ÐÐÐ ÐÐÐÐ¡ÐÐÐ + ÐÐÐ©ÐÐ¢Ð)
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN

    for match in matches:
        if not match or not isinstance(match, dict):
            continue
        
        if bets_placed >= max_bets:
            logger.info(f"â ï¸ ÐÐ¾ÑÑÐ¸Ð³Ð½ÑÑ Ð»Ð¸Ð¼Ð¸Ñ ÑÑÐ°Ð²Ð¾Ðº: {max_bets}")
            break

        try:
            fixture = match.get("fixture")
            if not fixture or not isinstance(fixture, dict):
                continue
            
            fixture_id = fixture.get("id")
            if not fixture_id:
                continue
            
            teams = match.get("teams")
            if not teams or not isinstance(teams, dict):
                continue
            
            home_team = teams.get("home")
            away_team = teams.get("away")
            
            if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                continue
            
            home = home_team.get("name", "Unknown")
            away = away_team.get("name", "Unknown")
            
            league_data = match.get("league")
            league = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"

            factors = match.get("factors", {})
            if not isinstance(factors, dict):
                factors = {}

            match_time = fixture.get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "ÐÑÐµÐ¼Ñ Ð½Ðµ ÑÐºÐ°Ð·Ð°Ð½Ð¾"

            # ===== xG =====
            try:
                home_xg, away_xg, reasons = xg_analyzer.calculate_xg(match, fixture_id)
            except Exception as e:
                logger.warning(f"ÐÑÐ¸Ð±ÐºÐ° xG {home} vs {away}: {e}")
                home_xg, away_xg, reasons = 1.2, 1.0, ["fallback"]

            try:
                home_xg, away_xg = ml_predictor.predict_xg(factors)
            except Exception as e:
                logger.warning(f"ÐÑÐ¸Ð±ÐºÐ° ML {home} vs {away}: {e}")

            probs = calculate_probabilities(home_xg, away_xg)
            if not isinstance(probs, dict):
                logger.warning(f"probs Ð½Ðµ ÑÐ»Ð¾Ð²Ð°ÑÑ Ð´Ð»Ñ {home} vs {away}: {type(probs)}")
                continue

            # ===== ÐÐÐ®Ð§ÐÐÐÐ¯ ÐÐÐ©ÐÐ¢Ð ÐÐ¢ ÐÐ¨ÐÐÐÐ =====
            odds_data = football_api.get_match_odds(fixture_id)

            if not odds_data or not isinstance(odds_data, dict):
                logger.warning(
                    f"ÐÑÐ¾Ð¿ÑÑÐº {home} vs {away} (fixture {fixture_id}) â "
                    f"odds_data = {type(odds_data)} | {str(odds_data)[:120]}"
                )
                continue

            bet_types = get_bet_types(odds_data)
            if not bet_types:
                continue

            match_data = {
                "home": home,
                "away": away,
                "league": league,
                "fixture_id": fixture_id,
                "match_time": match_time,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "weather_reason": match.get("weather_reason", "ð¤ï¸ ÐÐ¾Ð³Ð¾Ð´Ð° Ð¾ÑÐºÐ»ÑÑÐµÐ½Ð°"),
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
                    stake = min(bank * (ev / 100) * 0.3, bank * 0.05)
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
                        msg = f"ð¤ <b>ÐÐÐ¢Ð-Ð¡Ð¢ÐÐÐÐ #{bets_placed}</b>\n"
                        msg += f"ðï¸ {bet_result['match']}\n"
                        if bet_result.get('match_time'):
                            msg += f"ð {bet_result['match_time']}\n"
                        msg += f"ð {bet_result['bet']} | ÐÐ­Ð¤: {bet_result['odds']}\n"
                        msg += f"ð° Ð¡ÑÐ¼Ð¼Ð°: ${bet_result['stake']}\n"
                        msg += f"ð EV: {bet_result['ev']}%"
                        if bet_result.get('marker_stake'):
                            msg += f"\nð¯ ÐÐ°ÑÐºÐµÑ: ${bet_result['marker_stake']}"
                        send_telegram(msg)
                        logger.info(f"â ÐÐÐ¢Ð-Ð¡Ð¢ÐÐÐÐ #{bets_placed}")
                except Exception as e:
                    error_msg = f"ÐÑÐ¸Ð±ÐºÐ° Ð°Ð²ÑÐ¾-ÑÑÐ°Ð²ÐºÐ¸: {e}"
                    logger.error(f"â {error_msg}")
                    send_error_to_telegram(error_msg)

        except Exception as e:
            error_msg = f"ÐÑÐ¸Ð±ÐºÐ° Ð² find_top_matches: {e}"
            logger.error(f"â {error_msg}")
            send_error_to_telegram(error_msg)
            continue

    all_matches_data.sort(key=lambda x: x['bets'][0]['ev'] if x['bets'] else 0, reverse=True)
    logger.info(f"ð ÐÐ°Ð¹Ð´ÐµÐ½Ð¾ {len(all_matches_data)} Ð¼Ð°ÑÑÐµÐ¹, ÑÐ´ÐµÐ»Ð°Ð½Ð¾ {bets_placed} ÑÑÐ°Ð²Ð¾Ðº")
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
            
            logger.info(f"ð¨ ÐÐ°Ð¶Ð°ÑÐ° ÐºÐ½Ð¾Ð¿ÐºÐ°: {callback_data}")
            
            import requests
            answer_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"
            try:
                requests.post(answer_url, json={
                    "callback_query_id": callback.get('id', ''),
                    "text": "â Ð ÐµÐ·ÑÐ»ÑÑÐ°Ñ ÑÐ¾ÑÑÐ°Ð½ÑÐ½!"
                })
            except Exception as e:
                logger.error(f"ÐÑÐ¸Ð±ÐºÐ° Ð¾ÑÐ²ÐµÑÐ°: {e}")
            
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
                                    result = 'win' if 'ÐÐ¾Ð±ÐµÐ´Ð° ÑÐ¾Ð·ÑÐµÐ²' in best_bet['label'] else 'loss'
                                elif result_type == 'away':
                                    result = 'win' if 'ÐÐ¾Ð±ÐµÐ´Ð° Ð³Ð¾ÑÑÐµÐ¹' in best_bet['label'] else 'loss'
                                elif result_type == 'draw':
                                    if '1Ð¥' in best_bet['label'] or '2Ð¥' in best_bet['label']:
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
                                    
                                    msg = f"â Ð ÐµÐ·ÑÐ»ÑÑÐ°Ñ ÑÐ¾ÑÑÐ°Ð½ÑÐ½!\n{match.get('home')} vs {match.get('away')} â {result}"
                                    if result == 'win':
                                        msg += f"\nð° ÐÑÐ¸Ð±ÑÐ»Ñ: +${profit}"
                                    elif result == 'loss':
                                        msg += f"\nð° ÐÑÐ¾Ð¸Ð³ÑÑÑ: -${stake}"
                                    send_telegram(msg)
                                    
                                except Exception as e:
                                    error_msg = f"ÐÑÐ¸Ð±ÐºÐ° ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ð¸Ñ ÑÐµÐ·ÑÐ»ÑÑÐ°ÑÐ°: {e}"
                                    logger.error(f"â {error_msg}")
                                    send_error_to_telegram(error_msg)
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
                send_telegram("â ÐÐµÑ Ð´Ð¾ÑÑÑÐ¿Ð°")
                return "ok", 200
            
            if text == '/start':
                send_telegram(handlers.handle_start())
            
            elif text == '/update':
                if search_running:
                    send_telegram("â ï¸ ÐÐ¾Ð¸ÑÐº ÑÐ¶Ðµ Ð·Ð°Ð¿ÑÑÐµÐ½!")
                else:
                    search_running = True
                    start_time = datetime.now()
                    send_telegram(f"ð ÐÐ¾Ð¸ÑÐº Ð¼Ð°ÑÑÐµÐ¹ Ð² {len(Config.LEAGUES)} Ð»Ð¸Ð³Ð°Ñ...")

                    matches = get_matches_with_factors()
                    if matches:
                        send_telegram(f"ð ÐÐ°Ð¹Ð´ÐµÐ½Ð¾ {len(matches)} Ð¼Ð°ÑÑÐµÐ¹. ÐÐ½Ð°Ð»Ð¸Ð·Ð¸ÑÑÑ...")

                        top_matches = find_top_matches(matches)
                        if top_matches:
                            elapsed = (datetime.now() - start_time).seconds
                            send_telegram(
                                f"â <b>ÐÐÐÐ¡Ð ÐÐÐÐÐ Ð¨ÐÐ!</b>\n"
                                f"ð ÐÐ°Ð¹Ð´ÐµÐ½Ð¾ Ð¼Ð°ÑÑÐµÐ¹: {len(matches)}\n"
                                f"ð¤ ÐÐ²ÑÐ¾-ÑÑÐ°Ð²Ð¾Ðº: {auto_bet.bets_today}\n"
                                f"â±ï¸ ÐÑÐµÐ¼Ñ: {elapsed} ÑÐµÐº."
                            )
                        else:
                            send_telegram("â Ð¡ÑÐ°Ð²Ð¾Ðº Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾")
                    else:
                        send_telegram("â ÐÐ°ÑÑÐµÐ¹ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾")

                    search_running = False
            
            elif text == '/stop':
                search_running = False
                send_telegram("ð ÐÐÐÐ¡Ð ÐÐ¡Ð¢ÐÐÐÐÐÐÐ!")
            
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            
            elif text == '/help':
                send_telegram(handlers.handle_start())
            
            elif text == '/autobet':
                auto_bet.enabled = not getattr(auto_bet, 'enabled', True)
                status = "ÐÐÐÐ®Ð§ÐÐÐ«" if auto_bet.enabled else "ÐÐ«ÐÐÐ®Ð§ÐÐÐ«"
                send_telegram(f"ð¤ ÐÐ²ÑÐ¾-ÑÑÐ°Ð²ÐºÐ¸ {status}!")
            
            elif text == '/export':
                file, message = export_to_excel()
                if file:
                    send_telegram(message)
                    import requests
                    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                    files = {'document': ('history.xlsx', file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                    data = {'chat_id': Config.ADMIN_CHAT_ID, 'caption': 'ð ÐÑÑÐ¾ÑÐ¸Ñ ÑÑÐ°Ð²Ð¾Ðº'}
                    try:
                        requests.post(url, files=files, data=data, timeout=30)
                    except Exception as e:
                        logger.error(f"ÐÑÐ¸Ð±ÐºÐ° Ð¾ÑÐ¿ÑÐ°Ð²ÐºÐ¸ ÑÐ°Ð¹Ð»Ð°: {e}")
                else:
                    send_telegram(message)
            
            elif text == '/update_results':
                send_telegram("ð ÐÑÐ¾Ð²ÐµÑÐºÐ° ÑÐµÐ·ÑÐ»ÑÑÐ°ÑÐ¾Ð² Ð¼Ð°ÑÑÐµÐ¹...")
                updated = update_pending_bets()
                if updated > 0:
                    send_telegram(f"â ÐÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ {updated} ÑÐµÐ·ÑÐ»ÑÑÐ°ÑÐ¾Ð²!")
                else:
                    send_telegram("ð­ ÐÐµÑ Ð·Ð°Ð²ÐµÑÑÑÐ½Ð½ÑÑ Ð¼Ð°ÑÑÐµÐ¹ Ð´Ð»Ñ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ")
            
            else:
                send_telegram("â ÐÐµÐ¸Ð·Ð²ÐµÑÑÐ½Ð°Ñ ÐºÐ¾Ð¼Ð°Ð½Ð´Ð°. /help")
        
        return "ok", 200
    except Exception as e:
        error_msg = f"Webhook error: {e}"
        logger.error(f"â {error_msg}")
        send_error_to_telegram(error_msg)
        return "ok", 200

# ============================================================
# ÐÐÐ¢ÐÐÐÐ¢ÐÐ§ÐÐ¡ÐÐÐ ÐÐÐÐÐÐÐÐÐÐ Ð ÐÐÐ£ÐÐ¬Ð¢ÐÐ¢ÐÐ
# ============================================================

def determine_bet_result(bet_type, home_goals, away_goals):
    """ÐÐ¿ÑÐµÐ´ÐµÐ»ÑÐµÑ ÑÐµÐ·ÑÐ»ÑÑÐ°Ñ ÑÑÐ°Ð²ÐºÐ¸ Ð¿Ð¾ ÑÑÑÑÑ"""
    total = home_goals + away_goals
    bet_type_lower = bet_type.lower()
    
    if 'Ð¾Ð· - Ð´Ð°' in bet_type_lower or 'Ð¾Ð±Ð·' in bet_type_lower:
        if home_goals > 0 and away_goals > 0:
            return 'win'
        else:
            return 'loss'
    elif 'ÑÐ¼ 2.5' in bet_type_lower:
        if total < 2.5:
            return 'win'
        else:
            return 'loss'
    elif 'ÑÐ± 2.5' in bet_type_lower:
        if total > 2.5:
            return 'win'
        else:
            return 'loss'
    elif '1x' in bet_type_lower:
        if home_goals >= away_goals:
            return 'win'
        else:
            return 'loss'
    elif 'x2' in bet_type_lower:
        if away_goals >= home_goals:
            return 'win'
        else:
            return 'loss'
    elif 'Ð¿1' in bet_type_lower or 'Ð¿Ð¾Ð±ÐµÐ´Ð° ÑÐ¾Ð·ÑÐµÐ²' in bet_type_lower:
        if home_goals > away_goals:
            return 'win'
        elif home_goals == away_goals:
            return 'push'
        else:
            return 'loss'
    elif 'Ð¿2' in bet_type_lower or 'Ð¿Ð¾Ð±ÐµÐ´Ð° Ð³Ð¾ÑÑÐµÐ¹' in bet_type_lower:
        if away_goals > home_goals:
            return 'win'
        elif home_goals == away_goals:
            return 'push'
        else:
            return 'loss'
    return 'pending'

def update_pending_bets():
    """ÐÐ²ÑÐ¾Ð¼Ð°ÑÐ¸ÑÐµÑÐºÐ¾Ðµ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐµÐ·ÑÐ»ÑÑÐ°ÑÐ¾Ð² PENDING ÑÑÐ°Ð²Ð¾Ðº"""
    history = storage.load_history()
    updated = 0
    
    for bet in history:
        if bet.get('result') == 'pending' or bet.get('result') is None:
            fixture_id = bet.get('fixture_id')
            
            if not fixture_id:
                home = bet.get('home', '')
                away = bet.get('away', '')
                if home and away and home != 'Unknown' and away != 'Unknown':
                    fixture_id = football_api.find_fixture_by_teams(home, away)
                    if fixture_id:
                        bet['fixture_id'] = fixture_id
            
            if fixture_id:
                match_data = football_api.get_match_result(fixture_id)
                if match_data:
                    home_goals = match_data['goals']['home']
                    away_goals = match_data['goals']['away']
                    
                    if home_goals is not None and away_goals is not None:
                        bet_type = bet.get('bet', '')
                        result = determine_bet_result(bet_type, home_goals, away_goals)
                        
                        if result != 'pending':
                            bet['result'] = result
                            bet['home_goals'] = home_goals
                            bet['away_goals'] = away_goals
                            
                            if result == 'win':
                                bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                            elif result == 'loss':
                                bet['profit'] = -bet['stake']
                            else:
                                bet['profit'] = 0
                            
                            updated += 1
                            logger.info(f"â ÐÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð° ÑÑÐ°Ð²ÐºÐ°: {bet['home']} vs {bet['away']} â {result} ({home_goals}-{away_goals})")
    
    if updated > 0:
        storage.save_history(history)
        recalc_stats()
        send_telegram(f"â ÐÐ²ÑÐ¾Ð¼Ð°ÑÐ¸ÑÐµÑÐºÐ¸ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ {updated} ÑÐµÐ·ÑÐ»ÑÑÐ°ÑÐ¾Ð²!")
    
    return updated

def recalc_stats():
    """ÐÐµÑÐµÑÑÐ¸ÑÑÐ²Ð°ÐµÑ ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÑ"""
    history = storage.load_history()
    stats = storage.load_stats()
    
    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    pushes = sum(1 for b in history if b.get('result') == 'push')
    total_profit = sum(b.get('profit', 0) for b in history)
    total_stake = sum(b.get('stake', 0) for b in history)
    
    stats['total'] = total
    stats['wins'] = wins
    stats['losses'] = losses
    stats['pushes'] = pushes
    stats['total_profit'] = round(total_profit, 2)
    stats['winrate'] = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
    stats['roi'] = round((total_profit / total_stake * 100), 1) if total_stake > 0 else 0
    
    storage.save_stats(stats)
    logger.info(f"ð Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° Ð¿ÐµÑÐµÑÑÐ¸ÑÐ°Ð½Ð°: {stats}")

# ============================================================
# API Ð­ÐÐÐÐÐÐÐ¢Ð«
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
            return jsonify({'error': 'ÐÐµÑ Ð´Ð°Ð½Ð½ÑÑ'}), 400
        
        storage.save_history(history)
        logger.info(f"â ÐÑÑÐ¾ÑÐ¸Ñ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð°: {len(history)} Ð·Ð°Ð¿Ð¸ÑÐµÐ¹")
        
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
        error_msg = f"ÐÑÐ¸Ð±ÐºÐ° Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð¸ÑÑÐ¾ÑÐ¸Ð¸: {e}"
        logger.error(f"â {error_msg}")
        send_error_to_telegram(error_msg)
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    return f"ð¤ Quantum Bot v12 PRO | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    setup_logging()
    start_scheduler()
    port = int(os.environ.get("PORT", 10000))
    logger.info("ð ÐÐÐ¢ ÐÐÐÐ£Ð©ÐÐ!")
    logger.info(f"ð Ð¡ÐºÐ°Ð½Ð¸ÑÑÐµÑÑÑ {len(Config.LEAGUES)} Ð»Ð¸Ð³")
    logger.info(f"ð¤ ÐÐ°ÐºÑÐ¸Ð¼ÑÐ¼ ÑÑÐ°Ð²Ð¾Ðº: {Config.MAX_BETS_PER_RUN}")
    logger.info("â ÐÐ¾Ð½Ð¸ÑÐ¾ÑÐ¸Ð½Ð³ Ð¾ÑÐ¸Ð±Ð¾Ðº Ð²ÐºÐ»ÑÑÐµÐ½")
    app.run(host='0.0.0.0', port=port)
