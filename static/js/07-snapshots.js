// СТАТИСТИКА АНОМАЛИЙ
// ============================================================
async function loadAnomalyStats() {
    const container = document.getElementById('anomalyStatsContent');
    if (!container) return;

    container.innerHTML = `
        <div class="skeleton" style="width:80%"></div>
        <div class="skeleton" style="width:60%"></div>
    `;

    try {
        const period = document.getElementById('anomalyStatsPeriod')?.value || 30;
        const resp = await fetch(API_BASE + `/api/snapshot_anomalies/stats?days=${period}&t=` + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (data.status !== 'ok') throw new Error(data.error || 'API error');

        renderAnomalyStats(data);
    } catch (e) {
        console.error('loadAnomalyStats:', e);
        container.innerHTML = `
            <div style="padding:12px;color:var(--red-400);font-size:12px;">
                ❌ Ошибка: ${e.message}
            </div>
        `;
    }
}

function renderAnomalyStats(data) {
    const container = document.getElementById('anomalyStatsContent');
    if (!container) return;

    const total = data.total_anomalies || 0;
    const correct = data.correct_anomalies || 0;
    const wrong = data.wrong_anomalies || 0;
    const unknown = data.unknown_anomalies || 0;
    const hitRate = data.hit_rate || 0;
    const avgGrowth = data.avg_growth || 0;

    let html = `
        <div class="stats-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:12px;">
            <div class="stat-card">
                <div class="value">${data.total_matches || 0}</div>
                <div class="label">🎯 Матчей</div>
            </div>
            <div class="stat-card">
                <div class="value">${data.total_snapshots || 0}</div>
                <div class="label">📸 Снимков</div>
            </div>
            <div class="stat-card">
                <div class="value gold">${total}</div>
                <div class="label">🎯 Аномалий</div>
            </div>
            <div class="stat-card">
                <div class="value ${hitRate >= 55 ? 'green' : 'red'}">${hitRate}%</div>
                <div class="label">✅ Hit Rate</div>
            </div>
        </div>
    `;

    html += `
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:10px 0;border-bottom:1px solid var(--border-color);">
            <div style="text-align:center;">
                <div style="font-size:16px;font-weight:800;color:var(--emerald-400);">${correct}</div>
                <div style="font-size:9px;color:var(--text-tertiary);text-transform:uppercase;">✅ Сбылось</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:16px;font-weight:800;color:var(--red-400);">${wrong}</div>
                <div style="font-size:9px;color:var(--text-tertiary);text-transform:uppercase;">❌ Не сбылось</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:16px;font-weight:800;color:var(--text-tertiary);">${unknown}</div>
                <div style="font-size:9px;color:var(--text-tertiary);text-transform:uppercase;">⏳ Ждём</div>
            </div>
        </div>
    `;

    html += `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;font-size:12px;">
            <span style="color:var(--text-tertiary);">Средний рост кэфа:</span>
            <span style="font-weight:700;color:var(--gold-400);">+${avgGrowth}%</span>
        </div>
    `;

    if (data.top_good && data.top_good.length > 0) {
        html += `
            <div style="font-size:11px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-top:12px;margin-bottom:6px;">
                🏆 ТОП успешных
            </div>
        `;
        html += data.top_good.map(a => {
            const selLabel = a.selection === '1' ? '1X' : a.selection;
            return `
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:11px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-weight:600;">${escapeHtml(a.home || '?')} vs ${escapeHtml(a.away || '?')}</div>
                        <div style="color:var(--text-tertiary);font-size:10px;">${escapeHtml(a.league || '')} • ${selLabel}: ${a.first_odds.toFixed(2)} → ${a.max_odds.toFixed(2)}</div>
                    </div>
                    <div style="font-weight:700;color:var(--emerald-400);white-space:nowrap;padding-left:8px;">+${a.anomaly_pct}%</div>
                </div>
            `;
        }).join('');
    }

    if (data.top_bad && data.top_bad.length > 0) {
        html += `
            <div style="font-size:11px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-top:12px;margin-bottom:6px;">
                📉 ТОП провальных
            </div>
        `;
        html += data.top_bad.map(a => {
            const selLabel = a.selection === '1' ? '1X' : a.selection;
            return `
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:11px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-weight:600;">${escapeHtml(a.home || '?')} vs ${escapeHtml(a.away || '?')}</div>
                        <div style="color:var(--text-tertiary);font-size:10px;">${escapeHtml(a.league || '')} • ${selLabel}: ${a.first_odds.toFixed(2)} → ${a.max_odds.toFixed(2)}</div>
                    </div>
                    <div style="font-weight:700;color:var(--red-400);white-space:nowrap;padding-left:8px;">+${a.anomaly_pct}%</div>
                </div>
            `;
        }).join('');
    }

    if (total === 0) {
        html += `
            <div class="no-data" style="padding:20px;">
                <div class="emoji">📭</div>
                <div class="desc">Пока нет аномалий за этот период</div>
            </div>
        `;
    }

    container.innerHTML = html;
}

// ============================================================
// SNAPSHOTS
// ============================================================
let snapshotQuery = '';
let _snapSearchTimer = null;
function onSnapshotSearch() {
    clearTimeout(_snapSearchTimer);
    _snapSearchTimer = setTimeout(() => {
        const el = document.getElementById('snapshotSearch');
        snapshotQuery = el ? el.value.trim() : '';
        loadSnapshots();
    }, 400);
}

async function loadSnapshots() {
    const container = document.getElementById('snapshotsList');
    const countEl = document.getElementById('snapshotsCount');
    if (!container) return;

    container.innerHTML = `
        <div class="skeleton" style="height:100px;"></div>
        <div class="skeleton" style="height:100px;"></div>
        <div class="skeleton" style="height:100px;"></div>
    `;
    countEl.textContent = 'Загрузка...';

    loadAnomalyStats();

    try {
        // Все = всё, что хранится (30 дней); За 7 дней и Сегодня/Аномалии = последние 7 дней
        const snapDays = (snapshotFilter === 'all') ? 30 : 7;
        let url = API_BASE + '/api/snapshots?days=' + snapDays + '&limit=200';
        if (snapshotFilter === 'anomaly') url += '&only_anomaly=true';
        if (snapshotFilter === 'today') url += '&only_today=true';
        if (snapshotQuery) url += '&q=' + encodeURIComponent(snapshotQuery);
        const resp = await fetch(url + '&t=' + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        snapshotsData = data.matches || [];
        renderSnapshots();

        if (window._snapFastRefresh) clearTimeout(window._snapFastRefresh);
        const hasSoon = snapshotsData.some(s => {
            if (!s.match_time || s.match_time === '?') return false;
            try {
                const parts = s.match_time.split(' ');
                if (parts.length < 2) return false;
                const [d, m, y] = parts[0].split('.').map(Number);
                const [hh, mm] = parts[1].split(':').map(Number);
                const dt = new Date(y, m - 1, d, hh, mm);
                const mins = Math.round((dt - new Date()) / 60000);
                return mins > 0 && mins <= 30;
            } catch { return false; }
        });
        if (hasSoon && currentPage === 'snapshots') {
            window._snapFastRefresh = setTimeout(() => {
                if (currentPage === 'snapshots') loadSnapshots();
            }, 30000);
        }
    } catch (e) {
        console.error('Ошибка загрузки снимков:', e);
        container.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Ошибка загрузки</div>
                <div class="desc">${e.message}</div>
                <button class="btn btn-primary" onclick="loadSnapshots()" style="margin-top:12px;">🔄 Повторить</button>
            </div>
        `;
        countEl.textContent = 'Ошибка';
    }
}

function refreshSnapshots() {
    loadSnapshots();
    showNotification('🔄 Обновление снимков...', '');
}

function setSnapshotFilter(filter) {
    snapshotFilter = filter;
    document.querySelectorAll('.filter-btn[data-snapfilter]').forEach(b => {
        b.classList.toggle('active', b.dataset.snapfilter === filter);
    });
    haptic(6);
    loadSnapshots();
}

function setSnapshotSort(sort) {
    snapshotSort = sort;
    document.querySelectorAll('.filter-btn[data-snapsort]').forEach(b => {
        b.classList.toggle('active', b.dataset.snapsort === sort);
    });
    haptic(6);
    renderSnapshots();
}

function filterSnapshots() {
    snapshotsSearchQuery = document.getElementById('snapshotsSearch').value.toLowerCase();
    renderSnapshots();
}

function renderSnapshots() {
    const container = document.getElementById('snapshotsList');
    const countEl = document.getElementById('snapshotsCount');
    if (!container) return;

    let filtered = [...snapshotsData];

    if (snapshotsSearchQuery) {
        const q = snapshotsSearchQuery;
        filtered = filtered.filter(s =>
            (s.home && s.home.toLowerCase().includes(q)) ||
            (s.away && s.away.toLowerCase().includes(q)) ||
            (s.league && s.league.toLowerCase().includes(q))
        );
    }

    if (snapshotSort === 'recent') {
        filtered.sort((a, b) => (b.last_time || '').localeCompare(a.last_time || ''));
    } else if (snapshotSort === 'count') {
        filtered.sort((a, b) => (b.snapshot_count || 0) - (a.snapshot_count || 0));
    } else if (snapshotSort === 'anomaly') {
        filtered.sort((a, b) => {
            const aMax = a.anomalies && a.anomalies.length ? Math.max(...a.anomalies.map(x => Math.abs(x.trend))) : 0;
            const bMax = b.anomalies && b.anomalies.length ? Math.max(...b.anomalies.map(x => Math.abs(x.trend))) : 0;
            return bMax - aMax;
        });
    }

    countEl.textContent = `${filtered.length} матчей со снимками`;

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Нет снимков</div>
                <div class="desc">Снимки делаются каждые 30 минут для матчей 6 лиг Line Movement</div>
            </div>
        `;
        return;
    }

    container.innerHTML = filtered.map(s => renderSnapshotCard(s)).join('');
}

function renderSnapshotCard(s) {
    const hasAnomaly = s.anomalies && s.anomalies.length > 0;
    const first = s.first || {};
    const last = s.last || {};

    let lastTimeStr = '';
    try {
        if (s.last_time) {
            const dt = new Date(s.last_time);
            lastTimeStr = dt.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
        }
    } catch (e) {}

    const trendHtml = ['1', 'X', '2'].map(sel => {
        const f = first[sel] || 0;
        const l = last[sel] || 0;
        let pct = 0;
        if (f > 0 && l > 0) pct = ((l / f) - 1) * 100;
        const pctClass = pct > 0.5 ? 'up' : pct < -0.5 ? 'down' : 'flat';
        const pctStr = pct !== 0 ? (pct > 0 ? '+' : '') + pct.toFixed(1) + '%' : '=';
        const selLabel = sel === '1' ? '1X' : sel;
        return `
            <div class="snapshot-trend">
                <span class="trend-label">${selLabel}</span>
                <span class="trend-values">${f > 0 ? f.toFixed(2) : '—'}</span>
                <span class="trend-values">→ ${l > 0 ? l.toFixed(2) : '—'}</span>
                <span class="trend-pct ${pctClass}">${pctStr}</span>
            </div>
        `;
    }).join('');

    let anomalyHtml = '';
    if (hasAnomaly) {
        anomalyHtml = s.anomalies.slice(0, 2).map(a => {
            const selLabel = a.selection === '1' ? '1X' : a.selection;
            const isUp = a.trend > 0;
            return `<span style="display:inline-block;margin-right:6px;font-size:10px;color:var(--gold-400);">
                🎯 ${selLabel}: ${a.first} → ${a.last} (${isUp ? '+' : ''}${a.trend}%)
            </span>`;
        }).join('');
    }

    return `
        <div class="snapshot-card ${hasAnomaly ? 'has-anomaly' : ''}" onclick="showSnapshotChart(${s.fixture_id})">
            <div class="snapshot-header">
                <div style="flex:1;min-width:0;">
                    <div class="snapshot-match">${escapeHtml(s.home)} vs ${escapeHtml(s.away)}</div>
                    <div class="snapshot-meta">🏆 ${escapeHtml(s.league || '—')}</div>
                    <div class="snapshot-meta">📅 ${escapeHtml(s.match_time || '—')}</div>
                    <div class="snapshot-meta">📸 ${s.snapshot_count} снимков • обновлено ${lastTimeStr}</div>
                </div>
                <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                    ${hasAnomaly ? `<div class="snapshot-badge anomaly">🎯 Аномалия</div>` : `<div class="snapshot-badge">📸 ${s.snapshot_count}</div>`}
                </div>
            </div>
            <div class="snapshot-trends">${trendHtml}</div>
            ${anomalyHtml ? `<div style="padding-top:8px;margin-top:8px;border-top:1px solid var(--border-color);">${anomalyHtml}</div>` : ''}
        </div>
    `;
}

// ============================================================
// БЛОК РЕКОМЕНДАЦИИ В МОДАЛКЕ СНИМКА
// ★ FIX #7: Number(bet.stake || 0).toFixed(2)
// ============================================================
function renderSnapshotBetBlock(bet) {
    const container = document.getElementById('snapshotBetBlock');
    if (!container) return;

    if (!bet) {
        container.innerHTML = '';
        return;
    }

    const m = bet.minutes_to_match;
    let timeIcon = '⏰';
    let timeText = '';
    if (m > 0 && m <= 30) {
        timeText = `Матч через ${m} мин`;
    } else if (m >= -120 && m <= 0) {
        timeIcon = '🔴';
        timeText = `Матч идёт (~${-m} мин)`;
    } else {
        container.innerHTML = '';
        return;
    }

    const srcMap = {
        'value':         '💎 VALUE',
        'line_movement': '📈 LINE MOVEMENT',
        'btts':          '⚽ BTTS',
        'tm25_premium':  '🔥 ТМ 2.5 PREMIUM',
        'tm25_standard': '⭐ ТМ 2.5',
        '70_percent':    '🎯 70%+',
    };
    const srcLabel = srcMap[bet.source] || '🎯 70%+';

    const ev = bet.ev || 0;
    const evColor = ev >= 15 ? 'var(--emerald-400)'
                  : ev >= 5  ? 'var(--gold-400)'
                  : 'var(--text-secondary)';

    let movementHtml = '';
    if (bet.source === 'line_movement' && bet.movement_pct != null) {
        const arrow = bet.movement_pct < 0 ? '📉' : '📈';
        movementHtml = `
            <div style="display:flex;justify-content:space-between;padding:8px 0;
                        border-bottom:1px solid rgba(167,139,250,0.15);">
                <span style="color:var(--text-tertiary);font-size:11px;">Движение кэфа</span>
                <span style="color:#a78bfa;font-weight:800;font-size:13px;">
                    ${arrow} ${bet.movement_pct >= 0 ? '+' : ''}${bet.movement_pct}%
                    ${bet.movement_hours ? `<span style="font-size:10px;color:var(--text-tertiary);"> за ${bet.movement_hours}ч</span>` : ''}
                </span>
            </div>
        `;
        if (bet.old_odds) {
            movementHtml += `
                <div style="display:flex;justify-content:space-between;padding:8px 0;
                            border-bottom:1px solid rgba(167,139,250,0.15);">
                    <span style="color:var(--text-tertiary);font-size:11px;">Кэф</span>
                    <span style="font-size:13px;">
                        <span style="color:var(--text-tertiary);">${bet.old_odds}</span>
                        <span style="color:var(--text-tertiary);"> → </span>
                        <span style="color:#a78bfa;font-weight:800;">${bet.odds}</span>
                    </span>
                </div>
            `;
        }
    }

    const llmHtml = bet.llm_reason
        ? `<div style="margin-top:10px;padding:8px 10px;background:rgba(96,165,250,0.08);
                       border-left:3px solid var(--blue-400);border-radius:6px;
                       font-size:11px;color:var(--text-secondary);font-style:italic;">
             💡 ${escapeHtml(bet.llm_reason)}
           </div>`
        : '';

    container.innerHTML = `
        <div style="margin-bottom:14px;padding:14px;
                    background:linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(16,185,129,0.02) 100%);
                    border:1px solid rgba(16,185,129,0.3);border-radius:12px;
                    box-shadow:0 0 20px rgba(16,185,129,0.08);">

            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                <span style="font-size:11px;color:var(--emerald-400);font-weight:800;
                             text-transform:uppercase;letter-spacing:1px;">
                    ${timeIcon} ${timeText}
                </span>
                <span style="font-size:10px;color:var(--text-tertiary);font-weight:600;">
                    ${srcLabel}
                </span>
            </div>

            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
                <div style="flex:1;min-width:0;">
                    <div style="font-size:22px;font-weight:800;color:var(--text-primary);
                                letter-spacing:-0.5px;">
                        ${escapeHtml(bet.label)}
                    </div>
                    <div style="font-size:12px;color:var(--text-tertiary);margin-top:4px;">
                        📊 Prob: <b style="color:var(--text-primary);">${Number(bet.prob || 0).toFixed(0)}%</b>
                        &nbsp;•&nbsp;
                        EV: <b style="color:${evColor};">${ev >= 0 ? '+' : ''}${Number(ev).toFixed(1)}%</b>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:32px;font-weight:800;color:var(--emerald-400);
                                font-variant-numeric:tabular-nums;line-height:1;">
                        ${Number(bet.odds || 0).toFixed(2)}
                    </div>
                    ${bet.stake ? `<div style="font-size:11px;color:var(--text-tertiary);margin-top:4px;">
                        💵 $${Number(bet.stake || 0).toFixed(2)}
                    </div>` : ''}
                </div>
            </div>

            ${movementHtml ? `<div style="margin-top:10px;padding-top:4px;">${movementHtml}</div>` : ''}

            ${bet.bookmaker && bet.bookmaker !== '—' ? `
                <div style="display:flex;justify-content:space-between;padding:8px 0;
                            border-top:1px solid rgba(16,185,129,0.15);margin-top:6px;">
                    <span style="color:var(--text-tertiary);font-size:11px;">Букмекер</span>
                    <span style="color:var(--text-primary);font-size:11px;font-weight:600;">
                        ${escapeHtml(bet.bookmaker)}
                    </span>
                </div>
            ` : ''}

            ${llmHtml}
        </div>
    `;
}

// ============================================================
// SNAPSHOT CHART MODAL
// ============================================================
async function showSnapshotChart(fixtureId) {
    const modal = document.getElementById('snapshotChartModal');
    const title = document.getElementById('snapshotChartTitle');
    const info = document.getElementById('snapshotChartInfo');
    const statsEl = document.getElementById('snapshotChartStats');
    currentSnapshotFixture = fixtureId;

    modal.classList.add('active');
    title.textContent = '📈 Движение кэфов';
    info.textContent = 'Загрузка...';
    statsEl.innerHTML = '';

    const betBlock = document.getElementById('snapshotBetBlock');
    if (betBlock) betBlock.innerHTML = '';

    try {
        const resp = await fetch(API_BASE + `/api/snapshots/${fixtureId}?t=` + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (data.status !== 'ok') throw new Error(data.error || 'Unknown error');

        const m = data.match || {};
        title.textContent = `📈 ${m.home || '?'} vs ${m.away || '?'}`;
        info.innerHTML = `
            🏆 ${escapeHtml(m.league || '—')} &nbsp;•&nbsp;
            📅 ${escapeHtml(m.match_time || '—')} &nbsp;•&nbsp;
            📸 ${data.history.length} снимков
        `;

        renderSnapshotBetBlock(data.bet);

        renderSnapshotChart(data.history);
        renderSnapshotStats(data.history);
    } catch (e) {
        console.error('Ошибка графика снимков:', e);
        info.textContent = '❌ Ошибка загрузки: ' + e.message;
    }
}

function renderSnapshotChart(history) {
    const ctx = document.getElementById('snapshotChart');
    if (!ctx || !history || history.length === 0) return;
    if (snapshotChartInstance) snapshotChartInstance.destroy();

    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    const textColor = isLight ? 'rgba(6, 78, 59, 0.6)' : 'rgba(236, 253, 245, 0.6)';
    const gridColor = isLight ? 'rgba(6, 78, 59, 0.06)' : 'rgba(52, 211, 153, 0.05)';

    const labels = history.map(h => {
        try {
            const dt = new Date(h.created_at);
            return dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        } catch { return '?'; }
    });

    const datasets = [
        { label: '1X', data: history.map(h => h.odds['1'] || null),
          borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.08)',
          tension: 0.3, pointRadius: 3, pointHoverRadius: 6, spanGaps: true },
        { label: 'X', data: history.map(h => h.odds['X'] || null),
          borderColor: '#fbbf24', backgroundColor: 'rgba(251, 191, 36, 0.08)',
          tension: 0.3, pointRadius: 3, pointHoverRadius: 6, spanGaps: true },
        { label: '2', data: history.map(h => h.odds['2'] || null),
          borderColor: '#f87171', backgroundColor: 'rgba(248, 113, 113, 0.08)',
          tension: 0.3, pointRadius: 3, pointHoverRadius: 6, spanGaps: true }
    ];

    const has1X = history.some(h => h.odds['1X'] > 0);
    const hasX2 = history.some(h => h.odds['X2'] > 0);
    if (has1X) {
        datasets.push({
            label: 'DC 1X', data: history.map(h => h.odds['1X'] || null),
            borderColor: '#34d399', backgroundColor: 'rgba(52, 211, 153, 0.05)',
            borderDash: [5, 3], tension: 0.3, pointRadius: 2, pointHoverRadius: 5, spanGaps: true
        });
    }
    if (hasX2) {
        datasets.push({
            label: 'DC X2', data: history.map(h => h.odds['X2'] || null),
            borderColor: '#60a5fa', backgroundColor: 'rgba(96, 165, 250, 0.05)',
            borderDash: [5, 3], tension: 0.3, pointRadius: 2, pointHoverRadius: 5, spanGaps: true
        });
    }

    snapshotChartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: textColor, font: { size: 10 } } } },
            scales: {
                x: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } },
                y: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } }
            }
        }
    });
}

function renderSnapshotStats(history) {
    const statsEl = document.getElementById('snapshotChartStats');
    if (!statsEl || !history || history.length === 0) return;

    const stats = {};
    ['1', 'X', '2', '1X', 'X2'].forEach(sel => {
        const values = history.map(h => h.odds[sel]).filter(v => v > 0);
        if (values.length === 0) return;
        stats[sel] = {
            first: values[0], last: values[values.length - 1],
            max: Math.max(...values), min: Math.min(...values),
            pct: ((values[values.length - 1] / values[0]) - 1) * 100
        };
    });

    const rows = ['1', 'X', '2', '1X', 'X2'].map(sel => {
        if (!stats[sel]) return '';
        const s = stats[sel];
        const selLabel = sel === '1' ? '1X' : sel;
        const pctClass = s.pct > 0.5 ? 'up' : s.pct < -0.5 ? 'down' : 'flat';
        const pctStr = s.pct !== 0 ? (s.pct > 0 ? '+' : '') + s.pct.toFixed(1) + '%' : '=';
        const isDC = sel === '1X' || sel === 'X2';
        const color = isDC ? 'var(--blue-400)' : 'var(--emerald-400)';
        return `
            <div style="display:grid;grid-template-columns:60px 1fr 1fr 1fr 80px;gap:8px;padding:8px 0;border-bottom:1px solid var(--border-color);font-size:12px;align-items:center;">
                <strong style="color:${color};">${selLabel}</strong>
                <span style="color:var(--text-tertiary);">Старт: <strong style="color:var(--text-primary);">${s.first.toFixed(2)}</strong></span>
                <span style="color:var(--text-tertiary);">Макс: <strong style="color:var(--gold-400);">${s.max.toFixed(2)}</strong></span>
                <span style="color:var(--text-tertiary);">Мин: <strong style="color:var(--red-400);">${s.min.toFixed(2)}</strong></span>
                <span class="trend-pct ${pctClass}" style="text-align:right;">${pctStr}</span>
            </div>
        `;
    }).join('');

    statsEl.innerHTML = `
        <div style="font-size:11px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:8px;">
            📊 Статистика
        </div>
        ${rows}
    `;
}

function closeSnapshotChart() {
    document.getElementById('snapshotChartModal').classList.remove('active');
    if (snapshotChartInstance) {
        snapshotChartInstance.destroy();
        snapshotChartInstance = null;
    }
    currentSnapshotFixture = null;
    const betBlock = document.getElementById('snapshotBetBlock');
    if (betBlock) betBlock.innerHTML = '';
}

// ============================================================
