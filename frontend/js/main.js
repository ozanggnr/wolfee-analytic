// Main App Logic
let allStocks = [];
let currentSymbol = null;
let _pollInterval = null;
const POLL_INTERVAL_MS = 60000; // 60 seconds

// While the grid shows the "loading" placeholder (e.g. the server's first
// refresh has not finished yet), poll faster and rebuild the whole grid once
// data arrives. After the retries run out, the regular poll keeps checking.
const EMPTY_GRID_RETRY_MS = 5000;
const EMPTY_GRID_MAX_RETRIES = 12;
let _gridAwaitingData = false;
let _emptyGridRetryTimer = null;
let _emptyGridRetries = 0;

// Pause auto-polling when browser tab is inactive to reduce bandwidth and server load
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (_pollInterval) {
            clearInterval(_pollInterval);
            _pollInterval = null;
        }
    } else {
        pollForUpdates();
        startAutoPoll();
    }
});

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

        // Start background auto-polling
        startAutoPoll();
        
    } catch (error) {
        console.error('Init error:', error);
        document.getElementById('stock-grid').innerHTML =
            '<p class="grid-message is-error" role="alert">Market data could not be loaded. Retrying.</p>';
        _gridAwaitingData = true;
        startAutoPoll();
        scheduleEmptyGridRetry();
    } finally {
        loader.classList.add('hidden');
    }
}

function scheduleEmptyGridRetry() {
    if (!_gridAwaitingData || _emptyGridRetryTimer || document.hidden) return;
    if (_emptyGridRetries >= EMPTY_GRID_MAX_RETRIES) return;
    _emptyGridRetries++;
    _emptyGridRetryTimer = setTimeout(async () => {
        _emptyGridRetryTimer = null;
        await pollForUpdates();
    }, EMPTY_GRID_RETRY_MS);
}

function startAutoPoll() {
    if (_pollInterval) clearInterval(_pollInterval);
    _pollInterval = setInterval(async () => {
        await pollForUpdates();
    }, POLL_INTERVAL_MS);
}

/** Feed status on the header dot: fetching, live or error (colours in CSS). */
function setLiveState(state) {
    const dot = document.getElementById('live-dot');
    if (dot) dot.dataset.state = state;
}

async function pollForUpdates() {
    const label = document.getElementById('live-label');
    try {
        setLiveState('fetching');
        const response = await fetch(`${API_URL}/api/market-data/quick`, { cache: 'no-store' });
        if (!response.ok) throw new Error('Poll failed');
        const data = await response.json();
        const newStocks = deduplicateStocks(data.stocks || []);
        // A zone-less updated_at is UTC (API contract), not the viewer's local time
        const serverUpdatedAt = window.WolfeeFields.parseTimestamp(data.updated_at);

        // Find changed stocks and update only those cards
        let changedCount = 0;
        newStocks.forEach(newStock => {
            if (!newStock.price || newStock.price <= 0) return;
            const old = allStocks.find(s => s.symbol === newStock.symbol);
            if (!old || old.price !== newStock.price || old.change_pct !== newStock.change_pct) {
                changedCount++;
            }
        });

        if (changedCount > 0) {
            if (_gridAwaitingData) {
                // No cards to update in place yet: build the grid from scratch
                processData(data);
            } else {
                // Update allStocks and re-render changed cards in-place
                updateChangedCards(newStocks);
                allStocks = newStocks;
                window.allStocks = allStocks;
            }
            loadOpportunities();
            loadExchangeRates();
        } else {
            scheduleEmptyGridRetry();
        }

        // Update live label with data age
        if (serverUpdatedAt) {
            const ageSeconds = Math.round((Date.now() - serverUpdatedAt.getTime()) / 1000);
            const ageStr = ageSeconds < 60
                ? `${ageSeconds}s ago`
                : `${Math.round(ageSeconds / 60)}m ago`;
            if (label) label.textContent = `Updated ${ageStr}`;
        } else {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
            if (label) label.textContent = `Updated ${timeStr}`;
        }
        setLiveState('live');
    } catch (e) {
        console.warn('Poll error:', e);
        setLiveState('error');
        if (label) label.textContent = 'Reconnecting';
        scheduleEmptyGridRetry();
    }
}

function updateChangedCards(newStocks) {
    const toggle = document.getElementById('region-toggle');
    const isGlobalMode = toggle ? toggle.checked : false;
    const stockGrid = document.getElementById('stock-grid');
    if (!stockGrid) return;

    newStocks.forEach(newStock => {
        if (!newStock.price || newStock.price <= 0) return;
        const old = allStocks.find(s => s.symbol === newStock.symbol);
        if (old && old.price === newStock.price && old.change_pct === newStock.change_pct) return;

        // Check if this card is visible in the current region
        const sym = newStock.symbol || '';
        const isStockGlobal = !sym.endsWith('.IS') && newStock.market_type !== 'BIST';
        if (isGlobalMode !== isStockGlobal) return;

        // Replace the card's contents in place (same template as the first
        // render) and mark it briefly as updated
        const baseSym = baseSymbol(newStock);
        const card = stockGrid.querySelector(`[data-stock-symbol="${CSS.escape(baseSym)}"]`);
        if (!card) return;
        const replacement = createStockCardElement(newStock, stockCardInnerHTML(newStock));
        replacement.classList.add('is-updated');
        card.replaceWith(replacement);
        setTimeout(() => replacement.classList.remove('is-updated'), 1200);
    });
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
        if (!res.ok) throw new Error('Insight unavailable');
        const data = await res.json();
        const aiTextEl = document.getElementById('ai-text');
        if (aiTextEl) {
            renderAIResponse(aiTextEl, data, 'insight');
            addAIShowMore(aiTextEl);
        }
    } catch (e) {
        const aiTextEl = document.getElementById('ai-text');
        if (aiTextEl) {
            aiTextEl.innerHTML = '<p class="inline-error" role="alert">Market insight is not available right now. It will load on the next visit.</p>';
        }
    }
}

async function loadOpportunities() {
    try {
        const res = await fetch(`${API_URL}/api/opportunities`);
        const data = await res.json();
        renderOpportunities(data.opportunities || []);
    } catch (e) { console.error('Opportunities error:', e); }
}

let _processDataTimeout = null;

function deduplicateStocks(stocksArray) {
    if (!stocksArray || !Array.isArray(stocksArray)) return [];
    const seen = new Set();
    return stocksArray.filter(s => {
        if (!s || !s.symbol) return false;
        // Normalize symbol: uppercase, strip .IS and extra spaces
        const baseSymbol = s.symbol.toUpperCase().replace('.IS', '').trim();
        if (!baseSymbol || seen.has(baseSymbol)) return false;
        seen.add(baseSymbol);
        return true;
    });
}

function processData(data) {
    allStocks = deduplicateStocks(data.stocks || []);
    window.allStocks = allStocks;
    
    const toggle = document.getElementById('region-toggle');
    const isGlobalModeVal = toggle ? toggle.checked : false;
    
    const stockGrid = document.getElementById('stock-grid');
    if (!stockGrid) return;
    
    if (_processDataTimeout) {
        clearTimeout(_processDataTimeout);
    }
    
    // Fade out existing cards
    stockGrid.classList.add('switching');
    
    _processDataTimeout = setTimeout(() => {
        stockGrid.innerHTML = '';
        
        let displayStocks = allStocks.filter(stock => {
            if (!stock.price || stock.price <= 0) return false;
            const sym = stock.symbol || '';
            const isStockGlobal = !sym.endsWith('.IS') && stock.market_type !== 'BIST';
            return isGlobalModeVal ? isStockGlobal : !isStockGlobal;
        });

        // Double guarantee deduplication for display list
        const seenDisplay = new Set();
        displayStocks = displayStocks.filter(stock => {
            const symKey = (stock.symbol || '').toUpperCase().replace('.IS', '').trim();
            if (!symKey || seenDisplay.has(symKey)) return false;
            seenDisplay.add(symKey);
            return true;
        });
        
        if (displayStocks.length === 0) {
            stockGrid.innerHTML = '<p class="grid-message">No stocks to show yet. Market data is still loading.</p>';
            stockGrid.classList.remove('switching');
            _gridAwaitingData = true;
            scheduleEmptyGridRetry();
            return;
        }

        _gridAwaitingData = false;
        _emptyGridRetries = 0;
        stockGrid.classList.remove('switching');
        displayStocks.forEach((stock, i) => {
            renderStockCard(stock);
            const baseSym = (stock.symbol || '').replace('.IS', '').trim().toUpperCase();
            const card = stockGrid.querySelector(`[data-stock-symbol="${CSS.escape(baseSym)}"]`);
            if (card) {
                card.classList.add('card-animate-in');
                card.style.animationDelay = `${i * 0.03}s`;
            }
        });
        if (typeof initSearch === 'function') initSearch();
    }, 100);
}

function initSearch() {
    function bindSearch(inputEl, resultsEl, isMobile = false) {
        if (!inputEl || !resultsEl) return;
        
        // Remove old listeners by cloning
        const newInput = inputEl.cloneNode(true);
        inputEl.parentNode.replaceChild(newInput, inputEl);
        
        newInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            if (!query) { resultsEl.classList.add('hidden'); return; }
            
            let matches = [];
            if (typeof window.getFilteredStocks === 'function') {
                matches = window.getFilteredStocks(allStocks, query);
            } else {
                const toggle = document.getElementById('region-toggle') || document.getElementById('region-toggle-bar');
                const isGlobalModeVal = toggle ? toggle.checked : false;
                matches = allStocks.filter(stock => {
                    if (!stock.price || stock.price <= 0) return false;
                    const sym = stock.symbol || '';
                    const isStockGlobal = !sym.endsWith('.IS') && stock.market_type !== 'BIST';
                    if (isGlobalModeVal !== isStockGlobal) return false;
                    return sym.toLowerCase().includes(query) || (stock.name || '').toLowerCase().includes(query);
                });
            }
            
            if (matches.length > 0) {
                resultsEl.classList.remove('hidden');
                resultsEl.innerHTML = '';
                matches.slice(0, 15).forEach(stock => {
                    const div = document.createElement('button');
                    div.type = 'button';
                    div.className = 'search-result-item';
                    const currency = stock.currency === 'USD' ? '$' : '₺';
                    div.innerHTML = `
                        <span class="result-main">
                            <span class="result-symbol">${esc((stock.symbol||'').replace('.IS', ''))}</span>
                            <span class="result-name">${esc(stock.name || stock.symbol)}</span>
                        </span>
                        <span class="result-quote">
                            <span class="result-price">${esc(window.WolfeeFields.formatPrice(stock, 'price', currency))}</span>
                            ${changeHTML(stock, 'result-change')}
                        </span>
                    `;
                    div.onclick = () => { 
                        openModal(stock); 
                        resultsEl.classList.add('hidden'); 
                        newInput.value = ''; 
                        if (isMobile && typeof toggleMobileMenu === 'function') {
                            toggleMobileMenu();
                        }
                    };
                    resultsEl.appendChild(div);
                });
            } else {
                resultsEl.innerHTML = '<div class="search-empty">No matching symbol or name</div>';
                resultsEl.classList.remove('hidden');
            }
        });
        
        document.addEventListener('click', (e) => {
            if (!newInput.contains(e.target) && !resultsEl.contains(e.target)) {
                resultsEl.classList.add('hidden');
            }
        });
    }

    // Bind desktop search
    bindSearch(document.getElementById('search-input'), document.getElementById('search-results'), false);

    // Bind mobile drawer search
    bindSearch(document.getElementById('mobile-menu-search'), document.getElementById('mobile-search-results'), true);
}

// Universal synchronized Region Toggle across Desktop navbar, Mobile topbar, and Mobile drawer
window.toggleRegion = function(forcedChecked = null) {
    const desktopToggle = document.getElementById('region-toggle');
    const mobileBarToggle = document.getElementById('region-toggle-bar');
    const mobileDrawerToggle = document.getElementById('region-toggle-m');

    let isGlobal;
    if (typeof forcedChecked === 'boolean') {
        isGlobal = forcedChecked;
    } else if (desktopToggle && document.activeElement === desktopToggle) {
        isGlobal = desktopToggle.checked;
    } else if (mobileBarToggle && document.activeElement === mobileBarToggle) {
        isGlobal = mobileBarToggle.checked;
    } else if (mobileDrawerToggle && document.activeElement === mobileDrawerToggle) {
        isGlobal = mobileDrawerToggle.checked;
    } else if (desktopToggle) {
        isGlobal = desktopToggle.checked;
    } else {
        isGlobal = false;
    }

    // Synchronize all checkbox states
    if (desktopToggle) desktopToggle.checked = isGlobal;
    if (mobileBarToggle) mobileBarToggle.checked = isGlobal;
    if (mobileDrawerToggle) mobileDrawerToggle.checked = isGlobal;

    // Synchronize all label texts (colour comes from CSS)
    const labelText = isGlobal ? 'GLOBAL' : 'TR';

    ['region-label', 'region-label-bar', 'region-label-m'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerText = labelText;
    });

    processData({ stocks: allStocks });
};

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

// Portfolio Excel Export
window.triggerExport = async function(period) {
    const btnContent = document.querySelector(`.export-card[onclick="triggerExport('${period}')"]`);
    const originalHTML = btnContent ? btnContent.innerHTML : '';
    if (btnContent) btnContent.innerHTML = '<div class="export-icon">⏳</div><div class="export-info"><h3>Exporting...</h3></div>';
    
    try {
        const portfolio = typeof getPortfolio === 'function' ? getPortfolio() : [];
        if (portfolio.length === 0 && !window.currentUser) {
            alert('Your portfolio is empty! Add some stocks before exporting.');
            if (btnContent) btnContent.innerHTML = originalHTML;
            return;
        }

        const fetchFn = window.authFetch || fetch;
        const response = await fetchFn(`${API_URL}/api/export/portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ period, stocks: portfolio })
        });

        if (!response.ok) {
            let detail = 'Export failed';
            try {
                const errData = await response.json();
                if (errData && errData.detail) detail = errData.detail;
            } catch (e) {}
            throw new Error(detail);
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `portfolio_${period}.xlsx`;
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
        alert(error.message || 'Failed to generate portfolio export file.');
        if (btnContent) btnContent.innerHTML = '<div class="export-icon">❌</div><div class="export-info"><h3>Failed</h3></div>';
        setTimeout(() => { if (btnContent) btnContent.innerHTML = originalHTML; }, 2000);
    }
}

// Ensure DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    init();
});
