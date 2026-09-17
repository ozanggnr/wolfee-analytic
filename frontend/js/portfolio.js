// =========================================================================
// WOLFEE ANALYTICS - PORTFOLIO & WATCHLIST LOGIC
// Cloud Watchlist Sync (PostgreSQL) + Session Fallback + 60s Cached Summary
// =========================================================================

let _lastSummaryFetchTime = 0;
let _cachedSummaryData = null;
let _summaryCountdownInterval = null;

// Guest session storage fallback
window.getGuestPortfolio = function() {
    const raw = sessionStorage.getItem('wolfee_portfolio');
    return raw ? JSON.parse(raw) : [];
};

window.saveGuestPortfolio = function(list) {
    sessionStorage.setItem('wolfee_portfolio', JSON.stringify(list));
};

/**
 * Universal portfolio getter: returns current list of stock objects.
 * When logged in, returns cloud-synced items; otherwise returns session items.
 */
window.getPortfolio = function() {
    if (window._cachedCloudWatchlist && window.currentUser) {
        return window._cachedCloudWatchlist;
    }
    return getGuestPortfolio();
};

/**
 * Toggle watchlist item (Add or Remove)
 * Synchronizes with backend /api/watchlist if logged in,
 * or falls back to guest session storage if unauthenticated.
 */
window.togglePortfolioItem = async function(customSymbol = null) {
    const symbolToToggle = customSymbol || currentSymbol;
    if (!symbolToToggle) return;

    const baseSym = symbolToToggle.replace('.IS', '').trim().toUpperCase();

    // 1. Check if user is authenticated
    if (window.currentUser) {
        const currentList = window.getPortfolio();
        const exists = currentList.some(s => (s.symbol || s.ticker || '').toUpperCase().replace('.IS', '') === baseSym);

        try {
            if (exists) {
                // Remove via API
                const res = await (window.authFetch || fetch)(`${API_URL}/api/watchlist/${baseSym}`, {
                    method: 'DELETE'
                });
                if (!res.ok) throw new Error('Failed to remove ticker');
            } else {
                // Add via API
                const isBist = symbolToToggle.endsWith('.IS') || (typeof BIST_SYMBOLS !== 'undefined' && BIST_SYMBOLS.some(b => b.startsWith(baseSym)));
                const market = isBist ? 'BIST100' : 'US';
                const res = await (window.authFetch || fetch)(`${API_URL}/api/watchlist`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ticker: baseSym, market })
                });
                if (!res.ok) throw new Error('Failed to add ticker');
            }

            // Invalidate summary cache and re-fetch
            _lastSummaryFetchTime = 0;
            await loadPortfolio();

            if (typeof updatePortfolioButtonUI === 'function') {
                updatePortfolioButtonUI(symbolToToggle);
            }
            return;
        } catch (err) {
            console.error('Watchlist cloud toggle error:', err);
            // Fall through to guest storage if network fails
        }
    }

    // 2. Guest fallback
    let stock = window.currentModalStock || null;
    if (!stock || stock.symbol !== symbolToToggle) {
        stock = (window.allStocks || []).find(s => (s.symbol || '').toUpperCase().replace('.IS', '') === baseSym);
    }
    if (!stock) {
        stock = {
            symbol: symbolToToggle,
            name: symbolToToggle,
            price: parseFloat(document.getElementById('stat-last')?.textContent) || 0,
            change_pct: parseFloat(document.getElementById('stat-change')?.textContent) || 0,
            currency: symbolToToggle.endsWith('.IS') ? 'TRY' : 'USD'
        };
    }

    let list = getGuestPortfolio();
    const existingIndex = list.findIndex(s => (s.symbol || s.ticker || '').toUpperCase().replace('.IS', '') === baseSym);

    if (existingIndex >= 0) {
        list.splice(existingIndex, 1);
    } else {
        list.push(stock);
    }

    saveGuestPortfolio(list);

    if (typeof updatePortfolioButtonUI === 'function') {
        updatePortfolioButtonUI(symbolToToggle);
    }

    renderPortfolio();
};

/**
 * Add ticker directly from the Portfolio page search/add bar
 */
window.addTickerFromPortfolioInput = async function() {
    const input = document.getElementById('portfolio-add-input');
    if (!input) return;
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;

    input.value = '';
    await togglePortfolioItem(ticker);
};

/**
 * Load portfolio on tab switch or page refresh
 */
window.loadPortfolio = async function() {
    if (window.currentUser) {
        try {
            const res = await (window.authFetch || fetch)(`${API_URL}/api/watchlist`);
            if (res.ok) {
                const data = await res.json();
                window._cachedCloudWatchlist = data.items.map(item => ({
                    symbol: item.market === 'BIST100' ? `${item.ticker}.IS` : item.ticker,
                    ticker: item.ticker,
                    name: item.name || item.ticker,
                    price: item.price || 0,
                    change_pct: item.change_pct || 0,
                    volume: item.volume || 0,
                    day_high: item.day_high || item.price,
                    day_low: item.day_low || item.price,
                    rsi: item.rsi || 50,
                    currency: item.currency,
                    market: item.market,
                    prediction: item.prediction,
                    inPortfolio: true
                }));
            }
        } catch (e) {
            console.warn('Failed to load cloud watchlist, using local:', e);
        }
    }

    await loadPortfolioSummaryCard();
    renderPortfolio();
};

/**
 * Fetch and render the 60-second cached portfolio summary card
 */
window.loadPortfolioSummaryCard = async function(forceRefresh = false) {
    const summaryContainer = document.getElementById('portfolio-summary-card');
    if (!summaryContainer) return;

    const now = Date.now();
    // Check 60-second client TTL
    if (!forceRefresh && _cachedSummaryData && (now - _lastSummaryFetchTime < 60000)) {
        renderSummaryCardUI(_cachedSummaryData);
        return;
    }

    if (window.currentUser) {
        try {
            const url = `${API_URL}/api/watchlist/summary${forceRefresh ? '?force_refresh=true' : ''}`;
            const res = await (window.authFetch || fetch)(url);
            if (res.ok) {
                const data = await res.json();
                _cachedSummaryData = data;
                _lastSummaryFetchTime = now;
                renderSummaryCardUI(data);
                startSummaryCountdown(data.cache_expires_in || 60);
                return;
            }
        } catch (e) {
            console.warn('Summary API fetch error:', e);
        }
    }

    // Fallback: calculate summary client-side from guest portfolio
    const localList = window.getPortfolio();
    const summary = calculateClientSideSummary(localList);
    _cachedSummaryData = summary;
    _lastSummaryFetchTime = now;
    renderSummaryCardUI(summary);
    startSummaryCountdown(60);
};

function calculateClientSideSummary(stocks) {
    let up = 0, down = 0, flat = 0, totalChange = 0;
    let biggest = null, maxAbs = -1;
    const tickerChanges = [];

    stocks.forEach(s => {
        const change = s.change_pct || 0;
        const price = s.price || 0;
        const sym = (s.symbol || s.ticker || '').replace('.IS', '');
        const curr = s.currency || (s.symbol?.endsWith('.IS') ? 'TRY' : 'USD');

        if (change > 0) up++;
        else if (change < 0) down++;
        else flat++;

        totalChange += change;
        const fullSym = s.symbol || (curr === 'TRY' ? `${sym}.IS` : sym);
        tickerChanges.push({ symbol: sym, name: s.name || sym, change_pct: change, price, currency: curr, fullSymbol: fullSym });

        if (Math.abs(change) > maxAbs) {
            maxAbs = Math.abs(change);
            biggest = {
                symbol: sym,
                name: s.name || sym,
                price,
                change_pct: change,
                currency: curr,
                direction: change > 0 ? 'up' : (change < 0 ? 'down' : 'flat')
            };
        }
    });

    const count = stocks.length;
    return {
        total_count: count,
        up_count: up,
        down_count: down,
        flat_count: flat,
        avg_change_pct: count > 0 ? roundNumber(totalChange / count, 2) : 0,
        biggest_mover: biggest,
        ticker_changes: tickerChanges,
        cache_expires_in: 60
    };
}

function roundNumber(num, dec) {
    return Math.round(num * Math.pow(10, dec)) / Math.pow(10, dec);
}

function startSummaryCountdown(initialSeconds) {
    if (_summaryCountdownInterval) clearInterval(_summaryCountdownInterval);
    let secondsLeft = initialSeconds;

    const timerEl = document.getElementById('summary-cache-timer');
    if (timerEl) timerEl.textContent = `${secondsLeft}s`;

    _summaryCountdownInterval = setInterval(() => {
        secondsLeft--;
        const el = document.getElementById('summary-cache-timer');
        if (el) {
            if (secondsLeft > 0) {
                el.textContent = `${secondsLeft}s`;
            } else {
                el.textContent = 'Refreshing...';
                clearInterval(_summaryCountdownInterval);
                loadPortfolioSummaryCard(true);
            }
        } else {
            clearInterval(_summaryCountdownInterval);
        }
    }, 1000);
}

/**
 * Render the Summary Card UI
 */
function renderSummaryCardUI(data) {
    const summaryContainer = document.getElementById('portfolio-summary-card');
    if (!summaryContainer) return;

    if (!data || data.total_count === 0) {
        summaryContainer.innerHTML = `
            <div class="summary-card-glass empty-summary">
                <div class="summary-top-bar">
                    <span class="summary-badge">💼 Watchlist Analytics</span>
                    ${!window.currentUser ? '<button class="summary-login-prompt-btn" onclick="openAuthModal(\'login\')">Sign in to sync watchlist</button>' : ''}
                </div>
                <p style="color: var(--text-secondary); margin: 0.75rem 0 0.5rem;">
                    Add stocks to your watchlist to track daily performance metrics, biggest movers, and market distributions.
                </p>
            </div>
        `;
        return;
    }

    const avgIsUp = data.avg_change_pct >= 0;
    const avgColor = avgIsUp ? 'var(--success-color)' : 'var(--danger-color)';
    const avgIcon = avgIsUp ? '▲' : '▼';

    let moverHTML = '<span style="color:var(--text-muted)">No mover data</span>';
    if (data.biggest_mover) {
        const m = data.biggest_mover;
        const mIsUp = m.change_pct >= 0;
        const mIcon = mIsUp ? '▲' : '▼';
        const mCurr = m.currency === 'TRY' ? '₺' : '$';
        const mFullSym = m.currency === 'TRY' && !m.symbol.endsWith('.IS') ? `${m.symbol}.IS` : m.symbol;
        const escMoverSym = encodeURIComponent(mFullSym);
        const escMoverName = encodeURIComponent(m.name || m.symbol);
        moverHTML = `
            <div class="mover-content" style="cursor: pointer;" onclick="if(typeof openModal === 'function') openModal({symbol:decodeURIComponent('${escMoverSym}'), name:decodeURIComponent('${escMoverName}')})">
                <span class="mover-symbol">${m.symbol}</span>
                <span class="mover-badge ${mIsUp ? 'mover-up' : 'mover-down'}">
                    ${mIcon} ${Math.abs(m.change_pct).toFixed(2)}%
                </span>
                <span class="mover-price">${(m.price || 0).toFixed(2)} ${mCurr}</span>
            </div>
        `;
    }

    // Render individual ticker pills
    const pillsHTML = (data.ticker_changes || []).map(t => {
        const isUp = t.change_pct >= 0;
        const color = isUp ? 'var(--success-color)' : 'var(--danger-color)';
        const icon = isUp ? '▲' : '▼';
        const safeSym = typeof escapeHTML === 'function' ? escapeHTML(t.symbol) : t.symbol;
        const fullSym = t.fullSymbol || (t.currency === 'TRY' && !t.symbol.endsWith('.IS') ? `${t.symbol}.IS` : t.symbol);
        const escSym = encodeURIComponent(fullSym || t.symbol || '');
        const escName = encodeURIComponent(t.name || t.symbol || '');
        return `
            <div class="ticker-pill" onclick="if(typeof openModal === 'function') openModal({symbol:decodeURIComponent('${escSym}'), name:decodeURIComponent('${escName}')})">
                <span class="pill-sym">${safeSym}</span>
                <span class="pill-change" style="color:${color}">${icon} ${Math.abs(t.change_pct).toFixed(1)}%</span>
            </div>
        `;
    }).join('');

    summaryContainer.innerHTML = `
        <div class="summary-card-glass">
            <div class="summary-top-bar">
                <div class="summary-badge-group">
                    <span class="summary-badge">⚡ Watchlist Snapshot</span>
                    <span class="cache-badge">
                        Cached <span id="summary-cache-timer">${data.cache_expires_in || 60}s</span>
                    </span>
                </div>
                <div class="summary-actions">
                    <button class="icon-btn refresh-summary-btn" onclick="loadPortfolioSummaryCard(true)" title="Refresh snapshot">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                    </button>
                    ${!window.currentUser ? '<button class="summary-login-prompt-btn" onclick="openAuthModal(\'login\')">Sign In to Save</button>' : ''}
                </div>
            </div>

            <div class="summary-metrics-grid">
                <!-- 1. Market Distribution: Up vs Down -->
                <div class="summary-metric-card">
                    <span class="sm-label">Daily Distribution</span>
                    <div class="sm-distro">
                        <span class="sm-up-count">🟢 ${data.up_count} Up</span>
                        <span class="sm-down-count">🔴 ${data.down_count} Down</span>
                        ${data.flat_count > 0 ? `<span class="sm-flat-count">⚪ ${data.flat_count} Flat</span>` : ''}
                    </div>
                    <div class="sm-progress-bar">
                        <div class="sm-bar-up" style="width: ${data.total_count ? (data.up_count / data.total_count * 100) : 0}%"></div>
                        <div class="sm-bar-down" style="width: ${data.total_count ? (data.down_count / data.total_count * 100) : 0}%"></div>
                    </div>
                </div>

                <!-- 2. Portfolio Average Daily Move -->
                <div class="summary-metric-card">
                    <span class="sm-label">Watchlist Avg Move</span>
                    <div class="sm-value" style="color: ${avgColor}">
                        ${avgIcon} ${Math.abs(data.avg_change_pct).toFixed(2)}%
                    </div>
                    <span class="sm-sub">${data.total_count} active tickers</span>
                </div>

                <!-- 3. Highlighted Single Biggest Mover -->
                <div class="summary-metric-card mover-highlight-card">
                    <span class="sm-label">🚀 Biggest Mover</span>
                    ${moverHTML}
                </div>
            </div>

            <!-- Ticker Change Quick-Pills -->
            ${pillsHTML ? `
                <div class="ticker-pills-wrapper">
                    <div class="ticker-pills-label">Today's Moves:</div>
                    <div class="ticker-pills-scroll">
                        ${pillsHTML}
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

/**
 * Render Stock Cards in Portfolio Tab Grid
 */
window.renderPortfolio = function() {
    const portfolioGrid = document.getElementById('portfolio-grid');
    const portfolioEmpty = document.getElementById('portfolio-empty');
    if (!portfolioGrid || !portfolioEmpty) return;

    const list = window.getPortfolio();

    portfolioGrid.innerHTML = '';

    if (list.length === 0) {
        portfolioEmpty.classList.remove('hidden');
        return;
    }

    portfolioEmpty.classList.add('hidden');

    list.forEach(stock => {
        stock.inPortfolio = true;
        if (typeof renderStockCard === 'function') {
            renderStockCard(stock);
        }
    });
};
