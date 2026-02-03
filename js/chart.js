let currentChart = null;
let currentSymbol = null;

async function loadChart(symbol, range) {
    currentSymbol = symbol;
    // Reset buttons
    document.querySelectorAll('.chart-controls button').forEach(b => b.classList.remove('active'));
    const btnTextMap = {
        '1d': '1 Day',
        '1mo': '1 Month',
        '1y': '1 Year',
        '5y': '5 Years'
    };
    const btnText = btnTextMap[range] || '1 Year';
    const btn = Array.from(document.querySelectorAll('.chart-controls button')).find(b => b.textContent.includes(btnText));
    if (btn) btn.classList.add('active');

    // Fetch History from /api/chart endpoint
    try {
        const res = await fetch(`${API_URL}/api/chart/${symbol}/${range}`);
        const data = await res.json();
        renderChart(data.history, range);
    } catch (e) {
        console.error("Chart load failed", e);
    }
}

function renderChart(candleData, range) {
    if (!candleData || candleData.length === 0) {
        console.error("No data available for chart");
        return;
    }

    const chartContainer = document.getElementById('stockChart');
    chartContainer.innerHTML = ''; // Clear div

    // Prepare data for Plotly
    const dates = candleData.map(d => d.time);
    const opens = candleData.map(d => d.open);
    const highs = candleData.map(d => d.high);
    const lows = candleData.map(d => d.low);
    const closes = candleData.map(d => d.close);

    const trace = {
        x: dates,
        close: closes,
        decreasing: { line: { color: '#f87171' } },
        increasing: { line: { color: '#4ade80' } },
        high: highs,
        low: lows,
        open: opens,
        type: 'candlestick',
        name: currentSymbol
    };

    const layout = {
        dragmode: 'zoom',
        showlegend: false,
        xaxis: {
            rangeslider: { visible: false },
            gridcolor: 'rgba(255,255,255,0.05)',
            color: '#94a3b8',
            tickformat: range === '1d' ? '%H:%M' : '%Y-%m-%d'
        },
        yaxis: {
            gridcolor: 'rgba(255,255,255,0.05)',
            color: '#94a3b8'
        },
        plot_bgcolor: 'rgba(15, 23, 42, 0.5)',
        paper_bgcolor: 'transparent',
        font: { color: '#94a3b8', family: 'Inter, sans-serif' },
        margin: { l: 50, r: 20, t: 20, b: 50 },
        hovermode: 'x unified'
    };

    const config = {
        responsive: true,
        displayModeBar: false
    };

    Plotly.newPlot(chartContainer, [trace], layout, config);
}

// Expose globally
window.loadChart = loadChart;

// Add updateChart function for time period buttons
window.updateChart = function (period) {
    if (!currentSymbol) {
        console.error('No symbol selected');
        return;
    }
    loadChart(currentSymbol, period);
};
