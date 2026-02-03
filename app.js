// -------------------------------------------------------------------------
// [DEPLOYMENT CONFIG]
// 1. LOCAL (Testing):
// const API_URL = "http://127.0.0.1:8000/api";
// 2. PRODUCTION (Render/Railway):
const API_URL = "https://web-production-36df.up.railway.app/api";
// -------------------------------------------------------------------------

const stockGrid = document.getElementById('stock-grid');
const opportunitiesList = document.getElementById('opportunities-list');
const loader = document.getElementById('loader');
const stockModal = document.getElementById('stock-modal');
const stockCloseBtn = document.querySelector('#stock-modal .close-modal');
const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');

let currentChart = null;
let currentSymbol = null;
let allStocks = []; // Cache for search

const portfolioGrid = document.getElementById('portfolio-grid');
const portfolioView = document.getElementById('portfolio-view');
const marketView = document.getElementById('market-view');
const portfolioEmpty = document.getElementById('portfolio-empty');

// Initialize
async function init() {
    try {
        // 1. Try to load from Session Storage
        const cachedData = sessionStorage.getItem('wolfee_market_data');
        if (cachedData) {
            console.log("Loading from cache...");
            processData(JSON.parse(cachedData));
        } else {
            console.log("Fetching fresh data...");
            await fetchAndCache();
        }

        loadAIInsight(); // Fetch AI text
        loadPortfolio(); // Load portfolio state

        // Check for deep link or background open
        const urlParams = new URLSearchParams(window.location.search);
        const symbolParam = urlParams.get('symbol');
        if (symbolParam) {
            // Wait slightly for data to populate
            setTimeout(() => {
                const target = allStocks.find(s => s.symbol === symbolParam || s.symbol.replace('.IS', '') === symbolParam);
                if (target) openModal(target);
            }, 500);
        }

    } catch (error) {
        console.error("Init Error:", error);
        loader.innerHTML = '<p>Error connecting to backend.</p>';
    }
}

async function fetchAndCache() {
    const response = await fetch(`${API_URL}/stocks`);
    const data = await response.json();

    // Save to Cache
    sessionStorage.setItem('wolfee_market_data', JSON.stringify(data));

    processData(data);
}

function processData(data) {
    // Hide loader immediately so user sees empty grid populating
    loader.classList.add('hidden');

    // Combine all lists
    const allSymbols = [...data.stocks, ...data.commodities];

    // Clear previous grid
    stockGrid.innerHTML = '';
    allStocks = []; // Reset cache

    // Render individually
    allSymbols.forEach(symbol => {
        fetchStockData(symbol).then(stock => {
            if (stock) {
                renderStockCard(stock);
                allStocks.push(stock); // Add to cache
            }
        });
    });

    loadOpportunities();
}

// Refresh Button Logic
window.refreshMarket = function () {
    // Clear cache
    sessionStorage.removeItem('wolfee_market_data');
    // Show loader
    loader.classList.remove('hidden');
    // Re-init
    init();
}

// Search Logic
searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    searchResults.innerHTML = '';

    if (query.length < 1) {
        searchResults.classList.add('hidden');
        return;
    }

    const matches = allStocks.filter(stock =>
        stock.symbol.toLowerCase().includes(query) ||
        stock.name.toLowerCase().includes(query)
    );

    if (matches.length > 0) {
        searchResults.classList.remove('hidden');
        matches.forEach(stock => {
            const div = document.createElement('div');
            div.className = 'search-result-item';
            div.innerHTML = `
                <div>
                    <div class="result-symbol">${stock.symbol.replace('.IS', '')}</div>
                    <div class="result-name">${stock.name}</div>
                </div>
                <div class="result-price" style="color:${stock.change_pct >= 0 ? '#4ade80' : '#f87171'}">
                    ₺${stock.price.toFixed(2)}
                </div>
            `;
            div.onclick = () => {
                openModal(stock);
                searchResults.classList.add('hidden');
                searchInput.value = ''; // Clear input
            };
            searchResults.appendChild(div);
        });
    } else {
        searchResults.innerHTML = '<div class="search-result-item" style="color:var(--text-secondary)">No results found</div>';
        searchResults.classList.remove('hidden');
    }
});

// Close search on click outside
document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.classList.add('hidden');
    }
});

async function loadAIInsight() {
    const aiSection = document.getElementById('ai-section');
    aiSection.classList.remove('hidden');
    try {
        const res = await fetch(`${API_URL}/insight`);
        const data = await res.json();
        // Convert \n to <br> for HTML display
        document.getElementById('ai-text').innerHTML = data.insight.replace(/\n/g, '<br>');
    } catch (e) {
        document.getElementById('ai-text').innerText = "AI Protocol Offline.";
    }
}

async function fetchStockData(symbol) {
    try {
        const response = await fetch(`${API_URL}/analyze/${symbol}`);
        if (!response.ok) return null;
        return await response.json();
    } catch (e) { return null; }
}

// ... existing code ...

function renderChart(labels, prices) {
    const ctx = document.getElementById('stockChart').getContext('2d');

    if (currentChart) currentChart.destroy();

    // Determine Color (Up=Green, Down=Red)
    const isUp = prices[prices.length - 1] >= prices[0];
    const color = isUp ? '#4ade80' : '#f87171'; // Green : Red

    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    // Use dynamic color for gradient
    const r = isUp ? 74 : 248;
    const g = isUp ? 222 : 113;
    const b = isUp ? 128 : 113;

    gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.5)`);
    gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.0)`);

    currentChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Price (TRY)',
                data: prices,
                borderColor: color,
                backgroundColor: gradient,
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { grid: { display: false }, ticks: { color: '#64748b' } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}


function renderStockCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';

    // Determine badge if buyable
    let badgeHtml = '';
    if (stock.is_buyable) {
        badgeHtml = `<div class="prediction-mini">Signal: ${stock.prediction}</div>`;
    }

    // Formatting
    const priceColor = stock.change_pct >= 0 ? '#4ade80' : '#f87171';
    const cleanName = stock.name.replace('.IS', '');

    card.innerHTML = `
        <div class="stock-header">
            <div class="symbol-group">
                <div class="stock-symbol">${stock.symbol.replace('.IS', '')}</div>
                <div class="stock-name">${cleanName}</div>
            </div>
            <div>
                <div class="stock-price">₺${stock.price.toFixed(2)}</div>
                <div class="price-change" style="color: ${priceColor}">
                    ${stock.change_pct > 0 ? '+' : ''}${stock.change_pct}%
                </div>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-item">
                <span>MA(20)</span>
                <span>${stock.ma_20.toFixed(2)}</span>
            </div>
            <div class="stat-item">
                <span>RSI</span>
                <span style="color: ${getRsiColor(stock.rsi)}">${stock.rsi}</span>
            </div>
            <div class="stat-item">
                <span>Vol</span>
                <span>${stock.volatility}%</span>
            </div>
        </div>
        
        ${badgeHtml}
    `;

    card.addEventListener('click', () => openModal(stock));
    stockGrid.appendChild(card);
}

function renderOpportunities(opportunities) {
    opportunitiesList.innerHTML = '';
    if (opportunities.length === 0) {
        opportunitiesList.innerHTML = '<p style="color: grey;">No strong signals right now.</p>';
        return;
    }

    opportunities.forEach(opp => {
        const div = document.createElement('div');
        div.className = 'opportunity-card';

        // Classify badge
        let badgeClass = 'badge-trend';
        let badgeText = 'TREND';
        if (opp.reason.includes('Golden')) { badgeClass = 'badge-golden'; badgeText = 'GOLDEN CROSS'; }
        if (opp.reason.includes('Oversold')) { badgeClass = 'badge-oversold'; badgeText = 'OVERSOLD'; }

        div.innerHTML = `
            <span class="opp-badge ${badgeClass}">${badgeText}</span>
            <div style="display:flex; justify-content:space-between; font-weight:bold; color: #fff;">
                <span>${opp.symbol.replace('.IS', '')}</span>
                <span>₺${opp.price.toFixed(2)}</span>
            </div>
            <div class="reason-text" style="color: #94a3b8; font-size: 0.8rem; margin-top: 5px;">
                ${opp.prediction}
            </div>
        `;
        div.addEventListener('click', () => {
            openModal(opp);
            // Mobile Optimization: Close sidebar if open so modal is visible
            const sidebar = document.getElementById('sidebar');
            if (sidebar.classList.contains('sidebar-open')) {
                toggleSidebar();
            }
        });
        opportunitiesList.appendChild(div);
    });
}

function getRsiColor(rsi) {
    if (rsi > 70) return '#f87171';
    if (rsi < 30) return '#4ade80';
    return '#94a3b8';
}

async function loadOpportunities() {
    try {
        const res = await fetch(`${API_URL}/opportunities`);
        const data = await res.json();
        renderOpportunities(data.opportunities);
    } catch (e) { console.error(e); }
}

// Modal Logic
function openModal(stock) {
    currentSymbol = stock.symbol;
    document.getElementById('modal-title').textContent = stock.name + " (" + stock.symbol.replace('.IS', '') + ")";
    document.getElementById('modal-prediction').textContent = "Analysis: " + stock.prediction;

    stockModal.classList.remove('hidden');
    loadChart(stock.symbol, '1y'); // Default view

    updatePortfolioButtonUI();
}

function updatePortfolioButtonUI() {
    const btn = document.getElementById('btn-portfolio-action');
    if (!currentSymbol) return;

    const portfolio = getPortfolio();
    const isIn = portfolio.some(s => s.symbol === currentSymbol);

    if (isIn) {
        btn.innerHTML = "❌ Remove from Portfolio";
        btn.style.borderColor = "var(--danger-color)";
        btn.style.color = "var(--danger-color)";
    } else {
        btn.innerHTML = "+ Add to Portfolio";
        btn.style.borderColor = "var(--accent-color)";
        btn.style.color = "var(--accent-color)";
    }
}

stockCloseBtn.onclick = () => stockModal.classList.add('hidden');
window.onclick = (e) => {
    if (e.target == stockModal) stockModal.classList.add('hidden');
}

// Chart Logic
async function loadChart(symbol, range) {
    // Reset buttons
    document.querySelectorAll('.chart-controls button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active'); // Current clicked button

    // Fetch History
    try {
        const res = await fetch(`${API_URL}/history/${symbol}`);
        const data = await res.json();

        // Filter data based on range (simple slice for demo, real implementations query API with dates)
        let history = data.history;
        if (range === '1mo') history = history.slice(-22);
        if (range === '1y') history = history.slice(-252);

        // Lightweight Charts expects {time, open, high, low, close}
        function renderChart(candleData) {
            if (!candleData || candleData.length === 0) {
                console.error("No data available for chart");
                return;
            }

            const chartContainer = document.getElementById('stockChart');
            chartContainer.innerHTML = ''; // Clear div

            // Prepare data for Plotly
            // Plotly expects arrays of Open, High, Low, Close, Dates
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
                xaxis: 'x',
                yaxis: 'y'
            };

            const layout = {
                dragmode: 'zoom',
                margin: { r: 10, t: 25, b: 40, l: 60 },
                showlegend: false,
                xaxis: {
                    autorange: true,
                    title: 'Date',
                    type: 'date',
                    rangeslider: { visible: false }, // Hide bottom slider to match style
                    gridcolor: 'rgba(255, 255, 255, 0.1)',
                    tickcolor: '#94a3b8',
                    tickfont: { color: '#94a3b8' }
                },
                yaxis: {
                    autorange: true,
                    type: 'linear',
                    gridcolor: 'rgba(255, 255, 255, 0.1)',
                    tickcolor: '#94a3b8',
                    tickfont: { color: '#94a3b8' }
                },
                paper_bgcolor: '#1e293b',
                plot_bgcolor: '#1e293b',
                font: {
                    color: '#e2e8f0'
                }
            };

            Plotly.newPlot('stockChart', [trace], layout, { responsive: true, displayModeBar: false });
        }
        renderChart(history);
    } catch (e) {
        console.error("Chart load failed", e);
    }
}

// Make updateChart global for buttons
window.updateChart = function (range) {
    loadChart(currentSymbol, range);
}

// Export Modal Logic
const exportModal = document.getElementById('export-modal');

function openExportModal() {
    exportModal.classList.remove('hidden');
}

function closeExportModal() {
    exportModal.classList.add('hidden');
}

// Close export modal when clicking outside
window.addEventListener('click', (e) => {
    if (e.target == exportModal) {
        closeExportModal();
    }
    // Existing check for stock modal is in window.onclick override, 
    // better to use addEventListener for both to avoid conflicts
    if (e.target == stockModal) {
        stockModal.classList.add('hidden');
    }
});

async function triggerExport(period) {
    const btnContent = document.querySelector(`.export-card[onclick="triggerExport('${period}')"]`);
    const originalText = btnContent.innerHTML;

    // Show loading state
    btnContent.innerHTML = `<div class="spinner" style="width:20px;height:20px;border-width:2px;margin:auto"></div>`;

    try {
        const response = await fetch(`${API_URL}/export/${period}`);

        if (!response.ok) throw new Error("Export failed");

        // Handle Blob download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `wolfee_market_analysis_${period}.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        closeExportModal();

    } catch (e) {
        console.error("Export error:", e);
        alert("Failed to export data. Please try again.");
    } finally {
        // Restore button (if modal still open, though we close it on success)
        btnContent.innerHTML = originalText;
    }
}

// Mobile Sidebar Toggle
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('sidebar-open');
    document.body.classList.toggle('no-scroll');
}

// -------------------------------------------------------------------------
// PORTFOLIO LOGIC
// -------------------------------------------------------------------------

function getPortfolio() {
    const raw = sessionStorage.getItem('wolfee_portfolio');
    return raw ? JSON.parse(raw) : [];
}

function savePortfolio(list) {
    sessionStorage.setItem('wolfee_portfolio', JSON.stringify(list));
}

window.togglePortfolioItem = function () {
    if (!currentSymbol) return;

    // Find full stock object from cache
    const stock = allStocks.find(s => s.symbol === currentSymbol);
    if (!stock) return;

    let list = getPortfolio();
    const existingIndex = list.findIndex(s => s.symbol === currentSymbol);

    if (existingIndex >= 0) {
        // Remove
        list.splice(existingIndex, 1);
    } else {
        // Add
        list.push(stock);
    }

    savePortfolio(list);
    updatePortfolioButtonUI();
    renderPortfolio(); // Update grid in background
}

function loadPortfolio() {
    renderPortfolio();
}

function renderPortfolio() {
    const list = getPortfolio();
    portfolioGrid.innerHTML = '';

    if (list.length === 0) {
        portfolioEmpty.classList.remove('hidden');
        return;
    }

    portfolioEmpty.classList.add('hidden');

    list.forEach(stock => {
        // Reuse render logic but append to portfolio grid
        const card = createStockCardElement(stock);
        portfolioGrid.appendChild(card);
    });
}

// Extract card creation to reuse logic
function createStockCardElement(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';

    // Determine badge if buyable
    let badgeHtml = '';
    if (stock.is_buyable) {
        badgeHtml = `<div class="prediction-mini">Signal: ${stock.prediction}</div>`;
    }

    // Formatting
    const priceColor = stock.change_pct >= 0 ? '#4ade80' : '#f87171';
    const cleanName = stock.name.replace('.IS', '');

    card.innerHTML = `
        <div class="stock-header">
            <div class="symbol-group">
                <div class="stock-symbol">${stock.symbol.replace('.IS', '')}</div>
                <div class="stock-name">${cleanName}</div>
            </div>
            <div>
                <div class="stock-price">₺${stock.price.toFixed(2)}</div>
                <div class="price-change" style="color: ${priceColor}">
                    ${stock.change_pct > 0 ? '+' : ''}${stock.change_pct}%
                </div>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-item">
                <span>MA(20)</span>
                <span>${stock.ma_20.toFixed(2)}</span>
            </div>
            <div class="stat-item">
                <span>RSI</span>
                <span style="color: ${getRsiColor(stock.rsi)}">${stock.rsi}</span>
            </div>
            <div class="stat-item">
                <span>Vol</span>
                <span>${stock.volatility}%</span>
            </div>
        </div>
        
        ${badgeHtml}
    `;

    card.addEventListener('click', () => openModal(stock));
    return card;
}

// Modify original renderStockCard to use the helper
window.renderStockCard = function (stock) { // globalize for init
    const card = createStockCardElement(stock);
    stockGrid.appendChild(card);
}

// Tab Switching
window.switchTab = function (tab) {
    // Buttons
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');

    // Views
    if (tab === 'market') {
        marketView.classList.remove('hidden');
        portfolioView.classList.add('hidden');
    } else {
        marketView.classList.add('hidden');
        portfolioView.classList.remove('hidden');
        renderPortfolio(); // Refresh view
    }
}

init();
