"""LLM-анализ матчей через DeepSeek с травмами, счётом и стратегиями"""
import json
from openai import OpenAI

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client = None


def _get_client():
    """Ленивая инициализация клиента DeepSeek."""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=Config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
            timeout=Config.REQUEST_TIMEOUT,
        )
    return _client


def llm_analyze_match(match_data: dict) -> dict | None:
    """Отправляет данные матча в DeepSeek и получает вероятности + счёт + потенциалы."""
    if not Config.LLM_ENABLED:
        return None
    if not match_data:
        return None

    prompt = _build_prompt(match_data)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[
                {"role": "system", "content": "Ты — аналитик футбольных ставок. Отвечай строго JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ DeepSeek ошибка: {e}")
        return None

    return _parse_json_response(text)


def _format_injuries(injuries: list) -> str:
    """Форматирует список травмированных для промпта."""
    if not injuries:
        return "нет"
    lines = []
    for inj in injuries[:10]:
        player = inj.get('player', {})
        name = player.get('name', 'Unknown')
        position = player.get('position', '?')
        reason = inj.get('reason', '?')
        lines.append(f"  - {name} ({position}) — {reason}")
    return "\n" + "\n".join(lines)


def _build_prompt(m: dict) -> str:
    """Собирает промпт — травмы, счёт, ничья, андердог."""
    home_injuries = m.get('home_injuries', [])
    away_injuries = m.get('away_injuries', [])

    return f"""Оцени вероятности исходов футбольного матча + дай прогноз счёта и оценку ничьей/андердога.

Матч: {m.get('home')} vs {m.get('away')}
Лига: {m.get('league')}
xG хозяев: {m.get('home_xg')}, xG гостей: {m.get('away_xg')}, сумма: {m.get('total_xg')}
Форма хозяев: {m.get('home_form')}
Форма гостей: {m.get('away_form')}
Позиции: #{m.get('standings', {}).get('home_position')} vs #{m.get('standings', {}).get('away_position')}
Погода: {m.get('weather_reason', 'нет данных')}

Травмированные у хозяев: {_format_injuries(home_injuries)}
Травмированные у гостей: {_format_injuries(away_injuries)}

ВАЖНО:
- Если у команды травмирован ключевой игрок (вратарь, основной защитник, топ-бомбардир) — понижай её вероятность
- Если у команды 3+ травмы в основе — понижай на 5-10%

Верни СТРОГО JSON:
{{
  "home_win": 0.55,
  "draw": 0.25,
  "away_win": 0.20,
  "btts": 0.50,
  "confidence": 0.75,
  "most_likely_score": {{"home": 2, "away": 1, "prob": 0.15}},
  "total_goals": 2.8,
  "over_2_5": 0.55,
  "draw_potential": 0.65,
  "underdog_potential": 0.40
}}

Правила:
- Сумма home_win + draw + away_win = 1.0
- most_likely_score — самый вероятный счёт (целые числа, prob — вероятность 0-1)
- total_goals — ожидаемое количество голов (например, 2.8)
- over_2_5 — вероятность что голов будет больше 2.5 (0-1)
- draw_potential (0-1) — насколько вероятна НИЧЬЯ (обе команды равны, xG низкий, плохая погода, отсутствие мотивации)
- underdog_potential (0-1) — насколько вероятен АПСЕТ (фаворит устал, андердог в форме, мотивация выжить)
- Все значения от 0 до 1

Где:
- draw_potential высокий (>0.6), если: обе команды равны, xG низкий (<2.2), погода плохая, обе в середине таблицы
- underdog_potential высокий (>0.6), если: фаворит устал (3+ матча за неделю), андердог в форме (WWDLW), фаворит потерял ключевого игрока"""


def _parse_json_response(text: str) -> dict | None:
    """Чистит markdown-обёртку и парсит JSON."""
    text = text.strip()
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

    score = data.get('most_likely_score', {})
    most_likely_score = None
    if isinstance(score, dict):
        try:
            home_goals = int(score.get('home', 0))
            away_goals = int(score.get('away', 0))
            score_prob = float(score.get('prob', 0))
            if 0 <= home_goals <= 10 and 0 <= away_goals <= 10:
                most_likely_score = {
                    'home': home_goals,
                    'away': away_goals,
                    'prob': score_prob,
                    'label': f"{home_goals}:{away_goals}"
                }
        except (TypeError, ValueError):
            pass

    return {
        'home_win': hw,
        'draw': dr,
        'away_win': aw,
        '1X': hw + dr,
        'X2': aw + dr,
        'btts': float(data.get('btts', 0.5)),
        'confidence': float(data.get('confidence', 0.6)),
        'most_likely_score': most_likely_score,
        'total_goals': float(data.get('total_goals', 2.5)),
        'over_2_5': float(data.get('over_2_5', 0.5)),
        'draw_potential': float(data.get('draw_potential', 0.5)),
        'underdog_potential': float(data.get('underdog_potential', 0.4)),
    }
