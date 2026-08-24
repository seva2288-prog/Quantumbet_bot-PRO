import math
import numpy as np
from typing import Dict, List

def poisson_probability(xg: float, goals: int) -> float:
    if goals < 0 or xg <= 0:
        return 0.0
    try:
        return (math.exp(-xg) * (xg ** goals)) / math.factorial(goals)
    except OverflowError:
        return 0.0

def calculate_probabilities(home_xg: float, away_xg: float, max_goals: int = 6) -> Dict:
    home_probs = [poisson_probability(home_xg, i) for i in range(max_goals + 1)]
    away_probs = [poisson_probability(away_xg, i) for i in range(max_goals + 1)]
    
    home_sum = sum(home_probs)
    away_sum = sum(away_probs)
    if home_sum > 0:
        home_probs = [p / home_sum for p in home_probs]
    if away_sum > 0:
        away_probs = [p / away_sum for p in away_probs]
    
    prob_matrix = np.outer(home_probs, away_probs)
    
    home_win = float(np.sum(np.tril(prob_matrix, -1)))
    draw = float(np.sum(np.diag(prob_matrix)))
    away_win = float(np.sum(np.triu(prob_matrix, 1)))
    
    btts = 1 - (home_probs[0] * away_probs[0])
    
    over_2_5 = 0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            if i + j > 2.5:
                over_2_5 += prob_matrix[i][j]
    
    return {
        'home_win': home_win,
        'draw': draw,
        'away_win': away_win,
        'home_or_draw': home_win + draw,
        'away_or_draw': away_win + draw,
        'btts': btts,
        'over_2_5': over_2_5,
    }

def predict_half_goals(home_xg: float, away_xg: float) -> Dict:
    first_half_factor = 0.45
    second_half_factor = 0.55
    
    home_first = home_xg * first_half_factor
    away_first = away_xg * first_half_factor
    home_second = home_xg * second_half_factor
    away_second = away_xg * second_half_factor
    
    prob_first = 1 - (math.exp(-home_first) * math.exp(-away_first))
    prob_second = 1 - (math.exp(-home_second) * math.exp(-away_second))
    
    return {
        'first_half': {
            'home_xg': round(home_first, 2),
            'away_xg': round(away_first, 2),
            'goal_probability': round(prob_first * 100, 1)
        },
        'second_half': {
            'home_xg': round(home_second, 2),
            'away_xg': round(away_second, 2),
            'goal_probability': round(prob_second * 100, 1)
        }
    }

def predict_exact_score(home_xg: float, away_xg: float, max_goals: int = 4) -> dict:
    home_probs = [poisson_probability(home_xg, i) for i in range(max_goals + 1)]
    away_probs = [poisson_probability(away_xg, i) for i in range(max_goals + 1)]
    
    home_sum = sum(home_probs)
    away_sum = sum(away_probs)
    if home_sum > 0:
        home_probs = [p / home_sum for p in home_probs]
    if away_sum > 0:
        away_probs = [p / away_sum for p in away_probs]
    
    scores = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            prob = home_probs[i] * away_probs[j]
            scores[f"{i}-{j}"] = round(prob * 100, 1)
    
    sorted_scores = dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))
    return dict(list(sorted_scores.items())[:5])

def predict_corners(home_xg: float, away_xg: float) -> dict:
    avg_corners = (home_xg + away_xg) * 3.5
    return {
        "total": round(avg_corners, 1),
        "over_8_5": round(min(avg_corners / 10 * 100, 95), 1),
        "over_10_5": round(min(max(avg_corners / 12 * 100, 5), 90), 1),
    }

# ============================================================
# ПРОГНОЗ ЖЕЛТЫХ КАРТОЧЕК
# ============================================================

def predict_yellow_cards(home_team_cards: Dict, away_team_cards: Dict, referee_stats: Dict = None) -> Dict:
    home_avg = home_team_cards.get('yellow_cards_avg', 1.8)
    away_avg = away_team_cards.get('yellow_cards_avg', 1.8)
    
    if home_team_cards.get('trend') == 'aggressive':
        home_avg *= 1.25
    elif home_team_cards.get('trend') == 'disciplined':
        home_avg *= 0.75
    
    if away_team_cards.get('trend') == 'aggressive':
        away_avg *= 1.25
    elif away_team_cards.get('trend') == 'disciplined':
        away_avg *= 0.75
    
    if referee_stats:
        if referee_stats.get('style') == 'strict':
            home_avg *= 1.15
            away_avg *= 1.15
        elif referee_stats.get('style') == 'lenient':
            home_avg *= 0.85
            away_avg *= 0.85
    
    total_avg = home_avg + away_avg
    
    return {
        'total': round(total_avg, 1),
        'over_3_5': round(min(total_avg / 4 * 100, 95), 1),
        'over_4_5': round(min(max(total_avg / 5 * 100, 5), 90), 1),
        'over_5_5': round(min(max(total_avg / 6 * 100, 5), 85), 1),
        'home_avg': round(home_avg, 1),
        'away_avg': round(away_avg, 1),
    }


# ============================================================
# ТИПЫ СТАВОК С РЕАЛЬНЫМИ КОЭФАМИ
# ============================================================

def get_bet_types(odds_data=None):
    """
    Типы ставок с реальными коэфами из API
    Если коэфы не получены — используем средние
    """
    if odds_data:
        return [
            ('btts', odds_data.get('btts', 1.85), 'ОЗ - ДА'),
            ('over_2_5', odds_data.get('over_2_5', 1.80), 'Тотал > 2.5'),
            ('home_win', odds_data.get('home_win', 2.0), 'Победа хозяев'),
            ('away_win', odds_data.get('away_win', 2.0), 'Победа гостей'),
            ('home_or_draw', odds_data.get('home_win', 2.0) * 0.75, '1Х'),
            ('away_or_draw', odds_data.get('away_win', 2.0) * 0.75, '2Х'),
        ]
    else:
        return [
            ('btts', 1.85, 'ОЗ - ДА'),
            ('over_2_5', 1.80, 'Тотал > 2.5'),
            ('home_win', 2.0, 'Победа хозяев'),
            ('away_win', 2.0, 'Победа гостей'),
            ('home_or_draw', 1.5, '1Х'),
            ('away_or_draw', 1.5, '2Х'),
        ]

def calculate_ev(prob: float, odds: float) -> float:
    return (prob * odds - 1) * 100
