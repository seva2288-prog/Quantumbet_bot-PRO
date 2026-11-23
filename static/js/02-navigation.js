// НАВИГАЦИЯ
// ============================================================
function switchPage(page) {
    if (page === currentPage) return;
    previousPage = currentPage;

    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    const navBtn = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (navBtn) {
        navBtn.classList.add('active');
    } else if (page === 'today' || page === 'autobets' || page === 'simulator' || page === 'settings' || page === 'analytics' || page === 'calibration' || page === 'daily' || page === 'traintest' || page === 'split3way') {
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
        target.classList.add('page-transition');
        setTimeout(() => target.classList.remove('page-transition'), 400);
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
    let touchStartX = 0;
    let touchStartY = 0;
    const pages = ['dashboard', 'matches', 'snapshots', 'live', 'x2'];
    document.addEventListener('touchstart', (e) => {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
    }, { passive: true });
    document.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) < 80 || Math.abs(dy) > 60) return;
        if (e.target.closest('input, textarea, .table-wrapper, .chart-container, .modal, .bet-card, .bottom-sheet, .live-card')) return;
        if (currentPage === 'settings' || currentPage === 'autobets' || currentPage === 'simulator' || currentPage === 'analytics' || currentPage === 'calibration' || currentPage === 'daily' || currentPage === 'traintest' || currentPage === 'split3way') return;
        const idx = pages.indexOf(currentPage);
        if (dx < 0 && idx < pages.length - 1) switchPage(pages[idx + 1]);
        else if (dx > 0 && idx > 0) switchPage(pages[idx - 1]);
    }, { passive: true });
})();

// ============================================================
// PULL-TO-REFRESH
// ============================================================
(async function initPullToRefresh() {
    const PULL_THRESHOLD = 80;
    const PULL_RESISTANCE = 0.5;
    const INDICATOR_HEIGHT = 60;

    let startY = 0;
    let currentY = 0;
    let isPulling = false;
    let isRefreshing = false;
    let scrollableParent = null;

    const indicator = document.createElement('div');
    indicator.id = 'pullToRefreshIndicator';
    indicator.style.cssText = `
        position: fixed;
        top: 0;
        left: 50%;
        transform: translateX(-50%) translateY(-100%);
        width: 60px;
        height: 60px;
        background: var(--bg-card);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--border-color);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        z-index: 9998;
        transition: transform 0.2s ease, opacity 0.2s ease;
        opacity: 0;
        pointer-events: none;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        color: var(--emerald-400);
    `;
    indicator.innerHTML = '<span style="transform: rotate(0deg); display: block;">↓</span>';
    document.body.appendChild(indicator);

    const indicatorIcon = indicator.querySelector('span');

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
            indicator.style.transform = 'translateX(-50%) translateY(-100%)';
            indicator.style.opacity = '0';
            return;
        }

        isPulling = true;
        const distance = Math.min(deltaY * PULL_RESISTANCE, PULL_THRESHOLD * 1.5);
        const offsetY = -INDICATOR_HEIGHT + distance;
        indicator.style.transform = `translateX(-50%) translateY(${offsetY}px)`;
        indicator.style.opacity = Math.min(distance / PULL_THRESHOLD, 1);

        const progress = Math.min(distance / PULL_THRESHOLD, 1);
        const rotation = progress * 180;
        indicatorIcon.style.transform = `rotate(${rotation}deg)`;
        indicatorIcon.textContent = progress >= 1 ? '↻' : '↓';

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
            indicatorIcon.style.transform = 'none';
            indicatorIcon.textContent = '↻';
            indicatorIcon.style.animation = 'spin 0.8s linear infinite';
            haptic(30);

            try {
                await refreshCurrentPage();
                showNotification('✅ Обновлено', 'success');
            } catch (err) {
                console.error('Pull-to-refresh error:', err);
                showNotification('❌ Ошибка обновления', 'error');
            }

            setTimeout(() => {
                indicator.style.transform = 'translateX(-50%) translateY(-100%)';
                indicator.style.opacity = '0';
                indicatorIcon.style.animation = '';
                indicatorIcon.textContent = '↓';
                indicatorIcon.style.transform = 'rotate(0deg)';
                isRefreshing = false;
            }, 400);
        } else {
            indicator.style.transform = 'translateX(-50%) translateY(-100%)';
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
