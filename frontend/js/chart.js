let currentChartSymbol = null;

async function loadChart(symbol, period) {
    const chartEl = document.getElementById('stockChart');
    chartEl.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100%;color:var(--text-secondary)">Loading chart...</div>';
    currentChartSymbol = symbol;
    
    // Update button states
    document.querySelectorAll('.chart-controls button').forEach(b => {
        b.classList.remove('active');
        const text = b.textContent.toLowerCase();
        if (period === '1d' && text.includes('day')) b.classList.add('active');
        if (period === '1mo' && text.includes('month')) b.classList.add('active');
        if (period === '1y' && text.includes('year') && !text.includes('5')) b.classList.add('active');
        if (period === '5y' && text.includes('5')) b.classList.add('active');
    });
    
    try {
        const res = await fetch(`${API_URL}/api/chart/${symbol}/${period}`);
        if (!res.ok) throw new Error('Chart data unavailable');
        const data = await res.json();
        
        const history = data.history || [];
        if (history.length === 0) throw new Error('No data points');
        
        renderCandlestickChart(history);
    } catch(e) {
        console.error('Chart error:', e);
        chartEl.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100%;color:var(--text-secondary)">📊 Chart data unavailable for this period</div>';
    }
}

function renderCandlestickChart(history) {
    const dates = history.map(d => d.time);
    const opens = history.map(d => d.open);
    const highs = history.map(d => d.high);
    const lows = history.map(d => d.low);
    const closes = history.map(d => d.close);
    
    // Check if we have valid OHLC data
    const hasOHLC = opens.some(v => v && v > 0) && highs.some(v => v && v > 0);
    
    let traces;
    if (hasOHLC) {
        traces = [{
            x: dates, close: closes, open: opens, high: highs, low: lows,
            type: 'candlestick',
            increasing: { line: { color: '#4ade80' }, fillcolor: 'rgba(74,222,128,0.3)' },
            decreasing: { line: { color: '#f87171' }, fillcolor: 'rgba(248,113,113,0.3)' }
        }];
    } else {
        // Fallback: line chart
        const isUp = closes[closes.length-1] >= closes[0];
        traces = [{
            x: dates, y: closes, type: 'scatter', mode: 'lines',
            line: { color: isUp ? '#4ade80' : '#f87171', width: 2 },
            fill: 'tozeroy',
            fillcolor: isUp ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)'
        }];
    }
    
    const layout = {
        dragmode: 'zoom',
        margin: { r: 10, t: 10, b: 40, l: 60 },
        showlegend: false,
        xaxis: {
            autorange: true, type: 'date',
            rangeslider: { visible: false },
            gridcolor: 'rgba(255,255,255,0.05)',
            tickfont: { color: '#94a3b8', size: 10 }
        },
        yaxis: {
            autorange: true, type: 'linear',
            gridcolor: 'rgba(255,255,255,0.05)',
            tickfont: { color: '#94a3b8', size: 10 }
        },
        paper_bgcolor: '#1e293b',
        plot_bgcolor: '#1e293b',
        font: { color: '#e2e8f0' }
    };
    
    Plotly.newPlot('stockChart', traces, layout, { responsive: true, displayModeBar: false });
}

window.updateChart = function(period) {
    if (currentChartSymbol) loadChart(currentChartSymbol, period);
}
