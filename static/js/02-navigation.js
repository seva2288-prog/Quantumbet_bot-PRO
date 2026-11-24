// НАВИГАЦИЯ
// ============================================================
function switchPage(page) {
    if (page === currentPage) return;
    previousPage = currentPage;

    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    const navBtn = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (navBtn) {
        navBtn.classList.add('active');
    } else if (page === 'x2' || page === 'today' || page === 'autobets' || page === 'simulator' || page === 'settings' || page === 'analytics' || page === 'calibration' || page === 'daily' || page === 'traintest' || page === 'split3way') {
        const navItems = document.querySelectorAll('.nav-item');
        const moreBtn = navItems[navItems.length - 1];
        if (moreBtn) moreBtn.classList.add('active');
    }

    document.querySelectorAll('.page').forEach(p => {
        p.classList.remove('active');
        p.style.display = 'none';
    });

    const target = document.getElementById('page-' + page);
    if (target) {
        target.classList.add('active');
        target.style.display = 'block';
        const dir = window._swipeDir; window._swipeDir = null;
        const cls = dir === 'left' ? 'slide-in-right' : dir === 'right' ? 'slide-in-left' : 'page-transition';
        target.classList.add(cls);
        setTimeout(() => target.classList.remove(cls), 400);
    }

    currentPage = page;
    haptic(6);

    if (page !== 'live' && liveRefreshInterval) {
        clearInterval(liveRefreshInterval);
        liveRefreshInterval = null;
    }

    if (page === 'dashboard') loadPageData('dashboard');
    else if (page === 'matches') loadPageData('matches');
    else if (page === 'analytics') loadPageData('analytics');
    else if (page === 'live') {
        loadLive();
        startLiveRefresh();
    }
    else if (page === 'today') loadPageData('today');
    else if (page === 'x2') renderX2Page();
    else if (page === 'ht') loadHtPage();
    else if (page === 'lab') loadLab();
    else if (page === 'snapshots') loadSnapshots();
    else if (page === 'autobets') loadAutobets();
    else if (page === 'simulator') loadSimPresets();
    else if (page === 'calibration') loadCalibrationFull();
    else if (page === 'anomalies') loadAnomalies();
    else if (page === 'daily') loadDailyStats();
    else if (page === 'traintest') { /* Форма статичная */ }
    else if (page === 'split3way') { /* Форма статичная */ }
}

function openSettings() {
    previousPage = currentPage;
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    const navItems = document.querySelectorAll('.nav-item');
    const moreBtn = navItems[navItems.length - 1];
    if (moreBtn) moreBtn.classList.add('active');

    document.querySelectorAll('.page').forEach(p => {
        p.classList.remove('active');
        p.style.display = 'none';
    });
    const target = document.getElementById('page-settings');
    if (target) {
        target.classList.add('active');
        target.style.display = 'block';
        target.classList.add('page-transition');
    }
    currentPage = 'settings';
    renderSettings();
    haptic(6);
}

function closeSettings() {
    switchPage(previousPage || 'dashboard');
}

// ============================================================
// BOTTOM SHEET
// ============================================================
function toggleMoreMenu() {
    const modal = document.getElementById('moreMenuModal');
    if (modal.classList.contains('active')) closeMoreMenu();
    else {
        modal.classList.add('active');
        haptic(6);
    }
}

function closeMoreMenu() {
    const modal = document.getElementById('moreMenuModal');
    if (modal) modal.classList.remove('active');
}

function openFromMore(page) {
    closeMoreMenu();
    setTimeout(() => switchPage(page), 200);
}

// ============================================================
// СВАЙПЫ между страницами
// ============================================================
(function initSwipe() {
    let sx = 0, sy = 0, st = 0, blocked = false;
    const pages = ['dashboard', 'matches', 'snapshots', 'live', 'ht', 'lab'];
    // не листаем страницы, если палец начался на поле ввода, окне или прокручиваемой вбок таблице/графике
    function startsInBlockedArea(el) {
        if (el.closest('input, textarea, select, .modal-overlay.active, .bottom-sheet, .chart-container, canvas')) return true;
        let n = el;
        while (n && n !== document.body) {
            if (n.scrollWidth > n.clientWidth + 4) {
                const ox = getComputedStyle(n).overflowX;
                if (ox === 'auto' || ox === 'scroll') return true;
            }
            n = n.parentElement;
        }
        return false;
    }
    document.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) { blocked = true; return; }
        const t = e.touches[0];
        sx = t.clientX; sy = t.clientY; st = Date.now();
        blocked = sx < 24 || sx > window.innerWidth - 24 || startsInBlockedArea(e.target);   // края экрана оставляем системе iOS
    }, { passive: true });
    document.addEventListener('touchend', (e) => {
        if (blocked) return;
        const t = e.changedTouches[0];
        const dx = t.clientX - sx, dy = t.clientY - sy;
        if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.6 || Date.now() - st > 700) return;
        const idx = pages.indexOf(currentPage);
        if (idx < 0) return;
        if (dx < 0 && idx < pages.length - 1) { window._swipeDir = 'left'; switchPage(pages[idx + 1]); }
        else if (dx > 0 && idx > 0) { window._swipeDir = 'right'; switchPage(pages[idx - 1]); }
    }, { passive: true });
})();

// ============================================================
// PULL-TO-REFRESH
// ============================================================
(async function initPullToRefresh() {
    const PULL_THRESHOLD = 80;
    const PULL_RESISTANCE = 0.5;
    const INDICATOR_HEIGHT = 74;

    let startY = 0;
    let currentY = 0;
    let isPulling = false;
    let isRefreshing = false;
    let scrollableParent = null;

    const indicator = document.createElement('div');
    indicator.id = 'pullToRefreshIndicator';
    indicator.className = 'ptr-icon';
    indicator.innerHTML = '<svg class="ptr-arrow" viewBox="0 0 40 40" width="22" height="22" aria-hidden="true"><defs><linearGradient id="ptrG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#4fb3f0"/><stop offset="1" stop-color="#8fe3ff"/></linearGradient></defs><path d="M37 20 L5 35 L13 20 L5 5 Z" fill="url(#ptrG)" stroke="#bdeeff" stroke-width="1" stroke-linejoin="round"/></svg>';
    document.body.appendChild(indicator);

    const arrow = indicator.querySelector('.ptr-arrow');
    // стрелка едет слева направо вслед за протяжкой: progress 0 -> у левого края, 1 -> у правого
    function setArrow(progress) {
        const x = (progress - 0.5) * 66;
        arrow.style.transform = `translateX(${x}px)`;
    }
    setArrow(0);

    function isScrollableElement(el) {
        if (!el || el === document.body) return false;
        const style = window.getComputedStyle(el);
        const overflowY = style.overflowY;
        return (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
    }

    function findScrollableParent(el) {
        while (el && el !== document.body) {
            if (isScrollableElement(el)) return el;
            el = el.parentElement;
        }
        return null;
    }

    function canPull() {
        if (document.querySelector('.modal-overlay.active')) return false;
        if (isRefreshing) return false;
        const windowScroll = window.scrollY || window.pageYOffset || document.documentElement.scrollTop;
        if (windowScroll > 0) return false;
        if (scrollableParent && scrollableParent.scrollTop > 0) return false;
        return true;
    }

    function onTouchStart(e) {
        if (e.touches.length !== 1) return;
        if (e.target.closest('.modal-overlay.active, .bottom-sheet, input, textarea, button, .bet-card, .live-card, .snapshot-card')) return;
        scrollableParent = findScrollableParent(e.target);
        if (!canPull()) return;
        startY = e.touches[0].clientY;
        currentY = startY;
        isPulling = false;
    }

    function onTouchMove(e) {
        if (!startY || isRefreshing) return;
        if (e.touches.length !== 1) return;
        currentY = e.touches[0].clientY;
        const deltaY = currentY - startY;

        if (deltaY <= 0 || !canPull()) {
            if (!isPulling) return;
            isPulling = false;
            indicator.style.transform = 'translateX(-50%) translateY(-170%)';
            indicator.style.opacity = '0';
            return;
        }

        isPulling = true;
        const distance = Math.min(deltaY * PULL_RESISTANCE, PULL_THRESHOLD * 1.5);
        const offsetY = -INDICATOR_HEIGHT + distance;
        indicator.style.transform = `translateX(-50%) translateY(${offsetY}px)`;
        indicator.style.opacity = Math.min(distance / PULL_THRESHOLD, 1);

        const progress = Math.min(distance / PULL_THRESHOLD, 1);
        setArrow(progress);

        if (progress >= 1 && !indicator._thresholdHit) {
            indicator._thresholdHit = true;
            haptic(15);
        } else if (progress < 1) {
            indicator._thresholdHit = false;
        }
    }

    async function onTouchEnd() {
        if (!isPulling) {
            startY = 0;
            return;
        }
        const deltaY = currentY - startY;
        const distance = Math.min(deltaY * PULL_RESISTANCE, PULL_THRESHOLD * 1.5);

        if (distance >= PULL_THRESHOLD && !isRefreshing) {
            isRefreshing = true;
            indicator.style.transform = 'translateX(-50%) translateY(-10px)';
            indicator.style.opacity = '1';
            arrow.style.transform = '';
            indicator.classList.add('ptr-loading');
            haptic(30);

            try {
                await refreshCurrentPage();
                showNotification('✅ Обновлено', 'success');
            } catch (err) {
                console.error('Pull-to-refresh error:', err);
                showNotification('❌ Ошибка обновления', 'error');
            }

            setTimeout(() => {
                indicator.style.transform = 'translateX(-50%) translateY(-170%)';
                indicator.style.opacity = '0';
                indicator.classList.remove('ptr-loading');
                setArrow(0);
                isRefreshing = false;
            }, 400);
        } else {
            indicator.style.transform = 'translateX(-50%) translateY(-170%)';
            indicator.style.opacity = '0';
        }

        startY = 0;
        currentY = 0;
        isPulling = false;
        indicator._thresholdHit = false;
    }

    async function refreshCurrentPage() {
        switch (currentPage) {
            case 'dashboard':
                cachedData = null;
                await loadPageData('dashboard');
                await loadDashboardAnomalies();
                await loadDashboardAutobets();
                break;
            case 'matches':
                cachedData = null;
                await loadPageData('matches');
                break;
            case 'snapshots':
                await loadSnapshots();
                break;
            case 'live':
                await loadLive(true);
                break;
            case 'x2':
                await renderX2Page();
                break;
            case 'ht':
                await loadHtPage();
                break;
            case 'analytics':
                cachedData = null;
                await loadPageData('analytics');
                break;
            case 'calibration':
                await loadCalibrationFull();
                break;
            case 'daily':
                await loadDailyStats();
                break;
            case 'autobets':
                await loadAutobets();
                break;
            case 'simulator':
                await loadSimPresets();
                break;
            case 'settings':
                renderSettings();
                break;
            default:
                cachedData = null;
                await loadPageData(currentPage);
        }
    }

    document.addEventListener('touchstart', onTouchStart, { passive: true });
    document.addEventListener('touchmove', onTouchMove, { passive: true });
    document.addEventListener('touchend', onTouchEnd, { passive: true });
    document.addEventListener('touchcancel', onTouchEnd, { passive: true });

    window.__pullToRefreshCurrentPage = refreshCurrentPage;
})();

// ============================================================
