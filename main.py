import sys
import os
import requests
import time
import json
import logging
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import threading
import io

# ============================================================
# ИМПОРТЫ ИЗ ПРОЕКТА
# ============================================================
from app.config import Config
from app.database.storage import storage
from app.analytics.probability import calculate_ev
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
executor = ThreadPoolExecutor(max_workers=4)

# ============================================================
# ТОЛЬКО ТМ 2.5
# ============================================================
MARKERS = {
    42.86875000000006: ('under', 1.95, 'ТМ 2.5'),
    42.86875000000001: ('under', 1.95, 'ТМ 2.5'),
}

TOP_LEAGUES = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']

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
# КЛАСС FOOTBALL_API (СИНХРОННЫЙ, С КЭШИРОВАНИЕМ)
# ============================================================
class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        from app.config import Config
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 1.5
        self._lock = threading.Lock()
        
        logger.info(f"🔑 API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")
    
    def _make_request(self, endpoint, params=None):
        """Синхронный запрос к API"""
        try:
            with self._lock:
                now = time.time()
                if now - self.last_request_time < self.min_request_interval:
                    time.sleep(self.min_request_interval - (now - self.last_request_time))
                self.last_request_time = time.time()
            
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            
            url = f"{self.base_url}{endpoint}"
            logger.info(f"📡 Запрос: {endpoint}")
            if params:
                logger.info(f"📡 Параметры: {params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
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
    
    @lru_cache(maxsize=128)
    def get_matches_cached(self, league_id, date):
        return self.get_matches(league_id, date)
    
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
    
    @lru_cache(maxsize=128)
    def get_form_cached(self, team_id):
        return self.get_form(team_id)
    
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
    
    @lru_cache(maxsize=128)
    def get_match_statistics_cached(self, fixture_id):
        return self.get_match_statistics(fixture_id)
    
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
    
    @lru_cache(maxsize=128)
    def get_head_to_head_cached(self, home_team, away_team):
        return self.get_head_to_head(home_team, away_team)
    
    def get_head_to_head(self, home_team, away_team):
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
                        logger.warning(f"⚠️ API вернул пустой ответ для /fixtures/headtohead")
                        return None
            else:
                logger.warning(f"⚠️ Нет данных H2H для {home_team} vs {away_team}")
                return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения H2H {home_team} vs {away_team}: {e}")
        
        return None
    
    @lru_cache(maxsize=256)
    def get_team_id_cached(self, team_name):
        return self.get_team_id(team_name)
    
    def get_team_id(self, team_name):
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
    
    @lru_cache(maxsize=64)
    def get_standings_cached(self, league_id):
        return self.get_standings(league_id)
    
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
    
    def clear_cache(self):
        self.cache = {}
        self.get_matches_cached.cache_clear()
        self.get_form_cached.cache_clear()
        self.get_match_statistics_cached.cache_clear()
        self.get_head_to_head_cached.cache_clear()
        self.get_team_id_cached.cache_clear()
        self.get_standings_cached.cache_clear()
        logger.info("🧹 Кэш очищен")

# ============================================================
# СОЗДАЕМ ЭКЗЕМПЛЯР
# ============================================================
football_api = FootballAPI()

# ============================================================
# УЛУЧШЕНИЕ 1: КЛАСС УПРАВЛЕНИЯ РИСКАМИ
# ============================================================
class RiskManager:
    def __init__(self, bankroll):
        self.bankroll = bankroll
        self.max_stake_percent = 0.05
        self.max_daily_loss = 0.15
        self.daily_loss = 0
        self.bets_today = 0
        self.max_bets_per_day = 10
        
    def update_bankroll(self, new_bankroll):
        self.bankroll = new_bankroll
        
    def calculate_stake(self, ev, odds, prob):
        if ev < 0:
            return 0
        
        kelly_percent = (prob * odds - 1) / (odds - 1)
        kelly_percent = min(kelly_percent, self.max_stake_percent)
        
        if ev < 5:
            kelly_percent *= 0.5
        elif ev < 10:
            kelly_percent *= 0.75
        
        if self.daily_loss < -self.max_daily_loss * self.bankroll:
            kelly_percent *= 0.5
            logger.warning("⚠️ Дневной лимит проигрыша близок")
        
        if self.bets_today >= self.max_bets_per_day:
            logger.warning(f"⚠️ Достигнут лимит ставок за день ({self.max_bets_per_day})")
            return 0
        
        stake = self.bankroll * kelly_percent
        return round(stake, 2)
    
    def update_daily_loss(self, profit):
        self.daily_loss += profit
        self.bets_today += 1

# ============================================================
# УЛУЧШЕНИЕ 2: УЛУЧШЕННАЯ ВЕРОЯТНОСТЬ ТМ 2.5
# ============================================================
def calculate_under_probability(total_xg, home_goals_avg, away_goals_avg, 
                                home_conceded_avg, away_conceded_avg,
                                home_position, away_position):
    # 1. На основе XG
    if total_xg <= 1.5:
        prob_xg = 0.85
    elif total_xg <= 2.0:
        prob_xg = 0.75
    elif total_xg <= 2.3:
        prob_xg = 0.65
    elif total_xg <= 2.5:
        prob_xg = 0.55
    elif total_xg <= 2.8:
        prob_xg = 0.45
    elif total_xg <= 3.0:
        prob_xg = 0.35
    else:
        prob_xg = 0.25
    
    # 2. На основе формы команд
    avg_goals = (home_goals_avg + away_goals_avg) / 2
    avg_conceded = (home_conceded_avg + away_conceded_avg) / 2
    
    if avg_goals < 1.0 and avg_conceded < 1.0:
        prob_form = 0.80
    elif avg_goals < 1.2 and avg_conceded < 1.2:
        prob_form = 0.70
    elif avg_goals < 1.5 and avg_conceded < 1.5:
        prob_form = 0.60
    elif avg_goals < 1.8 and avg_conceded < 1.8:
        prob_form = 0.50
    else:
        prob_form = 0.40
    
    # 3. На основе турнирной позиции
    position_factor = 0
    if home_position <= 3 and away_position <= 3:
        position_factor = -0.15
    elif home_position <= 5 and away_position <= 5:
        position_factor = -0.10
    elif home_position <= 10 and away_position <= 10:
        position_factor = -0.05
    elif home_position >= 15 and away_position >= 15:
        position_factor = 0.10
    
    final_prob = prob_xg * 0.6 + prob_form * 0.3 + (prob_xg + prob_form) / 2 * 0.1
    final_prob += position_factor
    final_prob = max(0.20, min(0.90, final_prob))
    
    return final_prob

# ============================================================
# УЛУЧШЕНИЕ 3: ДЕТЕКТОР ВАЖНЫХ МАТЧЕЙ
# ============================================================
def is_important_match(home, away, home_position, away_position, league_name):
    if league_name in TOP_LEAGUES:
        if home_position <= 6 or away_position <= 6:
            return True, "Топ-матч"
    
    derbies = [
        ("Liverpool", "Everton"),
        ("Manchester United", "Manchester City"),
        ("Arsenal", "Tottenham"),
        ("Real Madrid", "Barcelona"),
        ("Atletico Madrid", "Real Madrid"),
        ("Bayern Munich", "Borussia Dortmund"),
        ("AC Milan", "Inter Milan"),
        ("Roma", "Lazio"),
        ("Celtic", "Rangers"),
        ("Fenerbahce", "Galatasaray"),
    ]
    
    for h, a in derbies:
        if (home == h and away == a) or (home == a and away == h):
            return True, f"Дерби: {h} vs {a}"
    
    return False, None

# ============================================================
# УЛУЧШЕНИЕ 4: АНАЛИЗ ВЫСОКОЙ РЕЗУЛЬТАТИВНОСТИ
# ============================================================
def analyze_high_scoring_potential(match_data, h2h_data=None):
    factors = []
    score = 0
    
    total_xg = match_data.get('total_xg', 0)
    if total_xg > 3.0:
        factors.append(f"Высокий XG: {total_xg:.2f}")
        score += 30
    elif total_xg > 2.5:
        factors.append(f"Средний XG: {total_xg:.2f}")
        score += 20
    
    home_goals_avg = match_data.get('home_goals_avg', 0)
    away_goals_avg = match_data.get('away_goals_avg', 0)
    
    if home_goals_avg > 1.8:
        factors.append(f"Дома много забивают: {home_goals_avg:.1f}")
        score += 15
    if away_goals_avg > 1.8:
        factors.append(f"В гостях много забивают: {away_goals_avg:.1f}")
        score += 15
    
    home_position = match_data.get('standings', {}).get('home_position', 99)
    away_position = match_data.get('standings', {}).get('away_position', 99)
    
    if home_position <= 3 and away_position <= 3:
        factors.append("Обе команды в топ-3")
        score += 20
    
    if h2h_data:
        avg_goals_h2h = h2h_data.get('avg_goals', 0)
        if avg_goals_h2h > 3.0:
            factors.append(f"В H2H много голов: {avg_goals_h2h:.1f}")
            score += 20
        elif avg_goals_h2h > 2.5:
            factors.append(f"В H2H средние голы: {avg_goals_h2h:.1f}")
            score += 10
    
    return {
        'score': score,
        'factors': factors,
        'is_high_scoring': score >= 50
    }

# ============================================================
# УЛУЧШЕНИЕ 5: МОНИТОРИНГ ЭФФЕКТИВНОСТИ
# ============================================================
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'total_bets': 0,
            'win_rate': 0,
            'profit': 0,
            'roi': 0,
            'avg_odds': 0,
            'avg_ev': 0,
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'current_streak': 0,
            'current_streak_type': 'none'
        }
        self._lock = threading.Lock()
    
    def update_metrics(self):
        with self._lock:
            history = storage.load_history()
            
            if not history:
                return
            
            wins = sum(1 for b in history if b.get('result') == 'win')
            losses = sum(1 for b in history if b.get('result') == 'loss')
            total_profit = sum(b.get('profit', 0) for b in history)
            total_stake = sum(b.get('stake', 0) for b in history)
            
            max_win_streak = 0
            max_loss_streak = 0
            current_streak = 0
            current_type = None
            
            for bet in history:
                result = bet.get('result')
                if result in ['win', 'loss']:
                    if current_type == result:
                        current_streak += 1
                    else:
                        current_type = result
                        current_streak = 1
                    
                    if current_type == 'win':
                        max_win_streak = max(max_win_streak, current_streak)
                    else:
                        max_loss_streak = max(max_loss_streak, current_streak)
            
            self.metrics = {
                'total_bets': len(history),
                'win_rate': round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
                'profit': round(total_profit, 2),
                'roi': round((total_profit / total_stake * 100), 1) if total_stake > 0 else 0,
                'avg_odds': round(sum(b.get('odds', 0) for b in history) / len(history), 2) if history else 0,
                'avg_ev': round(sum(b.get('ev', 0) for b in history) / len(history), 1) if history else 0,
                'max_win_streak': max_win_streak,
                'max_loss_streak': max_loss_streak,
                'current_streak': current_streak if current_type else 0,
                'current_streak_type': current_type if current_type else 'none'
            }
            
            storage.save_stats(self.metrics)

performance_monitor = PerformanceMonitor()

# ============================================================
# УЛУЧШЕНИЕ 6: ПОДРОБНОЕ ЛОГИРОВАНИЕ СТАВКИ
# ============================================================
def log_bet_analysis(bet_data):
    logger.info("=" * 60)
    logger.info(f"📊 АНАЛИЗ СТАВКИ: {bet_data.get('match', 'Unknown')}")
    logger.info("-" * 60)
    logger.info(f"📈 XG: {bet_data.get('xg_total', 0):.2f}")
    logger.info(f"📊 Вероятность ТМ 2.5: {bet_data.get('prob', 0)}%")
    logger.info(f"💹 EV: {bet_data.get('ev', 0)}%")
    logger.info(f"📊 Коэффициент: {bet_data.get('odds', 0)}")
    logger.info(f"💰 Сумма: ${bet_data.get('stake', 0)}")
    logger.info(f"📈 Форма: {bet_data.get('home_form', '')} vs {bet_data.get('away_form', '')}")
    logger.info(f"🏆 Позиции: #{bet_data.get('home_position', '?')} vs #{bet_data.get('away_position', '?')}")
    if bet_data.get('h2h_avg_goals'):
        logger.info(f"🔄 H2H средние голы: {bet_data.get('h2h_avg_goals', 0):.2f}")
    logger.info("=" * 60)

# ============================================================
# КЛАСС AUTOBET
# ============================================================
class AutoBet:
    def __init__(self):
        self.enabled = True
        self.bets_today = 0
        self.max_bets_per_day = 10
        self.risk_manager = None
        self.performance_monitor = PerformanceMonitor()
        self.bets_placed = []
        self._lock = threading.Lock()
        
    def initialize_risk_manager(self):
        bank = storage.load_bank()
        self.risk_manager = RiskManager(bank)
        
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
        
        if not self.risk_manager:
            self.initialize_risk_manager()
        
        ev = best_bet.get('ev', 0)
        odds = best_bet.get('odds', 0)
        prob = best_bet.get('prob', 0) / 100
        
        with self._lock:
            stake = self.risk_manager.calculate_stake(ev, odds, prob)
            
            if stake <= 0:
                return None
                
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
            'h2h_avg_goals': best_bet.get('h2h_avg_goals')
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
                        
                        home_name = home_team.get("name", "")
                        away_name = away_team.get("name", "")
                        h2h_data = football_api.get_head_to_head_cached(home_name, away_name)
                        
                        match["factors"] = {
                            "home_form": football_api.get_form_cached(home_id) if home_id else None,
                            "away_form": football_api.get_form_cached(away_id) if away_id else None,
                            "home_injuries_list": football_api.get_injuries(home_id) if home_id else [],
                            "away_injuries_list": football_api.get_injuries(away_id) if away_id else [],
                            "home_id": home_id,
                            "away_id": away_id,
                            "referee": fixture.get("referee"),
                            "h2h_data": h2h_data
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
    
    # Удаляем дубликаты
    seen_ids = set()
    unique_matches = []
    for match in all_matches:
        fixture = match.get("fixture", {})
        match_id = fixture.get("id")
        if match_id and match_id not in seen_ids:
            seen_ids.add(match_id)
            unique_matches.append(match)
    
    logger.info(f"📊 ВСЕГО найдено матчей: {len(unique_matches)}")
    return unique_matches

# ============================================================
# ТОП МАТЧЕЙ
# ============================================================

def find_top_matches(matches):
    bank = storage.load_bank()
    all_matches_data = []
    bets_placed = 0
    max_bets = Config.MAX_BETS_PER_RUN
    
    high_scoring_matches = []
    important_matches_list = []

    logger.info(f"🔍 Анализ {len(matches)} матчей с расширенными параметрами...")
    
    scored_matches = []
    
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
            
            h2h_data = match.get("factors", {}).get("h2h_data")
            
            # ============================================================
            # 1. ПОЛУЧАЕМ XG
            # ============================================================
            statistics = football_api.get_match_statistics_cached(fixture_id)
            
            home_xg = 1.2
            away_xg = 1.0
            home_shots = 0
            away_shots = 0
            home_shots_on_target = 0
            away_shots_on_target = 0
            home_possession = 50
            away_possession = 50
            home_corners = 0
            away_corners = 0
            
            api_worked = False
            
            if statistics:
                for team_name, stats in statistics.items():
                    if home.lower() in team_name.lower() or team_name.lower() in home.lower():
                        xg_val = stats.get('xG')
                        if xg_val is not None and xg_val > 0:
                            home_xg = float(xg_val)
                            api_worked = True
                        home_shots = stats.get('Total Shots', 0)
                        home_shots_on_target = stats.get('Shots on Goal', 0)
                        home_possession = stats.get('Possession', 50)
                        home_corners = stats.get('Corner Kicks', 0)
                    elif away.lower() in team_name.lower() or team_name.lower() in away.lower():
                        xg_val = stats.get('xG')
                        if xg_val is not None and xg_val > 0:
                            away_xg = float(xg_val)
                            api_worked = True
                        away_shots = stats.get('Total Shots', 0)
                        away_shots_on_target = stats.get('Shots on Goal', 0)
                        away_possession = stats.get('Possession', 50)
                        away_corners = stats.get('Corner Kicks', 0)
            
            if not api_worked or home_xg is None or away_xg is None:
                if league_name in FALLBACK_XG:
                    home_xg = FALLBACK_XG[league_name]['home']
                    away_xg = FALLBACK_XG[league_name]['away']
                else:
                    home_xg = 1.3
                    away_xg = 1.0
                
                random.seed(fixture_id)
                home_xg *= (1 + random.uniform(-0.1, 0.1))
                away_xg *= (1 + random.uniform(-0.1, 0.1))
            
            total_xg = home_xg + away_xg
            
            # ============================================================
            # 2. ПОЛУЧАЕМ ФОРМУ КОМАНД
            # ============================================================
            home_form_data = football_api.get_form_cached(home_team.get("id"))
            away_form_data = football_api.get_form_cached(away_team.get("id"))
            
            home_form = home_form_data.get('form', '') if home_form_data else ''
            away_form = away_form_data.get('form', '') if away_form_data else ''
            
            home_goals_avg = home_form_data.get('goals_avg', 1.2) if home_form_data else 1.2
            away_goals_avg = away_form_data.get('goals_avg', 1.0) if away_form_data else 1.0
            home_conceded_avg = home_form_data.get('conceded_avg', 1.0) if home_form_data else 1.0
            away_conceded_avg = away_form_data.get('conceded_avg', 1.2) if away_form_data else 1.2
            
            # ============================================================
            # 3. ПОЛУЧАЕМ ТУРНИРНУЮ ТАБЛИЦУ
            # ============================================================
            standings = football_api.get_standings_cached(league_id) if league_id else None
            
            home_position = 99
            away_position = 99
            home_points = 0
            away_points = 0
            
            if standings:
                if home in standings:
                    home_position = standings[home].get('position', 99)
                    home_points = standings[home].get('points', 0)
                if away in standings:
                    away_position = standings[away].get('position', 99)
                    away_points = standings[away].get('points', 0)
            
            # ============================================================
            # 4. УЛУЧШЕННЫЙ РАСЧЕТ ВЕРОЯТНОСТИ
            # ============================================================
            prob_under = calculate_under_probability(
                total_xg, home_goals_avg, away_goals_avg,
                home_conceded_avg, away_conceded_avg,
                home_position, away_position
            )
            
            # ============================================================
            # 5. РАСЧЕТ EV С КОМИССИЕЙ
            # ============================================================
            odds = 1.95
            commission = 0.05
            true_odds = odds * (1 - commission)
            ev = (prob_under * true_odds) - 1
            ev_percent = ev * 100
            
            # ============================================================
            # 6. ПРОВЕРКА НА ВАЖНЫЙ МАТЧ
            # ============================================================
            is_important, important_reason = is_important_match(
                home, away, home_position, away_position, league_name
            )
            
            # ============================================================
            # 7. АНАЛИЗ ВЫСОКОЙ РЕЗУЛЬТАТИВНОСТИ
            # ============================================================
            match_data_for_analysis = {
                'total_xg': total_xg,
                'home_goals_avg': home_goals_avg,
                'away_goals_avg': away_goals_avg,
                'standings': {
                    'home_position': home_position,
                    'away_position': away_position
                }
            }
            
            high_scoring_analysis = analyze_high_scoring_potential(match_data_for_analysis, h2h_data)
            is_high_scoring = high_scoring_analysis['is_high_scoring']
            high_scoring_factors = high_scoring_analysis['factors']
            
            # ============================================================
            # 8. СОХРАНЯЕМ ДАННЫЕ МАТЧА
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
                "home_goals_avg": home_goals_avg,
                "away_goals_avg": away_goals_avg,
                "home_shots": home_shots,
                "away_shots": away_shots,
                "home_shots_on_target": home_shots_on_target,
                "away_shots_on_target": away_shots_on_target,
                "home_possession": home_possession,
                "away_possession": away_possession,
                "home_corners": home_corners,
                "away_corners": away_corners,
                "standings": {
                    "home_position": home_position,
                    "away_position": away_position,
                    "home_points": home_points,
                    "away_points": away_points
                },
                "weather_reason": "🌤️",
                "factors": {},
                "intuition": [],
                "bets": [],
                "is_important": is_important,
                "important_reason": important_reason,
                "high_scoring_factors": high_scoring_factors,
                "h2h_data": h2h_data
            }
            
            # ============================================================
            # 9. ЕСЛИ МАТЧ С "МНОГО ГОЛОВ"
            # ============================================================
            if is_high_scoring:
                match_data['high_scoring_reason'] = ', '.join(high_scoring_factors)
                high_scoring_matches.append(match_data)
                logger.info(f"⚽ МНОГО ГОЛОВ: {home} vs {away} | {', '.join(high_scoring_factors)} | XG: {total_xg:.2f}")
                continue
            
            # ============================================================
            # 10. ФИЛЬТРУЕМ СТАВКИ
            # ============================================================
            skip_reason = None
            
            if ev_percent < 5:
                skip_reason = f"EV: {ev_percent:.1f}% (слишком низкое)"
            elif total_xg > 3.0:
                skip_reason = f"XG: {total_xg:.2f} (слишком высокий)"
            elif prob_under < 0.45:
                skip_reason = f"Prob: {prob_under*100:.1f}% (слишком низкая)"
            elif is_important:
                skip_reason = f"Важный матч: {important_reason}"
            
            if skip_reason:
                logger.info(f"⏭️ Пропускаем: {home} vs {away} | {skip_reason}")
                if is_important:
                    important_matches_list.append(match_data)
                continue
            
            # ============================================================
            # 11. ДОБАВЛЯЕМ СТАВКУ
            # ============================================================
            marker = list(MARKERS.keys())[0]
            
            match_data["bets"].append({
                "bet_type": 'under',
                "label": 'ТМ 2.5',
                "odds": odds,
                "prob": round(prob_under * 100, 1),
                "ev": round(ev_percent, 1),
                "stake": round(marker, 2),
                "marker_stake": marker,
                "xg_total": round(total_xg, 2),
                "xg_home": round(home_xg, 2),
                "xg_away": round(away_xg, 2),
                "home_form": home_form,
                "away_form": away_form,
                "home_position": home_position,
                "away_position": away_position,
                "h2h_avg_goals": h2h_data.get('avg_goals') if h2h_data else None
            })
            
            match_score = {
                'match_data': match_data,
                'score': ev_percent + (0.6 - prob_under) * 100
            }
            scored_matches.append(match_score)
            
            logger.info(f"✅ КАНДИДАТ: {home} vs {away} | XG: {total_xg:.2f} | EV: {ev_percent:.1f}% | Prob: {prob_under*100:.1f}%")
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            continue
    
    # ============================================================
    # 12. СОРТИРУЕМ И ВЫБИРАЕМ ЛУЧШИЕ
    # ============================================================
    scored_matches.sort(key=lambda x: x['score'], reverse=True)
    top_matches = scored_matches[:max_bets]
    
    logger.info(f"📊 Найдено {len(scored_matches)} кандидатов для ставок, выбрано {len(top_matches)} лучших")
    logger.info(f"⚽ Найдено {len(high_scoring_matches)} матчей с 'много голов'")
    logger.info(f"⭐ Найдено {len(important_matches_list)} важных матчей")
    
    # ============================================================
    # 13. ОТПРАВЛЯЕМ ИНФОРМАЦИЮ О ВАЖНЫХ МАТЧАХ
    # ============================================================
    if important_matches_list:
        msg = f"⭐ <b>ВАЖНЫЕ МАТЧИ</b>\n"
        msg += f"📊 Найдено: {len(important_matches_list)} матчей\n\n"
        
        for i, match_data in enumerate(important_matches_list[:5], 1):
            msg += f"{i}. <b>{match_data['home']} vs {match_data['away']}</b>\n"
            msg += f"   📅 {match_data['match_time']}\n"
            msg += f"   🏆 {match_data['league']}\n"
            msg += f"   ⭐ {match_data.get('important_reason', 'Важный матч')}\n"
            msg += f"   ⚽ XG: {match_data['total_xg']:.2f}\n"
            msg += f"   📈 Форма: {match_data['home_form']} vs {match_data['away_form']}\n"
            msg += "\n"
        
        msg += "❌ На эти матчи ставки НЕ делаются (высокая важность)"
        send_telegram(msg)
    
    # ============================================================
    # 14. ОТПРАВЛЯЕМ ИНФОРМАЦИЮ О МАТЧАХ С "МНОГО ГОЛОВ"
    # ============================================================
    if high_scoring_matches:
        msg = f"⚽ <b>МАТЧИ С ВЫСОКОЙ РЕЗУЛЬТАТИВНОСТЬЮ</b>\n"
        msg += f"📊 Найдено: {len(high_scoring_matches)} матчей\n\n"
        
        for i, match_data in enumerate(high_scoring_matches[:10], 1):
            msg += f"{i}. <b>{match_data['home']} vs {match_data['away']}</b>\n"
            msg += f"   📅 {match_data['match_time']}\n"
            msg += f"   🏆 {match_data['league']}\n"
            msg += f"   ⚽ XG: {match_data['total_xg']:.2f}\n"
            msg += f"   📊 {match_data.get('high_scoring_reason', '')}\n"
            msg += f"   📈 Форма: {match_data['home_form']} vs {match_data['away_form']}\n"
            msg += f"   🏆 Позиция: #{match_data['standings']['home_position']} vs #{match_data['standings']['away_position']}\n"
            msg += "\n"
        
        msg += "❌ На эти матчи ставки НЕ делаются (высокая результативность)"
        send_telegram(msg)
    
    # ============================================================
    # 15. РАЗМЕЩАЕМ СТАВКИ
    # ============================================================
    for item in top_matches:
        match_data = item['match_data']
        
        try:
            if auto_bet and hasattr(auto_bet, 'check_and_bet'):
                bet_result = auto_bet.check_and_bet(match_data)
                if bet_result:
                    bets_placed += 1
                    
                    log_bet_analysis(bet_result)
                    
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
                    if bet_result.get('h2h_avg_goals'):
                        msg += f"\n🔄 H2H средние голы: {bet_result['h2h_avg_goals']:.2f}"
                    send_telegram(msg)
                    logger.info(f"✅ АВТО-СТАВКА #{bets_placed}")
        except Exception as e:
            logger.error(f"❌ Ошибка авто-ставки: {e}")
    
    cache = storage.load_cache()
    cache['top_matches'] = [item['match_data'] for item in top_matches]
    cache['high_scoring_matches'] = high_scoring_matches
    cache['important_matches'] = important_matches_list
    storage.save_cache(cache)
    
    all_matches_data = [item['match_data'] for item in top_matches] + high_scoring_matches + important_matches_list
    
    return all_matches_data

# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================

def determine_bet_result(bet_type, home_goals, away_goals):
    total = home_goals + away_goals
    bet_type_lower = bet_type.lower()
    
    if 'тм 2.5' in bet_type_lower or 'under' in bet_type_lower:
        if total < 2.5:
            return 'win'
        else:
            return 'loss'
    elif 'тб 2.5' in bet_type_lower or 'over' in bet_type_lower:
        if total > 2.5:
            return 'win'
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
    performance_monitor.update_metrics()
    
    logger.info(f"📊 Статистика пересчитана: {stats}")

# ============================================================
# ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ДАННЫХ ГРАФИКА
# ============================================================
def get_profit_data(history):
    dates = []
    profits = []
    
    today = datetime.now().date()
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        
        day_profit = sum(
            b.get('profit', 0) 
            for b in history 
            if b.get('date', '').startswith(date_str)
        )
        
        dates.append(date.strftime('%d.%m'))
        profits.append(round(day_profit, 2))
    
    return {'dates': dates, 'profits': profits}

# ============================================================
# УЛУЧШЕНИЕ 7: ПОЛНЫЕ API ЭНДПОИНТЫ
# ============================================================

@app.route('/api/all_data', methods=['GET'])
def api_all_data():
    try:
        history = storage.load_history()
        stats = storage.load_stats()
        bank = storage.load_bank()
        cache = storage.load_cache()
        
        total_bets = len(history)
        wins = sum(1 for b in history if b.get('result') == 'win')
        losses = sum(1 for b in history if b.get('result') == 'loss')
        pushes = sum(1 for b in history if b.get('result') == 'push')
        total_profit = sum(b.get('profit', 0) for b in history)
        total_stake = sum(b.get('stake', 0) for b in history)
        
        winrate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
        roi = round((total_profit / total_stake * 100), 1) if total_stake > 0 else 0
        avg_stake = round(total_stake / total_bets, 2) if total_bets > 0 else 0
        
        profit_data = get_profit_data(history)
        
        return jsonify({
            'stats': {
                'bank': bank,
                'total_bets': total_bets,
                'wins': wins,
                'losses': losses,
                'pushes': pushes,
                'profit': round(total_profit, 2),
                'winrate': winrate,
                'roi': roi,
                'avg_stake': avg_stake
            },
            'history': history,
            'profit_data': profit_data,
            'cache': {
                'top_matches': cache.get('top_matches', []),
                'high_scoring_matches': cache.get('high_scoring_matches', []),
                'important_matches': cache.get('important_matches', [])
            }
        })
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit_bet', methods=['POST'])
def api_edit_bet():
    try:
        data = request.json
        index = data.get('index')
        
        history = storage.load_history()
        if index < 0 or index >= len(history):
            return jsonify({'success': False, 'error': 'Ставка не найдена'}), 404
        
        bet = history[index]
        bet['home'] = data.get('home', bet['home'])
        bet['away'] = data.get('away', bet['away'])
        bet['home_goals'] = data.get('home_goals')
        bet['away_goals'] = data.get('away_goals')
        bet['bet'] = data.get('bet', bet['bet'])
        bet['odds'] = data.get('odds', bet['odds'])
        bet['stake'] = data.get('stake', bet['stake'])
        bet['ev'] = data.get('ev', bet['ev'])
        bet['result'] = data.get('result', bet['result'])
        
        if bet['result'] == 'win':
            bet['profit'] = round(bet['stake'] * (bet['odds'] - 1), 2)
        elif bet['result'] == 'loss':
            bet['profit'] = -round(bet['stake'], 2)
        elif bet['result'] == 'push':
            bet['profit'] = 0
        else:
            bet['profit'] = 0
        
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete_bet', methods=['POST'])
def api_delete_bet():
    try:
        data = request.json
        index = data.get('index')
        
        history = storage.load_history()
        if index < 0 or index >= len(history):
            return jsonify({'success': False, 'error': 'Ставка не найдена'}), 404
        
        del history[index]
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bank', methods=['POST'])
def api_update_bank():
    try:
        data = request.json
        new_bank = data.get('bank')
        
        if new_bank is None or new_bank <= 0:
            return jsonify({'success': False, 'error': 'Неверная сумма'}), 400
        
        storage.save_bank(float(new_bank))
        auto_bet.initialize_risk_manager()
        
        return jsonify({'success': True, 'bank': float(new_bank)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/import_excel', methods=['POST'])
def api_import_excel():
    try:
        data = request.json
        imported_data = data.get('data', [])
        
        if not imported_data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        history = storage.load_history()
        count = 0
        
        for row in imported_data:
            try:
                date = row.get('Дата', '')
                match = row.get('Матч', '')
                score = row.get('Счёт', '')
                bet_type = row.get('Ставка', '')
                odds = float(row.get('Коэф', 0))
                ev = float(row.get('EV%', 0))
                stake = float(row.get('Сумма', 0))
                result = row.get('Результат', 'pending')
                
                if ' vs ' in match:
                    home, away = match.split(' vs ', 1)
                else:
                    home, away = match, ''
                
                home_goals = None
                away_goals = None
                if score and '-' in score:
                    parts = score.split('-')
                    if len(parts) == 2:
                        try:
                            home_goals = int(parts[0].strip())
                            away_goals = int(parts[1].strip())
                        except:
                            pass
                
                profit = 0
                if result == 'win':
                    profit = round(stake * (odds - 1), 2)
                elif result == 'loss':
                    profit = -round(stake, 2)
                elif result == 'push':
                    profit = 0
                
                bet = {
                    'date': date,
                    'home': home,
                    'away': away,
                    'home_goals': home_goals,
                    'away_goals': away_goals,
                    'bet': bet_type,
                    'odds': odds,
                    'ev': ev,
                    'stake': stake,
                    'result': result,
                    'profit': profit,
                    'fixture_id': None
                }
                
                history.append(bet)
                count += 1
                
            except Exception as e:
                logger.warning(f"Ошибка импорта строки: {e}")
                continue
        
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        logger.error(f"Ошибка импорта: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/import_project', methods=['POST'])
def api_import_project():
    try:
        data = request.json
        history_data = data.get('history', [])
        
        if history_data:
            current_history = storage.load_history()
            count = 0
            
            for bet in history_data:
                duplicate = False
                for existing in current_history:
                    if (existing.get('date') == bet.get('date') and
                        existing.get('home') == bet.get('home') and
                        existing.get('away') == bet.get('away') and
                        existing.get('bet') == bet.get('bet')):
                        duplicate = True
                        break
                
                if not duplicate:
                    current_history.append(bet)
                    count += 1
            
            storage.save_history(current_history)
            recalc_stats()
            
            return jsonify({'success': True, 'count': count})
        else:
            return jsonify({'success': True, 'count': 0})
    except Exception as e:
        logger.error(f"Ошибка импорта проекта: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/add_manual_match', methods=['POST'])
def api_add_manual_match():
    try:
        data = request.json
        match = data.get('match', '')
        score = data.get('score', '')
        result = data.get('result', 'pending')
        stake = data.get('stake', 0)
        bet_type = data.get('bet', '')
        odds = data.get('odds', 1.85)
        
        if not match or not bet_type:
            return jsonify({'success': False, 'error': 'Не все поля заполнены'}), 400
        
        if ' vs ' in match:
            home, away = match.split(' vs ', 1)
        else:
            home, away = match, ''
        
        home_goals = None
        away_goals = None
        if score and '-' in score:
            parts = score.split('-')
            if len(parts) == 2:
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
        
        profit = 0
        if result == 'win':
            profit = round(stake * (odds - 1), 2)
        elif result == 'loss':
            profit = -round(stake, 2)
        elif result == 'push':
            profit = 0
        
        history = storage.load_history()
        bet = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home': home,
            'away': away,
            'home_goals': home_goals,
            'away_goals': away_goals,
            'bet': bet_type,
            'odds': odds,
            'ev': 0,
            'stake': stake,
            'result': result,
            'profit': profit,
            'fixture_id': None
        }
        
        history.append(bet)
        storage.save_history(history)
        recalc_stats()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Ошибка добавления матча: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    try:
        data = request.json
        count = data.get('count', 1000)
        
        history = storage.load_history()
        if not history:
            return jsonify({'error': 'Нет данных для симуляции'}), 400
        
        bets = []
        for bet in history:
            if bet.get('result') in ['win', 'loss']:
                bets.append({
                    'stake': bet.get('stake', 0),
                    'odds': bet.get('odds', 0),
                    'result': bet.get('result', 'loss')
                })
        
        if len(bets) < 5:
            return jsonify({'error': 'Слишком мало данных (нужно минимум 5 ставок)'}), 400
        
        simulations = []
        for _ in range(count):
            selected = random.choices(bets, k=len(bets))
            
            total_profit = 0
            wins = 0
            for bet in selected:
                if bet['result'] == 'win':
                    profit = bet['stake'] * (bet['odds'] - 1)
                    total_profit += profit
                    wins += 1
                else:
                    total_profit -= bet['stake']
            
            winrate = (wins / len(selected)) * 100
            total_stake = sum(b['stake'] for b in selected)
            roi = (total_profit / total_stake) * 100 if total_stake > 0 else 0
            
            simulations.append({
                'profit': total_profit,
                'winrate': winrate,
                'roi': roi
            })
        
        profits = [s['profit'] for s in simulations]
        
        avg_profit = sum(profits) / len(profits)
        
        max_profit = max(profits)
        min_profit = min(profits)
        
        variance = sum((p - avg_profit) ** 2 for p in profits) / len(profits)
        risk = (variance ** 0.5) / (abs(avg_profit) + 1) * 100
        
        sorted_profits = sorted(profits)
        chart_history = []
        cumulative = 0
        for p in sorted_profits[:200]:
            cumulative += p
            chart_history.append(cumulative)
        
        return jsonify({
            'profit': round(avg_profit, 2),
            'winrate': round(sum(s['winrate'] for s in simulations) / len(simulations), 1),
            'roi': round(avg_profit / sum(b['stake'] for b in bets) * 100, 1) if sum(b['stake'] for b in bets) > 0 else 0,
            'risk': round(risk, 1),
            'total': len(bets),
            'wins': sum(1 for b in bets if b['result'] == 'win'),
            'losses': sum(1 for b in bets if b['result'] == 'loss'),
            'max_profit': round(max_profit, 2),
            'min_profit': round(min_profit, 2),
            'avg_stake': round(sum(b['stake'] for b in bets) / len(bets), 2),
            'history': chart_history,
            'labels': list(range(1, len(chart_history) + 1))
        })
    except Exception as e:
        logger.error(f"Ошибка симуляции: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['GET'])
def api_export():
    try:
        file, message = export_to_excel()
        if file:
            return send_file(
                file,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='quantum_bet_history.xlsx'
            )
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics', methods=['GET'])
def api_metrics():
    try:
        performance_monitor.update_metrics()
        return jsonify(performance_monitor.metrics)
    except Exception as e:
        logger.error(f"Ошибка получения метрик: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/clear', methods=['POST'])
def api_clear_cache():
    try:
        football_api.clear_cache()
        return jsonify({'success': True, 'message': 'Кэш очищен'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'ok',
        'time': datetime.now().isoformat(),
        'version': '12 PRO',
        'search_running': search_running,
        'cache_size': len(football_api.cache),
        'auto_bet_enabled': auto_bet.enabled
    })

# ============================================================
# FLASK WEBHOOK (TELEGRAM)
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
                            send_telegram("❌ Ставок не найдено")
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
                send_telegram("🔄 Проверка результатов...")
                updated = update_pending_bets()
                if updated > 0:
                    send_telegram(f"✅ Обновлено {updated} результатов!")
                else:
                    send_telegram("📭 Нет завершённых матчей")
            elif text == '/stop':
                search_running = False
                send_telegram("⏹️ Поиск остановлен")
            elif text == '/metrics':
                performance_monitor.update_metrics()
                metrics = performance_monitor.metrics
                msg = f"📊 <b>МЕТРИКИ ЭФФЕКТИВНОСТИ</b>\n\n"
                msg += f"📊 Всего ставок: {metrics['total_bets']}\n"
                msg += f"🎯 Проходимость: {metrics['win_rate']}%\n"
                msg += f"📈 Прибыль: ${metrics['profit']}\n"
                msg += f"💰 ROI: {metrics['roi']}%\n"
                msg += f"📊 Средний кэф: {metrics['avg_odds']}\n"
                msg += f"💹 Средний EV: {metrics['avg_ev']}%\n"
                msg += f"🔥 Макс. вин-стрик: {metrics['max_win_streak']}\n"
                msg += f"❄️ Макс. лосс-стрик: {metrics['max_loss_streak']}\n"
                msg += f"📈 Текущий стрик: {metrics['current_streak']} ({metrics['current_streak_type'].upper()})"
                send_telegram(msg)
            elif text == '/clear_cache':
                football_api.clear_cache()
                send_telegram("🧹 Кэш очищен!")
            else:
                send_telegram("❌ Неизвестная команда. /help")
        
        return "ok", 200
    except Exception as e:
        error_msg = f"Webhook error: {e}"
        logger.error(f"❌ {error_msg}")
        send_error_to_telegram(error_msg)
        return "ok", 200

# ============================================================
# УЛУЧШЕНИЕ 8: GRACEFUL SHUTDOWN
# ============================================================
import signal

def graceful_shutdown(signum, frame):
    logger.info("🛑 Получен сигнал остановки...")
    logger.info("🔄 Закрытие соединений...")
    football_api.clear_cache()
    logger.info("✅ Бот остановлен корректно")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    setup_logging()
    start_scheduler()
    
    auto_bet.initialize_risk_manager()
    
    port = int(os.environ.get("PORT", 10000))
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"📊 Сканируется {len(Config.LEAGUES)} лиг")
    logger.info(f"🤖 Максимум ставок: {Config.MAX_BETS_PER_RUN}")
    logger.info("✅ ВСЕ 8 УЛУЧШЕНИЙ АКТИВИРОВАНЫ:")
    logger.info("  1️⃣ 📈 Улучшенная вероятностная модель")
    logger.info("  2️⃣ 💰 Управление рисками (Келли)")
    logger.info("  3️⃣ ⭐ Детектор важных матчей")
    logger.info("  4️⃣ ⚽ Анализ высокой результативности")
    logger.info("  5️⃣ 📊 Мониторинг эффективности")
    logger.info("  6️⃣ 📝 Подробное логирование ставок")
    logger.info("  7️⃣ 🌐 Полные API эндпоинты")
    logger.info("  8️⃣ ⚡ Оптимизация производительности")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=port, threaded=True)
