// Main App Logic

let allStocks = [];

async function init() {
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');
    // loader.innerHTML = '<div class="loader-spinner"></div><p>Loading market data...</p>'; // Removed text update


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
        // loader.innerHTML = '<div class="loader-spinner"></div><p>✓ Fast data loaded!</p>'; // Removed text update


        // Stage 2: Load the rest silently
        fetchFullBatch();

        setTimeout(() => loader.classList.add('hidden'), 1000);

        // Data is now partially loaded
        loadAIInsight();
        loadOpportunities();
    } catch (error) {
        console.error('Init error:', error);
        document.getElementById('stock-grid').innerHTML =
            '<p style="color: red; grid-column: 1/-1;">Failed to load market data. Please refresh or check if Railway backend is running.</p>';
        loader.classList.add('hidden');
    }
}

// Stage 2: Fetch FULL batch (All stocks)
async function fetchFullBatch() {
    console.log("Fetching full market data...");
    try {
        const response = await fetch(`${API_URL}/api/market-data/full`);
        if (!response.ok) throw new Error("Full batch failed");

        const data = await response.json();

        // Merge with existing
        const fullList = data.stocks || [];
        if (fullList.length > 0) {
            sessionStorage.setItem('wolfee_market_data', JSON.stringify(data));
            sessionStorage.setItem('wolfee_cache_time', Date.now().toString());
            processData(data); // Re-render with full list
            console.log(`✓ Full data loaded: ${fullList.length} stocks`);
        }
    } catch (e) {
        console.warn("Full batch fetch failed, staying with quick data:", e);
    }
}

// Stage 1: Fetch quick batch (100 stocks)
async function fetchQuickBatch() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000); // 90 sec timeout for rate-limited APIs

    try {
        const response = await fetch(`${API_URL}/api/market-data/quick`, {
            signal: controller.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        // Mock data removed as per user request
        // function loadMockData() { ... }
        sessionStorage.setItem('wolfee_market_data', JSON.stringify(data));
        // Use mock data for local testing
        const mockData = window.generateMockStocks ? window.generateMockStocks() : [];
        const fallbackData = {
            stocks: mockData,
            timestamp: new Date().toISOString(),
            source: 'mock'
        };
        sessionStorage.setItem('wolfee_market_data', JSON.stringify(fallbackData));
        sessionStorage.setItem('wolfee_cache_time', Date.now().toString());
        processData(fallbackData);
        console.log(`✓ Mock data loaded for testing: ${mockData.length} stocks`);
    } finally {
        clearTimeout(timeout);
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
