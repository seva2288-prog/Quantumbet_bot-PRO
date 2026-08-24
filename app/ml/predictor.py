import json
import numpy as np
from datetime import datetime
from app.utils.logger import get_logger

logger = get_logger(__name__)

class MLPredictor:
    def __init__(self):
        self.weights = self.load_weights()
        self.history = self.load_history()
    
    def load_weights(self):
        try:
            with open('data/ml_weights.json', 'r') as f:
                return json.load(f)
        except:
            return {
                'home_advantage': 0.08,
                'form_weight': 0.30,
                'injury_weight': 0.10,
                'motivation_weight': 0.15,
                'h2h_weight': 0.10,
                'weather_weight': 0.05,
                'time_weight': 0.05,
                'league_factor': 0.12,
                'gk_factor': 0.05,
            }
    
    def load_history(self):
        try:
            with open('data/ml_history.json', 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_weights(self):
        with open('data/ml_weights.json', 'w') as f:
            json.dump(self.weights, f, indent=2)
    
    def save_history(self):
        with open('data/ml_history.json', 'w') as f:
            json.dump(self.history[-1000:], f, indent=2)
    
    def predict_xg(self, match_data):
        home_xg = 1.5
        away_xg = 1.3
        
        home_xg *= (1 + self.weights['home_advantage'])
        away_xg *= (1 - self.weights['home_advantage'] * 0.5)
        
        home_form = match_data.get('home_form', {}).get('ratio', 0.5)
        away_form = match_data.get('away_form', {}).get('ratio', 0.5)
        
        home_xg *= (1 + self.weights['form_weight'] * (home_form - 0.5))
        away_xg *= (1 + self.weights['form_weight'] * (away_form - 0.5))
        
        home_injuries = len(match_data.get('home_injuries_list', []))
        away_injuries = len(match_data.get('away_injuries_list', []))
        
        home_xg *= (1 - self.weights['injury_weight'] * home_injuries / 5)
        away_xg *= (1 - self.weights['injury_weight'] * away_injuries / 5)
        
        home_motivation = match_data.get('home_motivation', 1.0)
        away_motivation = match_data.get('away_motivation', 1.0)
        
        home_xg *= (1 + self.weights['motivation_weight'] * (home_motivation - 1))
        away_xg *= (1 + self.weights['motivation_weight'] * (away_motivation - 1))
        
        return home_xg, away_xg
    
    def train(self, match_data, actual_score):
        home_xg, away_xg = self.predict_xg(match_data)
        home_goals, away_goals = map(int, actual_score.split('-'))
        
        home_error = home_xg - home_goals
        away_error = away_xg - away_goals
        
        learning_rate = 0.01
        
        self.weights['form_weight'] -= learning_rate * home_error * 0.1
        self.weights['home_advantage'] -= learning_rate * home_error * 0.05
        self.weights['injury_weight'] -= learning_rate * abs(home_error) * 0.05
        
        for key in self.weights:
            self.weights[key] = max(0.01, min(self.weights[key], 0.5))
        
        self.history.append({
            'home_xg': home_xg,
            'away_xg': away_xg,
            'home_goals': home_goals,
            'away_goals': away_goals,
            'home_error': home_error,
            'away_error': away_error,
            'weights': dict(self.weights),
            'date': datetime.now().isoformat()
        })
        
        self.save_weights()
        self.save_history()
        
        logger.info(f"🧠 Обучение: ошибка xG = {abs(home_error):.2f}/{abs(away_error):.2f}")
        
        return {
            'home_error': home_error,
            'away_error': away_error,
            'home_xg': home_xg,
            'away_xg': away_xg
        }
    
    def get_stats(self):
        if not self.history:
            return "📭 Нет данных для обучения"
        
        total = len(self.history)
        avg_home_error = sum(abs(h['home_error']) for h in self.history) / total
        avg_away_error = sum(abs(h['away_error']) for h in self.history) / total
        
        return {
            'total_matches': total,
            'avg_home_error': round(avg_home_error, 2),
            'avg_away_error': round(avg_away_error, 2),
            'last_10_accuracy': self._get_recent_accuracy()
        }
    
    def _get_recent_accuracy(self):
        if len(self.history) < 10:
            return 0
        
        recent = self.history[-10:]
        correct = 0
        
        for match in recent:
            home_xg = match.get('home_xg', 0)
            home_goals = match.get('home_goals', 0)
            if abs(home_xg - home_goals) < 0.5:
                correct += 1
        
        return round(correct / 10 * 100, 1)

ml_predictor = MLPredictor()
