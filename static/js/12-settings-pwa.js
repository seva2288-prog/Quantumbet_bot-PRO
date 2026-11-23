// SETTINGS
// ============================================================
// ===== Настройки сигналов, уведомлений и отчёта (хранятся на сервере) =====
const BOT_SETTING_FIELDS = [
    {k: 'LINE_MOVEMENT_MIN_DROP_PCT', t: 'Мин. падение кэфа, %', d: 'Падение кэфа от (число с минусом)', step: 0.5},
    {k: 'LINE_MOVEMENT_MAX_DROP_PCT', t: 'Макс. падение кэфа, %', d: 'Падение глубже этого — игнорируем (минус)', step: 0.5},
    {k: 'LINE_MOVEMENT_MIN_ODDS', t: 'Мин. кэф', d: 'Ставим только на кэфы не ниже', step: 0.05},
    {k: 'LINE_MOVEMENT_MAX_ODDS', t: 'Макс. кэф', d: 'и не выше', step: 0.05},
    {k: 'LINE_MOVEMENT_STAKE_PCT', t: 'Ставка, % от банка', d: 'Размер ставки по сигналу', step: 0.1, scale: 100},
    {k: 'LINE_MOVEMENT_MAX_BETS', t: 'Макс. ставок за запуск', d: 'Сколько сигналов брать за раз', step: 1},
    {k: 'DAY_NOTIFY_MOVE_PCT', t: 'Уведомлять при движении, %', d: 'Telegram при изменении кэфа от этого порога', step: 0.5},
    {k: 'NOTIFY_QUIET_ENABLED', t: 'Тихие часы', d: 'Ночью уведомления копятся и приходят утром', bool: true},
    {k: 'NOTIFY_QUIET_FROM', t: 'Тихие часы: с (час, МСК)', d: '0–23', step: 1},
    {k: 'NOTIFY_QUIET_TO', t: 'Тихие часы: до (час, МСК)', d: '0–23', step: 1},
    {k: 'DAILY_REPORT_ENABLED', t: 'Ежедневный отчёт', d: 'Итоги вчерашнего дня в Telegram', bool: true},
    {k: 'DAILY_REPORT_HOUR', t: 'Час отчёта (МСК)', d: 'Не раньше этого часа', step: 1},
    {k: 'STREAK_ALERT_LOSSES', t: 'Предупреждать о серии поражений', d: 'Сообщение в Telegram после N проигрышей подряд (0 = выкл.)', step: 1},
];
async function loadBotSettingsUI() {
    const box = document.getElementById('botSettingsBox');
    if (!box) return;
    try {
        const r = await fetch(API_BASE + '/api/bot_settings_ui?t=' + Date.now());
        if (!r.ok) throw new Error(r.status);
        const j = await r.json();
        const v = j.settings || {};
        box.innerHTML = '<h2>🎛️ Сигналы и уведомления</h2>' + BOT_SETTING_FIELDS.map(f => {
            const raw = v[f.k];
            const input = f.bool
                ? `<input type="checkbox" data-k="${f.k}" ${raw ? 'checked' : ''} style="width:22px;height:22px;">`
                : `<input type="number" data-k="${f.k}" data-scale="${f.scale || 1}" step="${f.step}" value="${raw == null ? '' : +(raw * (f.scale || 1)).toFixed(3)}" style="width:90px;">`;
            return `<div class="setting-item"><div><div class="label">${f.t}</div><div class="desc">${f.d}</div></div><div class="input-group">${input}</div></div>`;
        }).join('') + '<button class="btn btn-primary" onclick="saveBotSettingsUI()" style="margin-top:10px;width:100%;padding:10px;">Сохранить</button>';
    } catch (e) {
        box.innerHTML = '<h2>🎛️ Сигналы и уведомления</h2><div style="font-size:12px;color:var(--text-tertiary);">Недоступно (обновите сервер)</div>';
    }
}
async function saveBotSettingsUI() {
    const body = {};
    document.querySelectorAll('#botSettingsBox [data-k]').forEach(el => {
        if (el.type === 'checkbox') body[el.dataset.k] = el.checked;
        else if (el.value !== '') body[el.dataset.k] = parseFloat(el.value) / (parseFloat(el.dataset.scale) || 1);
    });
    try {
        const r = await fetch(API_BASE + '/api/bot_settings_ui', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
        });
        const j = await r.json();
        if (!r.ok || j.status !== 'ok') throw new Error(j.error || r.status);
        showNotification('✅ Настройки сохранены', 'success');
        loadBotSettingsUI();
    } catch (e) {
        showNotification('❌ ' + e.message, 'error');
    }
}
async function downloadBackup() {
    try {
        showNotification('⏳ Готовлю архив…', '');
        const r = await fetch(API_BASE + '/api/backup/download');
        if (!r.ok) throw new Error('Сервер: ' + r.status);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'quantum_backup.zip';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
        showNotification('❌ Бэкап: ' + e.message, 'error');
    }
}

function renderSettings() {
    loadBotSettingsUI();
    const bank = cachedData && cachedData.stats ? cachedData.stats.bank : 1000;
    document.getElementById('bankInput').value = bank;
    document.getElementById('x2CountSettings').textContent = x2Data.length + autoX2Data.length;
    document.getElementById('themeSelect').value = themeMode;
    fetch(API_BASE + '/api/snapshots?days=30&limit=1')
        .then(r => r.json())
        .then(data => {
            if (data && data.count !== undefined) {
                document.getElementById('snapshotCountSettings').textContent = data.count + ' матчей';
            }
        })
        .catch(() => {});
}

async function updateBank() {
    const value = parseFloat(document.getElementById('bankInput').value);
    if (!value || value <= 0) return;
    try {
        const r = await fetch(API_BASE + '/api/bank', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bank: value })
        });
        const data = await r.json();
        if (data.success) {
            showNotification('✅ Банк: $' + value, 'success');
            haptic(15);
            refreshData();
        }
    } catch (e) {
        showNotification('❌ Ошибка', 'error');
    }
}

async function applyBotSettings() {
    const settings = {
        ev_min_70: parseFloat(document.getElementById('settingEvMin').value),
        prob_min_70: parseFloat(document.getElementById('settingProbMin').value),
        max_tm25_bets: parseFloat(document.getElementById('settingMaxTm25').value)
    };
    try {
        const r = await fetch(API_BASE + '/api/update_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const data = await r.json();
        if (data.success) {
            showNotification('✅ Настройки сохранены', 'success');
            haptic(15);
        }
    } catch (e) {
        showNotification('❌ Ошибка', 'error');
    }
}

function exportCSV() {
    if (!cachedData || !cachedData.history) return;
    const history = cachedData.history;
    const headers = ['Дата', 'Матч', 'Счёт', '1-й тайм', 'Ставка', 'Кэф', 'EV%', 'Prob%', 'Сумма', 'Результат', 'Прибыль', 'Букмекер'];
    const rows = history.map(b => [
        b.date || '',
        `${b.home || ''} vs ${b.away || ''}`,
        (b.home_goals != null && b.away_goals != null) ? `${b.home_goals}-${b.away_goals}` : '-',
        (b.halftime_home != null && b.halftime_away != null) ? `${b.halftime_home}-${b.halftime_away}` : '-',
        b.bet || '', b.odds || 0, b.ev || 0, b.prob || 0, b.stake || 0,
        b.result || 'pending', b.profit || 0, b.bookmaker || '—'
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `history_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showNotification('✅ CSV скачан', 'success');
}

function exportProject() {
    const projectData = {
        version: '23.0',
        exportDate: new Date().toISOString(),
        theme: themeMode,
        data: cachedData,
        x2Data: x2Data
    };
    const json = JSON.stringify(projectData, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `quantum_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showNotification('✅ Проект сохранён', 'success');
}

function importProject(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const projectData = JSON.parse(e.target.result);
            if (projectData.theme) applyTheme(projectData.theme);
            if (projectData.x2Data) {
                x2Data = projectData.x2Data;
                saveX2Data();
            }
            if (projectData.data && projectData.data.history) {
                const r = await fetch(API_BASE + '/api/import_project', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        history: projectData.data.history,
                        stats: projectData.data.stats
                    })
                });
                const data = await r.json();
                if (data.success) {
                    showNotification(`✅ Загружено ${data.count || 0} ставок`, 'success');
                    refreshData();
                }
            }
        } catch (err) {
            showNotification('❌ Ошибка: ' + err.message, 'error');
        }
    };
    reader.readAsText(file);
}

// ============================================================
// ADD MATCH MODAL
// ============================================================
function showAddMatchModal() {
    document.getElementById('addMatchModal').classList.add('active');
    haptic(10);
}

function hideAddMatchModal() {
    document.getElementById('addMatchModal').classList.remove('active');
}

async function saveManualMatch() {
    const match = document.getElementById('matchNameInput').value.trim();
    if (!match) {
        showNotification('❌ Введите матч', 'error');
        return;
    }
    const data = {
        match,
        score: document.getElementById('matchScoreInput').value.trim() || '-',
        bet: document.getElementById('matchBetInput').value.trim() || 'Ручная',
        odds: parseFloat(document.getElementById('matchOddsInput').value) || 1.85,
        stake: parseFloat(document.getElementById('matchStakeInput').value) || 42.87,
        result: document.getElementById('matchResultSelect').value,
        bookmaker: 'Ручное добавление'
    };
    try {
        const r = await fetch(API_BASE + '/api/add_manual_match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const res = await r.json();
        if (res.success) {
            showNotification('✅ Добавлено', 'success');
            hideAddMatchModal();
            refreshData();
        }
    } catch (e) {
        showNotification('❌ Ошибка', 'error');
    }
}

async function runBotUpdate() {
    if (window._searchInProgress) {
        showNotification('⏳ Поиск уже идёт...', '');
        return;
    }
    haptic(20);
    window._searchInProgress = true;
    showSearchProgressModal();
    try {
        const resp = await fetch(API_BASE + '/api/trigger_search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await resp.json();
        if (data.status === 'already_running') {
            showNotification('⏳ Поиск уже был запущен', '');
            pollSearchStatus();
            return;
        }
        if (data.status === 'ok') {
            showNotification('🚀 Поиск запущен!', 'success');
            pollSearchStatus();
        } else {
            showNotification('❌ Не удалось запустить поиск', 'error');
            hideSearchProgressModal();
            window._searchInProgress = false;
        }
    } catch (e) {
        console.error('trigger_search error:', e);
        showNotification('❌ Ошибка: ' + e.message, 'error');
        hideSearchProgressModal();
        window._searchInProgress = false;
    }
}

function showSearchProgressModal() {
    let modal = document.getElementById('searchProgressModal');
    if (modal) {
        modal.style.display = 'flex';
        return;
    }
    modal = document.createElement('div');
    modal.id = 'searchProgressModal';
    modal.className = 'modal-overlay active';
    modal.innerHTML = '<div class="modal" style="text-align:center;max-width:380px;">' +
        '<div style="font-size:48px;margin-bottom:12px;animation:spin 2s linear infinite;">🚀</div>' +
        '<h3 style="color:var(--emerald-400);margin-bottom:8px;">Анализ матчей</h3>' +
        '<p style="font-size:12px;color:var(--text-tertiary);margin-bottom:16px;">Бот проанализирует лиги и найдёт ставки.</p>' +
        '<div id="searchProgressElapsed" style="font-size:24px;font-weight:800;color:var(--emerald-400);margin-bottom:8px;">0 сек</div>' +
        '<div style="font-size:11px;color:var(--text-tertiary);">Обычно 2–5 минут</div>' +
        '<button class="btn btn-outline" onclick="hideSearchProgressModal();window._searchInProgress=false;" style="margin-top:20px;width:100%;">Свернуть</button>' +
        '</div>';
    document.body.appendChild(modal);
}

function hideSearchProgressModal() {
    const modal = document.getElementById('searchProgressModal');
    if (modal) modal.remove();
    window._searchInProgress = false;
}

async function pollSearchStatus() {
    const startTime = Date.now();
    const maxWaitMs = 30 * 60 * 1000;
    const interval = setInterval(async () => {
        if (!window._searchInProgress) { clearInterval(interval); return; }
        if (Date.now() - startTime > maxWaitMs) {
            clearInterval(interval);
            hideSearchProgressModal();
            showNotification('⏰ Поиск занимает слишком долго', 'error');
            return;
        }
        try {
            const resp = await fetch(API_BASE + '/api/search_status?t=' + Date.now());
            const data = await resp.json();
            const elapsedEl = document.getElementById('searchProgressElapsed');
            if (data.status === 'running') {
                const sec = data.elapsed_seconds || 0;
                if (elapsedEl) {
                    if (sec < 60) { elapsedEl.textContent = sec + ' сек'; }
                    else {
                        const m = Math.floor(sec / 60);
                        const s = sec % 60;
                        elapsedEl.textContent = m + ' мин ' + s + ' сек';
                    }
                }
            } else if (data.status === 'idle') {
                clearInterval(interval);
                hideSearchProgressModal();
                showNotification('✅ Поиск завершён!', 'success');
                cachedData = null;
                if (currentPage === 'dashboard' || currentPage === 'matches') loadPageData(currentPage);
                if (currentPage === 'anomalies') loadAnomalies();
                if (currentPage === 'x2') renderX2Page();
            }
        } catch (e) { console.error('pollSearchStatus:', e); }
    }, 3000);
}

// ============================================================
// CHART DASHBOARD
// ============================================================
function renderChart(profitData) {
    const ctx = document.getElementById('profitChart');
    if (!ctx) return;
    if (chartInstance) chartInstance.destroy();
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    const data = profitData || { dates: ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], profits: [0,0,0,0,0,0,0] };
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [{
                label: 'Прибыль ($)',
                data: data.profits,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.08)',
                fill: true, tension: 0.4,
                pointBackgroundColor: '#10b981',
                pointBorderColor: isLight ? 'white' : '#0d1a17',
                pointBorderWidth: 2, pointRadius: 4, pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            onClick: (e) => {
                const points = chartInstance.getElementsAtEventForMode(e, 'nearest', { intersect: true }, true);
                if (points.length) {
                    const idx = points[0].index;
                    showNotification(`📅 ${data.dates[idx]}: ${data.profits[idx] >= 0 ? '+' : ''}$${data.profits[idx]}`, '');
                }
            },
            plugins: { legend: { labels: { color: isLight ? 'rgba(6,78,59,0.6)' : 'rgba(236,253,245,0.6)', font: { size: 10 } } } },
            scales: {
                x: { ticks: { color: isLight ? 'rgba(6,78,59,0.4)' : 'rgba(236,253,245,0.3)', font: { size: 9 } }, grid: { color: isLight ? 'rgba(6,78,59,0.05)' : 'rgba(52,211,153,0.04)' } },
                y: { ticks: { color: isLight ? 'rgba(6,78,59,0.4)' : 'rgba(236,253,245,0.3)', callback: v => '$' + v, font: { size: 9 } }, grid: { color: isLight ? 'rgba(6,78,59,0.05)' : 'rgba(52,211,153,0.04)' } }
            }
        }
    });
}

function updateAllCharts(isLight) {
    if (chartInstance) {
        const color = isLight ? 'rgba(6,78,59,0.6)' : 'rgba(236,253,245,0.6)';
        chartInstance.options.plugins.legend.labels.color = color;
        chartInstance.update();
    }
    if (analyticsChartInstance) {
        analyticsChartInstance.destroy();
        renderAnalyticsChart();
    }
    if (snapshotChartInstance) {
        snapshotChartInstance.destroy();
        if (currentSnapshotFixture) showSnapshotChart(currentSnapshotFixture);
    }
}

// ============================================================
// KEEP-ALIVE
// ============================================================
function startKeepAlive() {
    keepAliveInterval = setInterval(async () => {
        try {
            await fetch(API_BASE + '/api/keepalive?t=' + Date.now());
            const el = document.getElementById('keepAliveStatus');
            if (el) el.textContent = '✅ ' + new Date().toLocaleTimeString();
        } catch (e) {}
    }, KEEPALIVE_MS);
    const el = document.createElement('div');
    el.id = 'keepAliveStatus';
    el.textContent = '🔄 Пинг активен';
    document.body.appendChild(el);
}

// ============================================================
// AUTO-REFRESH
// ============================================================
function startAutoRefresh() {
    autoRefreshInterval = setInterval(() => {
        if (document.visibilityState === 'visible' && !isLoading) {
            if (currentPage === 'dashboard' || currentPage === 'matches') {
                cachedData = null;
                loadPageData(currentPage);
            } else if (currentPage === 'snapshots') {
                loadSnapshots();
            } else if (currentPage === 'autobets') {
                loadAutobets();
            } else if (currentPage === 'x2') {
                renderX2Page();
            } else if (currentPage === 'calibration') {
                loadCalibrationFull();
            } else if (currentPage === 'daily') {
                loadDailyStats();
            }
        }
    }, AUTO_REFRESH_MS);
}

// ============================================================
// PWA
// ============================================================
function registerPWA() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').then(reg => {
            reg.addEventListener('updatefound', () => {
                const newWorker = reg.installing;
                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        showUpdateBanner();
                    }
                });
            });
        }).catch(() => {});
    }
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        showInstallBanner();
    });
    window.addEventListener('appinstalled', () => {
        hideInstallBanner();
        showNotification('✅ Приложение установлено', 'success');
    });
}

function showInstallBanner() {
    if (document.getElementById('pwa-install-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'pwa-install-banner';
    banner.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex:1;">
            <span style="font-size:24px;">📲</span>
            <div>
                <div style="font-weight:700;font-size:13px;">Установить</div>
                <div style="font-size:10px;color:var(--text-tertiary);">Добавить на главный экран</div>
            </div>
        </div>
        <button onclick="installPWA()" style="padding:8px 14px;background:linear-gradient(135deg,#10b981,#059669);border:none;color:white;border-radius:10px;font-size:11px;font-weight:700;cursor:pointer;">Установить</button>
        <button onclick="hideInstallBanner()" style="background:transparent;border:none;color:var(--text-tertiary);font-size:18px;cursor:pointer;padding:4px 8px;">✕</button>
    `;
    document.body.appendChild(banner);
}

function installPWA() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(() => {
            deferredPrompt = null;
            hideInstallBanner();
        });
    }
}

function hideInstallBanner() {
    const b = document.getElementById('pwa-install-banner');
    if (b) b.remove();
}

function showUpdateBanner() {
    if (document.getElementById('pwa-update-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'pwa-update-banner';
    banner.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;flex:1;">
            <span style="font-size:20px;">🔄</span>
            <div>
                <div style="font-weight:700;font-size:12px;">Доступно обновление</div>
                <div style="font-size:10px;color:var(--text-tertiary);">Обновить приложение</div>
            </div>
        </div>
        <button onclick="updatePWA()" style="padding:8px 14px;background:linear-gradient(135deg,#10b981,#059669);border:none;color:white;border-radius:10px;font-size:11px;font-weight:700;cursor:pointer;">Обновить</button>
    `;
    document.body.appendChild(banner);
}

function updatePWA() {
    navigator.serviceWorker.ready.then(reg => {
        reg.waiting?.postMessage({ type: 'SKIP_WAITING' });
    });
    document.getElementById('pwa-update-banner')?.remove();
}

function checkForUpdates() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.getRegistration().then(reg => {
            if (reg) reg.update().then(() => {
                showNotification('✅ Проверка выполнена', 'success');
            });
        });
    }
}

// ============================================================
