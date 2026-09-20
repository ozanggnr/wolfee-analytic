

async function fetchAndCache() {
    try {
        const response = await fetch(`${API_URL}/stocks`);
        const data = await response.json();

        // If backend returned 0 stocks, use client-side Yahoo Finance
        if (!data.stocks || data.stocks.length === 0) {
            console.warn('⚠️ Backend returned 0 stocks, fetching from browser...');
            const browserData = await fetchAllStocksFromBrowser();
            const fallbackData = {
                stocks: browserData,
                timestamp: new Date().toISOString(),
                source: 'browser'
            };
            sessionStorage.setItem('wolfee_market_data', JSON.stringify(fallbackData));
            processData(fallbackData);
            return;
        }

        // Backend has data, use it
        sessionStorage.setItem('wolfee_market_data', JSON.stringify(data));
        processData(data);
    } catch (error) {
        console.error('Backend fetch failed, using client-side fallback:', error);
        // Backend is down, use client-side
        const browserData = await fetchAllStocksFromBrowser();
        const fallbackData = {
            stocks: browserData,
            timestamp: new Date().toISOString(),
            source: 'browser'
        };
        sessionStorage.setItem('wolfee_market_data', JSON.stringify(fallbackData));
        processData(fallbackData);
    }
}

async function fetchStockData(symbol) {
    try {
        const response = await fetch(`${API_URL}/analyze/${symbol}`);
        if (!response.ok) return null;
        return await response.json();
    } catch (e) { return null; }
}

async function loadAIInsight() {
    const aiSection = document.getElementById('ai-section');
    aiSection.classList.remove('hidden');

    // check cache
    const cachedInsight = sessionStorage.getItem('wolfee_ai_insight');
    if (cachedInsight) {
        document.getElementById('ai-text').innerHTML = cachedInsight;
        return;
    }

    try {
        const res = await fetch(`${API_URL}/insight`);
        const data = await res.json();
        // Convert \n to <br> for HTML display
        const text = data.insight.replace(/\n/g, '<br>');
        document.getElementById('ai-text').innerHTML = text;
        sessionStorage.setItem('wolfee_ai_insight', text);
    } catch (e) {
        document.getElementById('ai-text').innerText = "AI Protocol Offline.";
    }
}

async function loadOpportunities() {
    try {
        const res = await fetch(`${API_URL}/opportunities`);
        const data = await res.json();
        renderOpportunities(data.opportunities);
    } catch (e) { console.error(e); }
}

// Refresh Button Logic
window.refreshMarket = function () {
    // Clear ALL cache keys
    sessionStorage.removeItem('wolfee_market_data');
    sessionStorage.removeItem('wolfee_ai_insight');
    sessionStorage.removeItem('wolfee_opportunities');

    // Show loader
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');
    // Re-init
    init();
}
