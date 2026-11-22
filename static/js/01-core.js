// ============================================================
// КОНФИГУРАЦИЯ
// ============================================================
const API_BASE = window.location.origin;

// ===== ADMIN TOKEN: автоматически добавляется ко всем запросам к /api/* и /export =====
const _origFetch = window.fetch.bind(window);
let _tokenPrompt = null;
let _tokenCancelAt = 0;
function getAdminToken() {
    try { return localStorage.getItem('qb_admin_token') || ''; } catch (e) { return ''; }
}
function setAdminToken(t) {
    try { localStorage.setItem('qb_admin_token', t); } catch (e) {}
}
function askAdminToken() {
    if (_tokenPrompt) return _tokenPrompt;
    if (Date.now() - _tokenCancelAt < 60000) return Promise.resolve('');
    _tokenPrompt = new Promise(function (resolve) {
        setTimeout(function () {
            const t = (window.prompt('Введите ADMIN_TOKEN') || '').trim();
            if (t) setAdminToken(t); else _tokenCancelAt = Date.now();
            _tokenPrompt = null;
            resolve(t);
        }, 0);
    });
    return _tokenPrompt;
}
window.fetch = async function (input, init) {
    const url = (typeof input === 'string') ? input : ((input && input.url) || '');
    const guarded = (url.indexOf('/api/') !== -1 && url.indexOf('/api/keepalive') === -1)
                    || /\/export(\?|$)/.test(url);
    if (!guarded) return _origFetch(input, init);
    const send = function (tok) {
        const o = Object.assign({}, init || {});
        const hd = new Headers(o.headers || {});
        if (tok) hd.set('X-Admin-Token', tok);
        o.headers = hd;
        return _origFetch(input, o);
    };
    let resp = await send(getAdminToken());
    if (resp.status === 401) {
        const t = await askAdminToken();
        if (t) resp = await send(t);
    }
    return resp;
};
async function downloadExcel() {
    try {
        const r = await fetch(API_BASE + '/export');
        if (!r.ok) { alert('Экспорт не удался: ' + (await r.text()).slice(0, 200)); return; }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'history_' + new Date().toISOString().slice(0, 10) + '.xlsx';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    } catch (e) { alert('Ошибка экспорта: ' + e); }
}
const AUTO_REFRESH_MS = 60000;
const KEEPALIVE_MS = 180000;
const AUTO_IMPORT_MS = 180000;
const ITEMS_LIMIT = 50;
const SWIPE_THRESHOLD = 100;
const LIVE_REFRESH_MS = 20000;

// ============================================================
// ★ FIX #12: безопасный localStorage
// ============================================================
function safeLSGet(key, defaultValue = null) {
    try {
        const v = localStorage.getItem(key);
        return v === null ? defaultValue : v;
    } catch (e) {
        return defaultValue;
    }
}
function safeLSSet(key, value) {
    try {
        localStorage.setItem(key, value);
        return true;
    } catch (e) {
        return false;
    }
}

// ============================================================
// ГЛОБАЛЬНОЕ СОСТОЯНИЕ
// ============================================================
let cachedData = null;
let chartInstance = null;
let analyticsChartInstance = null;
let snapshotChartInstance = null;
let simChart = null;
let currentSimResult = null;
let currentPage = 'dashboard';
let previousPage = 'dashboard';
let isLoading = false;
let x2Data = [];
let autoX2Data = [];
let editingX2Index = null;
let matchesSearchQuery = '';
let matchesFilter = 'all';
let x2CurrentFilter = 'all';
let viewMode = 'cards';
let keepAliveInterval = null;
let autoImportInterval = null;
let autoRefreshInterval = null;
let liveRefreshInterval = null;
let liveData = [];
let deferredPrompt = null;
let refreshTimeout = null;
let showAllItems = false;
let sortBy = 'date';
let sortDir = 'desc';
let themeMode = 'auto';

let snapshotsData = [];
let snapshotFilter = 'all';
let snapshotSort = 'recent';
let snapshotsSearchQuery = '';
let currentSnapshotFixture = null;

let dailyFilter = 30;
let dailySort = 'date';

let ttLastResult = null;
let s3LastResult = null;

// ============================================================
// ХАПТИК
// ============================================================
function haptic(ms = 10) {
    if (navigator.vibrate) { try { navigator.vibrate(ms); } catch (e) {} }
}

// ============================================================
// УВЕДОМЛЕНИЯ
// ============================================================
function showNotification(message, type = '') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'notification' + (type ? ' ' + type : '');
    toast.textContent = message;
    toast.style.pointerEvents = 'auto';
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================================
// ESCAPE HTML
// ============================================================
function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
}

// ============================================================
// SOURCE BADGE
// ============================================================
function getSourceBadge(source) {
    if (!source) return '';
    const map = {
        'auto':   { label: '🤖 Авто',   cls: 'auto' },
        'manual': { label: '✏️ Ручной', cls: 'manual' },
        'cache':  { label: '⚡ Кэш',    cls: 'cache' },
        'import': { label: '📥 Импорт', cls: 'import' },
    };
    const s = map[source];
    if (!s) return '';
    return `<span class="source-badge ${s.cls}">${s.label}</span>`;
}

// ============================================================
// SPARKLINE
// ============================================================
function renderSparkline(points, width = 200, height = 32) {
    if (!points || points.length < 2) {
        return '<div style="font-size:9px;color:var(--text-tertiary);padding:4px 0;">Нет данных для графика</div>';
    }

    const oddsValues = points.map(p => parseFloat(p.odds) || 0).filter(v => v > 1);
    if (oddsValues.length < 2) {
        return '<div style="font-size:9px;color:var(--text-tertiary);padding:4px 0;">Нет данных для графика</div>';
    }

    const min = Math.min(...oddsValues);
    const max = Math.max(...oddsValues);
    const range = max - min || 1;

    const padding = 4;
    const innerW = width - padding * 2;
    const innerH = height - padding * 2;

    const coords = points.map((p, i) => {
        const x = padding + (i / (points.length - 1)) * innerW;
        const val = parseFloat(p.odds) || 0;
        const y = padding + innerH - ((val - min) / range) * innerH;
        return { x, y, odds: val };
    });

    const pathD = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
    const first = oddsValues[0];
    const last = oddsValues[oddsValues.length - 1];
    const pctChange = ((last / first) - 1) * 100;

    const trendUp = pctChange >= 0;
    const lineColor = trendUp ? '#34d399' : '#f87171';
    const fillColor = trendUp ? 'rgba(52, 211, 153, 0.12)' : 'rgba(248, 113, 113, 0.12)';
    const arrow = trendUp ? '📈' : '📉';
    const pctStr = (pctChange >= 0 ? '+' : '') + pctChange.toFixed(1) + '%';

    const areaD = `${pathD} L${coords[coords.length - 1].x.toFixed(1)},${height - padding} L${coords[0].x.toFixed(1)},${height - padding} Z`;
    const lastCoord = coords[coords.length - 1];

    return `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 0;margin-top:6px;border-top:1px dashed var(--border-color);">
            <div style="flex:1;min-width:0;">
                <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block;width:100%;height:${height}px;max-width:100%;">
                    <path d="${areaD}" fill="${fillColor}" stroke="none"/>
                    <path d="${pathD}" fill="none" stroke="${lineColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="${lastCoord.x.toFixed(1)}" cy="${lastCoord.y.toFixed(1)}" r="2.5" fill="${lineColor}"/>
                </svg>
            </div>
            <div style="flex-shrink:0;text-align:right;">
                <div style="font-size:11px;font-weight:700;color:${lineColor};">
                    ${arrow} ${pctStr}
                </div>
                <div style="font-size:9px;color:var(--text-tertiary);">
                    ${first.toFixed(2)} → ${last.toFixed(2)}
                </div>
            </div>
        </div>
    `;
}

// ============================================================
// ЗВЁЗДЫ
// ============================================================
(function generateLoadingStars() {
    const container = document.getElementById('loadingStars');
    if (!container) return;
    for (let i = 0; i < 150; i++) {
        const star = document.createElement('div');
        star.className = 'loading-star';
        const size = 0.5 + Math.random() * 2.5;
        star.style.width = size + 'px';
        star.style.height = size + 'px';
        star.style.left = Math.random() * 100 + '%';
        star.style.top = Math.random() * 100 + '%';
        star.style.setProperty('--duration', (2 + Math.random() * 4) + 's');
        star.style.animationDelay = (Math.random() * 5) + 's';
        star.style.opacity = 0.2 + Math.random() * 0.6;
        container.appendChild(star);
    }
})();

(function generateBgStars() {
    const container = document.getElementById('starsContainer');
    if (!container) return;
    for (let i = 0; i < 200; i++) {
        const star = document.createElement('div');
        star.className = 'star';
        const size = 0.5 + Math.random() * 2;
        star.style.width = size + 'px';
        star.style.height = size + 'px';
        star.style.left = Math.random() * 100 + '%';
        star.style.top = Math.random() * 100 + '%';
        star.style.setProperty('--duration', (2 + Math.random() * 4) + 's');
        star.style.animationDelay = (Math.random() * 5) + 's';
        star.style.opacity = 0.2 + Math.random() * 0.5;
        container.appendChild(star);
    }
})();

function hideLoadingScreen() {
    const loading = document.getElementById('loadingScreen');
    if (loading && !loading.classList.contains('hidden')) {
        loading.classList.add('hidden');
    }
}

// ============================================================
// ТЕМА
// ============================================================
function getSystemTheme() {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function applyTheme(mode) {
    themeMode = mode;
    safeLSSet('theme', mode);  // ★ FIX #12
    let actualTheme = mode;
    if (mode === 'auto') actualTheme = getSystemTheme();
    document.documentElement.setAttribute('data-theme', actualTheme);
    const btn = document.getElementById('themeBtn');
    if (btn) btn.textContent = actualTheme === 'dark' ? '🌙' : '☀️';
    const sel = document.getElementById('themeSelect');
    if (sel) sel.value = mode;
    updateAllCharts(actualTheme === 'light');
}

function cycleTheme() {
    const modes = ['dark', 'light', 'auto'];
    const idx = modes.indexOf(themeMode);
    const nextMode = modes[(idx + 1) % modes.length];
    applyTheme(nextMode);
    haptic(8);
    const labels = { dark: 'Тёмная', light: 'Светлая', auto: 'Авто' };
    showNotification(`🎨 Тема: ${labels[nextMode]}`, '');
}

function setTheme(mode) {
    applyTheme(mode);
    haptic(10);
}

// initTheme() вызывается в 13-anomalies-init.js — после загрузки всех файлов (нужны функции из более поздних модулей)


// ============================================================
