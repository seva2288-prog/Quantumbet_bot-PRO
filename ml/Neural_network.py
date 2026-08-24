import numpy as np
import json
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from datetime import datetime
from app.utils.logger import get_logger

logger = get_logger(__name__)

class NeuralNetworkPredictor:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.load_model()
    
    def load_model(self):
        """Загрузка обученной модели"""
        try:
            with open('data/nn_model.json', 'r') as f:
                data = json.load(f)
                self.is_trained = data.get('trained', False)
                logger.info("✅ Нейросеть загружена")
        except:
            logger.info("⚠️ Нейросеть не обучена, создаем новую")
            self.model = MLPRegressor(
                hidden_layer_sizes=(64, 32, 16),
                activation='relu',
                solver='adam',
                max_iter=1000,
                random_state=42
            )
            self.is_trained = False
    
    def save_model(self):
        """Сохранение модели"""
        try:
            data = {
                'trained': self.is_trained,
                'model_params': str(self.model.get_params()) if self.model else None,
                'updated': datetime.now().isoformat()
            }
            with open('data/nn_model.json', 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("✅ Модель сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения модели: {e}")
    
    def prepare_features(self, match_data):
        """Подготовка признаков для нейросети"""
        features = []
        
        # 1. Форма команд (0-1)
        features.append(match_data.get('home_form', {}).get('ratio', 0.5))
        features.append(match_data.get('away_form', {}).get('ratio', 0.5))
        
        # 2. Травмы (количество)
        features.append(min(len(match_data.get('home_injuries_list', [])), 5) / 5)
        features.append(min(len(match_data.get('away_injuries_list', [])), 5) / 5)
        
        # 3. Мотивация (1.0-1.12)
        features.append(match_data.get('home_motivation', 1.0) - 1.0)
        features.append(match_data.get('away_motivation', 1.0) - 1.0)
        
        # 4. Сезонные факторы
        # 5. Лига (кодируем числом)
        league = match_data.get('league', 'Unknown')
        league_hash = hash(league) % 100 / 100
        features.append(league_hash)
        
        # 6. Время матча
        features.append(0.5)  # заглушка
        
        return np.array(features).reshape(1, -1)
    
    def train(self, history_data):
        """Обучение нейросети на истории матчей"""
        if len(history_data) < 50:
            logger.warning(f"⚠️ Недостаточно данных для обучения (нужно 50+, есть {len(history_data)})")
            return False
        
        X = []
        y = []
        
        for match in history_data:
            features = self.prepare_features(match)
            X.append(features.flatten())
            y.append(match.get('home_goals', 0))
            y.append(match.get('away_goals', 0))
        
        X = np.array(X)
        y = np.array(y)
        
        if len(X) < 10:
            logger.warning("⚠️ Недостаточно данных для обучения")
            return False
        
        # Нормализация
        X_scaled = self.scaler.fit_transform(X)
        
        # Создаем и обучаем модель
        self.model = MLPRegressor(
            hidden_layer_sizes=(64, 32, 16),
            activation='relu',
            solver='adam',
            max_iter=1000,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.1
        )
        
        self.model.fit(X_scaled, y)
        self.is_trained = True
        self.save_model()
        
        logger.info(f"✅ Нейросеть обучена на {len(X)} матчах")
        return True
    
    def predict_xg(self, match_data):
        """Предсказание xG с помощью нейросети"""
        if not self.is_trained:
            logger.warning("⚠️ Нейросеть не обучена, используем ML")
            return None, None
        
        try:
            features = self.prepare_features(match_data)
            X_scaled = self.scaler.transform(features)
            
            # Предсказываем голы хозяев и гостей
            prediction = self.model.predict(X_scaled)
            home_xg = max(0.3, prediction[0])
            away_xg = max(0.3, prediction[1] if len(prediction) > 1 else prediction[0] * 0.8)
            
            return home_xg, away_xg
        except Exception as e:
            logger.error(f"Ошибка предсказания нейросети: {e}")
            return None, None

# Глобальный экземпляр
neural_net = NeuralNetworkPredictor()
