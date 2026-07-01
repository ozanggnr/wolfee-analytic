

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
    // check cache
    const cachedOpps = sessionStorage.getItem('wolfee_opportunities');
    if (cachedOpps) {
        renderOpportunities(JSON.parse(cachedOpps));
        return;
    }

    try {
        const res = await fetch(`${API_URL}/opportunities`);
        const data = await res.json();
        renderOpportunities(data.opportunities);
        sessionStorage.setItem('wolfee_opportunities', JSON.stringify(data.opportunities));
    } catch (e) { console.error(e); }
}

async function triggerExport(period) {
    const btnContent = document.querySelector(`.export-card[onclick="triggerExport('${period}')"]`);
    const originalHTML = btnContent ? btnContent.innerHTML : '';
    if (btnContent) btnContent.innerHTML = '<div class="export-icon">⏳</div><div class="export-info"><h3>Exporting...</h3></div>';

    try {
        // Check if we're on Portfolio tab
        const portfolioView = document.getElementById('portfolio-view');
        const isPortfolioActive = portfolioView && !portfolioView.classList.contains('hidden');

        let response;

        if (isPortfolioActive) {
            // Export only portfolio stocks — send full stock objects via POST
            const portfolio = typeof getPortfolio === 'function' ? getPortfolio() : [];
            if (portfolio.length === 0) {
                alert('Your portfolio is empty! Add some stocks first.');
                if (btnContent) btnContent.innerHTML = originalHTML;
                return;
            }

            response = await fetch(`${API_URL}/api/export/portfolio`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ period, stocks: portfolio })
            });
        } else {
            response = await fetch(`${API_URL}/api/export/${period}`);
        }

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
