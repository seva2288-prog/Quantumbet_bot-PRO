def calculate_xg(match, fixture_id):
    """Расчёт xG без numpy"""
    # Временно используем простую логику
    home_xg = 1.2
    away_xg = 1.0
    reasons = ["fallback"]
    
    # Пример: если есть статистика, используем её
    if isinstance(match, dict):
        stats = match.get('statistics', {})
        if isinstance(stats, dict):
            home_shots = stats.get('shots_home', 0)
            away_shots = stats.get('shots_away', 0)
            
            if home_shots and away_shots:
                home_xg = max(0.5, min(3.0, home_shots * 0.1))
                away_xg = max(0.5, min(3.0, away_shots * 0.1))
                reasons = ["statistics"]
    
    return home_xg, away_xg, reasons
