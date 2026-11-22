// MATCHES PAGE
// ============================================================
let _lastDisplayed = [];
function renderMatchesPage(data) {
    if (!data) data = cachedData;
    if (!data) return;
    const history = data.history || [];
    const matches = data.matches || [];
    let allItems = buildAllItems(history, matches);

    if (matchesFilter !== 'all') {
        if (matchesFilter === 'active') allItems = allItems.filter(i => i.is_active);
        else if (matchesFilter === 'dm_live') allItems = allItems.filter(i => dmState(i) === 'live');
        else if (matchesFilter === 'dm_fin') allItems = allItems.filter(i => dmState(i) === 'fin');
        else if (matchesFilter === 'dm_soon') allItems = allItems.filter(i => dmState(i) === 'soon');
        else if (matchesFilter === 'fav') allItems = allItems.filter(i => isFav(i));
        else if (matchesFilter === 'dm_move') allItems = allItems.filter(i => Math.abs(dmMaxMove(i.dm)) >= DM_WARM_PCT);
        else allItems = allItems.filter(i => i.result === matchesFilter);
    }
    if (matchesSearchQuery) {
        const q = matchesSearchQuery.toLowerCase();
        allItems = allItems.filter(i =>
            (i.home && i.home.toLowerCase().includes(q)) ||
            (i.away && i.away.toLowerCase().includes(q)) ||
            (i.league && i.league.toLowerCase().includes(q)) ||
            (i.bet && i.bet.toLowerCase().includes(q))
        );
    }
    allItems = sortItems(allItems);
    const total = allItems.length;
    const limit = showAllItems ? total : ITEMS_LIMIT;
    const displayed = allItems.slice(0, limit);

    document.getElementById('matchesCount').textContent = total + ' записей';

    const showAllWrap = document.getElementById('showAllWrapper');
    if (total > ITEMS_LIMIT) {
        showAllWrap.style.display = 'block';
        document.getElementById('showAllBtn').textContent = showAllItems
            ? '📉 Свернуть'
            : `📊 Показать все (${total})`;
    } else {
        showAllWrap.style.display = 'none';
    }

    displayed.forEach((item, i) => item._index = i);
    _lastDisplayed = displayed;
    renderDaySummary();

    if (viewMode === 'cards') renderCardsView(displayed);
    else renderTableView(displayed);
}

function renderCardsView(items) {
    const container = document.getElementById('matchesCardsView');
    const tableContainer = document.getElementById('matchesTableView');
    tableContainer.style.display = 'none';
    container.style.display = 'block';
    if (items.length === 0) {
        container.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Нет матчей</div>
                <div class="desc">Попробуйте изменить фильтры</div>
            </div>
        `;
        return;
    }
    container.innerHTML = items.map(item => renderBetCard(item, item.is_active)).join('');
    setTimeout(initCardSwipes, 100);
}

function renderTableView(items) {
    const cardsContainer = document.getElementById('matchesCardsView');
    const tableContainer = document.getElementById('matchesTableView');
    cardsContainer.style.display = 'none';
    tableContainer.style.display = 'block';
    const tbody = document.getElementById('matchesTableBody');
    if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" class="no-data" style="padding:30px;text-align:center;">Нет данных</td></tr>`;
        return;
    }
    tbody.innerHTML = items.map((item, idx) => {
        const profitClass = item.profit > 0 ? 'profit-positive' : (item.profit < 0 ? 'profit-negative' : '');
        const profitStr = item.profit > 0 ? '+' + item.profit : item.profit;
        const oddsStr = item.odds > 0 ? Number(item.odds).toFixed(2) : '—';
        const evStr = item.ev !== 0 ? item.ev + '%' : '—';
        const htStr = (item.halftime_home != null && item.halftime_away != null)
            ? `${item.halftime_home}-${item.halftime_away}` : '—';
        return `
            <tr>
                <td>${idx + 1}</td>
                <td style="font-size:10px;white-space:nowrap;">${item.date}</td>
                <td><strong>${escapeHtml(item.home)}</strong> vs <strong>${escapeHtml(item.away)}</strong></td>
                <td>${item.score}</td>
                <td>${htStr}</td>
                <td>${escapeHtml(item.bet)}</td>
                <td>${oddsStr}</td>
                <td>$${item.stake}</td>
                <td>${evStr}</td>
                <td><span class="badge ${item.result}">${item.result}</span></td>
                <td class="${profitClass}">${profitStr}</td>
                <td>—</td>
            </tr>
        `;
    }).join('');
}

function buildAllItems(history, matches) {
    const items = [];
    const historyFids = new Set((history || []).map(h => h.fixture_id).filter(Boolean));
    const dmMap = {};
    (dayMatchesData || []).forEach(d => { if (d.fixture_id) dmMap[d.fixture_id] = d; });
    const seenFids = new Set();
    if (matches && matches.length) {
        matches.forEach(m => {
            if (m.fixture_id && historyFids.has(m.fixture_id)) return;   // этот матч есть в истории (со счётом)
            const best = m.best_bet || (m.bets && m.bets[0]) || {};
            items.push({
                type: 'match',
                date: m.match_time || 'Сегодня',
                home: m.home || 'Unknown',
                away: m.away || 'Unknown',
                score: '-',
                bet: best.label || '—',
                odds: best.odds || 0,
                stake: best.stake || 0,
                ev: best.ev || 0,
                prob: best.prob || 0,
                result: 'pending',
                profit: 0,
                is_active: true,
                league: m.league || '',
                country: m.country || '',
                country_flag: m.country_flag || '',
                total_xg: m.total_xg || 0,
                fixture_id: m.fixture_id,
                best_bet: best,
                bets: m.bets || [],
                halftime_home: null,
                halftime_away: null,
                source: m.source || '',
            });
        });
    }
    if (history && history.length) {
        history.forEach(h => {
            items.push({
                type: 'history',
                date: h.date || '-',
                home: h.home || 'Unknown',
                away: h.away || 'Unknown',
                score: (h.home_goals != null && h.away_goals != null)
                    ? h.home_goals + ' - ' + h.away_goals
                    : (h.live_score ? String(h.live_score).replace('-', ' - ') : '-'),
                live_minute: h.live_minute || 0,
                live_status: h.live_status || '',
                bet: h.bet || '—',
                odds: h.odds || 0,
                stake: h.stake || 0,
                ev: h.ev || 0,
                prob: h.prob || 0,
                result: h.result || 'pending',
                profit: h.profit || 0,
                is_active: false,
                league: h.league || '',
                country: h.country || '',
                country_flag: h.country_flag || '',
                total_xg: 0,
                fixture_id: h.fixture_id,
                best_bet: { label: h.bet, odds: h.odds, ev: h.ev, prob: h.prob },
                bets: [],
                halftime_home: h.halftime_home,
                halftime_away: h.halftime_away,
                home_goals: h.home_goals,
                away_goals: h.away_goals,
                source: h.source || '',
            });
        });
    }
    // применяем данные снимков: движение кэфов + счёт
    items.forEach(it => {
        const d = it.fixture_id ? dmMap[it.fixture_id] : null;
        if (!d) return;
        seenFids.add(it.fixture_id);
        it.dm = d;
        if (d.home_goals != null && d.away_goals != null && (!it.score || it.score === '-')) {
            it.score = d.home_goals + ' - ' + d.away_goals;
            it.home_goals = d.home_goals; it.away_goals = d.away_goals;
        }
        if (it.halftime_home == null && d.halftime_home != null) {
            it.halftime_home = d.halftime_home; it.halftime_away = d.halftime_away;
        }
    });
    // матчи со снимками, по которым нет ставки
    (dayMatchesData || []).forEach(d => {
        if (!d.fixture_id || seenFids.has(d.fixture_id)) return;
        const fin = DM_FINISHED.includes(d.status);
        const live = DM_LIVE.includes(d.status);
        const hasScore = d.home_goals != null && d.away_goals != null;
        items.push({
            type: 'daymatch',
            date: d.match_time || 'Сегодня',
            home: d.home || 'Unknown', away: d.away || 'Unknown',
            score: hasScore ? d.home_goals + ' - ' + d.away_goals : '-',
            bet: '—', odds: 0, stake: 0, ev: 0, prob: 0,
            result: 'pending', profit: 0,
            is_active: !fin && !live,
            league: d.league || '', country: d.country || '', country_flag: d.country_flag || '',
            total_xg: 0, fixture_id: d.fixture_id,
            best_bet: {}, bets: [],
            halftime_home: d.halftime_home, halftime_away: d.halftime_away,
            home_goals: d.home_goals, away_goals: d.away_goals,
            live_minute: live ? (d.elapsed || 0) : 0,
            live_status: live ? d.status : '',
            source: 'snapshots', dm: d,
        });
    });
    return items;
}

function sortItems(items) {
    const dir = sortDir === 'asc' ? 1 : -1;
    if (sortBy === 'time' || sortBy === 'move' || sortBy === 'status') {
        const rank = {live: 0, soon: 1, fin: 2};
        return items.sort((a, b) => {
            if (sortBy === 'time') return dir * (dmTimeValue(a) - dmTimeValue(b));
            if (sortBy === 'move') return dir * (Math.abs(dmMaxMove(a.dm)) - Math.abs(dmMaxMove(b.dm)));
            const d = rank[dmState(a)] - rank[dmState(b)];
            return d !== 0 ? d : dmTimeValue(a) - dmTimeValue(b);
        });
    }
    return items.sort((a, b) => {
        if (a.is_active && !b.is_active) return -1;
        if (!a.is_active && b.is_active) return 1;
        switch (sortBy) {
            case 'date': try { return dir * (new Date(a.date) - new Date(b.date)); } catch { return 0; }
            case 'odds': return dir * ((a.odds || 0) - (b.odds || 0));
            case 'stake': return dir * ((a.stake || 0) - (b.stake || 0));
            case 'ev': return dir * ((a.ev || 0) - (b.ev || 0));
            case 'profit': return dir * ((a.profit || 0) - (b.profit || 0));
            case 'result': return dir * ((a.result || '').localeCompare(b.result || ''));
            default: return 0;
        }
    });
}

function getItemByIndex(index) {
    if (_lastDisplayed && _lastDisplayed[index]) return _lastDisplayed[index];
    if (!cachedData) return null;
    let all = sortItems(buildAllItems(cachedData.history || [], cachedData.matches || []));
    const limit = showAllItems ? all.length : ITEMS_LIMIT;
    all = all.slice(0, limit);
    return all[index] || null;
}

// ★ FIX #4: сначала по fixture_id + home/away/date, потом fallback
function getHistoryIndex(displayIndex) {
    if (!cachedData) return null;
    const history = cachedData.history || [];
    let all = sortItems(buildAllItems(history, cachedData.matches || []));
    const limit = showAllItems ? all.length : ITEMS_LIMIT;
    all = all.slice(0, limit);
    const item = all[displayIndex];
    if (!item || item.type !== 'history') return null;

    // По fixture_id + home/away/date (основной матч)
    if (item.fixture_id) {
        for (let i = 0; i < history.length; i++) {
            const h = history[i];
            if (h.fixture_id === item.fixture_id &&
                (h.home || '') === item.home &&
                (h.away || '') === item.away &&
                (h.date || '') === item.date) return i;
        }
    }
    // Fallback: home/away/date/bet (для старых записей без fixture_id)
    for (let i = 0; i < history.length; i++) {
        const h = history[i];
        if ((h.home || '') === item.home &&
            (h.away || '') === item.away &&
            (h.date || '') === item.date &&
            (h.bet || '') === item.bet) return i;
    }
    return null;
}

// ============================================================
// FILTERS
// ============================================================
function filterMatches() {
    matchesSearchQuery = document.getElementById('matchesSearch').value.toLowerCase();
    renderMatchesPage();
}

function setMatchFilter(filter) {
    matchesFilter = filter;
    document.querySelectorAll('.filter-btn[data-filter]').forEach(b => {
        b.classList.toggle('active', b.dataset.filter === filter);
    });
    haptic(6);
    renderMatchesPage();
}

function setMatchSort(v) {
    sortBy = v;
    sortDir = (v === 'time' || v === 'status') ? 'asc' : 'desc';
    haptic(6);
    renderMatchesPage();
}

function renderDaySummary() {
    const el = document.getElementById('dayMatchesSummary');
    if (!el) return;
    const list = dayMatchesData || [];
    if (!list.length) { el.innerHTML = ''; return; }
    let live = 0, fin = 0, soon = 0, hot = 0;
    list.forEach(d => {
        if (DM_FINISHED.includes(d.status)) fin++;
        else if (DM_LIVE.includes(d.status)) live++;
        else soon++;
        if (Math.abs(dmMaxMove(d)) >= DM_HOT_PCT) hot++;
    });
    const hist = (cachedData && cachedData.history) || [];
    const fids = new Set(list.map(d => d.fixture_id));
    let w = 0, l = 0, profit = 0;
    hist.forEach(h => {
        if (!fids.has(h.fixture_id)) return;
        if (h.result === 'win') w++;
        else if (h.result === 'loss') l++;
        if (h.result === 'win' || h.result === 'loss') profit += Number(h.profit) || 0;
    });
    const pc = profit > 0 ? 'var(--emerald-400)' : profit < 0 ? 'var(--red-400)' : 'var(--text-secondary)';
    el.innerHTML = `<div class="dm-summary">
        <div class="dm-sum-item"><b>${list.length}</b><span>со снимками</span></div>
        <div class="dm-sum-item"><b>${live}</b><span>🔴 идут</span></div>
        <div class="dm-sum-item"><b>${soon}</b><span>🕒 скоро</span></div>
        <div class="dm-sum-item"><b>${fin}</b><span>🏁 завершены</span></div>
        <div class="dm-sum-item"><b>${hot}</b><span>🔥 движение</span></div>
        <div class="dm-sum-item"><b>${w}/${l}</b><span>WIN / LOSS</span></div>
        <div class="dm-sum-item"><b style="color:${pc};">${profit > 0 ? '+' : ''}${profit.toFixed(1)}</b><span>прибыль дня</span></div>
    </div>`;
}

function setViewMode(mode) {
    viewMode = mode;
    safeLSSet('viewMode', mode);  // ★ FIX #12
    document.getElementById('viewCardsBtn').style.color = mode === 'cards' ? 'var(--emerald-400)' : '';
    document.getElementById('viewTableBtn').style.color = mode === 'table' ? 'var(--emerald-400)' : '';
    haptic(6);
    renderMatchesPage();
}

function sortTable(field) {
    if (sortBy === field) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else { sortBy = field; sortDir = 'desc'; }
    haptic(6);
    renderMatchesPage();
}

function toggleShowAll() {
    showAllItems = !showAllItems;
    haptic(6);
    renderMatchesPage();
}

// ============================================================
// MATCH DETAIL
// ============================================================
function renderDmDetail(match) {
    const d = match && match.dm;
    if (!d || !d.selections) return '';
    const names = {'1': 'П1', 'X': 'Х', '2': 'П2', '1X': '1Х', 'X2': 'Х2'};
    const keys = ['1', 'X', '2', '1X', 'X2'].filter(k => d.selections[k]);
    if (!keys.length) return '';
    const betKey = dmBetSelection(match.bet);
    let h = '<div class="dm-detail"><div class="dm-title">📈 Движение кэфов по снимкам</div>';
    keys.forEach(k => {
        const x = d.selections[k];
        const ch = Number(x.change_pct) || 0;
        const col = ch < -0.05 ? 'var(--emerald-400)' : ch > 0.05 ? 'var(--red-400)' : 'var(--text-tertiary)';
        h += `<div class="dm-detail-sel">
            <div style="display:flex;justify-content:space-between;font-size:12px;">
                <b>${names[k]}${k === betKey ? ' • ваша ставка' : ''}</b>
                <span style="color:${col};font-weight:800;">${ch > 0 ? '+' : ''}${ch}%</span>
            </div>
            <div style="font-size:11px;color:var(--text-secondary);">старт ${Number(x.first).toFixed(2)} → сейчас ${Number(x.last).toFixed(2)} • мин ${Number(x.min).toFixed(2)} • макс ${Number(x.max).toFixed(2)}</div>
            ${renderDmSpark(x.points || [])}
            <div class="dm-times">${(x.points || []).map(p => `<span>${escapeHtml(String(p[0]))} <b>${Number(p[1]).toFixed(2)}</b></span>`).join('')}</div>
        </div>`;
    });
    h += dmClvHtml(d, match) + '</div>';
    return h;
}

function showMatchDetail(match) {
    const modal = document.getElementById('matchDetailModal');
    const body = document.getElementById('matchDetailBody');
    const title = document.getElementById('matchDetailTitle');
    title.textContent = `${match.home} vs ${match.away}`;
    const best = match.best_bet || {};
    const bets = match.bets || [];
    const isLM = (match.source || '') === 'line_movement';

    const countryStr = match.country
        ? ` • ${match.country_flag || ''} ${escapeHtml(match.country)}`
        : '';

    let html = `
        <div style="text-align:center;margin-bottom:16px;">
            <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:4px;">
                ${escapeHtml(match.league || '')}${countryStr}
            </div>
            <div style="font-size:12px;color:var(--text-secondary);">${match.date || match.match_time || ''}</div>
            ${match.halftime_home != null ? `<div style="font-size:11px;color:var(--text-tertiary);margin-top:4px;">1-й тайм: ${match.halftime_home}-${match.halftime_away}</div>` : ''}
        </div>
    `;

    if (isLM) {
        const direction = best.direction === 'drop' ? '📉' : '📈';
        html += `
            <div style="text-align:center;padding:12px;background:rgba(167,139,250,0.08);border-radius:12px;border:1px solid rgba(167,139,250,0.2);margin-bottom:16px;">
                <div style="font-size:11px;color:#a78bfa;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
                    📈 LINE MOVEMENT
                </div>
                <div style="font-size:24px;font-weight:800;color:#a78bfa;">
                    ${direction} ${best.movement_pct >= 0 ? '+' : ''}${best.movement_pct}%
                </div>
                <div style="font-size:11px;color:var(--text-tertiary);margin-top:4px;">
                    за ${best.movement_hours || 0}ч
                </div>
            </div>
            <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px;">
                <div class="stat-card">
                    <div class="value">${best.old_odds || '—'}</div>
                    <div class="label">Было</div>
                </div>
                <div class="stat-card">
                    <div class="value emerald">${best.odds || '—'}</div>
                    <div class="label">Стало</div>
                </div>
                <div class="stat-card">
                    <div class="value gold">${best.snapshots_count || 0}</div>
                    <div class="label">Снимков</div>
                </div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(167,139,250,0.05);border-radius:10px;border:1px solid rgba(167,139,250,0.15);">
                <div style="font-size:11px;color:var(--text-tertiary);">
                    💡 Кэф резко изменился — «умные деньги» идут в эту сторону
                </div>
                <div style="font-size:11px;color:var(--text-tertiary);margin-top:6px;">
                    💵 Stake: $${best.stake || 0}
                </div>
            </div>
        `;
    } else {
        const scoreNum = (typeof match.score === 'number' && isFinite(match.score)) ? match.score : null;
        html += `
            <div class="stats-grid" style="grid-template-columns:repeat(${scoreNum != null ? '4' : '3'},1fr);margin-bottom:16px;">
                <div class="stat-card">
                    <div class="value emerald">${best.ev ? Number(best.ev).toFixed(1) + '%' : '—'}</div>
                    <div class="label">EV</div>
                </div>
                <div class="stat-card">
                    <div class="value">${best.odds ? Number(best.odds).toFixed(2) : '—'}</div>
                    <div class="label">Кэф</div>
                </div>
                <div class="stat-card">
                    <div class="value gold">${best.prob ? Number(best.prob).toFixed(0) + '%' : '—'}</div>
                    <div class="label">Prob</div>
                </div>
                ${scoreNum != null ? `
                <div class="stat-card">
                    <div class="value" style="color:${scoreNum >= 75 ? 'var(--emerald-400)' : scoreNum >= 65 ? 'var(--gold-400)' : 'var(--red-400)'};font-weight:800;">
                        ${scoreNum.toFixed(1)}
                    </div>
                    <div class="label">Score</div>
                </div>
                ` : ''}
            </div>
        `;
        if (bets.length > 1) {
            html += `<div style="font-size:11px;color:var(--text-tertiary);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Все ставки</div>`;
            html += bets.slice(0, 7).map(b => {
                const emoji = b.ev > 10 ? '🟢' : b.ev > 5 ? '🟡' : '🔴';
                return `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color);font-size:12px;">
                    <span>${emoji} ${b.label}</span>
                    <span style="color:var(--text-secondary);">EV ${b.ev}% · Кэф ${b.odds}</span>
                </div>`;
            }).join('');
        }
    }

    html += renderDmDetail(match);
    html += renderNoteBox(match);
    body.innerHTML = html;
    modal.classList.add('active');
    haptic(8);
}

function closeMatchDetail() {
    document.getElementById('matchDetailModal').classList.remove('active');
}

// ============================================================
