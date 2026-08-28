import sys
import os
import time
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify

from app.config import Config
from app.database.storage import storage
from app.api.football import football_api
from app.api.weather import weather_api
from app.analytics.xg import xg_analyzer
from app.analytics.probability import calculate_probabilities, calculate_ev, get_bet_types
from app.analytics.arbitrage import arbitrage_analyzer
from app.analytics.anomalies import anomaly_detector
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler


logger = get_logger(__name__)
app = Flask(__name__)

search_running = False
TIMEZONE_OFFSET = 3

# ============================================================
# AUTOBET
# ============================================================

auto_bet = None


def get_auto_bet():
    global auto_bet

    if auto_bet is None:
        try:
            from app.betting.auto_bet import AutoBet

            auto_bet = AutoBet()

            logger.info("✅ AutoBet загружен")

        except Exception as e:
            logger.error(f"❌ Не удалось загрузить AutoBet: {e}")
            send_error_to_telegram(
                f"Не удалось загрузить AutoBet: {e}"
            )

            auto_bet = None

    return auto_bet


# ============================================================
# БЕЗОПАСНОЕ ПРЕОБРАЗОВАНИЕ В FLOAT
# ============================================================

def safe_float(value, default=0.0):
    """
    Безопасно преобразует значение в float.

    Исправляет ошибку:
    can't multiply sequence by non-int of type 'float'
    """

    try:
        if value is None:
            return default

        if value == "":
            return default

        if isinstance(value, str):
            value = value.replace(",", ".").strip()

        return float(value)

    except (TypeError, ValueError):
        return default


# ============================================================
# TELEGRAM ERROR
# ============================================================

def send_error_to_telegram(error_text: str):

    try:
        import requests

        url = (
            f"https://api.telegram.org/"
            f"bot{Config.TELEGRAM_TOKEN}/sendMessage"
        )

        error_text = str(error_text)

        if len(error_text) > 4000:
            error_text = error_text[:4000] + "...(обрезано)"

        data = {
            "chat_id": Config.ADMIN_CHAT_ID,
            "text": f"❌ <b>ОШИБКА БОТА</b>\n\n{error_text}",
            "parse_mode": "HTML"
        }

        requests.post(
            url,
            json=data,
            timeout=5
        )

    except Exception as e:

        logger.error(
            f"Не удалось отправить ошибку в Telegram: {e}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(
    text: str,
    parse_mode: str = "HTML"
):

    import requests

    url = (
        f"https://api.telegram.org/"
        f"bot{Config.TELEGRAM_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": Config.ADMIN_CHAT_ID,
        "text": str(text),
        "parse_mode": parse_mode
    }

    try:

        response = requests.post(
            url,
            json=data,
            timeout=10
        )

        if response.status_code != 200:

            logger.error(
                f"❌ Ошибка отправки: {response.text}"
            )

    except Exception as e:

        logger.error(
            f"❌ Send error: {e}"
        )


# ============================================================
# ЭКСПОРТ В EXCEL
# ============================================================

def export_to_excel():

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    import io

    history = storage.load_history()

    if not history:

        return (
            None,
            "📭 Нет данных для экспорта"
        )

    wb = Workbook()

    ws = wb.active
    ws.title = "Ставки"

    headers = [
        "Дата",
        "Матч",
        "Счёт",
        "Ставка",
        "Коэф",
        "EV%",
        "Сумма",
        "Результат",
        "Прибыль"
    ]

    ws.append(headers)

    header_font = Font(
        bold=True,
        color="FFFFFF"
    )

    header_fill = PatternFill(
        start_color="4472C4",
        end_color="4472C4",
        fill_type="solid"
    )

    for col in range(
        1,
        len(headers) + 1
    ):

        cell = ws.cell(
            row=1,
            column=col
        )

        cell.font = header_font
        cell.fill = header_fill

        cell.alignment = Alignment(
            horizontal="center"
        )

    total_profit = 0.0

    for bet in history:

        date = bet.get(
            "date",
            ""
        )

        home = bet.get(
            "home",
            ""
        )

        away = bet.get(
            "away",
            ""
        )

        home_goals = bet.get(
            "home_goals"
        )

        away_goals = bet.get(
            "away_goals"
        )

        if (
            home_goals is not None
            and away_goals is not None
        ):

            score = (
                f"{home_goals}-{away_goals}"
            )

        else:

            score = "-"

        bet_type = bet.get(
            "bet",
            ""
        )

        odds = safe_float(
            bet.get("odds"),
            0
        )

        ev = safe_float(
            bet.get("ev"),
            0
        )

        stake = safe_float(
            bet.get("stake"),
            0
        )

        result = bet.get(
            "result",
            "pending"
        )

        profit = safe_float(
            bet.get("profit"),
            0
        )

        if result == "win":

            if profit == 0:

                profit = round(
                    stake * (odds - 1),
                    2
                )

            total_profit += profit

        elif result == "loss":

            if profit == 0:

                profit = -round(
                    stake,
                    2
                )

            total_profit += profit

        else:

            profit = 0.0

        ws.append([
            date,
            f"{home} vs {away}",
            score,
            bet_type,
            odds,
            ev,
            stake,
            result,
            profit
        ])

    ws.append([])

    ws.append([
        "ИТОГО",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        round(total_profit, 2)
    ])

    for col in range(
        1,
        len(headers) + 1
    ):

        column_letter = chr(
            64 + col
        )

        ws.column_dimensions[
            column_letter
        ].width = 15

    output = io.BytesIO()

    wb.save(output)

    output.seek(0)

    return (
        output,
        (
            f"✅ Экспорт завершен! "
            f"Всего ставок: {len(history)}, "
            f"Прибыль: ${round(total_profit, 2)}"
        )
    )


# ============================================================
# ПОИСК МАТЧЕЙ
# ============================================================

def get_matches_with_factors():

    all_matches = []

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    logger.info(
        f"🔍 Поиск матчей на: {today}"
    )

    all_leagues = (
        list(Config.LEAGUES)
        + list(
            getattr(
                Config,
                "CUP_LEAGUES",
                []
            )
        )
    )

    logger.info(
        f"📊 Всего соревнований: "
        f"{len(all_leagues)}"
    )

    for league_id in all_leagues:

        search_date = today

        league_name = (
            Config.LEAGUE_NAMES.get(
                league_id,
                str(league_id)
            )
        )

        try:

            matches = football_api.get_matches(
                league_id,
                search_date
            )

            if (
                not matches
                or not isinstance(
                    matches,
                    list
                )
            ):

                logger.info(
                    f"🔥 Нет матчей в "
                    f"{league_name} "
                    f"на {search_date}"
                )

                continue

            for match in matches:

                if not isinstance(
                    match,
                    dict
                ):
                    continue

                fixture = match.get(
                    "fixture"
                )

                if not isinstance(
                    fixture,
                    dict
                ):
                    continue

                status = fixture.get(
                    "status",
                    {}
                )

                if not isinstance(
                    status,
                    dict
                ):
                    continue

                if status.get(
                    "short"
                ) != "NS":

                    continue

                match_id = fixture.get(
                    "id"
                )

                if not match_id:
                    continue

                duplicate = any(
                    isinstance(m, dict)
                    and m.get(
                        "fixture",
                        {}
                    ).get("id") == match_id
                    for m in all_matches
                )

                if duplicate:
                    continue

                teams = match.get(
                    "teams",
                    {}
                )

                if not isinstance(
                    teams,
                    dict
                ):
                    continue

                home_team = teams.get(
                    "home",
                    {}
                )

                away_team = teams.get(
                    "away",
                    {}
                )

                if (
                    not isinstance(
                        home_team,
                        dict
                    )
                    or not isinstance(
                        away_team,
                        dict
                    )
                ):
                    continue

                home_id = home_team.get(
                    "id"
                )

                away_id = away_team.get(
                    "id"
                )

                if not home_id or not away_id:
                    continue

                match["factors"] = {

                    "home_form":
                        football_api.get_form(
                            home_id
                        ),

                    "away_form":
                        football_api.get_form(
                            away_id
                        ),

                    "home_injuries_list":
                        football_api.get_injuries(
                            home_id
                        ) or [],

                    "away_injuries_list":
                        football_api.get_injuries(
                            away_id
                        ) or [],

                    "home_id":
                        home_id,

                    "away_id":
                        away_id,

                    "referee":
                        fixture.get(
                            "referee"
                        )
                }

                match["weather"] = None

                match["weather_reason"] = (
                    "🌤️ Погода отключена"
                )

                league_data = match.get(
                    "league"
                )

                if isinstance(
                    league_data,
                    dict
                ):

                    league_data["name"] = (
                        league_name
                    )

                all_matches.append(
                    match
                )

        except Exception as e:

            error_msg = (
                f"Ошибка {league_name} "
                f"на {search_date}: {e}"
            )

            logger.error(
                f"❌ {error_msg}"
            )

            send_error_to_telegram(
                error_msg
            )

        time.sleep(0.1)

    logger.info(
        f"📊 ВСЕГО найдено матчей: "
        f"{len(all_matches)}"
    )

    return all_matches


# ============================================================
# ПАРСИНГ КОЭФФИЦИЕНТОВ
# ============================================================

def parse_odds(odds_data):

    if not isinstance(
        odds_data,
        dict
    ):
        return None

    bookmakers = (
        odds_data.get(
            "bookmakers"
        ) or []
    )

    if (
        not isinstance(
            bookmakers,
            list
        )
        or not bookmakers
    ):
        return None

    bookmaker = bookmakers[0]

    if not isinstance(
        bookmaker,
        dict
    ):
        return None

    odds_dict = {}

    bets = (
        bookmaker.get(
            "bets"
        ) or []
    )

    for bet in bets:

        if not isinstance(
            bet,
            dict
        ):
            continue

        values = (
            bet.get(
                "values"
            ) or []
        )

        for value in values:

            if not isinstance(
                value,
                dict
            ):
                continue

            bet_type = str(
                value.get(
                    "value",
                    ""
                )
            ).strip()

            # =================================================
            # ГЛАВНОЕ ИСПРАВЛЕНИЕ
            # odds всегда превращаем в float
            # =================================================

            odd = safe_float(
                value.get("odd"),
                0
            )

            if (
                bet_type
                and odd > 0
            ):

                odds_dict[
                    bet_type
                ] = odd

    return odds_dict


# ============================================================
# РАСЧЕТ XG
# ============================================================

def calculate_adjusted_xg(
    home_id,
    away_id,
    factors
):

    home_xg = 1.2
    away_xg = 1.0

    home_form = (
        factors.get(
            "home_form",
            ""
        )
        or ""
    )

    away_form = (
        factors.get(
            "away_form",
            ""
        )
        or ""
    )

    if isinstance(
        home_form,
        (list, tuple)
    ):

        home_form = "".join(
            str(x)
            for x in home_form
        )

    if isinstance(
        away_form,
        (list, tuple)
    ):

        away_form = "".join(
            str(x)
            for x in away_form
        )

    home_form = str(
        home_form
    ).upper()

    away_form = str(
        away_form
    ).upper()

    if home_form:

        home_form_points = sum(
            3 if l == "W"
            else 1 if l == "D"
            else 0
            for l in home_form
        )

        home_form_ratio = (
            home_form_points
            /
            (len(home_form) * 3)
        )

        home_xg *= (
            0.8
            +
            home_form_ratio * 0.4
        )

        logger.info(
            f"   📊 Форма хозяев: "
            f"{home_form} "
            f"(коэф: "
            f"{0.8 + home_form_ratio * 0.4:.2f})"
        )

    if away_form:

        away_form_points = sum(
            3 if l == "W"
            else 1 if l == "D"
            else 0
            for l in away_form
        )

        away_form_ratio = (
            away_form_points
            /
            (len(away_form) * 3)
        )

        away_xg *= (
            0.8
            +
            away_form_ratio * 0.4
        )

        logger.info(
            f"   📊 Форма гостей: "
            f"{away_form} "
            f"(коэф: "
            f"{0.8 + away_form_ratio * 0.4:.2f})"
        )

    home_injuries = (
        factors.get(
            "home_injuries_list",
            []
        )
        or []
    )

    away_injuries = (
        factors.get(
            "away_injuries_list",
            []
        )
        or []
    )

    if home_injuries:

        injury_penalty = min(
            len(home_injuries) * 0.05,
            0.3
        )

        home_xg *= (
            1 - injury_penalty
        )

        logger.info(
            f"   🏥 Травмы хозяев: "
            f"{len(home_injuries)} "
            f"(пенальти: "
            f"{injury_penalty * 100:.0f}%)"
        )

    if away_injuries:

        injury_penalty = min(
            len(away_injuries) * 0.05,
            0.3
        )

        away_xg *= (
            1 - injury_penalty
        )

        logger.info(
            f"   🏥 Травмы гостей: "
            f"{len(away_injuries)} "
            f"(пенальти: "
            f"{injury_penalty * 100:.0f}%)"
        )

    home_xg *= 1.1
    away_xg *= 0.9

    logger.info(
        "   🏠 Домашнее преимущество: "
        "+10% / -10%"
    )

    return (
        home_xg,
        away_xg
    )


# ============================================================
# ТОП МАТЧЕЙ
# ============================================================

def find_top_matches(matches):

    all_matches_data = []

    bets_placed = 0

    max_bets = int(
        getattr(
            Config,
            "MAX_BETS_PER_RUN",
            0
        )
        or 0
    )

    logger.info(
        f"🔍 Анализ "
        f"{len(matches)} матчей..."
    )

    BET_TYPES = [

        {
            "type": "under",
            "label": "ТМ 2.5",
            "marker": 42.86875,
            "keys": [
                "Under 2.5",
                "Under",
                "U 2.5"
            ]
        },

        {
            "type": "btts",
            "label": "ОБЗ",
            "marker": 40.7253125,
            "keys": [
                "Both Team Score",
                "BTTS",
                "Both Teams to Score"
            ]
        },

        {
            "type": "1X",
            "label": "1X",
            "marker": 45.125,
            "keys": [
                "Home/Draw",
                "1X"
            ]
        },

        {
            "type": "over",
            "label": "ТБ 2.5",
            "marker": 41.375,
            "keys": [
                "Over 2.5",
                "Over",
                "O 2.5"
            ]
        },

        {
            "type": "X2",
            "label": "X2",
            "marker": 43.1875,
            "keys": [
                "Away/Draw",
                "X2"
            ]
        }
    ]

    for match in matches:

        if not isinstance(
            match,
            dict
        ):
            continue

        if (
            max_bets > 0
            and bets_placed >= max_bets
        ):

            logger.info(
                f"⚠️ Достигнут "
                f"лимит ставок: "
                f"{max_bets}"
            )

            break

        try:

            fixture = match.get(
                "fixture"
            )

            if not isinstance(
                fixture,
                dict
            ):
                continue

            fixture_id = fixture.get(
                "id"
            )

            teams = match.get(
                "teams"
            )

            if (
                not fixture_id
                or not isinstance(
                    teams,
                    dict
                )
            ):
                continue

            home_team = teams.get(
                "home"
            )

            away_team = teams.get(
                "away"
            )

            if (
                not isinstance(
                    home_team,
                    dict
                )
                or not isinstance(
                    away_team,
                    dict
                )
            ):
                continue

            home = home_team.get(
                "name",
                "Unknown"
            )

            away = away_team.get(
                "name",
                "Unknown"
            )

            logger.info(
                f"📊 Анализ: "
                f"{home} vs {away} "
                f"(ID: {fixture_id})"
            )

            odds_data = (
                football_api.get_match_odds(
                    fixture_id
                )
            )

            odds_dict = parse_odds(
                odds_data
            )

            if not odds_dict:

                logger.warning(
                    f"⚠️ Нет/не удалось "
                    f"распарсить коэффициенты: "
                    f"{home} vs {away}"
                )

                continue

            factors = (
                match.get(
                    "factors"
                )
                or {}
            )

            home_id = factors.get(
                "home_id"
            )

            away_id = factors.get(
                "away_id"
            )

            home_xg, away_xg = (
                calculate_adjusted_xg(
                    home_id,
                    away_id,
                    factors
                )
            )

            logger.info(
                f"   📈 Итоговый XG: "
                f"{home} "
                f"{home_xg:.2f} - "
                f"{away_xg:.2f} "
                f"{away}"
            )

            probs = (
                calculate_probabilities(
                    home_xg,
                    away_xg
                )
                or {}
            )

            league_data = match.get(
                "league"
            )

            if isinstance(
                league_data,
                dict
            ):

                league = league_data.get(
                    "name",
                    "Unknown"
                )

            else:

                league = "Unknown"

            match_time = fixture.get(
                "date",
                ""
            )

            if match_time:

                try:

                    dt = datetime.fromisoformat(
                        str(
                            match_time
                        ).replace(
                            "Z",
                            "+00:00"
                        )
                    )

                    dt += timedelta(
                        hours=TIMEZONE_OFFSET
                    )

                    match_time = dt.strftime(
                        "%d.%m.%Y %H:%M"
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    match_time = (
                        "Время не указано"
                    )

            else:

                match_time = (
                    "Время не указано"
                )

            match_data = {

                "home": home,

                "away": away,

                "league": league,

                "fixture_id":
                    fixture_id,

                "match_time":
                    match_time,

                "home_xg":
                    round(
                        home_xg,
                        2
                    ),

                "away_xg":
                    round(
                        away_xg,
                        2
                    ),

                "weather_reason":
                    "🌤️",

                "factors":
                    factors,

                "intuition":
                    [],

                "bets":
                    []
            }

            # =================================================
            # АНАЛИЗ СТАВОК
            # =================================================

            for bet_config in BET_TYPES:

                bet_type = (
                    bet_config["type"]
                )

                label = (
                    bet_config["label"]
                )

                marker = safe_float(
                    bet_config["marker"],
                    0
                )

                odds = None

                for key in bet_config[
                    "keys"
                ]:

                    if key in odds_dict:

                        odds = safe_float(
                            odds_dict[key],
                            0
                        )

                        break

                if (
                    odds is None
                    or odds <= 1
                ):
                    continue

                prob = safe_float(
                    probs.get(
                        bet_type,
                        0.33
                    ),
                    0.33
                )

                # Если вероятность пришла
                # как 75 вместо 0.75
                if prob > 1:

                    prob /= 100.0

                prob = max(
                    0.0,
                    min(
                        prob,
                        1.0
                    )
                )

                try:

                    ev = safe_float(
                        calculate_ev(
                            prob,
                            odds
                        ),
                        0
                    )

                except Exception as e:

                    logger.error(
                        f"❌ Ошибка EV "
                        f"для {label}: "
                        f"{e}"
                    )

                    continue

                if ev < 5:
                    continue

                match_data[
                    "bets"
                ].append({

                    "bet_type":
                        bet_type,

                    "label":
                        label,

                    "odds":
                        odds,

                    "prob":
                        round(
                            prob * 100,
                            1
                        ),

                    "ev":
                        round(
                            ev,
                            1
                        ),

                    "stake":
                        round(
                            marker,
                            2
                        ),

                    "marker_stake":
                        marker,

                    "fixture_id":
                        fixture_id
                })

                logger.info(
                    f"   ✅ ДОБАВЛЕНА "
                    f"СТАВКА: {label} | "
                    f"КЭФ: {odds:.2f} | "
                    f"EV: {ev:.2f}%"
                )

            if not match_data[
                "bets"
            ]:

                continue

            all_matches_data.append(
                match_data
            )

            # =================================================
            # AUTOBET
            # =================================================

            try:

                auto = get_auto_bet()

                if auto is None:

                    logger.error(
                        "❌ AutoBet не "
                        "загружен — "
                        "пропускаем ставку"
                    )

                    continue

                bet_result = (
                    auto.check_and_bet(
                        match_data
                    )
                )

                if bet_result:

                    bets_placed += 1

                    # =================================================
                    # ИСПРАВЛЕНО
                    # Здесь больше нет сломанной f-string.
                    # =================================================

                    bet_match = str(
                        bet_result.get(
                            "match",
                            f"{home} vs {away}"
                        )
                    )

                    bet_time = (
                        bet_result.get(
                            "match_time",
                            match_time
                        )
                    )

                    bet_name = str(
                        bet_result.get(
                            "bet",
                            ""
                        )
                    )

                    bet_odds = safe_float(
                        bet_result.get(
                            "odds"
                        ),
                        odds
                    )

                    bet_stake = safe_float(
                        bet_result.get(
                            "stake"
                        ),
                        0
                    )

                    bet_ev = safe_float(
                        bet_result.get(
                            "ev"
                        ),
                        0
                    )

                    marker_stake = (
                        bet_result.get(
                            "marker_stake"
                        )
                    )

                    msg = (
                        "🤖 <b>АВТО-СТАВКА "
                        f"#{bets_placed}</b>\n"
                    )

                    msg += (
                        "🏟️ {}\n".format(
                            bet_match
                        )
                    )

                    if bet_time:

                        msg += (
                            "📅 {}\n".format(
                                bet_time
                            )
                        )

                    msg += (
                        "📊 {} | КЭФ: "
                        "{:.2f}\n".format(
                            bet_name,
                            bet_odds
                        )
                    )

                    msg += (
                        "💰 Сумма: "
                        "${:.2f}\n".format(
                            bet_stake
                        )
                    )

                    msg += (
                        "📈 EV: "
                        "{:.1f}%".format(
                            bet_ev
                        )
                    )

                    if marker_stake is not None:

                        msg += (
                            "\n🎯 Маркер: "
                            "${:.2f}".format(
                                safe_float(
                                    marker_stake
                                )
                            )
                        )

                    send_telegram(
                        msg
                    )

                    logger.info(
                        f"✅ АВТО-СТАВКА "
                        f"#{bets_placed}"
                    )

            except Exception as e:

                logger.exception(
                    f"❌ Ошибка "
                    f"авто-ставки: {e}"
                )

                send_error_to_telegram(
                    f"Ошибка авто-ставки: {e}"
                )

        except Exception as e:

            logger.exception(
                f"❌ Ошибка анализа "
                f"матча: {e}"
            )

    logger.info(
        f"📊 Найдено "
        f"{len(all_matches_data)} "
        f"матчей, сделано "
        f"{bets_placed} ставок"
    )

    cache = storage.load_cache()

    cache[
        "top_matches"
    ] = all_matches_data

    storage.save_cache(
        cache
    )

    return all_matches_data[:20]


# ============================================================
# ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА
# ============================================================

def determine_bet_result(
    bet_type,
    home_goals,
    away_goals
):

    home_goals = int(
        home_goals
    )

    away_goals = int(
        away_goals
    )

    total = (
        home_goals
        +
        away_goals
    )

    bet_type_lower = str(
        bet_type or ""
    ).lower().strip()

    if (
        "оз - да"
        in bet_type_lower
        or "обз"
        in bet_type_lower
        or "btts"
        in bet_type_lower
    ):

        return (
            "win"
            if home_goals > 0
            and away_goals > 0
            else "loss"
        )

    if (
        "тм 2.5"
        in bet_type_lower
        or "under"
        in bet_type_lower
    ):

        return (
            "win"
            if total < 2.5
            else "loss"
        )

    if (
        "тб 2.5"
        in bet_type_lower
        or "over"
        in bet_type_lower
    ):

        return (
            "win"
            if total > 2.5
            else "loss"
        )

    if (
        "1x"
        in bet_type_lower
        or "1х"
        in bet_type_lower
    ):

        return (
            "win"
            if home_goals >= away_goals
            else "loss"
        )

    if (
        "x2"
        in bet_type_lower
        or "х2"
        in bet_type_lower
    ):

        return (
            "win"
            if away_goals >= home_goals
            else "loss"
        )

    if (
        "п1"
        in bet_type_lower
        or "победа хозяев"
        in bet_type_lower
    ):

        if home_goals > away_goals:
            return "win"

        if home_goals == away_goals:
            return "push"

        return "loss"

    if (
        "п2"
        in bet_type_lower
        or "победа гостей"
        in bet_type_lower
    ):

        if away_goals > home_goals:
            return "win"

        if home_goals == away_goals:
            return "push"

        return "loss"

    return "pending"


# ============================================================
# ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ
# ============================================================

def update_pending_bets():

    history = storage.load_history()

    updated = 0

    for bet in history:

        if bet.get(
            "result"
        ) not in (
            "pending",
            None
        ):

            continue

        fixture_id = bet.get(
            "fixture_id"
        )

        if not fixture_id:

            home = bet.get(
                "home",
                ""
            )

            away = bet.get(
                "away",
                ""
            )

            if (
                home
                and away
                and home != "Unknown"
                and away != "Unknown"
            ):

                try:

                    fixture_id = (
                        football_api.find_fixture_by_teams(
                            home,
                            away
                        )
                    )

                except Exception as e:

                    logger.error(
                        f"Ошибка поиска "
                        f"fixture: {e}"
                    )

                    fixture_id = None

                if fixture_id:

                    bet[
                        "fixture_id"
                    ] = fixture_id

        if not fixture_id:
            continue

        try:

            match_data = (
                football_api.get_match_result(
                    fixture_id
                )
            )

        except Exception as e:

            logger.error(
                f"Ошибка получения "
                f"результата "
                f"{fixture_id}: {e}"
            )

            continue

        if not match_data:
            continue

        goals = match_data.get(
            "goals",
            {}
        )

        if not isinstance(
            goals,
            dict
        ):
            continue

        home_goals = goals.get(
            "home"
        )

        away_goals = goals.get(
            "away"
        )

        if (
            home_goals is None
            or away_goals is None
        ):

            continue

        try:

            result = determine_bet_result(
                bet.get(
                    "bet",
                    ""
                ),
                home_goals,
                away_goals
            )

        except Exception as e:

            logger.error(
                f"Ошибка определения "
                f"результата: {e}"
            )

            continue

        if result == "pending":
            continue

        bet[
            "result"
        ] = result

        bet[
            "home_goals"
        ] = home_goals

        bet[
            "away_goals"
        ] = away_goals

        stake = safe_float(
            bet.get(
                "stake"
            ),
            0
        )

        odds = safe_float(
            bet.get(
                "odds"
            ),
            1
        )

        if result == "win":

            bet[
                "profit"
            ] = round(
                stake * (odds - 1),
                2
            )

        elif result == "loss":

            bet[
                "profit"
            ] = -round(
                stake,
                2
            )

        else:

            bet[
                "profit"
            ] = 0.0

        updated += 1

        logger.info(
            f"✅ Обновлена ставка: "
            f"{bet.get('home')} vs "
            f"{bet.get('away')} → "
            f"{result}"
        )

    if updated > 0:

        storage.save_history(
            history
        )

        recalc_stats()

        send_telegram(
            f"✅ Автоматически "
            f"обновлено "
            f"{updated} результатов!"
        )

    return updated


# ============================================================
# ПЕРЕСЧЕТ СТАТИСТИКИ
# ============================================================

def recalc_stats():

    history = storage.load_history()

    stats = storage.load_stats()

    total = len(
        history
    )

    wins = sum(
        1
        for b in history
        if b.get("result") == "win"
    )

    losses = sum(
        1
        for b in history
        if b.get("result") == "loss"
    )

    pushes = sum(
        1
        for b in history
        if b.get("result") == "push"
    )

    total_profit = sum(
        safe_float(
            b.get("profit"),
            0
        )
        for b in history
    )

    total_stake = sum(
        safe_float(
            b.get("stake"),
            0
        )
        for b in history
    )

    stats[
        "total"
    ] = total

    stats[
        "wins"
    ] = wins

    stats[
        "losses"
    ] = losses

    stats[
        "pushes"
    ] = pushes

    stats[
        "total_profit"
    ] = round(
        total_profit,
        2
    )

    stats[
        "winrate"
    ] = (
        round(
            wins
            /
            (wins + losses)
            * 100,
            1
        )
        if wins + losses
        else 0
    )

    stats[
        "roi"
    ] = (
        round(
            total_profit
            /
            total_stake
            * 100,
            1
        )
        if total_stake
        else 0
    )

    storage.save_stats(
        stats
    )

    logger.info(
        f"📊 Статистика "
        f"пересчитана: {stats}"
    )


# ============================================================
# WEBHOOK
# ============================================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    global search_running

    try:

        data = request.get_json(
            silent=True
        ) or {}

        logger.info(
            "=" * 50
        )

        logger.info(
            "📨 ПОЛУЧЕН ЗАПРОС "
            "ОТ TELEGRAM"
        )

        logger.info(
            "=" * 50
        )

        # ====================================================
        # CALLBACK
        # ====================================================

        if "callback_query" in data:

            callback = data[
                "callback_query"
            ]

            callback_data = str(
                callback.get(
                    "data",
                    ""
                )
            )

            logger.info(
                f"📨 Нажата кнопка: "
                f"{callback_data}"
            )

            import requests

            answer_url = (
                f"https://api.telegram.org/"
                f"bot{Config.TELEGRAM_TOKEN}/"
                f"answerCallbackQuery"
            )

            try:

                requests.post(
                    answer_url,
                    json={
                        "callback_query_id":
                            callback.get(
                                "id",
                                ""
                            ),

                        "text":
                            "✅ Результат сохранён!"
                    },
                    timeout=5
                )

            except Exception as e:

                logger.error(
                    f"Ошибка ответа: {e}"
                )

            if callback_data.startswith(
                "result_"
            ):

                parts = callback_data.split(
                    "_",
                    2
                )

                if len(parts) >= 3:

                    result_type = parts[1]

                    match_id = parts[2]

                    cache = (
                        storage.load_cache()
                    )

                    match = cache.get(
                        f"match_{match_id}"
                    )

                    if not match:

                        try:

                            with open(
                                f"data/match_{match_id}.json",
                                "r",
                                encoding="utf-8"
                            ) as f:

                                match = json.load(
                                    f
                                )

                        except (
                            OSError,
                            json.JSONDecodeError
                        ):

                            match = None

                    if (
                        match
                        and result_type
                        != "skip"
                    ):

                        bets = (
                            match.get(
                                "bets"
                            )
                            or []
                        )

                        if bets:

                            best_bet = bets[0]

                            label = str(
                                best_bet.get(
                                    "label",
                                    ""
                                )
                            ).lower()

                            if result_type == "home":

                                result = (
                                    "win"
                                    if (
                                        "1x"
                                        in label
                                        or "п1"
                                        in label
                                    )
                                    else "loss"
                                )

                            elif result_type == "away":

                                result = (
                                    "win"
                                    if (
                                        "x2"
                                        in label
                                        or "п2"
                                        in label
                                    )
                                    else "loss"
                                )

                            elif result_type == "draw":

                                result = (
                                    "win"
                                    if (
                                        "1x"
                                        in label
                                        or "x2"
                                        in label
                                    )
                                    else "loss"
                                )

                            else:

                                result = "loss"

                            stake = safe_float(
                                best_bet.get(
                                    "stake"
                                ),
                                0
                            )

                            odds = safe_float(
                                best_bet.get(
                                    "odds"
                                ),
                                1
                            )

                            if result == "win":

                                profit = round(
                                    stake
                                    * (
                                        odds - 1
                                    ),
                                    2
                                )

                            elif result == "loss":

                                profit = -stake

                            else:

                                profit = 0.0

                            history = (
                                storage.load_history()
                            )

                            history.append({

                                "home":
                                    match.get(
                                        "home",
                                        ""
                                    ),

                                "away":
                                    match.get(
                                        "away",
                                        ""
                                    ),

                                "league":
                                    match.get(
                                        "league",
                                        ""
                                    ),

                                "fixture_id":
                                    match.get(
                                        "fixture_id"
                                    ),

                                "bet":
                                    best_bet.get(
                                        "label",
                                        ""
                                    ),

                                "odds":
                                    odds,

                                "stake":
                                    stake,

                                "ev":
                                    safe_float(
                                        best_bet.get(
                                            "ev"
                                        ),
                                        0
                                    ),

                                "result":
                                    result,

                                "profit":
                                    profit,

                                "date":
                                    datetime.now().strftime(
                                        "%Y-%m-%d %H:%M"
                                    ),

                                "home_goals":
                                    None,

                                "away_goals":
                                    None
                            })

                            storage.save_history(
                                history
                            )

                            recalc_stats()

                            cache.pop(
                                f"match_{match_id}",
                                None
                            )

                            storage.save_cache(
                                cache
                            )

                            try:

                                os.remove(
                                    f"data/match_{match_id}.json"
                                )

                            except OSError:

                                pass

                            msg = (
                                "✅ Результат "
                                "сохранён!\n"
                                "{} vs {} → {}".format(
                                    match.get(
                                        "home",
                                        ""
                                    ),
                                    match.get(
                                        "away",
                                        ""
                                    ),
                                    result
                                )
                            )

                            if result == "win":

                                msg += (
                                    f"\n💰 Прибыль: "
                                    f"+${profit:.2f}"
                                )

                            elif result == "loss":

                                msg += (
                                    f"\n💰 Проигрыш: "
                                    f"-${stake:.2f}"
                                )

                            send_telegram(
                                msg
                            )

                    elif (
                        match
                        and result_type
                        == "skip"
                    ):

                        cache.pop(
                            f"match_{match_id}",
                            None
                        )

                        storage.save_cache(
                            cache
                        )

                        try:

                            os.remove(
                                f"data/match_{match_id}.json"
                            )

                        except OSError:

                            pass

            return "ok", 200

        # ====================================================
        # MESSAGE
        # ====================================================

        if "message" in data:

            message = data[
                "message"
            ]

            text = str(
                message.get(
                    "text",
                    ""
                )
                or ""
            )

            chat_id = (
                message.get(
                    "chat",
                    {}
                ).get(
                    "id"
                )
            )

            logger.info(
                f"👤 CHAT ID: "
                f"{chat_id}"
            )

            logger.info(
                f"📝 ТЕКСТ: "
                f"{text}"
            )

            if str(chat_id) != str(
                Config.ADMIN_CHAT_ID
            ):

                logger.warning(
                    f"⛔ ДОСТУП "
                    f"ЗАПРЕЩЕН "
                    f"для {chat_id}"
                )

                send_telegram(
                    "⛔ Нет доступа"
                )

                return "ok", 200

            # =================================================
            # COMMANDS
            # =================================================

            if text == "/start":

                send_telegram(
                    handlers.handle_start()
                )

            elif text == "/help":

                send_telegram(
                    handlers.handle_help()
                )

            elif text == "/update":

                if search_running:

                    send_telegram(
                        "⚠️ Поиск уже запущен!"
                    )

                else:

                    search_running = True

                    start_time = (
                        datetime.now()
                    )

                    try:

                        send_telegram(
                            f"🔄 Поиск "
                            f"матчей в "
                            f"{len(Config.LEAGUES)} "
                            f"лигах..."
                        )

                        matches = (
                            get_matches_with_factors()
                        )

                        if matches:

                            send_telegram(
                                f"📊 Найдено "
                                f"{len(matches)} "
                                f"матчей. "
                                f"Анализирую..."
                            )

                            top_matches = (
                                find_top_matches(
                                    matches
                                )
                            )

                            if top_matches:

                                elapsed = int(
                                    (
                                        datetime.now()
                                        - start_time
                                    ).total_seconds()
                                )

                                auto = (
                                    get_auto_bet()
                                )

                                bets_today_count = (
                                    getattr(
                                        auto,
                                        "bets_today",
                                        0
                                    )
                                    if auto
                                    else 0
                                )

                                send_telegram(

                                    "✅ "
                                    "<b>ПОИСК "
                                    "ЗАВЕРШЕН!</b>\n"

                                    f"📊 Найдено "
                                    f"матчей: "
                                    f"{len(matches)}\n"

                                    f"🤖 Авто-ставок: "
                                    f"{bets_today_count}\n"

                                    f"⏱️ Время: "
                                    f"{elapsed} сек."
                                )

                            else:

                                send_telegram(
                                    "❌ Ставок "
                                    "не найдено"
                                )

                        else:

                            send_telegram(
                                "❌ Матчей "
                                "не найдено"
                            )

                    except Exception as e:

                        logger.exception(
                            f"❌ Ошибка /update: "
                            f"{e}"
                        )

                        send_error_to_telegram(
                            f"Ошибка /update: {e}"
                        )

                    finally:

                        search_running = False

            elif text == "/today":

                send_telegram(
                    handlers.handle_today()
                )

            elif text == "/bank":

                send_telegram(
                    handlers.handle_bank()
                )

            elif text == "/stats":

                send_telegram(
                    handlers.handle_stats()
                )

            elif text == "/bettypes":

                send_telegram(
                    handlers.handle_bettypes()
                )

            elif text == "/timestats":

                send_telegram(
                    handlers.handle_timestats()
                )

            elif text == "/mlstats":

                send_telegram(
                    handlers.handle_mlstats()
                )

            elif text == "/report":

                send_telegram(
                    handlers.handle_report()
                )

            elif text == "/export":

                file, message_text = (
                    export_to_excel()
                )

                if file:

                    send_telegram(
                        message_text
                    )

                    import requests

                    url = (
                        f"https://api.telegram.org/"
                        f"bot{Config.TELEGRAM_TOKEN}/"
                        f"sendDocument"
                    )

                    files = {

                        "document": (
                            "history.xlsx",
                            file,
                            (
                                "application/"
                                "vnd.openxmlformats-"
                                "officedocument."
                                "spreadsheetml.sheet"
                            )
                        )
                    }

                    data_form = {
                        "chat_id":
                            Config.ADMIN_CHAT_ID,

                        "caption":
                            "📊 История ставок"
                    }

                    try:

                        requests.post(
                            url,
                            files=files,
                            data=data_form,
                            timeout=30
                        )

                    except Exception as e:

                        logger.error(
                            f"Ошибка отправки "
                            f"файла: {e}"
                        )

                else:

                    send_telegram(
                        message_text
                    )

            elif text == "/autobet":

                auto = get_auto_bet()

                if auto is None:

                    send_telegram(
                        "❌ AutoBet "
                        "не загружен"
                    )

                else:

                    auto.enabled = not getattr(
                        auto,
                        "enabled",
                        True
                    )

                    send_telegram(
                        handlers.handle_autobet(
                            auto.enabled
                        )
                    )

            elif text == "/train":

                send_telegram(
                    handlers.handle_train()
                )

            elif text == "/arb":

                send_telegram(
                    handlers.handle_arb()
                )

            elif text == "/anomalies":

                send_telegram(
                    handlers.handle_anomalies()
                )

            elif text == "/security":

                send_telegram(
                    handlers.handle_security()
                )

            elif text == "/stop":

                search_running = False

                send_telegram(
                    handlers.handle_stop()
                )

            elif text == "/update_results":

                send_telegram(
                    "🔄 Проверка "
                    "результатов матчей..."
                )

                updated = (
                    update_pending_bets()
                )

                if updated > 0:

                    send_telegram(
                        f"✅ Обновлено "
                        f"{updated} "
                        f"результатов!"
                    )

                else:

                    send_telegram(
                        "📭 Нет завершённых "
                        "матчей для обновления"
                    )

            elif text.startswith(
                "/team"
            ):

                team_name = (
                    text.replace(
                        "/team",
                        "",
                        1
                    ).strip()
                )

                send_telegram(
                    handlers.handle_team(
                        team_name
                    )
                )

            elif text.startswith(
                "/unblock"
            ):

                ip = (
                    text.replace(
                        "/unblock",
                        "",
                        1
                    ).strip()
                )

                send_telegram(
                    handlers.handle_unblock(
                        ip
                    )
                )

            elif text.startswith(
                "/result"
            ):

                # =================================================
                # ИСПРАВЛЕННЫЙ ПАРСИНГ
                #
                # Работает с названиями команд,
                # содержащими пробелы.
                #
                # /result Fulham vs Chelsea 2-1
                # =================================================

                parts = (
                    text.replace(
                        "/result",
                        "",
                        1
                    ).strip()
                )

                if " vs " in parts:

                    match_parts = (
                        parts.rsplit(
                            " ",
                            1
                        )
                    )

                    if (
                        len(match_parts) == 2
                        and "-"
                        in match_parts[1]
                    ):

                        send_telegram(
                            handlers.handle_result(
                                match_parts[0],
                                match_parts[1]
                            )
                        )

                    else:

                        send_telegram(
                            "⚠️ Используй: "
                            "/result "
                            "Fulham vs Chelsea 2-1"
                        )

                else:

                    send_telegram(
                        "⚠️ Используй: "
                        "/result "
                        "Fulham vs Chelsea 2-1"
                    )

            else:

                send_telegram(
                    "❌ Неизвестная команда. "
                    "/help"
                )

        logger.info(
            "✅ Webhook завершен"
        )

        return "ok", 200

    except Exception as e:

        error_msg = (
            f"Webhook error: {e}"
        )

        logger.exception(
            f"❌ {error_msg}"
        )

        send_error_to_telegram(
            error_msg
        )

        # Telegram должен получить 200,
        # чтобы не повторять webhook бесконечно
        return "ok", 200


# ============================================================
# API STATS
# ============================================================

@app.route(
    "/api/stats",
    methods=["GET"]
)
def api_stats():

    stats = storage.load_stats()

    bank = storage.load_bank()

    history = storage.load_history()

    total_bets = len(
        history
    )

    wins = stats.get(
        "wins",
        0
    )

    losses = stats.get(
        "losses",
        0
    )

    pushes = stats.get(
        "pushes",
        0
    )

    total_profit = safe_float(
        stats.get(
            "total_profit"
        ),
        0
    )

    winrate = (
        round(
            wins
            /
            (wins + losses)
            * 100,
            1
        )
        if wins + losses
        else 0
    )

    total_stake = sum(
        safe_float(
            bet.get("stake"),
            0
        )
        for bet in history
    )

    roi = (
        round(
            total_profit
            /
            total_stake
            * 100,
            1
        )
        if total_stake
        else 0
    )

    avg_stake = (
        round(
            total_stake
            /
            total_bets,
            2
        )
        if total_bets
        else 0
    )

    return jsonify({

        "bank":
            bank,

        "total_bets":
            total_bets,

        "wins":
            wins,

        "losses":
            losses,

        "pushes":
            pushes,

        "profit":
            round(
                total_profit,
                2
            ),

        "winrate":
            winrate,

        "roi":
            roi,

        "avg_stake":
            avg_stake
    })


# ============================================================
# API HISTORY
# ============================================================

@app.route(
    "/api/history",
    methods=["GET"]
)
def api_history():

    history = storage.load_history()

    result = []

    for bet in history:

        item = dict(
            bet
        )

        stake = safe_float(
            item.get(
                "stake"
            ),
            0
        )

        odds = safe_float(
            item.get(
                "odds"
            ),
            1
        )

        if item.get(
            "result"
        ) == "win":

            item[
                "profit"
            ] = round(
                stake
                * (
                    odds - 1
                ),
                2
            )

        elif item.get(
            "result"
        ) == "loss":

            item[
                "profit"
            ] = -round(
                stake,
                2
            )

        else:

            item[
                "profit"
            ] = 0.0

        item[
            "match"
        ] = (
            f"{item.get('home', '')} "
            f"vs "
            f"{item.get('away', '')}"
        )

        result.append(
            item
        )

    return jsonify(
        result
    )


# ============================================================
# API BANK
# ============================================================

@app.route(
    "/api/bank",
    methods=["POST"]
)
def api_update_bank():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    if "bank" not in data:

        return jsonify({
            "error":
                "No bank value"
        }), 400

    bank = safe_float(
        data["bank"],
        0
    )

    storage.save_bank(
        bank
    )

    return jsonify({

        "success":
            True,

        "bank":
            bank
    })


# ============================================================
# API UPDATE HISTORY
# ============================================================

@app.route(
    "/api/update_history",
    methods=["POST"]
)
def update_history():

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        history = data.get(
            "history",
            []
        )

        if (
            not isinstance(
                history,
                list
            )
            or not history
        ):

            return jsonify({
                "error":
                    "Нет данных"
            }), 400

        storage.save_history(
            history
        )

        recalc_stats()

        stats = (
            storage.load_stats()
        )

        return jsonify({

            "success":
                True,

            "total":
                stats.get(
                    "total",
                    len(history)
                ),

            "wins":
                stats.get(
                    "wins",
                    0
                ),

            "losses":
                stats.get(
                    "losses",
                    0
                ),

            "pushes":
                stats.get(
                    "pushes",
                    0
                ),

            "profit":
                stats.get(
                    "total_profit",
                    0
                )
        })

    except Exception as e:

        error_msg = (
            f"Ошибка обновления "
            f"истории: {e}"
        )

        logger.exception(
            f"❌ {error_msg}"
        )

        send_error_to_telegram(
            error_msg
        )

        return jsonify({
            "error":
                str(e)
        }), 500


# ============================================================
# API MATCHES
# ============================================================

@app.route(
    "/api/matches",
    methods=["GET"]
)
def api_matches():

    cache = (
        storage.load_cache()
    )

    return jsonify(
        cache.get(
            "top_matches",
            []
        )
    )


# ============================================================
# MAIN
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return (
        "🤖 Quantum Bot v12 PRO | "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return {
        "status":
            "ok",

        "time":
            datetime.now().isoformat()
    }


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    setup_logging()

    start_scheduler()

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    logger.info(
        "🚀 БОТ ЗАПУЩЕН!"
    )

    logger.info(
        f"📊 Сканируется "
        f"{len(Config.LEAGUES)} лиг"
    )

    logger.info(
        f"🤖 Максимум ставок: "
        f"{Config.MAX_BETS_PER_RUN}"
    )

    logger.info(
        "✅ Мониторинг ошибок включен"
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
