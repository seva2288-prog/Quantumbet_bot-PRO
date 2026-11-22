// DASHBOARD
// ============================================================
function renderDashboard(data) {
    const s = data.stats || {};
    const matches = data.matches || [];
    document.getElementById('statBank').textContent = '$' + (s.bank || 1000);
    document.getElementById('statProfit').textContent = (s.profit >= 0 ? '+' : '') + '$' + (s.profit || 0);
    document.getElementById('statWinrate').textContent = (s.winrate || 0) + '%';
    document.getElementById('statRoi').textContent = (s.roi || 0) + '%';

    const activeMatches = matches.slice(0, 3);
    renderActiveMatchesList(activeMatches);

    const x2Stats = calcX2Stats();
    document.getElementById('x2Total').textContent = x2Stats.total;
    document.getElementById('x2Wins').textContent = x2Stats.wins;
    document.getElementById('x2Winrate').textContent = x2Stats.winrate + '%';

    renderLMDashboardStats(data.history || []);

    setTimeout(() => renderChart(data.profit_data), 50);
}

function renderLMDashboardStats(history) {
    const lmBets = history.filter(b => (b.source || '') === 'line_movement'
                                     || (b.bet || '').includes('📈')
                                     || (b.bet || '').toLowerCase().includes('line movement'));
    const card = document.getElementById('lmDashboardCard');
    if (!card) return;

    const total = lmBets.length;
    if (total === 0) {
        card.style.display = 'none';
        return;
    }

    const wins = lmBets.filter(b => b.result === 'win').length;
    const losses = lmBets.filter(b => b.result === 'loss').length;
    const profit = lmBets.reduce((s, b) => s + (b.profit || 0), 0);
    const stakeSum = lmBets.reduce((s, b) => s + (b.stake || 0), 0);
    const wr = (wins + losses) > 0 ? (wins / (wins + losses) * 100) : 0;
    const roi = stakeSum > 0 ? (profit / stakeSum * 100) : 0;

    const totalEl = document.getElementById('lm-total');
    const winsEl = document.getElementById('lm-wins');
    const roiEl = document.getElementById('lm-roi');
    const wrEl = document.getElementById('lm-wr');

    if (totalEl) totalEl.textContent = total;
    if (winsEl) winsEl.textContent = wins;
    if (roiEl) roiEl.textContent = roi.toFixed(1) + '%';
    if (wrEl) wrEl.textContent = wr.toFixed(1) + '%';

    card.style.display = 'block';
}

async function loadDashboardAutobets() {
    try {
        const state = await fetch(API_BASE + '/api/autobets/state?t=' + Date.now()).then(r => r.json());
        document.getElementById('dash-ab-bank').textContent = '$' + (state.bank || 0).toFixed(2);
        const p = state.total_profit || 0;
        const pEl = document.getElementById('dash-ab-profit');
        pEl.textContent = (p >= 0 ? '+' : '') + '$' + p.toFixed(2);
        pEl.style.color = p >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        document.getElementById('dash-ab-roi').textContent = (state.roi || 0) + '%';
        const clv = state.avg_clv || 0;
        const clvEl = document.getElementById('dash-ab-clv');
        clvEl.textContent = (clv >= 0 ? '+' : '') + clv.toFixed(2) + '%';
        clvEl.style.color = clv >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
    } catch (e) {
        console.error('loadDashboardAutobets:', e);
    }
}

function renderActiveMatchesList(matches) {
    const container = document.getElementById('activeMatchesList');
    if (!container) return;
    if (!matches || matches.length === 0) {
        container.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Нет активных матчей</div>
                <div class="desc">Нажмите «Найти матчи» чтобы запустить бот</div>
            </div>
        `;
        return;
    }
    container.innerHTML = matches.map(m => renderBetCard(m, true)).join('');
}

// ============================================================
// АНОМАЛИИ НА DASHBOARD
// ★ FIX #1: объявлена `card`
// ============================================================
async function loadDashboardAnomalies() {
    try {
        const resp = await fetch(API_BASE + '/api/snapshot_anomalies?days=7&limit=3');
        if (!resp.ok) return;
        const data = await resp.json();
        const container = document.getElementById('dashboardAnomaliesList');
        // ★ FIX #1: card была не объявлена → ReferenceError
        const card = document.getElementById('anomaliesCard');
        if (!container || !card) return;

        if (!data.anomalies || data.anomalies.length === 0) {
            card.style.display = 'none';
            return;
        }
        card.style.display = 'block';

        container.innerHTML = data.anomalies.map(a => {
            const selLabel = a.selection === '1' ? '1X' : (a.selection === 'X' ? 'X' : '2');
            return `
                <div class="snapshot-card has-anomaly" style="padding:10px;margin-bottom:8px;" onclick="openSnapshotFromAnomaly(${a.fixture_id})">
                    <div style="display:flex;justify-content:space-between;gap:8px;">
                        <div style="flex:1;min-width:0;">
                            <div class="snapshot-match" style="font-size:13px;">${escapeHtml(a.home)} vs ${escapeHtml(a.away)}</div>
                            <div class="snapshot-meta">🏆 ${escapeHtml(a.league || '—')}</div>
                        </div>
                        <div class="snapshot-badge anomaly" style="font-size:8px;">
                            +${a.anomaly_pct.toFixed(1)}%
                        </div>
                    </div>
                    <div style="margin-top:6px;font-size:11px;color:var(--text-secondary);">
                        🎯 ${selLabel}: ${a.first_odds} → <strong style="color:var(--gold-400);">${a.max_odds}</strong>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Ошибка аномалий:', e);
    }
}

function openSnapshotFromAnomaly(fid) {
    switchPage('snapshots');
    setTimeout(() => showSnapshotChart(fid), 500);
}

// ============================================================
