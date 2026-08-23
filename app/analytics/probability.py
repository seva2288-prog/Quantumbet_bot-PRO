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

def calculate_ev(prob: float, odds: float) -> float:
    return (prob * odds - 1) * 100

def get_bet_types() -> List:
    return [
        ('btts', 1.85, 'ОЗ - ДА'),
        ('over_2_5', 1.80, 'Тотал > 2.5'),
        ('home_win', 2.0, 'Победа хозяев'),
        ('away_win', 2.0, 'Победа гостей'),
        ('home_or_draw', 1.5, '1Х'),
        ('away_or_draw', 1.5, '2Х'),
    ]
