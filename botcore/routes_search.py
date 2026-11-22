# ============================================================
# botcore/routes_search.py — Webhook Telegram и запуск поиска (/webhook, /api/trigger_search)
# (часть бывшего main.py; порядок модулей см. main.py)
# ============================================================
import sys
import os
import copy
import requests
import time
import json
import logging
import random
import math
import functools
import zipfile
import shutil
import itertools
import tempfile
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from threading import Lock, RLock, Thread
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory, render_template
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Config
from app.database.storage import storage
from app.telegram.handlers import handlers
from app.utils.logger import setup_logging, get_logger
from app.scheduler import start_scheduler
from app.llm import (
    llm_analyze_match,
    llm_analyze_batch,
    llm_generate_reason,
    llm_pick_best,
)


from botcore.common import *  # noqa: F401,F403
from botcore.football_api import *  # noqa: F401,F403
from botcore.autobet import *  # noqa: F401,F403
from botcore.simulator import *  # noqa: F401,F403
from botcore.analysis import *  # noqa: F401,F403
from botcore.odds_matches import *  # noqa: F401,F403
from botcore.strat_top import *  # noqa: F401,F403
from botcore.strat_value import *  # noqa: F401,F403
from botcore.lm_helpers import *  # noqa: F401,F403
from botcore.strat_lm import *  # noqa: F401,F403
from botcore.results import *  # noqa: F401,F403
from botcore.strat_combined import *  # noqa: F401,F403
from botcore.lab_tasks import *  # noqa: F401,F403
from botcore.calib_tools import *  # noqa: F401,F403
from botcore.jobs import *  # noqa: F401,F403

__all__ = [
    'search_running',
    'search_state',
    '_webhook_hits',
    '_webhook_lock',
    'WEBHOOK_MAX_PER_MINUTE',
    '_check_webhook_rate_limit',
    'webhook',
    'api_trigger_search',
    'api_search_status',
]


search_running = False


search_state = {}


# ============================================================
# WEBHOOK RATE-LIMIT
# ============================================================
_webhook_hits = defaultdict(list)


_webhook_lock = Lock()


WEBHOOK_MAX_PER_MINUTE = 30


def _check_webhook_rate_limit(chat_id):
    try:
        with _webhook_lock:
            now = time.time()
            _webhook_hits[chat_id] = [t for t in _webhook_hits[chat_id] if now - t < 60]
            if len(_webhook_hits[chat_id]) >= WEBHOOK_MAX_PER_MINUTE:
                return False
            _webhook_hits[chat_id].append(now)
            return True
    except Exception:
        return True


# ============================================================
# WEBHOOK
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global search_running, search_state
    try:
        if not hmac.compare_digest(
                request.headers.get('X-Telegram-Bot-Api-Secret-Token', '').encode('utf-8'),
                _WEBHOOK_SECRET.encode('utf-8')):
            return "forbidden", 403
        data = request.get_json()
        if not data:
            return "ok", 200

        if 'callback_query' in data:
            cb = data['callback_query']
            try:
                requests.post(
                    f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cb.get('id', ''), "text": "✅ Принято!"}
                )
            except Exception as e:
                logger.error(f"Ответ: {e}")
            return "ok", 200

        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            if str(chat_id) != str(Config.ADMIN_CHAT_ID):
                return "ok", 200
            if not _check_webhook_rate_limit(chat_id):
                send_telegram("⚠️ Слишком много команд.")
                return "ok", 200

            if text == '/start':
                send_telegram(handlers.handle_start())
            elif text == '/help':
                send_telegram(handlers.handle_help())

            elif text == '/analyze':
                send_telegram("⚠️ <code>/analyze Fulham vs Chelsea</code>")
            elif text.startswith('/analyze '):
                send_telegram(analyze_match(text[9:].strip()))

            elif text == '/team':
                send_telegram("⚠️ <code>/team Arsenal</code>")
            elif text.startswith('/team '):
                send_telegram(handlers.handle_team(text[6:].strip()))

            elif text == '/result':
                send_telegram("⚠️ <code>/result Fulham vs Chelsea 2-1</code>")
            elif text.startswith('/result '):
                parts = text[8:].strip()
                if ' vs ' in parts:
                    sp = parts.split(' vs ')
                    home = sp[0].strip()
                    rest = sp[1].split()
                    if len(rest) >= 2:
                        send_telegram(update_manual_result(f"{home} vs {rest[0]}", rest[1]))
                else:
                    send_telegram("⚠️ <code>/result Fulham vs Chelsea 2-1</code>")

            elif text == '/update':
                if search_running:
                    send_telegram("⚠️ Поиск уже запущен")
                    return "ok", 200
                search_running = True
                search_state = {'start_time': datetime.now()}
                send_telegram("🔎 Запущен анализ. Ждите...")

                def run_search():
                    global search_running
                    try:
                        matches = get_matches_with_factors()
                        if matches:
                            top = find_top_matches_with_tm25(matches)
                            if top:
                                value_list = [m for m in top if m.get('source') == 'value']
                                lm_list = [m for m in top if m.get('source') == 'line_movement']
                                other_list = [m for m in top if m.get('source') not in ('value', 'line_movement')]

                                msg = f"✅ <b>НАЙДЕНО: {len(top)}</b>\n"

                                if value_list:
                                    msg += f"\n💎 <b>VALUE ({len(value_list)}):</b>\n\n"
                                    for i, m in enumerate(value_list, 1):
                                        b = m['best_bet']
                                        clv_icon = ''
                                        if b.get('clv_action') == 'boosted':
                                            clv_icon = ' 🟢×1.25'
                                        elif b.get('clv_action') == 'reduced':
                                            clv_icon = ' 🟡×0.5'
                                        llm_str = ""
                                        if b.get('llm_reason'):
                                            llm_str = f"💡 <i>{b['llm_reason']}</i>\n"
                                        msg += (f"{i}. <b>{m['home']} vs {m['away']}</b> 💎{clv_icon}\n"
                                                f"🏆 {m.get('league', '?')}\n"
                                                f"📅 {m.get('match_time', '?')}\n"
                                                f"🎯 {b['label']} | КЭФ: {b['odds']} | EV: {b['ev']}%\n"
                                                f"📊 Prob: {b['prob']}% | XG: {m.get('total_xg', 0):.2f}\n"
                                                f"💵 Stake: ${b.get('stake', 0)}\n"
                                                f"🏷️ {b.get('bookmaker', '—')}\n"
                                                f"{llm_str}\n")

                                if lm_list:
                                    msg += f"\n📈 <b>LINE MOVEMENT ({len(lm_list)}):</b>\n\n"
                                    for i, m in enumerate(lm_list, 1):
                                        b = m['best_bet']
                                        direction = "📉" if b.get('direction') == 'drop' else "📈"
                                        msg += (f"{i}. <b>{m['home']} vs {m['away']}</b> {direction}\n"
                                                f"🏆 {m.get('league', '?')}\n"
                                                f"📅 {m.get('match_time', '?')}\n"
                                                f"🎯 {b['label']} | КЭФ: {b['odds']} (было {b.get('old_odds', 0)})\n"
                                                f"{direction} Движение: <b>{b.get('movement_pct', 0)}%</b> за {b.get('movement_hours', 0)}ч\n"
                                                f"📸 Снимков: {b.get('snapshots_count', 0)}\n"
                                                f"💵 Stake: ${b.get('stake', 0)}\n"
                                                f"💡 Кэф резко изменился — деньги идут в эту сторону\n\n")

                                if other_list:
                                    msg += f"\n🎯 <b>ОСТАЛЬНЫЕ ({len(other_list)}):</b>\n\n"
                                    for i, m in enumerate(other_list[:15], 1):
                                        b = m['best_bet']
                                        bonus = b.get('anomaly_bonus', 0)
                                        bonus_str = f" (+{bonus}% аномалия)" if bonus else ""
                                        src = m.get('source', '')
                                        lv = (" 🔥 PREMIUM" if src == 'tm25_premium'
                                              else (" ⭐ STANDARD" if src == 'tm25_standard' else ""))
                                        template_note = (" ⚠️ кэф шаблонный"
                                                         if b.get('odds_source') == 'template' else "")
                                        clv_icon = ''
                                        if b.get('clv_action') == 'boosted':
                                            clv_icon = ' 🟢×1.25'
                                        elif b.get('clv_action') == 'reduced':
                                            clv_icon = ' 🟡×0.5'
                                        llm_str = ""
                                        if b.get('llm_reason'):
                                            llm_str = f"💡 <i>{b['llm_reason']}</i>\n"
                                        msg += (f"{i}. <b>{m['home']} vs {m['away']}</b>{lv}{clv_icon}\n"
                                                f"🏆 {m.get('league', '?')}\n"
                                                f"📅 {m.get('match_time', '?')}\n"
                                                f"🎯 {b['label']} | КЭФ: {b['odds']} | EV: {b['ev']}%{bonus_str}{template_note}\n"
                                                f"📊 Prob: {b['prob']}% | XG: {m.get('total_xg', 0):.2f}\n"
                                                f"💵 Stake: ${b.get('stake', 0)}\n"
                                                f"🏷️ {b.get('bookmaker', '—')}\n"
                                                f"{llm_str}\n")
                                send_telegram(msg)
                            else:
                                send_telegram("❌ Ничего не найдено")
                        else:
                            send_telegram("❌ Матчей нет")
                    finally:
                        search_running = False

                Thread(target=run_search, daemon=True).start()

            elif text == '/reset_search':
                search_running = False
                send_telegram("✅ Сброшено")
            elif text == '/stop':
                search_running = False
                send_telegram("⏹️ Остановлено")

            elif text == '/today':
                send_telegram(handlers.handle_today())
            elif text == '/stats':
                send_telegram(handlers.handle_stats())
            elif text == '/bank':
                send_telegram(handlers.handle_bank())
            elif text == '/report':
                send_telegram(handlers.handle_report())
            elif text == '/bettypes':
                send_telegram(handlers.handle_bettypes())
            elif text == '/timestats':
                send_telegram(handlers.handle_timestats())

            elif text == '/strategies':
                report = strategy_tester.get_comparison_report()
                try:
                    clv_stats = _compute_all_strategy_clv(days=30)
                    if clv_stats:
                        report += "📊 <b>CLV ПО СТРАТЕГИЯМ (30д)</b>\n\n"
                        for src, st in clv_stats.items():
                            emoji = {
                                'excellent': '🟢',
                                'good': '🔵',
                                'weak': '🟡',
                                'critical': '🔴',
                                'insufficient_data': '⚪',
                            }.get(st['status'], '⚪')
                            label = {
                                '70_percent': '🎯 70%+',
                                'value': '💎 VALUE',
                                'tm25_premium': '🔥 ТМ 2.5 PREMIUM',
                                'tm25_standard': '⭐ ТМ 2.5 STD',
                                'btts': '⚽ BTTS',
                                'line_movement': '📈 LINE MOVEMENT',
                                'x2': '🔥 X2',
                            }.get(src, src)
                            report += (
                                f"{emoji} <b>{label}</b>\n"
                                f"   CLV: <b>{st['avg_clv']:+.2f}%</b> | "
                                f"Замеров: {st['count']} | "
                                f"x{st['multiplier']}\n\n"
                            )
                except Exception as e:
                    logger.error(f"CLV report: {e}")
                send_telegram(report)

            elif text == '/clv_strategies':
                try:
                    clv_stats = _compute_all_strategy_clv(days=30)
                    if not clv_stats:
                        send_telegram("📭 Нет данных CLV")
                    else:
                        msg = "📊 <b>CLV ПО СТРАТЕГИЯМ (30д)</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        for src, st in sorted(clv_stats.items(), key=lambda x: x[1]['avg_clv'], reverse=True):
                            emoji = {
                                'excellent': '🟢',
                                'good': '🔵',
                                'weak': '🟡',
                                'critical': '🔴',
                                'insufficient_data': '⚪',
                            }.get(st['status'], '⚪')
                            label = {
                                '70_percent': '🎯 70%+',
                                'value': '💎 VALUE',
                                'tm25_premium': '🔥 ТМ 2.5 PREMIUM',
                                'tm25_standard': '⭐ ТМ 2.5 STD',
                                'btts': '⚽ BTTS',
                                'line_movement': '📈 LINE MOVEMENT',
                                'x2': '🔥 X2',
                            }.get(src, src)
                            action = {
                                'excellent': 'x1.5 BOOST',
                                'good': 'normal',
                                'weak': 'x0.5 REDUCE',
                                'critical': '🛑 SKIP',
                                'insufficient_data': 'awaiting data',
                            }.get(st['status'], '')
                            msg += (
                                f"{emoji} <b>{label}</b>\n"
                                f"   CLV: <b>{st['avg_clv']:+.2f}%</b>\n"
                                f"   Замеров: {st['count']}\n"
                                f"   Действие: <b>{action}</b>\n\n"
                            )
                        send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/x2_info':
                try:
                    candidates = storage.get_x2_candidates(limit=500)
                    msg = f"🎯 <b>X2-КАНДИДАТЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += f"📊 Всего: <b>{len(candidates)}</b>\n\n"
                    if candidates:
                        msg += "🎯 <b>Последние 5:</b>\n"
                        for c in candidates[-5:][::-1]:
                            side = c.get('x2_side', 'X2')
                            ev = c.get('x2_ev', 0)
                            prob = c.get('x2_prob', 0)
                            entry = c.get('entry_odds', 0) or 0
                            res = c.get('result', 'pending')
                            emoji = '✅' if res == 'win' else '❌' if res == 'loss' else '⏳'
                            msg += (f"  {emoji} <b>{c.get('home')} vs {c.get('away')}</b>\n"
                                    f"    {side} @ {entry} | EV: {ev}% | Prob: {prob}%\n\n")
                    else:
                        msg += "📭 Пока нет кандидатов\n"
                    send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/update_results':
                send_telegram("🔄 Обновление запущено в фоне...")

                def _run_update_results():
                    try:
                        res = update_pending_bets()
                        x2 = update_x2_results()
                        ft = res.get('ft', 0)
                        live = res.get('live', 0)
                        if ft == 0 and live == 0 and x2 == 0:
                            send_telegram("📭 <b>Нет обновлений</b>")
                        else:
                            msg = "🔄 <b>ОБНОВЛЕНО</b>\n\n"
                            if ft > 0:
                                msg += f"✅ Завершено матчей: <b>{ft}</b>\n"
                            if live > 0:
                                msg += f"⚽ Live-счёт: <b>{live}</b>\n"
                            if x2 > 0:
                                msg += f"🎯 X2-результатов: <b>{x2}</b>\n"
                            send_telegram(msg)
                    except Exception as e:
                        logger.exception(f"update_results: {e}")
                        send_telegram(f"❌ Ошибка: {e}")

                Thread(target=_run_update_results, daemon=True).start()

            elif text == '/live':
                try:
                    bets = storage.autobet_load_all()
                    pending = [b for b in bets if b.get('result') == 'pending']
                    live_bets = [b for b in pending if b.get('live_score')]
                    no_live = [b for b in pending if not b.get('live_score')]
                    if not live_bets and not no_live:
                        send_telegram("📭 Нет активных матчей")
                    else:
                        status_map = {'1H': '1-й тайм', 'HT': 'Перерыв ⏸️',
                                      '2H': '2-й тайм', 'ET': 'Доп. время',
                                      'P': 'Пенальти', 'BT': 'Перерыв',
                                      'SUSP': 'Приостановлен', 'LIVE': 'LIVE'}
                        msg = f"⚽ <b>LIVE ({len(live_bets)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        for b in live_bets:
                            status = status_map.get(b.get('live_status', ''), 'LIVE')
                            minute = b.get('live_minute') or 0
                            ms = f" <b>{minute}'</b>" if minute else ""
                            msg += (f"🏟️ <b>{b.get('home')} vs {b.get('away')}</b>\n"
                                    f"⚽ <b>{b.get('live_score')}</b>{ms} • {status}\n"
                                    f"🎯 {b.get('bet_label', '—')} @ {b.get('odds', 0):.2f}\n\n")
                        if no_live:
                            msg += f"\n⏳ Ожидают: <b>{len(no_live)}</b>\n"
                        send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/force_settle':
                send_telegram("🔧 Запущено в фоне...")

                def _run_force_settle():
                    try:
                        res = update_pending_bets()
                        x2 = update_x2_results()
                        settled = autobet_manager.settle_pending()
                        clv = autobet_manager.compute_clv_for_settled()
                        send_telegram(
                            f"✅ <b>FORCE SETTLE ГОТОВО</b>\n\n"
                            f"📜 История: FT={res.get('ft', 0)}, LIVE={res.get('live', 0)}\n"
                            f"🎯 X2 закрыто: <b>{x2}</b>\n"
                            f"💸 Автоставки: <b>{settled}</b>\n"
                            f"📊 CLV: <b>{clv}</b>"
                        )
                    except Exception as e:
                        logger.exception(f"force_settle: {e}")
                        send_telegram(f"❌ Ошибка force_settle: {e}")

                Thread(target=_run_force_settle, daemon=True).start()

            elif text == '/force_settle_anomalies':
                send_telegram("🔧 Обновление аномалий...")

                def _run_settle_anomalies():
                    try:
                        updated = update_anomaly_results()
                        send_telegram(f"✅ Аномалий обновлено: <b>{updated}</b>")
                    except Exception as e:
                        logger.exception(f"force_settle_anomalies: {e}")
                        send_telegram(f"❌ Ошибка: {e}")

                Thread(target=_run_settle_anomalies, daemon=True).start()

            elif text == '/debug_pending':
                try:
                    bets = storage.autobet_load_all()
                    pending = [b for b in bets if b.get('result') == 'pending']
                    if not pending:
                        send_telegram("📭 Нет pending")
                    else:
                        msg = f"🔍 <b>DEBUG ({len(pending)})</b>\n\n"
                        for b in pending[:10]:
                            fid = b.get('fixture_id')
                            if fid:
                                md = football_api.get_match_result(fid)
                                if md:
                                    goals = md.get('goals', {})
                                    status = md.get('status', '?')
                                    is_final = ('✅FT' if md.get('is_final') else ('⚽' if md.get('is_live') else '⏳'))
                                    msg += f"<b>{b.get('home')} vs {b.get('away')}</b>\n  {is_final} {status} | {goals.get('home')}-{goals.get('away')}\n\n"
                        send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/snapshots':
                try:
                    stats = storage.get_odds_history_size()
                    x2_count = storage.x2_count()
                    send_telegram(f"📸 <b>СНИМКИ</b>\n\n"
                                  f"🎯 Матчей: <b>{stats['matches']}</b>\n"
                                  f"📊 Снимков: <b>{stats['snapshots']}</b>\n"
                                  f"💾 Размер: <b>{stats['size_kb']} КБ</b>\n"
                                  f"🎯 X2-кандидатов: <b>{x2_count}</b>")
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/snapshot':
                send_telegram("📸 Делаю снимки...")
                try:
                    n = snapshot_odds_for_upcoming()
                    send_telegram(f"✅ Создано: <b>{n}</b>" if n > 0 else "📭 Нечего снимать")
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/export':
                file, message = export_to_excel()
                send_telegram(message)
                if file:
                    try:
                        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendDocument"
                        requests.post(url,
                            files={'document': ('history.xlsx', file,
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                            data={'chat_id': Config.ADMIN_CHAT_ID, 'caption': '📊 История'},
                            timeout=30)
                    except Exception as e:
                        logger.error(f"Ошибка отправки: {e}")

            elif text == '/backup':
                send_telegram("💾 Создаю бэкап...")
                result = send_auto_backup()
                send_telegram("✅ Отправлен!" if result else "❌ Ошибка")

            elif text == '/autobet':
                autobet_manager.enabled = not autobet_manager.enabled
                status = "включены" if autobet_manager.enabled else "выключены"
                send_telegram(f"💸 Автоставки {status}")

            elif text == '/autobet_state':
                st = autobet_manager.get_state()
                live_count = st.get('live_count', 0)
                msg = (f"💸 <b>АВТОСТАВКИ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"💰 Банк: <b>${st['bank']:.2f}</b>\n"
                       f"📈 Прибыль: <b>${st['total_profit']:+.2f}</b>\n"
                       f"💎 ROI: <b>{st['roi']}%</b> • 🎯 Winrate: <b>{st['winrate']}%</b>\n"
                       f"🎲 Ставок: {st['total_bets']} (✅ {st['wins']} / ❌ {st['losses']})\n"
                       f"⏳ Pending: {st['pending']}")
                if live_count > 0:
                    msg += f" (⚽ <b>{live_count} live</b>)"
                msg += "\n"
                if st.get('clv_count', 0) > 0:
                    msg += f"📊 CLV: <b>{st.get('avg_clv', 0):+.2f}%</b> ({st.get('clv_count', 0)} шт.)\n"
                send_telegram(msg)

            elif text == '/clv':
                updated = autobet_manager.compute_clv_for_settled()
                st = autobet_manager.get_state()
                send_telegram(f"📊 <b>CLV</b>\n\nОбновлено: {updated}\n"
                              f"Средний CLV: <b>{st.get('avg_clv', 0):+.2f}%</b>\n"
                              f"Замеров: {st.get('clv_count', 0)}")

            elif text == '/grid_search':
                send_telegram("🎯 Запускаю Grid Search...")

                def run_grid():
                    try:
                        result = strategy_simulator.grid_search(max_combinations=200, min_bets=5)
                        if not result['top']:
                            send_telegram("❌ Не удалось найти стратегию")
                    except Exception as e:
                        send_telegram(f"❌ Ошибка: {e}")

                Thread(target=run_grid, daemon=True).start()

            elif text == '/calibration':
                try:
                    msg = _build_calibration_message()
                    send_telegram(msg)
                except Exception as e:
                    send_telegram(f"❌ Ошибка калибровки: {e}")

            elif text == '/calibration_save':
                send_telegram("💾 Сохраняю снапшот калибровки...")
                try:
                    ok = save_calibration_snapshot()
                    if ok:
                        snaps = _load_calibration_snapshots()
                        send_telegram(f"✅ Снапшот сохранён. Всего: <b>{len(snaps)}</b>")
                    else:
                        send_telegram("❌ Не удалось сохранить")
                except Exception as e:
                    send_telegram(f"❌ Ошибка: {e}")

            elif text == '/status':
                report = bot_state.get_status_report()
                try:
                    oh_size = storage.get_odds_history_size()
                    x2_count = storage.x2_count()
                    report += (f"\n📊 Снимки: {oh_size['matches']} матчей, "
                               f"{oh_size['snapshots']} снимков, {oh_size['size_kb']} КБ")
                    report += f"\n🎯 X2-кандидатов: {x2_count}"
                    report += f"\n🌍 Geocoding: {len(_geo_cache)} городов"
                    report += f"\n📁 DATA: {DATA_DIR}"
                except Exception:
                    pass
                send_telegram(report)

            else:
                send_telegram("❌ Неизвестная команда. /help")
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook: {e}")
        send_error_to_telegram(f"Webhook error: {e}")
        return "ok", 200


# ============================================================
# ЗАПУСК ПОИСКА ИЗ ПРИЛОЖЕНИЯ
# ============================================================
@app.route('/api/trigger_search', methods=['POST'])
def api_trigger_search():
    """Запускает поиск матчей из веб-приложения."""
    global search_running, search_state

    if search_running:
        return jsonify({
            'status': 'already_running',
            'message': 'Поиск уже запущен',
        }), 200

    search_running = True
    search_state = {'start_time': datetime.now()}
    logger.info("🚀 [APP] Поиск запущен через веб-интерфейс")
    send_telegram("🚀 <b>Поиск запущен из приложения</b>")

    def run_search():
        global search_running, search_state
        try:
            matches = get_matches_with_factors()
            if matches:
                top = find_top_matches_with_tm25(matches)
                if top:
                    send_telegram(f"✅ <b>Найдено:</b> {len(top)}")
                else:
                    send_telegram("❌ Ничего не найдено")
            else:
                send_telegram("❌ Матчей нет")
        except Exception as e:
            logger.exception(f"❌ [APP] Ошибка поиска: {e}")
            send_telegram(f"❌ <b>Ошибка поиска:</b>\n<code>{str(e)[:300]}</code>")
        finally:
            search_running = False
            search_state = {}

    Thread(target=run_search, daemon=True).start()

    return jsonify({
        'status': 'ok',
        'message': 'Поиск запущен',
        'started_at': search_state['start_time'].isoformat(),
    }), 200


@app.route('/api/search_status', methods=['GET'])
def api_search_status():
    """Возвращает статус поиска."""
    global search_running, search_state
    if search_running and search_state.get('start_time'):
        elapsed = (datetime.now() - search_state['start_time']).total_seconds()
        return jsonify({
            'status': 'running',
            'started_at': search_state['start_time'].isoformat(),
            'elapsed_seconds': int(elapsed),
        }), 200
    return jsonify({
        'status': 'idle',
        'started_at': None,
        'elapsed_seconds': 0,
    }), 200
