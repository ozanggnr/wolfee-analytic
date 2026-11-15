// =========================================================================
// WOLFEE ANALYTICS - PORTFOLIO & WATCHLIST LOGIC
// Cloud Watchlist Sync (PostgreSQL) + Session Fallback + 60s Cached Summary
// =========================================================================

let _lastSummaryFetchTime = 0;
let _cachedSummaryData = null;
let _summaryCountdownInterval = null;

// Persistent guest storage fallback (localStorage so items survive closing browser)
window.getGuestPortfolio = function() {
    try {
        const raw = localStorage.getItem('wolfee_guest_portfolio') || sessionStorage.getItem('wolfee_portfolio');
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
};

window.saveGuestPortfolio = function(list) {
    try {
        localStorage.setItem('wolfee_guest_portfolio', JSON.stringify(list));
    } catch (e) {}
};

// Immediately restore cached cloud watchlist from localStorage for zero-latency rendering
try {
    const rawCloud = localStorage.getItem('wolfee_cached_watchlist');
    if (rawCloud) {
        window._cachedCloudWatchlist = JSON.parse(rawCloud);
    }
} catch (e) {
    window._cachedCloudWatchlist = null;
}

/**
 * Universal portfolio getter: returns current list of stock objects.
 * When logged in, returns cloud-synced items; otherwise returns guest items.
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
    if (!window.WolfeeSafe.isValidSymbol(symbolToToggle)) return;

    const baseSym = symbolToToggle.replace('.IS', '').trim().toUpperCase();

    // 1. Check if user is authenticated
    if (window.currentUser) {
        const currentList = window.getPortfolio();
        const exists = currentList.some(s => (s.symbol || s.ticker || '').toUpperCase().replace('.IS', '') === baseSym);

        try {
            if (exists) {
                // Remove via API
                const res = await (window.authFetch || fetch)(`${API_URL}/api/watchlist/${encodeURIComponent(baseSym)}`, {
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
        // Figures read back from the open detail; "Not available" stays null
        const shownNumber = (id) => {
            const value = parseFloat(document.getElementById(id)?.textContent);
            return Number.isFinite(value) ? value : null;
        };
        stock = {
            symbol: symbolToToggle,
            name: symbolToToggle,
            price: shownNumber('stat-last'),
            change_pct: shownNumber('stat-change'),
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

    if (!window.WolfeeSafe.isValidSymbol(ticker)) {
        input.setCustomValidity('Enter a valid ticker, for example THYAO, NVDA or GC=F.');
        input.reportValidity();
        return;
    }
    input.setCustomValidity('');

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
                // Indicator fields pass through as sent: null stays null and
                // renders as "Not available" (REQ-27); nothing is filled in.
                window._cachedCloudWatchlist = data.items.map(item => ({
                    ...item,
                    symbol: item.market === 'BIST100' ? `${item.ticker}.IS` : item.ticker,
                    ticker: item.ticker,
                    name: item.name || item.ticker,
                    price: item.price || 0,
                    // null when there is no previous close: shown as "Not available"
                    change_pct: item.change_pct ?? null,
                    volume: item.volume || 0,
                    inPortfolio: true
                }));
                try {
                    localStorage.setItem('wolfee_cached_watchlist', JSON.stringify(window._cachedCloudWatchlist));
                } catch (e) {}
            }
        } catch (e) {
            console.warn('Failed to load cloud watchlist, using local cache:', e);
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
    // Check in-memory 60-second client TTL
    if (!forceRefresh && _cachedSummaryData && (now - _lastSummaryFetchTime < 60000)) {
        renderSummaryCardUI(_cachedSummaryData);
        return;
    }

    // Check localStorage cache for initial instant render
    if (!_cachedSummaryData && !forceRefresh) {
        try {
            const rawSummary = localStorage.getItem('wolfee_cached_summary');
            if (rawSummary) {
                _cachedSummaryData = JSON.parse(rawSummary);
                renderSummaryCardUI(_cachedSummaryData);
            }
        } catch (e) {}
    }

    if (window.currentUser) {
        try {
            const url = `${API_URL}/api/watchlist/summary${forceRefresh ? '?force_refresh=true' : ''}`;
            const res = await (window.authFetch || fetch)(url);
            if (res.ok) {
                const data = await res.json();
                _cachedSummaryData = data;
                _lastSummaryFetchTime = now;
                try {
                    localStorage.setItem('wolfee_cached_summary', JSON.stringify(data));
                } catch (e) {}
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
    const tickerChanges = (stocks || []).map(s => {
        const sym = (s.symbol || s.ticker || '').replace('.IS', '');
        const curr = s.currency || (s.symbol?.endsWith('.IS') ? 'TRY' : 'USD');
        return {
            symbol: sym,
            name: s.name || sym,
            change_pct: window.WolfeeFields.numberField(s, 'change_pct'),
            price: window.WolfeeFields.numberField(s, 'price'),
            currency: curr,
            fullSymbol: s.symbol || (curr === 'TRY' ? `${sym}.IS` : sym)
        };
    });
    // A null change is unknown: not flat, not in the average, never the mover
    const counts = window.WolfeeFields.summarizeChanges(tickerChanges);
    return {
        total_count: tickerChanges.length,
        ...counts,
        ticker_changes: tickerChanges,
        cache_expires_in: 60
    };
}

/**
 * Encodes a value for use inside decodeURIComponent('...') in an inline
 * handler. encodeURIComponent leaves the apostrophe alone, which would end
 * the string literal.
 */
function encodeHandlerArg(value) {
    return encodeURIComponent(value).replace(/'/g, '%27');
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
                el.textContent = 'now';
                clearInterval(_summaryCountdownInterval);
                loadPortfolioSummaryCard(true);
            }
        } else {
            clearInterval(_summaryCountdownInterval);
        }
    }, 1000);
}

/** Opens the detail for a summary entry (symbol and name passed encoded). */
function summaryOpenHandler(entry) {
    const fullSym = entry.fullSymbol || (entry.currency === 'TRY' && !String(entry.symbol).endsWith('.IS') ? `${entry.symbol}.IS` : entry.symbol);
    const escSym = encodeHandlerArg(fullSym || entry.symbol || '');
    const escName = encodeHandlerArg(entry.name || entry.symbol || '');
    return `if(typeof openModal === 'function') openModal({symbol:decodeURIComponent('${escSym}'), name:decodeURIComponent('${escName}')})`;
}

function summarySignInHTML(label) {
    return window.currentUser ? '' : `<button type="button" class="link-btn" onclick="openAuthModal('login')">${esc(label)}</button>`;
}

/**
 * Render the Summary Card UI
 */
function renderSummaryCardUI(data) {
    const summaryContainer = document.getElementById('portfolio-summary-card');
    if (!summaryContainer) return;
    const F = window.WolfeeFields;

    if (!data || data.total_count === 0) {
        summaryContainer.innerHTML = `
            <section class="panel watchlist-summary is-empty" aria-labelledby="summary-title">
                <div class="summary-head">
                    <h2 class="section-title" id="summary-title">Watchlist summary</h2>
                    ${summarySignInHTML('Sign in to sync your watchlist')}
                </div>
                <p class="summary-note">Add instruments to see how many moved up or down today, the average move and the biggest move.</p>
            </section>
        `;
        return;
    }

    const unknownCount = Number(data.unknown_count) || 0;
    const total = data.total_count || 0;
    const share = (count) => (total ? (count / total) * 100 : 0).toFixed(1);

    let moverHTML = `<span class="not-available">${esc(F.NOT_AVAILABLE)}</span>`;
    if (data.biggest_mover) {
        const m = data.biggest_mover;
        const mCurr = m.currency === 'TRY' ? '₺' : '$';
        moverHTML = `
            <button type="button" class="mover-btn" onclick="${summaryOpenHandler(m)}">
                <span class="mover-symbol">${esc(m.symbol)}</span>
                ${changeHTML(m, 'mover-change')}
                <span class="mover-price">${esc(F.formatPrice(m, 'price', mCurr))}</span>
            </button>
        `;
    }

    const pillsHTML = (data.ticker_changes || []).map(t => `
        <button type="button" class="ticker-pill" onclick="${summaryOpenHandler(t)}">
            <span class="pill-sym">${esc(t.symbol)}</span>
            ${changeHTML(t, 'pill-change', { digits: 1 })}
        </button>
    `).join('');

    summaryContainer.innerHTML = `
        <section class="panel watchlist-summary" aria-labelledby="summary-title">
            <div class="summary-head">
                <h2 class="section-title" id="summary-title">Watchlist summary</h2>
                <div class="summary-actions">
                    <span class="summary-cache">Refreshes in <span id="summary-cache-timer">${data.cache_expires_in || 60}s</span></span>
                    <button type="button" class="icon-btn" onclick="loadPortfolioSummaryCard(true)" aria-label="Refresh summary" title="Refresh summary">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/></svg>
                    </button>
                    ${summarySignInHTML('Sign in to save')}
                </div>
            </div>

            <div class="summary-metrics">
                <div class="summary-metric">
                    <span class="sm-label">Instruments</span>
                    <span class="kpi-value">${total}</span>
                </div>
                <div class="summary-metric">
                    <span class="sm-label">Today</span>
                    <div class="sm-distro">
                        <span class="is-gain">${data.up_count} up</span>
                        <span class="is-loss">${data.down_count} down</span>
                        ${data.flat_count > 0 ? `<span>${data.flat_count} unchanged</span>` : ''}
                        ${unknownCount > 0 ? `<span class="not-available">${unknownCount} not available</span>` : ''}
                    </div>
                    <div class="sm-bar" aria-hidden="true">
                        <span class="sm-bar-up" style="width: ${share(data.up_count)}%"></span>
                        <span class="sm-bar-down" style="width: ${share(data.down_count)}%"></span>
                    </div>
                </div>
                <div class="summary-metric">
                    <span class="sm-label">Average move today</span>
                    <span class="kpi-value${F.numberField(data, 'avg_change_pct') === null ? ' not-available' : ''}">${esc(F.formatChange(data, { field: 'avg_change_pct', style: 'signed' }))}</span>
                </div>
                <div class="summary-metric">
                    <span class="sm-label">Biggest move</span>
                    ${moverHTML}
                </div>
            </div>

            ${pillsHTML ? `
                <div class="ticker-pills">
                    <span class="sm-label">Today's moves</span>
                    <div class="ticker-pills-scroll">${pillsHTML}</div>
                </div>
            ` : ''}
        </section>
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
