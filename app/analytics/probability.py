import math

def calculate_probabilities(home_xg, away_xg):
    """Расчёт вероятностей без numpy"""
    total = home_xg + away_xg
    if total == 0:
        total = 1
    
    # Простая формула для вероятностей
    home_win = max(0.1, min(0.8, (away_xg / total) * 0.7))
    away_win = max(0.1, min(0.8, (home_xg / total) * 0.7))
    draw = max(0.05, min(0.9, 1 - home_win - away_win))
    
    return {
        'home_win': home_win,
        'away_win': away_win,
        'draw': draw,
        'over_2_5': min(0.9, (home_xg + away_xg) / 3.5),
        'under_2_5': max(0.1, 1 - (home_xg + away_xg) / 3.5),
        'both_score': min(0.8, (home_xg * away_xg) / 3.0)
    }

def calculate_ev(prob, odds):
    """Расчёт ожидаемой ценности"""
    return round((prob * odds - 1) * 100, 1)

def get_bet_types(odds_data):
    """Получение типов ставок из данных"""
    bet_types = []
    
    if not odds_data or not isinstance(odds_data, dict):
        return bet_types
    
    # Пример парсинга коэффициентов
    if 'home' in odds_data:
        bet_types.append(('home_win', odds_data['home'], 'Победа хозяев'))
    if 'away' in odds_data:
        bet_types.append(('away_win', odds_data['away'], 'Победа гостей'))
    if 'draw' in odds_data:
        bet_types.append(('draw', odds_data['draw'], 'Ничья'))
    if 'over_2_5' in odds_data:
        bet_types.append(('over_2_5', odds_data['over_2_5'], 'ТБ 2.5'))
    if 'under_2_5' in odds_data:
        bet_types.append(('under_2_5', odds_data['under_2_5'], 'ТМ 2.5'))
    if 'both_score' in odds_data:
        bet_types.append(('both_score', odds_data['both_score'], 'ОЗ - Да'))
    
    return bet_types
