# app/betting/auto_bet.py
from datetime import datetime
from app.config import Config
from app.database.storage import storage
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AutoBet:
    def __init__(self):
        self.enabled = True
        self.max_bets_per_day = getattr(Config, 'MAX_BETS_PER_DAY', 20)
        self.max_bets_per_run = getattr(Config, 'MAX_BETS_PER_RUN', 20)
        self.min_ev = getattr(Config, 'MIN_EV', 5)
        self.min_odds = getattr(Config, 'MIN_ODDS', 1.5)
        self.marker_threshold = getattr(Config, 'MARKER_THRESHOLD', 80)
        self.bets_today = 0
        self.last_bet_date = None

    def check_and_bet(self, match_data):
        """Проверка и автоматическая ставка"""
        if not self.enabled:
            return None

        today = datetime.now().strftime('%Y-%m-%d')
        if self.last_bet_date != today:
            self.bets_today = 0
            self.last_bet_date = today

        if self.bets_today >= self.max_bets_per_day:
            logger.info(f"⚠️ Дневной лимит ставок исчерпан ({self.max_bets_per_day})")
            return None

        history = storage.load_history()
        markers = self._find_markers(history)

        if not markers:
            logger.info("⚠️ Нет активных маркеров")
            return None

        bets = match_data.get('bets', [])
        if not bets:
            return None

        best_bet = bets[0]
        ev = best_bet.get('ev', 0)
        odds = best_bet.get('odds', 0)

        if ev < self.min_ev:
            return None
        if odds < self.min_odds:
            return None

        marker = self._find_marker_for_bet(markers, best_bet)
        if not marker:
            logger.info(f"⚠️ Нет маркера для {best_bet.get('label')}")
            return None

        stake = marker.get('stake', 0)
        if stake <= 0:
            stake = best_bet.get('stake', 10)

        bank = storage.load_bank()
        if stake > bank * 0.1:
            stake = round(bank * 0.05, 2)

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
        markers = []

        # ============================================================
        # 1. АВТОМАТИЧЕСКИЕ МАРКЕРЫ ИЗ ИСТОРИИ
        # ============================================================
        if len(history) >= 3:
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

            for key, group in stake_groups.items():
                if group['total'] < 2:
                    continue

                winrate = (group['wins'] / group['total']) * 100
                if winrate >= self.marker_threshold:
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

        # ============================================================
        # 2. РУЧНЫЕ МАРКЕРЫ (ВСЕГДА АКТИВНЫ)
        # ============================================================
        manual_markers = [
            # Маркер 1: 1X
            {
                'stake': 45.125,
                'winrate': 100.0,
                'total': 7,
                'wins': 7,
                'type': '1X',
                'confidence': 100.0
            },
            # Маркер 2: ТМ 2.5
            {
                'stake': 42.86875000000006,
                'winrate': 100.0,
                'total': 4,
                'wins': 4,
                'type': 'ТМ 2.5',
                'confidence': 100.0
            },
            # Маркер 3: ОБЗ
            {
                'stake': 40.7253125,
                'winrate': 66.7,
                'total': 3,
                'wins': 2,
                'type': 'ОБЗ',
                'confidence': 66.7
            },
            # ===== МАРКЕР 4: X2 (с суммой 01) =====
            {
                'stake': 42.86875000000001,
                'winrate': 80.0,
                'total': 3,
                'wins': 2,
                'type': 'X2',
                'confidence': 66.7
            },
        ]

        markers.extend(manual_markers)

        # ============================================================
        # 3. УДАЛЯЕМ ДУБЛИКАТЫ
        # ============================================================
        unique_markers = {}
        for marker in markers:
            stake = marker['stake']
            if stake not in unique_markers:
                unique_markers[stake] = marker
            else:
                if marker['total'] > unique_markers[stake]['total']:
                    unique_markers[stake] = marker

        markers = list(unique_markers.values())
        markers.sort(key=lambda x: x['winrate'], reverse=True)

        logger.info(f"🎯 Найдено маркеров: {len(markers)}")
        for m in markers:
            logger.info(f"   📊 ${m['stake']} → {m['type']} ({m['winrate']}%, {m['total']} ставок)")

        return markers

    def _find_marker_for_bet(self, markers, bet):
        """Находит подходящий маркер для ставки"""
        if not markers:
            return None

        bet_label = bet.get('label', '')

        for marker in markers:
            marker_type = marker.get('type', '')
            if marker_type.lower() in bet_label.lower():
                return marker

        return markers[0] if markers else None


auto_bet = AutoBet()
