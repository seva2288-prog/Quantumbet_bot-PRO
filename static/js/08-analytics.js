// ANALYTICS
// ============================================================
function renderBankCalc() {
    const box = document.getElementById('bankCalcBody');
    if (!box) return;
    const hist = ((cachedData && cachedData.history) || []).filter(b => b.result === 'win' || b.result === 'loss');
    const bankDef = (cachedData && cachedData.stats && cachedData.stats.bank) || 1000;
    const bank = parseFloat(safeLSGet('calcBank', bankDef)) || bankDef;
    const pct = parseFloat(safeLSGet('calcPct', 1.5)) || 1.5;
    const sorted = hist.slice().sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));
    let cum = 0, peak = 0, maxDd = 0;
    sorted.forEach(b => {
        cum += Number(b.profit) || 0;
        if (cum > peak) peak = cum;
        maxDd = Math.max(maxDd, peak - cum);
    });
    const curDd = peak - cum;
    const stake = bank * pct / 100;
    box.innerHTML = `
        <div class="dm-calc-row">
            <label>Банк<input type="number" id="calcBank" value="${bank}" step="10" oninput="saveBankCalc()"></label>
            <label>% на ставку<input type="number" id="calcPct" value="${pct}" step="0.1" min="0.1" max="20" oninput="saveBankCalc()"></label>
        </div>
        <div class="dm-summary" style="grid-template-columns:repeat(3,1fr);">
            <div class="dm-sum-item"><b id="calcStake">${stake.toFixed(2)}</b><span>ставка</span></div>
            <div class="dm-sum-item"><b style="color:var(--red-400);">−${maxDd.toFixed(2)}</b><span>макс. просадка</span></div>
            <div class="dm-sum-item"><b style="color:${curDd > 0 ? 'var(--red-400)' : 'var(--emerald-400)'};">${curDd > 0 ? '−' + curDd.toFixed(2) : '0'}</b><span>сейчас от пика</span></div>
        </div>
        <div style="font-size:11px;color:var(--text-tertiary);">Просадка считается по ${hist.length} рассчитанным ставкам. Макс. просадка = ${bank ? (maxDd / bank * 100).toFixed(1) : 0}% от банка.</div>`;
}
function saveBankCalc() {
    const b = parseFloat(document.getElementById('calcBank').value) || 0;
    const p = parseFloat(document.getElementById('calcPct').value) || 0;
    safeLSSet('calcBank', String(b)); safeLSSet('calcPct', String(p));
    const el = document.getElementById('calcStake');
    if (el) el.textContent = (b * p / 100).toFixed(2);
}

async function renderBacktestForm() {
    const box = document.getElementById('backtestForm');
    if (!box || box.dataset.ready) return;
    let v = {};
    try {
        const r = await fetch(API_BASE + '/api/bot_settings_ui');
        if (r.ok) v = (await r.json()).settings || {};
    } catch (e) {}
    const f = (id, label, val, step) => `<label>${label}<input type="number" id="${id}" value="${val}" step="${step}"></label>`;
    box.innerHTML = `<div class="dm-calc-row" style="grid-template-columns:repeat(2,1fr);">
        ${f('btMinDrop', 'Мин. падение, %', v.LINE_MOVEMENT_MIN_DROP_PCT ?? -4, 0.5)}
        ${f('btMaxDrop', 'Макс. падение, %', v.LINE_MOVEMENT_MAX_DROP_PCT ?? -15, 0.5)}
        ${f('btMinOdds', 'Мин. кэф', v.LINE_MOVEMENT_MIN_ODDS ?? 2, 0.05)}
        ${f('btMaxOdds', 'Макс. кэф', v.LINE_MOVEMENT_MAX_ODDS ?? 4.5, 0.05)}
    </div>
    <button class="btn btn-primary" onclick="runBacktest()" style="width:100%;padding:10px;margin-bottom:10px;">▶️ Запустить бэктест</button>`;
    box.dataset.ready = '1';
}
async function runBacktest() {
    const out = document.getElementById('backtestResult');
    out.innerHTML = '<div style="font-size:12px;color:var(--text-tertiary);">Считаю…</div>';
    const g = id => document.getElementById(id).value;
    const q = `min_drop=${g('btMinDrop')}&max_drop=${g('btMaxDrop')}&min_odds=${g('btMinOdds')}&max_odds=${g('btMaxOdds')}`;
    try {
        const r = await fetch(API_BASE + '/api/backtest?days=60&' + q);
        const d = await r.json();
        if (!r.ok || d.status !== 'ok') throw new Error(d.error || r.status);
        const x = d.result;
        const col = v => v == null ? '' : v > 0 ? 'var(--emerald-400)' : v < 0 ? 'var(--red-400)' : '';
        const row = (name, a) => `<tr><td>${name}</td><td>${a.n}</td><td>${a.wins}/${a.losses}</td><td>${fmtPct(a.winrate)}</td><td style="color:${col(a.roi)};">${fmtPct(a.roi, true)}</td><td style="color:${col(a.avg_clv)};">${fmtPct(a.avg_clv, true)}</td></tr>`;
        const head = '<thead><tr><th></th><th>Ст.</th><th>W/L</th><th>Win%</th><th>ROI</th><th>CLV</th></tr></thead>';
        out.innerHTML = `
            <div class="dm-summary" style="grid-template-columns:repeat(4,1fr);">
                <div class="dm-sum-item"><b>${x.n}</b><span>ставок</span></div>
                <div class="dm-sum-item"><b>${fmtPct(x.winrate)}</b><span>Win rate</span></div>
                <div class="dm-sum-item"><b style="color:${col(x.roi)};">${fmtPct(x.roi, true)}</b><span>ROI</span></div>
                <div class="dm-sum-item"><b style="color:${col(x.profit)};">${x.profit > 0 ? '+' : ''}${x.profit}</b><span>прибыль (ед.)</span></div>
            </div>
            <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:10px;">Матчей со снимками: ${d.coverage.fixtures}, из них со счётом: ${d.coverage.with_result}. Чем больше матчей со счётом, тем надёжнее вывод (меньше 30 ставок — это скорее шум).</div>
            <div class="dm-title">Порог падения (мин.)</div>
            <div class="dm-tablewrap"><table class="dm-table">${head}<tbody>${d.grid_drop.map(g => row(g.value + '%', g)).join('')}</tbody></table></div>
            <div class="dm-title" style="margin-top:12px;">Диапазон кэфов</div>
            <div class="dm-tablewrap"><table class="dm-table">${head}<tbody>${d.grid_odds.map(g => row(g.value, g)).join('')}</tbody></table></div>`;
    } catch (e) {
        out.innerHTML = '<div style="font-size:12px;color:var(--red-400);">Ошибка: ' + escapeHtml(String(e.message)) + '</div>';
    }
}

function renderAnalytics(data) {
    if (!data) data = cachedData;
    if (!data) return;
    const history = data.history || [];
    const total = history.length;
    const wins = history.filter(b => b.result === 'win').length;
    const losses = history.filter(b => b.result === 'loss').length;
    const avgOdds = total > 0 ? (history.reduce((s, b) => s + (b.odds || 0), 0) / total).toFixed(2) : 0;
    document.getElementById('aTotal').textContent = total;
    document.getElementById('aWins').textContent = wins;
    document.getElementById('aLosses').textContent = losses;
    document.getElementById('aAvgOdds').textContent = avgOdds;
    setTimeout(() => renderAnalyticsChart(), 100);
    loadLmAnalytics();
    renderBankCalc();
    renderCalendar();
    loadAnomalyOutcomes();
    loadHtStats();
    loadHtLive();
    loadLateGoal();
    renderBacktestForm();
    renderStrategyBars(history);
    renderBetTypeBreakdown(history);
    renderLeagueBreakdown(history);
    loadClvByStrategy();
}

function renderAnalyticsChart() {
    const ctx = document.getElementById('analyticsChart');
    if (!ctx || !cachedData) return;
    const period = parseInt(document.getElementById('analyticsPeriod').value) || 30;
    const history = cachedData.history || [];
    const labels = [];
    const profits = [];
    let cumulative = 0;
    for (let i = period - 1; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().slice(0, 10);
        labels.push(date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }));
        const dayProfit = history.reduce((sum, b) => {
            const bDate = (b.date || '').split(' ')[0];
            if (bDate === dateStr && b.result) {
                return sum + (b.result === 'win' ? (b.profit || 0) : b.result === 'loss' ? -(b.stake || 0) : 0);
            }
            return sum;
        }, 0);
        cumulative += dayProfit;
        profits.push(cumulative);
    }
    if (analyticsChartInstance) analyticsChartInstance.destroy();
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    const textColor = isLight ? 'rgba(6, 78, 59, 0.6)' : 'rgba(236, 253, 245, 0.6)';
    const gridColor = isLight ? 'rgba(6, 78, 59, 0.06)' : 'rgba(52, 211, 153, 0.05)';
    analyticsChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Прибыль ($)',
                data: profits,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.08)',
                fill: true, tension: 0.4,
                pointBackgroundColor: '#10b981',
                pointBorderColor: isLight ? 'white' : '#0d1a17',
                pointBorderWidth: 2, pointRadius: 3, pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: textColor, font: { size: 10 } } } },
            scales: {
                x: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } },
                y: { ticks: { color: textColor, callback: v => '$' + v, font: { size: 9 } }, grid: { color: gridColor } }
            }
        }
    });
}

function renderStrategyBars(history) {
    const container = document.getElementById('strategyBars');
    if (!container) return;
    const strategies = {
        '70%+': { wins: 0, losses: 0, profit: 0, stake: 0, label: '70%+ матчи' },
        'X2': { wins: 0, losses: 0, profit: 0, stake: 0, label: 'X2 Стратегия' },
        'ТМ 2.5': { wins: 0, losses: 0, profit: 0, stake: 0, label: 'ТМ 2.5' },
        'LINE MOVEMENT': { wins: 0, losses: 0, profit: 0, stake: 0, label: '📈 LINE MOVEMENT' },
        'Другое': { wins: 0, losses: 0, profit: 0, stake: 0, label: 'Другое' }
    };
    history.forEach(b => {
        if (!b.result || b.result === 'pending') return;
        let key = 'Другое';
        const bet = (b.bet || '').toLowerCase();
        const src = (b.source || '').toLowerCase();
        if (src === 'line_movement' || bet.includes('📈') || bet.includes('line movement')) key = 'LINE MOVEMENT';
        else if (bet.includes('x2')) key = 'X2';
        else if (bet.includes('тм') || bet.includes('under')) key = 'ТМ 2.5';
        else if (bet.includes('1x') || bet.includes('п1') || bet.includes('п2')) key = '70%+';
        const s = strategies[key];
        if (b.result === 'win') s.wins++;
        else if (b.result === 'loss') s.losses++;
        s.profit += b.profit || 0;
        s.stake += b.stake || 0;
    });
    const entries = Object.entries(strategies).filter(([_, s]) => (s.wins + s.losses) > 0);
    if (entries.length === 0) {
        container.innerHTML = `<div class="no-data" style="padding:20px;"><div class="desc">Нет данных</div></div>`;
        return;
    }
    container.innerHTML = entries.map(([key, s]) => {
        const total = s.wins + s.losses;
        const wr = total > 0 ? (s.wins / total * 100) : 0;
        const roi = s.stake > 0 ? (s.profit / s.stake * 100) : 0;
        const valueColor = s.profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        return `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color);">
            <span style="font-size:12px;color:${valueColor};font-weight:700;">${s.label}</span>
            <span style="font-size:12px;">WR ${wr.toFixed(0)}% · ROI ${roi.toFixed(0)}% · ${s.profit >= 0 ? '+' : ''}$${s.profit.toFixed(2)}</span>
        </div>`;
    }).join('');
}

function renderBetTypeBreakdown(history) {
    const container = document.getElementById('betTypeBreakdown');
    if (!container) return;
    const types = {};
    history.forEach(b => {
        if (!b.result || b.result === 'pending') return;
        const bet = b.bet || 'Другое';
        if (!types[bet]) types[bet] = { wins: 0, losses: 0 };
        if (b.result === 'win') types[bet].wins++;
        else if (b.result === 'loss') types[bet].losses++;
    });
    const sorted = Object.entries(types).sort((a, b) => (b[1].wins + b[1].losses) - (a[1].wins + a[1].losses)).slice(0, 6);
    container.innerHTML = sorted.map(([name, s]) => {
        const total = s.wins + s.losses;
        const wr = (s.wins / total * 100).toFixed(0);
        const color = wr >= 60 ? 'var(--emerald-400)' : wr >= 45 ? 'var(--gold-400)' : 'var(--red-400)';
        return `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color);">
            <span style="font-size:12px;">${name}</span>
            <span style="color:${color};font-weight:700;font-size:12px;">${s.wins}/${total} (${wr}%)</span>
        </div>`;
    }).join('');
}

function renderLeagueBreakdown(history) {
    const container = document.getElementById('leagueBreakdown');
    if (!container) return;
    const leagues = {};
    history.forEach(b => {
        if (!b.result || b.result === 'pending') return;
        const league = b.league || 'Другое';
        if (!leagues[league]) leagues[league] = { wins: 0, losses: 0, profit: 0 };
        if (b.result === 'win') leagues[league].wins++;
        else if (b.result === 'loss') leagues[league].losses++;
        leagues[league].profit += b.profit || 0;
    });
    const sorted = Object.entries(leagues).sort((a, b) => b[1].profit - a[1].profit).slice(0, 8);
    container.innerHTML = sorted.map(([name, s]) => {
        const color = s.profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        return `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color);">
            <span style="font-size:12px;">${name}</span>
            <span style="color:${color};font-weight:700;font-size:12px;">${s.profit >= 0 ? '+' : ''}$${s.profit.toFixed(2)}</span>
        </div>`;
    }).join('');
}

// ============================================================
// ★ FIX #10: СТАТИСТИКА ПО ДНЯМ (будущие даты)
// ============================================================
async function loadDailyStats() {
    const listEl = document.getElementById('dailyList');
    const summaryEl = document.getElementById('dailySummary');
    if (!listEl) return;

    listEl.innerHTML = `
        <div class="skeleton" style="height:80px;"></div>
        <div class="skeleton" style="height:80px;"></div>
        <div class="skeleton" style="height:80px;"></div>
    `;

    try {
        const resp = await fetch(API_BASE + '/api/all_data?t=' + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        const history = data.history || [];

        const days = aggregateByDay(history, dailyFilter);
        renderDailySummary(days, summaryEl);
        renderDailyList(days, listEl);
    } catch (e) {
        console.error('loadDailyStats:', e);
        listEl.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Ошибка загрузки</div>
                <div class="desc">${e.message}</div>
                <button class="btn btn-primary" onclick="loadDailyStats()" style="margin-top:12px;">🔄 Повторить</button>
            </div>
        `;
    }
}

function aggregateByDay(history, period) {
    const byDay = {};

    for (const bet of history) {
        const dateStr = (bet.date || '').split(' ')[0];
        if (!dateStr) continue;

        // ★ FIX #10: пропускаем будущие и слишком старые
        let betDate;
        try { betDate = new Date(dateStr); } catch (e) { continue; }
        const now = new Date();
        const diffDays = Math.floor((now - betDate) / (1000 * 60 * 60 * 24));
        if (diffDays < 0) continue;
        if (period !== 'all' && diffDays > period) continue;

        if (!byDay[dateStr]) {
            byDay[dateStr] = {
                date: dateStr,
                bets: 0,
                wins: 0,
                losses: 0,
                pushes: 0,
                pending: 0,
                profit: 0,
                stake: 0,
                items: [],
            };
        }

        const d = byDay[dateStr];
        d.bets += 1;
        d.items.push(bet);

        const result = bet.result || 'pending';
        const stake = bet.stake || 0;
        let profit = 0;

        if (result === 'win') {
            d.wins += 1;
            profit = (bet.profit && bet.profit !== 0) ? bet.profit : (stake * (bet.odds - 1));
        } else if (result === 'loss') {
            d.losses += 1;
            profit = -stake;
        } else if (result === 'push') {
            d.pushes += 1;
            profit = 0;
        } else {
            d.pending += 1;
            profit = 0;
        }

        d.profit += profit;
        d.stake += stake;
    }

    let days = Object.values(byDay);

    if (dailySort === 'date') {
        days.sort((a, b) => b.date.localeCompare(a.date));
    } else if (dailySort === 'profit') {
        days.sort((a, b) => b.profit - a.profit);
    } else if (dailySort === 'bets') {
        days.sort((a, b) => b.bets - a.bets);
    }

    return days;
}

function renderDailySummary(days, el) {
    if (!el) return;

    const totalBets = days.reduce((s, d) => s + d.bets, 0);
    const totalWins = days.reduce((s, d) => s + d.wins, 0);
    const totalLosses = days.reduce((s, d) => s + d.losses, 0);
    const totalProfit = days.reduce((s, d) => s + d.profit, 0);
    const totalStake = days.reduce((s, d) => s + d.stake, 0);

    const roi = totalStake > 0 ? (totalProfit / totalStake * 100).toFixed(1) : '0.0';
    const profitClass = totalProfit >= 0 ? 'green' : 'red';

    el.innerHTML = `
        <div class="stat-card">
            <div class="value">${totalBets}</div>
            <div class="label">🎲 Ставок</div>
        </div>
        <div class="stat-card">
            <div class="value green">${totalWins}</div>
            <div class="label">✅ WIN</div>
        </div>
        <div class="stat-card">
            <div class="value red">${totalLosses}</div>
            <div class="label">❌ LOSS</div>
        </div>
        <div class="stat-card">
            <div class="value ${profitClass}">
                ${totalProfit >= 0 ? '+' : ''}$${totalProfit.toFixed(2)}
            </div>
            <div class="label">💰 Прибыль (${roi}% ROI)</div>
        </div>
    `;
}

function renderDailyList(days, el) {
    if (!el) return;

    if (!days.length) {
        el.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Нет данных</div>
                <div class="desc">Пока нет ставок за выбранный период</div>
            </div>
        `;
        return;
    }

    el.innerHTML = days.map(d => {
        const profitClass = d.profit > 0 ? 'var(--emerald-400)'
                          : d.profit < 0 ? 'var(--red-400)'
                          : 'var(--text-tertiary)';
        const profitStr = d.profit === 0 ? '$0'
                        : (d.profit > 0 ? `+$${d.profit.toFixed(2)}` : `-$${Math.abs(d.profit).toFixed(2)}`);

        const roi = d.stake > 0 ? (d.profit / d.stake * 100).toFixed(1) : '0.0';
        const winrate = (d.wins + d.losses) > 0
            ? (d.wins / (d.wins + d.losses) * 100).toFixed(0)
            : '0';

        let dateStr = d.date;
        try {
            const dt = new Date(d.date);
            const options = { day: '2-digit', month: 'short', year: 'numeric' };
            dateStr = dt.toLocaleDateString('ru-RU', options);
            const weekday = dt.toLocaleDateString('ru-RU', { weekday: 'short' });
            dateStr += ` (${weekday})`;
        } catch (e) {}

        const pendingStr = d.pending > 0 ? ` · ⏳ ${d.pending}` : '';

        return `
            <div class="card" style="padding:12px;margin-bottom:8px;cursor:pointer;"
                 onclick="showDayDetail('${d.date}')">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px;">
                    <div>
                        <div style="font-size:13px;font-weight:700;color:var(--text-primary);">
                            📅 ${dateStr}
                        </div>
                        <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">
                            🎲 ${d.bets} ставок${pendingStr}
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:18px;font-weight:800;color:${profitClass};">
                            ${profitStr}
                        </div>
                        <div style="font-size:9px;color:var(--text-tertiary);">
                            ROI ${roi}%
                        </div>
                    </div>
                </div>

                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;padding-top:8px;border-top:1px solid var(--border-color);">
                    <div>
                        <div style="font-size:9px;color:var(--text-tertiary);text-transform:uppercase;">WIN</div>
                        <div style="font-size:13px;font-weight:700;color:var(--emerald-400);">
                            ${d.wins}
                        </div>
                    </div>
                    <div>
                        <div style="font-size:9px;color:var(--text-tertiary);text-transform:uppercase;">LOSS</div>
                        <div style="font-size:13px;font-weight:700;color:var(--red-400);">
                            ${d.losses}
                        </div>
                    </div>
                    <div>
                        <div style="font-size:9px;color:var(--text-tertiary);text-transform:uppercase;">WR</div>
                        <div style="font-size:13px;font-weight:700;color:var(--gold-400);">
                            ${winrate}%
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function setDailyFilter(period) {
    dailyFilter = period === 'all' ? 'all' : parseInt(period);
    document.querySelectorAll('[data-dailyfilter]').forEach(b => {
        b.classList.toggle('active', b.dataset.dailyfilter === String(period));
    });
    haptic(6);
    loadDailyStats();
}

function setDailySort(sort) {
    dailySort = sort;
    document.querySelectorAll('[data-dailysort]').forEach(b => {
        b.classList.toggle('active', b.dataset.dailysort === sort);
    });
    haptic(6);
    loadDailyStats();
}

async function showDayDetail(dateStr) {
    try {
        const resp = await fetch(API_BASE + '/api/all_data?t=' + Date.now());
        const data = await resp.json();
        const history = data.history || [];
        const dayBets = history.filter(b => (b.date || '').split(' ')[0] === dateStr);

        if (!dayBets.length) {
            showNotification('📭 Нет ставок в этот день', '');
            return;
        }

        let displayDate = dateStr;
        try {
            const dt = new Date(dateStr);
            displayDate = dt.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
        } catch (e) {}

        const modal = document.createElement('div');
        modal.className = 'modal-overlay active';
        modal.innerHTML = `
            <div class="modal modal-large">
                <div class="modal-header">
                    <h3>📅 ${displayDate}</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">✕</button>
                </div>
                <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:12px;">
                    ${dayBets.length} ставок
                </div>
                <div style="max-height:60vh;overflow-y:auto;">
                    ${dayBets.map(b => {
                        const emoji = b.result === 'win' ? '✅' :
                                     b.result === 'loss' ? '❌' :
                                     b.result === 'push' ? '🔄' : '⏳';
                        const profit = b.profit || 0;
                        const profitColor = profit > 0 ? 'var(--emerald-400)' :
                                           profit < 0 ? 'var(--red-400)' : 'var(--text-tertiary)';
                        const score = (b.home_goals != null && b.away_goals != null)
                            ? ` ${b.home_goals}-${b.away_goals}` : '';
                        return `
                            <div style="padding:10px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;gap:8px;">
                                <div style="flex:1;min-width:0;">
                                    <div style="font-size:12px;font-weight:700;">
                                        ${emoji} ${b.home} vs ${b.away}${score}
                                    </div>
                                    <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">
                                        ${b.bet || '—'} @ ${Number(b.odds || 0).toFixed(2)}
                                        ${b.league ? ` · ${b.league}` : ''}
                                    </div>
                                </div>
                                <div style="text-align:right;flex-shrink:0;">
                                    <div style="font-size:13px;font-weight:700;color:${profitColor};">
                                        ${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}
                                    </div>
                                    <div style="font-size:10px;color:var(--text-tertiary);">
                                        $${(b.stake || 0).toFixed(2)}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

// ============================================================
// CLV ПО СТРАТЕГИЯМ
// ============================================================
async function loadClvByStrategy() {
    const container = document.getElementById('clvByStrategyContent');
    if (!container) return;

    container.innerHTML = `
        <div class="skeleton" style="width:80%"></div>
        <div class="skeleton" style="width:60%"></div>
    `;

    try {
        const period = document.getElementById('clvPeriod')?.value || 30;
        const resp = await fetch(API_BASE + `/api/clv/by_strategy?days=${period}&t=` + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();

        if (data.status !== 'ok') throw new Error(data.error || 'API error');

        const strategies = data.strategies || {};
        if (Object.keys(strategies).length === 0) {
            container.innerHTML = `
                <div class="no-data" style="padding:20px;">
                    <div class="emoji">📭</div>
                    <div class="title">Пока нет CLV-данных</div>
                    <div class="desc">Нужно больше рассчитанных автоставок. Подожди 2-3 дня.</div>
                </div>
            `;
            return;
        }

        renderClvByStrategy(strategies, period);
    } catch (e) {
        console.error('loadClvByStrategy:', e);
        container.innerHTML = `
            <div style="padding:12px;color:var(--red-400);font-size:12px;">
                ❌ Ошибка: ${e.message}
                <button class="btn btn-outline" onclick="loadClvByStrategy()" style="margin-left:8px;padding:2px 8px;font-size:10px;">🔄</button>
            </div>
        `;
    }
}

function renderClvByStrategy(strategies, period) {
    const container = document.getElementById('clvByStrategyContent');
    if (!container) return;

    const labelMap = {
        '70_percent': '🎯 70%+',
        'value': '💎 VALUE',
        'btts': '⚽ BTTS',
        'tm25_premium': '🔥 ТМ 2.5 PREMIUM',
        'tm25_standard': '⭐ ТМ 2.5 STD',
        'line_movement': '📈 LINE MOVEMENT',
        'x2': '🔥 X2',
    };

    const statusMap = {
        'excellent':         { emoji: '🟢', action: '×1.25 BOOST', color: 'var(--emerald-400)' },
        'good':              { emoji: '🔵', action: 'normal',       color: 'var(--blue-400)' },
        'weak':              { emoji: '🟡', action: '×0.5 REDUCE',  color: 'var(--gold-400)' },
        'critical':          { emoji: '🔴', action: '🛑 SKIP',      color: 'var(--red-400)' },
        'insufficient_data': { emoji: '⚪', action: 'ожидаем',       color: 'var(--text-tertiary)' },
        'no_data':           { emoji: '⚪', action: 'нет данных',    color: 'var(--text-tertiary)' },
        'active':            { emoji: '⚪', action: 'ожидаем',       color: 'var(--text-tertiary)' },
        'no_model':          { emoji: '🔵', action: 'N/A',          color: 'var(--text-tertiary)' },
    };

    const sorted = Object.entries(strategies).sort((a, b) =>
        (b[1].avg_clv || 0) - (a[1].avg_clv || 0)
    );

    const positive = sorted.filter(([_, s]) => s.avg_clv > 0).length;
    const total = sorted.length;

    let html = `
        <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px;">
            <div class="stat-card">
                <div class="value emerald">${positive}/${total}</div>
                <div class="label">📈 С CLV+</div>
            </div>
            <div class="stat-card">
                <div class="value">${period}д</div>
                <div class="label">📅 Период</div>
            </div>
            <div class="stat-card">
                <div class="value">${sorted.reduce((s, [_, x]) => s + (x.count || 0), 0)}</div>
                <div class="label">📊 Замеров</div>
            </div>
        </div>
    `;

    html += sorted.map(([src, st]) => {
        const label = labelMap[src] || src;
        const meta = statusMap[st.status] || statusMap['no_data'];
        const avgClv = st.avg_clv || 0;
        const clvClass = avgClv >= 0 ? 'up' : 'down';
        const clvStr = (avgClv >= 0 ? '+' : '') + avgClv.toFixed(2) + '%';

        const barPct = Math.min(Math.abs(avgClv) / 3 * 100, 100);
        const barColor = avgClv >= 0 ? 'linear-gradient(90deg, var(--emerald-500), var(--emerald-400))' :
                                       'linear-gradient(90deg, var(--red-500), var(--red-400))';

        return `
            <div style="padding:12px;margin-bottom:8px;border-radius:10px;
                        background:rgba(255,255,255,0.02);
                        border:1px solid var(--border-color);">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:13px;font-weight:700;color:${meta.color};">
                            ${meta.emoji} ${label}
                        </div>
                        <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">
                            ${st.count} замеров • действие: <b style="color:${meta.color};">${meta.action}</b>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div class="trend-pct ${clvClass}" style="font-size:16px;font-weight:800;">
                            ${clvStr}
                        </div>
                        <div style="font-size:9px;color:var(--text-tertiary);">avg CLV</div>
                    </div>
                </div>
                <div style="height:6px;background:rgba(255,255,255,0.05);border-radius:999px;overflow:hidden;">
                    <div style="height:100%;width:${barPct}%;background:${barColor};transition:width 0.5s;"></div>
                </div>
            </div>
        `;
    }).join('');

    html += `
        <div style="font-size:10px;color:var(--text-tertiary);margin-top:12px;padding-top:10px;border-top:1px solid var(--border-color);">
            💡 CLV > +1% → Kelly × 1.5 • CLV < -0.5% → Kelly × 0.5 • CLV < -3% → пропуск ставки
        </div>
    `;

    container.innerHTML = html;
}

// ============================================================
