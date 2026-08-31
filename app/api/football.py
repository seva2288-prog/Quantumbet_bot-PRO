import requests
import logging
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class FootballAPI:
    def __init__(self, api_key=None, base_url=None):
        from app.config import Config
        self.api_key = api_key or Config.FOOTBALL_API_KEY
        self.base_url = base_url or "https://v3.football.api-sports.io"
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 1.5  # 1.5 секунды между запросами
        
        logger.info(f"🔑 API ключ загружен: {self.api_key[:8]}..." if self.api_key else "❌ API КЛЮЧ НЕ НАЙДЕН!")
        
    def _make_request(self, endpoint, params=None):
        """Выполняет запрос к API с кэшированием"""
        try:
            # Ограничение частоты запросов
            now = time.time()
            if now - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (now - self.last_request_time))
            
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            
            url = f"{self.base_url}{endpoint}"
            
            # Логируем запрос
            logger.info(f"📡 Запрос: {endpoint}")
            logger.info(f"📡 Параметры: {params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            self.last_request_time = time.time()
            
            # Логируем ответ
            logger.info(f"📡 Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Проверяем ошибки API
                if data.get('errors'):
                    logger.error(f"❌ API ошибка: {data['errors']}")
                    return None
                
                # Проверяем наличие данных
                if 'response' in data:
                    logger.info(f"📡 Получено записей: {len(data['response'])}")
                    if len(data['response']) == 0:
                        logger.warning(f"⚠️ API вернул пустой ответ для {endpoint}")
                else:
                    logger.warning(f"⚠️ Нет ключа 'response' в ответе API")
                    
                return data
            else:
                logger.error(f"❌ API ошибка {response.status_code}: {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"❌ Таймаут запроса к API: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Ошибка соединения с API: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка запроса к API: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_matches(self, league_id, date):
        """Получает матчи по лиге и дате"""
        cache_key = f"matches_{league_id}_{date}"
        if cache_key in self.cache:
            logger.info(f"📊 Матчи для лиги {league_id} из кэша")
            return self.cache[cache_key]
        
        logger.info(f"🔍 Запрос матчей: лига={league_id}, дата={date}")
        params = {
            'league': league_id,
            'season': datetime.now().year,
            'date': date
        }
        data = self._make_request('/fixtures', params)
        
        if data and 'response' in data:
            matches = data['response']
            logger.info(f"✅ Найдено {len(matches)} матчей в лиге {league_id}")
            self.cache[cache_key] = matches
            return matches
        
        logger.warning(f"⚠️ Нет матчей для лиги {league_id} на {date}")
        return []
    
    def get_form(self, team_id):
        """Получает форму команды (последние 5 матчей)"""
        cache_key = f"form_{team_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            logger.info(f"📊 Запрос формы для команды {team_id}")
            params = {
                'team': team_id,
                'last': 5,
                'status': 'FT'
            }
            data = self._make_request('/fixtures', params)
            
            if data and 'response' in data:
                matches = data['response']
                if matches and len(matches) > 0:
                    goals_scored = []
                    goals_conceded = []
                    wins:
 = 0
                    draws = 0
                    losses = 0
                    
                    for match in                matches:
                        goals = match.get('goals', {})
                        teams = match.get('teams', {})
                        
                        # Определяем, играла ли команда дома или в гостях
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
                            'matches': len(matches if),
                            'form': self._calculate_form home(matches, team_id)
                        }
                        logger.info(f"✅ Форма команды {team_id}: {result['form']}, голы: {result['goals_avg']}")
                        self.cache[cache_key] = result
                        return result
                    else:
                        logger.warning(f"⚠️ Нет данных о голах для команды {team_id}")
                else:
                    logger.warning(f"⚠️ Нет завершенных матчей для команды {team_id}")
            else:
                logger.warning(f"⚠️ Нет данных формы для команды {team_id}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка получения формы команды {team_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def _calculate_form(self, matches, team_id):
        """Рассчитывает форму команды (последние 5 матчей)"""
        form = []
        for match in matches:
            teams = match.get('teams', {})
            goals = match.get('goals', {})
            
            home_score = goals.get('home', 0) or 0
            away_score = goals.get('away', 0) or 0
            
            if teams.get('home', {}).get('id') == team_id_score > away_score:
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
        """Получает расширенную статистику матча (xG, удары, владение)"""
        cache_key = f"stats_{fixture_id}"
        if cache_key in self.cache:
            logger.info(f"📊 Статистика для {fixture_id} из кэша")
            return self.cache[cache_key]
        
        try:
            logger.info(f"📡 Запрос статистики для матча {fixture_id}")
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
                        
                        # Обработка разных типов данных
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
                    logger.info(f"   📊 {team_name}: xG={stats.get('xG', 0)}, удары={stats.get('Total Shots', 0)}")
                
                self.cache[cache_key] = statistics
                logger.info(f"✅ Статистика получена для матча {fixture_id}")
                return statistics
            else:
                logger.warning(f"⚠️ Нет данных статистики для матча {fixture_id}")
                if data:
                    logger.warning(f"   Ответ: {data}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики матча {fixture_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def get_head_to_head(self, home_team, away_team):
        """Получает историю личных встреч"""
        cache_key = f"h2h_{home_team}_{away_team}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            logger.info(f"📊 Запрос H2H: {home_team} vs {away_team}")
            
            # Получаем ID команд
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
                            
                            logger.info(f"✅ H2H: {home_team} vs {away_team}: {result['home_wins']}-{result['draws']}-{result['away_wins']}")
                            self.cache[cache_key] = result
                            return result
                    else:
                        logger.warning(f"⚠️ Нет данных H2H для {home_team} vs {away_team}")
                else:
                    logger.warning(f"⚠️ Нет ответа H2H для {home_team} vs {away_team}")
            else:
                logger.warning(f"⚠️ Не найдены ID команд для {home_team} vs {away_team}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения H2H {home_team} vs {away_team}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def get_team_id(self, team_name):
        """Получает ID команды по названию"""
        cache_key = f"team_id_{team_name}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            logger.info(f"🔍 Поиск ID команды: {team_name}")
            params = {'name': team_name}
            data = self._make_request('/teams', params)
            
            if data and 'response' in data:
                for team in data['response']:
                    team_data = team.get('team', {})
                    if team_data.get('name', '').lower() == team_name.lower():
                        team_id = team_data.get('id')
                        logger.info(f"✅ Найден ID для {team_name}: {team_id}")
                        self.cache[cache_key] = team_id
                        return team_id
                
                # Если точное совпадение не найдено, ищем по частичному совпадению
                for team in data['response']:
                    team_data = team.get('team', {})
                    if team_name.lower() in team_data.get('name', '').lower():
                        team_id = team_data.get('id')
                        logger.info(f"✅ Найден ID для {team_name} (частичное совпадение): {team_id}")
                        self.cache[cache_key] = team_id
                        return team_id
                        
                logger.warning(f"⚠️ Команда не найдена: {team_name}")
            else:
                logger.warning(f"⚠️ Нет ответа при поиске команды {team_name}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка получения ID команды {team_name}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def get_standings(self, league_id):
        """Получает турнирную таблицу"""
        cache_key = f"standings_{league_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            logger.info(f"📊 Запрос таблицы для лиги {league_id}")
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
                
                logger.info(f"✅ Получена таблица для лиги {league_id}, команд: {len(standings)}")
                self.cache[cache_key] = standings
                return standings
            else:
                logger.warning(f"⚠️ Нет данных таблицы для лиги {league_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения таблицы {league_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def get_injuries(self, team_id):
        """Получает травмированных игроков команды"""
        cache_key = f"injuries_{team_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            logger.info(f"📊 Запрос травм для команды {team_id}")
            params = {
                'team': team_id,
                'season': datetime.now().year
            }
            data = self._make_request('/injuries', params)
            
            if data and 'response' in data:
                injuries = data['response']
                logger.info(f"✅ Найдено {len(injuries)} травм для команды {team_id}")
                self.cache[cache_key] = injuries
                return injuries
            else:
                logger.info(f"ℹ️ Нет травм для команды {team_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения травм команды {team_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return []
    
    def get_match_result(self, fixture_id):
        """Получает результат матча по ID"""
        cache_key = f"result_{fixture_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            logger.info(f"📊 Запрос результата матча {fixture_id}")
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
                    logger.info(f"✅ Результат матча {fixture_id}: {result['goals']}")
                    self.cache[cache_key] = result
                    return result
            else:
                logger.warning(f"⚠️ Нет результата для матча {fixture_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения результата {fixture_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def find_fixture_by_teams(self, home_team, away_team):
        """Находит ID матча по названиям команд"""
        try:
            logger.info(f"🔍 Поиск матча: {home_team} vs {away_team}")
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
                        fixture_id = fixture.get('fixture', {}).get('id')
                        logger.info(f"✅ Найден матч: {home} vs {away} (ID: {fixture_id})")
                        return fixture_id
                
                logger.warning(f"⚠️ Матч не найден: {home_team} vs {away_team}")
            else:
                logger.warning(f"⚠️ Нет данных для поиска матча")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка поиска матча {home_team} vs {away_team}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def get_match_odds(self, fixture_id):
        """
        Получает коэффициенты для матча из Football API
        Возвращает лучшие коэффициенты для разных типов ставок
        """
        cache_key = f"odds_{fixture_id}"
        if cache_key in self.cache:
            logger.info(f"📊 Коэффициенты для {fixture_id} из кэша")
            return self.cache[cache_key]
        
        try:
            logger.info(f"📡 Запрос коэффициентов для матча {fixture_id}")
            params = {'fixture': fixture_id}
            data = self._make_request('/fixtures/odds', params)
            
            if data and 'response' in data:
                odds_data = data['response']
                if odds_data:
                    result = self._extract_best_odds(odds_data)
                    if result.get('best_odds', 0) > 0:
                        logger.info(f"✅ Найдены коэффициенты для матча {fixture_id}: best_odds={result['best_odds']}")
                    else:
                        logger.warning(f"⚠️ Нет коэффициентов для матча {fixture_id}")
                    self.cache[cache_key] = result
                    return result
                else:
                    logger.warning(f"⚠️ Нет данных коэффициентов для матча {fixture_id}")
                    return None
            else:
                logger.warning(f"⚠️ Нет ответа коэффициентов для матча {fixture_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения коэффициентов для матча {fixture_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def _extract_best_odds(self, odds_data):
        """
        Извлекает лучшие коэффициенты из данных Football API
        Возвращает словарь с лучшими кэфами для разных исходов
        """
        result = {
            'best_odds': 0,
            'bookmaker': '—',
            'home_odds': 0,
            'draw_odds': 0,
            'away_odds': 0,
            'under_odds': 0,
            'over_odds': 0
        }
        
        # Словарь для отслеживания лучших кэфов по типам ставок
        best_odds_by_type = {}
        
        for bookmaker in odds_data:
            bookmaker_name = bookmaker.get('bookmaker', {}).get('name', '—')
            
            # Проверяем, есть ли коэффициенты у букмекера
            bets = bookmaker.get('bets', [])
            if not bets:
                continue
            
            # Ищем коэффициенты по типам ставок
            for bet in bets:
                bet_name = bet.get('name', '').lower()
                values = bet.get('values', [])
                
                if not values:
                    continue
                
                # === КОЭФФИЦИЕНТЫ НА ИСХОДЫ МАТЧА (1X2) ===
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
                
                # === КОЭФФИЦИЕНТЫ НА ТОТАЛ (OVER/UNDER) ===
                if 'тотал' in bet_name or 'total' in bet_name:
                    # Проверяем, что тотал 2.5
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
                        
                        # Обновляем best_odds, если нашли более высокий кэф
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bookmaker_name
                
                # === КОЭФФИЦИЕНТЫ НА ДВОЙНОЙ ШАНС ===
                if 'двойной' in bet_name or 'double chance' in bet_name:
                    for value in values:
                        value_name = value.get('value', '').lower()
                        odd = value.get('odd', 0)
                        
                        if odd <= 0:
                            continue
                        
                        # Сохраняем в отдельный словарь для двойного шанса
                        key = f"dc_{value_name.replace(' ', '_')}"
                        if odd > best_odds_by_type.get(key, 0):
                            best_odds_by_type[key] = odd
                        
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bookmaker_name
                
                # === КОЭФФИЦИЕНТЫ НА ОБЕ ЗАБЬЮТ (BTTS) ===
                if 'обе забьют' in bet_name or 'both teams' in bet_name:
                    for value in values:
                        value_name = value.get('value', '').lower()
                        odd = value.get('odd', 0)
                        
                        if odd <= 0:
                            continue
                        
                        if 'да' in value_name or 'yes' in value_name:
                            if odd > best_odds_by_type.get('btts_yes', 0):
                                best_odds_by_type['btts_yes'] = odd
                        elif 'нет' in value_name or 'no' in value_name:
                            if odd > best_odds_by_type.get('btts_no', 0):
                                best_odds_by_type['btts_no'] = odd
                        
                        if odd > result['best_odds']:
                            result['best_odds'] = odd
                            result['bookmaker'] = bookmaker_name
        
        # Сохраняем все найденные коэффициенты
        result['all_odds'] = best_odds_by_type
        
        logger.info(f"📊 Извлечены кэфы: home={result['home_odds']}, draw={result['draw_odds']}, away={result['away_odds']}, under={result['under_odds']}, over={result['over_odds']}")
        
        return result
    
    def get_odds_for_bet_type(self, fixture_id, bet_type):
        """
        Получает коэффициент для конкретного типа ставки
        bet_type: '1X', 'X2', 'П1', 'П2', 'under', 'over', 'btts_yes', 'btts_no'
        """
        odds_data = self.get_match_odds(fixture_id)
        if not odds_data:
            return None
        
        mapping = {
            '1X': 'dc_1_x',
            'X2': 'dc_x_2',
            'П1': 'home_odds',
            'П2': 'away_odds',
            'under': 'under_odds',
            'over': 'over_odds',
            'btts_yes': 'btts_yes',
            'btts_no': 'btts_no'
        }
        
        # Пробуем получить коэффициент
        odds_key = mapping.get(bet_type)
        if odds_key:
            # Проверяем в основном словаре
            if odds_key in odds_data and odds_data[odds_key] > 0:
                return odds_data[odds_key]
            
            # Проверяем в all_odds
            if 'all_odds' in odds_data and odds_key in odds_data['all_odds']:
                return odds_data['all_odds'][odds_key]
        
        # Если не нашли, возвращаем best_odds
        return odds_data.get('best_odds', 0)
    
    def clear_cache(self):
        """Очищает кэш"""
        self.cache = {}
        logger.info("🧹 Кэш очищен")

# Создаем глобальный экземпляр
football_api = FootballAPI()
