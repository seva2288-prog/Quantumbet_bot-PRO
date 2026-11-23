// ============================================================
// ЭКРАН «СЕГОДНЯ» И КАЛЕНДАРЬ РЕЗУЛЬТАТОВ
// ============================================================
let _todayItems = [];

function refreshToday() {
    haptic(8);
    loadPageData('today');
}

function dmCountdown(it) {
    const t = dmTimeValue(it);
    if (!t) return '';
    const mins = Math.round((t - Date.now()) / 60000);
    if (mins <= 0) return 'скоро';
    if (mins < 60) return 'через ' + mins + ' мин';
    return 'через ' + Math.floor(mins / 60) + 'ч ' + (mins % 60) + 'м';
}

function todayRow(it, idx) {
    const st = dmState(it);
    const d = it.dm || {};
    const time = String(it.date || '').split(' ')[1] || '';
    const score = (it.home_goals != null && it.away_goals != null) ? it.home_goals + ':' + it.away_goals : '';
    const mv = dmMaxMove(d);
    const mvCol = mv < -0.05 ? 'var(--emerald-400)' : mv > 0.05 ? 'var(--red-400)' : 'var(--text-tertiary)';
    let status = '';
    if (st === 'live') status = `<span class="today-live">🔴 ${d.status === 'HT' ? 'перерыв' : (d.elapsed || it.live_minute || '') + "'"}</span>`;
    else if (st === 'soon') status = `<span class="today-soon">${time} • ${dmCountdown(it)}</span>`;
    else status = `<span class="today-fin">🏁 ${time}</span>`;
    let bet = '';
    if (it.type !== 'daymatch' && it.odds) {
        const ic = it.result === 'win' ? '✅' : it.result === 'loss' ? '❌' : it.result === 'push' ? '➖' : '🎯';
        bet = `<span class="today-bet">${ic} ${escapeHtml(String(it.bet))} @ ${Number(it.odds).toFixed(2)}</span>`;
    }
    return `<div class="today-row ${st}" onclick="showMatchDetail(_todayItems[${idx}])">
        <div class="today-main">
            <div class="today-status">${status}</div>
            <div class="today-teams">${escapeHtml(it.home)} — ${escapeHtml(it.away)}</div>
            <div class="today-sub">
                <span>${escapeHtml(it.league || '')}</span>
                <span style="color:${mvCol};font-weight:700;">${mv ? (mv > 0 ? '+' : '') + mv + '%' : ''}</span>
                ${dmHourBadge(d)} ${bet}
            </div>
        </div>
        <div class="today-score">${score}</div>
    </div>`;
}

function renderTodayPage() {
    const body = document.getElementById('todayBody');
    if (!body) return;
    const history = (cachedData && cachedData.history) || [];
    const matches = (cachedData && cachedData.matches) || [];
    const items = buildAllItems(history, matches).filter(i => i.dm);
    const groups = {live: [], soon: [], fin: []};
    items.forEach(i => groups[dmState(i)].push(i));
    groups.live.sort((a, b) => (b.dm.elapsed || 0) - (a.dm.elapsed || 0));
    groups.soon.sort((a, b) => dmTimeValue(a) - dmTimeValue(b));
    groups.fin.sort((a, b) => dmTimeValue(b) - dmTimeValue(a));
    _todayItems = [...groups.live, ...groups.soon, ...groups.fin];

    const hot = items.filter(i => Math.abs(dmMaxMove(i.dm)) >= DM_HOT_PCT || Math.abs(dmMaxHour(i.dm)) >= DM_HOUR_PCT).length;
    const sum = document.getElementById('todaySummary');
    if (sum) sum.innerHTML = `<div class="dm-summary" style="grid-template-columns:repeat(4,1fr);">
        <div class="dm-sum-item"><b>${groups.live.length}</b><span>🔴 идут</span></div>
        <div class="dm-sum-item"><b>${groups.soon.length}</b><span>🕒 скоро</span></div>
        <div class="dm-sum-item"><b>${groups.fin.length}</b><span>🏁 завершены</span></div>
        <div class="dm-sum-item"><b>${hot}</b><span>🔥 движение</span></div></div>`;

    let idx = 0;
    const section = (title, arr) => arr.length
        ? `<div class="today-section">${title} <span>${arr.length}</span></div>` + arr.map(i => todayRow(i, idx++)).join('')
        : '';
    body.innerHTML = _todayItems.length
        ? section('🔴 Идут сейчас', groups.live) + section('🕒 Ближайшие', groups.soon) + section('🏁 Завершены', groups.fin)
        : '<div class="card"><div style="font-size:13px;color:var(--text-tertiary);">Сегодня пока нет матчей со снимками. Бот делает снимки для матчей 6 лиг Line Movement.</div></div>';

    const feed = document.getElementById('todayFeed');
    if (feed) feed.innerHTML = (dayFeed && dayFeed.length)
        ? dayFeed.map(e => `<div class="feed-item"><span class="feed-time">${escapeHtml(e.time || '')}</span><span>${escapeHtml(e.text || '')}</span></div>`).join('')
        : '<div style="font-size:12px;color:var(--text-tertiary);">Событий пока нет</div>';
}

// ===== Календарь результатов =====
let calMonth = null;     // первый день показываемого месяца
let calSelected = null;  // 'YYYY-MM-DD'

function betDayKey(b) {
    const m = String(b.match_time || '').match(/^(\d{2})\.(\d{2})\.(\d{4})/);
    if (m) return m[3] + '-' + m[2] + '-' + m[1];
    const d = String(b.date || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return d ? d[0] : null;
}
function calShift(delta) {
    calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() + delta, 1);
    calSelected = null;
    renderCalendar();
}
function calSelect(key) {
    calSelected = (calSelected === key) ? null : key;
    haptic(6);
    renderCalendar();
}
function renderCalendar() {
    const box = document.getElementById('calBody');
    if (!box) return;
    if (!calMonth) { const n = new Date(); calMonth = new Date(n.getFullYear(), n.getMonth(), 1); }
    const hist = (cachedData && cachedData.history) || [];
    const days = {};
    hist.forEach(b => {
        const k = betDayKey(b);
        if (!k) return;
        const d = days[k] || (days[k] = {profit: 0, n: 0, settled: 0, bets: []});
        d.n++; d.bets.push(b);
        if (b.result === 'win' || b.result === 'loss') { d.settled++; d.profit += Number(b.profit) || 0; }
    });
    const y = calMonth.getFullYear(), m = calMonth.getMonth();
    const first = new Date(y, m, 1);
    const lead = (first.getDay() + 6) % 7;                 // неделя с понедельника
    const dim = new Date(y, m + 1, 0).getDate();
    const pad = n => String(n).padStart(2, '0');
    const nowD = new Date();
    const todayKey = nowD.getFullYear() + '-' + pad(nowD.getMonth() + 1) + '-' + pad(nowD.getDate());
    let cells = '', monthProfit = 0, monthBets = 0;
    for (let i = 0; i < lead; i++) cells += '<div class="cal-cell empty"></div>';
    for (let day = 1; day <= dim; day++) {
        const key = y + '-' + pad(m + 1) + '-' + pad(day);
        const d = days[key];
        let cls = 'cal-cell', val = '';
        if (d) {
            monthBets += d.n;
            if (d.settled) { monthProfit += d.profit; cls += d.profit > 0 ? ' plus' : d.profit < 0 ? ' minus' : ' zero'; val = (d.profit > 0 ? '+' : '') + Math.round(d.profit); }
            else { cls += ' pend'; val = '⏳'; }
        }
        if (key === todayKey) cls += ' today';
        if (key === calSelected) cls += ' sel';
        cells += `<div class="${cls}" ${d ? `onclick="calSelect('${key}')"` : ''}><span class="cal-d">${day}</span><span class="cal-v">${val}</span></div>`;
    }
    const monthNames = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
    let detail = '';
    if (calSelected && days[calSelected]) {
        const d = days[calSelected];
        detail = `<div class="dm-title" style="margin-top:12px;">${calSelected.split('-').reverse().join('.')} • ${d.n} ставок • ${d.profit > 0 ? '+' : ''}${d.profit.toFixed(2)}</div>` +
            d.bets.map(b => {
                const ic = b.result === 'win' ? '✅' : b.result === 'loss' ? '❌' : b.result === 'push' ? '➖' : '⏳';
                const p = (b.result === 'win' || b.result === 'loss') ? ` • ${Number(b.profit) > 0 ? '+' : ''}${Number(b.profit).toFixed(2)}` : '';
                return `<div class="feed-item"><span>${ic}</span><span>${escapeHtml(String(b.home))} — ${escapeHtml(String(b.away))} • ${escapeHtml(String(b.bet))} @ ${b.odds}${p}</span></div>`;
            }).join('');
    }
    box.innerHTML = `
        <div class="cal-head">
            <button class="btn btn-outline" onclick="calShift(-1)" style="padding:4px 12px;">◀</button>
            <b>${monthNames[m]} ${y}</b>
            <button class="btn btn-outline" onclick="calShift(1)" style="padding:4px 12px;">▶</button>
        </div>
        <div class="cal-grid cal-dow">${['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map(x => `<div>${x}</div>`).join('')}</div>
        <div class="cal-grid">${cells}</div>
        <div style="font-size:11px;color:var(--text-tertiary);margin-top:8px;">За месяц: ${monthBets} ставок, прибыль <b style="color:${monthProfit > 0 ? 'var(--emerald-400)' : monthProfit < 0 ? 'var(--red-400)' : 'inherit'};">${monthProfit > 0 ? '+' : ''}${monthProfit.toFixed(2)}</b>. Нажмите на день, чтобы увидеть ставки.</div>
        ${detail}`;
}
