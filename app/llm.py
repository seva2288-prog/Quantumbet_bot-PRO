"""LLM-анализ матчей через DeepSeek с батчингом и параллелизмом"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client = None
_semaphore = threading.Semaphore(4)   # глобальный лимит на одновременные запросы

MAX_BATCH_SIZE = 6          # матчей в одном запросе к LLM
MAX_PARALLEL_BATCHES = 3    # одновременных запросов к LLM


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


# ============================================================
# ПУБЛИЧНОЕ API
# ============================================================
def llm_analyze_match(match_data: dict) -> dict | None:
    """Одиночный анализ (обратная совместимость со старым main.py)."""
    if not Config.LLM_ENABLED or not match_data:
        return None
    results = llm_analyze_batch([match_data])
    return results[0] if results else None


def llm_analyze_batch(matches: list) -> list:
    """
    Батч-анализ матчей. Возвращает список результатов той же длины.
    Не прошедшие матчи → None.
    """
    if not Config.LLM_ENABLED or not matches:
        return [None] * len(matches)

    indexed = list(enumerate(matches))
    batches = [
        indexed[i:i + MAX_BATCH_SIZE]
        for i in range(0, len(indexed), MAX_BATCH_SIZE)
    ]

    results = [None] * len(matches)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_BATCHES) as ex:
        futures = {ex.submit(_analyze_one_batch, batch): batch for batch in batches}
        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                batch_results = fut.result()
                for (orig_idx, _), res in zip(batch, batch_results):
                    results[orig_idx] = res
            except Exception as e:
                logger.error(f"❌ Батч LLM упал: {e}")

    return results


# ============================================================
# ВНУТРЕННЕЕ
# ============================================================
def _analyze_one_batch(batch: list) -> list:
    """batch: [(original_index, match_data), ...]"""
    prompt = _build_batch_prompt([m for _, m in batch])
    try:
        with _semaphore:
            client = _get_client()
            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — аналитик футбольных ставок. "
                            "Отвечай строго JSON-объектом с ключом 'matches' — массивом "
                            "результатов в том же порядке, что и входные матчи."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=400 * len(batch) + 200,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ DeepSeek ошибка: {e}")
        return [None] * len(batch)

    parsed = _parse_batch_response(text, len(batch))
    if parsed is None:
        return [None] * len(batch)
    return parsed


def _build_batch_prompt(matches: list) -> str:
    parts = [
        f"Проанализируй {len(matches)} футбольных матчей. "
        f"Верни JSON вида {{\"matches\": [{{...}}, {{...}}, ...]}} — "
        f"массив объектов в ТОМ ЖЕ ПОРЯДКЕ, что и матчи ниже.\n"
    ]
    for i, m in enumerate(matches, 1):
        parts.append(_format_single_match(i, m))
    parts.append(_json_schema_hint())
    return "\n".join(parts)


def _format_single_match(idx: int, m: dict) -> str:
    standings = m.get('standings', {})
    return f"""
=== МАТЧ #{idx} ===
{m.get('home')} vs {m.get('away')} | Лига: {m.get('league')}
xG хозяев: {m.get('home_xg')}, гостей: {m.get('away_xg')}, сумма: {m.get('total_xg')}
Форма хозяев: {m.get('home_form')}
Форма гостей: {m.get('away_form')}
Хозяева: #{standings.get('home_position', 99)} место, "
f"{standings.get('home_points', 0)} очков, МД {standings.get('home_goals_diff', 0):+d}, "
f"мотивация: {_motivation_text(standings.get('home_motivation', 'mid_table'))}"
Гости: #{standings.get('away_position', 99)} место, "
f"{standings.get('away_points', 0)} очков, МД {standings.get('away_goals_diff', 0):+d}, "
f"мотивация: {_motivation_text(standings.get('away_motivation', 'mid_table'))}"
Погода: {m.get('weather_reason', 'нет')}
Травмы хозяев: {_format_injuries(m.get('home_injuries', []))}
Травмы гостей: {_format_injuries(m.get('away_injuries', []))}
"""


def _json_schema_hint() -> str:
    return """
Для КАЖДОГО матча верни объект:
{
  "home_win": 0.55,
  "draw": 0.25,
  "away_win": 0.20,
  "btts": 0.50,
  "confidence": 0.75,
  "most_likely_score": {"home": 2, "away": 1, "prob": 0.15},
  "total_goals": 2.8,
  "over_2_5": 0.55,
  "draw_potential": 0.65,
  "underdog_potential": 0.40
}

Правила:
- home_win + draw + away_win = 1.0
- draw_potential высокий (>0.6), если обе в середине таблицы + низкий xG + плохая погода
- underdog_potential высокий (>0.6), если фаворит устал / потерял ключевого игрока, а андердог в форме и борется за выживание
- Все значения от 0 до 1

Верни ТОЛЬКО JSON: {"matches": [ {...}, {...}, ... ]}"""


def _parse_batch_response(text: str, expected: int):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"❌ LLM вернул не JSON: {e} | {text[:200]}")
        return None

    if isinstance(data, dict) and 'matches' in data:
        arr = data['matches']
    elif isinstance(data, list):
        arr = data
    else:
        logger.error(f"❌ LLM: неожиданная структура {type(data)}")
        return None

    if not isinstance(arr, list):
        return None

    result = [None] * expected
    for i in range(min(len(arr), expected)):
        result[i] = _normalize(arr[i])

    if len(arr) != expected:
        logger.warning(f"⚠️ LLM вернул {len(arr)} из {expected} матчей")

    return result


# ============================================================
# ФОРМАТТЕРЫ / НОРМАЛИЗАЦИЯ
# ============================================================
def _format_injuries(injuries: list) -> str:
    if not injuries:
        return "нет"
    lines = []
    for inj in injuries[:6]:
        player = inj.get('player', {})
        lines.append(
            f"{player.get('name', '?')} ({player.get('position', '?')}) — {inj.get('reason', '?')}"
        )
    return "; ".join(lines)


def _motivation_text(motivation: str) -> str:
    mapping = {
        'title_race': 'борьба за титул',
        'champions_league': 'борьба за ЛЧ',
        'europa_league': 'борьба за ЛЕ',
        'mid_table': 'середина таблицы',
        'relegation_playoff': 'борьба за выживание',
        'relegation': 'зона вылета',
    }
    return mapping.get(motivation, 'обычная')


def _normalize(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    try:
        hw = float(data.get('home_win', 0))
        dr = float(data.get('draw', 0))
        aw = float(data.get('away_win', 0))
    except (TypeError, ValueError):
        return None

    total = hw + dr + aw
    if total <= 0:
        return None

    hw, dr, aw = hw / total, dr / total, aw / total

    score = data.get('most_likely_score', {})
    most_likely_score = None
    if isinstance(score, dict):
        try:
            h_goals = int(score.get('home', 0))
            a_goals = int(score.get('away', 0))
            if 0 <= h_goals <= 10 and 0 <= a_goals <= 10:
                most_likely_score = {
                    'home': h_goals,
                    'away': a_goals,
                    'prob': float(score.get('prob', 0)),
                    'label': f"{h_goals}:{a_goals}"
                }
        except (TypeError, ValueError):
            pass

    def _f(k, default):
        try:
            return float(data.get(k, default))
        except (TypeError, ValueError):
            return default

    return {
        'home_win': hw,
        'draw': dr,
        'away_win': aw,
        '1X': hw + dr,
        'X2': aw + dr,
        'btts': _f('btts', 0.5),
        'confidence': _f('confidence', 0.6),
        'most_likely_score': most_likely_score,
        'total_goals': _f('total_goals', 2.5),
        'over_2_5': _f('over_2_5', 0.5),
        'draw_potential': _f('draw_potential', 0.5),
        'underdog_potential': _f('underdog_potential', 0.4),
    }
