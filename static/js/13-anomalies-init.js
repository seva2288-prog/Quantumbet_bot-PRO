// ★ v23.3: АНОМАЛИИ (пропущенные матчи)
// ============================================================
async function loadAnomalies() {
    const statsEl = document.getElementById('anomalyStatsGrid');
    const listEl = document.getElementById('anomaliesList');
    const hypEl = document.getElementById('anomalyHypothetical');
    if (!statsEl || !listEl) return;

    statsEl.innerHTML = '<div class="skeleton" style="height:60px;"></div>'.repeat(4);
    listEl.innerHTML = '<div class="skeleton" style="height:80px;"></div>'.repeat(2);

    try {
        const resp = await fetch(API_BASE + '/api/anomalies?t=' + Date.now());
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (data.status !== 'ok') throw new Error(data.error || 'API error');

        const s = data.stats || {};

        statsEl.innerHTML = `
            <div class="stat-card">
                <div class="value">${s.total || 0}</div>
                <div class="label">🚫 Всего</div>
            </div>
            <div class="stat-card">
                <div class="value green">${s.wins || 0}</div>
                <div class="label">✅ WIN</div>
            </div>
            <div class="stat-card">
                <div class="value red">${s.losses || 0}</div>
                <div class="label">❌ LOSS</div>
            </div>
            <div class="stat-card">
                <div class="value gold">${s.hit_rate || 0}%</div>
                <div class="label">🎯 Hit Rate</div>
            </div>
        `;

        if (hypEl) {
            const profit = s.hypothetical_profit || 0;
            const color = profit >= 0 ? 'var(--emerald-400)' : 'var(--red-400)';
            const stake = s.stake_per_bet || 50;
            hypEl.innerHTML = `
                <div style="text-align:center;padding:12px;background:rgba(255,255,255,0.02);border-radius:10px;margin-top:12px;">
                    <div style="font-size:10px;color:var(--text-tertiary);">
                        Если бы ставили $${stake} на каждый пропущенный
                    </div>
                    <div style="font-size:24px;font-weight:800;color:${color};margin-top:4px;">
                        ${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}
                    </div>
                    <div style="font-size:10px;color:var(--text-tertiary);margin-top:4px;">
                        ${profit < 0 ? '✅ Фильтр спас банк' : '⚠️ Фильтр зря пропускает матчи'}
                    </div>
                </div>
            `;
        }

        let items = data.items || [];

        const filterEl = document.getElementById('anomalyFilter');
        const filter = filterEl ? (filterEl.value || 'all') : 'all';

        if (filter === 'unknown') {
            items = items.filter(x => {
                const r = (x.result || 'pending').toLowerCase();
                return r !== 'win' && r !== 'loss' && r !== 'pending';
            });
        } else if (filter !== 'all') {
            items = items.filter(x => (x.result || 'pending').toLowerCase() === filter);
        }

        if (items.length === 0) {
            listEl.innerHTML = `
                <div class="no-data" style="padding:20px;">
                    <div class="emoji">📭</div>
                    <div class="desc">Пока нет аномалий</div>
                </div>
            `;
            return;
        }

        let html = '';
        for (let i = 0; i < items.length; i++) {
            const it = items[i];
            const r = (it.result || 'pending').toLowerCase();
            const emoji = r === 'win' ? '✅' : (r === 'loss' ? '❌' : '⏳');
            const resultColor = r === 'win' ? 'var(--emerald-400)' :
                               (r === 'loss' ? 'var(--red-400)' : 'var(--gold-400)');
            let resultBadge;
            if (r === 'win') resultBadge = 'WIN';
            else if (r === 'loss') resultBadge = 'LOSS';
            else if (r === 'pending') resultBadge = 'PENDING';
            else resultBadge = 'UNKNOWN';

            const home = it.home || '?';
            const away = it.away || '?';
            const league = it.league || '—';
            const bestOdds = it.best_odds || 0;
            const avgOdds = it.avg_odds || 0;
            const diff = it.diff || 0;
            const anomalyPct = it.anomaly_pct || 0;
            const betType = it.bet_type || 'VALUE';

            const scoreStr = (it.home_goals != null && it.away_goals != null)
                ? `${it.home_goals}-${it.away_goals}` : '';

            const buttonHtml = (r === 'pending' || resultBadge === 'UNKNOWN') ? `
                <div style="margin-top:8px;">
                    <button class="btn btn-outline"
                            onclick="event.stopPropagation();openAnomalyResultModal(${it.fixture_id}, '${(it.selection || '').replace(/'/g, "\\'")}', '${(home + ' vs ' + away).replace(/'/g, "\\'")}')"
                            style="padding:6px 10px;font-size:11px;width:100%;">
                        ✏️ Ввести счёт
                    </button>
                </div>
            ` : '';

            html += `
                <div class="snapshot-card has-anomaly" style="margin-bottom:10px;">
                    <div class="snapshot-header">
                        <div style="flex:1;min-width:0;">
                            <div class="snapshot-match">
                                ${emoji} ${home} vs ${away}
                            </div>
                            <div class="snapshot-meta">
                                🏆 ${league}
                            </div>
                            <div class="snapshot-meta">
                                🎯 ${betType}${it.selection ? ' • ' + it.selection : ''} ${scoreStr ? '• Счёт: ' + scoreStr : ''}
                            </div>
                        </div>
                        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                            <div class="snapshot-badge anomaly" style="background:rgba(245,158,11,0.15);color:${resultColor};border-color:${resultColor}40;">
                                ${resultBadge}
                            </div>
                            <div style="font-size:10px;color:var(--gold-400);font-weight:700;">
                                +${anomalyPct}%
                            </div>
                        </div>
                    </div>
                    <div class="snapshot-trends">
                        <div class="snapshot-trend">
                            <span class="trend-label">Best</span>
                            <span class="trend-values" style="color:var(--gold-400);font-weight:800;">${bestOdds}</span>
                        </div>
                        <div class="snapshot-trend">
                            <span class="trend-label">Avg</span>
                            <span class="trend-values">${avgOdds}</span>
                        </div>
                        <div class="snapshot-trend">
                            <span class="trend-label">Diff</span>
                            <span class="trend-values" style="color:var(--emerald-400);">+${diff}</span>
                        </div>
                    </div>
                    <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border-color);font-size:10px;color:var(--text-tertiary);text-align:center;">
                        🚫 Пропущен фильтром (разброс букмекеров > 0.5)
                    </div>
                    ${buttonHtml}
                </div>
            `;
        }
        listEl.innerHTML = html;

    } catch (e) {
        console.error('loadAnomalies error:', e);
        if (listEl) listEl.innerHTML = `
            <div class="no-data">
                <div class="emoji">⚠️</div>
                <div class="desc">Ошибка: ${e.message}</div>
            </div>
        `;
    }
}

// ============================================================
// ANOMALY SET RESULT — РУЧНОЕ ОБНОВЛЕНИЕ
// ============================================================
function openAnomalyResultModal(fixtureId, selection, matchName) {
    const modal = document.getElementById('anomalyResultModal');
    if (!modal) {
        console.error('anomalyResultModal not found in DOM!');
        showNotification('❌ Модалка не найдена', 'error');
        return;
    }
    document.getElementById('anomalyResultFixtureId').value = fixtureId || '';
    document.getElementById('anomalyResultSelection').value = selection || '';
    document.getElementById('anomalyResultMatch').textContent = '🏟️ ' + matchName;
    document.getElementById('anomalyResultHome').value = 0;
    document.getElementById('anomalyResultAway').value = 0;
    modal.classList.add('active');
    haptic(8);
}

function closeAnomalyResultModal() {
    const modal = document.getElementById('anomalyResultModal');
    if (modal) modal.classList.remove('active');
}

async function saveAnomalyResult() {
    const fixtureId = parseInt(document.getElementById('anomalyResultFixtureId').value);
    const selection = document.getElementById('anomalyResultSelection').value;
    const hg = parseInt(document.getElementById('anomalyResultHome').value) || 0;
    const ag = parseInt(document.getElementById('anomalyResultAway').value) || 0;

    if (!fixtureId) {
        showNotification('❌ Нет ID матча', 'error');
        return;
    }

    try {
        const resp = await fetch(API_BASE + '/api/anomaly_set_result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fixture_id: fixtureId,
                home_goals: hg,
                away_goals: ag,
                selection: selection,
            })
        });
        const data = await resp.json();
        if (data.status === 'ok') {
            showNotification(`✅ ${data.result.toUpperCase()}: ${hg}:${ag}`, 'success');
            closeAnomalyResultModal();
            await loadAnomalies();
        } else {
            showNotification('❌ ' + (data.error || 'Ошибка'), 'error');
        }
    } catch (e) {
        showNotification('❌ ' + e.message, 'error');
    }
}

// ============================================================
// ФИНАЛЬНЫЙ ЗАПУСК
// ============================================================
window.addEventListener('load', async () => {
    try { viewMode = safeLSGet('viewMode', 'cards'); } catch (e) { viewMode = 'cards'; }  // ★ FIX #12
    setViewMode(viewMode);
    await loadPageData('dashboard');
    loadAutoX2();
    startKeepAlive();
    startAutoRefresh();
    autoImportInterval = setInterval(autoImportX2FromLogs, AUTO_IMPORT_MS);
    setTimeout(autoImportX2FromLogs, 5000);
    registerPWA();

    try {
        const resp = await fetch(API_BASE + '/api/live?t=' + Date.now());
        if (resp.ok) {
            const data = await resp.json();
            if (data.status === 'ok') {
                const liveCount = (data.matches || []).filter(m => m.is_live).length;
                const badge = document.getElementById('liveNavBadge');
                if (badge && liveCount > 0) {
                    badge.textContent = liveCount;
                    badge.style.display = 'flex';
                }
            }
        }
    } catch (e) {}
});

document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('active');
    });
});

// ============================================================
// ЭКСПОРТ В WINDOW
// ============================================================

async function loadLab() {
    const container = document.getElementById('labList');
    if (!container) return;
    container.innerHTML = '<div class="skeleton" style="height:100px;margin-bottom:10px;"></div>';

    try {
        const resp = await fetch(API_BASE + '/api/lab?t=' + Date.now());
        const data = await resp.json();

        let total = data.items ? data.items.length : 0;
        let wins = data.items ? data.items.filter(i => i.result === 'win').length : 0;
        let losses = data.items ? data.items.filter(i => i.result === 'loss').length : 0;
        let resolved = wins + losses;
        let winrate = resolved > 0 ? Math.round((wins / resolved) * 100) : 0;

        const elTotal = document.getElementById('lab-stat-total');
        const elWins = document.getElementById('lab-stat-wins');
        const elLosses = document.getElementById('lab-stat-losses');
        const elWinrate = document.getElementById('lab-stat-winrate');

        if (elTotal) elTotal.textContent = total;
        if (elWins) elWins.textContent = wins;
        if (elLosses) elLosses.textContent = losses;
        if (elWinrate) elWinrate.textContent = winrate + '%';

        if (data.status !== 'ok' || !data.items.length) {
            container.innerHTML = '<div class="no-data"><div class="emoji">🧪</div><div class="title">Лаборатория пуста</div><div class="desc">Здесь появятся аномалии (EV > 50%)</div></div>';
            return;
        }

        container.innerHTML = data.items.map(it => {
            const evColor = it.ev > 100 ? 'var(--red-400)' : 'var(--gold-400)';
            let statusBadge = '';
            if (it.result === 'win') statusBadge = '<span class="badge win">✅ WIN</span>';
            else if (it.result === 'loss') statusBadge = '<span class="badge loss">❌ LOSS</span>';
            else statusBadge = '<span class="badge pending">⏳ PENDING</span>';

            const scoreStr = (it.home_goals != null && it.away_goals != null)
                ? ` • ${it.home_goals}-${it.away_goals}` : '';

            // ★ НОВОЕ: кнопка ручного ввода только для pending
            const buttonHtml = (it.result === 'pending' || !it.result) ? `
                <div style="margin-top:10px;">
                    <button class="btn btn-outline"
                            onclick='event.stopPropagation(); openLabResultModal(
                                ${it.fixture_id},
                                ${JSON.stringify(it.reverse_bet || "")},
                                ${JSON.stringify((it.home || "?") + " vs " + (it.away || "?"))}
                            )'
                            style="padding:8px 12px;font-size:11px;width:100%;">
                        ✏️ Ввести счёт вручную
                    </button>
                </div>
            ` : '';

            return `
                <div class="card" style="padding:14px;margin-bottom:10px;">
                    <div class="bet-header" style="margin-bottom:8px;">
                        <div style="flex:1;min-width:0;">
                            <div class="bet-match">${escapeHtml(it.home)} vs ${escapeHtml(it.away)}</div>
                            <div class="bet-league">🏆 ${escapeHtml(it.league || '—')}</div>
                            <div class="bet-time">📅 ${escapeHtml(it.date || '—')}${scoreStr}</div>
                        </div>
                        <div style="text-align:right;">
                            ${statusBadge}
                        </div>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;padding-top:10px;border-top:1px solid var(--border-color);">
                        <div>
                            <div style="font-size:10px;color:var(--text-tertiary);">Модель</div>
                            <div style="font-size:13px;font-weight:700;">${escapeHtml(it.original_bet || '—')} @ ${it.odds}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:10px;color:var(--text-tertiary);">Обратная</div>
                            <div style="font-size:13px;font-weight:700;color:var(--emerald-400);">${escapeHtml(it.reverse_bet || '—')}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:10px;color:var(--text-tertiary);">EV</div>
                            <div style="font-size:13px;font-weight:700;color:${evColor};">+${it.ev}%</div>
                        </div>
                    </div>
                    ${buttonHtml}
                </div>
            `;
        }).join('');
    } catch(e) {
        container.innerHTML = '<div class="no-data">Ошибка загрузки</div>';
    }
}

// ============================================================
// ★ РУЧНОЙ ВВОД РЕЗУЛЬТАТА В ЛАБОРАТОРИИ
// ============================================================
function openLabResultModal(fixtureId, reverseBet, matchName) {
    const modal = document.getElementById('labResultModal');
    if (!modal) {
        showNotification('❌ Модалка не найдена', 'error');
        return;
    }
    document.getElementById('labResultFixtureId').value = fixtureId || '';
    document.getElementById('labResultReverseBet').value = reverseBet || '';
    document.getElementById('labResultMatch').textContent = '🏟️ ' + matchName;
    document.getElementById('labResultBetLabel').textContent = reverseBet || '—';
    document.getElementById('labResultHome').value = 0;
    document.getElementById('labResultAway').value = 0;
    modal.classList.add('active');
    haptic(8);
}

function closeLabResultModal() {
    const modal = document.getElementById('labResultModal');
    if (modal) modal.classList.remove('active');
}

async function saveLabResult() {
    const fixtureId = parseInt(document.getElementById('labResultFixtureId').value);
    const reverseBet = document.getElementById('labResultReverseBet').value;
    const hg = parseInt(document.getElementById('labResultHome').value) || 0;
    const ag = parseInt(document.getElementById('labResultAway').value) || 0;

    if (!fixtureId) {
        showNotification('❌ Нет ID матча', 'error');
        return;
    }

    try {
        const resp = await fetch(API_BASE + '/api/lab/set_result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fixture_id: fixtureId,
                home_goals: hg,
                away_goals: ag,
                reverse_bet: reverseBet,
            })
        });
        const data = await resp.json();
        if (data.status === 'ok') {
            const emoji = data.result === 'win' ? '✅' : '❌';
            showNotification(
                `${emoji} ${data.result.toUpperCase()}: ${hg}:${ag}`,
                'success'
            );
            closeLabResultModal();
            await loadLab();
        } else {
            showNotification('❌ ' + (data.error || 'Ошибка'), 'error');
        }
    } catch (e) {
        showNotification('❌ ' + e.message, 'error');
    }
}

Object.assign(window, {
    // Основные
    cycleTheme, setTheme, switchPage, refreshData,
    openSettings, closeSettings,
    toggleMoreMenu, closeMoreMenu, openFromMore,
    filterMatches, setMatchFilter, setViewMode, sortTable, toggleShowAll,
    showMatchDetail, closeMatchDetail,
    showAddMatchModal, hideAddMatchModal, saveManualMatch,
    updateBank, applyBotSettings, exportCSV,
    exportProject, importProject, clearAllX2,
    openX2Modal, closeX2Modal, saveX2Match, editX2Match, deleteX2Match,
    exportX2Excel, setX2Filter, openX2ImportModal, closeX2ImportModal,
    importX2Excel, autoImportX2FromLogs,
    installPWA, hideInstallBanner, updatePWA, checkForUpdates,
    runBotUpdate, renderAnalyticsChart,
    loadSnapshots, refreshSnapshots, setSnapshotFilter, setSnapshotSort,
    filterSnapshots, showSnapshotChart, closeSnapshotChart,
    openSnapshotFromAnomaly, loadAnomalies,
    quickSetResult,
    loadAutobets, autobetsPlace, autobetsSettle, autobetsReset,
    loadSimPresets, applySimPreset, runSimulation, saveSimulation,
    computeClv, loadClvStats, runGridSearch, renderGridTop5,
    loadDashboardAutobets, getSourceBadge,
    loadAutoX2, openX2Detail,
    loadLive, renderLive, startLiveRefresh,
    renderSparkline,
    loadAnomalyStats, renderAnomalyStats,
    loadClvByStrategy, renderClvByStrategy,
    renderLMDashboardStats,
    renderSnapshotBetBlock,
    showSearchProgressModal, hideSearchProgressModal, pollSearchStatus,

    // Калибровка
    loadCalibration, renderCalibration,
    loadCalibrationSnapshots, renderCalibrationSnapshots,
    saveCalibrationSnapshot, deleteCalibrationSnapshot,
    loadCalibrationFull,

    // Статистика по дням
    loadDailyStats, aggregateByDay, renderDailySummary,
    renderDailyList, setDailyFilter, setDailySort, showDayDetail,

    loadDashboardAnomalies,

    // Лаборатория
    loadLab,
    openLabResultModal,
    closeLabResultModal,
    saveLabResult,

    // Train/Test
    runTrainTest,
    renderTrainTestResults,
    runTrainTestGrid,
    renderTrainTestGridTop5,
    resetTrainTestForm,

    // 3-Way Split
    run3WaySplit,
    render3WayResults,
    run3WaySplitGrid,
    render3WayGridTop5,
    reset3WayForm,

    // Аномалии
    openAnomalyResultModal,
    closeAnomalyResultModal,
    saveAnomalyResult,
});

// ============================================================
// ТЕМА: инициализация (перенесено из 01-core.js)
// ============================================================
(function initTheme() {
    const saved = safeLSGet('theme', 'auto');  // ★ FIX #12
    applyTheme(saved);
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
        if (themeMode === 'auto') applyTheme('auto');
    });
})();
