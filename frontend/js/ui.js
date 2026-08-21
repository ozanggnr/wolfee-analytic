function getCurrencySymbol(code) {
    const map = {
        'USD': '$', 'EUR': '\u20ac', 'GBP': '\u00a3', 'TRY': '\u20ba',
        'JPY': '\u00a5', 'CHF': 'CHF', 'CAD': 'CA$', 'AUD': 'A$',
        'HKD': 'HK$', 'SGD': 'S$', 'CNY': '\u00a5', 'KRW': '\u20a9',
        'INR': '\u20b9', 'BRL': 'R$', 'MXN': 'MX$', 'NOK': 'kr',
        'SEK': 'kr', 'DKK': 'kr',
    };
    return map[code] || code || '$';
}

function getSignalStyle(prediction) {
    const p = (prediction || '').toUpperCase();
    if (p.includes('PURCHASABLE')) {
        return {
            color: '#10f5a8',
            bg: 'rgba(16,245,168,0.1)',
            border: 'rgba(16,245,168,0.25)',
            icon: '🟢',
            label: prediction
        };
    }
    if (p.includes('ACCUMULATE')) {
        return {
            color: '#43e6fc',
            bg: 'rgba(67,230,252,0.09)',
            border: 'rgba(67,230,252,0.22)',
            icon: '🔵',
            label: prediction
        };
    }
    if (p.includes('WATCH TO BUY')) {
        return {
            color: '#fbbf24',
            bg: 'rgba(251,191,36,0.09)',
            border: 'rgba(251,191,36,0.22)',
            icon: '🟡',
            label: prediction
        };
    }
    if (p.includes('TAKE PROFITS')) {
        return {
            color: '#c86fff',
            bg: 'rgba(200,111,255,0.1)',
            border: 'rgba(200,111,255,0.25)',
            icon: '🟣',
            label: prediction
        };
    }
    if (p.includes('AVOID')) {
        return {
            color: '#ff4f6e',
            bg: 'rgba(255,79,110,0.09)',
            border: 'rgba(255,79,110,0.22)',
            icon: '🔴',
            label: prediction
        };
    }
    // Fallback: derive from change direction
    const isUp = !p.includes('DECLIN') && !p.includes('DOWN') && !p.includes('LOSS');
    return {
        color: isUp ? '#10f5a8' : '#ff4f6e',
        bg: isUp ? 'rgba(16,245,168,0.08)' : 'rgba(255,79,110,0.08)',
        border: isUp ? 'rgba(16,245,168,0.2)' : 'rgba(255,79,110,0.2)',
        icon: isUp ? '🟢' : '🔴',
        label: prediction || (isUp ? 'Positive momentum' : 'Downward pressure')
    };
}

function renderStockCard(stock) {
    const grid = document.getElementById(stock.inPortfolio ? 'portfolio-grid' : 'stock-grid');
    if (!grid) return;

    const currency = getCurrencySymbol(stock.currency);
    const isUp = (stock.change_pct || 0) >= 0;
    const icon = isUp ? '▲' : '▼';
    const priceColor = isUp ? 'var(--success-color)' : 'var(--danger-color)';
    const sig = getSignalStyle(stock.prediction);

    const card = document.createElement('div');
    card.className = 'stock-card skeleton';

    // Remove skeleton class once data is loaded
    setTimeout(() => card.classList.remove('skeleton'), 100);

    card.innerHTML = `
        <div class="stock-header">
            <div class="symbol-group">
                <span class="stock-symbol">${(stock.symbol||'').replace('.IS', '')}</span>
                <span class="stock-name" title="${stock.name}">${(stock.name || '').substring(0, 22)}${(stock.name || '').length > 22 ? '...' : ''}</span>
            </div>
            <div>
                <div class="stock-price" style="color: ${priceColor}">${(stock.price||0).toFixed(2)} ${currency}</div>
                <div class="price-change" style="color: ${priceColor}">
                    ${icon} ${Math.abs(stock.change_pct||0).toFixed(2)}%
                </div>
            </div>
        </div>
        <div class="stats-grid">
            <div class="stat-item">
                <span>Volume</span>
                <span>${formatNumber(stock.volume)}</span>
            </div>
            <div class="stat-item">
                <span>RSI</span>
                <span style="color: ${getRsiColor(stock.rsi)}">${(stock.rsi||50).toFixed(1)}</span>
            </div>
            <div class="stat-item">
                <span>Trend</span>
                <span style="color: ${priceColor}">${isUp ? 'Bullish' : 'Bearish'}</span>
            </div>
        </div>
        <div class="signal-chip" style="color:${sig.color}; background:${sig.bg}; border-color:${sig.border};">
            ${sig.icon} ${sig.label}
        </div>
    `;

    card.onclick = () => openModal(stock);
    grid.appendChild(card);
}

function renderGoldCards(goldData) {
    let goldSection = document.getElementById('gold-section');
    if (!goldSection) {
        // Create it if it doesn't exist
        goldSection = document.createElement('div');
        goldSection.id = 'gold-section';
        goldSection.className = 'gold-section';
        
        const marketView = document.getElementById('market-view');
        const stockGrid = document.getElementById('stock-grid');
        if (marketView && stockGrid) {
            marketView.insertBefore(goldSection, stockGrid);
        }
    }
    
    if (!goldData || goldData.length === 0) {
        goldSection.innerHTML = '';
        return;
    }
    
    let html = `<h2>🥇 Turkish Gold (TRY)</h2><div class="gold-grid">`;
    goldData.forEach(g => {
        html += `
            <div class="gold-card">
                <div class="gold-name">${g.display_name}</div>
                <div class="gold-price">${(g.selling_price || 0).toFixed(2)} ₺</div>
                <div class="gold-detail">
                    Buy: ${(g.buying_price || 0).toFixed(2)} ₺ 
                    <span style="color:${(g.change_pct||0) >= 0 ? 'var(--success-color)' : 'var(--danger-color)'}; float:right;">
                        ${(g.change_pct||0) >= 0 ? '▲' : '▼'} ${Math.abs(g.change_pct||0).toFixed(2)}%
                    </span>
                </div>
            </div>
        `;
    });
    html += `</div>`;
    goldSection.innerHTML = html;
}

function renderExchangeRates(rates) {
    let header = document.querySelector('header');
    let wrapper = document.getElementById('exchange-ticker-wrapper');
    let ticker = document.getElementById('exchange-ticker');
    
    // Create wrapper + ticker if they don't exist (fallback)
    if (!wrapper) {
        wrapper = document.createElement('div');
        wrapper.id = 'exchange-ticker-wrapper';
        wrapper.className = 'exchange-ticker-wrapper';
        if (header && header.nextSibling) {
            header.parentNode.insertBefore(wrapper, header.nextSibling);
        }
    }
    if (!ticker) {
        ticker = document.createElement('div');
        ticker.id = 'exchange-ticker';
        ticker.className = 'exchange-ticker';
        wrapper.appendChild(ticker);
    }
    
    if (!rates || rates.length === 0) {
        ticker.style.display = 'none';
        return;
    }
    
    ticker.style.display = 'flex';
    let html = '';
    rates.forEach(r => {
        const color = (r.change_pct || 0) >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
        const icon = (r.change_pct || 0) >= 0 ? '▲' : '▼';
        html += `
            <div class="exchange-item" style="cursor: pointer;" onclick="openExchangeModal('${r.pair}', ${r.selling || 0}, ${r.change_pct || 0})">
                <span class="pair">${r.pair}</span>
                <span class="rate">${(r.selling || 0).toFixed(4)}</span>
                <span style="color:${color}; font-size:0.75rem;">${icon} ${Math.abs(r.change_pct||0).toFixed(2)}%</span>
            </div>
        `;
    });
    ticker.innerHTML = html;
}

window.openExchangeModal = function(pair, price, change_pct) {
    const symbol = pair.replace('/', '') + '=X'; // e.g. USDTRY=X
    const stock = {
        symbol: symbol,
        name: pair,
        price: price,
        change_pct: change_pct,
        currency: 'TRY',
        market_type: 'CURRENCY',
        rsi: 50,
        ma_20: price,
        volatility: 'LOW',
        prediction: 'Currency pair tracking',
        reason: 'Currency pair tracking',
        day_low: price * 0.99,
        day_high: price * 1.01,
        open: price,
        previous_close: price,
        volume: 0
    };
    if (typeof openModal === 'function') openModal(stock);
};

function renderOpportunities(opportunities) {
    // Store globally for opportunities page tab
    window._opportunitiesData = opportunities || [];
    
    // Also render on the opportunities page if it's currently visible
    const oppView = document.getElementById('opportunities-view');
    if (oppView && !oppView.classList.contains('hidden')) {
        renderOpportunitiesPage();
    }
}

window.renderOpportunitiesPage = function() {
    const grid = document.getElementById('opportunities-grid');
    if (!grid) return;
    
    const opportunities = window._opportunitiesData || [];
    
    if (!opportunities || opportunities.length === 0) {
        grid.innerHTML = '<p style="color: var(--text-secondary); grid-column: 1/-1; text-align: center;">No clear signals at the moment.</p>';
        return;
    }
    
    grid.innerHTML = '';
    const validOpps = opportunities.filter(stock => stock.price && stock.price > 0);
    validOpps.forEach(stock => {
        const currency = getCurrencySymbol(stock.currency);
        const isUp = (stock.change_pct || 0) >= 0;
        const priceColor = isUp ? 'var(--success-color)' : 'var(--danger-color)';
        const icon = isUp ? '▲' : '▼';
        const sig = getSignalStyle(stock.prediction);
        
        let badges = '';
        if (stock.rsi < 35) badges += '<span class="opp-badge badge-oversold">Oversold</span> ';
        if (stock.change_pct > 2) badges += '<span class="opp-badge badge-trend">Uptrend</span> ';
        if (!badges) badges = '<span class="opp-badge badge-golden">Value Pick</span> ';
        
        const card = document.createElement('div');
        card.className = 'stock-card';
        card.innerHTML = `
            <div class="stock-header">
                <div class="symbol-group">
                    <span class="stock-symbol">${(stock.symbol||'').replace('.IS', '')}</span>
                    <span class="stock-name" title="${stock.name}">${(stock.name || '').substring(0, 22)}${(stock.name || '').length > 22 ? '...' : ''}</span>
                </div>
                <div>
                    <div class="stock-price" style="color: ${priceColor}">${(stock.price||0).toFixed(2)} ${currency}</div>
                    <div class="price-change" style="color: ${priceColor}">
                        ${icon} ${Math.abs(stock.change_pct||0).toFixed(2)}%
                    </div>
                </div>
            </div>
            <div class="stats-grid">
                <div class="stat-item">
                    <span>Volume</span>
                    <span>${formatNumber(stock.volume)}</span>
                </div>
                <div class="stat-item">
                    <span>RSI</span>
                    <span style="color: ${getRsiColor(stock.rsi)}">${(stock.rsi||50).toFixed(1)}</span>
                </div>
                <div class="stat-item">
                    <span>Trend</span>
                    <span style="color: ${priceColor}">${isUp ? 'Bullish' : 'Bearish'}</span>
                </div>
            </div>
            <div style="margin: 5px 0;">${badges}</div>
            <div class="signal-chip" style="color:${sig.color}; background:${sig.bg}; border-color:${sig.border};">
                ${sig.icon} ${sig.label}
            </div>
            <div class="reason-text" style="color:var(--text-secondary); margin-top: 0.5rem; font-size: 0.82rem;">${stock.reason || 'Positive signals detected.'}</div>
        `;
        card.onclick = () => openModal(stock);
        grid.appendChild(card);
    });
}

function openModal(stock) {
    currentSymbol = stock.symbol;
    window.currentModalStock = stock;
    const modal = document.getElementById('stock-modal');
    
    // Add AI button to header
    const title = document.getElementById('modal-title');
    title.innerHTML = `${stock.name || stock.symbol} <span style="font-size:0.8rem;color:var(--text-secondary)">${stock.symbol}</span>`;
    
    const currency = getCurrencySymbol(stock.currency);
    
    // Show cached data immediately for instant modal open
    _applyStockToModal(stock, currency, false);

    // AI Analysis Section Injection
    let aiSection = document.getElementById('ai-analysis-section');
    if (!aiSection) {
        aiSection = document.createElement('div');
        aiSection.id = 'ai-analysis-section';
        aiSection.className = 'ai-analysis-section';
        const chartControls = document.querySelector('.chart-controls');
        if (chartControls) {
            chartControls.parentNode.insertBefore(aiSection, chartControls);
        }
    }
    aiSection.innerHTML = `<button class="ai-analyze-btn" onclick="askWolfeeAI('${stock.symbol}')">🐺 Ask Wolfee AI for Deep Analysis</button>`;

    updatePortfolioButtonUI(stock.symbol);
    modal.classList.remove('hidden');
    document.body.classList.add('no-scroll');

    // Default to 1Y chart
    if (typeof loadChart === 'function') loadChart(stock.symbol, '1y');
    else if (typeof updateChart === 'function') updateChart('1y');

    // Silently fetch live price and update modal fields once it arrives
    _fetchLivePriceForModal(stock.symbol);
}

function _applyStockToModal(stock, currency, isLive) {
    if (!currency) currency = getCurrencySymbol(stock.currency);
    const price = stock.price || 0;
    const day_low = stock.day_low || (price * 0.98);
    const day_high = stock.day_high || (price * 1.02);
    const open_price = stock.open || stock.open_price || (price * 0.99);
    const prev_close = stock.previous_close || (price * 0.99);

    const lastEl = document.getElementById('stat-last');
    if (lastEl) {
        lastEl.textContent = `${price.toFixed(2)} ${currency}`;
        if (isLive) {
            // Flash green to indicate live price just arrived
            lastEl.style.transition = 'color 0.3s';
            lastEl.style.color = 'var(--success-color)';
            setTimeout(() => { lastEl.style.color = ''; }, 1500);
        }
    }

    document.getElementById('stat-symbol').textContent = (stock.symbol||'').replace('.IS', '');
    const bidEl = document.getElementById('stat-bid');
    if (bidEl) bidEl.textContent = stock.bid ? `${stock.bid.toFixed(2)} ${currency}` : `${(price*0.998).toFixed(2)} ${currency}`;
    const askEl = document.getElementById('stat-ask');
    if (askEl) askEl.textContent = stock.ask ? `${stock.ask.toFixed(2)} ${currency}` : `${(price*1.002).toFixed(2)} ${currency}`;

    const changeEl = document.getElementById('stat-change');
    if (changeEl) {
        changeEl.textContent = `${(stock.change_pct||0) >= 0 ? '+' : ''}${(stock.change_pct||0).toFixed(2)}%`;
        changeEl.style.color = (stock.change_pct||0) >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
    }

    const lowEl = document.getElementById('stat-low');
    if (lowEl) lowEl.textContent = `${day_low.toFixed(2)} ${currency}`;
    const highEl = document.getElementById('stat-high');
    if (highEl) highEl.textContent = `${day_high.toFixed(2)} ${currency}`;
    const vwapEl = document.getElementById('stat-vwap');
    if (vwapEl) vwapEl.textContent = `${open_price.toFixed(2)} ${currency}`;
    const volTlEl = document.getElementById('stat-vol-tl');
    if (volTlEl) volTlEl.textContent = `${prev_close.toFixed(2)} ${currency}`;
    const volLotEl = document.getElementById('stat-vol-lot');
    if (volLotEl) volLotEl.textContent = formatNumber(stock.volume || 0);

    const predEl = document.getElementById('modal-prediction');
    if (predEl) {
        predEl.textContent = stock.prediction || 'Stable trend';
        predEl.style.color = (stock.change_pct||0) >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
    }
}

async function _fetchLivePriceForModal(symbol) {
    try {
        const res = await fetch(`${API_URL}/api/live-price/${encodeURIComponent(symbol)}`);
        if (!res.ok) return;
        const liveData = await res.json();
        // Only update if the modal is still showing the same stock
        if (currentSymbol !== symbol) return;
        const currency = getCurrencySymbol(liveData.currency);
        _applyStockToModal(liveData, currency, true);
        // Also update the in-memory cache so portfolio exports use fresh data
        if (window.allStocks) {
            const idx = window.allStocks.findIndex(s => s.symbol === symbol);
            if (idx >= 0) window.allStocks[idx] = { ...window.allStocks[idx], ...liveData };
        }
    } catch (e) {
        // Silent fail — cached data is still shown
    }
}

window.askWolfeeAI = async function(symbol) {
    const aiSection = document.getElementById('ai-analysis-section');
    if (!aiSection) return;
    
    aiSection.innerHTML = `<div class="ai-response"><div class="spinner" style="width:20px;height:20px;border-width:2px;display:inline-block;vertical-align:middle;"></div> <span style="vertical-align:middle;margin-left:10px;">Wolfee AI is analyzing ${symbol.replace('.IS','')}...</span></div>`;
    
    try {
        const res = await fetch(`${API_URL}/api/ai/analyze/${symbol}`);
        if (!res.ok) throw new Error('Analysis failed');
        const data = await res.json();
        let raw = data.analysis || 'Analysis unavailable';
        // Strip residual markdown
        raw = raw
            .replace(/\*\*(.*?)\*\*/g, '$1')
            .replace(/\*(.*?)\*/g, '$1')
            .replace(/#{1,6}\s/g, '')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
        // Highlight section labels like "Decision:", "Risk to watch:" etc.
        raw = raw.replace(/^(Decision|Why this decision|Why someone should buy it|Why to wait|Risk to watch):/gm,
            '<span style="color:var(--accent-color);font-weight:600;">$1:</span>');
        const text = raw.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
        aiSection.innerHTML = `<div class="ai-response">${text}</div>`;
    } catch(e) {
        aiSection.innerHTML = `<div class="ai-response" style="color:var(--danger-color)">Wolfee AI is temporarily offline. Please try again in a moment.</div>`;
    }
}

function getRsiColor(rsi) {
    if (!rsi) return 'var(--text-secondary)';
    if (rsi < 30) return 'var(--success-color)';
    if (rsi > 70) return 'var(--danger-color)';
    return '#fbbf24';
}

function formatNumber(num) {
    if (!num || num === 0) return '0';
    if (num >= 1000000000) return (num / 1000000000).toFixed(2) + 'B';
    if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

window.toggleSidebar = function() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('sidebar-open');
        // Lock body scroll when sidebar is open on mobile
        document.body.classList.toggle('no-scroll', sidebar.classList.contains('sidebar-open'));
    }
}

window.switchTab = function(tab) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    
    // Activate desktop + mobile tab buttons
    const desktopBtn = document.getElementById(`tab-${tab}`);
    const mobileBtn = document.getElementById(`tab-${tab}-m`);
    if (desktopBtn) desktopBtn.classList.add('active');
    if (mobileBtn) mobileBtn.classList.add('active');
    
    // Hide all views
    const marketView = document.getElementById('market-view');
    const portfolioView = document.getElementById('portfolio-view');
    const opportunitiesView = document.getElementById('opportunities-view');
    const aiSection = document.getElementById('ai-section');
    const goldSection = document.getElementById('gold-section');
    const sectionHeader = document.querySelector('.section-header');
    const filterBtn = document.getElementById('filter-toggle-btn');

    if (marketView) marketView.classList.add('hidden');
    if (portfolioView) portfolioView.classList.add('hidden');
    if (opportunitiesView) opportunitiesView.classList.add('hidden');
    if (aiSection) aiSection.classList.add('hidden');
    if (goldSection) goldSection.classList.add('hidden');
    if (sectionHeader) sectionHeader.style.display = 'none';
    if (filterBtn) filterBtn.style.display = 'none';

    if (tab === 'market') {
        if (marketView) marketView.classList.remove('hidden');
        if (aiSection) aiSection.classList.remove('hidden');
        if (goldSection) goldSection.classList.remove('hidden');
        if (sectionHeader) sectionHeader.style.display = '';
        if (filterBtn) filterBtn.style.display = 'block';
    } else if (tab === 'portfolio') {
        if (portfolioView) portfolioView.classList.remove('hidden');
        if (typeof renderPortfolio === 'function') renderPortfolio();
    } else if (tab === 'opportunities') {
        if (opportunitiesView) opportunitiesView.classList.remove('hidden');
        if (typeof renderOpportunitiesPage === 'function') renderOpportunitiesPage();
    }
}

window.openExportModal = function() {
    document.getElementById('export-modal').classList.remove('hidden');
}

window.closeExportModal = function() {
    document.getElementById('export-modal').classList.add('hidden');
}

window.updatePortfolioButtonUI = function(symbol) {
    const btn = document.getElementById('btn-portfolio-action');
    if (!btn) return;
    
    const portfolio = typeof getPortfolio === 'function' ? getPortfolio() : [];
    const inPortfolio = portfolio.some(s => s.symbol === symbol);
    
    if (inPortfolio) {
        btn.textContent = '− Remove from Portfolio';
        btn.style.color = 'var(--danger-color)';
        btn.style.borderColor = 'var(--danger-color)';
    } else {
        btn.textContent = '+ Add to Portfolio';
        btn.style.color = 'var(--accent-color)';
        btn.style.borderColor = 'var(--accent-color)';
    }
}

function closeModalWithAnim() {
    const activeModals = document.querySelectorAll('.modal:not(.hidden)');
    activeModals.forEach(m => {
        const content = m.querySelector('.modal-content');
        if (content) {
            content.style.animation = 'slideUp 0.25s ease-in forwards';
        }
    });
    
    setTimeout(() => {
        activeModals.forEach(m => {
            m.classList.add('hidden');
            const content = m.querySelector('.modal-content');
            if (content) content.style.animation = '';
        });
        document.body.classList.remove('no-scroll');
    }, 240);
}

document.querySelectorAll('.close-modal').forEach(btn => {
    btn.onclick = () => closeModalWithAnim();
});

window.onclick = function(event) {
    const modals = document.querySelectorAll('.modal:not(.hidden)');
    modals.forEach(m => {
        if (event.target === m) {
            closeModalWithAnim();
        }
    });
};

// AI Protocol Collapse/Expand
window.toggleAICollapse = function() {
    const body = document.getElementById('ai-body');
    const chevron = document.getElementById('ai-chevron');
    const header = document.querySelector('.ai-header-toggle');
    if (!body) return;
    const isCollapsed = body.classList.toggle('collapsed');
    if (chevron) chevron.classList.toggle('rotated', isCollapsed);
    if (header) header.setAttribute('aria-expanded', String(!isCollapsed));
};
