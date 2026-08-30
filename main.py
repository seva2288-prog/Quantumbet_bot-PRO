import sys
import os
import requests
import time
import json
import logging
import random
import math
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ============================================================
# ИМПОРТЫ ИЗ ПРОЕКТА (С app.)
# ============================================================
from app.config import Config
from app.database.storage import storage
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
logger = get_logger(__name__)
app = Flask(__name__)

search_running = False
TIMEZONE_OFFSET = 3

# ============================================================
# МАРКЕРЫ
# ============================================================
MARKERS = {
    42.86875000000006: ('under', 1.95, 'ТМ 2.5'),
    42.86875000000001: ('under', 1.95, 'ТМ 2.5'),
}

TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

# ============================================================
# ДОМАШНЕЕ ПРЕИМУЩЕСТВО ПО ЛИГАМ
# ============================================================
HOME_ADVANTAGE = {
    'Premier League': 1.15,
    'La Liga': 1.12,
    'Bundesliga': 1.18,
    'Serie A': 1.10,
    'Ligue 1': 1.13,
    'Championship': 1.12,
    '2. Bundesliga': 1.15,
    'Eredivisie': 1.14,
    'Primeira Liga': 1.11,
    'Süper Lig': 1.16,
}

# ============================================================
# ЗАПАСНЫЕ ЗНАЧЕНИЯ XG
# ============================================================
FALLBACK_XG = {
    'Premier League': {'home': 1.6, 'away': 1.2},
    'La Liga': {'home': 1.5, 'away': 1.2},
    'Bundesliga': {'home': 1.7, 'away': 1.3},
    'Serie A': {'home': 1.5, 'away': 1.1},
    'Ligue 1': {'home': 1.5, 'away': 1.2},
    'Championship': {'home': 1.4, 'away': 1.1},
    'League One': {'home': 1.3, 'away': 1.0},
    'League Two': {'home': 1.2, 'away': 0.9},
    'La Liga 2': {'home': 1.3, 'away': 1.0},
    'Süper Lig': {'home': 1.5, 'away': 1.1},
    'Primeira Liga': {'home': 1.4, 'away': 1.1},
}

# ============================================================
# КЛАСС FOOTBALL_API
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 0.3
        
        logger.info(f"🔑 API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")
        
    def _make_request(self, endpoint, params=None):
        try:
            now = time.time()
            if now - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (now - self.last_request_time))
            
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            
            url = f"{self.base_url}{endpoint}"
            logger.info(f"📡 Запрос: {endpoint}")
            logger.info(f"📡 Параметры: {params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            self.last_request_time = time.time()
            
            logger.info(f"📡 Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('errors'):
                    logger.error(f"❌ API ошибка: {data['errors']}")
                    return None
                if 'response' in data:
                    logger.info(f"📡 Получено записей: {len(data['response'])}")
                return data
            else:
                logger.error(f"❌ API ошибка {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка запроса к API: {e}")
            return None
    
    def get_matches(self, league_id, date):
        cache_key = f"matches_{league_id}_{date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        params = {
            'league': league_id,
            'season': datetime.now().year,
            'date': date
        }
        data = self._make_request('/fixtures', params)
        
        if data and 'response' in data:
            matches = data['response']
            self.cache[cache_key] = matches
            return matches
        
        return []
    
    def get_form(self, team_id):
        cache_key = f"form_{team_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {
                'team': team_id,
                'last': 5,
                'status': 'FT'
            }
            data = self._make_request('/fixtures', params)
            
            if data and 'response' in data:
                matches = data['response']
                if matches:
                    goals_scored = []
                    goals_conceded = []
                    wins = 0
                    draws = 0
                    losses = 0
                    
                    for match in matches:
                        goals = match.get('goals', {})
                        teams = match.get('teams', {})
                        
                        if teams.get('home', {}).get('id') == team_id:
                            scored = goals.get('home', 0) or 0
                            conceded = goals.get('away', 0) or 0
                        else:
                            scored = goals.get('away', 0) or 0
                            conceded = goals.get('home', 0) or 0
                        
                        goals_scored.append(scored)
                        goals_conceded.append(conceded)
                        
                        if scored > conceded:
                            wins += 1
                        elif scored == conceded:
                            draws += 1
                        else:
                            losses += 1
                    
                    if goals_scored:
                        result = {
                            'goals_avg': round(sum(goals_scored) / len(goals_scored), 2),
                            'conceded_avg': round(sum(goals_conceded) / len(goals_conceded), 2),
                            'wins': wins,
                            'draws': draws,
                            'losses': losses,
                            'matches': len(matches),
                            'form': self._calculate_form(matches, team_id)
                        }
                        self.cache[cache_key] = result
                        return result
                        
        except Exception as e:
            logger.error(f"Ошибка получения формы команды {team_id}: {e}")
        
        return None
    
    def _calculate_form(self, matches, team_id):
        form = []
        for match in matches:
            teams = match.get('teams', {})
            goals = match.get('goals', {})
            
            home_score = goals.get('home', 0) or 0
            away_score = goals.get('away', 0) or 0
            
            if teams.get('home', {}).get('id') == team_id:
                if home_score > away_score:
                    form.append('W')
                elif home_score == away_score:
                    form.append('D')
                else:
                    form.append('L')
            else:
                if away_score > home_score:
                    form.append('W')
                elif away_score == home_score:
                    form.append('D')
                else:
                    form.append('L')
        return ''.join(form)
    
    def get_match_statistics(self, fixture_id):
        cache_key = f"stats_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'fixture': fixture_id}
            data = self._make_request('/fixtures/statistics', params)
            
            if data and 'response' in data:
                statistics = {}
                for team_stats in data['response']:
                    team_name = team_stats.get('team', {}).get('name', 'Unknown')
                    stats = {}
                    
                    for stat in team_stats.get('statistics', []):
                        key = stat.get('type', '')
                        value = stat.get('value', 0)
                        
                        if value is None:
                            value = 0
                        elif isinstance(value, str):
                            if '%' in value:
                                try:
                                    value = float(value.replace('%', ''))
                                except:
                                    value = 0
                            else:
                                try:
                                    value = float(value)
                                except:
                                    value = 0
                        elif isinstance(value, (int, float)):
                            value = float(value)
                        else:
                            value = 0
                        
                        stats[key] = value
                    
                    statistics[team_name] = stats
                
                self.cache[cache_key] = statistics
                return statistics
            else:
                logger.warning(f"⚠️ API вернул пустой ответ для /fixtures/statistics")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики матча {fixture_id}: {e}")
        
        return None
    
    def get_standings(self, league_id):
        cache_key = f"standings_{league_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {
                'league': league_id,
                'season': datetime.now().year
            }
            data = self._make_request('/standings', params)
            
            if data and 'response' in data:
                standings = {}
                for league in data['response']:
                    for standing in league.get('league', {}).get('standings', []):
                        for team in standing:
                            team_name = team.get('team', {}).get('name', '')
                            standings[team_name] = {
                                'position': team.get('rank', 0),
                                'points': team.get('points', 0),
                                'form': team.get('form', ''),
                                'goals_diff': team.get('goalsDiff', 0)
                            }
                self.cache[cache_key] = standings
                return standings
                
        except Exception as e:
            logger.error(f"Ошибка получения таблицы {league_id}: {e}")
        
        return None
    
    def get_injuries(self, team_id):
        cache_key = f"injuries_{team_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {
                'team': team_id,
                'season': datetime.now().year
            }
            data = self._make_request('/injuries', params)
            
            if data and 'response' in data:
                injuries = data['response']
                self.cache[cache_key] = injuries
                return injuries
                
        except Exception as e:
            logger.error(f"Ошибка получения травм команды {team_id}: {e}")
        
        return []
    
    def get_match_result(self, fixture_id):
        cache_key = f"result_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'id': fixture_id}
            data = self._make_request('/fixtures', params)
            
            if data and 'response' in data:
                fixtures = data['response']
                if fixtures:
                    fixture = fixtures[0]
                    goals = fixture.get('goals', {})
                    result = {
                        'goals': {
                            'home': goals.get('home'),
                            'away': goals.get('away')
                        },
                        'status': fixture.get('status', {}).get('short', 'FT')
                    }
                    self.cache[cache_key] = result
                    return result
                    
        except Exception as e:
            logger.error(f"Ошибка получения результата {fixture_id}: {e}")
        
        return None
    
    def find_fixture_by_teams(self, home_team, away_team):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            params = {
                'date': today,
                'status': 'FT'
            }
            data = self._make_request('/fixtures', params)
            
            if data and 'response' in data:
                for fixture in data['response']:
                    teams = fixture.get('teams', {})
                    home = teams.get('home', {}).get('name', '')
                    away = teams.get('away', {}).get('name', '')
                    
                    if home_team.lower() in home.lower() and away_team.lower() in away.lower():
                        return fixture.get('fixture', {}).get('id')
                        
        except Exception as e:
            logger.error(f"Ошибка поиска матча {home_team} vs {away_team}: {e}")
        
        return None
    
    def get_head_to_head(self, home_team, away_team):
        """Получает историю личных встреч"""
        cache_key = f"h2h_{home_team}_{away_team}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            home_id = self.get_team_id(home_team)
            away_id = self.get_team_id(away_team)
            
            if home_id and away_id:
                params = {
                    'h2h': f"{home_id}-{away_id}",
                    'last': 5
                }
                data = self._make_request('/fixtures/headtohead', params)
                
                if data and 'response' in data:
                    fixtures = data['response']
                    if fixtures:
                        result = {
                            'matches': [],
                            'home_wins': 0,
                            'away_wins': 0,
                            'draws': 0,
                            'goals_scored': 0,
                            'goals_conceded': 0
                        }
                        
                        for fixture in fixtures:
                            teams = fixture.get('teams', {})
                            goals = fixture.get('goals', {})
                            
                            home_score = goals.get('home', 0) or 0
                            away_score = goals.get('away', 0) or 0
                            
                            result['matches'].append({
                                'home': teams.get('home', {}).get('name', ''),
                                'away': teams.get('away', {}).get('name', ''),
                                'home_score': home_score,
                                'away_score': away_score
                            })
                            
                            if home_score > away_score:
                                result['home_wins'] += 1
                            elif home_score < away_score:
                                result['away_wins'] += 1
                            else:
                                result['draws'] += 1
                            
                            result['goals_scored'] += home_score
                            result['goals_conceded'] += away_score
                        
                        if result['matches']:
                            total_matches = len(result['matches'])
                            result['avg_goals'] = round((result['goals_scored'] + result['goals_conceded']) / total_matches, 2)
                            result['home_win_rate'] = round((result['home_wins'] / total_matches) * 100, 1)
                            result['total_matches'] = total_matches
                            
                            self.cache[cache_key] = result
                            return result
                    else:
                        logger.warning(f"⚠️ Нет данных H2H для {home_team} vs {away_team}")
            else:
                logger.warning(f"⚠️ Не найдены ID команд для H2H")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения H2H: {e}")
        
        return None
    
    def get_team_id(self, team_name):
        """Получает ID команды по названию"""
        cache_key = f"team_id_{team_name}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'name': team_name}
            data = self._make_request('/teams', params)
            
            if data and 'response' in data:
                for team in data['response']:
                    team_data = team.get('team', {})
                    if team_data.get('name', '').lower() == team_name.lower():
                        team_id = team_data.get('id')
                        self.cache[cache_key] = team_id
                        return team_id
                        
        except Exception as e:
            logger.error(f"Ошибка получения ID команды {team_name}: {e}")
        
        return None
    
    def clear_cache(self):
        self.cache = {}
        logger.info("🧹 Кэш очищен")

# ============================================================
# СОЗДАЕМ ЭКЗЕМПЛЯР
# ============================================================
football_api = FootballAPI()

# ============================================================
# КЛАСС AUTOBET
# ============================================================
class AutoBet:
    def __init__(self):
        self.enabled = True
        self.bets_today = 0
        self.max_bets_per_day = 10
        
    def check_and_bet(self, match_data):
        if not self.enabled:
            logger.warning("⚠️ AutoBet отключен")
            return None
            
        bets = match_data.get('bets', [])
        if not bets:
            return None
            
        best_bet = max(bets, key=lambda x: x.get('ev', 0))
        
        if best_bet.get('ev', 0) <= 0:
            return None
            
        if best_bet.get('odds', 0) < 1.5:
            return None
            
        bank = storage.load_bank()
        stake = best_bet.get('stake', 0)
        max_stake = bank * 0.1
        
        if stake > max_stake:
            stake = max_stake
            best_bet['stake'] = stake
            
        self.bets_today += 1
        
        return {
            'match': f"{match_data.get('home', '')} vs {match_data.get('away', '')}",
            'match_time': match_data.get('match_time', ''),
            'bet': best_bet.get('label', ''),
            'odds': best_bet.get('odds', 0),
            'stake': stake,
            'ev': best_bet.get('ev', 0),
            'marker_stake': best_bet.get('marker_stake', 0),
            'xg_total': best_bet.get('xg_total', 0),
            'prob': best_bet.get('prob', 0),
            'home_form': best_bet.get('home_form', ''),
            'away_form': best_bet.get('away_form', ''),
            'home_position': best_bet.get('home_position', '?'),
            'away_position': best_bet.get('away_position', '?'),
            'bet_type': best_bet.get('bet_type', 'under'),
            'is_over': best_bet.get('is_over', False)
        }

auto_bet = AutoBet()

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def send_error_to_telegram(error_text: str):
    try:
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
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': Config.ADMIN_CHAT_ID,
            'text': text,
            'parse_mode': parse_mode
        }
        response = requests.post(url, json=data, timeout=10)
        if response.status_code != 200:
            logger.error(f"❌ Ошибка отправки: {response.text}")
    except Exception as e:
        logger.error(f"❌ Send error: {e}")
        send_error_to_telegram(f"Ошибка отправки в Telegram: {e}")

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

def get_profit_data(history):
    """Формирует данные для графика прибыли"""
    profits = []
    days = 7
    
    for i in range(days - 1, -1, -1):
        day_profit = 0
        day = datetime.now() - timedelta(days=i)
        for bet in history:
            try:
                bet_date = datetime.strptime(bet.get('date', '').split()[0], '%Y-%m-%d')
                if bet_date.date() == day.date():
                    stake = bet.get('stake', 0)
                    if isinstance(stake, str):
                        try:
                            stake = float(stake)
                        except:
                            stake = 0
                    odds = bet.get('odds', 1)
                    if isinstance(odds, str):
                        try:
                            odds = float(odds)
                        except:
                            odds = 1
                    
                    if bet.get('result') == 'win':
                        day_profit += stake * (odds - 1)
                    elif bet.get('result') == 'loss':
                        day_profit -= stake
            except:
                pass
        profits.append(round(day_profit, 2))
    
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(days - 1, -1, -1)]
    return {'dates': dates, 'profits': profits}

# ============================================================
# НОВЫЕ ФУНКЦИИ ДЛЯ УЛУЧШЕНИЙ
# ============================================================

def get_motivation(position):
    """Определяет мотивацию команды по позиции в таблице"""
    if position <= 4:
        return 'champions_league'
    elif position <= 6:
        return 'europa_league'
    elif position <= 17:
        return 'mid_table'
    else:
        return 'relegation'

def analyze_form(form_string):
    """Анализирует форму команды (последние 5 матчей)"""
    if not form_string:
        return 'average'
    wins = form_string.count('W')
    if wins >= 4:
        return 'excellent'
    elif wins >= 3:
        return 'good'
    elif wins >= 2:
        return 'average'
    else:
        return 'poor'

def is_quality_match(home_xg, away_xg, home_position, away_position, home_form, away_form):
    """Проверяет, является ли матч качественным для ставки"""
    try:
        total_xg = home_xg + away_xg
        conditions = [
            total_xg > 1.5,
            total_xg < 3.5,
            home_position < 20,
            away_position < 20,
            len(home_form) >= 3,
            len(away_form) >= 3,
        ]
        return all(conditions)
    except:
        return False

def calculate_poisson_probability(home_xg, away_xg):
    """Рассчитывает вероятности по распределению Пуассона"""
    def poisson_prob(avg, goals):
        return (math.exp(-avg) * avg ** goals) / math.factorial(goals)
    
    home_goals_prob = [poisson_prob(home_xg, i) for i in range(6)]
    away_goals_prob = [poisson_prob(away_xg, i) for i in range(6)]
    
    prob_home_win = 0
    prob_away_win = 0
    prob_draw = 0
    prob_1X = 0
    prob_X2 = 0
    prob_over_2_5 = 0
    prob_under_2_5 = 0
    prob_btts = 0
    
    for h_g in range(6):
        for a_g in range(6):
            p = home_goals_prob[h_g] * away_goals_prob[a_g]
            total_goals = h_g + a_g
            
            if h_g > a_g:
                prob_home_win += p
            elif h_g < a_g:
                prob_away_win += p
            else:
                prob_draw += p
            
            if h_g >= a_g:
                prob_1X += p
            if a_g >= h_g:
                prob_X2 += p
            
            if total_goals > 2.5:
                prob_over_2_5 += p
            else:
                prob_under_2_5 += p
            
            if h_g > 0 and a_g > 0:
                prob_btts += p
    
    return {
        'home_win': prob_home_win,
        'away_win': prob_away_win,
        'draw': prob_draw,
        '1X': prob_1X,
        'X2': prob_X2,
        'over_2_5': prob_over_2_5,
        'under_2_5': prob_under_2_5,
        'btts': prob_btts
    }

def calculate_form_probability(home_form, away_form):
    """Рассчитывает вероятности на основе формы команд"""
    home_form_quality = analyze_form(home_form)
    away_form_quality = analyze_form(away_form)
    
    prob = {
        'home_win': 0.35,
        'away_win': 0.30,
        'draw': 0.35,
        '1X': 0.70,
        'X2': 0.65,
        'over_2_5': 0.45,
        'under_2_5': 0.55,
        'btts': 0.45
    }
    
    if home_form_quality == 'excellent' and away_form_quality == 'poor':
        prob['home_win'] += 0.15
        prob['1X'] += 0.10
        prob['away_win'] -= 0.10
        prob['X2'] -= 0.10
    elif home_form_quality == 'poor' and away_form_quality == 'excellent':
        prob['away_win'] += 0.15
        prob['X2'] += 0.10
        prob['home_win'] -= 0.10
        prob['1X'] -= 0.10
    
    return prob

def calculate_h2h_probability(h2h_data):
    """Рассчитывает вероятности на основе личных встреч"""
    prob = {
        'home_win': 0.33,
        'away_win': 0.33,
        'draw': 0.34,
        '1X': 0.67,
        'X2': 0.67,
        'over_2_5': 0.50,
        'under_2_5': 0.50,
        'btts': 0.50
    }
    
    if h2h_data:
        total = h2h_data.get('total_matches', 0)
        if total > 0:
            home_wins = h2h_data.get('home_wins', 0) / total
            away_wins = h2h_data.get('away_wins', 0) / total
            draws = h2h_data.get('draws', 0) / total
            
            prob['home_win'] = home_wins * 0.5 + 0.25
            prob['away_win'] = away_wins * 0.5 + 0.25
            prob['draw'] = draws * 0.5 + 0.25
            prob['1X'] = prob['home_win'] + prob['draw']
            prob['X2'] = prob['away_win'] + prob['draw']
            
            avg_goals = h2h_data.get('avg_goals', 2.5)
            if avg_goals > 2.5:
                prob['over_2_5'] = 0.55
                prob['under_2_5'] = 0.45
            else:
                prob['over_2_5'] = 0.45
                prob['under_2_5'] = 0.55
    
    return prob

def ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data):
    """Ансамбль моделей - комбинирует все методы"""
    poisson = calculate_poisson_probability(home_xg, away_xg)
    form_prob = calculate_form_probability(home_form, away_form)
    h2h_prob = calculate_h2h_probability(h2h_data)
    
    final_prob = {
        'home_win': poisson['home_win'] * 0.5 + form_prob['home_win'] * 0.3 + h2h_prob['home_win'] * 0.2,
        'away_win': poisson['away_win'] * 0.5 + form_prob['away_win'] * 0.3 + h2h_prob['away_win'] * 0.2,
        'draw': poisson['draw'] * 0.5 + form_prob['draw'] * 0.3 + h2h_prob['draw'] * 0.2,
        '1X': poisson['1X'] * 0.5 + form_prob['1X'] * 0.3 + h2h_prob['1X'] * 0.2,
        'X2': poisson['X2'] * 0.5 + form_prob['X2'] * 0.3 + h2h_prob['X2'] * 0.2,
        'over_2_5': poisson['over_2_5'] * 0.5 + form_prob['over_2_5'] * 0.3 + h2h_prob['over_2_5'] * 0.2,
        'under_2_5': poisson['under_2_5'] * 0.5 + form_prob['under_2_5'] * 0.3 + h2h_prob['under_2_5'] * 0.2,
        'btts': poisson['btts'] * 0.5 + form_prob['btts'] * 0.3 + h2h_prob['btts'] * 0.2
    }
    
    total_win_prob = final_prob['home_win'] + final_prob['draw'] + final_prob['away_win']
    if total_win_prob > 0:
        final_prob['home_win'] /= total_win_prob
        final_prob['away_win'] /= total_win_prob
        final_prob['draw'] /= total_win_prob
        final_prob['1X'] = final_prob['home_win'] + final_prob['draw']
        final_prob['X2'] = final_prob['away_win'] + final_prob['draw']
    
    return final_prob

# ============================================================
# ФУНКЦИЯ РУЧНОГО ОБНОВЛЕНИЯ РЕЗУЛЬТАТА
# ============================================================

def update_manual_result(match_name, score):
    """Ручное обновление результата матча"""
    try:
        home_goals = None
        away_goals = None
        if score and '-' in score:
            parts = score.split('-')
            try:
                home_goals = int(parts[0].strip())
                away_goals = int(parts[1].strip())
            except:
                return "❌ Неверный формат счета. Используй: 2-1"
        
        history = storage.load_history()
        found = False
        result = 'pending'
        
        for bet in history:
            if bet.get('result') == 'pending' or bet.get('result') is None:
                home = bet.get('home', '')
                away = bet.get('away', '')
                full_match = f"{home} vs {away}"
                
                if match_name.lower() in full_match.lower() or full_match.lower() in match_name.lower():
                    bet['home_goals'] = home_goals
                    bet['away_goals'] = away_goals
                    
                    bet_type = bet.get('bet', '')
                    result = determine_bet_result(bet_type, home_goals, away_goals)
                    bet['result'] = result
                    
                    if result == 'win':
                        bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
                    elif result == 'loss':
                        bet['profit'] = -bet['stake']
                    else:
                        bet['profit'] = 0
                    
                    found = True
                    break
        
        if found:
            storage.save_history(history)
            recalc_stats()
            
            msg = f"✅ Результат обновлен!\n"
            msg += f"🏟️ {match_name}\n"
            msg += f"⚽ Счет: {home_goals}-{away_goals}\n"
            msg += f"📊 Результат: {result}"
            return msg
        else:
            return f"❌ Матч '{match_name}' не найден в истории или уже завершен"
            
    except Exception as e:
        logger.error(f"Ошибка ручного обновления: {e}")
        return f"❌ Ошибка: {e}"

# ============================================================
# ФУНКЦИЯ АНАЛИЗА МАТЧА
# ============================================================

def analyze_match(match_name):
    """Анализирует конкретный матч и возвращает лучшую ставку"""
    try:
        cache = storage.load_cache()
        matches = cache.get('top_matches', [])
        
        for match in matches:
            home = match.get('home', '')
            away = match.get('away', '')
            full_match = f"{home} vs {away}"
            
            if match_name.lower() in full_match.lower() or full_match.lower() in match_name.lower():
                result = f"📊 <b>АНАЛИЗ МАТЧА</b>\n"
                result += f"🏟️ {full_match}\n"
                result += f"🏆 Лига: {match.get('league', 'Unknown')}\n"
                result += f"📅 Дата: {match.get('match_time', 'Unknown')}\n\n"
                
                best = match.get('best_bet', {})
                result += f"🎯 <b>ЛУЧШАЯ СТАВКА: {best.get('label', '—')}</b>\n"
                result += f"📈 EV: <b>{best.get('ev', 0)}%</b> | Вероятность: {best.get('prob', 0)}%\n"
                result += f"💰 Коэффициент: {best.get('odds', 0)}\n\n"
                
                result += "📊 <b>ВСЕ СТАВКИ:</b>\n"
                bets = match.get('bets', [])
                for i, bet in enumerate(bets[:7], 1):
                    ev = bet.get('ev', 0)
                    emoji = "🟢" if ev > 10 else ("🟡" if ev > 5 else "🔴")
                    result += f"{emoji} {i}. {bet.get('label', '—')} | EV: {bet.get('ev', 0)}% | Prob: {bet.get('prob', 0)}% | КЭФ: {bet.get('odds', 0)}\n"
                
                result += f"\n⚽ XG: {match.get('total_xg', 0):.2f}"
                result += f" | Хозяева: {match.get('home_xg', 0):.2f}"
                result += f" | Гости: {match.get('away_xg', 0):.2f}\n"
                result += f"📈 Форма: {match.get('home_form', '—')} vs {match.get('away_form', '—')}\n"
                result += f"🏆 Позиция: #{match.get('standings', {}).get('home_position', '?')} vs #{match.get('standings', {}).get('away_position', '?')}\n\n"
                
                if best.get('ev', 0) > 10:
                    result += f"💡 <b>Рекомендация: {best.get('label', '—')}</b> (EV: {best.get('ev', 0)}%) ✅"
                elif best.get('ev', 0) > 5:
                    result += f"💡 <b>Рекомендация: {best.get('label', '—')}</b> (EV: {best.get('ev', 0)}%) ⚠️"
                else:
                    result += "⚠️ <b>Ставка с низким EV</b>. Рекомендуется пропустить."
                
                return result
        
        return f"❌ Матч '{match_name}' не найден в кэше. Запустите /update сначала."
        
    except Exception as e:
        logger.error(f"Ошибка анализа матча: {e}")
        return f"❌ Ошибка: {e}"

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
# ТОП МАТЧЕЙ - ВСЕ ЛИГИ С ФИЛЬТРАМИ ДЛЯ 70%+
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN

    logger.info(f"🔍 Анализ {len(matches)} матчей из всех лиг с фильтрами для 70%+...")
    
    best_matches = []
    bet_type_count = {}
    league_count = {}
    
    for match in matches:
        if not match or not isinstance(match, dict):
            continue

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
            league_name = league_data.get("name", "Unknown") if isinstance(league_data, dict) else "Unknown"
            league_id = league_data.get("id") if isinstance(league_data, dict) else None

            match_time = fixture.get("date", "")
            if match_time:
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                    dt = dt + timedelta(hours=TIMEZONE_OFFSET)
                    match_time = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    match_time = "Время не указано"
            
            # ============================================================
            # 1. ПОЛУЧАЕМ XG
            # ============================================================
            
            statistics = football_api.get_match_statistics(fixture_id)
            
            home_xg = 1.2
            away_xg = 1.0
            
            if statistics:
                for team_name, stats in statistics.items():
                    if home.lower() in team_name.lower() or team_name.lower() in home.lower():
                        xg_val = stats.get('xG')
                        if xg_val is not None and xg_val > 0:
                            home_xg = float(xg_val)
                    elif away.lower() in team_name.lower() or team_name.lower() in away.lower():
                        xg_val = stats.get('xG')
                        if xg_val is not None and xg_val > 0:
                            away_xg = float(xg_val)
            
            if home_xg == 1.2 and away_xg == 1.0:
                if league_name in FALLBACK_XG:
                    home_xg = FALLBACK_XG[league_name]['home']
                    away_xg = FALLBACK_XG[league_name]['away']
                else:
                    home_xg = 1.3
                    away_xg = 1.0
                
                random.seed(fixture_id)
                home_xg *= (1 + random.uniform(-0.1, 0.1))
                away_xg *= (1 + random.uniform(-0.1, 0.1))
            
            # ============================================================
            # 2. ДОМАШНЕЕ ПРЕИМУЩЕСТВО
            # ============================================================
            
            home_adv = HOME_ADVANTAGE.get(league_name, 1.10)
            home_xg *= home_adv
            away_xg /= home_adv
            
            total_xg = home_xg + away_xg
            
            # ============================================================
            # 3. ФИЛЬТР: КАЧЕСТВО XG (70%+)
            # ============================================================
            
            if total_xg < 1.8 or total_xg > 3.0:
                logger.info(f"⏭️ Пропускаем (XG вне диапазона 1.8-3.0): {home} vs {away} | XG: {total_xg:.2f}")
                continue
            
            # ============================================================
            # 4. ПОЛУЧАЕМ ФОРМУ КОМАНД
            # ============================================================
            
            home_form_data = football_api.get_form(home_team.get("id"))
            away_form_data = football_api.get_form(away_team.get("id"))
            
            home_form = home_form_data.get('form', '') if home_form_data else ''
            away_form = away_form_data.get('form', '') if away_form_data else ''
            
            home_goals_avg = home_form_data.get('goals_avg', 1.2) if home_form_data else 1.2
            away_goals_avg = away_form_data.get('goals_avg', 1.0) if away_form_data else 1.0
            home_conceded_avg = home_form_data.get('conceded_avg', 1.0) if home_form_data else 1.0
            away_conceded_avg = away_form_data.get('conceded_avg', 1.2) if away_form_data else 1.2
            
            # ============================================================
            # 5. ФИЛЬТР: ФОРМА КОМАНД (70%+)
            # ============================================================
            
            home_form_quality = analyze_form(home_form)
            away_form_quality = analyze_form(away_form)
            
            if home_form_quality not in ['excellent', 'good'] or away_form_quality not in ['excellent', 'good']:
                logger.info(f"⏭️ Пропускаем (плохая форма): {home} vs {away} | H: {home_form_quality}, A: {away_form_quality}")
                continue
            
            # ============================================================
            # 6. ПОЛУЧАЕМ ТУРНИРНУЮ ТАБЛИЦУ
            # ============================================================
            
            standings = football_api.get_standings(league_id) if league_id else None
            
            home_position = 99
            away_position = 99
            
            if standings:
                if home in standings:
                    home_position = standings[home].get('position', 99)
                if away in standings:
                    away_position = standings[away].get('position', 99)
            
            # ============================================================
            # 7. ФИЛЬТР: МОТИВАЦИЯ (70%+)
            # ============================================================
            
            home_motivation = get_motivation(home_position)
            away_motivation = get_motivation(away_position)
            
            # Пропускаем матчи без мотивации (середняки)
            if home_motivation == 'mid_table' and away_motivation == 'mid_table':
                logger.info(f"⏭️ Пропускаем (нет мотивации): {home} vs {away}")
                continue
            
            # ============================================================
            # 8. ФИЛЬТР: ПОЗИЦИЯ В ТАБЛИЦЕ
            # ============================================================
            
            if home_position > 15 or away_position > 15:
                logger.info(f"⏭️ Пропускаем (низкая позиция): {home} vs {away} | H: #{home_position}, A: #{away_position}")
                continue
            
            # ============================================================
            # 9. ЛИЧНЫЕ ВСТРЕЧИ (H2H)
            # ============================================================
            
            h2h_data = football_api.get_head_to_head(home, away)
            
            # ============================================================
            # 10. АНСАМБЛЬ ВЕРОЯТНОСТЕЙ
            # ============================================================
            
            probs = ensemble_probability(home_xg, away_xg, home_form, away_form, h2h_data)
            
            prob_home_win = probs['home_win']
            prob_away_win = probs['away_win']
            prob_draw = probs['draw']
            prob_1X = probs['1X']
            prob_X2 = probs['X2']
            prob_over_2_5 = probs['over_2_5']
            prob_under_2_5 = probs['under_2_5']
            prob_btts = probs['btts']
            
            # ============================================================
            # 11. КОРРЕКТИРОВКА НА МОТИВАЦИЮ
            # ============================================================
            
            if home_motivation == 'relegation' and away_motivation == 'mid_table':
                prob_home_win += 0.10
                prob_1X += 0.08
            elif away_motivation == 'relegation' and home_motivation == 'mid_table':
                prob_away_win += 0.10
                prob_X2 += 0.08
            elif home_motivation == 'champions_league' and away_motivation == 'mid_table':
                prob_home_win += 0.08
                prob_1X += 0.05
            elif away_motivation == 'champions_league' and home_motivation == 'mid_table':
                prob_away_win += 0.08
                prob_X2 += 0.05
            
            # ============================================================
            # 12. КОЭФФИЦИЕНТЫ ДЛЯ СТАВОК
            # ============================================================
            
            odds = {
                '1X': 1.85,
                'X2': 1.85,
                'П1': 2.10,
                'П2': 2.10,
                'ТМ 2.5': 1.95,
                'ТБ 2.5': 1.95,
                'ОБЗ': 1.90,
            }
            
            # ============================================================
            # 13. РАССЧИТЫВАЕМ EV ДЛЯ ВСЕХ СТАВОК
            # ============================================================
            
            bets = []
            
            ev_1x = (prob_1X * odds['1X']) - 1
            bets.append({
                'type': '1X',
                'label': '1X',
                'prob': round(prob_1X * 100, 1),
                'ev': round(ev_1x * 100, 1),
                'odds': odds['1X'],
                'stake': round(42.86875, 2)
            })
            
            ev_x2 = (prob_X2 * odds['X2']) - 1
            bets.append({
                'type': 'X2',
                'label': 'X2',
                'prob': round(prob_X2 * 100, 1),
                'ev': round(ev_x2 * 100, 1),
                'odds': odds['X2'],
                'stake': round(42.86875, 2)
            })
            
            ev_p1 = (prob_home_win * odds['П1']) - 1
            bets.append({
                'type': 'П1',
                'label': 'П1',
                'prob': round(prob_home_win * 100, 1),
                'ev': round(ev_p1 * 100, 1),
                'odds': odds['П1'],
                'stake': round(42.86875, 2)
            })
            
            ev_p2 = (prob_away_win * odds['П2']) - 1
            bets.append({
                'type': 'П2',
                'label': 'П2',
                'prob': round(prob_away_win * 100, 1),
                'ev': round(ev_p2 * 100, 1),
                'odds': odds['П2'],
                'stake': round(42.86875, 2)
            })
            
            ev_under = (prob_under_2_5 * odds['ТМ 2.5']) - 1
            bets.append({
                'type': 'under',
                'label': 'ТМ 2.5',
                'prob': round(prob_under_2_5 * 100, 1),
                'ev': round(ev_under * 100, 1),
                'odds': odds['ТМ 2.5'],
                'stake': round(42.86875, 2)
            })
            
            ev_over = (prob_over_2_5 * odds['ТБ 2.5']) - 1
            bets.append({
                'type': 'over',
                'label': 'ТБ 2.5',
                'prob': round(prob_over_2_5 * 100, 1),
                'ev': round(ev_over * 100, 1),
                'odds': odds['ТБ 2.5'],
                'stake': round(42.86875, 2)
            })
            
            ev_btts = (prob_btts * odds['ОБЗ']) - 1
            bets.append({
                'type': 'btts',
                'label': 'ОБЗ',
                'prob': round(prob_btts * 100, 1),
                'ev': round(ev_btts * 100, 1),
                'odds': odds['ОБЗ'],
                'stake': round(42.86875, 2)
            })
            
            bets.sort(key=lambda x: x['ev'], reverse=True)
            
            best_bet = bets[0]
            
            # ============================================================
            # 14. ФИЛЬТР: EV > 20% (70%+)
            # ============================================================
            
            if best_bet['ev'] < 20:
                logger.info(f"⏭️ Пропускаем (EV < 20%): {home} vs {away} | EV: {best_bet['ev']}%")
                continue
            
            # ============================================================
            # 15. ФИЛЬТР: ВЕРОЯТНОСТЬ > 60% (70%+)
            # ============================================================
            
            if best_bet['prob'] < 60:
                logger.info(f"⏭️ Пропускаем (Prob < 60%): {home} vs {away} | Prob: {best_bet['prob']}%")
                continue
            
            # ============================================================
            # 16. ФИЛЬТР: ЛИМИТ ПО ТИПАМ СТАВОК
            # ============================================================
            
            bet_type = best_bet['type']
            bet_type_count[bet_type] = bet_type_count.get(bet_type, 0) + 1
            
            if bet_type_count[bet_type] > 3:
                logger.info(f"⏭️ Пропускаем (лимит типа {bet_type}): {home} vs {away}")
                continue
            
            # ============================================================
            # 17. ФИЛЬТР: ЛИМИТ ПО ЛИГАМ
            # ============================================================
            
            league_count[league_name] = league_count.get(league_name, 0) + 1
            
            if league_count[league_name] > 2:
                logger.info(f"⏭️ Пропускаем (лимит лиги {league_name}): {home} vs {away}")
                continue
            
            # ============================================================
            # 18. СОХРАНЯЕМ МАТЧ
            # ============================================================
            
            match_data = {
                "home": home,
                "away": away,
                "league": league_name,
                "fixture_id": fixture_id,
                "match_time": match_time,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "total_xg": round(total_xg, 2),
                "home_form": home_form,
                "away_form": away_form,
                "home_form_quality": home_form_quality,
                "away_form_quality": away_form_quality,
                "home_goals_avg": home_goals_avg,
                "away_goals_avg": away_goals_avg,
                "home_conceded_avg": home_conceded_avg,
                "away_conceded_avg": away_conceded_avg,
                "standings": {
                    "home_position": home_position,
                    "away_position": away_position,
                    "home_motivation": home_motivation,
                    "away_motivation": away_motivation
                },
                "bets": bets,
                "best_bet": best_bet,
                "weather_reason": "🌤️",
                "factors": {}
            }
            
            best_matches.append(match_data)
            
            logger.info(f"✅ КАНДИДАТ (70%+): {home} vs {away} | ЛУЧШАЯ СТАВКА: {best_bet['label']} | EV: {best_bet['ev']}% | Prob: {best_bet['prob']}%")
            
            for i, bet in enumerate(bets[:3], 1):
                logger.info(f"   {i}. {bet['label']} | EV: {bet['ev']}% | Prob: {bet['prob']}%")
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            continue
    
    # ============================================================
    # 19. СОРТИРОВКА И ВЫБОР ЛУЧШИХ
    # ============================================================
    
    best_matches.sort(key=lambda x: x['best_bet']['ev'], reverse=True)
    top_matches = best_matches[:max_bets]
    
    logger.info(f"📊 Найдено {len(best_matches)} кандидатов (70%+), выбрано {len(top_matches)} лучших")
    
    # ============================================================
    # 20. ОТПРАВКА В TELEGRAM
    # ============================================================
    
    if top_matches:
        msg = f"🎯 <b>ЛУЧШИЕ СТАВКИ (70%+)</b>\n"
        msg += f"📊 Найдено: {len(top_matches)} матчей\n\n"
        
        for i, match_data in enumerate(top_matches, 1):
            best = match_data['best_bet']
            msg += f"{i}. <b>{match_data['home']} vs {match_data['away']}</b>\n"
            msg += f"   📅 {match_data['match_time']}\n"
            msg += f"   🏆 {match_data['league']}\n"
            msg += f"   🎯 <b>{best['label']}</b> | КЭФ: {best['odds']}\n"
            msg += f"   📈 EV: <b>{best['ev']}%</b> | Вероятность: {best['prob']}%\n"
            msg += f"   ⚽ XG: {match_data['total_xg']:.2f}\n"
            msg += f"   📈 Форма: {match_data['home_form']} ({match_data['home_form_quality']}) vs {match_data['away_form']} ({match_data['away_form_quality']})\n"
            msg += f"   🏆 Позиция: #{match_data['standings']['home_position']} vs #{match_data['standings']['away_position']}\n"
            msg += f"   🔥 Мотивация: {match_data['standings']['home_motivation']} vs {match_data['standings']['away_motivation']}\n"
            msg += "\n"
        
        msg += "✅ Ставки готовы (цель 70%+)!"
        send_telegram(msg)
    
    # ============================================================
    # 21. РАЗМЕЩЕНИЕ СТАВОК
    # ============================================================
    
    for match_data in top_matches:
        try:
            if auto_bet and hasattr(auto_bet, 'check_and_bet'):
                bet_result = auto_bet.check_and_bet(match_data)
                if bet_result:
                    bets_placed += 1
                    msg = f"🤖 <b>АВТО-СТАВКА #{bets_placed}</b>\n"
                    msg += f"🏟️ {bet_result['match']}\n"
                    if bet_result.get('match_time'):
                        msg += f"📅 {bet_result['match_time']}\n"
                    msg += f"📊 {bet_result['bet']} | КЭФ: {bet_result['odds']}\n"
                    msg += f"💰 Сумма: ${bet_result['stake']}\n"
                    msg += f"📈 EV: {bet_result['ev']}%\n"
                    msg += f"⚽ XG: {bet_result.get('xg_total', 0):.2f}\n"
                    msg += f"📊 Prob: {bet_result.get('prob', 0)}%\n"
                    msg += f"📈 Форма: {bet_result.get('home_form', '')} vs {bet_result.get('away_form', '')}\n"
                    msg += f"🏆 Позиция: #{bet_result.get('home_position', '?')} vs #{bet_result.get('away_position', '?')}"
                    if bet_result.get('marker_stake'):
                        msg += f"\n🎯 Маркер: ${bet_result['marker_stake']}"
                    send_telegram(msg)
                    logger.info(f"✅ АВТО-СТАВКА #{bets_placed} (70%+)")
        except Exception as e:
            logger.error(f"❌ Ошибка авто-ставки: {e}")
    
    # ============================================================
    # 22. СОХРАНЕНИЕ В КЭШ
    # ============================================================
    
    cache = storage.load_cache()
    cache['top_matches'] = top_matches
    storage.save_cache(cache)
    
    logger.info(f"💾 Сохранено в кэш: {len(top_matches)} матчей (70%+)")
    
    return top_matches

# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================

def determine_bet_result(bet_type, home_goals, away_goals):
    total = home_goals + away_goals
    bet_type_lower = bet_type.lower()
    
    if 'п1' in bet_type_lower:
        return 'win' if home_goals > away_goals else ('push' if home_goals == away_goals else 'loss')
    elif 'п2' in bet_type_lower:
        return 'win' if away_goals > home_goals else ('push' if home_goals == away_goals else 'loss')
    elif '1x' in bet_type_lower:
        return 'win' if home_goals >= away_goals else 'loss'
    elif 'x2' in bet_type_lower:
        return 'win' if away_goals >= home_goals else 'loss'
    elif 'обз' in bet_type_lower or 'btts' in bet_type_lower:
        return 'win' if home_goals > 0 and away_goals > 0 else 'loss'
    elif 'тм 2.5' in bet_type_lower or 'under' in bet_type_lower:
        return 'win' if total < 2.5 else 'loss'
    elif 'тб 2.5' in bet_type_lower or 'over' in bet_type_lower:
        return 'win' if total > 2.5 else 'loss'
    
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
                if home and away:
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
# FLASK WEBHOOK
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
            
            answer_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery"
            try:
                requests.post(answer_url, json={
                    "callback_query_id": callback.get('id', ''),
                    "text": "✅ Результат сохранён!"
                })
            except Exception as e:
                logger.error(f"Ошибка ответа: {e}")
            
            return "ok", 200
        
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            if str(chat_id) != str(Config.ADMIN_CHAT_ID):
                logger.warning(f"⛔ ДОСТУП ЗАПРЕЩЕН для {chat_id}")
                send_telegram("⛔ Нет доступа")
                return "ok", 200
            
            if text == '/start':
                send_telegram(handlers.handle_start())
            
            elif text == '/help':
                send_telegram(handlers.handle_help())
            
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
                            elapsed = (datetime.now() - start_time).seconds
                            send_telegram(
                                f"✅ <b>ПОИСК ЗАВЕРШЕН!</b>\n"
                                f"📊 Найдено матчей: {len(matches)}\n"
                                f"🤖 Авто-ставок: {auto_bet.bets_today}\n"
                                f"⏱️ Время: {elapsed} сек."
                            )
                        else:
                            send_telegram("❌ Ставок не найдено (фильтры 70%+)")
                    else:
                        send_telegram("❌ Матчей не найдено")
                    
                    search_running = False
            
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            
            elif text == '/export':
                file, message = export_to_excel()
                if file:
                    send_telegram(message)
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
                auto_bet.enabled = not auto_bet.enabled
                send_telegram(f"🤖 AutoBet: {'ВКЛЮЧЕН' if auto_bet.enabled else 'ВЫКЛЮЧЕН'}")
            
            elif text == '/update_results':
                logger.info("🔄 Обработка /update_results")
                send_telegram("🔄 Проверка результатов матчей...")
                updated = update_pending_bets()
                if updated > 0:
                    send_telegram(f"✅ Обновлено {updated} результатов!")
                else:
                    send_telegram("📭 Нет завершённых матчей для обновления")
            
            elif text.startswith('/result'):
                logger.info("🔄 Обработка /result")
                parts = text.replace('/result', '').strip()
                if ' vs ' in parts:
                    match_part = parts.split(' vs ')
                    if len(match_part) == 2:
                        match_and_score = match_part[1].split(' ')
                        if len(match_and_score) >= 2:
                            away = match_and_score[0]
                            score = match_and_score[1] if len(match_and_score) > 1 else ''
                            home = match_part[0].strip()
                            match = f"{home} vs {away}"
                            send_telegram(f"🔄 Обновление результата: {match} {score}")
                            result = update_manual_result(match, score)
                            send_telegram(result)
                        else:
                            send_telegram("⚠️ Используй: /result Aris Thessalonikis vs OFI 2-1")
                    else:
                        send_telegram("⚠️ Используй: /result Aris Thessalonikis vs OFI 2-1")
                else:
                    send_telegram("⚠️ Используй: /result Aris Thessalonikis vs OFI 2-1")
            
            elif text.startswith('/analyze'):
                logger.info("🔄 Обработка /analyze")
                match_name = text.replace('/analyze', '').strip()
                if match_name:
                    send_telegram("🔍 Анализирую матч...")
                    result = analyze_match(match_name)
                    send_telegram(result)
                else:
                    send_telegram("⚠️ Используй: /analyze Aris Thessalonikis vs OFI")
            
            elif text == '/stop':
                search_running = False
                send_telegram("⏹️ Поиск остановлен")
            
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok", 200
    except Exception as e:
        error_msg = f"Webhook error: {e}"
        logger.error(f"❌ {error_msg}")
        send_error_to_telegram(error_msg)
        return "ok", 200

# ============================================================
# API ЭНДПОИНТЫ
# ============================================================

@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = storage.load_stats()
    bank = storage.load_bank()
    return jsonify({'bank': bank, **stats})

@app.route('/api/history', methods=['GET'])
def api_history():
    history = storage.load_history()
    return jsonify(history)

@app.route('/api/matches', methods=['GET'])
def api_matches():
    cache = storage.load_cache()
    return jsonify(cache.get('top_matches', []))

@app.route('/api/all_data', methods=['GET'])
def all_data():
    try:
        logger.info("📡 Запрос всех данных для веб-приложения")
        
        stats = storage.load_stats()
        bank = storage.load_bank()
        history = storage.load_history()
        cache = storage.load_cache()
        
        profit_data = get_profit_data(history)
        
        result = {
            'stats': {
                'bank': bank,
                'total_bets': stats.get('total', 0),
                'wins': stats.get('wins', 0),
                'losses': stats.get('losses', 0),
                'profit': stats.get('total_profit', 0),
                'winrate': stats.get('winrate', 0),
                'roi': stats.get('roi', 0),
                'avg_stake': stats.get('avg_stake', 0)
            },
            'history': history,
            'profit_data': profit_data,
            'matches': cache.get('top_matches', [])
        }
        
        logger.info(f"✅ Данные отправлены: {len(history)} ставок, {len(result['matches'])} матчей")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /api/all_data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def import_excel():
    try:
        data = request.json
        excel_data = data.get('data', [])
        
        if not excel_data:
            return jsonify({'error': 'Нет данных'}), 400
        
        history = storage.load_history()
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
            
            score = row.get('Счёт', '') or row.get('Score', '')
            home_goals = None
            away_goals = None
            if score and '-' in str(score):
                parts = str(score).split('-')
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
            
            bet = row.get('Ставка', '') or row.get('Bet', '')
            odds = float(row.get('Коэф', 1.85))
            stake = float(row.get('Сумма', 0))
            ev = float(row.get('EV%', 0))
            result = row.get('Результат', 'pending')
            profit = float(row.get('Прибыль', 0))
            date = row.get('Дата', '') or datetime.now().strftime('%Y-%m-%d %H:%M')
            
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
        
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True, 'count': imported})
        
    except Exception as e:
        logger.error(f"Ошибка импорта Excel: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def import_project():
    try:
        data = request.json
        history = data.get('history', [])
        stats = data.get('stats', {})
        
        if not history:
            return jsonify({'error': 'Нет данных для импорта'}), 400
        
        current_history = storage.load_history()
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
        
        if stats and 'bank' in stats:
            storage.save_bank(stats['bank'])
        
        storage.save_history(current_history)
        recalc_stats()
        
        return jsonify({'success': True, 'count': imported})
        
    except Exception as e:
        logger.error(f"Ошибка импорта проекта: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def edit_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        
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
        
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def delete_bet():
    try:
        data = request.json
        index = data.get('index')
        history = storage.load_history()
        
        if index >= len(history):
            return jsonify({'error': 'Ставка не найдена'}), 404
        
        history.pop(index)
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def update_bank():
    try:
        data = request.json
        if 'bank' in data:
            storage.save_bank(data['bank'])
            return jsonify({'success': True, 'bank': data['bank']})
        return jsonify({'error': 'No bank value'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        data = request.json
        count = data.get('count', 1000)
        history = storage.load_history()
        
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
        
        history = storage.load_history()
        
        bet_record = {
            'home': home or 'Unknown',
            'away': away or 'Unknown',
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
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True, 'count': 1})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@app.route('/', methods=['GET'])
def index():
    return f"🤖 Quantum Bot PRO (70%+ Target) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    setup_logging()
    start_scheduler()
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН (70%+ TARGET, ВСЕ ЛИГИ)!")
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    logger.info("🎯 ФИЛЬТРЫ ДЛЯ 70%+:") 
    logger.info("   - Все лиги из config.py")
    logger.info("   - EV > 20%")
    logger.info("   - Prob > 60%")
    logger.info("   - XG 1.8-3.0")
    logger.info("   - Форма excellent/good")
    logger.info("   - Мотивация (не середняки)")
    logger.info("   - Лимит 3 ставки на тип")
    logger.info("   - Лимит 2 ставки на лигу")
    logger.info("✅ Команды: /update_results, /result, /analyze")
    logger.info("✅ Кэш матчей сохраняется")
    app.run(host='0.0.0.0', port=port)
