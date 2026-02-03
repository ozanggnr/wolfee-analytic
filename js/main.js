// Main App Logic

let allStocks = [];

async function init() {
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');
    loader.innerHTML = '<div class="loader-spinner"></div><p>Loading market data...</p>';

    // Check cache first  
    const cachedData = sessionStorage.getItem('wolfee_market_data');
    const cacheTime = sessionStorage.getItem('wolfee_cache_time');
    const now = Date.now();

    // Use cache if less than 5 minutes old
    if (cachedData && cacheTime && (now - parseInt(cacheTime)) < 300000) {
        console.log("Using cached data");
        const data = JSON.parse(cachedData);
        processData(data);
        loader.classList.add('hidden');
        loadAIInsight();
        loadOpportunities();
        return;
    }

    // Two-stage loading
    try {
        // Stage 1: Quick batch (100 stocks with multi-API fallback)
        await fetchQuickBatch();
        loader.innerHTML = '<div class="loader-spinner"></div><p>✓ Data loaded!</p>';
        setTimeout(() => loader.classList.add('hidden'), 1500);

        // Stage 2: Load rest in background (doesn't block UI)
        fetchFullBatchInBackground();

        loadAIInsight();
        loadOpportunities();
    } catch (error) {
        console.error('Init error:', error);
        document.getElementById('stock-grid').innerHTML =
            '<p style="color: red; grid-column: 1/-1;">Failed to load market data. Please refresh or check if Railway backend is running.</p>';
        loader.classList.add('hidden');
    }
}

// Stage 1: Fetch quick batch (100 stocks)
async function fetchQuickBatch() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000); // 2 min timeout

    try {
        const response = await fetch(`${API_URL}/api/market-data/quick`, {
            signal: controller.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Save to Cache with timestamp
        sessionStorage.setItem('wolfee_market_data', JSON.stringify(data));
        sessionStorage.setItem('wolfee_cache_time', Date.now().toString());

        processData(data);
        console.log(`✓ Quick batch loaded: ${data.stocks.length} stocks`);
    } catch (error) {
        console.error("Quick batch error:", error);
        throw error;
    } finally {
        clearTimeout(timeout);
    }
}

// Stage 2: Fetch full batch in background (doesn't block UI)
async function fetchFullBatchInBackground() {
    console.log("⏳ Starting background load of remaining stocks...");

    try {
        const response = await fetch(`${API_URL}/api/market-data/full`);

        if (!response.ok) {
            console.error("Background load failed:", response.status);
            return;
        }

        const data = await response.json();

        // Update cache with full data
        sessionStorage.setItem('wolfee_market_data', JSON.stringify(data));
        sessionStorage.setItem('wolfee_cache_time', Date.now().toString());

        // Merge new stocks into display
        const currentStocks = window.allStocks || [];
        const newStocks = data.stocks.filter(newStock =>
            !currentStocks.some(existing => existing.symbol === newStock.symbol)
        );

        if (newStocks.length > 0) {
            window.allStocks = [...currentStocks, ...newStocks];
            console.log(`✓ Background load complete: +${newStocks.length} new stocks (Total: ${window.allStocks.length})`);

            // Re-render with new stocks
            const toggle = document.getElementById('region-toggle');
            const isGlobalMode = toggle ? toggle.checked : false;

            // Add new stock cards
            newStocks.forEach(stock => {
                const isStockGlobal = !stock.symbol.endsWith('.IS');
                if ((isGlobalMode && isStockGlobal) || (!isGlobalMode && !isStockGlobal)) {
                    renderStockCard(stock);
                }
            });
        }
    } catch (error) {
        console.error("Background load error:", error);
    }
}

function processData(data) {
    allStocks = data.stocks || [];
    window.allStocks = allStocks; // Make globally accessible for filters

    // Get current region
    const toggle = document.getElementById('region-toggle');
    const isGlobalMode = toggle ? toggle.checked : false;

    const stockGrid = document.getElementById('stock-grid');
    stockGrid.innerHTML = '';

    // Filter by region
    let displayStocks = allStocks.filter(stock => {
        const isStockGlobal = !stock.symbol.endsWith('.IS');
        return isGlobalMode ? isStockGlobal : !isStockGlobal;
    });

    console.log(`Loaded ${allStocks.length} total, showing ${displayStocks.length} for ${isGlobalMode ? 'GLOBAL' : 'TR'}`);

    if (displayStocks.length === 0) {
        stockGrid.innerHTML = '<p style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">Loading stocks...</p>';
        return;
    }

    displayStocks.forEach(stock => {
        renderStockCard(stock);
    });

    // Initialize search
    initSearch();
}

// Search Logic
function initSearch() {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();

        if (!query) {
            searchResults.classList.add('hidden');
            return;
        }

        // Get current region
        const toggle = document.getElementById('region-toggle');
        const isGlobalMode = toggle ? toggle.checked : false;

        // Filter by region AND search query
        const matches = allStocks.filter(stock => {
            const isStockGlobal = !stock.symbol.endsWith('.IS');

            // Region filter
            if (isGlobalMode !== isStockGlobal) return false;

            // Text Filter
            return stock.symbol.toLowerCase().includes(query) ||
                stock.name.toLowerCase().includes(query);
        });

        if (matches.length > 0) {
            searchResults.classList.remove('hidden');
            searchResults.innerHTML = '';
            matches.forEach(stock => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.innerHTML = `
                    <div>
                        <div class="result-symbol">${stock.symbol.replace('.IS', '')}</div>
                        <div class="result-name">${stock.name}</div>
                    </div>
                    <div class="result-price" style="color:${stock.change_pct >= 0 ? '#4ade80' : '#f87171'}">
                        ${stock.currency === 'USD' ? '$' : '₺'}${stock.price.toFixed(2)}
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
}

// Start
init();
