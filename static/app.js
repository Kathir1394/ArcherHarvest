/* ═══════════════════════════════════════════════════
   NSE Market Data Downloader — Frontend Logic
   SSE real-time updates, controls, stock grid, logs
   ═══════════════════════════════════════════════════ */

const API = '';  // same origin

// ── State ──
let sseSource = null;
let isAuthenticated = false;
let engineStatus = 'idle'; // idle | running | paused
let stockStates = {};
let pollInterval = null;

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    setDefaultDates();
    checkAuth();
    connectSSE();
    startPolling();
    checkUrlParams();
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
            document.getElementById('stat-total-val').textContent = data.instruments_loaded.toLocaleString();
        }
    } catch (e) {
        console.error('Auth check failed:', e);
    }
}

function updateAuthUI(data) {
    const badge = document.getElementById('auth-indicator');
    const label = document.getElementById('auth-label');
    const btn = document.getElementById('btn-auth');

    if (data.authenticated) {
        badge.className = 'auth-badge auth-badge--connected';
        label.textContent = `${data.user_id} ✓`;
        btn.textContent = 'Disconnect';
        btn.className = 'btn btn--outline';
    } else {
        badge.className = 'auth-badge auth-badge--disconnected';
        label.textContent = 'Not Connected';
        btn.textContent = 'Connect Kite';
        btn.className = 'btn btn--primary';
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
            updateControlButtons();
            addLog('info', `Download started: ${data.total_stocks} stocks [${data.date_from} → ${data.date_to}]`);
            break;

        case 'stock_started':
            updateStockChip(data.symbol, 'in_progress');
            document.getElementById('current-stock').textContent = data.symbol;
            document.getElementById('stat-progress-val').textContent = data.index;
            addLog('progress', `Downloading ${data.symbol}... [${data.index}/${data.total}]`);
            break;

        case 'stock_completed':
            updateStockChip(data.symbol, 'completed');
            addLog('success', `✓ ${data.symbol} — ${(data.candles || 0).toLocaleString()} candles`);
            break;

        case 'stock_failed':
            updateStockChip(data.symbol, 'failed');
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
            updateControlButtons();
            updateProgressFromSummary(data);
            document.getElementById('current-stock').textContent = '—';
            addLog('info', `Download finished! ${data.completed}/${data.total} completed, ${data.failed} failed`);
            break;

        case 'status_change':
            engineStatus = data.status === 'paused' ? 'paused' : (data.status === 'stopped' ? 'idle' : data.status);
            updateControlButtons();
            addLog('info', `Engine status: ${data.status}`);
            break;

        case 'stock_error':
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
    const symbols = document.getElementById('symbols-filter').value.trim();
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
    await fetch(`${API}/api/download/stop`, { method: 'POST' });
    engineStatus = 'idle';
    updateControlButtons();
    document.getElementById('current-stock').textContent = '—';
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
    btnStop.disabled   = engineStatus === 'idle';
    btnRetry.disabled  = engineStatus !== 'idle';

    document.getElementById('engine-status').textContent = capitalize(engineStatus);
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

    const pct = summary.progress_pct || 0;
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
