// AUTOBETS
// ============================================================
async function loadAutobets() {
    try {
        const [state, history] = await Promise.all([
            fetch(API_BASE + '/api/autobets/state?t=' + Date.now()).then(r => r.json()),
            fetch(API_BASE + '/api/autobets/history?limit=50&t=' + Date.now()).then(r => r.json())
        ]);
        document.getElementById('ab-bank').textContent = '$' + (state.bank || 0).toFixed(2);
        const profit = state.total_profit || 0;
        const profEl = document.getElementById('ab-profit');
        profEl.textContent = (profit >= 0 ? '+' : '') + '$' + profit.toFixed(2);
        profEl.style.color = profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        document.getElementById('ab-roi').textContent = (state.roi || 0) + '%';
        document.getElementById('ab-winrate').textContent = (state.winrate || 0) + '%';
        renderAutobetsHistory(history || []);
        loadClvStats();
    } catch (e) {
        console.error('loadAutobets:', e);
        showNotification('❌ Ошибка загрузки автоставок', 'error');
    }
}

function renderAutobetsHistory(history) {
    const el = document.getElementById('autobets-history');
    if (!el) return;
    if (!history.length) {
        el.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Пока нет автоставок</div>
                <div class="desc">Нажмите «Сделать ставки» чтобы поставить на матчи из кэша</div>
            </div>
        `;
        return;
    }
    el.innerHTML = history.map(b => {
        const emoji = b.result === 'win' ? '✅' :
                      b.result === 'loss' ? '❌' :
                      b.result === 'push' ? '➖' : '⏳';
        const profitColor = b.profit > 0 ? 'var(--emerald-400)' :
                            b.profit < 0 ? 'var(--red-400)' : 'var(--text-tertiary)';

        let liveStr = '';
        if (b.result === 'pending' && b.live_score) {
            const statusMap = {'1H': '1-й тайм', 'HT': 'Перерыв', '2H': '2-й тайм',
                               'ET': 'Доп. время', 'P': 'Пенальти', 'LIVE': 'LIVE'};
            const statusText = statusMap[b.live_status] || 'LIVE';
            const minuteStr = b.live_minute ? ` ${b.live_minute}'` : '';
            liveStr = `
                <div style="font-size:11px;color:var(--gold-400);margin-top:6px;
                            padding:6px 10px;background:rgba(245,158,11,0.1);
                            border-radius:8px;border:1px solid rgba(245,158,11,0.2);
                            display:flex;justify-content:space-between;align-items:center;">
                    <span>⚽ LIVE: <strong>${b.live_score}</strong>${minuteStr}</span>
                    <span style="font-size:10px;color:var(--text-tertiary);">${statusText}</span>
                </div>
            `;
        }

        const ht = (b.halftime_home != null && b.halftime_away != null)
            ? ` • 1-й: ${b.halftime_home}-${b.halftime_away}` : '';
        const score = (b.result !== 'pending' && b.home_goals != null && b.away_goals != null)
            ? `<div style="font-size:11px;color:var(--text-tertiary);margin-top:6px;">
                 Счёт: <strong>${b.home_goals}-${b.away_goals}</strong>${ht}
               </div>` : '';

        let clvStr = '';
        if (b.clv !== undefined && b.clv !== null) {
            const clvColor = b.clv >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
            clvStr = `<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px;">
                📊 CLV: <strong style="color:${clvColor};">${b.clv >= 0 ? '+' : ''}${b.clv.toFixed(2)}%</strong>
                ${b.closing_odds ? ` (закрытие: ${b.closing_odds.toFixed(2)})` : ''}
            </div>`;
        }

        return `
            <div class="bet-card" style="cursor:default;margin-bottom:8px;">
                <div class="bet-header">
                    <div style="flex:1;min-width:0;">
                        <div class="bet-match">${escapeHtml(b.home)} vs ${escapeHtml(b.away)}</div>
                        <div class="bet-league">${escapeHtml(b.bet_label || '—')} • ${escapeHtml(b.league || '')}</div>
                    </div>
                    <div style="font-size:18px;">${emoji}</div>
                </div>
                <div class="bet-stats">
                    <div class="bet-stat">
                        <span class="stat-label">Кэф</span>
                        <span class="stat-value">${Number(b.odds || 0).toFixed(2)}</span>
                    </div>
                    <div class="bet-stat">
                        <span class="stat-label">Ставка</span>
                        <span class="stat-value">$${Number(b.stake || 0).toFixed(2)}</span>
                    </div>
                    <div class="bet-stat">
                        <span class="stat-label">Прибыль</span>
                        <span class="stat-value" style="color:${profitColor};">
                            ${b.profit >= 0 ? '+' : ''}$${Number(b.profit || 0).toFixed(2)}
                        </span>
                    </div>
                </div>
                ${liveStr}${score}${clvStr}
            </div>
        `;
    }).join('');
}

async function autobetsPlace() {
    showNotification('💸 Размещаю автоставки...', '');
    try {
        const r = await fetch(API_BASE + '/api/autobets/place', { method: 'POST' }).then(r => r.json());
        showNotification(`✅ Размещено: ${r.placed}`, 'success');
        loadAutobets();
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function autobetsSettle() {
    showNotification('🔄 Обновляю результаты...', '');
    try {
        const r = await fetch(API_BASE + '/api/autobets/settle', { method: 'POST' }).then(r => r.json());
        showNotification(`✅ Обновлено: ${r.updated}`, 'success');
        loadAutobets();
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function autobetsReset() {
    if (!confirm('⚠️ Сбросить ВСЕ автоставки? Это действие необратимо.')) return;
    try {
        await fetch(API_BASE + '/api/autobets/reset', { method: 'POST' });
        showNotification('🗑️ Автоставки сброшены', 'success');
        loadAutobets();
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function computeClv() {
    showNotification('📊 Пересчитываю CLV...', '');
    try {
        const r = await fetch(API_BASE + '/api/autobets/clv/compute', { method: 'POST' }).then(r => r.json());
        showNotification(`✅ Обновлено: ${r.updated}`, 'success');
        loadAutobets();
        loadClvStats();
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function loadClvStats() {
    try {
        const stats = await fetch(API_BASE + '/api/autobets/clv/stats?t=' + Date.now()).then(r => r.json());
        if (stats.status !== 'ok') return;
        const avgEl = document.getElementById('clv-avg');
        const posEl = document.getElementById('clv-positive');
        const cntEl = document.getElementById('clv-count');
        if (avgEl) {
            avgEl.textContent = (stats.avg_clv >= 0 ? '+' : '') + stats.avg_clv.toFixed(2) + '%';
            avgEl.style.color = stats.avg_clv >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        }
        if (posEl) posEl.textContent = stats.positive_rate + '%';
        if (cntEl) cntEl.textContent = stats.count;
    } catch (e) {
        console.error('loadClvStats:', e);
    }
}

// ============================================================
// SIMULATOR
// ============================================================
async function loadSimPresets() {
    try {
        const presets = await fetch(API_BASE + '/api/simulator/presets?t=' + Date.now()).then(r => r.json());
        const el = document.getElementById('sim-presets');
        if (!el) return;
        el.innerHTML = Object.entries(presets).map(([key, p]) =>
            `<button class="filter-btn" onclick="applySimPreset('${key}')">${p.name}</button>`
        ).join('');
        window._simPresets = presets;
    } catch (e) {
        console.error('loadSimPresets:', e);
    }
}

function applySimPreset(key) {
    const p = window._simPresets && window._simPresets[key] ? window._simPresets[key].params : null;
    if (!p) return;
    const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
    };
    set('sim-min-ev', p.min_ev);
    set('sim-min-prob', p.min_prob);
    set('sim-min-odds', p.min_odds);
    set('sim-max-odds', p.max_odds);
    set('sim-min-xg', p.min_xg);
    set('sim-max-xg', p.max_xg);
    set('sim-stake', p.stake_pct);
    set('sim-bank', p.start_bank);
    showNotification('🎯 Пресет применён', '');
    haptic(8);
}

async function runSimulation() {
    const params = {
        min_ev: parseFloat(document.getElementById('sim-min-ev').value),
        max_ev: 500,
        min_prob: parseFloat(document.getElementById('sim-min-prob').value),
        max_prob: 100,
        min_odds: parseFloat(document.getElementById('sim-min-odds').value),
        max_odds: parseFloat(document.getElementById('sim-max-odds').value),
        min_xg: parseFloat(document.getElementById('sim-min-xg').value),
        max_xg: parseFloat(document.getElementById('sim-max-xg').value),
        bet_types: [],
        leagues: [],
        stake_pct: parseFloat(document.getElementById('sim-stake').value),
        start_bank: parseFloat(document.getElementById('sim-bank').value)
    };
    showNotification('🚀 Симулирую...', '');
    try {
        const r = await fetch(API_BASE + '/api/simulator/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(params)
        }).then(r => r.json());

        if (r.status !== 'ok') {
            showNotification('❌ ' + (r.error || 'Ошибка'), 'error');
            return;
        }

        currentSimResult = r.result;
        const res = r.result;
        document.getElementById('sim-results').style.display = 'block';

        const profitEl = document.getElementById('sim-profit');
        profitEl.textContent = (res.profit >= 0 ? '+' : '') + '$' + res.profit.toFixed(2);
        profitEl.style.color = res.profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';

        document.getElementById('sim-roi').textContent = res.roi + '%';
        document.getElementById('sim-winrate').textContent = res.winrate + '%';
        document.getElementById('sim-bets').textContent = res.total_bets;
        document.getElementById('sim-dd').textContent = res.max_drawdown + '%';
        document.getElementById('sim-end').textContent = '$' + res.end_bank.toFixed(2);

        if (simChart) simChart.destroy();
        const ctx = document.getElementById('sim-chart').getContext('2d');
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        const textColor = isLight ? 'rgba(6, 78, 59, 0.6)' : 'rgba(236, 253, 245, 0.6)';
        const gridColor = isLight ? 'rgba(6, 78, 59, 0.06)' : 'rgba(52, 211, 153, 0.05)';

        simChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: res.bets.map((_, i) => i + 1),
                datasets: [{
                    label: 'Банк',
                    data: res.bets.map(b => b.bank_after),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true, tension: 0.3,
                    pointRadius: 2, pointHoverRadius: 5
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } },
                    y: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } }
                }
            }
        });

        showNotification(`✅ Готово: ${res.total_bets} ставок`, 'success');
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function saveSimulation() {
    if (!currentSimResult) return;
    const name = prompt('Название стратегии:', 'Моя стратегия');
    if (!name) return;
    try {
        const r = await fetch(API_BASE + '/api/simulator/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, result: currentSimResult })
        }).then(r => r.json());
        showNotification(r.status === 'ok' ? '✅ Стратегия сохранена' : '❌ Ошибка',
                          r.status === 'ok' ? 'success' : 'error');
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

// ★ FIX #5: evt?.target с fallback
async function runGridSearch(evt) {
    if (!confirm('🎯 Запустить Grid Search?\n\nЭто переберёт ~200 комбинаций параметров. Займёт 30-60 сек.')) return;

    showNotification('🎯 Grid Search запущен...', '');
    const btn = (evt && evt.target) || document.querySelector('button[onclick="runGridSearch(event)"]');
    const oldText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Поиск (30-60 сек)...';
    }

    try {
        const r = await fetch(API_BASE + '/api/simulator/grid_search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_combinations: 200, min_bets: 5 })
        }).then(r => r.json());

        if (r.status !== 'ok') {
            showNotification('❌ ' + (r.error || 'Ошибка'), 'error');
            return;
        }

        const result = r.result;
        if (!result.top || result.top.length === 0) {
            showNotification('❌ Не найдено стратегий', 'error');
            return;
        }

        const best = result.top[0];
        const p = best.params;

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
        };
        set('sim-min-ev', p.min_ev);
        set('sim-min-prob', p.min_prob);
        set('sim-min-odds', p.min_odds);
        set('sim-max-odds', p.max_odds);
        set('sim-stake', p.stake_pct);

        showNotification(`🏆 Лучшая: ROI ${best.roi}% | Ставок ${best.total_bets}`, 'success');

        await runSimulation();
        renderGridTop5(result.top);
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || '🎯 Найти лучшую стратегию (Grid Search)';
        }
    }
}

function renderGridTop5(top) {
    const simResults = document.getElementById('sim-results');
    if (!simResults) return;

    let gridDiv = document.getElementById('grid-top5');
    if (gridDiv) gridDiv.remove();

    gridDiv = document.createElement('div');
    gridDiv.id = 'grid-top5';
    gridDiv.className = 'card';
    gridDiv.style.marginTop = '16px';

    const rowsHtml = top.map((t, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : (i + 1);
        const rowStyle = i === 0 ? 'background: rgba(16,185,129,0.08); font-weight:700;' : '';
        const roiColor = t.roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        const profitColor = t.profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        return `
            <tr style="${rowStyle}">
                <td>${medal}</td><td>${t.params.min_ev}%</td><td>${t.params.min_prob}%</td>
                <td>${t.params.min_odds}-${t.params.max_odds}</td><td>${t.total_bets}</td>
                <td>${t.winrate}%</td>
                <td style="color:${roiColor};font-weight:700;">${t.roi >= 0 ? '+' : ''}${t.roi}%</td>
                <td style="color:${profitColor};">${t.profit >= 0 ? '+' : ''}$${t.profit.toFixed(2)}</td>
                <td>${t.max_drawdown}%</td>
            </tr>
        `;
    }).join('');

    gridDiv.innerHTML = `
        <div class="card-header"><h2>🏆 ТОП-5 СТРАТЕГИЙ</h2></div>
        <div style="overflow-x:auto;">
            <table style="width:100%; font-size:11px; min-width:500px;">
                <thead><tr>
                    <th>#</th><th>EV</th><th>Prob</th><th>Кэф</th>
                    <th>Ставок</th><th>WR</th><th>ROI</th><th>Прибыль</th><th>DD</th>
                </tr></thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        </div>
    `;

    if (simResults.parentNode) {
        simResults.parentNode.insertBefore(gridDiv, simResults.nextSibling);
    }
}

// ============================================================
