import requests
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        from app.config import Config
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = {}
        self.last_request_time = 0
        # БЫЛО 1.5 -> Стало 0.2 (5 запросов в секунду, безопасно для тарифа Pro 300/мин)
        self.min_request_interval = 0.2  
        self.max_requests_per_min = 250  # Запас от лимита 300
        self.request_times = []
        
        logger.info(f"🔑 API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")

    def _wait_for_rate_limit(self):
        """Проверка и ожидание лимита запросов в минуту"""
        now = time.time()
        self.request_times = [t for t in self.request_times if now - t < 60]
        if len(self.request_times) >= self.max_requests_per_min:
            sleep_time = 60 - (now - self.request_times[0])
            logger.warning(f"⏳ Лимит {self.max_requests_per_min}/мин, ждем {sleep_time:.1f} сек")
            time.sleep(sleep_time)
        self.request_times.append(now)

    def _make_request(self, endpoint, params=None):
        try:
            self._wait_for_rate_limit()
            
            now = time.time()
            if now - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (now - self.last_request_time))
            
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=headers, params=params, timeout=15)
            self.last_request_time = time.time()

            # Логирование реального остатка лимитов
            try:
                rem_min = response.headers.get('x-ratelimit-remaining')
                lim_min = response.headers.get('x-ratelimit-limit')
                rem_day = response.headers.get('x-ratelimit-requests-remaining')
                lim_day = response.headers.get('x-ratelimit-requests-limit')
                logger.info(f"📊 Лимиты API: {rem_min}/{lim_min} в минуту | {rem_day}/{lim_day} в день")
            except:
                pass

            if response.status_code == 200:
                data = response.json()
                if data.get('errors'):
                    if 'rate limit' in str(data['errors']).lower():
                        time.sleep(60)
                    logger.error(f"❌ API ошибка: {data['errors']}")
                    return None
                return data
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"⏳ Получен 429, ждем {retry_after} сек")
                time.sleep(retry_after)
                return None
            else:
                logger.error(f"❌ API ошибка {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка запроса: {e}")
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
            logger.error(f"Ошибка получения формы: {e}")
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
                        elif isinstance(value, str) and '%' in value:
                            try:
                                value = float(value.replace('%', ''))
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
        except Exception as e:
            logger.error(f"Ошибка статистики: {e}")
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
            logger.error(f"Ошибка таблицы: {e}")
        return None
    
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
        except Exception as e:
            logger.error(f"Ошибка H2H: {e}")
        return None
    
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
            logger.error(f"Ошибка ID команды: {e}")
        return None
    
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
            logger.error(f"Ошибка результата: {e}")
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
            logger.error(f"Ошибка поиска: {e}")
        return None
    
    def get_injuries(self, team_id):
        """Получает травмированных игроков команды"""
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
    
    def get_match_odds(self, fixture_id):
        cache_key = f"odds_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            params = {'fixture': fixture_id}
            data = self._make_request('/fixtures/odds', params)
            
            if data and 'response' in data:
                odds_data = data['response']
                if odds_data:
                    result = self._extract_best_odds(odds_data)
                    if result.get('best_odds', 0) > 0:
                        logger.info(f"✅ Найдены кэфы для матча {fixture_id}")
                    self.cache[cache_key] = result
                    return result
        except Exception as e:
            logger.error(f"Ошибка кэфов: {e}")
        return None
    
    def _extract_best_odds(self, odds_data):
        result = {
            'best_odds': 0,
            'bookmaker': '—',
            'home_odds': 0,
            'draw_odds': 0,
            'away_odds': 0,
            'under_odds': 0,
            'over_odds': 0
        }
        
        for bookmaker in odds_data:
            bookmaker_name = bookmaker.get('bookmaker', {}).get('name', '—')
            bets = bookmaker.get('bets', [])
            
            for bet in bets:
                bet_name = bet.get('name', '').lower()
                values = bet.get('values', [])
                
                if not values:
                    continue
                
                if 'матч' in bet_name or 'match' in bet_name or 'побед' in bet_name:
                    for value in values:
                        value_name = value.get('value', '').lower()
                        odd = value.get('odd', 0)
                        
                        if odd <= 0:
                            continue
                        
                        if '1' in value_name or 'home' in value_name:
                            if odd > result['home_odds']:
                                result['home_odds'] = odd
                        elif '2' in value_name or 'away' in value_name:
                            if odd > result['away_odds']:
                                result['away_odds'] = odd
                        elif 'x' in value_name or 'draw' in value_name:
                            if odd > result['draw_odds']:
                                result['draw_odds'] = odd
                        
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bookmaker_name
                
                if 'тотал' in bet_name or 'total' in bet_name:
                    is_2_5 = False
                    for value in values:
                        if '2.5' in value.get('value', ''):
                            is_2_5 = True
                            break
                    
                    if not is_2_5:
                        continue
                    
                    for value in values:
                        value_name = value.get('value', '').lower()
                        odd = value.get('odd', 0)
                        
                        if odd <= 0:
                            continue
                        
                        if 'меньше' in value_name or 'under' in value_name:
                            if odd > result['under_odds']:
                                result['under_odds'] = odd
                        elif 'больше' in value_name or 'over' in value_name:
                            if odd > result['over_odds']:
                                result['over_odds'] = odd
                        
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bookmaker_name
        
        return result
    
    def clear_cache(self):
        self.cache = {}
        logger.info("🧹 Кэш очищен")

# ============================================================
# СОЗДАЕМ ЭКЗЕМПЛЯР
# ============================================================
football_api = FootballAPI()
