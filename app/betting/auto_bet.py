# app/betting/auto_bet.py
import random
from datetime import datetime
from app.config import Config
from app.database.storage import storage
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AutoBet:
    def __init__(self):
        self.enabled = True
        self.max_bets_per_day = Config.MAX_BETS_PER_DAY
        self.max_bets_per_run = Config.MAX_BETS_PER_RUN
        self.min_ev = Config.MIN_EV
        self.min_odds = Config.MIN_ODDS
        self.marker_threshold = Config.MARKER_THRESHOLD
        self.bets_today = 0
        self.last_bet_date = None

    def check_and_bet(self, match_data):
        """Проверка и автоматическая ставка"""
        if not self.enabled:
            return None

        # Проверяем лимит на день
        today = datetime.now().strftime('%Y-%m-%d')
        if self.last_bet_date != today:
            self.bets_today = 0
            self.last_bet_date = today

        if self.bets_today >= self.max_bets_per_day:
            logger.info(f"⚠️ Дневной лимит ставок исчерпан ({self.max_bets_per_day})")
            return None

        # Получаем историю для поиска маркеров
        history = storage.load_history()
        markers = self._find_markers(history)

        if not markers:
            logger.info("⚠️ Нет активных маркеров")
            return None

        # Проверяем ставки в матче
        bets = match_data.get('bets', [])
        if not bets:
            return None

        # Выбираем лучшую ставку
        best_bet = bets[0]
        ev = best_bet.get('ev', 0)
        odds = best_bet.get('odds', 0)

        if ev < self.min_ev:
            return None
        if odds < self.min_odds:
            return None

        # Находим подходящий маркер
        marker = self._find_marker_for_bet(markers, best_bet)
        if not marker:
            logger.info(f"⚠️ Нет маркера для {best_bet.get('label')}")
            return None

        # Делаем ставку
        stake = marker.get('stake', 0)
        if stake <= 0:
            stake = best_bet.get('stake', 10)

        # Проверяем банк
        bank = storage.load_bank()
        if stake > bank * 0.1:  # Не более 10% банка
            stake = round(bank * 0.05, 2)

        # Сохраняем ставку
        bet_record = {
            'home': match_data.get('home', ''),
            'away': match_data.get('away', ''),
            'league': match_data.get('league', ''),
            'bet': best_bet.get('label', ''),
            'odds': odds,
            'stake': stake,
            'ev': ev,
            'result': 'pending',
            'profit': 0,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': None,
            'away_goals': None,
            'auto': True
        }

        # Сохраняем в историю
        history.append(bet_record)
        storage.save_history(history)

        self.bets_today += 1
        logger.info(f"✅ АВТО-СТАВКА: {bet_record['bet']} на {bet_record['home']} vs {bet_record['away']}")

        return {
            'match': f"{bet_record['home']} vs {bet_record['away']}",
            'bet': bet_record['bet'],
            'odds': bet_record['odds'],
            'stake': bet_record['stake'],
            'ev': bet_record['ev'],
            'marker_stake': marker.get('stake', 0),
            'marker_type': marker.get('type', 'unknown')
        }

    def _find_markers(self, history):
        """Находит маркеры (паттерны с высокой проходимостью)"""
        if len(history) < 3:
            return []

        # Группируем по суммам
        stake_groups = {}
        for bet in history:
            stake = bet.get('stake', 0)
            if stake <= 0:
                continue

            key = str(stake)
            if key not in stake_groups:
                stake_groups[key] = {
                    'stake': stake,
                    'bets': [],
                    'wins': 0,
                    'total': 0
                }

            stake_groups[key]['bets'].append(bet)
            stake_groups[key]['total'] += 1
            if bet.get('result') == 'win':
                stake_groups[key]['wins'] += 1

        # Фильтруем маркеры (проходимость >= MARKER_THRESHOLD)
        markers = []
        for key, group in stake_groups.items():
            if group['total'] < 2:
                continue

            winrate = (group['wins'] / group['total']) * 100
            if winrate >= self.marker_threshold:
                # Определяем тип ставки
                bet_types = {}
                for bet in group['bets']:
                    bet_type = bet.get('bet', 'unknown')
                    bet_types[bet_type] = bet_types.get(bet_type, 0) + 1

                best_type = max(bet_types, key=bet_types.get) if bet_types else 'unknown'

                markers.append({
                    'stake': group['stake'],
                    'winrate': round(winrate, 1),
                    'total': group['total'],
                    'wins': group['wins'],
                    'type': best_type,
                    'confidence': round((group['wins'] / group['total']) * 100, 1)
                })

        # Сортируем по проходимости
        markers.sort(key=lambda x: x['winrate'], reverse=True)
        logger.info(f"🎯 Найдено маркеров: {len(markers)}")

        # Логируем маркеры
        for m in markers:
            logger.info(f"   📊 ${m['stake']} → {m['type']} ({m['winrate']}%)")

        return markers

    def _find_marker_for_bet(self, markers, bet):
        """Находит подходящий маркер для ставки"""
        if not markers:
            return None

        bet_label = bet.get('label', '')

        # Проверяем соответствие типа ставки
        for marker in markers:
            marker_type = marker.get('type', '')
            if marker_type.lower() in bet_label.lower():
                return marker

        # Если не нашли точное совпадение, берем лучший маркер
        return markers[0] if markers else None
