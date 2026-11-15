let currentChartSymbol = null;

/** Writes a loading or empty message into the chart area. */
function setChartMessage(chartEl, text, isError = false) {
    chartEl.replaceChildren();
    const message = document.createElement('div');
    message.className = isError ? 'chart-message is-empty' : 'chart-message';
    if (!isError) message.setAttribute('role', 'status');
    message.textContent = text;
    chartEl.appendChild(message);
}

async function loadChart(symbol, period) {
    const chartEl = document.getElementById('stockChart');
    if (window.Plotly) Plotly.purge(chartEl);
    setChartMessage(chartEl, 'Loading chart');
    currentChartSymbol = symbol;

    // Update button states
    document.querySelectorAll('.chart-controls button').forEach(b => {
        b.classList.remove('active');
        const text = b.textContent.toLowerCase();
        if (period === '1d' && text.includes('day')) b.classList.add('active');
        if (period === '1mo' && text.includes('month')) b.classList.add('active');
        if (period === '1y' && text.includes('year') && !text.includes('5')) b.classList.add('active');
        if (period === '5y' && text.includes('5')) b.classList.add('active');
        b.setAttribute('aria-pressed', String(b.classList.contains('active')));
    });

    try {
        const res = await fetch(`${API_URL}/api/chart/${encodeURIComponent(symbol)}/${encodeURIComponent(period)}`);
        if (!res.ok) throw new Error('Chart data unavailable');
        const data = await res.json();
        if (currentChartSymbol !== symbol) return;

        // A bar without a close is skipped; open, high and low may be null
        // and are not used by the line.
        const points = (data.history || []).filter(d => d && d.time && typeof d.close === 'number' && Number.isFinite(d.close));
        if (points.length === 0) throw new Error('No data points');

        renderLineChart(chartEl, points);
    } catch(e) {
        console.error('Chart error:', e);
        setChartMessage(chartEl, 'Chart data is not available for this period.', true);
    }
}

/** Reads a design token from tokens.css, so the chart follows the palette. */
function chartToken(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Closing prices as one blue line over a light blue area. */
function renderLineChart(chartEl, points) {
    const axisFont = { family: chartToken('--font-numeric'), size: 11, color: chartToken('--chart-axis') };
    const closes = points.map(d => d.close);
    const low = Math.min(...closes);
    const high = Math.max(...closes);
    const pad = (high - low) * 0.08 || high * 0.01;

    const trace = {
        x: points.map(d => d.time),
        y: closes,
        type: 'scatter',
        mode: 'lines',
        line: { color: chartToken('--chart-line'), width: 2 },
        fill: 'tozeroy',
        fillcolor: chartToken('--chart-area'),
        hovertemplate: '%{x}<br>%{y:.2f}<extra></extra>'
    };

    const layout = {
        dragmode: false,
        margin: { r: 12, t: 12, b: 36, l: 56 },
        showlegend: false,
        xaxis: {
            type: 'date',
            rangeslider: { visible: false },
            showgrid: false,
            linecolor: chartToken('--chart-grid'),
            tickfont: axisFont
        },
        yaxis: {
            type: 'linear',
            range: [low - pad, high + pad],
            gridcolor: chartToken('--chart-grid'),
            zeroline: false,
            tickfont: axisFont
        },
        hoverlabel: { font: { family: chartToken('--font-numeric') } },
        paper_bgcolor: chartToken('--color-surface'),
        plot_bgcolor: chartToken('--color-surface'),
        font: { family: chartToken('--font-sans'), color: chartToken('--color-text') }
    };

    chartEl.replaceChildren();
    Plotly.newPlot(chartEl, [trace], layout, { responsive: true, displayModeBar: false });
}

window.updateChart = function(period) {
    const symbolToLoad = currentChartSymbol || (typeof currentSymbol !== 'undefined' ? currentSymbol : null);
    if (symbolToLoad) loadChart(symbolToLoad, period);
}
