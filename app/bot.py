import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
import time
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
from app.scheduler import start_scheduler

# ============================================================
# ПРЯМОЙ ИМПОРТ AutoBet (БЕЗ ЛЕНИВОЙ ЗАГРУЗКИ)
# ============================================================
from app.betting.auto_bet import AutoBet
auto_bet = AutoBet()

logger = get_logger(__name__)
app = Flask(__name__)

search_running = False
TIMEZONE_OFFSET = 3

def send_error_to_telegram(error_text: str):
    try:
        import requests
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        if len(error_text) > 4000:
            error_text = error_text[:4000] + "...(обрезано)"
        data = {
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': f"❌ <b>ОШИБКА БОТА</b>\n\n{error_text}",
            'parse_mode': 'HTML'
        }
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Не удалось отправить ошибку в Telegram: {e}")

def send_telegram(text: str, parse_mode: str = 'HTML'):
    import requests
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id': Config.ADMIN_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code != 200:
            logger.error(f"❌ Ошибка отправки: {response.text}")
    except Exception as e:
        logger.error(f"❌ Send error: {e}")
        send_error_to_telegram(f"Ошибка отправки в Telegram: {e}")

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
# ПОИСК МАТЧЕЙ
# ============================================================

def get_matches_with_factors():
    all_matches = []
    today = datetime.now().strftime('%Y-%m-%d')
    dates_to_search = [today]
    
    logger.info(f"🔍 Поиск матчей на: {today}")
    
    all_leagues = Config.LEAGUES + getattr(Config, 'CUP_LEAGUES', [])
    logger.info(f"📊 Всего соревнований: {len(all_leagues)}")
    
    for league_id in all_leagues:
        for search_date in dates_to_search:
            try:
                matches = football_api.get_matches(league_id, search_date)
                league_name = Config.LEAGUE_NAMES.get(league_id, str(league_id))
                
                if not matches or not isinstance(matches, list):
                    logger.info(f"🔥 Нет матчей в {league_name} на {search_date}")
                    continue
                
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                    
                    fixture = match.get("fixture")
                    if not fixture or not isinstance(fixture, dict):
                        continue
                    
                    status = fixture.get("status", {})
                    if not isinstance(status, dict):
                        continue
                    
                    if status.get("short") == "NS":
                        match_id = fixture.get("id")
                        if not match_id:
                            continue
                        
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
                        match["weather_reason"] = "🌤️ Погода отключена"
                        
                        league_data = match.get("league", {})
                        if isinstance(league_data, dict):
                            league_data["name"] = league_name
                        
                        all_matches.append(match)
                        
            except Exception as e:
                error_msg = f"Ошибка {league_name} на {search_date}: {e}"
                logger.error(f"❌ {error_msg}")
                send_error_to_telegram(error_msg)
            
            time.sleep(0.1)
    
    logger.info(f"📊 ВСЕГО найдено матчей: {len(all_matches)}")
    return all_matches

# ============================================================
# ПАРСИНГ КОЭФФИЦИЕНТОВ
# ============================================================

def parse_odds(odds_data):
    """Парсинг коэффициентов из API"""
    if not odds_data:
        return None
    
    bookmakers = odds_data.get('bookmakers', [])
    if not bookmakers:
        return None
    
    bookmaker = bookmakers[0]
    bets = bookmaker.get('bets', [])
    
    odds_dict = {}
    for bet in bets:
        values = bet.get('values', [])
        for value in values:
            bet_type = value.get('value', '')
            odd = value.get('odd')
            if bet_type and odd:
                odds_dict[bet_type] = odd
    
    return odds_dict

# ============================================================
# РАСЧЕТ XG С УЧЕТОМ ФАКТОРОВ
# ============================================================

def calculate_adjusted_xg(home_id, away_id, factors):
    """Расчет XG с учетом формы, травм и других факторов"""
    home_xg = 1.2
    away_xg = 1.0
    
    # 1. Форма команд (последние 5 матчей)
    home_form = factors.get('home_form', '')
    away_form = factors.get('away_form', '')
    
    if home_form:
        home_form_points = 0
        for letter in home_form:
            if letter == 'W':
                home_form_points += 3
            elif letter == 'D':
                home_form_points += 1
        home_form_ratio = home_form_points / (len(home_form) * 3) if home_form else 0.5
        home_xg *= (0.8 + home_form_ratio * 0.4)
        logger.info(f"   📊 Форма хозяев: {home_form} (коэф: {0.8 + home_form_ratio * 0.4:.2f})")
    
    if away_form:
        away_form_points = 0
        for letter in away_form:
            if letter == 'W':
                away_form_points += 3
            elif letter == 'D':
                away_form_points += 1
        away_form_ratio = away_form_points / (len(away_form) * 3) if away_form else 0.5
        away_xg *= (0.8 + away_form_ratio * 0.4)
        logger.info(f"   📊 Форма гостей: {away_form} (коэф: {0.8 + away_form_ratio * 0.4:.2f})")
    
    # 2. Травмы
    home_injuries = factors.get('home_injuries_list', [])
    away_injuries = factors.get('away_injuries_list', [])
    
    if home_injuries:
        injury_penalty = min(len(home_injuries) * 0.05, 0.3)
        home_xg *= (1 - injury_penalty)
        logger.info(f"   🏥 Травмы хозяев: {len(home_injuries)} игроков (пенальти: {injury_penalty*100:.0f}%)")
    
    if away_injuries:
        injury_penalty = min(len(away_injuries) * 0.05, 0.3)
        away_xg *= (1 - injury_penalty)
        logger.info(f"   🏥 Травмы гостей: {len(away_injuries)} игроков (пенальти: {injury_penalty*100:.0f}%)")
    
    # 3. Преимущество домашнего поля
    home_xg *= 1.1
    away_xg *= 0.9
    logger.info(f"   🏠 Преимущество домашнего поля: +10% для хозяев, -10% для гостей")
    
    return home_xg, away_xg

# ============================================================
# ТОП-20 МАТЧЕЙ
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN

    logger.info(f"🔍 Анализ {len(matches)} матчей...")
    
    # ============================================================
    # ВСЕ МАРКЕРЫ И ТИПЫ СТАВОК
    # ============================================================
    BET_TYPES = [
        {'type': 'under', 'label': 'ТМ 2.5', 'marker': 42.86875000000006, 'keys': ['Under 2.5', 'Under', 'U 2.5']},
        {'type': 'btts', 'label': 'ОБЗ', 'marker': 40.7253125, 'keys': ['Both Team Score', 'BTTS', 'Both Teams to Score']},
        {'type': '1X', 'label': '1X', 'marker': 45.125, 'keys': ['Home/Draw', '1X']},
        {'type': 'over', 'label': 'ТБ 2.5', 'marker': 41.375, 'keys': ['Over 2.5', 'Over', 'O 2.5']},
        {'type': 'X2', 'label': 'X2', 'marker': 43.1875, 'keys': ['Away/Draw', 'X2']},
    ]
    
    for match in matches:
        if not match or not isinstance(match, dict):
            continue
        
        if bets_placed >= max_bets:
            logger.info(f"⚠️ Достигнут лимит ставок: {max_bets}")
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
            
            logger.info(f"📊 Анализ: {home} vs {away} (ID: {fixture_id})")
            
            # ============================================================
            # 1. ПОЛУЧАЕМ КОЭФФИЦИЕНТЫ
            # ============================================================
            odds_data = football_api.get_match_odds(fixture_id)
            
            if not odds_data:
                logger.warning(f"⚠️ Нет коэффициентов для {home} vs {away}")
                continue
            
            odds_dict = parse_odds(odds_data)
            
            if not odds_dict:
                logger.warning(f"⚠️ Не удалось распарсить коэффициенты для {home} vs {away}")
                continue
            
            logger.info(f"   📊 Доступные коэффициенты: {odds_dict}")
            
            # ============================================================
            # 2. РАСЧЕТ XG С УЧЕТОМ ВСЕХ ФАКТОРОВ
            # ============================================================
            factors = match.get('factors', {})
            home_id = factors.get('home_id')
            away_id = factors.get('away_id')
            
            home_xg, away_xg = calculate_adjusted_xg(home_id, away_id, factors)
            
            logger.info(f"   📈 Итоговый XG: {home} {home_xg:.2f} - {away_xg:.2f} {away}")
            
            # ============================================================
            # 3. РАСЧЕТ ВЕРОЯТНОСТЕЙ
            # ============================================================
            probs = calculate_probabilities(home_xg, away_xg)
            
            league_data = match.get("league")
            league = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"

            match_time = fixture.get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            match_data = {
                "home": home,
                "away": away,
                "league": league,
                "fixture_id": fixture_id,
                "match_time": match_time,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "weather_reason": "🌤️",
                "factors": factors,
                "intuition": [],
                "bets": []
            }

            # ============================================================
            # 4. ПРОВЕРЯЕМ КАЖДЫЙ ТИП СТАВКИ
            # ============================================================
            for bet_config in BET_TYPES:
                bet_type = bet_config['type']
                label = bet_config['label']
                marker = bet_config['marker']
                keys = bet_config['keys']
                
                # Ищем коэффициент
                odds = None
                for key in keys:
                    if key in odds_dict:
                        odds = odds_dict[key]
                        break
                
                if not odds:
                    logger.info(f"   ⏭️ Нет коэффициента для {label}")
                    continue
                
                # Получаем вероятность
                prob = probs.get(bet_type, 0.33)
                
                # Считаем EV
                ev = calculate_ev(prob, odds)
                
                logger.info(f"   📊 {label}: prob={prob*100:.1f}%, odds={odds}, ev={ev}%")
                
                # ============================================================
                # 5. ЕСЛИ EV > 5% — ДОБАВЛЯЕМ СТАВКУ
                # ============================================================
                if ev < 5:
                    logger.info(f"   ⏭️ Пропуск {label}: EV={ev}% < 5%")
                    continue
                
                match_data["bets"].append({
                    "bet_type": bet_type,
                    "label": label,
                    "odds": odds,
                    "prob": round(prob * 100, 1),
                    "ev": round(ev, 1),
                    "stake": round(marker, 2),
                    "marker_stake": marker
                })
                logger.info(f"   ✅ ДОБАВЛЕНА СТАВКА: {label} | КЭФ: {odds} | EV: {ev}% | Маркер: {marker}")

            if match_data["bets"]:
                all_matches_data.append(match_data)
                
                try:
                    bet_result = auto_bet.check_and_bet(match_data)
                    if bet_result:
                        bets_placed += 1
                        msg = f"🤖 <b>АВТО-СТАВКА #{bets_placed}</b>\n"
                        msg += f"🏟️ {bet_result['match']}\n"
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
                    logger.error(f"❌ Ошибка авто-ставки: {e}")

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            continue

    logger.info(f"📊 Найдено {len(all_matches_data)} матчей, сделано {bets_placed} ставок")
    
    cache = storage.load_cache()
    cache['top_matches'] = all_matches_data
    storage.save_cache(cache)
    
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
        
        logger.info("=" * 50)
        logger.info(f"📨 ПОЛУЧЕН ЗАПРОС ОТ TELEGRAM")
        logger.info("=" * 50)
        
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
                                    error_msg = f"Ошибка сохранения результата: {e}"
                                    logger.error(f"❌ {error_msg}")
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
            
            logger.info(f"👤 CHAT ID: {chat_id}")
            logger.info(f"📝 ТЕКСТ: {text}")
            logger.info(f"🔑 ADMIN ID: {Config.ADMIN_CHAT_ID}")
            
            if str(chat_id) != str(Config.ADMIN_CHAT_ID):
                logger.warning(f"⛔ ДОСТУП ЗАПРЕЩЕН для {chat_id}")
                send_telegram("⛔ Нет доступа")
                return "ok", 200
            
            logger.info(f"✅ ДОСТУП РАЗРЕШЕН для {chat_id}")
            
            if text == '/start':
                logger.info("🔄 Обработка /start")
                send_telegram(handlers.handle_start())
            
            elif text == '/help':
                logger.info("🔄 Обработка /help")
                send_telegram(handlers.handle_help())
            
            elif text == '/update':
                logger.info("🔄 Обработка /update")
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
                            elapsed = (datetime.now() - start_time).seconds
                            send_telegram(
                                f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                                f"📊 Найдено матчей: {len(matches)}\n"
                                f"🤖 Авто-ставок: {auto_bet.bets_today if auto_bet else 0}\n"
                                f"⏱️ Время: {elapsed} сек."
                            )
                        else:
                            send_telegram("❌ Ставок не найдено")
                    else:
                        send_telegram("❌ Матчей не найдено")

                    search_running = False
            
            elif text == '/today':
                send_telegram(handlers.handle_today())
            
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            
            elif text == '/bettypes':
                send_telegram(handlers.handle_bettypes())
            
            elif text == '/timestats':
                send_telegram(handlers.handle_timestats())
            
            elif text == '/mlstats':
                send_telegram(handlers.handle_mlstats())
            
            elif text == '/report':
                send_telegram(handlers.handle_report())
            
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
                        logger.info("✅ Excel отправлен")
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла: {e}")
                else:
                    send_telegram(message)
            
            elif text == '/autobet':
                auto_bot_enabled = not getattr(auto_bet, 'enabled', True)
                auto_bet.enabled = auto_bot_enabled
                send_telegram(handlers.handle_autobet(auto_bot_enabled))
            
            elif text == '/train':
                send_telegram(handlers.handle_train())
            
            elif text == '/arb':
                send_telegram(handlers.handle_arb())
            
            elif text == '/anomalies':
                send_telegram(handlers.handle_anomalies())
            
            elif text == '/security':
                send_telegram(handlers.handle_security())
            
            elif text == '/stop':
                search_running = False
                send_telegram(handlers.handle_stop())
            
            elif text == '/update_results':
                send_telegram("🔄 Проверка результатов матчей...")
                updated = update_pending_bets()
                if updated > 0:
                    send_telegram(f"✅ Обновлено {updated} результатов!")
                else:
                    send_telegram("📭 Нет завершённых матчей для обновления")
            
            elif text.startswith('/team'):
                team_name = text.replace('/team', '').strip()
                send_telegram(handlers.handle_team(team_name))
            
            elif text.startswith('/unblock'):
                ip = text.replace('/unblock', '').strip()
                send_telegram(handlers.handle_unblock(ip))
            
            elif text.startswith('/result'):
                parts = text.replace('/result', '').strip()
                if ' vs ' in parts:
                    match_part = parts.split(' vs ')
                    if len(match_part) == 2:
                        match_parts = match_part[1].split(' ')
                        if len(match_parts) >= 2:
                            away = match_parts[0]
                            score = match_parts[1] if len(match_parts) > 1 else ''
                            match = match_part[0].strip() + ' vs ' + away
                            send_telegram(handlers.handle_result(match, score))
                        else:
                            send_telegram("⚠️ Используй: /result Fulham vs Chelsea 2-1")
                    else:
                        send_telegram("⚠️ Используй: /result Fulham vs Chelsea 2-1")
                else:
                    send_telegram("⚠️ Используй: /result Fulham vs Chelsea 2-1")
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        logger.info("✅ Webhook завершен")
        return "ok", 200
    except Exception as e:
        error_msg = f"Webhook error: {e}"
        logger.error(f"❌ {error_msg}")
        send_error_to_telegram(error_msg)
        return "ok", 200

# ============================================================
# АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================

def determine_bet_result(bet_type, home_goals, away_goals):
    total = home_goals + away_goals
    bet_type_lower = bet_type.lower()
    
    if 'оз - да' in bet_type_lower or 'обз' in bet_type_lower or 'btts' in bet_type_lower:
        if home_goals > 0 and away_goals > 0:
            return 'win'
        else:
            return 'loss'
    elif 'тм 2.5' in bet_type_lower or 'under' in bet_type_lower:
        if total < 2.5:
            return 'win'
        else:
            return 'loss'
    elif 'тб 2.5' in bet_type_lower or 'over' in bet_type_lower:
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
    elif 'п1' in bet_type_lower or 'победа хозяев' in bet_type_lower:
        if home_goals > away_goals:
            return 'win'
        elif home_goals == away_goals:
            return 'push'
        else:
            return 'loss'
    elif 'п2' in bet_type_lower or 'победа гостей' in bet_type_lower:
        if away_goals > home_goals:
            return 'win'
        elif home_goals == away_goals:
            return 'push'
        else:
            return 'loss'
    return 'pending'

def update_pending_bets():
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
                            logger.info(f"✅ Обновлена ставка: {bet['home']} vs {bet['away']} → {result} ({home_goals}-{away_goals})")
    
    if updated > 0:
        storage.save_history(history)
        recalc_stats()
        send_telegram(f"✅ Автоматически обновлено {updated} результатов!")
    
    return updated

def recalc_stats():
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
    logger.info(f"📊 Статистика пересчитана: {stats}")

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
        error_msg = f"Ошибка обновления истории: {e}"
        logger.error(f"❌ {error_msg}")
        send_error_to_telegram(error_msg)
        return jsonify({'error': str(e)}), 500

@app.route('/api/matches', methods=['GET'])
def api_matches():
    cache = storage.load_cache()
    matches = cache.get('top_matches', [])
    return jsonify(matches)

@app.route('/', methods=['GET'])
def index():
    return f"🤖 Quantum Bot v12 PRO | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    setup_logging()
    start_scheduler()
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    logger.info("✅ Мониторинг ошибок включен")
    app.run(host='0.0.0.0', port=port)
