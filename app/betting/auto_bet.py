# app/betting/auto_bet.py
from datetime import datetime
from app.config import Config
from app.database.storage import storage
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AutoBet:
    def __init__(self):
        self.enabled = True
        self.max_bets_per_day = getattr(Config, 'MAX_BETS_PER_DAY', 30)
        self.max_bets_per_run = getattr(Config, 'MAX_BETS_PER_RUN', 30)
        self.min_ev = getattr(Config, 'MIN_EV', 1)
        self.min_odds = getattr(Config, 'MIN_ODDS', 1.0)
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

        bets = match_data.get('bets', [])
        if not bets:
            return None

        # ============================================================
        # ИЩЕМ СТАВКУ ТМ 2.5 ПО ФОРМУЛЕ
        # ============================================================
        target_bet = None
        
        for bet in bets:
            label = bet.get('label', '')
            if 'ТМ 2.5' in label or 'under' in label:
                target_bet = bet
                logger.info(f"🎯 Найдена ставка ТМ 2.5: {label} | EV={bet.get('ev')}% | Сумма={bet.get('stake')}")
                break
        
        if not target_bet:
            logger.info("⚠️ ТМ 2.5 не найдена в списке ставок")
            return None

        ev = target_bet.get('ev', 0)
        odds = target_bet.get('odds', 0)
        stake = target_bet.get('stake', 0)
        label = target_bet.get('label', '')

        # ============================================================
        # ПРОВЕРКА EV
        # ============================================================
        if ev < self.min_ev:
            logger.info(f"⏭️ Пропуск: EV={ev}% < {self.min_ev}%")
            return None

        if odds < self.min_odds:
            logger.info(f"⏭️ Пропуск: КЭФ={odds} < {self.min_odds}")
            return None

        # Проверяем банк
        bank = storage.load_bank()
        if stake > bank * 0.1:
            stake = round(bank * 0.05, 2)
            logger.info(f"⚠️ Сумма скорректирована до {stake}")

        match_time = match_data.get('match_time', '')
        if not match_time:
            match_time = datetime.now().strftime('%d.%m.%Y %H:%M')

        # ===== СОХРАНЯЕМ СТАВКУ =====
        bet_record = {
            'home': match_data.get('home', ''),
            'away': match_data.get('away', ''),
            'fixture_id': match_data.get('fixture_id'),
            'league': match_data.get('league', ''),
            'match_time': match_time,
            'bet': label,
            'odds': odds,
            'stake': stake,
            'ev': ev,
            'result': 'pending',
            'profit': 0,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'home_goals': None,
            'away_goals': None,
            'auto': True,
            'marker_stake': stake
        }

        history = storage.load_history()
        history.append(bet_record)
        storage.save_history(history)

        self.bets_today += 1
        logger.info(f"✅ АВТО-СТАВКА: {bet_record['bet']} | {bet_record['home']} vs {bet_record['away']}")

        return {
            'match': f"{bet_record['home']} vs {bet_record['away']}",
            'match_time': match_time,
            'bet': bet_record['bet'],
            'odds': bet_record['odds'],
            'stake': bet_record['stake'],
            'ev': bet_record['ev'],
            'marker_stake': stake,
            'marker_type': 'tm25',
            'fixture_id': match_data.get('fixture_id')
        }

    def _find_markers(self, history):
        """Находит маркеры (паттерны с высокой проходимостью)"""
        markers = []

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

        return markers

    def _find_marker_for_bet(self, markers, bet):
        if not markers:
            return None

        bet_label = bet.get('label', '')

        for marker in markers:
            marker_type = marker.get('type', '')
            if marker_type.lower() in bet_label.lower():
                return marker

        return markers[0] if markers else None


auto_bet = AutoBet()
