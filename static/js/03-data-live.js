// ЗАГРУЗКА ДАННЫХ
// ============================================================
let dayMatchesData = [];
async function loadDayMatches() {
    try {
        const r = await fetch(API_BASE + '/api/day_matches?t=' + Date.now());
        if (!r.ok) return;
        const j = await r.json();
        if (j && Array.isArray(j.matches)) dayMatchesData = j.matches;
    } catch (e) {}
    try {
        const r2 = await fetch(API_BASE + '/api/notes?t=' + Date.now());
        if (r2.ok) { const j2 = await r2.json(); if (j2 && j2.notes) betNotes = j2.notes; }
    } catch (e) {}
    try {
        const r3 = await fetch(API_BASE + '/api/real_odds?t=' + Date.now());
        if (r3.ok) { const j3 = await r3.json(); if (j3 && j3.odds) realOdds = j3.odds; }
    } catch (e) {}
}

// ===== Избранное (на устройстве) и заметки (на сервере) =====
let betNotes = {};
let realOdds = {};
function renderRealOddsBox(m) {
    if (!m.fixture_id || m.type === 'daymatch' || !m.odds) return '';
    const key = 'f' + m.fixture_id;
    const val = realOdds[key] || '';
    return `<div class="dm-detail">
        <div class="dm-title">💵 Реальный кэф (по какому поставили)</div>
        <div style="display:flex;gap:8px;align-items:center;">
            <input type="number" id="realOddsInput" class="note-input" style="width:120px;" step="0.01" min="1.01" value="${val}" placeholder="${Number(m.odds).toFixed(2)}">
            <button class="btn btn-primary" data-key="${key}" onclick="saveRealOdds(this.dataset.key)" style="padding:8px 14px;font-size:12px;">Сохранить</button>
        </div>
        <div style="font-size:10px;color:var(--text-tertiary);margin-top:6px;">Пусто = удалить. Попадает в «Аналитику» как прибыль по реальным кэфам.</div>
    </div>`;
}
async function saveRealOdds(key) {
    const el = document.getElementById('realOddsInput');
    if (!el) return;
    const v = el.value.trim();
    try {
        const r = await fetch(API_BASE + '/api/real_odds', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({key: key, odds: v === '' ? null : parseFloat(v)})
        });
        const j = await r.json();
        if (!r.ok || j.status !== 'ok') throw new Error(j.error || r.status);
        if (v === '') delete realOdds[key]; else realOdds[key] = parseFloat(v);
        showNotification('💵 Сохранено', 'success');
    } catch (e) {
        showNotification('❌ ' + e.message, 'error');
    }
}
function itemKey(m) {
    return m.fixture_id ? 'f' + m.fixture_id : ((m.home || '') + '|' + (m.away || '') + '|' + String(m.date || m.match_time || '').split(' ')[0]);
}
function getFavs() {
    try { return new Set(JSON.parse(safeLSGet('favItems', '[]') || '[]')); } catch (e) { return new Set(); }
}
function isFav(m) { return getFavs().has(itemKey(m)); }
function toggleFav(ev, key) {
    if (ev) { ev.stopPropagation(); ev.preventDefault(); }
    const f = getFavs();
    if (f.has(key)) f.delete(key); else f.add(key);
    safeLSSet('favItems', JSON.stringify([...f]));
    haptic(8);
    renderMatchesPage();
}
async function saveNote(key) {
    const ta = document.getElementById('noteInput');
    if (!ta) return;
    const note = ta.value.trim();
    try {
        const r = await fetch(API_BASE + '/api/notes', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({key: key, note: note})
        });
        if (!r.ok) throw new Error('Сервер: ' + r.status);
        if (note) betNotes[key] = note; else delete betNotes[key];
        showNotification(note ? '📝 Заметка сохранена' : '🗑️ Заметка удалена', 'success');
        renderMatchesPage();
    } catch (e) {
        showNotification('❌ Не удалось сохранить: ' + e.message, 'error');
    }
}
function renderNoteBox(m) {
    const key = itemKey(m);
    const val = betNotes[key] || '';
    return `<div class="dm-detail">
        <div class="dm-title">📝 Заметка</div>
        <textarea id="noteInput" class="note-input" maxlength="500" rows="3" placeholder="Например: движение после новости о составе">${escapeHtml(val)}</textarea>
        <button class="btn btn-primary" data-key="${escapeHtml(key)}" onclick="saveNote(this.dataset.key)" style="margin-top:8px;padding:8px 16px;font-size:12px;">Сохранить</button>
    </div>`;
}

// ===== Состояние бота =====
async function loadBotHealth() {
    const box = document.getElementById('botHealthBox');
    if (!box) return;
    try {
        const r = await fetch(API_BASE + '/api/bot_health?t=' + Date.now());
        if (!r.ok) return;
        const h = await r.json();
        if (h.status !== 'ok') return;
        const ok = h.ok;
        const ago = h.minutes_ago == null ? 'нет данных' : (h.minutes_ago < 1 ? 'только что' : h.minutes_ago + ' мин назад');
        const q = h.quota && h.quota.remaining != null ? h.quota.remaining + (h.quota.limit ? ' / ' + h.quota.limit : '') : '—';
        box.innerHTML = `<div class="health-card ${ok ? 'ok' : 'warn'}">
            <div class="health-head">${ok ? '🟢 Бот работает' : '🟠 Нужно внимание'}</div>
            <div class="health-grid">
                <div><b>${ago}</b><span>последний снимок</span></div>
                <div><b>${h.snapshots_today}</b><span>снимков сегодня</span></div>
                <div><b>${h.fixtures_today}</b><span>матчей</span></div>
                <div><b>${q}</b><span>лимит API</span></div>
            </div>
            ${(h.warnings || []).map(w => `<div class="health-warn">⚠️ ${escapeHtml(w)}</div>`).join('')}
            ${(h.usage && h.usage.length) ? `<div style="font-size:11px;color:var(--text-tertiary);margin-top:8px;">Запросов к API с 00:00 UTC (после перезапуска сервера): <b>${h.usage_total}</b><br>${h.usage.map(u => escapeHtml(u[0]) + ': ' + u[1]).join('<br>')}</div>` : ''}
        </div>`;
    } catch (e) {}
}

// ===== Аналитика Line Movement =====
function fmtPct(v, plus) { return v == null ? '—' : (plus && v > 0 ? '+' : '') + v + '%'; }
function lmRow(name, a) {
    const clvCol = a.avg_clv == null ? '' : a.avg_clv > 0 ? 'var(--emerald-400)' : 'var(--red-400)';
    const roiCol = a.roi == null ? '' : a.roi > 0 ? 'var(--emerald-400)' : a.roi < 0 ? 'var(--red-400)' : '';
    return `<tr>
        <td>${escapeHtml(String(name))}${a.weak ? ' <span title="CLV < 0 после 30+ ставок">⚠️</span>' : ''}</td><td>${a.n}</td>
        <td>${a.wins}/${a.losses}</td><td>${fmtPct(a.winrate)}</td>
        <td style="color:${roiCol};">${fmtPct(a.roi, true)}</td>
        <td style="color:${clvCol};">${fmtPct(a.avg_clv, true)}</td></tr>`;
}
async function loadLmAnalytics() {
    const box = document.getElementById('lmAnalyticsBody');
    if (!box) return;
    try {
        const r = await fetch(API_BASE + '/api/lm_analytics?t=' + Date.now());
        if (!r.ok) throw new Error(r.status);
        const d = await r.json();
        if (d.status !== 'ok') throw new Error(d.error || 'error');
        const o = d.overall;
        const clvCol = o.avg_clv == null ? '' : o.avg_clv > 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        const head = '<thead><tr><th></th><th>Ст.</th><th>W/L</th><th>Win%</th><th>ROI</th><th>CLV</th></tr></thead>';
        box.innerHTML = `
            <div class="dm-summary" style="grid-template-columns:repeat(4,1fr);">
                <div class="dm-sum-item"><b>${o.n}</b><span>ставок</span></div>
                <div class="dm-sum-item"><b>${fmtPct(o.winrate)}</b><span>Win rate</span></div>
                <div class="dm-sum-item"><b>${fmtPct(o.roi, true)}</b><span>ROI</span></div>
                <div class="dm-sum-item"><b style="color:${clvCol};">${fmtPct(o.avg_clv, true)}</b><span>средний CLV</span></div>
            </div>
            <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:10px;">
                CLV — насколько кэф ставки выше последнего снимка перед матчем. Стабильно выше 0 = стратегия берёт цену лучше рынка. Доля ставок с CLV&gt;0: ${fmtPct(o.clv_pos)} (по ${o.clv_n} ставкам).
            </div>
            <div class="dm-summary" style="grid-template-columns:repeat(3,1fr);">
                <div class="dm-sum-item"><b style="color:var(--emerald-400);">${d.streaks.best_win}</b><span>макс. серия побед</span></div>
                <div class="dm-sum-item"><b style="color:var(--red-400);">${d.streaks.best_loss}</b><span>макс. серия поражений</span></div>
                <div class="dm-sum-item"><b>${d.streaks.current}${d.streaks.current_type === 'win' ? ' ✅' : d.streaks.current_type === 'loss' ? ' ❌' : ''}</b><span>текущая серия</span></div>
            </div>
            ${o.real && o.real.n ? `<div style="font-size:12px;margin-bottom:10px;padding:8px 10px;border-radius:12px;background:rgba(255,255,255,.06);">
                💵 По реальным кэфам (${o.real.n} ставок): <b style="color:${o.real.profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">${o.real.profit > 0 ? '+' : ''}${o.real.profit}</b>
                против ${o.real.model_profit > 0 ? '+' : ''}${o.real.model_profit} по кэфам бота • ROI ${fmtPct(o.real.roi, true)}</div>` : ''}
            <div class="dm-title">По лигам</div>
            <div class="dm-tablewrap"><table class="dm-table">${head}<tbody>${d.by_league.map(x => lmRow(x.league, x)).join('') || '<tr><td colspan="6">Нет данных</td></tr>'}</tbody></table></div>
            <div class="dm-title" style="margin-top:12px;">По размеру движения (от первого снимка до кэфа ставки)</div>
            <div class="dm-tablewrap"><table class="dm-table">${head}<tbody>${d.by_move.map(x => lmRow(x.bucket, x)).join('')}</tbody></table></div>`;
    } catch (e) {
        box.innerHTML = '<div style="font-size:12px;color:var(--text-tertiary);">Нет данных (обновите сервер)</div>';
    }
}
async function exportHistoryCsv() {
    try {
        const r = await fetch(API_BASE + '/api/export_history.csv');
        if (!r.ok) throw new Error('Сервер: ' + r.status);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'history.csv';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
        showNotification('❌ Экспорт: ' + e.message, 'error');
    }
}
const DM_FINISHED = ['FT', 'AET', 'PEN'];
const DM_LIVE = ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'];
const DM_HOT_PCT = 8;     // сильное движение
const DM_WARM_PCT = 5;    // заметное движение

const DM_HOUR_PCT = 4;    // резкое движение за час
// самое сильное изменение кэфа за последний час (со знаком) или 0
function dmMaxHour(d) {
    if (!d || !d.selections) return 0;
    let best = 0;
    Object.values(d.selections).forEach(x => {
        const c = Number(x.hour_change_pct);
        if (!isNaN(c) && x.hour_change_pct != null && Math.abs(c) > Math.abs(best)) best = c;
    });
    return best;
}
function dmHourBadge(d) {
    const h = dmMaxHour(d);
    if (Math.abs(h) < DM_HOUR_PCT) return '';
    return `<span class="dm-hour ${h < 0 ? 'drop' : 'rise'}">⚡ ${h > 0 ? '+' : ''}${h}% за 60 мин</span>`;
}
let dayFeed = [];
async function loadDayFeed() {
    try {
        const r = await fetch(API_BASE + '/api/day_feed?t=' + Date.now());
        if (!r.ok) return;
        const j = await r.json();
        if (j && Array.isArray(j.events)) dayFeed = j.events;
    } catch (e) {}
}

function dmMaxMove(d) {
    if (!d || !d.selections) return 0;
    let best = 0;
    Object.values(d.selections).forEach(x => {
        const c = Number(x.change_pct) || 0;
        if (Math.abs(c) > Math.abs(best)) best = c;
    });
    return best;
}
// 'live' | 'fin' | 'soon' для любого элемента списка
function dmState(it) {
    const st = it.dm && it.dm.status;
    if (st) {
        if (DM_FINISHED.includes(st)) return 'fin';
        if (DM_LIVE.includes(st)) return 'live';
        return 'soon';
    }
    if (it.result && it.result !== 'pending') return 'fin';
    return it.is_active ? 'soon' : 'live';
}
function dmTimeValue(it) {
    const m = String(it.date || '').match(/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})/);
    if (m) return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]).getTime();
    const t = new Date(it.date).getTime();
    return isNaN(t) ? 0 : t;
}
const DM_BETKEY = {'П1': '1', 'P1': '1', '1': '1', 'Х': 'X', 'X': 'X', 'Н': 'X', 'П2': '2', 'P2': '2', '2': '2', '1Х': '1X', '1X': '1X', 'Х2': 'X2', 'X2': 'X2'};
function dmBetSelection(label) {
    const t = String(label || '').toUpperCase().replace(/\s+/g, '');
    return DM_BETKEY[t] || null;
}

// автообновление вкладки «Матчи»: счёт, минуты, кэфы + уведомления о событиях
let _dmPrev = null;
async function dmAutoRefresh() {
    if (document.hidden) return;
    if (currentPage === 'today') {
        await loadDayMatches(); await loadDayFeed();
        dmNotifyChanges();
        renderTodayPage();
        return;
    }
    if (currentPage !== 'matches') return;
    const modal = document.getElementById('matchDetailModal');
    if (modal && modal.classList && (modal.classList.contains('show') || modal.classList.contains('active'))) return;
    await loadDayMatches();
    dmNotifyChanges();
    renderMatchesPage();
}
function dmNotifyChanges() {
    const cur = {};
    (dayMatchesData || []).forEach(d => { cur[d.fixture_id] = d; });
    if (_dmPrev) {
        Object.keys(cur).forEach(fid => {
            const n = cur[fid], o = _dmPrev[fid];
            if (!o) return;
            const nm = (n.home || '?') + ' — ' + (n.away || '?');
            if (!DM_FINISHED.includes(o.status) && DM_FINISHED.includes(n.status)) {
                showNotification('🏁 ' + nm + ' ' + n.home_goals + ':' + n.away_goals, 'success');
                try { haptic(20); } catch (e) {}
            } else if (Math.abs(dmMaxMove(n)) >= DM_HOT_PCT && Math.abs(dmMaxMove(o)) < DM_HOT_PCT) {
                showNotification('🔥 ' + nm + ': кэф ' + (dmMaxMove(n) > 0 ? '+' : '') + dmMaxMove(n) + '%', '');
            }
        });
    }
    _dmPrev = cur;
}
setInterval(dmAutoRefresh, 45000);

async function loadPageData(page) {
    if (isLoading) return;
    isLoading = true;
    try {
        const response = await fetch(API_BASE + '/api/all_data?t=' + Date.now());
        if (!response.ok) throw new Error('Сервер: ' + response.status);
        const data = await response.json();
        try {
            const mResp = await fetch(API_BASE + '/api/matches?t=' + Date.now());
            if (mResp.ok) {
                const matches = await mResp.json();
                if (Array.isArray(matches) && matches.length > 0) {
                    data.matches = matches;
                }
            }
        } catch (e) {}
        if (page === 'matches' || page === 'today') { await loadDayMatches(); }
        if (page === 'today') { await loadDayFeed(); }
        cachedData = data;
        updateLastUpdate();

        if (page === 'dashboard') {
            renderDashboard(data);
            loadDashboardAnomalies();
            loadBotHealth();
            loadStratBoard();
            loadDashboardAutobets();
        } else if (page === 'matches') {
            renderMatchesPage(data);
        } else if (page === 'today') {
            renderTodayPage();
        } else if (page === 'analytics') {
            renderAnalytics(data);
        }
        hideLoadingScreen();
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        showNotification('❌ Ошибка: ' + error.message, 'error');
        hideLoadingScreen();
    }
    isLoading = false;
}

function refreshData() {
    // ★ FIX #13: clearTimeout уже есть — оставляем
    if (refreshTimeout) clearTimeout(refreshTimeout);
    refreshTimeout = setTimeout(() => {
        cachedData = null;
        loadPageData(currentPage);
        if (currentPage === 'snapshots') loadSnapshots();
        if (currentPage === 'autobets') loadAutobets();
        if (currentPage === 'x2') renderX2Page();
        if (currentPage === 'live') loadLive();
        if (currentPage === 'calibration') loadCalibrationFull();
        if (currentPage === 'daily') loadDailyStats();
        showNotification('🔄 Обновление...', '');
    }, 250);
}

function updateLastUpdate() {
    const el = document.getElementById('lastUpdate');
    if (el) {
        el.textContent = 'Обновлено ' + new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }
}

// ============================================================
// LIVE
// ============================================================
async function loadLive(force = false) {
    const container = document.getElementById('liveList');
    if (!container) return;

    if (liveData.length === 0) {
        container.innerHTML = `
            <div class="skeleton" style="height:100px;"></div>
            <div class="skeleton" style="height:100px;"></div>
            <div class="skeleton" style="height:100px;"></div>
        `;
    }

    try {
        const resp = await fetch(API_BASE + '/api/live?t=' + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();

        if (data.status !== 'ok') {
            throw new Error(data.error || 'API error');
        }

        liveData = data.matches || [];
        // ★ FIX #3: убран двойной рендер
        renderLive();
        updateLiveLastUpdate();
        updateLiveNavBadge();

        if (force) showNotification('✅ Live обновлён', 'success');
    } catch (e) {
        console.error('loadLive error:', e);
        if (liveData.length === 0) {
            container.innerHTML = `
                <div class="no-data">
                    <div class="emoji">📭</div>
                    <div class="title">Ошибка загрузки</div>
                    <div class="desc">${e.message}</div>
                    <button class="btn btn-primary" onclick="loadLive(true)" style="margin-top:12px;">🔄 Повторить</button>
                </div>
            `;
        }
    }
}

function updateLiveLastUpdate() {
    const el = document.getElementById('liveLastUpdate');
    if (el) {
        const time = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        el.textContent = '🕐 ' + time;
    }
}

function updateLiveNavBadge() {
    const badge = document.getElementById('liveNavBadge');
    if (!badge) return;
    const liveCount = liveData.filter(m => m.is_live).length;
    if (liveCount > 0) {
        badge.textContent = liveCount;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}

function renderLive() {
    const container = document.getElementById('liveList');
    if (!container) return;

    const total = liveData.length;
    const liveCount = liveData.filter(m => m.is_live).length;
    const soonCount = liveData.filter(m => !m.is_live && !m.is_final).length;

    const elAll = document.getElementById('liveCountAll');
    const elLive = document.getElementById('liveCountLive');
    const elSoon = document.getElementById('liveCountSoon');
    if (elAll) elAll.textContent = total;
    if (elLive) elLive.textContent = liveCount;
    if (elSoon) elSoon.textContent = soonCount;

    if (total === 0) {
        container.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Нет активных матчей</div>
                <div class="desc">Матчи в ближайшие 2 часа появятся здесь</div>
            </div>
        `;
        return;
    }

    container.innerHTML = liveData.map(m => renderLiveCard(m)).join('');
}

function renderLiveCard(m) {
    const isLive = m.is_live;
    const isFinal = m.is_final;
    const minutes = m.minutes_to_match;
    const cls = isLive ? 'is-live' : (isFinal ? '' : 'is-soon');

    let timeInfo = '';
    if (isLive) {
        const minStr = m.minute ? `${m.minute}'` : '';
        timeInfo = `<span style="color:var(--red-400);font-weight:700;">🔴 LIVE ${minStr}</span>`;
    } else if (isFinal) {
        timeInfo = `<span style="color:var(--emerald-400);">Завершён</span>`;
    } else if (minutes >= 0) {
        if (minutes < 60) {
            timeInfo = `через <b>${Math.round(minutes)} мин</b>`;
        } else {
            const h = Math.floor(minutes / 60);
            const mn = Math.round(minutes % 60);
            timeInfo = `через <b>${h}ч ${mn}м</b>`;
        }
    } else {
        const liveMin = Math.max(1, Math.round(-minutes));
        timeInfo = `<span style="color:var(--red-400);">🔴 идёт ${liveMin}-я минута</span>`;
    }

    let statusBadge = '';
    if (isLive) {
        statusBadge = `<span class="live-badge-live">⚽ LIVE</span>`;
    } else if (isFinal) {
        statusBadge = `<span class="live-badge-final">✅ Завершён</span>`;
    } else if (minutes < 0) {
        statusBadge = `<span class="live-badge-live">⚽ LIVE</span>`;
    } else {
        statusBadge = `<span class="live-badge-soon">⏳ Скоро</span>`;
    }

    const bb = m.best_bet || {};
    const hasBet = (bb.prob || 0) > 0 && bb.label && bb.label !== '1X2' && bb.label !== '—';
    const betLabel = hasBet ? (bb.label || '—') : 'Нет ставки';
    const betOdds = hasBet && bb.odds ? Number(bb.odds || 0).toFixed(2) : '—';
    const betEv = hasBet && bb.ev ? (Number(bb.ev) >= 0 ? '+' : '') + Number(bb.ev).toFixed(1) + '%' : '—';
    const betProb = hasBet && bb.prob ? Number(bb.prob).toFixed(0) + '%' : '—';

    const trend = m.odds_trend || 0;
    const trendEmoji = trend > 1 ? '📈' : trend < -1 ? '📉' : '';
    const trendStr = trend !== 0 ? ` (${trend > 0 ? '+' : ''}${trend.toFixed(1)}%)` : '';

    const countryHtml = m.country
        ? ` • ${m.country_flag || ''} <span style="color:var(--text-secondary);">${escapeHtml(m.country)}</span>`
        : '';

    // ★ УЛУЧШЕНИЕ 2: Таймлайн для Live-карточек
    let scoreHtml = '';
    if (isLive && m.score) {
        const minuteStr = m.minute ? ` <span style="font-size:11px;color:var(--red-400);font-weight:700;">${m.minute}'</span>` : '';
        let matchProgress = 0;
        if (m.minute) {
            matchProgress = Math.min((m.minute / 95) * 100, 100);
        }
        scoreHtml = `
            <div style="display:flex;align-items:center;gap:8px;margin:6px 0 0;">
                <span class="live-score">${escapeHtml(m.score)}</span>
                ${minuteStr}
            </div>
            <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                <div style="flex: 1; height: 4px; background: rgba(255,255,255,0.1); border-radius: 999px; overflow: hidden;">
                    <div style="height: 100%; width: ${matchProgress}%; background: linear-gradient(90deg, var(--red-400), var(--red-500)); border-radius: 999px; transition: width 0.5s ease;"></div>
                </div>
                <span style="font-size: 9px; color: var(--text-tertiary); font-weight: 600;">90'</span>
            </div>
        `;
    } else if (isFinal && m.score) {
        scoreHtml = `
            <div style="display:flex;align-items:center;gap:8px;margin:6px 0 0;">
                <span class="live-score" style="color:var(--emerald-400);">${escapeHtml(m.score)}</span>
            </div>
        `;
    }

    const sparklineHtml = renderSparkline(m.sparkline || []);

    return `
        <div class="live-card ${cls}">
            <div class="bet-header">
                <div style="flex:1;min-width:0;">
                    <div class="bet-match">${escapeHtml(m.home)} vs ${escapeHtml(m.away)}</div>
                    <div class="bet-league">🏆 ${escapeHtml(m.league)}${countryHtml}</div>
                    <div class="bet-time">
                        📅 ${escapeHtml(m.match_time)} ${timeInfo ? '• ' + timeInfo : ''}
                    </div>
                    ${scoreHtml}
                </div>
                <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                    ${statusBadge}
                </div>
            </div>
            <div class="bet-stats" style="margin-top:10px;">
                <div class="bet-stat">
                    <span class="stat-label">Ставка</span>
                    <span class="stat-value">${escapeHtml(betLabel)}</span>
                </div>
                <div class="bet-stat">
                    <span class="stat-label">Кэф</span>
                    <span class="stat-value">${betOdds}${trendEmoji}${trendStr}</span>
                </div>
                <div class="bet-stat">
                    <span class="stat-label">Prob / EV</span>
                    <span class="stat-value gold">${betProb} · ${betEv}</span>
                </div>
            </div>
            ${sparklineHtml ? `
                <div style="font-size:10px;color:var(--text-tertiary);margin-top:6px;padding-top:6px;border-top:1px dashed var(--border-color);">
                    💰 Движение: <b style="color:var(--gold-400);">${escapeHtml(m.sparkline_label || '—')}</b>
                    ${m.sparkline_change ? `<span style="color:var(--emerald-400);">+${m.sparkline_change}%</span>` : ''}
                </div>
            ` : ''}
            ${sparklineHtml}
        </div>
    `;
}

function startLiveRefresh() {
    if (liveRefreshInterval) clearInterval(liveRefreshInterval);
    liveRefreshInterval = setInterval(() => {
        if (document.visibilityState === 'visible' && currentPage === 'live') {
            loadLive();
        }
    }, LIVE_REFRESH_MS);
}

setInterval(async () => {
    if (document.visibilityState === 'visible' && currentPage !== 'live') {
        try {
            const resp = await fetch(API_BASE + '/api/live?t=' + Date.now());
            if (resp.ok) {
                const data = await resp.json();
                if (data.status === 'ok') {
                    const liveCount = (data.matches || []).filter(m => m.is_live).length;
                    const badge = document.getElementById('liveNavBadge');
                    if (badge) {
                        if (liveCount > 0) {
                            badge.textContent = liveCount;
                            badge.style.display = 'flex';
                        } else {
                            badge.style.display = 'none';
                        }
                    }
                }
            }
        } catch (e) {}
    }
}, 120000);

// ============================================================
