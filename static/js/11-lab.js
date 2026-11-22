// TRAIN/TEST
// ============================================================
async function runTrainTest() {
    const params = {
        min_ev: parseFloat(document.getElementById('tt-min-ev')?.value || 10),
        max_ev: 500,
        min_prob: parseFloat(document.getElementById('tt-min-prob')?.value || 52),
        max_prob: 100,
        min_odds: parseFloat(document.getElementById('tt-min-odds')?.value || 1.4),
        max_odds: parseFloat(document.getElementById('tt-max-odds')?.value || 5.0),
        min_xg: 0, max_xg: 99,
        bet_types: [], leagues: [],
        stake_pct: parseFloat(document.getElementById('tt-stake')?.value || 2.0),
        start_bank: parseFloat(document.getElementById('tt-bank')?.value || 1000),
    };
    const testSize = parseFloat(document.getElementById('tt-test-size')?.value || 30) / 100;

    showNotification('🎓 Запускаю Train/Test...', '');

    const btn = document.querySelector('button[onclick="runTrainTest()"]');
    let oldText = '';
    if (btn) {
        oldText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⏳ Анализ...';
    }

    try {
        const r = await fetch(API_BASE + '/api/simulator/train_test', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ params, test_size: testSize })
        }).then(r => r.json());

        if (r.status !== 'ok') {
            showNotification('❌ ' + (r.error || 'Ошибка'), 'error');
            return;
        }

        const res = r.result;
        if (!res || res.error) {
            showNotification('❌ ' + (res?.error || 'Неизвестная ошибка'), 'error');
            return;
        }

        ttLastResult = res;
        renderTrainTestResults(res);
        showNotification(
            `✅ Train: ${res.train.roi}% | Test: ${res.test.roi}% | Gap: ${res.gap}%`,
            'success'
        );
    } catch (e) {
        console.error('runTrainTest:', e);
        showNotification('❌ Ошибка: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || '🚀 Запустить Train/Test';
        }
    }
}

function renderTrainTestResults(res) {
    const container = document.getElementById('tt-results');
    if (!container) return;
    container.style.display = 'block';

    const train = res.train || {};
    const test = res.test || {};

    const trainRoiEl = document.getElementById('tt-train-roi');
    const testRoiEl = document.getElementById('tt-test-roi');

    if (trainRoiEl) {
        trainRoiEl.textContent = (train.roi || 0) + '%';
        trainRoiEl.style.color = train.roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
    }
    if (testRoiEl) {
        testRoiEl.textContent = (test.roi || 0) + '%';
        testRoiEl.style.color = test.roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
    }

    const gap = res.gap || 0;
    const gapEl = document.getElementById('tt-gap');
    if (gapEl) {
        gapEl.textContent = (gap >= 0 ? '+' : '') + gap + '%';
        gapEl.style.color = gap > 20 ? 'var(--red-400)'
                          : gap > 10 ? 'var(--gold-400)'
                          : 'var(--emerald-400)';
    }

    const verdictEl = document.getElementById('tt-verdict');
    if (verdictEl) {
        verdictEl.textContent = res.verdict || '';
        verdictEl.style.color = gap > 20 ? 'var(--red-400)'
                              : gap > 10 ? 'var(--gold-400)'
                              : 'var(--emerald-400)';
    }

    const tbody = document.getElementById('tt-table-body');
    if (!tbody) return;

    const rows = [
        ['🎲 Ставок', train.total_bets || 0, test.total_bets || 0],
        ['✅ WIN', train.wins || 0, test.wins || 0],
        ['❌ LOSS', train.losses || 0, test.losses || 0],
        ['🔄 PUSH', train.pushes || 0, test.pushes || 0],
        ['🎯 Winrate', (train.winrate || 0) + '%', (test.winrate || 0) + '%'],
        ['💎 ROI', (train.roi || 0) + '%', (test.roi || 0) + '%'],
        [
            '💰 Прибыль',
            (train.profit >= 0 ? '+' : '') + '$' + (train.profit || 0).toFixed(2),
            (test.profit >= 0 ? '+' : '') + '$' + (test.profit || 0).toFixed(2),
        ],
        [
            '🏁 Конец банка',
            '$' + (train.end_bank || 0).toFixed(2),
            '$' + (test.end_bank || 0).toFixed(2),
        ],
        [
            '📉 Просадка',
            (train.max_drawdown || 0) + '%',
            (test.max_drawdown || 0) + '%',
        ],
    ];

    tbody.innerHTML = rows.map(([label, trainVal, testVal]) => `
        <tr>
            <td style="font-weight:700;font-size:11px;">${label}</td>
            <td style="font-size:11px;">${trainVal}</td>
            <td style="font-size:11px;">${testVal}</td>
        </tr>
    `).join('');

    const oldInfo = container.querySelector('.tt-info-line');
    if (oldInfo) oldInfo.remove();

    const infoDiv = document.createElement('div');
    infoDiv.className = 'tt-info-line';
    infoDiv.innerHTML = `
        <div style="font-size:10px;color:var(--text-tertiary);
                    margin-top:12px;padding-top:10px;
                    border-top:1px solid var(--border-color);">
            📊 Всего отфильтровано: <b>${res.total_filtered || 0}</b> матчей •
            🎓 Train: <b>${res.train_count || 0}</b> •
            🧪 Test: <b>${res.test_count || 0}</b>
        </div>
    `;
    container.appendChild(infoDiv);
}

async function runTrainTestGrid() {
    if (!confirm('🎯 Запустить Grid Search + Train/Test?\n\nПереберёт ~100 комбинаций и проверит каждую на Train/Test. Займёт 30-90 сек.')) {
        return;
    }

    showNotification('🎯 Grid Search + Train/Test запущен...', '');

    const btn = document.querySelector('button[onclick="runTrainTestGrid()"]');
    let oldText = '';
    if (btn) {
        oldText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⏳ Поиск (30-90 сек)...';
    }

    try {
        const r = await fetch(API_BASE + '/api/simulator/train_test_grid', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                max_combinations: 100,
                min_bets: 30,
                test_size: parseFloat(document.getElementById('tt-test-size')?.value || 30) / 100,
            })
        }).then(r => r.json());

        if (r.status !== 'ok') {
            showNotification('❌ ' + (r.error || 'Ошибка'), 'error');
            return;
        }

        const top = (r.result && r.result.top) || [];
        if (top.length === 0) {
            showNotification('❌ Не найдено стратегий с ' + (r.result?.total_checked || 0) + ' проверок', 'error');
            return;
        }

        renderTrainTestGridTop5(top, r.result);

        const best = top[0];
        showNotification(
            `🏆 Лучшая: Train ${best.train_roi}% | Test ${best.test_roi}% | Gap ${best.gap}%`,
            'success'
        );
    } catch (e) {
        console.error('runTrainTestGrid:', e);
        showNotification('❌ Ошибка: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || '🎯 Grid Search + Train/Test';
        }
    }
}

function renderTrainTestGridTop5(top, meta) {
    const container = document.getElementById('tt-results');
    if (!container) return;
    container.style.display = 'block';

    let gridDiv = document.getElementById('tt-grid-top5');
    if (gridDiv) gridDiv.remove();

    gridDiv = document.createElement('div');
    gridDiv.id = 'tt-grid-top5';
    gridDiv.className = 'card';
    gridDiv.style.marginTop = '16px';

    const rowsHtml = top.map((t, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : (i + 1);
        const rowStyle = i === 0 ? 'background: rgba(16,185,129,0.08); font-weight:700;' : '';
        const gapColor = t.gap > 20 ? 'var(--red-400)'
                       : t.gap > 10 ? 'var(--gold-400)'
                       : 'var(--emerald-400)';
        const trainRoiColor = t.train_roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
        const testRoiColor = t.test_roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';

        return `
            <tr style="${rowStyle}">
                <td>${medal}</td>
                <td>${t.params?.min_ev || 0}%</td>
                <td>${t.params?.min_prob || 0}%</td>
                <td>${t.params?.min_odds || 0}-${t.params?.max_odds || 0}</td>
                <td>${t.total_bets || 0}</td>
                <td style="color:${trainRoiColor};font-weight:700;">
                    ${t.train_roi >= 0 ? '+' : ''}${t.train_roi}%
                </td>
                <td style="color:${testRoiColor};font-weight:700;">
                    ${t.test_roi >= 0 ? '+' : ''}${t.test_roi}%
                </td>
                <td style="color:${gapColor};font-weight:700;">
                    ${t.gap >= 0 ? '+' : ''}${t.gap}%
                </td>
                <td>${t.train_wr || 0}%</td>
                <td>${t.test_wr || 0}%</td>
            </tr>
        `;
    }).join('');

    const metaHtml = meta ? `
        <div style="font-size:10px;color:var(--text-tertiary);
                    margin-bottom:8px;">
            Проверено: <b>${meta.total_checked || 0}</b> комбинаций •
            Валидных: <b>${meta.total_valid || 0}</b> •
            Показано: <b>${top.length}</b>
        </div>
    ` : '';

    gridDiv.innerHTML = `
        <div class="card-header">
            <h2>🏆 ТОП-5 СТРАТЕГИЙ (Train/Test)</h2>
        </div>
        ${metaHtml}
        <div style="overflow-x:auto;">
            <table style="width:100%; font-size:11px; min-width:600px;">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>EV</th>
                        <th>Prob</th>
                        <th>Кэф</th>
                        <th>Ставок</th>
                        <th>Train ROI</th>
                        <th>Test ROI</th>
                        <th>Gap</th>
                        <th>Train WR</th>
                        <th>Test WR</th>
                    </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        </div>
        <div style="font-size:10px;color:var(--text-tertiary);
                    margin-top:12px;padding-top:10px;
                    border-top:1px solid var(--border-color);">
            💡 <b>Gap</b> = Train ROI - Test ROI.
            <br>• Gap &lt; 5% → ✅ Стабильно
            <br>• Gap 5-15% → 🟠 Небольшой overfit
            <br>• Gap 15-30% → 🟡 Возможен overfit
            <br>• Gap &gt; 30% → 🔴 Сильный overfit
        </div>
    `;

    const resultsCard = container.querySelector('.card');
    if (resultsCard && resultsCard.nextSibling) {
        container.insertBefore(gridDiv, resultsCard.nextSibling);
    } else {
        container.appendChild(gridDiv);
    }
}

function resetTrainTestForm() {
    const defaults = {
        'tt-test-size': 30,
        'tt-min-ev': 10,
        'tt-min-prob': 52,
        'tt-min-odds': 1.4,
        'tt-max-odds': 5.0,
        'tt-stake': 2.0,
        'tt-bank': 1000,
    };
    Object.entries(defaults).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) {
            el.value = val;
            el.dispatchEvent(new Event('input'));
        }
    });

    const container = document.getElementById('tt-results');
    if (container) container.style.display = 'none';

    const grid = document.getElementById('tt-grid-top5');
    if (grid) grid.remove();

    ttLastResult = null;

    showNotification('🔄 Форма сброшена', '');
}

// ============================================================
// 3-WAY SPLIT
// ============================================================
async function run3WaySplit() {
    const params = {
        min_ev: parseFloat(document.getElementById('s3-min-ev')?.value || 10),
        max_ev: 500,
        min_prob: parseFloat(document.getElementById('s3-min-prob')?.value || 52),
        max_prob: 100,
        min_odds: parseFloat(document.getElementById('s3-min-odds')?.value || 1.4),
        max_odds: parseFloat(document.getElementById('s3-max-odds')?.value || 5.0),
        min_xg: 0, max_xg: 99,
        bet_types: [], leagues: [],
        stake_pct: parseFloat(document.getElementById('s3-stake')?.value || 2.0),
        start_bank: parseFloat(document.getElementById('s3-bank')?.value || 1000),
    };
    const testSize = parseFloat(document.getElementById('s3-test-size')?.value || 20) / 100;
    const validSize = parseFloat(document.getElementById('s3-valid-size')?.value || 20) / 100;

    showNotification('🔬 Запускаю 3-Way Split...', '');

    const btn = document.querySelector('button[onclick="run3WaySplit()"]');
    let oldText = '';
    if (btn) {
        oldText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⏳ Анализ...';
    }

    try {
        const r = await fetch(API_BASE + '/api/simulator/3way_split', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ params, test_size: testSize, valid_size: validSize })
        }).then(r => r.json());

        if (r.status !== 'ok') {
            showNotification('❌ ' + (r.error || 'Ошибка'), 'error');
            return;
        }

        const res = r.result;
        if (!res || res.error) {
            showNotification('❌ ' + (res?.error || 'Неизвестная ошибка'), 'error');
            return;
        }

        s3LastResult = res;
        render3WayResults(res);
        showNotification(
            `✅ T:${res.train.roi}% V:${res.valid.roi}% Test:${res.test.roi}% | Spread:${res.spread}%`,
            'success'
        );
    } catch (e) {
        console.error('run3WaySplit:', e);
        showNotification('❌ Ошибка: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || '🔬 Запустить 3-Way Split';
        }
    }
}

function render3WayResults(res) {
    const container = document.getElementById('s3-results');
    if (!container) return;
    container.style.display = 'block';

    const t = res.train || {}, v = res.valid || {}, ts = res.test || {};

    const setVal = (id, val, color) => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = (val >= 0 ? '+' : '') + val + '%';
            el.style.color = color || (val >= 0 ? 'var(--emerald-400)' : 'var(--red-400)');
        }
    };

    setVal('s3-train-roi', t.roi || 0);
    setVal('s3-valid-roi', v.roi || 0);
    setVal('s3-test-roi', ts.roi || 0);

    const gapEl = document.getElementById('s3-gap');
    const gap = res.gap || 0;
    if (gapEl) {
        gapEl.textContent = (gap >= 0 ? '+' : '') + gap + '%';
        gapEl.style.color = gap > 20 ? 'var(--red-400)' : gap > 10 ? 'var(--gold-400)' : 'var(--emerald-400)';
    }

    const spreadEl = document.getElementById('s3-spread');
    const spread = res.spread || 0;
    if (spreadEl) {
        spreadEl.textContent = spread + '%';
        spreadEl.style.color = spread > 25 ? 'var(--red-400)' : spread > 15 ? 'var(--gold-400)' : 'var(--emerald-400)';
    }

    const verdictEl = document.getElementById('s3-verdict');
    if (verdictEl) {
        verdictEl.textContent = res.verdict || '';
        const colors = {
            'green': 'var(--emerald-400)', 'red': 'var(--red-400)',
            'gold': 'var(--gold-400)', 'orange': '#fb923c',
            'blue': 'var(--blue-400)', 'gray': 'var(--text-tertiary)'
        };
        verdictEl.style.color = colors[res.verdict_color] || 'var(--text-primary)';
    }

    const tbody = document.getElementById('s3-table-body');
    if (tbody) {
        const rows = [
            ['🎲 Ставок', t.total_bets||0, v.total_bets||0, ts.total_bets||0],
            ['✅ WIN', t.wins||0, v.wins||0, ts.wins||0],
            ['❌ LOSS', t.losses||0, v.losses||0, ts.losses||0],
            ['🎯 Winrate', (t.winrate||0)+'%', (v.winrate||0)+'%', (ts.winrate||0)+'%'],
            ['💎 ROI', (t.roi||0)+'%', (v.roi||0)+'%', (ts.roi||0)+'%'],
            ['💰 Прибыль',
                (t.profit>=0?'+':'')+'$'+(t.profit||0).toFixed(2),
                (v.profit>=0?'+':'')+'$'+(v.profit||0).toFixed(2),
                (ts.profit>=0?'+':'')+'$'+(ts.profit||0).toFixed(2)],
            ['🏁 Банк',
                '$'+(t.end_bank||0).toFixed(2),
                '$'+(v.end_bank||0).toFixed(2),
                '$'+(ts.end_bank||0).toFixed(2)],
            ['📉 Просадка', (t.max_drawdown||0)+'%', (v.max_drawdown||0)+'%', (ts.max_drawdown||0)+'%'],
        ];
        tbody.innerHTML = rows.map(([label, a, b, c]) => `
            <tr>
                <td style="font-weight:700;font-size:11px;">${label}</td>
                <td style="font-size:11px;">${a}</td>
                <td style="font-size:11px;">${b}</td>
                <td style="font-size:11px;">${c}</td>
            </tr>
        `).join('');
    }

    const oldInfo = container.querySelector('.s3-info-line');
    if (oldInfo) oldInfo.remove();
    const infoDiv = document.createElement('div');
    infoDiv.className = 's3-info-line';
    infoDiv.innerHTML = `
        <div style="font-size:10px;color:var(--text-tertiary);
                    margin-top:12px;padding-top:10px;
                    border-top:1px solid var(--border-color);">
            📊 Всего отфильтровано: <b>${res.total_filtered||0}</b> •
            🎓 Train: <b>${res.train_count||0}</b> •
            📊 Valid: <b>${res.valid_count||0}</b> •
            🧪 Test: <b>${res.test_count||0}</b> •
            📈 OOS: <b>${res.oos_roi||0}%</b>
        </div>
    `;
    container.appendChild(infoDiv);
}

async function run3WaySplitGrid() {
    if (!confirm('🎯 Запустить Grid Search + 3-Way Split?\n\nПереберёт ~100 комбинаций по Train/Validate/Test. Займёт 60-120 сек.')) return;

    showNotification('🎯 Grid Search + 3-Way Split запущен...', '');

    const btn = document.querySelector('button[onclick="run3WaySplitGrid()"]');
    let oldText = '';
    if (btn) {
        oldText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⏳ Поиск (60-120 сек)...';
    }

    try {
        const r = await fetch(API_BASE + '/api/simulator/3way_split_grid', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                max_combinations: 100,
                min_bets: 30,
                test_size: parseFloat(document.getElementById('s3-test-size')?.value || 20) / 100,
                valid_size: parseFloat(document.getElementById('s3-valid-size')?.value || 20) / 100,
            })
        }).then(r => r.json());

        if (r.status !== 'ok') {
            showNotification('❌ ' + (r.error || 'Ошибка'), 'error');
            return;
        }

        const top = (r.result && r.result.top) || [];
        if (top.length === 0) {
            showNotification('❌ Не найдено стратегий', 'error');
            return;
        }

        render3WayGridTop5(top, r.result);

        const best = top[0];
        showNotification(
            `🏆 Train ${best.train_roi}% | Valid ${best.valid_roi}% | Test ${best.test_roi}%`,
            'success'
        );
    } catch (e) {
        console.error('run3WaySplitGrid:', e);
        showNotification('❌ Ошибка: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || '🎯 Grid Search + 3-Way Split';
        }
    }
}

function render3WayGridTop5(top, meta) {
    const container = document.getElementById('s3-results');
    if (!container) return;
    container.style.display = 'block';

    let gridDiv = document.getElementById('s3-grid-top5');
    if (gridDiv) gridDiv.remove();

    gridDiv = document.createElement('div');
    gridDiv.id = 's3-grid-top5';
    gridDiv.className = 'card';
    gridDiv.style.marginTop = '16px';

    const rowsHtml = top.map((t, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : (i + 1);
        const rowStyle = i === 0 ? 'background: rgba(16,185,129,0.08); font-weight:700;' : '';
        const spreadColor = t.spread > 25 ? 'var(--red-400)' : t.spread > 15 ? 'var(--gold-400)' : 'var(--emerald-400)';
        return `
            <tr style="${rowStyle}">
                <td>${medal}</td>
                <td>${t.params?.min_ev || 0}%</td>
                <td>${t.params?.min_prob || 0}%</td>
                <td>${t.params?.min_odds || 0}-${t.params?.max_odds || 0}</td>
                <td>${t.train_bets || 0}/${t.valid_bets || 0}/${t.test_bets || 0}</td>
                <td style="color:${t.train_roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">
                    ${t.train_roi >= 0 ? '+' : ''}${t.train_roi}%
                </td>
                <td style="color:${t.valid_roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">
                    ${t.valid_roi >= 0 ? '+' : ''}${t.valid_roi}%
                </td>
                <td style="color:${t.test_roi >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">
                    ${t.test_roi >= 0 ? '+' : ''}${t.test_roi}%
                </td>
                <td style="color:${spreadColor};font-weight:700;">${t.spread}%</td>
            </tr>
        `;
    }).join('');

    const metaHtml = meta ? `
        <div style="font-size:10px;color:var(--text-tertiary);margin-bottom:8px;">
            Проверено: <b>${meta.total_checked || 0}</b> •
            Валидных: <b>${meta.total_valid || 0}</b> •
            Показано: <b>${top.length}</b>
        </div>
    ` : '';

    gridDiv.innerHTML = `
        <div class="card-header"><h2>🏆 ТОП-5 СТРАТЕГИЙ (3-Way)</h2></div>
        ${metaHtml}
        <div style="overflow-x:auto;">
            <table style="width:100%; font-size:11px; min-width:700px;">
                <thead>
                    <tr>
                        <th>#</th><th>EV</th><th>Prob</th><th>Кэф</th>
                        <th>Tr/Va/Te</th>
                        <th>🎓 Train</th><th>📊 Valid</th><th>🧪 Test</th>
                        <th>Spread</th>
                    </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        </div>
        <div style="font-size:10px;color:var(--text-tertiary);
                    margin-top:12px;padding-top:10px;
                    border-top:1px solid var(--border-color);">
            💡 <b>Spread</b> = разброс между тремя ROI.
            <br>• Spread &lt; 10% → ✅ Стабильно
            <br>• Spread 10-25% → 🟡 Умеренно
            <br>• Spread &gt; 25% → 🔴 Нестабильно
        </div>
    `;

    const resultsCard = container.querySelector('.card');
    if (resultsCard && resultsCard.nextSibling) {
        container.insertBefore(gridDiv, resultsCard.nextSibling);
    } else {
        container.appendChild(gridDiv);
    }
}

function reset3WayForm() {
    const defaults = {
        's3-test-size': 20, 's3-valid-size': 20,
        's3-min-ev': 10, 's3-min-prob': 52,
        's3-min-odds': 1.4, 's3-max-odds': 5.0,
        's3-stake': 2.0, 's3-bank': 1000,
    };
    Object.entries(defaults).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) { el.value = val; el.dispatchEvent(new Event('input')); }
    });
    const container = document.getElementById('s3-results');
    if (container) container.style.display = 'none';
    const grid = document.getElementById('s3-grid-top5');
    if (grid) grid.remove();
    s3LastResult = null;
    showNotification('🔄 Форма сброшена', '');
}

// ============================================================
// КАЛИБРОВКА
// ============================================================
async function loadCalibration() {
    const container = document.getElementById('calibrationContent');
    if (!container) return;

    container.innerHTML = `
        <div class="skeleton" style="height:100px;"></div>
        <div class="skeleton" style="height:150px;"></div>
        <div class="skeleton" style="height:100px;"></div>
    `;

    try {
        const resp = await fetch(API_BASE + '/api/calibration?t=' + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();

        if (data.status !== 'ok') throw new Error(data.error || 'API error');

        if (data.total === 0) {
            container.innerHTML = `
                <div class="no-data">
                    <div class="emoji">📭</div>
                    <div class="title">Нет данных</div>
                    <div class="desc">Нужно ≥50 завершённых ставок с prob</div>
                </div>
            `;
            return;
        }

        renderCalibration(data);
    } catch (e) {
        console.error('loadCalibration:', e);
        container.innerHTML = `
            <div style="padding:12px;color:var(--red-400);font-size:12px;">
                ❌ Ошибка: ${e.message}
                <button class="btn btn-outline" onclick="loadCalibration()" style="margin-left:8px;padding:2px 8px;font-size:10px;">🔄</button>
            </div>
        `;
    }
}

function renderCalibration(data) {
    const container = document.getElementById('calibrationContent');
    if (!container) return;

    const ov = data.overall;
    const diff = ov.diff;
    let verdict, verdictColor, verdictEmoji, verdictDesc;

    if (Math.abs(diff) < 3) {
        verdict = 'ХОРОШАЯ КАЛИБРОВКА';
        verdictColor = 'var(--emerald-400)';
        verdictEmoji = '✅';
        verdictDesc = 'Модель точна. EV можно доверять.';
    } else if (diff < -10) {
        verdict = 'СИЛЬНО ЗАВЫШАЕТ';
        verdictColor = 'var(--red-400)';
        verdictEmoji = '🔴';
        verdictDesc = `Модель даёт prob на ${Math.abs(diff).toFixed(1)}% выше реальности. EV фиктивный.`;
    } else if (diff < -3) {
        verdict = 'ЗАВЫШАЕТ';
        verdictColor = 'var(--gold-400)';
        verdictEmoji = '🟡';
        verdictDesc = `Модель завышает prob на ${Math.abs(diff).toFixed(1)}%. EV завышен.`;
    } else if (diff > 10) {
        verdict = 'СИЛЬНО ЗАНИЖАЕТ';
        verdictColor = 'var(--blue-400)';
        verdictEmoji = '🔵';
        verdictDesc = `Модель недооценивает на ${diff.toFixed(1)}%. Есть скрытый edge.`;
    } else {
        verdict = 'ЗАНИЖАЕТ';
        verdictColor = 'var(--blue-400)';
        verdictEmoji = '🔵';
        verdictDesc = `Модель занижает prob на ${diff.toFixed(1)}%.`;
    }

    let html = `
        <div class="card" style="border-color:${verdictColor}40;">
            <div class="card-header">
                <h2 style="color:${verdictColor};">${verdictEmoji} ${verdict}</h2>
            </div>
            <div style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                ${verdictDesc}
            </div>
            <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);">
                <div class="stat-card">
                    <div class="value">${ov.predicted}%</div>
                    <div class="label">📊 Прогноз</div>
                </div>
                <div class="stat-card">
                    <div class="value ${diff >= 0 ? 'green' : 'red'}">${ov.actual}%</div>
                    <div class="label">🎯 Реальность</div>
                </div>
                <div class="stat-card">
                    <div class="value" style="color:${verdictColor};">
                        ${diff >= 0 ? '+' : ''}${diff}%
                    </div>
                    <div class="label">📈 Разница</div>
                </div>
            </div>
            <div style="font-size:11px;color:var(--text-tertiary);margin-top:10px;">
                Всего ставок: <b>${data.total}</b> •
                Калибровочный коэффициент: <b style="color:${verdictColor};">${ov.calibration_factor}</b>
            </div>
        </div>
    `;

    if (data.buckets && data.buckets.length > 0) {
        html += `
            <div class="card">
                <div class="card-header">
                    <h2>📊 По бакетам</h2>
                </div>
                <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:8px;">
                    Если "Реально" &lt; "Модель" → переоценка
                </div>
        `;

        data.buckets.forEach(b => {
            const ok = Math.abs(b.diff) < 5;
            const warn = Math.abs(b.diff) < 10;
            const color = ok ? 'var(--emerald-400)' : warn ? 'var(--gold-400)' : 'var(--red-400)';
            const icon = ok ? '🟢' : warn ? '🟡' : '🔴';

            html += `
                <div style="padding:8px 0;border-bottom:1px solid var(--border-color);">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;">
                        <span style="font-weight:700;">${icon} ${b.range}</span>
                        <span style="color:var(--text-tertiary);font-size:10px;">${b.count} ставок</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;">
                        <span style="color:var(--text-tertiary);">
                            Модель: <b style="color:var(--text-primary);">${b.predicted}%</b>
                        </span>
                        <span style="color:var(--text-tertiary);">
                            Реально: <b style="color:var(--text-primary);">${b.actual}%</b>
                        </span>
                        <span style="color:${color};font-weight:700;">
                            ${b.diff >= 0 ? '+' : ''}${b.diff}%
                        </span>
                    </div>
                </div>
            `;
        });

        html += `</div>`;
    }

    if (data.sources && data.sources.length > 0) {
        html += `
            <div class="card">
                <div class="card-header">
                    <h2>💎 По стратегиям</h2>
                </div>
        `;

        data.sources.sort((a, b) => a.diff - b.diff).forEach(s => {
            const ok = Math.abs(s.diff) < 5;
            const color = ok ? 'var(--emerald-400)' : (s.diff < 0 ? 'var(--red-400)' : 'var(--blue-400)');
            const labelMap = {
                '70_percent': '🎯 70%+',
                'value': '💎 VALUE',
                'x2': '🔥 X2',
                'btts': '⚽ BTTS',
                'tm25_premium': '🔥 ТМ 2.5 PREMIUM',
                'tm25_standard': '⭐ ТМ 2.5',
                'line_movement': '📈 LINE MOVEMENT',
            };
            const label = labelMap[s.source] || s.source;

            html += `
                <div style="padding:10px 0;border-bottom:1px solid var(--border-color);">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:12px;font-weight:700;">${label}</span>
                        <span style="color:${color};font-weight:700;font-size:13px;">
                            ${s.diff >= 0 ? '+' : ''}${s.diff}%
                        </span>
                    </div>
                    <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">
                        ${s.count} ставок • модель ${s.avg_prob}% → реально ${s.avg_actual}%
                    </div>
                </div>
            `;
        });

        html += `</div>`;
    }

    html += `
        <div class="card" style="background:rgba(16,185,129,0.04);">
            <div class="card-header">
                <h2 class="emerald-title">💡 Что это значит</h2>
            </div>
            <div style="font-size:11px;color:var(--text-secondary);line-height:1.6;">
                • Если модель <b>завышает</b> prob — EV фиктивный, ставки переоценены<br>
                • Если <b>занижает</b> — есть скрытый edge<br>
                • Если <b>точно</b> — можно доверять EV и Kelly<br>
                • <b>Калибровочный коэффициент</b> = actual / predicted<br>
                &nbsp;&nbsp;&nbsp;×0.8 → умножать prob на 0.8 перед EV<br>
                &nbsp;&nbsp;&nbsp;×1.1 → умножать на 1.1 (есть edge)
            </div>
        </div>
    `;

    container.innerHTML = html;
}

async function loadCalibrationSnapshots() {
    const container = document.getElementById('calibrationSnapshotsList');
    if (!container) return;

    try {
        const resp = await fetch(API_BASE + '/api/calibration/snapshots?t=' + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();

        if (data.status !== 'ok') throw new Error(data.error || 'API error');

        if (!data.snapshots || data.snapshots.length === 0) {
            container.innerHTML = `
                <div style="padding:12px;text-align:center;color:var(--text-tertiary);font-size:11px;">
                    📭 Пока нет сохранённых снапшотов.<br>
                    Первый сохранится автоматически 1-го или 15-го числа.
                </div>
            `;
            return;
        }

        renderCalibrationSnapshots(data.snapshots);
    } catch (e) {
        console.error('loadCalibrationSnapshots:', e);
        container.innerHTML = `
            <div style="padding:12px;color:var(--red-400);font-size:11px;">
                ❌ Ошибка: ${e.message}
            </div>
        `;
    }
}

function renderCalibrationSnapshots(snapshots) {
    const container = document.getElementById('calibrationSnapshotsList');
    if (!container) return;

    let comparisonHtml = '';
    if (snapshots.length >= 2) {
        const [latest, prev] = snapshots;
        const diffOverall = (latest.overall.actual - prev.overall.actual).toFixed(1);
        const diffPredicted = (latest.overall.predicted - prev.overall.predicted).toFixed(1);
        const diffCount = latest.total - prev.total;

        comparisonHtml = `
            <div style="padding:12px;background:rgba(16,185,129,0.06);
                        border-radius:10px;border:1px solid rgba(16,185,129,0.2);
                        margin-bottom:12px;">
                <div style="font-size:11px;color:var(--emerald-400);font-weight:700;
                            text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">
                    📊 Сравнение (последние 2)
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center;">
                    <div>
                        <div style="font-size:9px;color:var(--text-tertiary);">СТАВОК</div>
                        <div style="font-size:14px;font-weight:800;">${latest.total}</div>
                        <div style="font-size:9px;color:${diffCount >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">
                            ${diffCount >= 0 ? '+' : ''}${diffCount}
                        </div>
                    </div>
                    <div>
                        <div style="font-size:9px;color:var(--text-tertiary);">МОДЕЛЬ</div>
                        <div style="font-size:14px;font-weight:800;">${latest.overall.predicted}%</div>
                        <div style="font-size:9px;color:var(--text-tertiary);">
                            ${diffPredicted >= 0 ? '+' : ''}${diffPredicted}%
                        </div>
                    </div>
                    <div>
                        <div style="font-size:9px;color:var(--text-tertiary);">РЕАЛЬНО</div>
                        <div style="font-size:14px;font-weight:800;">${latest.overall.actual}%</div>
                        <div style="font-size:9px;color:${diffOverall >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">
                            ${diffOverall >= 0 ? '+' : ''}${diffOverall}%
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    const itemsHtml = snapshots.map((s, idx) => {
        const ov = s.overall || {};
        const diff = ov.diff || 0;
        const verdict = diff < -10 ? '🔴' : diff < -3 ? '🟡' : diff > 3 ? '🔵' : '✅';

        let ageStr = '';
        try {
            const savedTs = s.saved_at_ts || 0;
            const ageHours = (Date.now() / 1000 - savedTs) / 3600;
            if (ageHours < 24) {
                ageStr = `<span style="font-size:9px;color:var(--gold-400);">
                    (удалится через ${Math.round(24 - ageHours)}ч)
                </span>`;
            } else {
                ageStr = `<span style="font-size:9px;color:var(--text-tertiary);">архив</span>`;
            }
        } catch (e) {}

        const isLatest = idx === 0;
        const borderColor = isLatest ? 'rgba(16,185,129,0.4)' : 'var(--border-color)';

        return `
            <div style="padding:10px;border-radius:8px;
                        background:${isLatest ? 'rgba(16,185,129,0.05)' : 'rgba(255,255,255,0.02)'};
                        border:1px solid ${borderColor};
                        margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div>
                        <span style="font-size:11px;font-weight:700;">
                            ${isLatest ? '🆕 ' : '📁 '}${s.saved_at}
                        </span>
                        ${ageStr}
                    </div>
                    <button class="btn btn-outline"
                            onclick="deleteCalibrationSnapshot(${idx})"
                            style="padding:2px 6px;font-size:9px;">✕</button>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:10px;">
                    <div>
                        <div style="color:var(--text-tertiary);">Модель</div>
                        <div style="font-weight:700;">${ov.predicted || 0}%</div>
                    </div>
                    <div>
                        <div style="color:var(--text-tertiary);">Реально</div>
                        <div style="font-weight:700;">${ov.actual || 0}%</div>
                    </div>
                    <div>
                        <div style="color:var(--text-tertiary);">Разница</div>
                        <div style="font-weight:700;color:${diff >= 0 ? 'var(--emerald-400)' : 'var(--red-400)'};">
                            ${verdict} ${diff >= 0 ? '+' : ''}${diff}%
                        </div>
                    </div>
                </div>
                <div style="font-size:9px;color:var(--text-tertiary);margin-top:4px;">
                    Ставок: ${s.total || 0} • фактор: ${ov.calibration_factor || 1.0}
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = comparisonHtml + itemsHtml;
}

async function saveCalibrationSnapshot() {
    if (!confirm('💾 Сохранить текущий снапшот калибровки?\n\nБудет добавлен к существующим (максимум 2).')) return;
    showNotification('💾 Сохраняю...', '');
    try {
        const r = await fetch(API_BASE + '/api/calibration/save', { method: 'POST' }).then(r => r.json());
        if (r.status === 'ok') {
            showNotification('✅ Снапшот сохранён', 'success');
            loadCalibrationSnapshots();
        } else {
            showNotification('❌ Ошибка: ' + (r.error || 'неизвестно'), 'error');
        }
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function deleteCalibrationSnapshot(idx) {
    if (!confirm('Удалить этот снапшот?')) return;
    try {
        const r = await fetch(API_BASE + `/api/calibration/snapshots/${idx}`, { method: 'DELETE' }).then(r => r.json());
        if (r.status === 'ok') {
            showNotification('🗑️ Удалено', '');
            loadCalibrationSnapshots();
        }
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

async function loadCalibrationFull() {
    await Promise.all([
        loadCalibration(),
        loadCalibrationSnapshots(),
    ]);
}

// ============================================================
