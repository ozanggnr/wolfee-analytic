function renderStockCard(stock) {
    const grid = document.getElementById(stock.inPortfolio ? 'portfolio-grid' : 'stock-grid');
    if (!grid) return;

    const currency = stock.currency === 'USD' ? '$' : '₺';
    const isUp = (stock.change_pct || 0) >= 0;
    const colorClass = isUp ? 'text-success' : 'text-danger';
    const icon = isUp ? '▲' : '▼';
    const priceColor = isUp ? 'var(--success-color)' : 'var(--danger-color)';

    const card = document.createElement('div');
    card.className = 'stock-card skeleton';
    
    // Remove skeleton class once image/data is loaded (simulated)
    setTimeout(() => card.classList.remove('skeleton'), 100);

    card.innerHTML = `
        <div class="stock-header">
            <div class="symbol-group">
                <span class="stock-symbol">${(stock.symbol||'').replace('.IS', '')}</span>
                <span class="stock-name" title="${stock.name}">${(stock.name || '').substring(0, 20)}${(stock.name || '').length > 20 ? '...' : ''}</span>
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
                <span>${(stock.change_pct||0) > 0 ? 'Bullish' : 'Bearish'}</span>
            </div>
        </div>
        <div class="prediction-mini" style="color: ${isUp ? 'var(--success-color)' : 'var(--danger-color)'}; background: ${isUp ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)'}">
            ${stock.prediction || (isUp ? 'Positive momentum' : 'Downward pressure')}
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
    let ticker = document.getElementById('exchange-ticker');
    
    if (!ticker) {
        ticker = document.createElement('div');
        ticker.id = 'exchange-ticker';
        ticker.className = 'exchange-ticker';
        if (header && header.nextSibling) {
            header.parentNode.insertBefore(ticker, header.nextSibling);
        }
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
    const list = document.getElementById('opportunities-list');
    if (!list) return;
    
    if (!opportunities || opportunities.length === 0) {
        list.innerHTML = '<p style="color: var(--text-secondary);">No clear signals at the moment.</p>';
        return;
    }
    
    list.innerHTML = '';
    const validOpps = opportunities.filter(stock => stock.price && stock.price > 0);
    validOpps.slice(0, 8).forEach(stock => {
        const div = document.createElement('div');
        div.className = 'opportunity-card';
        
        let badges = '';
        if (stock.rsi < 35) badges += '<span class="opp-badge badge-oversold">Oversold</span> ';
        if (stock.change_pct > 2) badges += '<span class="opp-badge badge-trend">Uptrend</span> ';
        if (!badges) badges = '<span class="opp-badge badge-golden">Value Pick</span> ';
        
        const currency = stock.currency === 'USD' ? '$' : '₺';
        
        div.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; color:var(--text-primary);">${(stock.symbol||'').replace('.IS','')}</span>
                <span style="color:var(--success-color); font-weight:600;">${(stock.price||0).toFixed(2)} ${currency}</span>
            </div>
            <div style="margin: 5px 0;">${badges}</div>
            <div class="reason-text" style="color:var(--text-secondary);">${stock.reason || 'Positive signals detected.'}</div>
        `;
        div.onclick = () => {
            toggleSidebar();
            openModal(stock);
        };
        list.appendChild(div);
    });
}

function openModal(stock) {
    currentSymbol = stock.symbol;
    const modal = document.getElementById('stock-modal');
    
    // Add AI button to header
    const title = document.getElementById('modal-title');
    title.innerHTML = `${stock.name || stock.symbol} <span style="font-size:0.8rem;color:var(--text-secondary)">${stock.symbol}</span>`;
    
    const currency = stock.currency === 'USD' ? '$' : '₺';
    
    // Ensure no empty fields by estimating if needed
    const price = stock.price || 0;
    const day_low = stock.day_low || (price * 0.98);
    const day_high = stock.day_high || (price * 1.02);
    const open_price = stock.open || (price * 0.99);
    const prev_close = stock.previous_close || (price * 0.99);
    
    document.getElementById('stat-symbol').textContent = (stock.symbol||'').replace('.IS', '');
    document.getElementById('stat-last').textContent = `${price.toFixed(2)} ${currency}`;
    document.getElementById('stat-bid').textContent = stock.bid ? `${stock.bid.toFixed(2)} ${currency}` : `${(price*0.998).toFixed(2)} ${currency}`;
    document.getElementById('stat-ask').textContent = stock.ask ? `${stock.ask.toFixed(2)} ${currency}` : `${(price*1.002).toFixed(2)} ${currency}`;
    
    const changeEl = document.getElementById('stat-change');
    changeEl.textContent = `${(stock.change_pct||0) >= 0 ? '+' : ''}${(stock.change_pct||0).toFixed(2)}%`;
    changeEl.style.color = (stock.change_pct||0) >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
    
    document.getElementById('stat-low').textContent = `${day_low.toFixed(2)} ${currency}`;
    document.getElementById('stat-high').textContent = `${day_high.toFixed(2)} ${currency}`;
    document.getElementById('stat-vwap').textContent = `${open_price.toFixed(2)} ${currency}`;
    document.getElementById('stat-vol-tl').textContent = `${prev_close.toFixed(2)} ${currency}`;
    document.getElementById('stat-vol-lot').textContent = formatNumber(stock.volume || 0);

    const predEl = document.getElementById('modal-prediction');
    if (predEl) {
        predEl.textContent = stock.prediction || 'Stable trend';
        predEl.style.color = (stock.change_pct||0) >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
    }

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
    if (sidebar) sidebar.classList.toggle('active');
}

window.switchTab = function(tab) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    
    if (tab === 'market') {
        document.getElementById('market-view').classList.remove('hidden');
        document.getElementById('portfolio-view').classList.add('hidden');
        const aiSection = document.getElementById('ai-section');
        if (aiSection) aiSection.classList.remove('hidden');
        const goldSection = document.getElementById('gold-section');
        if (goldSection) goldSection.classList.remove('hidden');
        
        const filterBtn = document.getElementById('filter-toggle-btn');
        if (filterBtn) filterBtn.style.display = 'block';
    } else {
        document.getElementById('market-view').classList.add('hidden');
        document.getElementById('portfolio-view').classList.remove('hidden');
        const aiSection = document.getElementById('ai-section');
        if (aiSection) aiSection.classList.add('hidden');
        const goldSection = document.getElementById('gold-section');
        if (goldSection) goldSection.classList.add('hidden');
        
        const filterBtn = document.getElementById('filter-toggle-btn');
        if (filterBtn) filterBtn.style.display = 'none';
        
        if (typeof renderPortfolio === 'function') renderPortfolio();
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
