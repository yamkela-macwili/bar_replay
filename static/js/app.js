/* ═══════════════════════════════════════════════════════════
   PyReplay Trader — Frontend Application
   ═══════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────
let isPlaying = false;
let playInterval = null;
let intervalMs = 1000;
let currentData = null;

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

const INDICATOR_COLORS = {
    'SMA': '#ff9800',
    'EMA': '#ab47bc',
    'BB_Upper': '#2962ff',
    'BB_Middle': '#2962ff',
    'BB_Lower': '#2962ff',
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
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    setupControls();
    setupKeyboard();
    fetchData();  // Load initial data
});

function initChart() {
    Plotly.newPlot('chart', [], { ...baseLayout }, plotConfig);
}

// ── Data Fetching ─────────────────────────────────────────
async function fetchData() {
    try {
        const res = await fetch('/api/data');
        const data = await res.json();
        if (data.status === 'ok') {
            currentData = data;
            updateChart(data);
            updateStats(data.account);
            updateProgress(data.progress);
            updatePositions(data.open_positions);
            updateHistory(data.trade_history);
        }
    } catch (err) {
        console.error('Failed to fetch data:', err);
    }
}

async function sendAction(endpoint, body = {}) {
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return await res.json();
    } catch (err) {
        console.error(`Action failed: ${endpoint}`, err);
        return null;
    }
}

// ── Chart Rendering ───────────────────────────────────────
function updateChart(data) {
    const bars = data.bars;
    const indicators = data.indicators || {};
    const positions = data.open_positions || [];
    const history = data.trade_history || [];

    // Format x-axis labels (show time only for intraday)
    const labels = bars.datetime.map(dt => {
        const d = new Date(dt);
        const h = d.getHours().toString().padStart(2, '0');
        const m = d.getMinutes().toString().padStart(2, '0');
        const mon = (d.getMonth() + 1).toString().padStart(2, '0');
        const day = d.getDate().toString().padStart(2, '0');
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
    let hasRSI = false;
    let hasMACd = false;
    let rsiData = null;
    let macdData = {};

    // Indicator overlays
    for (const [name, values] of Object.entries(indicators)) {
        if (name.startsWith('RSI')) {
            hasRSI = true;
            rsiData = { labels, values, name };
            continue;
        }
        if (name.startsWith('MACD')) {
            hasMACd = true;
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
    const slTpLines = getSLTPShapes(positions);

    const layout = {
        ...baseLayout,
        shapes: slTpLines,
    };

    Plotly.react('chart', traces, layout, plotConfig);

    // RSI sub-chart
    const rsiContainer = document.getElementById('rsiContainer');
    if (hasRSI && rsiData) {
        rsiContainer.style.display = 'block';
        renderRSI(rsiData);
    } else {
        rsiContainer.style.display = 'none';
    }

    // MACD sub-chart
    const macdContainer = document.getElementById('macdContainer');
    if (hasMACd && Object.keys(macdData).length > 0) {
        macdContainer.style.display = 'block';
        renderMACD(macdData);
    } else {
        macdContainer.style.display = 'none';
    }
}

function getTradeMarkers(openPos, closedPos, bars, labels) {
    const traces = [];
    const allPositions = [...openPos, ...closedPos];

    // Entry markers
    const buyEntries = { x: [], y: [], text: [] };
    const sellEntries = { x: [], y: [], text: [] };

    for (const pos of allPositions) {
        const entryIdx = findNearestIndex(bars.datetime, pos.entry_time);
        if (entryIdx >= 0) {
            const target = pos.direction === 'buy' ? buyEntries : sellEntries;
            target.x.push(labels[entryIdx]);
            target.y.push(pos.entry_price);
            target.text.push(`${pos.direction.toUpperCase()} @ ${pos.entry_price}`);
        }

        // Exit markers for closed positions
        if (pos.status === 'closed' && pos.exit_price) {
            const exitIdx = findNearestIndex(bars.datetime, pos.exit_time);
            if (exitIdx >= 0) {
                const exitTarget = pos.pnl >= 0 ? buyEntries : sellEntries;
                exitTarget.x.push(labels[exitIdx]);
                exitTarget.y.push(pos.exit_price);
                exitTarget.text.push(`Close @ ${pos.exit_price} (${pos.pnl >= 0 ? '+' : ''}${pos.pnl})`);
            }
        }
    }

    if (buyEntries.x.length > 0) {
        traces.push({
            x: buyEntries.x, y: buyEntries.y, text: buyEntries.text,
            type: 'scatter', mode: 'markers',
            marker: {
                symbol: 'triangle-up', size: 12, color: COLORS.green,
                line: { width: 1, color: '#fff' }
            },
            name: 'Buy', showlegend: false, hoverinfo: 'text',
        });
    }

    if (sellEntries.x.length > 0) {
        traces.push({
            x: sellEntries.x, y: sellEntries.y, text: sellEntries.text,
            type: 'scatter', mode: 'markers',
            marker: {
                symbol: 'triangle-down', size: 12, color: COLORS.red,
                line: { width: 1, color: '#fff' }
            },
            name: 'Sell', showlegend: false, hoverinfo: 'text',
        });
    }

    return traces;
}

function findNearestIndex(datetimes, target) {
    if (!target) return -1;
    const targetStr = target.toString().substring(0, 19);
    for (let i = 0; i < datetimes.length; i++) {
        if (datetimes[i].substring(0, 19) === targetStr) return i;
    }
    // Find nearest
    for (let i = datetimes.length - 1; i >= 0; i--) {
        if (datetimes[i] <= targetStr) return i;
    }
    return -1;
}

function getSLTPShapes(positions) {
    const shapes = [];
    for (const pos of positions) {
        if (pos.sl) {
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1,
                yref: 'y', y0: pos.sl, y1: pos.sl,
                line: { color: COLORS.red, width: 1, dash: 'dot' },
            });
        }
        if (pos.tp) {
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1,
                yref: 'y', y0: pos.tp, y1: pos.tp,
                line: { color: COLORS.green, width: 1, dash: 'dot' },
            });
        }
    }
    return shapes;
}

// ── RSI Sub-Chart ─────────────────────────────────────────
function renderRSI(rsiData) {
    const trace = {
        x: rsiData.labels,
        y: rsiData.values,
        type: 'scatter',
        mode: 'lines',
        name: rsiData.name,
        line: { color: COLORS.yellow, width: 1.5 },
    };

    const layout = {
        paper_bgcolor: COLORS.bg,
        plot_bgcolor: COLORS.bg,
        font: { family: 'Inter', size: 10, color: COLORS.text },
        margin: { l: 50, r: 60, t: 5, b: 20 },
        xaxis: { showticklabels: false, gridcolor: COLORS.grid, zeroline: false },
        yaxis: {
            gridcolor: COLORS.grid, side: 'right', range: [0, 100],
            tickvals: [30, 50, 70], zeroline: false, tickfont: { size: 9 },
        },
        shapes: [
            {
                type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 70, y1: 70,
                line: { color: COLORS.red, width: 0.5, dash: 'dot' }
            },
            {
                type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 30, y1: 30,
                line: { color: COLORS.green, width: 0.5, dash: 'dot' }
            },
        ],
        showlegend: false,
    };

    Plotly.react('rsiChart', [trace], layout, { ...plotConfig, displayModeBar: false });
}

// ── MACD Sub-Chart ────────────────────────────────────────
function renderMACD(macdData) {
    const traces = [];

    if (macdData['MACD']) {
        traces.push({
            x: macdData['MACD'].labels, y: macdData['MACD'].values,
            type: 'scatter', mode: 'lines', name: 'MACD',
            line: { color: COLORS.blue, width: 1.5 },
        });
    }
    if (macdData['MACD_Signal']) {
        traces.push({
            x: macdData['MACD_Signal'].labels, y: macdData['MACD_Signal'].values,
            type: 'scatter', mode: 'lines', name: 'Signal',
            line: { color: COLORS.orange, width: 1.5 },
        });
    }
    if (macdData['MACD_Hist']) {
        const colors = macdData['MACD_Hist'].values.map(v => v >= 0 ? COLORS.green : COLORS.red);
        traces.push({
            x: macdData['MACD_Hist'].labels, y: macdData['MACD_Hist'].values,
            type: 'bar', name: 'Histogram',
            marker: { color: colors, opacity: 0.6 },
        });
    }

    const layout = {
        paper_bgcolor: COLORS.bg,
        plot_bgcolor: COLORS.bg,
        font: { family: 'Inter', size: 10, color: COLORS.text },
        margin: { l: 50, r: 60, t: 5, b: 20 },
        xaxis: { showticklabels: false, gridcolor: COLORS.grid, zeroline: false },
        yaxis: {
            gridcolor: COLORS.grid, side: 'right', zeroline: true,
            zerolinecolor: COLORS.grid, tickfont: { size: 9 }, tickformat: '.5f',
        },
        showlegend: false,
        barmode: 'relative',
    };

    Plotly.react('macdChart', traces, layout, { ...plotConfig, displayModeBar: false });
}

// ── Stats Update ──────────────────────────────────────────
function updateStats(account) {
    if (!account) return;

    const fmt = (val) => `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    setStatValue('statBalance', fmt(account.balance));
    setStatValue('statEquity', fmt(account.equity));

    const floatEl = document.getElementById('statFloating');
    floatEl.textContent = fmt(account.floating_pnl);
    floatEl.className = `stat-value ${account.floating_pnl > 0 ? 'positive' : account.floating_pnl < 0 ? 'negative' : 'neutral'}`;

    const closedEl = document.getElementById('statClosed');
    closedEl.textContent = fmt(account.closed_pnl);
    closedEl.className = `stat-value ${account.closed_pnl > 0 ? 'positive' : account.closed_pnl < 0 ? 'negative' : 'neutral'}`;

    document.getElementById('statDrawdown').textContent = `${account.max_drawdown}%`;
    document.getElementById('statWinRate').textContent = `${account.win_rate}%`;
    document.getElementById('statTrades').textContent = account.total_trades;
}

function setStatValue(id, text) {
    document.getElementById(id).textContent = text;
}

// ── Progress Update ───────────────────────────────────────
function updateProgress(progress) {
    if (!progress) return;

    const slider = document.getElementById('progressSlider');
    slider.max = progress.total_bars - 1;
    slider.value = progress.current_index;

    document.getElementById('progressLabel').textContent =
        `${progress.current_index + 1} / ${progress.total_bars}`;

    document.getElementById('currentDatetime').textContent =
        progress.current_datetime || '--';
}

// ── Positions Update ──────────────────────────────────────
function updatePositions(positions) {
    const container = document.getElementById('openPositions');
    if (!positions || positions.length === 0) {
        container.innerHTML = '<span class="empty-msg">No open positions</span>';
        return;
    }

    container.innerHTML = positions.map(pos => {
        const pnlClass = pos.pnl >= 0 ? 'positive' : 'negative';
        const pnlStr = pos.pnl >= 0 ? `+${pos.pnl}` : pos.pnl;
        return `
            <div class="position-row">
                <span class="dir ${pos.direction}">${pos.direction}</span>
                <span>${pos.lot_size}L @ ${pos.entry_price}</span>
                <span class="pnl ${pnlClass}">${pnlStr}</span>
                <button class="close-pos-btn" onclick="closePosition('${pos.id}')">Close</button>
            </div>
        `;
    }).join('');
}

// ── Trade History Update ──────────────────────────────────
function updateHistory(history) {
    const container = document.getElementById('tradeHistory');
    if (!history || history.length === 0) {
        container.innerHTML = '<span class="empty-msg">No trades yet</span>';
        return;
    }

    // Show most recent first, max 50
    const recent = history.slice(-50).reverse();
    container.innerHTML = recent.map(trade => {
        const pnlClass = trade.pnl >= 0 ? 'positive' : 'negative';
        const pnlStr = trade.pnl >= 0 ? `+${trade.pnl}` : trade.pnl;
        return `
            <div class="history-row">
                <span class="dir ${trade.direction}">${trade.direction.toUpperCase()}</span>
                <span>${trade.lot_size}L ${trade.entry_price} → ${trade.exit_price}</span>
                <span class="pnl ${pnlClass}">${pnlStr}</span>
            </div>
        `;
    }).join('');
}

// ── Replay Controls ───────────────────────────────────────
function setupControls() {
    // Load button
    document.getElementById('loadBtn').addEventListener('click', async () => {
        const symbol = document.getElementById('symbolSelect').value;
        const timeframe = document.getElementById('timeframeSelect').value;
        stopPlaying();
        const result = await sendAction('/api/load', { symbol, timeframe });
        if (result && result.status === 'ok') {
            fetchData();
        }
    });

    // Replay buttons
    document.getElementById('stepBackBtn').addEventListener('click', async () => {
        await stepBack();
    });

    document.getElementById('stepFwdBtn').addEventListener('click', async () => {
        await stepForward();
    });

    document.getElementById('playPauseBtn').addEventListener('click', () => {
        togglePlay();
    });

    document.getElementById('jumpBackBtn').addEventListener('click', async () => {
        stopPlaying();
        await sendAction('/api/jump', { index: 0 });
        fetchData();
    });

    document.getElementById('jumpFwdBtn').addEventListener('click', async () => {
        stopPlaying();
        const total = currentData?.progress?.total_bars || 500;
        await sendAction('/api/jump', { index: total - 1 });
        fetchData();
    });

    // Speed buttons
    document.querySelectorAll('.btn-speed').forEach(btn => {
        btn.addEventListener('click', async () => {
            const speed = parseInt(btn.dataset.speed);
            document.querySelectorAll('.btn-speed').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const result = await sendAction('/api/speed', { speed });
            if (result) {
                intervalMs = result.interval_ms || 1000;
                if (isPlaying) {
                    stopPlaying();
                    startPlaying();
                }
            }
        });
    });

    // Progress slider
    document.getElementById('progressSlider').addEventListener('input', async (e) => {
        stopPlaying();
        await sendAction('/api/jump', { index: parseInt(e.target.value) });
        fetchData();
    });

    // Trading buttons
    document.getElementById('buyBtn').addEventListener('click', () => executeTrade('buy'));
    document.getElementById('sellBtn').addEventListener('click', () => executeTrade('sell'));
    document.getElementById('closeAllBtn').addEventListener('click', async () => {
        await sendAction('/api/trade', { action: 'close_all' });
        fetchData();
    });

    // Indicator modal
    document.getElementById('indicatorBtn').addEventListener('click', () => {
        document.getElementById('indicatorModal').classList.remove('hidden');
    });

    document.getElementById('closeModal').addEventListener('click', () => {
        document.getElementById('indicatorModal').classList.add('hidden');
    });

    document.getElementById('applyIndicators').addEventListener('click', applyIndicators);

    // Close modal on outside click
    document.getElementById('indicatorModal').addEventListener('click', (e) => {
        if (e.target === document.getElementById('indicatorModal')) {
            document.getElementById('indicatorModal').classList.add('hidden');
        }
    });
}

// ── Keyboard Shortcuts ────────────────────────────────────
function setupKeyboard() {
    document.addEventListener('keydown', (e) => {
        // Don't trigger when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

        switch (e.code) {
            case 'Space':
                e.preventDefault();
                togglePlay();
                break;
            case 'ArrowRight':
                e.preventDefault();
                stepForward();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                stepBack();
                break;
            case 'Home':
                e.preventDefault();
                stopPlaying();
                sendAction('/api/jump', { index: 0 }).then(() => fetchData());
                break;
            case 'End':
                e.preventDefault();
                stopPlaying();
                const total = currentData?.progress?.total_bars || 500;
                sendAction('/api/jump', { index: total - 1 }).then(() => fetchData());
                break;
            case 'KeyB':
                e.preventDefault();
                executeTrade('buy');
                break;
            case 'KeyS':
                e.preventDefault();
                executeTrade('sell');
                break;
        }
    });
}

// ── Play/Pause Logic ──────────────────────────────────────
function togglePlay() {
    if (isPlaying) {
        stopPlaying();
        sendAction('/api/pause');
    } else {
        startPlaying();
        sendAction('/api/play');
    }
}

function startPlaying() {
    isPlaying = true;
    updatePlayButton();
    playInterval = setInterval(async () => {
        const result = await sendAction('/api/step');
        if (result && result.status === 'ok') {
            fetchData();
        } else {
            stopPlaying();
        }
    }, intervalMs);
}

function stopPlaying() {
    isPlaying = false;
    if (playInterval) {
        clearInterval(playInterval);
        playInterval = null;
    }
    updatePlayButton();
}

function updatePlayButton() {
    const btn = document.getElementById('playPauseBtn');
    if (isPlaying) {
        btn.textContent = '⏸';
        btn.classList.add('playing');
        btn.title = 'Pause (Space)';
    } else {
        btn.textContent = '▶';
        btn.classList.remove('playing');
        btn.title = 'Play (Space)';
    }
}

async function stepForward() {
    const result = await sendAction('/api/step');
    if (result) fetchData();
}

async function stepBack() {
    const result = await sendAction('/api/back');
    if (result) fetchData();
}

// ── Trading ───────────────────────────────────────────────
async function executeTrade(direction) {
    const lotSize = parseFloat(document.getElementById('lotSize').value) || 0.1;
    const slVal = document.getElementById('slInput').value;
    const tpVal = document.getElementById('tpInput').value;

    const body = {
        action: direction,
        lot_size: lotSize,
    };

    if (slVal) body.sl = parseFloat(slVal);
    if (tpVal) body.tp = parseFloat(tpVal);

    const result = await sendAction('/api/trade', body);
    if (result) fetchData();
}

async function closePosition(positionId) {
    const result = await sendAction('/api/trade', {
        action: 'close',
        position_id: positionId,
    });
    if (result) fetchData();
}

// ── Indicators ────────────────────────────────────────────
async function applyIndicators() {
    // Clear all first
    await sendAction('/api/indicators', { action: 'clear' });

    // Add checked indicators
    if (document.getElementById('indSMA').checked) {
        await sendAction('/api/indicators', {
            action: 'set', name: 'sma',
            settings: { period: parseInt(document.getElementById('smaPeriod').value) }
        });
    }

    if (document.getElementById('indEMA').checked) {
        await sendAction('/api/indicators', {
            action: 'set', name: 'ema',
            settings: { period: parseInt(document.getElementById('emaPeriod').value) }
        });
    }

    if (document.getElementById('indRSI').checked) {
        await sendAction('/api/indicators', {
            action: 'set', name: 'rsi',
            settings: { period: parseInt(document.getElementById('rsiPeriod').value) }
        });
    }

    if (document.getElementById('indMACD').checked) {
        await sendAction('/api/indicators', {
            action: 'set', name: 'macd',
            settings: {
                fast: parseInt(document.getElementById('macdFast').value),
                slow: parseInt(document.getElementById('macdSlow').value),
                signal: parseInt(document.getElementById('macdSignal').value),
            }
        });
    }

    if (document.getElementById('indBB').checked) {
        await sendAction('/api/indicators', {
            action: 'set', name: 'bollinger',
            settings: {
                period: parseInt(document.getElementById('bbPeriod').value),
                std_dev: parseFloat(document.getElementById('bbStd').value),
            }
        });
    }

    document.getElementById('indicatorModal').classList.add('hidden');
    fetchData();
}

// ── Window Resize ─────────────────────────────────────────
window.addEventListener('resize', () => {
    Plotly.Plots.resize('chart');
    const rsiC = document.getElementById('rsiContainer');
    if (rsiC.style.display !== 'none') Plotly.Plots.resize('rsiChart');
    const macdC = document.getElementById('macdContainer');
    if (macdC.style.display !== 'none') Plotly.Plots.resize('macdChart');
});
