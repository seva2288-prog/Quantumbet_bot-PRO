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

# ============================================================
# ПРОГНОЗ ТОЧНОГО СЧЕТА (Улучшение 4)
# ============================================================

def predict_exact_score(home_xg: float, away_xg: float, max_goals: int = 4) -> dict:
    """
    Прогноз точного счета через распределение Пуассона
    Возвращает топ-5 наиболее вероятных счетов
    """
    from app.analytics.probability import poisson_probability
    
    # Вероятности для каждого количества голов
    home_probs = [poisson_probability(home_xg, i) for i in range(max_goals + 1)]
    away_probs = [poisson_probability(away_xg, i) for i in range(max_goals + 1)]
    
    # Нормализация (чтобы сумма была = 1)
    home_sum = sum(home_probs)
    away_sum = sum(away_probs)
    if home_sum > 0:
        home_probs = [p / home_sum for p in home_probs]
    if away_sum > 0:
        away_probs = [p / away_sum for p in away_probs]
    
    # Расчет вероятностей для всех счетов
    scores = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            prob = home_probs[i] * away_probs[j]
            scores[f"{i}-{j}"] = round(prob * 100, 1)
    
    # Сортируем по убыванию вероятности
    sorted_scores = dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))
    
    # Возвращаем топ-5
    return dict(list(sorted_scores.items())[:5])


def predict_corners(home_xg: float, away_xg: float) -> dict:
    """
    Прогноз угловых на основе xG
    """
    # Среднее количество угловых = (сумма xG) * 3.5
    avg_corners = (home_xg + away_xg) * 3.5
    
    return {
        "total": round(avg_corners, 1),
        "over_8_5": round(min(avg_corners / 10 * 100, 95), 1),
        "over_10_5": round(min(max(avg_corners / 12 * 100, 5), 90), 1),
    }


def predict_goalscorer(home_team: str, away_team: str, match_data: dict) -> list:
    """
    Прогноз бомбардира матча (заглушка)
    В реальном проекте нужна статистика игроков
    """
    # Заглушка - в реальности нужны данные о игроках
    return [
        {"name": "Топ бомбардир хозяев", "probability": 25.5},
        {"name": "Топ бомбардир гостей", "probability": 18.2},
        {"name": "Другой игрок", "probability": 12.8},
    ]

# ============================================================
# ПРОГНОЗ ПО ТАЙМАМ
# ============================================================

def predict_half_goals(home_xg: float, away_xg: float) -> dict:
    """
    Прогноз голов по таймам
    """
    first_half_factor = 0.45
    second_half_factor = 0.55
    
    home_first = home_xg * first_half_factor
    away_first = away_xg * first_half_factor
    home_second = home_xg * second_half_factor
    away_second = away_xg * second_half_factor
    
    import math
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


# ============================================================
# ПРОГНОЗ ТОЧНОГО СЧЕТА
# ============================================================

def predict_exact_score(home_xg: float, away_xg: float, max_goals: int = 4) -> dict:
    """
    Прогноз точного счета через распределение Пуассона
    """
    from app.analytics.probability import poisson_probability
    
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


# ============================================================
# ПРОГНОЗ УГЛОВЫХ
# ============================================================

def predict_corners(home_xg: float, away_xg: float) -> dict:
    """
    Прогноз угловых
    """
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
    """
    Прогноз желтых карточек на основе статистики команд и судьи
    """
    # Базовые значения
    home_avg = home_team_cards.get('yellow_cards_avg', 1.8)
    away_avg = away_team_cards.get('yellow_cards_avg', 1.8)
    
    # Корректировка на стиль команды
    if home_team_cards.get('trend') == 'aggressive':
        home_avg *= 1.25
    elif home_team_cards.get('trend') == 'disciplined':
        home_avg *= 0.75
    
    if away_team_cards.get('trend') == 'aggressive':
        away_avg *= 1.25
    elif away_team_cards.get('trend') == 'disciplined':
        away_avg *= 0.75
    
    # Корректировка на судью
    if referee_stats:
        if referee_stats.get('style') == 'strict':
            home_avg *= 1.15
            away_avg *= 1.15
        elif referee_stats.get('style') == 'lenient':
            home_avg *= 0.85
            away_avg *= 0.85
    
    total_avg = home_avg + away_avg
    
    # Расчет вероятностей для тоталов
    probs = {
        'total': round(total_avg, 1),
        'over_3_5': round(min(total_avg / 4 * 100, 95), 1),
        'over_4_5': round(min(max(total_avg / 5 * 100, 5), 90), 1),
        'over_5_5': round(min(max(total_avg / 6 * 100, 5), 85), 1),
        'home_avg': round(home_avg, 1),
        'away_avg': round(away_avg, 1),
    }
    
    return probs
