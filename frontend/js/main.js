// Main App Logic
let allStocks = [];
let currentSymbol = null;

async function init() {
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');
    
    try {
        // Load everything in parallel (all from DB = instant)
        await Promise.all([
            fetchMarketData(),
            loadTurkishGold(),
            loadExchangeRates()
        ]);
        
        // Load these after main data
        loadAIInsight();
        loadOpportunities();
        
    } catch (error) {
        console.error('Init error:', error);
        document.getElementById('stock-grid').innerHTML =
            '<p style="color: var(--danger-color); grid-column: 1/-1; text-align: center;">Failed to load market data. Please refresh.</p>';
    } finally {
        loader.classList.add('hidden');
    }
}

async function fetchMarketData() {
    const response = await fetch(`${API_URL}/api/market-data/quick`);
    if (!response.ok) throw new Error('Failed to fetch market data');
    const data = await response.json();
    processData(data);
}

async function loadTurkishGold() {
    try {
        const res = await fetch(`${API_URL}/api/turkish-gold`);
        if (!res.ok) return;
        const data = await res.json();
        renderGoldCards(data.gold || []);
    } catch (e) { console.warn('Gold data unavailable:', e); }
}

async function loadExchangeRates() {
    try {
        const res = await fetch(`${API_URL}/api/exchange-rates`);
        if (!res.ok) return;
        const data = await res.json();
        renderExchangeRates(data.rates || []);
    } catch (e) { console.warn('Exchange rates unavailable:', e); }
}

async function loadAIInsight() {
    const aiSection = document.getElementById('ai-section');
    if (aiSection) aiSection.classList.remove('hidden');
    try {
        const res = await fetch(`${API_URL}/api/insight`);
        const data = await res.json();
        const text = (data.insight || 'Analyzing market...').replace(/\n/g, '<br>');
        const aiTextEl = document.getElementById('ai-text');
        if (aiTextEl) aiTextEl.innerHTML = text;
    } catch (e) {
        const aiTextEl = document.getElementById('ai-text');
        if (aiTextEl) aiTextEl.innerText = '🐺 AI Protocol Offline.';
    }
}

async function loadOpportunities() {
    try {
        const res = await fetch(`${API_URL}/api/opportunities`);
        const data = await res.json();
        renderOpportunities(data.opportunities || []);
    } catch (e) { console.error('Opportunities error:', e); }
}

function processData(data) {
    allStocks = data.stocks || [];
    window.allStocks = allStocks;
    
    const toggle = document.getElementById('region-toggle');
    const isGlobalMode = toggle ? !toggle.checked : false; // Default TR is checked? Wait, let's look at logic: checked means TR or Global?
    // Let's assume toggle checked means Global mode
    const isGlobalModeVal = toggle ? toggle.checked : false;
    
    const stockGrid = document.getElementById('stock-grid');
    if (!stockGrid) return;
    stockGrid.innerHTML = '';
    
    let displayStocks = allStocks.filter(stock => {
        const sym = stock.symbol || '';
        const isStockGlobal = !sym.endsWith('.IS') && stock.market_type !== 'BIST';
        return isGlobalModeVal ? isStockGlobal : !isStockGlobal;
    });
    
    if (displayStocks.length === 0) {
        stockGrid.innerHTML = '<p style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">No stocks found. Data is loading...</p>';
        return;
    }
    
    displayStocks.forEach(stock => renderStockCard(stock));
    if (typeof initSearch === 'function') initSearch();
}

function initSearch() {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');
    if (!searchInput || !searchResults) return;
    
    // Remove old listeners by cloning
    const newInput = searchInput.cloneNode(true);
    searchInput.parentNode.replaceChild(newInput, searchInput);
    
    newInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        if (!query) { searchResults.classList.add('hidden'); return; }
        
        const toggle = document.getElementById('region-toggle');
        const isGlobalModeVal = toggle ? toggle.checked : false;
        
        const matches = allStocks.filter(stock => {
            const sym = stock.symbol || '';
            const isStockGlobal = !sym.endsWith('.IS') && stock.market_type !== 'BIST';
            if (isGlobalModeVal !== isStockGlobal) return false;
            return sym.toLowerCase().includes(query) || (stock.name || '').toLowerCase().includes(query);
        });
        
        if (matches.length > 0) {
            searchResults.classList.remove('hidden');
            searchResults.innerHTML = '';
            matches.slice(0, 15).forEach(stock => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                const currency = stock.currency === 'USD' ? '$' : '₺';
                div.innerHTML = `
                    <div>
                        <div class="result-symbol">${(stock.symbol||'').replace('.IS', '')}</div>
                        <div class="result-name">${stock.name || stock.symbol}</div>
                    </div>
                    <div class="result-price" style="color:${(stock.change_pct||0) >= 0 ? '#4ade80' : '#f87171'}">
                        ${(stock.price||0).toFixed(2)} ${currency}
                    </div>
                `;
                div.onclick = () => { openModal(stock); searchResults.classList.add('hidden'); newInput.value = ''; };
                searchResults.appendChild(div);
            });
        } else {
            searchResults.innerHTML = '<div class="search-result-item" style="color:var(--text-secondary)">No results found</div>';
            searchResults.classList.remove('hidden');
        }
    });
    
    document.addEventListener('click', (e) => {
        if (!newInput.contains(e.target) && !searchResults.contains(e.target)) {
            searchResults.classList.add('hidden');
        }
    });
}

// Region toggle
window.toggleRegion = function() {
    const toggle = document.getElementById('region-toggle');
    const label = document.getElementById('region-label');
    if (toggle && label) {
        label.innerText = toggle.checked ? 'GLOBAL' : 'TR';
        label.style.color = toggle.checked ? '#f87171' : '#38bdf8';
    }
    processData({ stocks: allStocks });
}

// Refresh
window.refreshMarket = async function() {
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');
    try {
        // Trigger backend refresh
        await fetch(`${API_URL}/api/refresh`, { method: 'POST' });
        // Wait a moment then reload data
        await new Promise(r => setTimeout(r, 2000));
        await init();
    } catch(e) {
        console.error('Refresh error:', e);
    } finally {
        loader.classList.add('hidden');
    }
}

// Export
window.triggerExport = async function(period) {
    const btnContent = document.querySelector(`.export-card[onclick="triggerExport('${period}')"]`);
    const originalHTML = btnContent ? btnContent.innerHTML : '';
    if (btnContent) btnContent.innerHTML = '<div class="export-icon">⏳</div><div class="export-info"><h3>Exporting...</h3></div>';
    
    try {
        const portfolioView = document.getElementById('portfolio-view');
        const isPortfolioActive = portfolioView && !portfolioView.classList.contains('hidden');
        let endpoint = `${API_URL}/api/export/${period}`;
        
        if (isPortfolioActive) {
            const portfolio = typeof getPortfolio === 'function' ? getPortfolio() : [];
            if (portfolio.length === 0) { 
                alert('Portfolio is empty!'); 
                if (btnContent) btnContent.innerHTML = originalHTML; 
                return; 
            }
            const symbols = portfolio.map(s => s.symbol).join(',');
            endpoint = `${API_URL}/api/export/portfolio?symbols=${encodeURIComponent(symbols)}&period=${period}`;
        }
        
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Export failed');
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = isPortfolioActive ? `portfolio_${period}.xlsx` : `market_${period}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        
        if (btnContent) btnContent.innerHTML = '<div class="export-icon">✅</div><div class="export-info"><h3>Downloaded!</h3></div>';
        setTimeout(() => { 
            if (btnContent) btnContent.innerHTML = originalHTML; 
            if (typeof closeExportModal === 'function') closeExportModal(); 
        }, 1500);
    } catch (error) {
        console.error('Export error:', error);
        if (btnContent) btnContent.innerHTML = '<div class="export-icon">❌</div><div class="export-info"><h3>Failed</h3></div>';
        setTimeout(() => { if (btnContent) btnContent.innerHTML = originalHTML; }, 2000);
    }
}

// Ensure DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    init();
});
