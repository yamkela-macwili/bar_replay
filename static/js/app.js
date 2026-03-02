/* ═══════════════════════════════════════════════════════════
   PyReplay Trader — Frontend Application
   ═══════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────
let isPlaying = false;
let playInterval = null;
let intervalMs = 1000;
let currentData = null;
let isLoadingMore = false;
let currentSessionId = null;

// ── Color Palette ─────────────────────────────────────────
const COLORS = {
    bg: '#131722',
    grid: '#1e222d',
    text: '#787b86',
    textBright: '#d1d4dc',
    green: '#26a69a',
    red: '#ef5350',
    blue: '#2962ff',
    orange: '#ff9800',
    purple: '#ab47bc',
    yellow: '#ffeb3b',
    bbFill: 'rgba(41, 98, 255, 0.06)',
};

// ── Chart Layout ──────────────────────────────────────────
const baseLayout = {
    paper_bgcolor: COLORS.bg,
    plot_bgcolor: COLORS.bg,
    font: { family: 'Inter, sans-serif', size: 11, color: COLORS.text },
    margin: { l: 50, r: 60, t: 10, b: 30 },
    xaxis: {
        type: 'category',
        gridcolor: COLORS.grid,
        showgrid: true,
        zeroline: false,
        tickfont: { size: 10 },
        rangeslider: { visible: false },
        nticks: 10,
    },
    yaxis: {
        gridcolor: COLORS.grid,
        showgrid: true,
        zeroline: false,
        side: 'right',
        tickfont: { size: 10 },
        tickformat: '.5f',
    },
    showlegend: true,
    legend: {
        x: 0, y: 1,
        bgcolor: 'rgba(30,34,45,0.8)',
        bordercolor: '#2a2e39',
        borderwidth: 1,
        font: { size: 10, color: COLORS.textBright },
        orientation: 'h',
    },
    dragmode: 'pan',
    hovermode: 'x unified',
    hoverlabel: {
        bgcolor: '#2a2e39',
        bordercolor: '#363a45',
        font: { family: 'Inter, sans-serif', size: 11, color: '#d1d4dc' },
    },
};

const plotConfig = {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['select2d', 'lasso2d', 'toImage'],
    displaylogo: false,
    scrollZoom: true,
};

// ── Initialization ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await bootstrapSession();
    initChart();
    setupControls();
    setupKeyboard();
    fetchData();  // Load initial data
});

async function bootstrapSession() {
    try {
        const res = await fetch('/api/session');
        const data = await res.json();
        if (data.status === 'ok') {
            currentSessionId = data.session_id;
            console.log('🆔 Session initialized:', currentSessionId);
        }
    } catch (err) {
        console.error('Failed to bootstrap session:', err);
    }
}

function initChart() {
    const chart = document.getElementById('chart');
    Plotly.newPlot(chart, [], { ...baseLayout }, plotConfig);

    // Lazy loading scroll detection
    chart.on('plotly_relayout', (eventData) => {
        if (eventData['xaxis.range[0]'] !== undefined) {
            const startIdx = eventData['xaxis.range[0]'];
            // If scrolled near the beginning (left side) of data
            if (startIdx < 5 && !isLoadingMore) {
                loadMoreData('backward');
            }
        }
    });
}

// ── Data Fetching ─────────────────────────────────────────
async function fetchData(isInitialLoad = false, visibleCount = 200, startIndex = null) {
    try {
        const url = `/api/data?session_id=${currentSessionId}`;
        const res = await fetch(url);
        const data = await res.json();
        if (data.status === 'ok') {
            currentData = data;
            if (data.session_id) currentSessionId = data.session_id;

            // If it's the first load of a symbol/timeframe, set the initial range
            const layoutUpdate = {};
            if (isInitialLoad && startIndex !== null) {
                layoutUpdate['xaxis.range'] = [startIndex, startIndex + visibleCount];
            }

            updateChart(data, layoutUpdate);
            updateStats(data.account);
            updateProgress(data.progress);
            updatePositions(data.open_positions);
            updateHistory(data.trade_history);
        }
    } catch (err) {
        console.error('Failed to fetch data:', err);
    }
}

async function loadMoreData(direction = 'backward') {
    isLoadingMore = true;
    console.log(`📡 Fetching more historical data (${direction})...`);

    try {
        const res = await fetch(`/api/data/load_more?direction=${direction}&session_id=${currentSessionId}`);
        const result = await res.json();

        if (result.status === 'discarded') {
            console.warn('⚠️ Lazy load discarded due to session mismatch');
            return;
        }

        if (result.status === 'ok' && result.added > 0) {
            console.log(`✅ Loaded ${result.added} more bars`);

            // Store previous range to maintain scroll position
            const chart = document.getElementById('chart');
            const oldRange = chart.layout.xaxis.range;
            const newRange = [oldRange[0] + result.added, oldRange[1] + result.added];

            // Refresh data and chart, preserving the offset
            await fetchData(false);

            // Adjust range to keep focus on same bars
            Plotly.relayout('chart', { 'xaxis.range': newRange });
        } else if (result.added === 0 && result.total_bars >= 3000) {
            console.info('ℹ️ Memory ceiling reached (3000 bars). Backward scrolling locked.');
        } else {
            console.log('ℹ️ No more data available from provider');
        }
    } catch (err) {
        console.error('Lazy load failed:', err);
    } finally {
        // Prevent immediate re-triggering
        setTimeout(() => { isLoadingMore = false; }, 1000);
    }
}

async function sendAction(endpoint, body = {}) {
    // Ensure session_id is always present in the body
    const finalBody = { ...body, session_id: currentSessionId };
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(finalBody),
        });
        return await res.json();
    } catch (err) {
        console.error(`Action failed: ${endpoint}`, err);
        return null;
    }
}


// ── Chart Rendering ───────────────────────────────────────
function updateChart(data, layoutUpdate = null) {
    const bars = data.bars;
    const indicators = data.indicators || {};
    const positions = data.open_positions || [];
    const history = data.trade_history || [];

    // Format x-axis labels
    const labels = bars.datetime.map(dt => {
        const d = new Date(dt);
        const h = d.getHours().toString().padStart(2, '0');
        const m = d.getMinutes().toString().padStart(2, '0');
        const day = d.getDate().toString().padStart(2, '0');
        const mon = (d.getMonth() + 1).toString().padStart(2, '0');
        return `${mon}/${day} ${h}:${m}`;
    });

    // Candlestick trace
    const candlestick = {
        x: labels,
        open: bars.open,
        high: bars.high,
        low: bars.low,
        close: bars.close,
        type: 'candlestick',
        name: 'Price',
        increasing: { line: { color: COLORS.green, width: 1 }, fillcolor: COLORS.green },
        decreasing: { line: { color: COLORS.red, width: 1 }, fillcolor: COLORS.red },
        showlegend: false,
        hoverinfo: 'none',
    };

    const traces = [candlestick];
    let rsiData = null;
    let macdData = {};
    let hasRSI = false;
    let hasMACD = false;

    // Indicator overlays
    for (const [name, values] of Object.entries(indicators)) {
        if (name.startsWith('RSI')) {
            hasRSI = true;
            rsiData = { labels, values, name };
            continue;
        }
        if (name.startsWith('MACD')) {
            hasMACD = true;
            macdData[name] = { labels, values };
            continue;
        }

        let color = COLORS.orange;
        let dash = 'solid';
        let width = 1.5;

        if (name.startsWith('SMA')) { color = COLORS.orange; }
        else if (name.startsWith('EMA')) { color = COLORS.purple; }
        else if (name === 'BB_Upper') { color = COLORS.blue; dash = 'dash'; width = 1; }
        else if (name === 'BB_Middle') { color = COLORS.blue; width = 1; }
        else if (name === 'BB_Lower') { color = COLORS.blue; dash = 'dash'; width = 1; }

        traces.push({
            x: labels,
            y: values,
            type: 'scatter',
            mode: 'lines',
            name: name,
            line: { color, width, dash },
            hoverinfo: 'y',
        });

        // Bollinger band fill
        if (name === 'BB_Lower' && indicators['BB_Upper']) {
            traces.push({
                x: labels,
                y: indicators['BB_Upper'],
                type: 'scatter',
                mode: 'lines',
                line: { width: 0 },
                showlegend: false,
                hoverinfo: 'skip',
            });
            traces.push({
                x: labels,
                y: values,
                type: 'scatter',
                mode: 'lines',
                fill: 'tonexty',
                fillcolor: COLORS.bbFill,
                line: { width: 0 },
                showlegend: false,
                hoverinfo: 'skip',
            });
        }
    }

    // Trade markers on chart
    const tradeMarkers = getTradeMarkers(positions, history, bars, labels);
    traces.push(...tradeMarkers);

    // SL/TP lines for open positions
    const slTpLines = getSLTPLines(positions);

    const layout = {
        ...baseLayout,
        shapes: slTpLines,
        ...layoutUpdate
    };

    Plotly.react('chart', traces, layout, plotConfig);
    renderSubCharts(hasRSI, rsiData, hasMACD, macdData);
}

function getTradeMarkers(openPos, closedPos, bars, labels) {
    const traces = [];
    const allPositions = [...openPos, ...closedPos];

    const buyMarkers = { x: [], y: [], text: [], marker: { symbol: 'triangle-up', color: COLORS.green } };
    const sellMarkers = { x: [], y: [], text: [], marker: { symbol: 'triangle-down', color: COLORS.red } };

    for (const pos of allPositions) {
        const entryIdx = findNearestIndex(bars.datetime, pos.entry_time);
        if (entryIdx >= 0) {
            const target = pos.direction === 'buy' ? buyMarkers : sellMarkers;
            target.x.push(labels[entryIdx]);
            target.y.push(pos.entry_price);
            target.text.push(`${pos.direction.toUpperCase()} @ ${pos.entry_price}`);
        }

        if (pos.status === 'closed') {
            const exitIdx = findNearestIndex(bars.datetime, pos.exit_time);
            if (exitIdx >= 0) {
                const exitTarget = pos.pnl >= 0 ? buyMarkers : sellMarkers;
                exitTarget.x.push(labels[exitIdx]);
                exitTarget.y.push(pos.exit_price);
                exitTarget.text.push(`CLOSE @ ${pos.exit_price} (${pos.pnl >= 0 ? '+' : ''}${pos.pnl})`);
            }
        }
    }

    [buyMarkers, sellMarkers].forEach(m => {
        if (m.x.length > 0) {
            traces.push({
                x: m.x, y: m.y, text: m.text,
                type: 'scatter', mode: 'markers',
                marker: { ...m.marker, size: 12, line: { width: 1, color: '#fff' } },
                showlegend: false, hoverinfo: 'text'
            });
        }
    });

    return traces;
}

function findNearestIndex(datetimes, target) {
    if (!target) return -1;
    const targetStr = target.toString().substring(0, 19);
    for (let i = 0; i < datetimes.length; i++) {
        if (datetimes[i].substring(0, 19) === targetStr) return i;
    }
    // Fallback search
    for (let i = datetimes.length - 1; i >= 0; i--) {
        if (datetimes[i] <= targetStr) return i;
    }
    return -1;
}

function getSLTPLines(positions) {
    const shapes = [];
    for (const pos of positions) {
        if (pos.sl) {
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: pos.sl, y1: pos.sl,
                line: { color: COLORS.red, width: 1, dash: 'dot' }
            });
        }
        if (pos.tp) {
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: pos.tp, y1: pos.tp,
                line: { color: COLORS.green, width: 1, dash: 'dot' }
            });
        }
    }
    return shapes;
}

function renderSubCharts(hasRSI, rsiData, hasMACD, macdData) {
    const rsiCont = document.getElementById('rsiContainer');
    if (hasRSI && rsiData) {
        rsiCont.style.display = 'block';
        const trace = { x: rsiData.labels, y: rsiData.values, type: 'scatter', mode: 'lines', line: { color: COLORS.yellow, width: 1.5 } };
        const layout = {
            paper_bgcolor: COLORS.bg, plot_bgcolor: COLORS.bg, margin: { l: 50, r: 60, t: 5, b: 20 },
            xaxis: { showticklabels: false, gridcolor: COLORS.grid },
            yaxis: { gridcolor: COLORS.grid, side: 'right', range: [0, 100], tickvals: [30, 50, 70] },
            shapes: [
                { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 70, y1: 70, line: { color: COLORS.red, width: 0.5, dash: 'dot' } },
                { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 30, y1: 30, line: { color: COLORS.green, width: 0.5, dash: 'dot' } }
            ]
        };
        Plotly.react('rsiChart', [trace], layout, { ...plotConfig, displayModeBar: false });
    } else { rsiCont.style.display = 'none'; }

    const macdCont = document.getElementById('macdContainer');
    if (hasMACD) {
        macdCont.style.display = 'block';
        const mTraces = [];
        if (macdData['MACD']) mTraces.push({ x: rsiData.labels, y: macdData['MACD'].values, name: 'MACD', line: { color: COLORS.blue } });
        if (macdData['MACD_Signal']) mTraces.push({ x: rsiData.labels, y: macdData['MACD_Signal'].values, name: 'Signal', line: { color: COLORS.orange } });
        if (macdData['MACD_Hist']) mTraces.push({ x: rsiData.labels, y: macdData['MACD_Hist'].values, type: 'bar', marker: { color: macdData['MACD_Hist'].values.map(v => v >= 0 ? COLORS.green : COLORS.red) } });
        const mLayout = { paper_bgcolor: COLORS.bg, plot_bgcolor: COLORS.bg, margin: { l: 50, r: 60, t: 5, b: 20 }, xaxis: { showticklabels: false }, yaxis: { side: 'right' }, barmode: 'relative' };
        Plotly.react('macdChart', mTraces, mLayout, { ...plotConfig, displayModeBar: false });
    } else { macdCont.style.display = 'none'; }
}

// ── Stats, Progress, Positions UI ──────────────────────────
function updateStats(account) {
    if (!account) return;
    const f = (v) => `$${v.toFixed(2)}`;
    document.getElementById('statBalance').textContent = f(account.balance);
    document.getElementById('statEquity').textContent = f(account.equity);
    const float = document.getElementById('statFloating');
    float.textContent = f(account.floating_pnl);
    float.className = `stat-value ${account.floating_pnl >= 0 ? 'positive' : 'negative'}`;
    const closed = document.getElementById('statClosed');
    closed.textContent = f(account.closed_pnl);
    closed.className = `stat-value ${account.closed_pnl >= 0 ? 'positive' : 'negative'}`;
    document.getElementById('statDrawdown').textContent = `${account.max_drawdown}%`;
    document.getElementById('statWinRate').textContent = `${account.win_rate}%`;
    document.getElementById('statTrades').textContent = account.total_trades;
}

function updateProgress(progress) {
    if (!progress) return;
    const slider = document.getElementById('progressSlider');
    slider.max = progress.total_bars - 1;
    slider.value = progress.current_index;
    document.getElementById('progressLabel').textContent = `${progress.current_index + 1} / ${progress.total_bars}`;
    document.getElementById('currentDatetime').textContent = progress.current_datetime || '--';
}

function updatePositions(positions) {
    const cont = document.getElementById('openPositions');
    if (!positions || positions.length === 0) { cont.innerHTML = '<span class="empty-msg">No open positions</span>'; return; }
    cont.innerHTML = positions.map(p => `
        <div class="position-row">
            <span class="dir ${p.direction}">${p.direction}</span>
            <span>${p.lot_size}L @ ${p.entry_price}</span>
            <span class="pnl ${p.pnl >= 0 ? 'positive' : 'negative'}">${p.pnl.toFixed(2)}</span>
            <button class="close-pos-btn" onclick="closePosition('${p.id}')">✕</button>
        </div>
    `).join('');
}

function updateHistory(history) {
    const cont = document.getElementById('tradeHistory');
    if (!history || history.length === 0) { cont.innerHTML = '<span class="empty-msg">No trades yet</span>'; return; }
    cont.innerHTML = history.slice(-50).reverse().map(h => `
        <div class="history-row">
            <span class="dir ${h.direction}">${h.direction.toUpperCase()}</span>
            <span>${h.entry_price} → ${h.exit_price}</span>
            <span class="pnl ${h.pnl >= 0 ? 'positive' : 'negative'}">${h.pnl.toFixed(2)}</span>
        </div>
    `).join('');
}

// ── Controls Setup ────────────────────────────────────────
function setupControls() {
    document.getElementById('loadBtn').addEventListener('click', async () => {
        const provider = document.getElementById('providerSelect').value;
        const symbol = document.getElementById('symbolSelect').value;
        const timeframe = document.getElementById('timeframeSelect').value;

        stopPlaying();

        // Visual feedback: Clear chart for a moment or show loading
        Plotly.purge('chart');
        initChart();

        const res = await sendAction('/api/load', { symbol, timeframe, provider });
        if (res && res.status === 'ok') {
            currentSessionId = res.session_id;
            await fetchData(true, res.visible_count, res.start_index);
        } else {
            alert(`Error: ${res?.message || 'Load failed'}`);
        }
    });

    document.getElementById('playPauseBtn').addEventListener('click', togglePlay);
    document.getElementById('stepFwdBtn').addEventListener('click', stepForward);
    document.getElementById('stepBackBtn').addEventListener('click', stepBack);

    document.getElementById('jumpBackBtn').addEventListener('click', async () => {
        stopPlaying();
        await sendAction('/api/jump', { index: 0 });
        await fetchData();
    });

    document.getElementById('jumpFwdBtn').addEventListener('click', async () => {
        stopPlaying();
        await sendAction('/api/jump', { index: 999999 }); // Server handles end
        await fetchData();
    });

    document.querySelectorAll('.btn-speed').forEach(btn => {
        btn.addEventListener('click', async () => {
            const speed = parseInt(btn.dataset.speed);
            document.querySelectorAll('.btn-speed').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const res = await sendAction('/api/speed', { speed });
            if (res) intervalMs = res.interval_ms;
        });
    });

    document.getElementById('progressSlider').addEventListener('input', async (e) => {
        stopPlaying();
        await sendAction('/api/jump', { index: parseInt(e.target.value) });
        await fetchData();
    });

    document.getElementById('buyBtn').addEventListener('click', () => executeTrade('buy'));
    document.getElementById('sellBtn').addEventListener('click', () => executeTrade('sell'));
    document.getElementById('closeAllBtn').addEventListener('click', async () => {
        await sendAction('/api/trade', { action: 'close_all' });
        await fetchData();
    });

    document.getElementById('indicatorBtn').addEventListener('click', () => document.getElementById('indicatorModal').classList.remove('hidden'));
    document.getElementById('closeModal').addEventListener('click', () => document.getElementById('indicatorModal').classList.add('hidden'));
    document.getElementById('applyIndicators').addEventListener('click', applyIndicators);
}

// ── Helpers & Core Logic ───────────────────────────────────
function setupKeyboard() {
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT') return;
        if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
        if (e.code === 'ArrowRight') stepForward();
        if (e.code === 'ArrowLeft') stepBack();
        if (e.code === 'KeyB') executeTrade('buy');
        if (e.code === 'KeyS') executeTrade('sell');
    });
}

function togglePlay() {
    if (isPlaying) { stopPlaying(); sendAction('/api/pause'); }
    else { startPlaying(); sendAction('/api/play'); }
}

function startPlaying() {
    isPlaying = true; updatePlayButton();
    playInterval = setInterval(async () => {
        const res = await sendAction('/api/step');
        if (res && res.status === 'ok') await fetchData();
        else stopPlaying();
    }, intervalMs);
}

function stopPlaying() {
    isPlaying = false;
    if (playInterval) { clearInterval(playInterval); playInterval = null; }
    updatePlayButton();
}

function updatePlayButton() {
    const b = document.getElementById('playPauseBtn');
    b.textContent = isPlaying ? '⏸' : '▶';
}

async function stepForward() { await sendAction('/api/step'); await fetchData(); }
async function stepBack() { await sendAction('/api/back'); await fetchData(); }

async function executeTrade(action) {
    const lot = parseFloat(document.getElementById('lotSize').value);
    const sl = parseFloat(document.getElementById('slInput').value);
    const tp = parseFloat(document.getElementById('tpInput').value);
    await sendAction('/api/trade', { action, lot_size: lot, sl: sl || null, tp: tp || null });
    await fetchData();
}

window.closePosition = async (id) => {
    await sendAction('/api/trade', { action: 'close', position_id: id });
    await fetchData();
};

async function applyIndicators() {
    await sendAction('/api/indicators', { action: 'clear' });
    const getVal = (id) => document.getElementById(id).value;
    const isChecked = (id) => document.getElementById(id).checked;

    if (isChecked('indSMA')) await sendAction('/api/indicators', { action: 'set', name: 'sma', settings: { period: parseInt(getVal('smaPeriod')) } });
    if (isChecked('indEMA')) await sendAction('/api/indicators', { action: 'set', name: 'ema', settings: { period: parseInt(getVal('emaPeriod')) } });
    if (isChecked('indRSI')) await sendAction('/api/indicators', { action: 'set', name: 'rsi', settings: { period: parseInt(getVal('rsiPeriod')) } });
    if (isChecked('indMACD')) await sendAction('/api/indicators', { action: 'set', name: 'macd', settings: { fast: parseInt(getVal('macdFast')), slow: parseInt(getVal('macdSlow')), signal: parseInt(getVal('macdSignal')) } });
    if (isChecked('indBB')) await sendAction('/api/indicators', { action: 'set', name: 'bollinger', settings: { period: parseInt(getVal('bbPeriod')), std_dev: parseFloat(getVal('bbStd')) } });

    document.getElementById('indicatorModal').classList.add('hidden');
    await fetchData();
}

window.addEventListener('resize', () => Plotly.Plots.resize('chart'));
