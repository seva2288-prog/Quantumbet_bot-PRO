"""LLM-анализ матчей через DeepSeek с батчингом и параллелизмом
★ v4.9: добавлены генерация объяснений + pick_best + Tool Calling с news/injuries/odds"""
import json
import threading
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET

from openai import OpenAI

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client = None
_semaphore = threading.Semaphore(4)

MAX_BATCH_SIZE = 6
MAX_PARALLEL_BATCHES = 3

# ============================================================
# КЭШ для новостей (чтобы не дёргать RSS каждый раз)
# ============================================================
_NEWS_CACHE = {}
_NEWS_CACHE_TTL = 1800   # 30 минут
_INJURIES_CACHE = {}
_INJURIES_CACHE_TTL = 3600   # 1 час


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
    """Батч-анализ матчей. Возвращает список результатов той же длины."""
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
# ★ v4.9: Генерация объяснения для ставки
# ============================================================
def llm_generate_reason(match_data: dict) -> str:
    """
    Генерирует 1-2 предложения — почему эта ставка выгодна.
    Возвращает строку или '' при ошибке.
    """
    if not Config.LLM_ENABLED or not match_data:
        return ''
    try:
        home = match_data.get('home', '?')
        away = match_data.get('away', '?')
        league = match_data.get('league', '?')
        best = match_data.get('best_bet', {})
        label = best.get('label', '?')
        odds = best.get('odds', 0)
        home_xg = match_data.get('home_xg', 0)
        away_xg = match_data.get('away_xg', 0)
        total_xg = match_data.get('total_xg', 0)
        home_form = match_data.get('home_form', '')
        away_form = match_data.get('away_form', '')
        standings = match_data.get('standings', {}) or {}
        hp = standings.get('home_position', '?')
        ap = standings.get('away_position', '?')
        hm = _motivation_text(standings.get('home_motivation', 'mid_table'))
        am = _motivation_text(standings.get('away_motivation', 'mid_table'))

        prompt = (
            f"Ты футбольный аналитик. Объясни ОДНИМ-ДВУМЯ предложениями "
            f"(макс 25 слов) ПОЧЕМУ эта ставка выгодна. Без воды, без цифр EV/Prob.\n\n"
            f"Матч: {home} vs {away}\n"
            f"Лига: {league}\n"
            f"Ставка: {label} @ {odds}\n"
            f"xG: {home} {home_xg} — {away} {away_xg} (сумма {total_xg})\n"
            f"Форма: {home} [{home_form}] vs {away} [{away_form}]\n"
            f"Позиции: {hp} ({hm}) vs {ap} ({am})\n\n"
            f"Отвечай ТОЛЬКО текстом объяснения на русском, без префиксов."
        )

        with _semaphore:
            client = _get_client()
            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {'role': 'system', 'content': 'Ты краткий футбольный аналитик. Отвечай 1-2 предложениями на русском.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.7,
                max_tokens=80,
            )
        text = response.choices[0].message.content.strip()

        for prefix in ['Объяснение:', 'Почему:', 'Причина:', '**']:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = text.replace('**', '').strip()
        return text[:200]
    except Exception as e:
        logger.error(f"llm_generate_reason: {e}")
        return ''


# ============================================================
# ★ v4.9: DeepSeek выбирает ОДИН лучший матч
# ============================================================
def llm_pick_best(matches: list) -> dict | None:
    """
    DeepSeek выбирает ОДИН самый уверенный матч из списка.
    Возвращает dict {'match': {...}, 'reason': '...'} или None.
    """
    if not Config.LLM_ENABLED or not matches:
        return None
    try:
        top = matches[:20]
        lines = []
        for i, m in enumerate(top, 1):
            best = m.get('best_bet', {})
            lines.append(
                f"{i}. {m.get('home', '?')} vs {m.get('away', '?')} | "
                f"{m.get('league', '?')} | "
                f"Ставка: {best.get('label', '?')} @ {best.get('odds', 0)} | "
                f"EV: {best.get('ev', 0)}% | Prob: {best.get('prob', 0)}% | "
                f"xG: {m.get('total_xg', 0):.2f} | "
                f"Форма: {m.get('home_form', '')} vs {m.get('away_form', '')}"
            )
        matches_text = '\n'.join(lines)

        prompt = (
            f"Ты профессиональный футбольный аналитик. Из списка матчей "
            f"выбери ОДИН, в котором ты больше всего уверен.\n\n"
            f"{matches_text}\n\n"
            f"Ответь строго в формате JSON:\n"
            f'{{"index": <номер_матча_1_до_N>, "reason": "<кратко 1 предложение почему именно он>"}}\n'
            f"Только JSON, без markdown-обёрток."
        )

        with _semaphore:
            client = _get_client()
            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {'role': 'system', 'content': 'Ты аналитик ставок. Отвечай только JSON.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.3,
                max_tokens=200,
                response_format={'type': 'json_object'},
            )
        content = response.choices[0].message.content.strip()
        content = content.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(content)

        idx = int(parsed.get('index', 0)) - 1
        reason = str(parsed.get('reason', '')).strip()[:200]

        if 0 <= idx < len(top):
            return {'match': top[idx], 'reason': reason}
        return None
    except Exception as e:
        logger.error(f"llm_pick_best: {e}")
        return None


# ============================================================
# ★ v4.9: NEWS через RSS (бесплатно, без API)
# ============================================================
def get_team_news(team_name: str, limit: int = 5) -> list:
    """
    Получает последние новости о команде через RSS BBC Sport.
    Кэш 30 минут.
    """
    key = team_name.lower().strip()
    now = time.time()

    if key in _NEWS_CACHE:
        cached, ts = _NEWS_CACHE[key]
        if now - ts < _NEWS_CACHE_TTL:
            return cached

    results = []
    try:
        # BBC Sport Football RSS
        rss_urls = [
            "https://feeds.bbci.co.uk/sport/football/rss.xml",
            "https://www.skysports.com/rss/12040",
        ]
        team_lower = team_name.lower()

        for url in rss_urls:
            try:
                resp = requests.get(url, timeout=8, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; QuantumBetBot/1.0)'
                })
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                for item in root.iter('item'):
                    title = item.findtext('title', '')
                    desc = item.findtext('description', '')
                    pub_date = item.findtext('pubDate', '')
                    link = item.findtext('link', '')

                    text = f"{title} {desc}".lower()
                    if team_lower in text:
                        results.append({
                            'title': title.strip()[:200],
                            'description': desc.strip()[:300],
                            'published': pub_date,
                            'link': link,
                        })
                        if len(results) >= limit:
                            break
                if len(results) >= limit:
                    break
            except Exception as e:
                logger.debug(f"RSS {url}: {e}")
                continue

        _NEWS_CACHE[key] = (results, now)
        logger.info(f"📰 News: {team_name} → {len(results)} новостей")
        return results
    except Exception as e:
        logger.error(f"get_team_news({team_name}): {e}")
        _NEWS_CACHE[key] = ([], now)
        return []


# ============================================================
# ★ v4.9: INJURIES через Football API (кэш)
# ============================================================
def get_team_injuries(team_id: int) -> list:
    """Кэш травм на 1 час."""
    if not team_id:
        return []
    key = f"inj_{team_id}"
    now = time.time()
    if key in _INJURIES_CACHE:
        cached, ts = _INJURIES_CACHE[key]
        if now - ts < _INJURIES_CACHE_TTL:
            return cached

    try:
        from main import football_api
        data = football_api.get_injuries(team_id)
        _INJURIES_CACHE[key] = (data or [], now)
        return data or []
    except Exception as e:
        logger.error(f"get_team_injuries({team_id}): {e}")
        return []


# ============================================================
# ★ v4.9: ODDs history из SQLite
# ============================================================
def get_odds_history(fixture_id: int, market: str = '1X2',
                      selection: str = '1', limit: int = 20) -> list:
    """Последние N снимков кэфа из SQLite."""
    if not fixture_id:
        return []
    try:
        from app.database.storage import storage
        rows = storage.get_odds_history(fixture_id, market, selection)
        if not rows:
            return []
        return rows[-limit:]
    except Exception as e:
        logger.error(f"get_odds_history({fixture_id}): {e}")
        return []


# ============================================================
# ★ v4.9: TOOL CALLING — единый вызов с функциями
# ============================================================
def llm_analyze_with_tools(match_data: dict) -> dict | None:
    """
    Анализ матча с использованием Tool Calling.
    DeepSeek сам решает, вызвать ли get_news/get_injuries/get_odds_history.
    """
    if not Config.LLM_ENABLED or not match_data:
        return None

    try:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_news",
                    "description": "Получить последние новости о команде (травмы, составы, трансферы)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_name": {"type": "string", "description": "Название команды"}
                        },
                        "required": ["team_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_injuries",
                    "description": "Получить список травмированных игроков команды",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_id": {"type": "integer", "description": "ID команды в Football API"}
                        },
                        "required": ["team_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_odds_history",
                    "description": "История движения кэфа (для определения тренда)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fixture_id": {"type": "integer"},
                            "market": {"type": "string", "description": "1X2, DC, O/U 2.5, BTTS"},
                            "selection": {"type": "string", "description": "1, X, 2, 1X, X2, BTTS, Over, Under"}
                        },
                        "required": ["fixture_id"]
                    }
                }
            }
        ]

        home = match_data.get('home', '?')
        away = match_data.get('away', '?')
        league = match_data.get('league', '?')
        fixture_id = match_data.get('fixture_id')
        hid = match_data.get('home_team_id') or match_data.get('hid')
        aid = match_data.get('away_team_id') or match_data.get('aid')

        system_msg = (
            "Ты — футбольный аналитик. Проанализируй матч и верни вероятности "
            "исходов в формате JSON. Если нужны свежие данные — вызывай доступные функции. "
            "Ответ строго JSON: {home_win, draw, away_win, btts, confidence, total_goals, "
            "over_2_5, most_likely_score: {home, away, prob}}"
        )

        user_msg = (
            f"Матч: {home} vs {away}\n"
            f"Лига: {league}\n"
            f"xG: {match_data.get('home_xg', 0)} — {match_data.get('away_xg', 0)}\n"
            f"Форма: {match_data.get('home_form', '')} vs {match_data.get('away_form', '')}\n"
            f"Fixture ID: {fixture_id}\n"
            f"Home team ID: {hid}\n"
            f"Away team ID: {aid}\n"
            f"Погода: {match_data.get('weather_reason', 'нет')}\n\n"
            f"Проанализируй матч. Если нужно — вызови функции для свежих данных."
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        # Цикл вызовов: до 3 раундов tool calling
        for round_num in range(3):
            with _semaphore:
                client = _get_client()
                response = client.chat.completions.create(
                    model=Config.LLM_MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=800,
                )

            msg = response.choices[0].message

            # Если модель запросила tool calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })

                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or '{}')
                    except Exception:
                        args = {}

                    tool_result = _execute_tool(tc.function.name, args)
                    logger.info(f"🔧 Tool call: {tc.function.name}({args}) → {len(str(tool_result))} символов")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result, ensure_ascii=False)[:4000]
                    })
                continue  # Ещё раунд

            # Финальный ответ
            text = msg.content.strip()
            parsed = _parse_single_response(text)
            if parsed:
                return parsed
            return None

        return None
    except Exception as e:
        logger.error(f"llm_analyze_with_tools: {e}")
        return None


def _execute_tool(name: str, args: dict):
    """Диспетчер tool calls."""
    try:
        if name == 'get_news':
            return get_team_news(args.get('team_name', ''), limit=5)
        elif name == 'get_injuries':
            return get_team_injuries(args.get('team_id'))
        elif name == 'get_odds_history':
            return get_odds_history(
                args.get('fixture_id'),
                args.get('market', '1X2'),
                args.get('selection', '1'),
                limit=20,
            )
        return {'error': f'unknown tool: {name}'}
    except Exception as e:
        return {'error': str(e)}


def _parse_single_response(text: str) -> dict | None:
    """Парсит одиночный JSON-ответ от LLM."""
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"❌ LLM не JSON: {text[:200]}")
        return None
    return _normalize(data)


# ============================================================
# ВНУТРЕННЕЕ (батч)
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
        'international': 'сборные',
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

# ============================================================
# ★ v4.9: Генерация объяснения для ставки
# ============================================================
def llm_generate_reason(match_data: dict) -> str:
    """
    Генерирует 1-2 предложения — почему эта ставка выгодна.
    Работает только с данными, которые уже есть в match_data.
    Возвращает строку или '' при ошибке.
    """
    if not Config.LLM_ENABLED or not match_data:
        return ''
    try:
        home = match_data.get('home', '?')
        away = match_data.get('away', '?')
        league = match_data.get('league', '?')
        best = match_data.get('best_bet', {})
        label = best.get('label', '?')
        odds = best.get('odds', 0)
        home_xg = match_data.get('home_xg', 0)
        away_xg = match_data.get('away_xg', 0)
        total_xg = match_data.get('total_xg', 0)
        home_form = match_data.get('home_form', '')
        away_form = match_data.get('away_form', '')
        standings = match_data.get('standings', {}) or {}
        hp = standings.get('home_position', '?')
        ap = standings.get('away_position', '?')
        hm = _motivation_text(standings.get('home_motivation', 'mid_table'))
        am = _motivation_text(standings.get('away_motivation', 'mid_table'))

        prompt = (
            f"Ты футбольный аналитик. Объясни ОДНИМ-ДВУМЯ предложениями "
            f"(макс 25 слов) ПОЧЕМУ эта ставка выгодна. Без воды, без цифр EV/Prob.\n\n"
            f"Матч: {home} vs {away}\n"
            f"Лига: {league}\n"
            f"Ставка: {label} @ {odds}\n"
            f"xG: {home} {home_xg} — {away} {away_xg} (сумма {total_xg})\n"
            f"Форма: {home} [{home_form}] vs {away} [{away_form}]\n"
            f"Позиции: {hp} ({hm}) vs {ap} ({am})\n\n"
            f"Отвечай ТОЛЬКО текстом объяснения на русском, без префиксов."
        )

        with _semaphore:
            client = _get_client()
            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {'role': 'system',
                     'content': 'Ты краткий футбольный аналитик. Отвечай 1-2 предложениями на русском.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.7,
                max_tokens=80,
            )
        text = response.choices[0].message.content.strip()

        # Чистим возможные префиксы
        for prefix in ['Объяснение:', 'Почему:', 'Причина:', '**']:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = text.replace('**', '').strip()
        return text[:200]
    except Exception as e:
        logger.error(f"llm_generate_reason: {e}")
        return ''


# ============================================================
# ★ v4.9: DeepSeek выбирает ОДИН лучший матч
# ============================================================
def llm_pick_best(matches: list) -> dict | None:
    """
    DeepSeek выбирает ОДИН самый уверенный матч из списка.
    Возвращает dict {'match': {...}, 'reason': '...'} или None.
    """
    if not Config.LLM_ENABLED or not matches:
        return None
    try:
        top = matches[:20]
        lines = []
        for i, m in enumerate(top, 1):
            best = m.get('best_bet', {})
            lines.append(
                f"{i}. {m.get('home', '?')} vs {m.get('away', '?')} | "
                f"{m.get('league', '?')} | "
                f"Ставка: {best.get('label', '?')} @ {best.get('odds', 0)} | "
                f"EV: {best.get('ev', 0)}% | Prob: {best.get('prob', 0)}% | "
                f"xG: {m.get('total_xg', 0):.2f} | "
                f"Форма: {m.get('home_form', '')} vs {m.get('away_form', '')}"
            )
        matches_text = '\n'.join(lines)

        prompt = (
            f"Ты профессиональный футбольный аналитик. Из списка матчей "
            f"выбери ОДИН, в котором ты больше всего уверен.\n\n"
            f"{matches_text}\n\n"
            f"Ответь строго в формате JSON:\n"
            f'{{"index": <номер_матча_1_до_N>, "reason": "<кратко 1 предложение почему именно он>"}}\n'
            f"Только JSON, без markdown-обёрток."
        )

        with _semaphore:
            client = _get_client()
            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {'role': 'system', 'content': 'Ты аналитик ставок. Отвечай только JSON.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.3,
                max_tokens=200,
                response_format={'type': 'json_object'},
            )
        content = response.choices[0].message.content.strip()
        content = content.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(content)

        idx = int(parsed.get('index', 0)) - 1
        reason = str(parsed.get('reason', '')).strip()[:200]

        if 0 <= idx < len(top):
            return {'match': top[idx], 'reason': reason}
        return None
    except Exception as e:
        logger.error(f"llm_pick_best: {e}")
        return None
