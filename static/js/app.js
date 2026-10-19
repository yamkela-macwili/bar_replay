/* ═══════════════════════════════════════════════════════════
   PyReplay Trader — Frontend Application
   ═══════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────
let isPlaying = false;
let playInterval = null;
let intervalMs = 1000;
let currentData = null;
let isLoadingMore = false;
let hasMoreHistory = true;
let currentSessionId = null;
let loadMoreTimer = null;
let activeDrawingTool = '';
let drawingPoints = [];
let chartDrawings = [];
let indicatorColors = JSON.parse(localStorage.getItem('pyreplay-indicator-colors') || '{}');
let indicatorVisibility = JSON.parse(localStorage.getItem('pyreplay-indicator-visibility') || '{"rsi":true,"volumeProfile":false}');
let volumeProfileBins = Number(localStorage.getItem('pyreplay-volume-profile-bins')) || 24;

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
    modeBarButtonsToAdd: ['eraseshape'],
    modeBarButtonsToRemove: ['select2d', 'lasso2d', 'toImage'],
    displaylogo: false,
    scrollZoom: true,
};

// ── Initialization ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await initChart();
    setupControls();
    setupKeyboard();
    const loadButton = document.getElementById('loadBtn');
    loadButton.disabled = true;
    showChartMessage('Loading market data…', 'loading');
    await bootstrapSession();
    loadButton.disabled = false;
    await loadSelectedData();
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

async function initChart() {
    const chart = document.getElementById('chart');
    await Plotly.newPlot(chart, [], { ...baseLayout }, plotConfig);

    // Lazy loading scroll detection
    chart.on('plotly_relayout', (eventData) => {
        const shapeWasEdited = Object.keys(eventData).some(key => key === 'shapes' || key.startsWith('shapes['));
        if (shapeWasEdited) {
            const fixedShapeCount = currentData
                ? getSLTPLines(currentData.open_positions || []).length : 0;
            const shapes = chart.layout?.shapes || [];
            chartDrawings = shapes.slice(fixedShapeCount).map(shape => JSON.parse(JSON.stringify(shape)));
            saveDrawings();
            document.getElementById('drawingMessage').textContent = 'Drawing saved';
        }

        const start = eventData['xaxis.range[0]'] ?? eventData['xaxis.range']?.[0];
        if (start === undefined || isLoadingMore || !hasMoreHistory || !currentData?.bars?.datetime?.length) return;
        const categories = chart.data?.[0]?.x || [];
        let startPosition = typeof start === 'number' ? start : categories.indexOf(start);
        if (startPosition < 0 && Number.isFinite(Number(start))) startPosition = Number(start);
        if (startPosition >= 0 && startPosition < Math.min(5, categories.length)) {
            if (loadMoreTimer) clearTimeout(loadMoreTimer);
            loadMoreTimer = setTimeout(() => loadMoreData('backward'), 150);
        }
    });

    chart.on('plotly_click', (eventData) => {
        if (!eventData.points?.length) return;
        const traceName = eventData.points[0].data?.name;
        if (!activeDrawingTool && traceName && traceName !== 'Price') {
            openIndicatorSettings(traceName);
            return;
        }
        if (!activeDrawingTool) return;
        const point = eventData.points[0];
        addDrawingPoint({ x: point.x, y: Number(point.y) });
    });
}

function openIndicatorSettings(traceName) {
    const modal = document.getElementById('indicatorModal');
    syncIndicatorModal();
    const match = traceName.match(/^(SMA|EMA|RSI)\((\d+)\)$/);
    const ids = { SMA: ['indSMA', 'smaPeriod'], EMA: ['indEMA', 'emaPeriod'], RSI: ['indRSI', 'rsiPeriod'] };
    const kind = match?.[1];
    if (kind) {
        document.getElementById(ids[kind][0]).checked = true;
        document.getElementById(ids[kind][1]).value = match[2];
    } else if (traceName.startsWith('BB_')) {
        document.getElementById('indBB').checked = true;
    } else if (traceName.startsWith('MACD')) {
        document.getElementById('indMACD').checked = true;
    }
    modal.classList.remove('hidden');
    const row = kind ? document.getElementById(ids[kind][0]).closest('.indicator-item') : null;
    row?.classList.add('indicator-item-focused');
    setTimeout(() => row?.classList.remove('indicator-item-focused'), 1200);
}

function syncIndicatorModal() {
    const names = Object.keys(currentData?.indicators || {});
    const matchPeriod = prefix => names.find(name => name.startsWith(prefix + '('))?.match(/\((\d+)\)/)?.[1];
    document.getElementById('indSMA').checked = Boolean(matchPeriod('SMA'));
    document.getElementById('indEMA').checked = Boolean(matchPeriod('EMA'));
    document.getElementById('indRSI').checked = Boolean(matchPeriod('RSI'));
    document.getElementById('indMACD').checked = names.some(name => name.startsWith('MACD'));
    document.getElementById('indBB').checked = names.some(name => name.startsWith('BB_'));
    document.getElementById('smaPeriod').value = matchPeriod('SMA') || 20;
    document.getElementById('emaPeriod').value = matchPeriod('EMA') || 50;
    document.getElementById('rsiPeriod').value = matchPeriod('RSI') || 14;
    document.getElementById('indVolumeProfile').checked = indicatorVisibility.volumeProfile;
    document.getElementById('smaColor').value = indicatorColors.sma || COLORS.orange;
    document.getElementById('emaColor').value = indicatorColors.ema || COLORS.purple;
    document.getElementById('rsiColor').value = indicatorColors.rsi || COLORS.yellow;
    document.getElementById('bbColor').value = indicatorColors.bollinger || COLORS.blue;
    document.getElementById('volumeProfileBins').value = volumeProfileBins;
}

function getVolumeProfileShapes(bars, bins) {
    const lows = bars.low || [], highs = bars.high || [], volumes = bars.volume || [];
    const low = Math.min(...lows.filter(Number.isFinite));
    const high = Math.max(...highs.filter(Number.isFinite));
    if (!Number.isFinite(low) || !Number.isFinite(high) || high <= low) return [];
    const step = (high - low) / bins;
    const totals = Array(bins).fill(0);
    for (let i = 0; i < volumes.length; i++) {
        const price = Number(bars.close[i]);
        const volume = Math.max(0, Number(volumes[i]) || 0);
        const index = Math.min(bins - 1, Math.max(0, Math.floor((price - low) / step)));
        totals[index] += volume;
    }
    const maxVolume = Math.max(...totals, 1);
    return totals.map((volume, i) => {
        const width = 0.18 * volume / maxVolume;
        const bottom = low + i * step;
        return { type: 'rect', xref: 'paper', yref: 'y', x0: 1 - width, x1: 1,
            y0: bottom, y1: bottom + step, fillcolor: 'rgba(41,98,255,0.20)',
            line: { width: 0 }, layer: 'below' };
    });
}

function drawingStorageKey() {
    return `pyreplay-drawings:${document.getElementById('symbolSelect').value}:${document.getElementById('timeframeSelect').value}`;
}

function restoreDrawings() {
    try {
        chartDrawings = JSON.parse(localStorage.getItem(drawingStorageKey()) || '[]');
        if (!Array.isArray(chartDrawings)) chartDrawings = [];
        chartDrawings = chartDrawings.map(shape => ({ ...shape, editable: true }));
    } catch (_) {
        chartDrawings = [];
    }
}

function saveDrawings() {
    localStorage.setItem(drawingStorageKey(), JSON.stringify(chartDrawings));
}

function drawingShape(type, x0, y0, x1, y1, extra = {}) {
    return { type, xref: 'x', yref: 'y', x0, y0, x1, y1, editable: true, ...extra };
}

function finishDrawing() {
    activeDrawingTool = '';
    drawingPoints = [];
    const selector = document.getElementById('drawingTool');
    if (selector) selector.value = '';
}

function addDrawingPoint(point) {
    const tool = activeDrawingTool;
    const message = document.getElementById('drawingMessage');
    if (['hline', 'hray'].includes(tool)) {
        const shapes = tool === 'hline'
            ? [drawingShape('line', 0, point.y, 1, point.y, { xref: 'paper', line: { color: COLORS.yellow, width: 1.5 } })]
            : [drawingShape('line', point.x, point.y, document.getElementById('chart').data[0].x.at(-1), point.y, { line: { color: COLORS.yellow, width: 1.5 } })];
        chartDrawings.push(...shapes);
    } else if (tool === 'vline') {
        chartDrawings.push(drawingShape('line', point.x, 0, point.x, 1, {
            yref: 'paper', line: { color: COLORS.blue, width: 1.5 }
        }));
    } else if (tool === 'vray') {
        chartDrawings.push(drawingShape('line', point.x, point.y, point.x, 1, {
            line: { color: COLORS.blue, width: 1.5 }
        }));
    } else {
        drawingPoints.push(point);
        const needed = tool === 'long' || tool === 'short' ? 3 : 2;
        if (drawingPoints.length < needed) {
            message.textContent = tool === 'long' || tool === 'short'
                ? `Click ${needed - drawingPoints.length} more point(s)` : 'Click the second point';
            return;
        }
        const [a, b, c] = drawingPoints;
        if (tool === 'trend') {
            chartDrawings.push(drawingShape('line', a.x, a.y, b.x, b.y, { line: { color: COLORS.orange, width: 2 } }));
        } else if (tool === 'rect') {
            chartDrawings.push(drawingShape('rect', a.x, a.y, b.x, b.y, {
                line: { color: COLORS.blue, width: 1.5 }, fillcolor: 'rgba(41, 98, 255, 0.10)'
            }));
        } else {
            const isLong = tool === 'long';
            const riskColor = 'rgba(239, 83, 80, 0.18)';
            const rewardColor = 'rgba(38, 166, 154, 0.18)';
            chartDrawings.push(
                drawingShape('rect', a.x, a.y, c.x, b.y, { line: { color: COLORS.red, width: 1 }, fillcolor: riskColor }),
                drawingShape('rect', a.x, a.y, c.x, c.y, { line: { color: COLORS.green, width: 1 }, fillcolor: rewardColor }),
                drawingShape('line', a.x, a.y, c.x, a.y, { line: { color: isLong ? COLORS.green : COLORS.red, width: 1.5, dash: 'dash' } })
            );
        }
        drawingPoints = [];
    }
    saveDrawings();
    if (['hline', 'hray', 'vline', 'vray'].includes(tool) || drawingPoints.length === 0) {
        finishDrawing();
    }
    if (currentData) updateChart(currentData);
    message.textContent = 'Drawing added';
}

// ── Data Fetching ─────────────────────────────────────────
async function fetchData() {
    try {
        const url = `/api/data?session_id=${currentSessionId}`;
        const res = await fetch(url);
        const data = await res.json();
        if (data.status === 'ok') {
            currentData = data;
            if (data.session_id) currentSessionId = data.session_id;

            await updateChart(data);
            updateMarketDataStatus(data.market_data);
            showChartMessage('', 'hidden');
            updateStats(data.account);
            updateProgress(data.progress);
            updatePositions(data.open_positions);
            updateHistory(data.trade_history);
        } else {
            showChartMessage(data.message || 'Could not load chart data. Use Load to retry.', 'error');
        }
    } catch (err) {
        console.error('Failed to fetch data:', err);
        showChartMessage('Could not reach the server. Check the connection and use Load to retry.', 'error');
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
            const oldRange = chart.layout?.xaxis?.range || chart._fullLayout?.xaxis?.range;
            const preservedRange = oldRange?.map(value =>
                typeof value === 'number' ? value + result.added : value
            );

            // Refresh data and chart, preserving the offset
            await fetchData();

            // Adjust range to keep focus on same bars
            if (preservedRange) await Plotly.relayout('chart', { 'xaxis.range': preservedRange });
        } else if (result.added === 0 && result.total_bars >= 3000) {
            hasMoreHistory = false;
            console.info('ℹ️ Memory ceiling reached (3000 bars). Backward scrolling locked.');
        } else {
            if (result.status === 'ok' && result.added === 0) hasMoreHistory = false;
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

function showChartMessage(message, state) {
    const element = document.getElementById('chartMessage');
    if (!element) return;
    document.getElementById('chartMessageText').textContent = message;
    element.className = `chart-message ${state}`;
    document.getElementById('retryLoad').hidden = state !== 'error';
}

async function loadSelectedData() {
    const button = document.getElementById('loadBtn');
    button.disabled = true;
    stopPlaying();
    hasMoreHistory = true;
    showChartMessage('Loading market data…', 'loading');

    try {
        while (true) {
            const symbol = document.getElementById('symbolSelect').value;
            const timeframe = document.getElementById('timeframeSelect').value;
            const balanceInput = document.getElementById('balanceInput');
            const initialBalance = Number(balanceInput.value);
            if (!Number.isFinite(initialBalance) || initialBalance <= 0) {
                throw new Error('Enter a balance greater than zero.');
            }
            const result = await sendAction('/api/load', {
                symbol, timeframe, provider: 'yfinance', initial_balance: initialBalance
            });
            if (!result || result.status !== 'ok') {
                throw new Error(result?.message || 'Load failed. Check the symbol and timeframe, then retry.');
            }

            currentSessionId = result.session_id;
            // If the user changed a selection while the request was running, load the new choice.
            if (symbol !== document.getElementById('symbolSelect').value ||
                timeframe !== document.getElementById('timeframeSelect').value ||
                initialBalance !== Number(balanceInput.value)) continue;

            const response = await fetch(`/api/data?session_id=${currentSessionId}`);
            const data = await response.json();
            if (!response.ok || data.status !== 'ok') {
                throw new Error(data.message || 'No chart data was returned for this selection.');
            }
            if (symbol !== document.getElementById('symbolSelect').value ||
                timeframe !== document.getElementById('timeframeSelect').value ||
                initialBalance !== Number(balanceInput.value)) continue;
            currentData = data;
            restoreDrawings();
            await updateChart(data);
            updateMarketDataStatus(data.market_data);
            updateStats(data.account);
            updateProgress(data.progress);
            updatePositions(data.open_positions);
            updateHistory(data.trade_history);
            balanceInput.value = Number(data.account.balance).toFixed(2);
            delete balanceInput.dataset.dirty;
            showChartMessage('', 'hidden');
            return;
        }
    } catch (err) {
        console.error('Failed to load chart:', err);
        showChartMessage(`${err.message} Use Load to retry.`, 'error');
    } finally {
        button.disabled = false;
    }
}


// ── Chart Rendering ───────────────────────────────────────
async function updateChart(data) {
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

    const profileShapes = indicatorVisibility.volumeProfile ? getVolumeProfileShapes(bars, volumeProfileBins) : [];
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

        let color = indicatorColors[name.startsWith('SMA') ? 'sma' : name.startsWith('EMA') ? 'ema' : 'bollinger'] || COLORS.orange;
        let dash = 'solid';
        let width = 1.5;

        if (name.startsWith('SMA')) { color = indicatorColors.sma || COLORS.orange; }
        else if (name.startsWith('EMA')) { color = indicatorColors.ema || COLORS.purple; }
        else if (name === 'BB_Upper') { color = indicatorColors.bollinger || COLORS.blue; dash = 'dash'; width = 1; }
        else if (name === 'BB_Middle') { color = indicatorColors.bollinger || COLORS.blue; width = 1; }
        else if (name === 'BB_Lower') { color = indicatorColors.bollinger || COLORS.blue; dash = 'dash'; width = 1; }

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
        dragmode: activeDrawingTool ? false : 'pan',
        shapes: [...profileShapes, ...slTpLines, ...chartDrawings]
    };

    await Plotly.react('chart', traces, layout, plotConfig);
    renderSubCharts(hasRSI && indicatorVisibility.rsi, rsiData, hasMACD, macdData);
    requestAnimationFrame(() => Plotly.Plots.resize('chart'));
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
        const trace = { x: rsiData.labels, y: rsiData.values, type: 'scatter', mode: 'lines', name: rsiData.name, line: { color: indicatorColors.rsi || COLORS.yellow, width: 1.5 } };
        const layout = {
            paper_bgcolor: COLORS.bg, plot_bgcolor: COLORS.bg, margin: { l: 50, r: 60, t: 5, b: 20 },
            xaxis: { showticklabels: false, gridcolor: COLORS.grid },
            yaxis: { gridcolor: COLORS.grid, side: 'right', range: [0, 100], tickvals: [30, 50, 70] },
            shapes: [
                { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 70, y1: 70, line: { color: COLORS.red, width: 0.5, dash: 'dot' } },
                { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 30, y1: 30, line: { color: COLORS.green, width: 0.5, dash: 'dot' } }
            ]
        };
        Plotly.react('rsiChart', [trace], layout, { ...plotConfig, displayModeBar: false }).then(() => {
            const rsiChart = document.getElementById('rsiChart');
            if (!rsiChart.dataset.settingsClickBound) {
                rsiChart.dataset.settingsClickBound = 'true';
                rsiChart.on('plotly_click', eventData => {
                    if (eventData.points?.length) openIndicatorSettings('RSI');
                });
            }
        });
    } else { rsiCont.style.display = 'none'; }

    const macdCont = document.getElementById('macdContainer');
    if (hasMACD) {
        macdCont.style.display = 'block';
        const mTraces = [];
        const macdLabels = macdData['MACD']?.labels || macdData['MACD_Signal']?.labels || macdData['MACD_Hist']?.labels || [];
        if (macdData['MACD']) mTraces.push({ x: macdLabels, y: macdData['MACD'].values, name: 'MACD', type: 'scatter', mode: 'lines', line: { color: COLORS.blue } });
        if (macdData['MACD_Signal']) mTraces.push({ x: macdLabels, y: macdData['MACD_Signal'].values, name: 'Signal', type: 'scatter', mode: 'lines', line: { color: COLORS.orange } });
        if (macdData['MACD_Hist']) mTraces.push({ x: macdLabels, y: macdData['MACD_Hist'].values, type: 'bar', marker: { color: macdData['MACD_Hist'].values.map(v => v >= 0 ? COLORS.green : COLORS.red) } });
        const mLayout = { paper_bgcolor: COLORS.bg, plot_bgcolor: COLORS.bg, margin: { l: 50, r: 60, t: 5, b: 20 }, xaxis: { showticklabels: false }, yaxis: { side: 'right' }, barmode: 'relative' };
        Plotly.react('macdChart', mTraces, mLayout, { ...plotConfig, displayModeBar: false }).then(() => {
            const macdChart = document.getElementById('macdChart');
            if (!macdChart.dataset.settingsClickBound) {
                macdChart.dataset.settingsClickBound = 'true';
                macdChart.on('plotly_click', eventData => {
                    if (eventData.points?.length) openIndicatorSettings(eventData.points[0].data?.name || 'MACD');
                });
            }
        });
    } else { macdCont.style.display = 'none'; }
}

// ── Stats, Progress, Positions UI ──────────────────────────
function updateStats(account) {
    if (!account) return;
    const f = (v) => `$${v.toFixed(2)}`;
    document.getElementById('statBalance').textContent = f(account.balance);
    const balanceInput = document.getElementById('balanceInput');
    if (balanceInput.dataset.dirty !== 'true') {
        balanceInput.value = Number(account.balance).toFixed(2);
    }
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
    document.getElementById('currentDatetime').textContent = formatLocalTime(progress.current_datetime);
}

function formatLocalTime(timestamp) {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return String(timestamp);
    return new Intl.DateTimeFormat(undefined, {
        year: 'numeric', month: 'short', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    }).format(date);
}

function updateMarketDataStatus(marketData) {
    const status = document.getElementById('latestDataStatus');
    if (!status || !marketData?.latest_bar) return;
    const latestDate = new Date(marketData.latest_bar);
    const isToday = latestDate.toDateString() === new Date().toDateString();
    const note = marketData.refresh_error ? ' · refresh failed' : (!isToday ? ' · no bar today' : '');
    status.textContent = `Latest ${marketData.symbol} ${marketData.timeframe}: ${formatLocalTime(marketData.latest_bar)}${note}`;
    status.classList.toggle('stale', Boolean(marketData.refresh_error) || !isToday);
    status.title = `Latest bar returned by ${marketData.provider}; displayed in your local timezone. ${marketData.refresh_error ? `The provider refresh failed: ${marketData.refresh_error}` : (isToday ? 'The latest bar date is today.' : 'The provider returned no bar dated today; the market may be closed or its feed may be delayed.')} ${marketData.checked_at ? `Provider request checked ${formatLocalTime(marketData.checked_at)}.` : 'No provider refresh was attempted for this data load.'}`;
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
        await loadSelectedData();
    });
    document.getElementById('retryLoad').addEventListener('click', loadSelectedData);
    const drawingTool = document.getElementById('drawingTool');
    drawingTool.addEventListener('change', () => {
        activeDrawingTool = drawingTool.value;
        drawingPoints = [];
        const labels = {
            hline: 'Click chart for horizontal line', hray: 'Click chart for horizontal ray',
            vline: 'Click chart for vertical line', vray: 'Click chart for vertical ray',
            trend: 'Click two points for trend line', rect: 'Click two corners for rectangle',
            long: 'Click entry, stop, then target', short: 'Click entry, stop, then target'
        };
        document.getElementById('drawingMessage').textContent = labels[activeDrawingTool] ||
            'Click a drawing to select it; drag its handles to edit. Use the eraser to remove it.';
        Plotly.relayout('chart', { dragmode: activeDrawingTool ? false : 'pan' });
    });
    document.getElementById('clearDrawings').addEventListener('click', () => {
        chartDrawings = [];
        drawingPoints = [];
        saveDrawings();
        document.getElementById('drawingMessage').textContent = 'Drawings cleared';
        if (currentData) updateChart(currentData);
    });
    const balanceInput = document.getElementById('balanceInput');
    balanceInput.addEventListener('input', () => { balanceInput.dataset.dirty = 'true'; });
    document.getElementById('balanceForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const message = document.getElementById('balanceMessage');
        const button = event.currentTarget.querySelector('button[type="submit"]');
        const value = Number(balanceInput.value);
        if (!Number.isFinite(value) || value <= 0) {
            message.textContent = 'Enter a balance greater than zero.';
            message.className = 'error';
            return;
        }

        button.disabled = true;
        message.textContent = 'Updating balance…';
        message.className = '';
        const result = await sendAction('/api/account/balance', { balance: value });
        if (result?.status === 'ok') {
            updateStats(result.account);
            balanceInput.value = Number(result.account.balance).toFixed(2);
            delete balanceInput.dataset.dirty;
            message.textContent = 'Balance updated. Open trade P&L is unchanged.';
            message.className = 'success';
        } else {
            message.textContent = result?.message || 'Could not update the balance.';
            message.className = 'error';
        }
        button.disabled = false;
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

    document.getElementById('indicatorBtn').addEventListener('click', () => {
        syncIndicatorModal();
        document.getElementById('indicatorModal').classList.remove('hidden');
    });
    document.getElementById('closeModal').addEventListener('click', () => document.getElementById('indicatorModal').classList.add('hidden'));
    document.getElementById('applyIndicators').addEventListener('click', applyIndicators);
}

// ── Helpers & Core Logic ───────────────────────────────────
function setupKeyboard() {
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT') return;
        if (e.code === 'Escape' && activeDrawingTool) {
            finishDrawing();
            document.getElementById('drawingMessage').textContent = 'Drawing cancelled';
            Plotly.relayout('chart', { dragmode: 'pan' });
            return;
        }
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

    indicatorVisibility.rsi = isChecked('indRSI');
    indicatorVisibility.volumeProfile = isChecked('indVolumeProfile');
    localStorage.setItem('pyreplay-indicator-visibility', JSON.stringify(indicatorVisibility));
    volumeProfileBins = Math.max(8, Math.min(60, parseInt(getVal('volumeProfileBins')) || 24));
    localStorage.setItem('pyreplay-volume-profile-bins', String(volumeProfileBins));
    indicatorColors = {
        sma: document.getElementById('smaColor').value,
        ema: document.getElementById('emaColor').value,
        rsi: document.getElementById('rsiColor').value,
        bollinger: document.getElementById('bbColor').value,
    };
    localStorage.setItem('pyreplay-indicator-colors', JSON.stringify(indicatorColors));

    if (isChecked('indSMA')) await sendAction('/api/indicators', { action: 'set', name: 'sma', settings: { period: parseInt(getVal('smaPeriod')) } });
    if (isChecked('indEMA')) await sendAction('/api/indicators', { action: 'set', name: 'ema', settings: { period: parseInt(getVal('emaPeriod')) } });
    if (isChecked('indRSI')) await sendAction('/api/indicators', { action: 'set', name: 'rsi', settings: { period: parseInt(getVal('rsiPeriod')) } });
    if (isChecked('indMACD')) await sendAction('/api/indicators', { action: 'set', name: 'macd', settings: { fast: parseInt(getVal('macdFast')), slow: parseInt(getVal('macdSlow')), signal: parseInt(getVal('macdSignal')) } });
    if (isChecked('indBB')) await sendAction('/api/indicators', { action: 'set', name: 'bollinger', settings: { period: parseInt(getVal('bbPeriod')), std_dev: parseFloat(getVal('bbStd')) } });

    document.getElementById('indicatorModal').classList.add('hidden');
    await fetchData();
}

window.addEventListener('resize', () => Plotly.Plots.resize('chart'));
