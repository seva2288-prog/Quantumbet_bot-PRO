// BET CARD
// ★ FIX #2: убраны дублирующие блоки Score
// ============================================================
function renderBetCard(m, isActive = false) {
    const best = m.best_bet || (m.bets && m.bets[0]) || {};
    const betLabel = best.label || m.bet || '—';
    const source = m.source || '';
    const isLM = source === 'line_movement';

    const odds = best.odds || m.odds || 0;
    const ev = best.ev || m.ev || 0;
    const prob = best.prob || m.prob || 0;
    const league = m.league || '—';
    const matchTime = m.match_time || m.date || '—';
    const score = m.score || '-';
    const result = m.result || 'pending';

    // Score-based: число или null
    const matchScore = (typeof m.score === 'number' && isFinite(m.score)) ? m.score : null;

    const htH = m.halftime_home;
    const htA = m.halftime_away;
    const hasHalftime = (htH !== null && htH !== undefined && htA !== null && htA !== undefined);

    const betClass = getBetClass(betLabel);
    const probColor = prob >= 70 ? 'emerald' : prob >= 55 ? 'gold' : 'red';
    const evColor = ev >= 15 ? 'emerald' : ev >= 5 ? 'gold' : 'red';

    let homeGoals = '-', awayGoals = '-';
    if (score && score !== '-' && String(score || '').includes('-')) {
        const parts = score.split('-').map(s => s.trim());
        homeGoals = parts[0];
        awayGoals = parts[1];
    }

    let scoreColor = 'var(--text-secondary)';
    if (result === 'win') scoreColor = 'var(--emerald-400)';
    else if (result === 'loss') scoreColor = 'var(--red-400)';
    else if (result === 'push') scoreColor = 'var(--gold-400)';

    const showScore = (!isActive || (m.dm && m.dm.status && m.dm.status !== 'NS')) && score !== '-' && homeGoals !== '-' && awayGoals !== '-';

    let resultBadge = '';
    if (!isActive && result && result !== 'pending') {
        resultBadge = `<span class="badge ${result}">${result.toUpperCase()}</span>`;
    }

    let displayDate = matchTime;
    try {
        if (matchTime.includes('.')) {
            const parts = matchTime.split(' ');
            const datePart = parts[0].split('.');
            if (datePart.length >= 2) {
                displayDate = `${datePart[0]}.${datePart[1]}` + (parts[1] ? ' ' + parts[1] : '');
            }
        }
    } catch (e) {}

    const oddsDisplay = odds > 0 ? Number(odds).toFixed(2) : '—';

    const evDisplay = isLM
        ? (best.movement_pct !== undefined && best.movement_pct !== null
            ? (best.movement_pct >= 0 ? '+' : '') + best.movement_pct + '%'
            : '—')
        : (ev !== 0 ? (ev >= 0 ? '+' : '') + Number(ev).toFixed(1) + '%' : '—');

    const probDisplay = isLM
        ? (best.snapshots_count ? best.snapshots_count + ' сним.' : '—')
        : (prob > 0 ? Number(prob).toFixed(0) + '%' : '—');

    const evLabel = isLM ? 'Движение' : 'EV';
    const probLabel = isLM ? 'Снимков' : 'Prob';

    const itemIndex = m._index !== undefined ? m._index : -1;

    const countryHtml = m.country
        ? ` • ${m.country_flag || ''} <span style="color:var(--text-secondary);">${escapeHtml(m.country)}</span>`
        : '';

    const lmBadge = isLM
        ? `<span class="bet-badge" style="background:rgba(167,139,250,0.15);color:#a78bfa;border:1px solid rgba(167,139,250,0.3);">
             📈 LM ${best.direction === 'drop' ? '📉' : '📈'}
           </span>`
        : '';

    const lmMovementHtml = isLM && best.old_odds
        ? `<div style="margin-top:6px;font-size:10px;color:var(--text-tertiary);">
             <span style="color:#a78bfa;font-weight:700;">${best.old_odds} → ${best.odds}</span>
             ${best.movement_hours ? ` • за ${best.movement_hours}ч` : ''}
           </div>`
        : '';

    const dmHtml = renderDayMovement(m.dm, m);
    const _key = itemKey(m);
    const _fav = isFav(m);
    const _note = betNotes[_key] || '';
    const noteHtml = _note ? `<div class="card-note">📝 ${escapeHtml(_note)}</div>` : '';
    const favBtn = `<button class="fav-btn ${_fav ? 'on' : ''}" data-key="${escapeHtml(_key)}" onclick="toggleFav(event, this.dataset.key)" aria-label="Избранное">${_fav ? '★' : '☆'}</button>`;
    const _mv = dmMaxMove(m.dm);
    const dmHotClass = Math.abs(_mv) >= DM_HOT_PCT ? (_mv < 0 ? 'dm-hot-drop' : 'dm-hot-rise')
        : Math.abs(_mv) >= DM_WARM_PCT ? 'dm-warm' : '';
    const dmFinal = (m.dm && DM_FINISHED.includes(m.dm.status))
        ? '<span class="bet-halftime">🏁 Итог</span>' : '';

    // ★ УЛУЧШЕНИЕ 1: Цветной Score (исправлен баг: было matchScore, стало matchScoreColor)
    let matchScoreColor = 'var(--text-tertiary)';
    let matchScoreBg = 'rgba(255,255,255,0.05)';
    if (matchScore != null) {
        if (matchScore >= 10) {
            matchScoreColor = 'var(--emerald-400)';
            matchScoreBg = 'rgba(16, 185, 129, 0.15)';
        } else if (matchScore >= 7) {
            matchScoreColor = 'var(--gold-400)';
            matchScoreBg = 'rgba(245, 158, 11, 0.15)';
        } else {
            matchScoreColor = 'var(--red-400)';
            matchScoreBg = 'rgba(248, 113, 113, 0.15)';
        }
    }

    // Динамическая сетка: 3 или 4 колонки
    const statsGridStyle = matchScore != null
        ? 'grid-template-columns: repeat(4, 1fr);'
        : '';

    // ★ УЛУЧШЕНИЕ 1: HTML для Score (с фоновым бейджем)
    let scoreHtml = '';
    if (matchScore != null) {
        scoreHtml = `
            <div class="bet-stat">
                <span class="stat-label">Score</span>
                <span class="stat-value" style="
                    color: ${matchScoreColor};
                    font-weight: 800;
                    background: ${matchScoreBg};
                    padding: 2px 6px;
                    border-radius: 6px;
                    display: inline-block;
                    align-self: flex-start;
                    margin-top: 2px;
                ">
                    ${Number(matchScore).toFixed(1)}
                </span>
            </div>
        `;
    }

    return `
        <div class="bet-card ${isActive ? 'active' : ''} ${dmHotClass}"
             data-fixture="${m.fixture_id || ''}"
             data-index="${itemIndex}"
             onclick='handleCardClick(event, ${JSON.stringify(m).replace(/'/g, "&#39;")})'>
            <div class="swipe-hint left">✅ WIN →</div>
            <div class="swipe-hint right">← ❌ LOSS</div>
            <div class="bet-header">
                <div style="flex:1;min-width:0;">
                    <div class="bet-match">${escapeHtml(m.home || '?')} vs ${escapeHtml(m.away || '?')}</div>
                    <div class="bet-league">🏆 ${escapeHtml(league)}${countryHtml}</div>
                    <div class="bet-time">
                        <span>📅 ${escapeHtml(displayDate)}</span>
                        ${m.weather_reason && m.weather_reason !== '🌤️ Нет данных' ? `<span title="${escapeHtml(m.weather_reason)}" style="cursor:help;font-size:10px;">${m.weather_reason.split(',')[0] || ''}</span>` : ''}
                        ${showScore ? `<span class="bet-score" style="color:${scoreColor};">${homeGoals} - ${awayGoals}</span>` : ''}
                        ${hasHalftime && showScore ? `<span class="bet-halftime">1-й тайм: ${htH}-${htA}</span>` : ''}
                        ${dmFinal}
                        ${favBtn}
                        ${(m.live_minute || m.live_status) && result === 'pending' && !(m.dm && DM_FINISHED.includes(m.dm.status)) ? `<span class="bet-halftime">🔴 LIVE ${m.live_status === 'HT' ? 'HT' : (m.live_minute || '') + "'"}</span>` : ''}
                    </div>
                </div>
                <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                    ${lmBadge}
                    <span class="bet-badge ${betClass}">${escapeHtml(betLabel)}</span>
                    ${resultBadge}
                </div>
            </div>
            <div class="bet-stats" style="${statsGridStyle}${m.type === 'daymatch' ? 'display:none;' : ''}">
                <div class="bet-stat">
                    <span class="stat-label">Кэф</span>
                    <span class="stat-value">${oddsDisplay}</span>
                </div>
                <div class="bet-stat">
                    <span class="stat-label">${evLabel}</span>
                    <span class="stat-value ${isLM ? 'gold' : evColor}">${evDisplay}</span>
                </div>
                <div class="bet-stat">
                    <span class="stat-label">${probLabel}</span>
                    <span class="stat-value ${isLM ? 'emerald' : probColor}">${probDisplay}</span>
                </div>
                ${scoreHtml}
            </div>
            ${lmMovementHtml}
            ${dmHtml}
            ${noteHtml}
        </div>
    `;
}

function dmClvHtml(d, m) {
    if (!d || !m || !m.odds) return '';
    const k = dmBetSelection(m.bet);
    const x = k && d.selections ? d.selections[k] : null;
    if (!x) return '';
    const clv = (Number(m.odds) / Number(x.last) - 1) * 100;
    const good = clv >= 0;
    return `<div class="dm-clv" style="color:${good ? 'var(--emerald-400)' : 'var(--red-400)'};">
        ${good ? '✅' : '⚠️'} Взяли ${Number(m.odds).toFixed(2)} • сейчас/закрытие ${Number(x.last).toFixed(2)}
        (${clv > 0 ? '+' : ''}${clv.toFixed(1)}%)</div>`;
}

function renderDayMovement(d, m) {
    if (!d || !d.selections) return '';
    const order = ['1', 'X', '2', '1X', 'X2'];
    const names = {'1': 'П1', 'X': 'Х', '2': 'П2', '1X': '1Х', 'X2': 'Х2'};
    const keys = order.filter(k => d.selections[k]);
    if (!keys.length) return '';
    const chips = keys.map(k => {
        const x = d.selections[k];
        const ch = Number(x.change_pct) || 0;
        const col = ch < -0.05 ? 'var(--emerald-400)' : ch > 0.05 ? 'var(--red-400)' : 'var(--text-tertiary)';
        const arrow = ch < -0.05 ? '▼' : ch > 0.05 ? '▲' : '•';
        return `<div class="dm-chip">
            <span class="dm-name">${names[k]}</span>
            <span class="dm-odds">${Number(x.first).toFixed(2)} → <b>${Number(x.last).toFixed(2)}</b></span>
            <span class="dm-ch" style="color:${col};">${arrow} ${ch > 0 ? '+' : ''}${ch}%</span>
        </div>`;
    }).join('');
    const main = d.selections['2'] || d.selections[keys[0]];
    const spark = renderDmSpark(main.points || []);
    return `<div class="dm-box">
        <div class="dm-title">📈 Движение кэфов <span style="opacity:.7;">• ${d.snapshots_count} сним.</span></div>
        <div class="dm-chips">${chips}</div>
        ${spark}
        ${dmClvHtml(d, m)}
    </div>`;
}

function renderDmSpark(points) {
    if (!points || points.length < 2) return '';
    const vals = points.map(p => p[1]);
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const w = 260, h = 34, pad = 3;
    const rng = (mx - mn) || 1;
    const pts = vals.map((v, i) => {
        const x = pad + i * (w - 2 * pad) / (vals.length - 1);
        const y = h - pad - (v - mn) / rng * (h - 2 * pad);
        return x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
    const up = vals[vals.length - 1] > vals[0];
    const col = vals[vals.length - 1] < vals[0] ? '#34d399' : up ? '#f87171' : '#94a3b8';
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:34px;margin-top:6px;">
        <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-tertiary);">
            <span>${points[0][0]}</span><span>${points[points.length - 1][0]}</span></div>`;
}

function handleCardClick(event, m) {
    if (event.target.closest('.swipe-hint')) return;
    if (event.defaultPrevented) return;
    showMatchDetail(m);
}

function getBetClass(label) {
    if (!label) return 'bet-1x';
    const l = label.toLowerCase();
    if (l.includes('x2')) return 'bet-x2';
    if (l.includes('1x')) return 'bet-1x';
    if (l.includes('тм') || l.includes('under')) return 'bet-under';
    if (l.includes('тб') || l.includes('over')) return 'bet-over';
    if (l.includes('обз') || l.includes('btts')) return 'bet-btts';
    return 'bet-1x';
}

// ============================================================
// СВАЙПЫ WIN/LOSS
// ★ FIX #6: добавлены mouse-события
// ============================================================
function initCardSwipes() {
    document.querySelectorAll('.bet-card[data-index]').forEach(card => {
        const idx = parseInt(card.dataset.index);
        if (isNaN(idx) || idx < 0) return;
        const item = getItemByIndex(idx);
        if (!item || item.is_active) return;
        if (item.result && item.result !== 'pending') return;

        let startX = 0, startY = 0, currentX = 0, isSwiping = false;

        function start(clientX, clientY) {
            startX = clientX;
            startY = clientY;
            isSwiping = false;
        }
        function move(clientX, clientY) {
            if (!startX) return;
            const dx = clientX - startX;
            const dy = clientY - startY;
            if (Math.abs(dy) > Math.abs(dx)) return;
            if (Math.abs(dx) < 10) return;
            isSwiping = true;
            currentX = dx;
            if (dx > 0) {
                card.classList.add('swipe-left');
                card.classList.remove('swipe-right');
            } else {
                card.classList.add('swipe-right');
                card.classList.remove('swipe-left');
            }
        }
        function end() {
            if (!isSwiping) { startX = 0; currentX = 0; return; }
            if (currentX > SWIPE_THRESHOLD) { haptic(30); quickSetResult(idx, 'win'); }
            else if (currentX < -SWIPE_THRESHOLD) { haptic(30); quickSetResult(idx, 'loss'); }
            else { card.classList.remove('swipe-left', 'swipe-right'); }
            startX = 0; currentX = 0; isSwiping = false;
        }

        // touch (мобильные)
        card.addEventListener('touchstart', (e) => start(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
        card.addEventListener('touchmove', (e) => move(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
        card.addEventListener('touchend', end, { passive: true });

        // ★ FIX #6: mouse (десктоп)
        card.addEventListener('mousedown', (e) => { if (e.button === 0) start(e.clientX, e.clientY); });
        card.addEventListener('mousemove', (e) => { if (startX) move(e.clientX, e.clientY); });
        card.addEventListener('mouseup', end);
        card.addEventListener('mouseleave', () => { if (startX) end(); });
    });
}

async function quickSetResult(displayIndex, result) {
    if (!cachedData) return;
    const item = getItemByIndex(displayIndex);
    if (!item) return;
    const historyIndex = getHistoryIndex(displayIndex);
    if (historyIndex === null) {
        showNotification('❌ Нельзя изменить активный матч', 'error');
        return;
    }
    try {
        const resp = await fetch(API_BASE + '/api/edit_bet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                index: historyIndex,
                result: result,
                home_goals: item.home_goals,
                away_goals: item.away_goals
            })
        });
        const data = await resp.json();
        if (data.success) {
            const emoji = result === 'win' ? '✅' : result === 'loss' ? '❌' : '🔄';
            showNotification(`${emoji} Результат: ${result.toUpperCase()}`, 'success');
            refreshData();
        } else {
            showNotification('❌ Ошибка: ' + data.error, 'error');
        }
    } catch (e) {
        showNotification('❌ Ошибка: ' + e.message, 'error');
    }
}

// ============================================================
