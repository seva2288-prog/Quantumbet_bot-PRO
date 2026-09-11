"""LLM-анализ матчей для PREDICTION_ENGINE='llm'"""
import json
import requests

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def llm_analyze_match(match_data: dict) -> dict | None:
    """
    Отправляет данные матча в LLM и получает скорректированные вероятности.

    Возвращает dict вида:
        {'home_win': 0.55, 'draw': 0.25, 'away_win': 0.20,
         '1X': 0.80, 'X2': 0.45, 'btts': 0.50, 'confidence': 0.75}
    или None, если LLM отключён / ошибка.
    """
    if not Config.LLM_ENABLED:
        return None
    if not match_data:
        return None

    prompt = _build_prompt(match_data)

    try:
        if Config.LLM_PROVIDER == "gemini":
            return _call_gemini(prompt)
        elif Config.LLM_PROVIDER == "openai":
            return _call_openai(prompt)
        else:
            logger.error(f"❌ Неизвестный LLM_PROVIDER: {Config.LLM_PROVIDER}")
            return None
    except Exception as e:
        logger.error(f"❌ LLM ошибка: {e}")
        return None


def _build_prompt(m: dict) -> str:
    """Собирает промпт для модели."""
    return f"""Ты — аналитик футбольных ставок. Оцени вероятности исходов матча.

Матч: {m.get('home')} vs {m.get('away')}
Лига: {m.get('league')}
xG хозяев: {m.get('home_xg')}, xG гостей: {m.get('away_xg')}, сумма: {m.get('total_xg')}
Форма хозяев: {m.get('home_form')}
Форма гостей: {m.get('away_form')}
Позиции: #{m.get('standings', {}).get('home_position')} vs #{m.get('standings', {}).get('away_position')}
Погода: {m.get('weather_reason', 'нет данных')}

Верни СТРОГО JSON без пояснений и без markdown:
{{
  "home_win": 0.55,
  "draw": 0.25,
  "away_win": 0.20,
  "btts": 0.50,
  "confidence": 0.75
}}

Правила:
- Сумма home_win + draw + away_win = 1.0
- Все значения от 0 до 1
- confidence — твоя уверенность в прогнозе от 0 до 1"""


def _call_gemini(prompt: str) -> dict | None:
    """Запрос к Google Gemini."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{Config.LLM_MODEL}:generateContent?key={Config.LLM_API_KEY}"
    )
    r = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 300
            }
        },
        timeout=Config.REQUEST_TIMEOUT
    )
    if r.status_code != 200:
        logger.error(f"❌ Gemini {r.status_code}: {r.text[:200]}")
        return None

    try:
        text = r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except (KeyError, IndexError) as e:
        logger.error(f"❌ Gemini неожиданный ответ: {e}")
        return None

    return _parse_json_response(text)


def _call_openai(prompt: str) -> dict | None:
    """Запрос к OpenAI."""
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.LLM_API_KEY}"},
        json={
            "model": Config.LLM_MODEL or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        },
        timeout=Config.REQUEST_TIMEOUT
    )
    if r.status_code != 200:
        logger.error(f"❌ OpenAI {r.status_code}: {r.text[:200]}")
        return None

    try:
        text = r.json()['choices'][0]['message']['content']
    except (KeyError, IndexError) as e:
        logger.error(f"❌ OpenAI неожиданный ответ: {e}")
        return None

    return _parse_json_response(text)


def _parse_json_response(text: str) -> dict | None:
    """Чистит markdown-обёртку и парсит JSON."""
    text = text.strip()
    # Убираем ```json ... ``` если модель добавила
    if text.startswith('```'):
        text = text.split('\n', 1)[-1]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"❌ LLM вернул не JSON: {e} | текст: {text[:200]}")
        return None

    return _normalize(data)


def _normalize(data: dict) -> dict | None:
    """Приводит ответ LLM к формату ensemble_probability()."""
    try:
        hw = float(data.get('home_win', 0))
        dr = float(data.get('draw', 0))
        aw = float(data.get('away_win', 0))
    except (TypeError, ValueError):
        logger.error(f"❌ LLM: некорректные типы в ответе {data}")
        return None

    total = hw + dr + aw
    if total <= 0:
        logger.error(f"❌ LLM: сумма вероятностей = {total}")
        return None

    hw /= total
    dr /= total
    aw /= total

    return {
        'home_win': hw,
        'draw': dr,
        'away_win': aw,
        '1X': hw + dr,
        'X2': aw + dr,
        'btts': float(data.get('btts', 0.5)),
        'confidence': float(data.get('confidence', 0.6)),
    }
