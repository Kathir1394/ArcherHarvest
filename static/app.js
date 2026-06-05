/* ═══════════════════════════════════════════════════
   NSE Market Data Downloader — Frontend Logic
   SSE real-time updates, controls, stock grid, logs
   ═══════════════════════════════════════════════════ */

const API = '';  // same origin

// ── State ──
let sseSource = null;
let isAuthenticated = false;
let engineStatus = 'idle'; // idle | running | paused | stopping
let stockStates = {};
let activeDownloads = new Set();
let pollInterval = null;
let instrumentList = [];  // cached instrument list for autocomplete
let selectedSymbols = []; // tag chips
let dropdownActiveIndex = -1;

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    setDefaultDates();
    checkAuth();
    connectSSE();
    startPolling();
    checkUrlParams();
    initAutocomplete();
});

function setDefaultDates() {
    const today = new Date();
    const fiveYearsAgo = new Date(today);
    fiveYearsAgo.setFullYear(fiveYearsAgo.getFullYear() - 5);

    const formatISO = (d) => {
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        return `${d.getFullYear()}-${mm}-${dd}`;
    };
    const formatDisplay = (d) => {
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        return `${dd}-${mm}-${d.getFullYear()}`;
    };

    document.getElementById('date-from').value = formatISO(fiveYearsAgo);
    document.getElementById('date-to').value = formatISO(today);

    // Update display text for custom date picker triggers
    const wrappers = document.querySelectorAll('[data-datepicker]');
    if (wrappers.length >= 2) {
        const fromText = wrappers[0].querySelector('.date-display__text');
        const toText = wrappers[1].querySelector('.date-display__text');
        if (fromText) fromText.textContent = formatDisplay(fiveYearsAgo);
        if (toText) toText.textContent = formatDisplay(today);
    }
}

function checkUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const auth = params.get('auth');
    if (auth === 'success') {
        addLog('success', 'Successfully authenticated with Kite Connect');
        window.history.replaceState({}, '', '/');
        checkAuth();
    } else if (auth === 'failed') {
        const err = params.get('error') || 'Unknown error';
        addLog('error', `Authentication failed: ${err}`);
        window.history.replaceState({}, '', '/');
    }
}

// ── Auth ──
async function checkAuth() {
    try {
        const resp = await fetch(`${API}/api/auth/status`);
        const data = await resp.json();
        isAuthenticated = data.authenticated;
        updateAuthUI(data);
        if (data.instruments_loaded > 0) {
            loadInstrumentList();
        }
    } catch (e) {
        console.error('Auth check failed:', e);
    }
}

let sessionTimerInterval;

function getNextIST6AM() {
    // Current time
    const now = new Date();
    // Convert to IST
    const istOffset = 5.5 * 60 * 60 * 1000;
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const istNow = new Date(utc + istOffset);
    
    // Create target time (6:00 AM IST)
    const target = new Date(istNow);
    target.setHours(6, 0, 0, 0);
    
    // If it's already past 6 AM IST today, set target to tomorrow 6 AM IST
    if (istNow.getTime() >= target.getTime()) {
        target.setDate(target.getDate() + 1);
    }
    
    // Convert target back to local timezone time
    return new Date(target.getTime() - istOffset - (now.getTimezoneOffset() * 60000));
}

function updateSessionTimer() {
    const timerVal = document.getElementById('session-timer-val');
    if (!isAuthenticated) return;
    
    const now = new Date();
    const target = getNextIST6AM();
    const diffMs = target - now;
    
    if (diffMs <= 0) {
        timerVal.textContent = "Expired";
        timerVal.style.color = "var(--error)";
        return;
    }
    
    const h = Math.floor(diffMs / (1000 * 60 * 60));
    const m = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    const s = Math.floor((diffMs % (1000 * 60)) / 1000);
    
    timerVal.textContent = `${h}h ${m}m ${s}s`;
    timerVal.style.color = h < 1 ? "var(--warning)" : "var(--text)";
}

function updateAuthUI(data) {
    const badge = document.getElementById('auth-indicator');
    const label = document.getElementById('auth-label');
    const btn = document.getElementById('btn-auth');
    const timerDiv = document.getElementById('session-timer');

    if (sessionTimerInterval) clearInterval(sessionTimerInterval);

    if (data.authenticated) {
        badge.className = 'auth-badge auth-badge--connected';
        label.textContent = `${data.user_id} ✓`;
        btn.textContent = 'Disconnect';
        btn.className = 'btn btn--outline';
        
        timerDiv.style.display = 'flex';
        updateSessionTimer();
        sessionTimerInterval = setInterval(updateSessionTimer, 1000);
    } else {
        badge.className = 'auth-badge auth-badge--disconnected';
        label.textContent = 'Not Connected';
        btn.textContent = 'Connect Kite';
        btn.className = 'btn btn--primary';
        timerDiv.style.display = 'none';
    }
}

async function handleAuth() {
    if (isAuthenticated) {
        await fetch(`${API}/api/auth/logout`, { method: 'POST' });
        isAuthenticated = false;
        updateAuthUI({ authenticated: false });
        addLog('info', 'Disconnected from Kite');
        return;
    }

    try {
        const resp = await fetch(`${API}/api/auth/login-url`);
        const data = await resp.json();
        addLog('info', 'Opening Kite login page...');
        window.location.href = data.login_url;
    } catch (e) {
        addLog('error', `Failed to get login URL: ${e.message}`);
    }
}

// ── SSE Connection ──
function connectSSE() {
    if (sseSource) sseSource.close();

    sseSource = new EventSource(`${API}/api/events`);

    sseSource.addEventListener('message', (event) => {
        try {
            const data = JSON.parse(event.data);
            handleSSEEvent(data);
        } catch (e) {
            console.warn('SSE parse error:', e);
        }
    });

    sseSource.addEventListener('open', () => {
        addLog('info', 'Real-time event stream connected');
    });

    sseSource.addEventListener('error', () => {
        addLog('warning', 'Event stream disconnected — reconnecting...');
    });
}

function handleSSEEvent(data) {
    const type = data.type;

    switch (type) {
        case 'download_started':
            engineStatus = 'running';
            activeDownloads.clear();
            renderActiveBadges();
            updateControlButtons();
            addLog('info', `Download started: ${data.total_stocks} stocks [${data.date_from} → ${data.date_to}]`);
            break;

        case 'stock_started':
            updateStockChip(data.symbol, 'in_progress');
            activeDownloads.add(data.symbol);
            renderActiveBadges();
            document.getElementById('stat-progress-val').textContent = data.index;
            addLog('progress', `Downloading ${data.symbol}... [${data.index}/${data.total}]`);
            break;

        case 'stock_completed':
            updateStockChip(data.symbol, 'completed');
            activeDownloads.delete(data.symbol);
            renderActiveBadges();
            addLog('success', `✓ ${data.symbol} — ${(data.candles || 0).toLocaleString()} candles`);
            break;

        case 'stock_failed':
            updateStockChip(data.symbol, 'failed');
            activeDownloads.delete(data.symbol);
            renderActiveBadges();
            addLog('error', `✗ ${data.symbol} — ${data.error}`);
            break;

        case 'retry':
            addLog('warning', `↻ ${data.symbol} retry ${data.attempt}/${data.max_retries}: ${data.error}`);
            break;

        case 'progress_update':
            updateProgressFromSummary(data);
            break;

        case 'download_finished':
            engineStatus = 'idle';
            activeDownloads.clear();
            renderActiveBadges();
            updateControlButtons();
            updateProgressFromSummary(data);
            addLog('info', `Download finished! ${data.completed}/${data.total} completed, ${data.failed} failed`);
            break;

        case 'status_change':
            engineStatus = data.status === 'paused' ? 'paused' : (data.status === 'stopped' || data.status === 'idle' ? 'idle' : data.status);
            if (engineStatus === 'idle') activeDownloads.clear();
            renderActiveBadges();
            updateControlButtons();
            addLog('info', `Engine status: ${data.status}`);
            break;

        case 'stock_error':
            activeDownloads.delete(data.symbol);
            renderActiveBadges();
            addLog('error', `${data.symbol}: ${data.error}`);
            break;
    }
}

// ── Polling for status ──
function startPolling() {
    pollInterval = setInterval(fetchStatus, 5000);
}

async function fetchStatus() {
    try {
        const resp = await fetch(`${API}/api/download/status`);
        const data = await resp.json();

        engineStatus = data.engine;
        updateControlButtons();
        updateProgressFromSummary(data.summary);

        if (data.storage) {
            document.getElementById('stat-storage-val').textContent = data.storage.total_bytes_display || '0 B';
        }

        const statusEl = document.getElementById('engine-status');
        statusEl.textContent = capitalize(data.engine);
    } catch (e) {
        // Server might be down — silent
    }
}

// ── Download Controls ──
async function startDownload() {
    if (!isAuthenticated) {
        addLog('error', 'Please connect to Kite first');
        return;
    }

    const dateFrom = document.getElementById('date-from').value;
    const dateTo = document.getElementById('date-to').value;
    const symbols = selectedSymbols.join(',');
    const timeframe = document.getElementById('timeframe').value;
    const segmentCheckboxes = document.querySelectorAll('input[name="segment"]:checked');
    const segment = Array.from(segmentCheckboxes).map(cb => cb.value).join(',');
    const exchangeRadio = document.querySelector('input[name="exchange-filter"]:checked');
    const exchangeFilter = exchangeRadio ? exchangeRadio.value : 'NSE_BSE';
    const continuousData = document.getElementById('continuous-data').checked;

    if (!dateFrom || !dateTo) {
        addLog('error', 'Please select date range');
        return;
    }

    let url = `${API}/api/download/start?date_from=${dateFrom}&date_to=${dateTo}&timeframe=${timeframe}&segment=${segment}&exchange_filter=${exchangeFilter}&continuous_data=${continuousData}`;
    if (symbols) url += `&symbols=${encodeURIComponent(symbols)}`;

    try {
        const resp = await fetch(url, { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            engineStatus = 'running';
            updateControlButtons();
            addLog('info', `Download queued: ${dateFrom} → ${dateTo}`);
            const titleEl = document.getElementById('grid-status-title');
            if (titleEl) titleEl.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="panel-icon"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>${segment || 'Selected'} Status`;
            loadStockGrid();
        } else {
            addLog('error', data.error || 'Failed to start download');
        }
    } catch (e) {
        addLog('error', `Start failed: ${e.message}`);
    }
}

async function pauseDownload() {
    await fetch(`${API}/api/download/pause`, { method: 'POST' });
    engineStatus = 'paused';
    updateControlButtons();
}

async function resumeDownload() {
    await fetch(`${API}/api/download/resume`, { method: 'POST' });
    engineStatus = 'running';
    updateControlButtons();
}

async function stopDownload() {
    engineStatus = 'stopping';
    updateControlButtons();
    await fetch(`${API}/api/download/stop`, { method: 'POST' });
}

async function retryFailed() {
    try {
        const resp = await fetch(`${API}/api/download/retry-failed`, { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            engineStatus = 'running';
            updateControlButtons();
            addLog('info', 'Retrying failed stocks...');
        } else {
            addLog('error', data.error || 'Retry failed');
        }
    } catch (e) {
        addLog('error', `Retry error: ${e.message}`);
    }
}

// ── UI Updates ──
function updateControlButtons() {
    const btnStart  = document.getElementById('btn-start');
    const btnPause  = document.getElementById('btn-pause');
    const btnResume = document.getElementById('btn-resume');
    const btnStop   = document.getElementById('btn-stop');
    const btnRetry  = document.getElementById('btn-retry');

    btnStart.disabled  = engineStatus !== 'idle';
    btnPause.disabled  = engineStatus !== 'running';
    btnResume.disabled = engineStatus !== 'paused';
    btnStop.disabled   = engineStatus === 'idle' || engineStatus === 'stopping';
    btnRetry.disabled  = engineStatus !== 'idle';

    document.getElementById('engine-status').textContent = engineStatus === 'stopping' ? 'Stopping...' : capitalize(engineStatus);
}

function toggleContinuousCheckbox() {
    const checkedSegments = Array.from(document.querySelectorAll('input[name="segment"]:checked')).map(cb => cb.value);
    const cb = document.getElementById('continuous-data');
    const track = document.getElementById('continuous-track');
    
    if (checkedSegments.includes('Future') || checkedSegments.includes('Commodity')) {
        cb.checked = true;
        if (track) track.classList.add('active');
    } else {
        cb.checked = false;
        if (track) track.classList.remove('active');
    }
    
    // Also toggle grid clear visually
    const grid = document.getElementById('stock-grid');
    grid.innerHTML = '<div class="stock-grid-empty">Segment changed. Click Start Download to view stocks.</div>';
    recalculateTotalStocks();
}

function recalculateTotalStocks() {
    if (engineStatus !== 'idle') return; // Don't override while running
    if (!instrumentList || instrumentList.length === 0) return;

    const segmentCheckboxes = document.querySelectorAll('input[name="segment"]:checked');
    const allowedSegments = Array.from(segmentCheckboxes).map(cb => cb.value);
    const exchangeRadio = document.querySelector('input[name="exchange-filter"]:checked');
    const exchangeFilter = exchangeRadio ? exchangeRadio.value : 'NSE_BSE';

    let nseSymbols = new Set();
    if (exchangeFilter === 'NSE_BSE') {
        for (const i of instrumentList) {
            if (i.exchange === 'NSE') nseSymbols.add(i.rawSymbol);
        }
    }

    let total = 0;
    for (const i of instrumentList) {
        if (!allowedSegments.includes(i.uiSegment)) continue;
        if (exchangeFilter === 'NSE_ONLY' && i.exchange === 'BSE') continue;
        if (exchangeFilter === 'BSE_ONLY' && i.exchange === 'NSE') continue;
        if (exchangeFilter === 'NSE_BSE' && i.exchange === 'BSE' && nseSymbols.has(i.rawSymbol)) continue;
        total++;
    }

    document.getElementById('stat-total-val').textContent = total.toLocaleString();
    document.getElementById('stat-completed-val').textContent = "0";
    document.getElementById('stat-progress-val').textContent = "0";
    document.getElementById('stat-failed-val').textContent = "0";
}

function toggleContinuousManual() {
    const cb = document.getElementById('continuous-data');
    const track = document.getElementById('continuous-track');
    cb.checked = !cb.checked;
    if (cb.checked) {
        track.classList.add('active');
    } else {
        track.classList.remove('active');
    }
}

function updateProgressFromSummary(summary) {
    if (!summary || summary.total === 0) return;

    const pct = Math.min(summary.progress_pct || 0, 100);
    document.getElementById('progress-bar').style.width = `${pct}%`;
    document.getElementById('progress-text').textContent = `${pct}%`;

    document.getElementById('stat-total-val').textContent = (summary.total || 0).toLocaleString();
    document.getElementById('stat-completed-val').textContent = (summary.completed || 0).toLocaleString();
    document.getElementById('stat-progress-val').textContent = (summary.in_progress || 0).toLocaleString();
    document.getElementById('stat-failed-val').textContent = (summary.failed || 0).toLocaleString();
    document.getElementById('stat-candles-val').textContent = (summary.total_candles || 0).toLocaleString();

    document.getElementById('elapsed-time').textContent = formatDuration(summary.elapsed_sec || 0);
    document.getElementById('eta-time').textContent = summary.eta_sec > 0 ? formatDuration(summary.eta_sec) : '—';
}

// ── Stock Grid ──
async function loadStockGrid() {
    try {
        const resp = await fetch(`${API}/api/download/stocks`);
        const data = await resp.json();
        renderStockGrid(data.stocks || []);
    } catch (e) {
        console.warn('Failed to load stock grid:', e);
    }
}

function renderStockGrid(stocks) {
    const grid = document.getElementById('stock-grid');
    if (!stocks || stocks.length === 0) {
        grid.innerHTML = '<div class="stock-grid-empty">No stocks tracked yet. Start a download to populate.</div>';
        return;
    }

    stockStates = {};
    let html = '';
    for (const s of stocks) {
        stockStates[s.symbol] = s.status;
        html += buildStockChipHTML(s.symbol, s.status);
    }
    grid.innerHTML = html;
}

function buildStockChipHTML(symbol, status) {
    const label = status === 'in_progress' ? 'fetching' : status;
    return `<div class="stock-chip" id="chip-${symbol}" data-status="${status}" data-symbol="${symbol}">
        <span class="stock-chip__symbol">${symbol}</span>
        <span class="stock-chip__badge badge--${status}">${label}</span>
    </div>`;
}

function updateStockChip(symbol, status) {
    stockStates[symbol] = status;
    const chip = document.getElementById(`chip-${symbol}`);
    if (chip) {
        chip.dataset.status = status;
        const badge = chip.querySelector('.stock-chip__badge');
        badge.className = `stock-chip__badge badge--${status}`;
        badge.textContent = status === 'in_progress' ? 'fetching' : status;
    } else {
        // Chip not rendered yet — append
        const grid = document.getElementById('stock-grid');
        const empty = grid.querySelector('.stock-grid-empty');
        if (empty) empty.remove();
        grid.insertAdjacentHTML('beforeend', buildStockChipHTML(symbol, status));
    }
}

function filterStocks() {
    const query = document.getElementById('stock-search').value.toUpperCase().trim();
    const chips = document.querySelectorAll('.stock-chip');
    chips.forEach(chip => {
        const sym = chip.dataset.symbol || '';
        chip.style.display = sym.includes(query) ? '' : 'none';
    });
}

// ── Activity Log ──
const MAX_LOG_ENTRIES = 300;

function addLog(level, message) {
    const container = document.getElementById('log-container');
    const now = new Date();
    const time = now.toLocaleTimeString('en-IN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

    const entry = document.createElement('div');
    entry.className = `log-entry log-entry--${level}`;
    entry.innerHTML = `<span class="log-time">${time}</span><span class="log-msg">${escapeHTML(message)}</span>`;

    container.appendChild(entry);

    // Duplicate to error container if needed
    if (level === 'error' || level === 'warning') {
        const errContainer = document.getElementById('error-container');
        if (errContainer) {
            const errEntry = entry.cloneNode(true);
            errContainer.appendChild(errEntry);
            while (errContainer.children.length > MAX_LOG_ENTRIES) {
                errContainer.removeChild(errContainer.firstChild);
            }
            errContainer.scrollTop = errContainer.scrollHeight;
        }
    }

    // Trim old entries
    while (container.children.length > MAX_LOG_ENTRIES) {
        container.removeChild(container.firstChild);
    }

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function clearLog() {
    const container = document.getElementById('log-container');
    container.innerHTML = '';
    const errContainer = document.getElementById('error-container');
    if (errContainer) errContainer.innerHTML = '';
    addLog('info', 'Log cleared');
}

// ── Helpers ──
function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '00:00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Instrument List for Autocomplete ──
async function loadInstrumentList() {
    try {
        const resp = await fetch(`${API}/api/instruments`);
        const data = await resp.json();
        instrumentList = (data.instruments || []).map(i => ({
            symbol: i.symbol,
            rawSymbol: i.raw_symbol,
            exchange: i.exchange,
            name: i.name || '',
            segment: i.segment || '',
            uiSegment: i.ui_segment || '',
        }));
        recalculateTotalStocks();
    } catch (e) {
        console.warn('Failed to load instruments:', e);
    }
}

// ── Dynamic Badges ──
function renderActiveBadges() {
    const container = document.getElementById('active-badges');
    if (!container) return;
    if (activeDownloads.size === 0) {
        container.innerHTML = '<span class="meta-value mono">—</span>';
        return;
    }
    const html = Array.from(activeDownloads).map(sym => 
        `<span class="active-badge">${sym}</span>`
    ).join('');
    container.innerHTML = html;
}

// ── Log Tabs ──
function switchLogTab(tabId) {
    document.getElementById('tab-all').classList.toggle('active', tabId === 'all');
    document.getElementById('tab-errors').classList.toggle('active', tabId === 'errors');
    
    document.getElementById('log-container').style.display = tabId === 'all' ? 'flex' : 'none';
    document.getElementById('error-container').style.display = tabId === 'errors' ? 'flex' : 'none';
    
    const showErrActions = tabId === 'errors' ? 'flex' : 'none';
    document.getElementById('btn-copy-errors').style.display = showErrActions;
    document.getElementById('btn-dl-errors').style.display = showErrActions;
}

function copyErrors() {
    const errContainer = document.getElementById('error-container');
    if (!errContainer) return;
    const text = Array.from(errContainer.querySelectorAll('.log-entry')).map(el => {
        return el.querySelector('.log-time').textContent + ' ' + el.querySelector('.log-msg').textContent;
    }).join('\n');
    navigator.clipboard.writeText(text).then(() => {
        addLog('info', 'Errors copied to clipboard');
    });
}

function downloadErrors() {
    const errContainer = document.getElementById('error-container');
    if (!errContainer) return;
    const text = Array.from(errContainer.querySelectorAll('.log-entry')).map(el => {
        return el.querySelector('.log-time').textContent + ' ' + el.querySelector('.log-msg').textContent;
    }).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `archer_errors_${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

// ── Autocomplete ──
function initAutocomplete() {
    const input = document.getElementById('symbols-filter');
    const dropdown = document.getElementById('symbol-dropdown');
    const container = document.getElementById('symbol-autocomplete');

    input.addEventListener('input', () => {
        const query = input.value.trim().toUpperCase();
        dropdownActiveIndex = -1;
        if (query.length < 1) {
            dropdown.classList.remove('active');
            return;
        }
        const matches = instrumentList.filter(i =>
            !selectedSymbols.includes(i.rawSymbol) &&
            (i.rawSymbol.toUpperCase().includes(query) ||
             i.name.toUpperCase().includes(query))
        ).sort((a, b) => {
            const aSym = a.rawSymbol.toUpperCase();
            const bSym = b.rawSymbol.toUpperCase();
            
            // 1. Exact symbol match
            if (aSym === query && bSym !== query) return -1;
            if (bSym === query && aSym !== query) return 1;
            
            // 2. Starts with symbol
            const aStarts = aSym.startsWith(query);
            const bStarts = bSym.startsWith(query);
            if (aStarts && !bStarts) return -1;
            if (bStarts && !aStarts) return 1;
            
            // 3. Demote ETF/MF
            const aIsMF = a.uiSegment === 'ETF/MF';
            const bIsMF = b.uiSegment === 'ETF/MF';
            if (!aIsMF && bIsMF) return -1;
            if (aIsMF && !bIsMF) return 1;
            
            return aSym.localeCompare(bSym);
        }).slice(0, 15);

        if (matches.length === 0) {
            dropdown.classList.remove('active');
            return;
        }

        dropdown.innerHTML = matches.map((m, idx) => `
            <div class="symbol-dropdown-item" data-symbol="${m.rawSymbol}" data-full="${m.symbol}" data-idx="${idx}">
                <span>
                    <span class="symbol-dropdown-item__symbol">${m.rawSymbol}</span>
                    <span class="symbol-dropdown-item__exchange">${m.exchange}</span>
                </span>
                <span class="symbol-dropdown-item__name">${escapeHTML(m.name)}</span>
            </div>
        `).join('');
        dropdown.classList.add('active');

        dropdown.querySelectorAll('.symbol-dropdown-item').forEach(item => {
            item.addEventListener('click', () => {
                addSymbolTag(item.dataset.symbol);
                input.value = '';
                dropdown.classList.remove('active');
                input.focus();
            });
        });
    });

    input.addEventListener('keydown', (e) => {
        const items = dropdown.querySelectorAll('.symbol-dropdown-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            dropdownActiveIndex = Math.min(dropdownActiveIndex + 1, items.length - 1);
            updateDropdownHighlight(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            dropdownActiveIndex = Math.max(dropdownActiveIndex - 1, 0);
            updateDropdownHighlight(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (dropdownActiveIndex >= 0 && items[dropdownActiveIndex]) {
                addSymbolTag(items[dropdownActiveIndex].dataset.symbol);
                input.value = '';
                dropdown.classList.remove('active');
            }
        } else if (e.key === 'Backspace' && input.value === '' && selectedSymbols.length > 0) {
            removeSymbolTag(selectedSymbols[selectedSymbols.length - 1]);
        }
    });

    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) {
            dropdown.classList.remove('active');
        }
    });

    container.addEventListener('click', () => {
        input.focus();
    });
}

function updateDropdownHighlight(items) {
    items.forEach((item, idx) => {
        item.classList.toggle('active', idx === dropdownActiveIndex);
    });
    if (items[dropdownActiveIndex]) {
        items[dropdownActiveIndex].scrollIntoView({ block: 'nearest' });
    }
}

function addSymbolTag(rawSymbol) {
    if (selectedSymbols.includes(rawSymbol)) return;
    selectedSymbols.push(rawSymbol);
    renderTags();
}

function removeSymbolTag(rawSymbol) {
    selectedSymbols = selectedSymbols.filter(s => s !== rawSymbol);
    renderTags();
}

function renderTags() {
    const container = document.getElementById('symbol-tags');
    container.innerHTML = selectedSymbols.map(sym => `
        <span class="symbol-tag">
            ${sym}
            <button class="symbol-tag__remove" onclick="removeSymbolTag('${sym}')" title="Remove">&times;</button>
        </span>
    `).join('');
    document.getElementById('symbols-hidden').value = selectedSymbols.join(',');
}
