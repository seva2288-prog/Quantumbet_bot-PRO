// X2 PAGE
// ============================================================
async function loadAutoX2() {
    try {
        const resp = await fetch(API_BASE + '/api/x2_auto?t=' + Date.now());
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.status === 'ok' && Array.isArray(data.candidates)) {
            autoX2Data = data.candidates;
        }
    } catch (e) {
        console.error('loadAutoX2:', e);
    }
}

async function renderX2Page() {
    loadX2Data();
    await loadAutoX2();

    const stats = calcX2Stats();
    document.getElementById('x2TotalFull').textContent = stats.total;
    document.getElementById('x2WinsFull').textContent = stats.wins;
    document.getElementById('x2LossesFull').textContent = stats.losses;
    document.getElementById('x2RoiFull').textContent = stats.roi + '%';
    renderX2List();
}

function renderX2List() {
    const container = document.getElementById('x2List');
    if (!container) return;

    const autoItems = (autoX2Data || []).map(c => ({
        _source: 'auto',
        _id: c.id,
        match: c.match,
        date: (c.match_time || '').split(' ')[0],
        time: (c.match_time || '').split(' ')[1] || '',
        favorite: c.favorite,
        underdog: c.underdog,
        league: c.league,
        country: c.country,
        country_flag: c.country_flag,
        side: c.x2_side || 'X2',
        odds: c.current_odds || c.entry_odds || 0,
        prob: c.x2_prob || 0,
        ev: c.x2_ev || 0,
        trend: c.odds_trend || 0,
        result: c.result || 'pending',
        profit: c.profit || 0,
        score: (c.home_goals != null && c.away_goals != null)
                ? `${c.home_goals}:${c.away_goals}` : '-',
    }));

    const manualItems = (x2Data || []).map(m => ({
        _source: 'manual',
        _id: m.id,
        match: m.match,
        date: m.date,
        time: m.time || '',
        favorite: m.favorite,
        underdog: m.underdog,
        league: '',
        country: '',
        country_flag: '',
        side: 'X2',
        odds: m.odds || 0,
        prob: m.prob || 0,
        ev: 0,
        trend: 0,
        result: m.result || 'pending',
        profit: m.profit || 0,
        score: m.score || '-',
    }));

    let all = [...autoItems, ...manualItems];

    if (x2CurrentFilter !== 'all') {
        all = all.filter(m => m.result === x2CurrentFilter);
    }

    if (all.length === 0) {
        container.innerHTML = `
            <div class="no-data">
                <div class="emoji">📭</div>
                <div class="title">Нет X2 матчей</div>
                <div class="desc">Бот найдёт кандидатов при следующем /update</div>
            </div>
        `;
        return;
    }

    container.innerHTML = all.map((m) => {
        const profitColor = m.profit > 0 ? 'var(--emerald-400)' :
                            m.profit < 0 ? 'var(--red-400)' : 'var(--text-tertiary)';
        const profitStr = m.result === 'win' ? `+$${m.profit}` :
                          m.result === 'loss' ? `-$${Math.abs(m.profit) || 20}` : '$0';
        const resultEmoji = m.result === 'win' ? '✅' :
                            m.result === 'loss' ? '❌' :
                            m.result === 'push' ? '🔄' : '⏳';

        const oddsStr = m.odds > 0 ? Number(m.odds).toFixed(2) : '—';
        const probStr = m.prob > 0 ? Number(m.prob).toFixed(1) + '%' : '—';
        const evStr = m.ev > 0 ? `${m.ev >= 0 ? '+' : ''}${Number(m.ev).toFixed(1)}%` : '';

        const trendEmoji = m.trend > 1 ? '📈' : m.trend < -1 ? '📉' : '';
        const trendStr = m.trend !== 0 ? ` (${m.trend > 0 ? '+' : ''}${m.trend.toFixed(1)}%)` : '';

        const dateTimeStr = m.time ? `${m.date} 🕐 ${m.time}` : m.date;

        const sourceBadge = m._source === 'auto'
            ? '<span class="source-badge auto">🤖 Авто</span>'
            : '<span class="source-badge manual">✏️ Ручной</span>';

        const countryHtml = m.country
            ? ` • ${m.country_flag || ''} <span style="color:var(--text-secondary);">${escapeHtml(m.country)}</span>`
            : '';

        const leagueHtml = m.league
            ? `<div class="bet-league">🏆 ${escapeHtml(m.league)}${countryHtml}</div>`
            : '';

        const scoreHtml = (m.score && m.score !== '-' && m.result !== 'pending')
            ? ` • <strong>${m.score}</strong>` : '';

        return `
            <div class="bet-card" onclick="openX2Detail('${m._source}', ${m._id})">
                <div class="bet-header">
                    <div style="flex:1;min-width:0;">
                        <div class="bet-match">${escapeHtml(m.match)}</div>
                        ${leagueHtml}
                        <div class="bet-league">📅 ${dateTimeStr}${scoreHtml}</div>
                        <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">
                            🏆 ${escapeHtml(m.favorite)} vs 📉 ${escapeHtml(m.underdog)}
                        </div>
                        <div style="margin-top:4px;">${sourceBadge}</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="bet-badge bet-x2" style="margin-bottom:4px;">${m.side}</div>
                        <div style="font-size:14px;">${resultEmoji}</div>
                    </div>
                </div>
                <div class="bet-stats">
                    <div class="bet-stat">
                        <span class="stat-label">Кэф</span>
                        <span class="stat-value">${oddsStr}${trendEmoji}${trendStr}</span>
                    </div>
                    <div class="bet-stat">
                        <span class="stat-label">Prob${evStr ? ' · EV' : ''}</span>
                        <span class="stat-value gold">${probStr} ${evStr}</span>
                    </div>
                    <div class="bet-stat">
                        <span class="stat-label">Прибыль</span>
                        <span class="stat-value" style="color:${profitColor};">${profitStr}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function openX2Detail(source, id) {
    if (source === 'manual') {
        const item = x2Data.find(m => m.id === id);
        if (item) openX2Modal(item);
        return;
    }
    const item = autoX2Data.find(c => c.id === id);
    if (!item) return;
    showNotification(
        `💎 ${item.home} vs ${item.away} | ${item.x2_side} | Prob ${item.x2_prob}%`,
        ''
    );
}

// ★ FIX #9: дедупликация auto + manual
function calcX2Stats() {
    const seen = new Set();
    const all = [];
    for (const c of (autoX2Data || [])) {
        const key = `auto|${c.home || ''}|${c.away || ''}|${(c.match_time || '').split(' ')[0]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        all.push({ result: c.result || 'pending', profit: c.profit || 0, stake: 20 });
    }
    for (const m of (x2Data || [])) {
        const key = `manual|${m.match || ''}|${m.date || ''}`;
        if (seen.has(key)) continue;
        seen.add(key);
        all.push({ result: m.result || 'pending', profit: m.profit || 0, stake: m.stake || 20 });
    }

    const total = all.length;
    const wins = all.filter(m => m.result === 'win').length;
    const losses = all.filter(m => m.result === 'loss').length;
    const totalProfit = all.reduce((s, m) =>
        s + (m.result === 'win' ? (m.profit || 0) : m.result === 'loss' ? -m.stake : 0), 0);
    const totalStake = all.reduce((s, m) => s + (m.stake || 0), 0);
    const winrate = (wins + losses) > 0 ? Math.round((wins / (wins + losses)) * 100) : 0;
    const roi = totalStake > 0 ? Math.round((totalProfit / totalStake) * 100) : 0;
    return { total, wins, losses, totalProfit, winrate, roi };
}

function loadX2Data() {
    x2Data = [];
    x2CurrentFilter = 'all';
    try {
        const saved = safeLSGet('x2_matches');  // ★ FIX #12
        x2Data = saved ? JSON.parse(saved) : [];
    } catch (e) { x2Data = []; }
    try {
        x2CurrentFilter = safeLSGet('x2_filter', 'all');  // ★ FIX #12
    } catch (e) { x2CurrentFilter = 'all'; }

    fetch(API_BASE + '/api/x2_data?t=' + Date.now())
        .then(r => r.json())
        .then(data => {
            if (data && data.status === 'ok' && Array.isArray(data.data) && data.data.length > 0) {
                x2Data = data.data;
                safeLSSet('x2_matches', JSON.stringify(x2Data));  // ★ FIX #12
                renderX2List();
            }
        })
        .catch(() => {});
}

function saveX2Data() {
    safeLSSet('x2_matches', JSON.stringify(x2Data));  // ★ FIX #12
    syncX2ToServer();
}

async function syncX2ToServer() {
    try {
        await fetch(API_BASE + '/api/x2_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data: x2Data })
        });
    } catch (e) {}
}

function setX2Filter(filter) {
    x2CurrentFilter = filter;
    safeLSSet('x2_filter', filter);  // ★ FIX #12
    document.querySelectorAll('#page-x2 .filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.x2filter === filter);
    });
    haptic(6);
    renderX2List();
}

function openX2Modal(data) {
    const modal = document.getElementById('x2Modal');
    const title = document.getElementById('x2ModalTitle');
    if (data) {
        title.textContent = '✏️ Редактировать X2';
        document.getElementById('x2Date').value = data.date || '';
        document.getElementById('x2Time').value = data.time || '';
        document.getElementById('x2Match').value = data.match || '';
        document.getElementById('x2Favorite').value = data.favorite || '';
        document.getElementById('x2Underdog').value = data.underdog || '';
        document.getElementById('x2Odds').value = data.odds || '';
        document.getElementById('x2Stake').value = data.stake || '';
        document.getElementById('x2Score').value = data.score || '';
        document.getElementById('x2Result').value = data.result || 'pending';
        document.getElementById('x2Note').value = data.note || '';
        editingX2Index = x2Data.indexOf(data);
    } else {
        title.textContent = '➕ X2 Матч';
        document.getElementById('x2Date').value = new Date().toISOString().slice(0,10);
        document.getElementById('x2Time').value = '';
        ['x2Match','x2Favorite','x2Underdog','x2Odds','x2Stake','x2Score','x2Note'].forEach(id => document.getElementById(id).value = '');
        document.getElementById('x2Result').value = 'pending';
        editingX2Index = null;
    }
    modal.classList.add('active');
    haptic(8);
}

function closeX2Modal() {
    document.getElementById('x2Modal').classList.remove('active');
    editingX2Index = null;
}

function saveX2Match() {
    const date = document.getElementById('x2Date').value;
    const time = document.getElementById('x2Time').value;
    const match = document.getElementById('x2Match').value.trim();
    const favorite = document.getElementById('x2Favorite').value.trim();
    const underdog = document.getElementById('x2Underdog').value.trim();
    const odds = parseFloat(document.getElementById('x2Odds').value);
    const stake = parseFloat(document.getElementById('x2Stake').value);
    const score = document.getElementById('x2Score').value.trim();
    const result = document.getElementById('x2Result').value;
    const note = document.getElementById('x2Note').value.trim();
    if (!match || !favorite || !underdog || !odds || !stake) {
        showNotification('❌ Заполните все поля', 'error');
        return;
    }
    let profit = 0;
    if (result === 'win') profit = Math.round((stake * odds - stake) * 100) / 100;
    else if (result === 'loss') profit = -stake;

    const existingSource = editingX2Index !== null && editingX2Index >= 0 ? x2Data[editingX2Index].source : null;
    const source = existingSource || 'manual';

    const data = { date, time, match, favorite, underdog, odds, stake, score, result, profit, note, source };
    if (editingX2Index !== null && editingX2Index >= 0) {
        x2Data[editingX2Index] = { ...x2Data[editingX2Index], ...data };
        showNotification('✅ X2 обновлён', 'success');
    } else {
        data.id = Date.now();
        x2Data.push(data);
        showNotification('✅ X2 добавлен', 'success');
    }
    saveX2Data();
    haptic(20);
    closeX2Modal();
    renderX2Page();
}

function editX2Match(index) {
    if (index >= 0 && index < x2Data.length) openX2Modal(x2Data[index]);
}

function deleteX2Match(index) {
    if (index >= 0 && index < x2Data.length && confirm('Удалить?')) {
        x2Data.splice(index, 1);
        saveX2Data();
        renderX2Page();
        haptic(15);
        showNotification('🗑️ Удалено', '');
    }
}

function clearAllX2() {
    if (confirm('⚠️ Удалить все X2 матчи?')) {
        x2Data = [];
        saveX2Data();
        renderX2Page();
        showNotification('🗑️ Все X2 удалены', '');
    }
}

// ============================================================
// AUTO-IMPORT X2
// ============================================================
async function autoImportX2FromLogs() {
    try {
        const resp = await fetch(API_BASE + '/api/matches_log?t=' + Date.now());
        if (!resp.ok) return;
        const data = await resp.json();
        const logText = data.log || '';
        if (!logText.trim()) return;

        const lines = logText.split('\n');
        let newCount = 0;
        const uniqueMatches = new Map();

        for (const line of lines) {
            if (!line.includes('нет мотивации') && !line.includes('no motivation')) continue;

            const m = line.match(/([A-Za-zА-Яа-яÀ-ÿ\s.\-']+?)\s+vs\s+([A-Za-zА-Яа-яÀ-ÿ\s.\-']+?)\s*\|/);
            if (!m) continue;

            const home = m[1].trim();
            const away = m[2].trim();
            const matchName = home + ' vs ' + away;
            if (uniqueMatches.has(matchName)) continue;

            const dateTimeMatch = line.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
            const logDate = dateTimeMatch ? dateTimeMatch[1] : new Date().toISOString().slice(0,10);
            const logTime = dateTimeMatch ? dateTimeMatch[2] : '';

            const xgMatch = line.match(/XG:\s*([\d.]+)/i);
            const xg = xgMatch ? parseFloat(xgMatch[1]) : null;

            const posMatch = line.match(/H:\s*#(\d+),\s*A:\s*#(\d+)/i);
            let favorite = home, underdog = away;
            if (posMatch) {
                const hp = parseInt(posMatch[1]), ap = parseInt(posMatch[2]);
                if (hp > ap) { favorite = away; underdog = home; }
            }

            uniqueMatches.set(matchName, {
                home, away, favorite, underdog,
                date: logDate, time: logTime,
                note: 'Авто-импорт' + (xg ? ' | XG: ' + xg : '')
            });
        }

        const existingNames = new Set(x2Data.map(x => x.match));
        for (const [matchName, info] of uniqueMatches) {
            if (existingNames.has(matchName)) continue;
            x2Data.push({
                id: Date.now() + Math.random() * 1000 + newCount,
                date: info.date, time: info.time,
                match: matchName,
                favorite: info.favorite,
                underdog: info.underdog,
                odds: 0, stake: 0, score: '-',
                result: 'pending', profit: 0,
                note: info.note,
                source: 'auto'
            });
            newCount++;
        }

        if (newCount > 0) {
            saveX2Data();
            showNotification(`🤖 Добавлено ${newCount} X2`, 'success');
            if (currentPage === 'x2') renderX2Page();
        }
    } catch (e) {
        console.error('Auto-import X2 error:', e);
    }
}

// ============================================================
// IMPORT/EXPORT X2
// ============================================================
function openX2ImportModal() {
    document.getElementById('x2ImportModal').classList.add('active');
    document.getElementById('x2ImportFile').value = '';
    document.getElementById('x2ImportStatus').textContent = '';
}

function closeX2ImportModal() {
    document.getElementById('x2ImportModal').classList.remove('active');
}

function importX2Excel() {
    const input = document.getElementById('x2ImportFile');
    const status = document.getElementById('x2ImportStatus');
    if (!input.files.length) {
        status.textContent = '❌ Выберите файл';
        return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const wb = XLSX.read(new Uint8Array(e.target.result), { type: 'array' });
            const sheet = wb.Sheets[wb.SheetNames[0]];
            const rows = XLSX.utils.sheet_to_json(sheet);
            let imported = 0;
            rows.forEach(row => {
                const match = row['Матч'] || row['match'];
                const favorite = row['Фаворит'] || row['favorite'];
                const underdog = row['Аутсайдер'] || row['underdog'];
                if (!match || !favorite || !underdog) return;
                const odds = parseFloat(row['Кэф X2'] || row['odds'] || 0);
                const stake = parseFloat(row['Сумма'] || row['stake'] || 0);
                const result = (row['Результат'] || row['result'] || 'pending').toLowerCase();
                let profit = 0;
                if (result === 'win') profit = Math.round((stake * odds - stake) * 100) / 100;
                else if (result === 'loss') profit = -stake;
                x2Data.push({
                    id: Date.now() + Math.random() * 1000 + imported,
                    date: row['Дата'] || row['date'] || new Date().toISOString().slice(0,10),
                    time: row['Время'] || row['time'] || '',
                    match, favorite, underdog, odds, stake, profit,
                    score: row['Счёт'] || '-',
                    result, note: row['Примечание'] || 'Импорт',
                    source: 'import'
                });
                imported++;
            });
            if (imported > 0) {
                saveX2Data();
                status.textContent = `✅ Импортировано ${imported}`;
                status.style.color = 'var(--emerald-400)';
                renderX2Page();
                setTimeout(closeX2ImportModal, 1500);
            }
        } catch (err) {
            status.textContent = '❌ Ошибка: ' + err.message;
            status.style.color = 'var(--red-400)';
        }
    };
    reader.readAsArrayBuffer(input.files[0]);
}

function exportX2Excel() {
    const autoItems = (autoX2Data || []).map(c => ({
        date: (c.match_time || '').split(' ')[0],
        time: (c.match_time || '').split(' ')[1] || '',
        match: c.match, favorite: c.favorite, underdog: c.underdog,
        odds: c.current_odds || c.entry_odds || 0, stake: 20,
        score: (c.home_goals != null && c.away_goals != null) ? `${c.home_goals}:${c.away_goals}` : '-',
        result: c.result || 'pending',
        profit: c.profit || 0,
        note: `Auto | Prob: ${c.x2_prob}% | EV: ${c.x2_ev}%`,
    }));
    const manualItems = (x2Data || []).map(m => ({
        date: m.date, time: m.time || '',
        match: m.match, favorite: m.favorite, underdog: m.underdog,
        odds: m.odds || 0, stake: m.stake || 0,
        score: m.score || '-',
        result: m.result || 'pending',
        profit: m.profit || 0,
        note: m.note || 'Ручной',
    }));
    const all = [...autoItems, ...manualItems];

    if (!all.length) {
        showNotification('❌ Нет данных', 'error');
        return;
    }

    const data = all.map((m, i) => ({
        '#': i + 1,
        'Дата': m.date, 'Время': m.time || '',
        'Матч': m.match, 'Фаворит': m.favorite, 'Аутсайдер': m.underdog,
        'Кэф X2': m.odds, 'Сумма': m.stake, 'Счёт': m.score,
        'Результат': (m.result || 'pending').toUpperCase(),
        'Прибыль': m.result === 'win' ? m.profit : m.result === 'loss' ? -m.stake : 0,
        'Примечание': m.note || ''
    }));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(data), 'X2');
    XLSX.writeFile(wb, `x2_${new Date().toISOString().slice(0,10)}.xlsx`);
    showNotification('✅ Экспортировано', 'success');
}

// ============================================================
