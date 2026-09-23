# ============================================================
# app/analytics/calibration.py
# Модуль анализа калибровки модели
# v22.1 — Calibration Snapshots
# ============================================================
import os
import json
import time
import tempfile
from datetime import datetime
from collections import defaultdict

from flask import Blueprint, jsonify

from app.database.storage import storage
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# BLUEPRINT
# ============================================================
calibration_bp = Blueprint('calibration', __name__)


# ============================================================
# ПУТИ (зависимость от DATA_DIR)
# ============================================================
def _get_data_dir():
    """Определяет DATA_DIR (Render / локально / .)"""
    _RENDER_DISK = '/opt/render/project/src/data'
    if os.path.exists(_RENDER_DISK):
        return _RENDER_DISK
    if os.path.exists('/data'):
        return '/data'
    return '.'


def _get_calibration_file():
    return os.path.join(_get_data_dir(), 'calibration_snapshots.json')


# ============================================================
# ЗАГРУЗКА / СОХРАНЕНИЕ СНАПШОТОВ
# ============================================================
def _load_calibration_snapshots():
    """Загружает список снапшотов из JSON."""
    try:
        path = _get_calibration_file()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception as e:
        logger.error(f"_load_calibration_snapshots: {e}")
    return []


def _save_calibration_snapshots(snapshots):
    """Атомарно сохраняет список снапшотов."""
    try:
        path = _get_calibration_file()
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(path) or '.',
            suffix='.tmp'
        )
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.error(f"_save_calibration_snapshots: {e}")
        return False


def _cleanup_calibration_snapshots(snapshots):
    """
    Оставляет максимум 2 снапшота:
    - свежий — всегда
    - предыдущий — если ему < 24ч
    """
    now = time.time()
    cleaned = []
    for s in snapshots:
        saved_at = s.get('saved_at_ts', 0)
        cleaned.append((saved_at, s))
    cleaned.sort(key=lambda x: x[0], reverse=True)

    result = []
    for i, (saved_at, s) in enumerate(cleaned):
        if i == 0:
            result.append(s)
        else:
            age_hours = (now - saved_at) / 3600
            if age_hours < 24:
                result.append(s)
    return result


# ============================================================
# ПОСТРОЕНИЕ ДАННЫХ КАЛИБРОВКИ
# ============================================================
def _build_calibration_data():
    """
    Строит полный dict для снапшота калибровки.
    Использует историю ставок из storage.
    """
    history = storage.load_history()
    finished = [
        b for b in history
        if b.get('result') in ('win', 'loss') and b.get('prob', 0) > 0
    ]

    buckets_map = defaultdict(list)
    for b in finished:
        prob = b.get('prob', 0)
        bucket = int(prob // 5) * 5
        if bucket < 30:
            continue
        if bucket > 95:
            bucket = 95
        buckets_map[bucket].append(1 if b['result'] == 'win' else 0)

    buckets = []
    for bucket in sorted(buckets_map.keys()):
        results = buckets_map[bucket]
        n = len(results)
        if n < 3:
            continue
        actual = sum(results) / n * 100
        predicted = bucket + 2.5
        buckets.append({
            'range': f'{bucket}-{bucket+5}%',
            'count': n,
            'predicted': round(predicted, 1),
            'actual': round(actual, 1),
            'diff': round(actual - predicted, 1),
        })

    total_n = sum(b['count'] for b in buckets)
    if total_n > 0:
        overall_predicted = sum(
            b['predicted'] * b['count'] for b in buckets
        ) / total_n
        overall_actual = sum(
            b['actual'] * b['count'] for b in buckets
        ) / total_n
        overall_diff = overall_actual - overall_predicted
    else:
        overall_predicted = overall_actual = overall_diff = 0

    return {
        'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'saved_at_ts': time.time(),
        'total': len(finished),
        'buckets': buckets,
        'overall': {
            'count': total_n,
            'predicted': round(overall_predicted, 1),
            'actual': round(overall_actual, 1),
            'diff': round(overall_diff, 1),
            'calibration_factor': (
                round(overall_actual / overall_predicted, 3)
                if overall_predicted > 0 else 1.0
            ),
        },
    }


# ============================================================
# СОХРАНЕНИЕ СНАПШОТА
# ============================================================
def save_calibration_snapshot():
    """
    Сохраняет текущий снапшот.
    Оставляет максимум 2 (свежий + предыдущий если <24ч).
    """
    try:
        snapshots = _load_calibration_snapshots()
        new_snap = _build_calibration_data()
        snapshots.append(new_snap)
        snapshots = _cleanup_calibration_snapshots(snapshots)
        ok = _save_calibration_snapshots(snapshots)
        if ok:
            logger.info(
                f"📸 Калибровка сохранена: {new_snap['saved_at']} | "
                f"ставок={new_snap['total']} | снапшотов={len(snapshots)}"
            )
        return ok
    except Exception as e:
        logger.exception(f"save_calibration_snapshot: {e}")
        return False


def _cleanup_and_save_snapshots():
    """Периодическая очистка старых снапшотов (>24ч)."""
    try:
        snapshots = _load_calibration_snapshots()
        cleaned = _cleanup_calibration_snapshots(snapshots)
        if len(cleaned) != len(snapshots):
            _save_calibration_snapshots(cleaned)
            logger.info(
                f"🧹 Калибровка: очищено "
                f"{len(snapshots) - len(cleaned)} снапшотов"
            )
        return len(cleaned)
    except Exception as e:
        logger.error(f"_cleanup_and_save_snapshots: {e}")
        return 0

  # ============================================================
# API ENDPOINTS (Blueprint)
# ============================================================
@calibration_bp.route('/api/calibration', methods=['GET'])
def api_calibration():
    """Полный анализ калибровки модели."""
    try:
        history = storage.load_history()
        finished = [
            b for b in history
            if b.get('result') in ('win', 'loss') and b.get('prob', 0) > 0
        ]
        if not finished:
            return jsonify({
                'status': 'ok', 'total': 0,
                'message': 'Нет завершённых ставок с prob',
                'buckets': [], 'overall': {}, 'sources': [],
            })

        buckets_map = defaultdict(list)
        for b in finished:
            prob = b.get('prob', 0)
            bucket = int(prob // 5) * 5
            if bucket < 30:
                continue
            if bucket > 95:
                bucket = 95
            buckets_map[bucket].append(1 if b['result'] == 'win' else 0)

        buckets = []
        for bucket in sorted(buckets_map.keys()):
            results = buckets_map[bucket]
            n = len(results)
            if n < 3:
                continue
            actual = sum(results) / n * 100
            predicted = bucket + 2.5
            diff = actual - predicted
            buckets.append({
                'range': f'{bucket}-{bucket+5}%',
                'bucket_mid': predicted,
                'count': n,
                'predicted': round(predicted, 1),
                'actual': round(actual, 1),
                'diff': round(diff, 1),
                'wins': sum(results),
            })

        total_n = sum(b['count'] for b in buckets)
        if total_n > 0:
            overall_predicted = sum(
                b['predicted'] * b['count'] for b in buckets
            ) / total_n
            overall_actual = sum(
                b['actual'] * b['count'] for b in buckets
            ) / total_n
            overall_diff = overall_actual - overall_predicted
        else:
            overall_predicted = overall_actual = overall_diff = 0

        by_source = defaultdict(list)
        for b in finished:
            prob = b.get('prob', 0)
            if prob <= 0:
                continue
            src = b.get('source', '70_percent') or '70_percent'
            by_source[src].append(
                (prob, 1 if b['result'] == 'win' else 0)
            )

        sources = []
        for src, data in by_source.items():
            if len(data) < 5:
                continue
            avg_prob = sum(p for p, _ in data) / len(data)
            avg_actual = sum(a for _, a in data) / len(data) * 100
            sources.append({
                'source': src,
                'count': len(data),
                'avg_prob': round(avg_prob, 1),
                'avg_actual': round(avg_actual, 1),
                'diff': round(avg_actual - avg_prob, 1),
            })

        return jsonify({
            'status': 'ok',
            'total': len(finished),
            'buckets': buckets,
            'overall': {
                'count': total_n,
                'predicted': round(overall_predicted, 1),
                'actual': round(overall_actual, 1),
                'diff': round(overall_diff, 1),
                'calibration_factor': (
                    round(overall_actual / overall_predicted, 3)
                    if overall_predicted > 0 else 1.0
                ),
            },
            'sources': sources,
        })
    except Exception as e:
        logger.exception(f"api_calibration error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@calibration_bp.route('/api/calibration/snapshots', methods=['GET'])
def api_calibration_snapshots():
    """Возвращает все сохранённые снапшоты."""
    try:
        snapshots = _load_calibration_snapshots()
        snapshots = _cleanup_calibration_snapshots(snapshots)
        snapshots.sort(
            key=lambda x: x.get('saved_at_ts', 0),
            reverse=True
        )
        return jsonify({
            'status': 'ok',
            'count': len(snapshots),
            'snapshots': snapshots,
        })
    except Exception as e:
        logger.exception(f"api_calibration_snapshots: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@calibration_bp.route('/api/calibration/save', methods=['POST'])
def api_calibration_save():
    """Сохраняет текущий снапшот калибровки вручную."""
    try:
        ok = save_calibration_snapshot()
        return jsonify({'status': 'ok' if ok else 'error'})
    except Exception as e:
        logger.exception(f"api_calibration_save: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@calibration_bp.route('/api/calibration/snapshots/<int:idx>', methods=['DELETE'])
def api_calibration_snapshot_delete(idx):
    """Удаляет снапшот по индексу."""
    try:
        snapshots = _load_calibration_snapshots()
        snapshots.sort(
            key=lambda x: x.get('saved_at_ts', 0),
            reverse=True
        )
        if idx < 0 or idx >= len(snapshots):
            return jsonify({
                'status': 'error',
                'error': 'Index out of range'
            }), 404
        snapshots.pop(idx)
        _save_calibration_snapshots(snapshots)
        return jsonify({'status': 'ok', 'count': len(snapshots)})
    except Exception as e:
        logger.exception(f"api_calibration_snapshot_delete: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# TELEGRAM-СООБЩЕНИЕ (для команды /calibration)
# ============================================================
def _build_calibration_message():
    """Строит текст сообщения для Telegram-команды."""
    history = storage.load_history()
    finished = [
        b for b in history
        if b.get('result') in ('win', 'loss') and b.get('prob', 0) > 0
    ]

    if not finished:
        return "📭 Нет завершённых ставок с prob"

    buckets_map = defaultdict(list)
    for b in finished:
        prob = b.get('prob', 0)
        bucket = int(prob // 5) * 5
        if bucket < 30:
            continue
        if bucket > 95:
            bucket = 95
        buckets_map[bucket].append(1 if b['result'] == 'win' else 0)

    total_n = sum(len(v) for v in buckets_map.values())
    if total_n == 0:
        return "📭 Нет данных для бакетов"

    sum_pred = 0
    sum_act = 0
    for bucket, results in buckets_map.items():
        n = len(results)
        pred = bucket + 2.5
        act = sum(results) / n * 100
        sum_pred += pred * n
        sum_act += act * n

    overall_pred = sum_pred / total_n
    overall_act = sum_act / total_n
    diff = overall_act - overall_pred

    if abs(diff) < 3:
        emoji, verdict = "✅", "КАЛИБРОВКА ХОРОШАЯ"
    elif diff < -10:
        emoji, verdict = "🔴", "СИЛЬНО ЗАВЫШАЕТ"
    elif diff < -3:
        emoji, verdict = "🟡", "ЗАВЫШАЕТ"
    elif diff > 10:
        emoji, verdict = "🔵", "СИЛЬНО ЗАНИЖАЕТ"
    else:
        emoji, verdict = "🔵", "ЗАНИЖАЕТ"

    msg = (
        f"📊 <b>КАЛИБРОВКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} <b>{verdict}</b>\n\n"
        f"📊 Модель: <b>{overall_pred:.1f}%</b>\n"
        f"🎯 Реально: <b>{overall_act:.1f}%</b>\n"
        f"📈 Разница: <b>{diff:+.1f}%</b>\n"
        f"🎲 Ставок: {total_n}\n"
        f"⚙️ Коэффициент: <b>{overall_act/overall_pred:.3f}</b>\n\n"
        f"<b>По бакетам:</b>\n"
    )

    for bucket in sorted(buckets_map.keys()):
        results = buckets_map[bucket]
        n = len(results)
        if n < 3:
            continue
        actual = sum(results) / n * 100
        predicted = bucket + 2.5
        d = actual - predicted
        icon = "🟢" if abs(d) < 5 else "🟡" if abs(d) < 10 else "🔴"
        msg += (
            f"{icon} {bucket}-{bucket+5}%: "
            f"{predicted:.0f}% → {actual:.0f}% ({d:+.1f}%)\n"
        )

    return msg


# ============================================================
# ШЕДУЛЕР (регистрируется из main.py)
# ============================================================
def start_calibration_scheduler(scheduler):
    """
    Регистрирует задачи калибровки в переданном scheduler.
    Вызывать из main.py в schedule_auto_backup().
    """
    from app.utils.job_wrapper import safe_job  # см. примечание ниже

    scheduler.add_job(
        func=safe_job(save_calibration_snapshot, "save_calibration"),
        trigger='cron', day='1,15', hour=5, minute=0,
        id='save_calibration',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    scheduler.add_job(
        func=safe_job(_cleanup_and_save_snapshots, "cleanup_calibration_snaps"),
        trigger='cron', hour=6, minute=0,
        id='cleanup_calibration_snaps',
        replace_existing=True, misfire_grace_time=1800,
        coalesce=True, max_instances=1
    )
    logger.info("📅 Калибровка: шедулер зарегистрирован")
