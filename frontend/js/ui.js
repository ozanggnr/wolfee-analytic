/** Escapes untrusted text before it is placed in innerHTML. */
function esc(value) {
    return window.WolfeeSafe.escapeHTML(value);
}

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

// Opportunity badges (REQ-29): the oversold threshold follows the card label
// table (RSI < 30); the daily-move badge describes today only.
const OVERSOLD_RSI = 30;
const UP_TODAY_BADGE_PCT = 2;

const TREND_TEXT = { up: 'Up today', down: 'Down today', flat: 'Unchanged today' };

/** Base symbol without the BIST suffix, as used for card keys. */
function baseSymbol(stock) {
    return ((stock && stock.symbol) || '').replace('.IS', '').trim().toUpperCase();
}

/**
 * The day's change as a span: green or red only for a real move, neutral and
 * "Not available" when change_pct is null (unknown, not 0).
 */
function changeHTML(record, className, options = {}) {
    const F = window.WolfeeFields;
    const direction = F.changeDirection(record, options.field);
    const classes = [className, F.directionClass(direction), direction === null ? 'not-available' : '']
        .filter(Boolean).join(' ');
    return `<span class="${classes}">${esc(F.formatChange(record, options))}</span>`;
}

function trendHTML(stock) {
    const F = window.WolfeeFields;
    const direction = F.changeDirection(stock);
    if (direction === null) return `<span class="not-available">${esc(F.NOT_AVAILABLE)}</span>`;
    return `<span class="${F.directionClass(direction)}">${TREND_TEXT[direction]}</span>`;
}

/** The descriptive label chip; no chip at all when there is no label. */
function signalChipHTML(stock) {
    const label = window.WolfeeFields.fieldValue(stock, 'prediction');
    return typeof label === 'string' ? `<div class="signal-chip">${esc(label)}</div>` : '';
}

/** RSI value for a card stat cell, with its as-of date when there is one. */
function rsiStatHTML(stock) {
    const F = window.WolfeeFields;
    const rsi = F.indicatorNumber(stock, 'rsi');
    if (rsi === null) {
        return `<span class="not-available">${esc(F.NOT_AVAILABLE)}</span>`;
    }
    const asOf = F.indicatorsAsOf(stock);
    const asOfHTML = asOf ? `<small class="indicator-asof">as of <time datetime="${esc(asOf)}">${esc(asOf)}</time></small>` : '';
    return `<span>${rsi.toFixed(1)}${asOfHTML}</span>`;
}

/**
 * Inner markup of a stock card. Shared by the first render and the in-place
 * update after a poll, so both show the same fields the same way.
 */
function stockCardInnerHTML(stock, extraHTML = '') {
    const F = window.WolfeeFields;
    const name = stock.name || '';
    return `
        <div class="stock-header">
            <div class="symbol-group">
                <span class="stock-symbol">${esc(baseSymbol(stock))}</span>
                <span class="stock-name" title="${esc(name)}">${esc(name)}</span>
            </div>
            <div>
                <div class="stock-price">${esc(F.formatPrice(stock, 'price', getCurrencySymbol(stock.currency)))}</div>
                ${changeHTML(stock, 'price-change')}
            </div>
        </div>
        <div class="stats-grid">
            <div class="stat-item">
                <span>Volume</span>
                <span>${formatNumber(stock.volume)}</span>
            </div>
            <div class="stat-item">
                <span>RSI</span>
                ${rsiStatHTML(stock)}
            </div>
            <div class="stat-item">
                <span>Trend</span>
                ${trendHTML(stock)}
            </div>
        </div>
        ${extraHTML}
        ${signalChipHTML(stock)}
    `;
}

/** A card element that opens the stock detail on click, Enter or Space. */
function createStockCardElement(stock, innerHTML) {
    const card = document.createElement('div');
    card.className = 'stock-card';
    card.setAttribute('data-stock-symbol', baseSymbol(stock));
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.innerHTML = innerHTML;
    card.onclick = () => openModal(stock);
    card.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        openModal(stock);
    });
    return card;
}

function renderStockCard(stock) {
    const grid = document.getElementById(stock.inPortfolio ? 'portfolio-grid' : 'stock-grid');
    if (!grid || !stock) return;

    const baseSym = baseSymbol(stock);
    if (!baseSym) return;

    // Strict DOM guard: NEVER render duplicate card for the same symbol
    if (grid.querySelector(`[data-stock-symbol="${CSS.escape(baseSym)}"]`)) {
        return;
    }

    grid.removeAttribute('aria-busy');
    grid.appendChild(createStockCardElement(stock, stockCardInnerHTML(stock)));
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
    
    const F = window.WolfeeFields;
    let html = `<h2 class="section-title">Turkish gold (TRY)</h2><div class="gold-grid">`;
    goldData.forEach(g => {
        html += `
            <div class="gold-card">
                <div class="gold-name">${esc(g.display_name)}</div>
                <div class="gold-price">${esc(F.formatPrice(g, 'selling_price', '₺'))}</div>
                <div class="gold-detail">
                    <span>Buy ${esc(F.formatPrice(g, 'buying_price', '₺'))}</span>
                    ${changeHTML(g, 'gold-change')}
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
    
    ticker.style.display = '';
    const F = window.WolfeeFields;
    ticker.innerHTML = '';
    rates.forEach(r => {
        const rate = F.numberField(r, 'selling');
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'exchange-item';
        item.innerHTML = `
            <span class="pair">${esc(r.pair)}</span>
            <span class="rate${rate !== null && rate > 0 ? '' : ' not-available'}">${esc(rate !== null && rate > 0 ? rate.toFixed(4) : F.NOT_AVAILABLE)}</span>
            ${changeHTML(r, 'exchange-change')}
        `;
        item.addEventListener('click', () => openExchangeModal(r.pair, rate, F.numberField(r, 'change_pct')));
        ticker.appendChild(item);
    });
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
        // The exchange-rate feed carries none of these; show them as not
        // available rather than estimating them from the rate (REQ-27).
        rsi: null,
        ma_20: null,
        volatility: null,
        prediction: null,
        reason: null,
        day_low: null,
        day_high: null,
        open: null,
        previous_close: null,
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
    
    const rawOpps = window._opportunitiesData || [];
    
    // Strict deduplication by normalized symbol
    const seenOpps = new Set();
    const opportunities = rawOpps.filter(stock => {
        if (!stock || !stock.symbol || !stock.price || stock.price <= 0) return false;
        const symKey = stock.symbol.toUpperCase().replace('.IS', '').trim();
        if (!symKey || seenOpps.has(symKey)) return false;
        seenOpps.add(symKey);
        return true;
    });
    
    if (!opportunities || opportunities.length === 0) {
        grid.innerHTML = '<p class="grid-message">No instruments meet these conditions right now. The list updates with market data.</p>';
        return;
    }

    grid.innerHTML = '';
    opportunities.forEach(stock => {
        const baseSym = baseSymbol(stock);
        if (grid.querySelector(`[data-stock-symbol="${CSS.escape(baseSym)}"]`)) return;
        grid.appendChild(createStockCardElement(stock, stockCardInnerHTML(stock, opportunityExtraHTML(stock))));
    });
}

/**
 * Condition badges and the backend's reason line. Badges come only from
 * available inputs (REQ-27): no RSI, no RSI badge; a null change, no move badge.
 * The reason is left out when missing or when it only repeats the label.
 */
function opportunityExtraHTML(stock) {
    const F = window.WolfeeFields;
    const badges = [];
    const rsi = F.indicatorNumber(stock, 'rsi');
    if (rsi !== null && rsi < OVERSOLD_RSI) badges.push('<span class="opp-badge">RSI below 30</span>');
    const change = F.numberField(stock, 'change_pct');
    if (change !== null && change > UP_TODAY_BADGE_PCT) badges.push(`<span class="opp-badge">Up more than ${UP_TODAY_BADGE_PCT}% today</span>`);

    const reason = F.fieldValue(stock, 'reason');
    const label = F.fieldValue(stock, 'prediction');
    const showReason = typeof reason === 'string' && reason !== label;

    return (badges.length ? `<div class="opp-badges">${badges.join('')}</div>` : '')
        + (showReason ? `<p class="reason-text">${esc(reason)}</p>` : '');
}

function openModal(stock) {
    currentSymbol = stock.symbol;
    window.currentModalStock = stock;
    const modal = document.getElementById('stock-modal');
    
    // Remember what had focus, to return to it when the dialog closes
    _modalReturnFocus = document.activeElement;
    markSelectedCard(stock.symbol);

    const title = document.getElementById('modal-title');
    title.innerHTML = `${esc(stock.name || stock.symbol)} <span class="modal-symbol">${esc(stock.symbol)}</span>`;
    
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
    aiSection.innerHTML = '<button type="button" class="ai-analyze-btn">Ask Wolfee AI for analysis</button>';
    aiSection.querySelector('.ai-analyze-btn').addEventListener('click', () => askWolfeeAI(stock.symbol));

    updatePortfolioButtonUI(stock.symbol);
    modal.classList.remove('hidden');
    modal.scrollTop = 0;
    document.body.classList.add('no-scroll');
    const closeBtn = modal.querySelector('.close-modal');
    if (closeBtn) closeBtn.focus();

    // Default to 1Y chart
    if (typeof loadChart === 'function') loadChart(stock.symbol, '1y');
    else if (typeof updateChart === 'function') updateChart('1y');

    // Silently fetch live price and update modal fields once it arrives
    _fetchLivePriceForModal(stock.symbol);
}

let _modalReturnFocus = null;

/** Highlights the card whose detail is open (tint and accent border). */
function markSelectedCard(symbol) {
    document.querySelectorAll('.stock-card[aria-current="true"]').forEach(card => card.removeAttribute('aria-current'));
    if (!symbol) return;
    const key = baseSymbol({ symbol });
    document.querySelectorAll(`.stock-card[data-stock-symbol="${CSS.escape(key)}"]`)
        .forEach(card => card.setAttribute('aria-current', 'true'));
}

/**
 * A price field as display text. Missing, estimated or zero values (the
 * providers send 0 for bid/ask they do not have) are not available; nothing
 * is derived from the last price.
 */
function _modalPriceText(stock, field, currency) {
    return window.WolfeeFields.formatPrice(stock, field, currency);
}

/** Sets a key figure; "Not available" is set in the text face, not mono. */
function _setModalText(id, text) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.classList.toggle('not-available', text === window.WolfeeFields.NOT_AVAILABLE);
}

function _volatilityText(stock) {
    const F = window.WolfeeFields;
    const level = F.indicatorField(stock, 'volatility');
    const pct = F.indicatorNumber(stock, 'volatility_pct');
    const parts = [];
    if (typeof level === 'string') parts.push(level);
    if (pct !== null) parts.push(`${pct.toFixed(1)}%`);
    return parts.length > 0 ? parts.join(' · ') : F.NOT_AVAILABLE;
}

function _applyIndicatorsToModal(stock, currency) {
    const F = window.WolfeeFields;
    _setModalText('stat-rsi', F.formatIndicatorField(stock, 'rsi', 1));
    _setModalText('stat-ma20', F.formatIndicatorField(stock, 'ma_20', 2, ` ${currency}`));
    _setModalText('stat-volatility', _volatilityText(stock));
    _setModalText('stat-ind-asof', F.indicatorsAsOf(stock) || F.NOT_AVAILABLE);

    const method = F.indicatorField(stock, 'indicator_method');
    const methodEl = document.getElementById('stat-ind-method');
    if (methodEl) {
        methodEl.textContent = typeof method === 'string' ? `Method: ${method}` : '';
        methodEl.classList.toggle('hidden', typeof method !== 'string');
    }
}

function _applyStockToModal(stock, currency, isLive) {
    if (!currency) currency = getCurrencySymbol(stock.currency);
    const F = window.WolfeeFields;

    _setModalText('stat-last', F.formatPrice(stock, 'price', currency));
    const lastEl = document.getElementById('stat-last');
    if (lastEl && isLive) {
        // Brief tint: the live price just arrived
        lastEl.classList.add('is-flash');
        setTimeout(() => lastEl.classList.remove('is-flash'), 1500);
    }

    document.getElementById('stat-symbol').textContent = (stock.symbol||'').replace('.IS', '');
    _setModalText('stat-bid', _modalPriceText(stock, 'bid', currency));
    _setModalText('stat-ask', _modalPriceText(stock, 'ask', currency));

    // A null change_pct (no previous close) is not available, never +0.00%
    _setModalText('stat-change', F.formatChange(stock, { style: 'signed' }));
    const changeEl = document.getElementById('stat-change');
    if (changeEl) {
        const direction = F.changeDirection(stock);
        changeEl.classList.toggle('is-gain', direction === 'up');
        changeEl.classList.toggle('is-loss', direction === 'down');
    }

    _setModalText('stat-low', _modalPriceText(stock, 'day_low', currency));
    _setModalText('stat-high', _modalPriceText(stock, 'day_high', currency));
    _setModalText('stat-vwap', _modalPriceText(
        { ...stock, open: stock.open ?? stock.open_price }, 'open', currency));
    _setModalText('stat-vol-tl', _modalPriceText(stock, 'previous_close', currency));
    _setModalText('stat-vol-lot', formatNumber(stock.volume || 0));
    _applyIndicatorsToModal(stock, currency);

    // Descriptive label: shown when there is one, no badge otherwise
    const predEl = document.getElementById('modal-prediction');
    if (predEl) {
        const prediction = F.fieldValue(stock, 'prediction');
        const hasLabel = typeof prediction === 'string';
        predEl.textContent = hasLabel ? prediction : '';
        predEl.classList.toggle('hidden', !hasLabel);
    }
}

async function _fetchLivePriceForModal(symbol) {
    try {
        const res = await fetch(`${API_URL}/api/live-price/${encodeURIComponent(symbol)}`, { cache: 'no-store' });
        if (!res.ok) return;
        const liveData = await res.json();
        // Only update if the modal is still showing the same stock
        if (currentSymbol !== symbol) return;
        const currency = getCurrencySymbol(liveData.currency);
        _applyStockToModal(liveData, currency, true);
        // Keep currentModalStock in sync for portfolio
        if (window.currentModalStock && window.currentModalStock.symbol === symbol) {
            window.currentModalStock = { ...window.currentModalStock, ...liveData };
        }
        // Also update the in-memory cache so portfolio exports use fresh data
        if (window.allStocks) {
            const idx = window.allStocks.findIndex(s => s.symbol === symbol);
            if (idx >= 0) window.allStocks[idx] = { ...window.allStocks[idx], ...liveData };
        }
    } catch (e) {
        // Silent fail — cached data is still shown
    }
}

const AI_ANALYSIS_LABELS = ['Decision', 'Why this decision', 'Why someone should buy it', 'Why to wait', 'Risk to watch'];

/**
 * Renders an AI response (/api/insight or /api/ai/analyze) into `container`:
 * the text, a provenance line and the disclaimer, which is always shown.
 * Text in the REQ-25 shape is plain and is added as text nodes only; the
 * older shape may contain markdown and goes through the escaping
 * aiTextToHTML. `violations` is never read.
 */
function setAISourceBadge(badge, label) {
    badge.textContent = label || '';
    badge.hidden = !label;
    badge.classList.toggle('is-template', label === 'Template');
    badge.title = label === 'Template' ? 'Written from a fixed template, not by the AI model' : '';
}

/**
 * `sourceBadge`, when given, is an existing element that shows "AI generated"
 * or "Template" (REQ-34 a); otherwise that label goes in the provenance line.
 */
function renderAIResponse(container, data, textField, highlightLabels = [], sourceBadge = null) {
    const F = window.WolfeeFields;
    const info = F.aiProvenance(data, textField);
    const sourceLabel = F.aiSourceLabel(info);

    const body = document.createElement('div');
    body.className = 'ai-response-text';
    if (info.text.trim() === '') {
        body.textContent = 'AI text not available.';
    } else if (info.isPlainText) {
        F.splitLabelledLines(info.text, highlightLabels).forEach((line, index) => {
            if (index > 0) body.appendChild(document.createElement('br'));
            if (line.label) {
                const labelEl = document.createElement('span');
                labelEl.className = 'ai-label';
                labelEl.textContent = `${line.label}:`;
                body.appendChild(labelEl);
            }
            body.appendChild(document.createTextNode(line.text));
        });
    } else {
        body.innerHTML = window.WolfeeSafe.aiTextToHTML(info.text, { highlightLabels });
    }

    const meta = document.createElement('div');
    meta.className = 'ai-meta';
    const metaParts = [];
    if (info.generatedAt) metaParts.push(`Generated ${info.generatedAt}`);
    if (info.inputsAsOf) metaParts.push(`data as of ${info.inputsAsOf}`);
    meta.textContent = metaParts.join(' · ');
    if (sourceBadge) {
        setAISourceBadge(sourceBadge, sourceLabel);
    } else if (sourceLabel) {
        const badge = document.createElement('span');
        badge.className = 'ai-badge';
        setAISourceBadge(badge, sourceLabel);
        meta.appendChild(badge);
    }

    const disclaimer = document.createElement('div');
    disclaimer.className = 'ai-disclaimer';
    disclaimer.textContent = info.disclaimer;

    container.replaceChildren(body, ...(meta.childNodes.length > 0 ? [meta] : []), disclaimer);
}

window.askWolfeeAI = async function(symbol) {
    const aiSection = document.getElementById('ai-analysis-section');
    if (!aiSection) return;
    
    aiSection.innerHTML = `<div class="ai-response is-loading" role="status"><span class="spinner" aria-hidden="true"></span><span>Wolfee AI is analysing ${esc(symbol.replace('.IS',''))}</span></div>`;
    
    try {
        const res = await fetch(`${API_URL}/api/ai/analyze/${encodeURIComponent(symbol)}`);
        if (!res.ok) throw new Error('Analysis failed');
        const data = await res.json();
        const response = document.createElement('div');
        response.className = 'ai-response';
        renderAIResponse(response, data, 'analysis', AI_ANALYSIS_LABELS);
        aiSection.replaceChildren(response);
    } catch(e) {
        aiSection.innerHTML = `<div class="inline-error" role="alert">Wolfee AI could not answer just now. Close this panel and try again in a moment.</div>`;
    }
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
    
    // Helper to safely transition in
    const showWithAnim = (el, displayStyle = null, delay = 0) => {
        if (!el) return;
        el.classList.remove('tab-transition');
        el.classList.remove('hidden');
        if (displayStyle !== null) {
            el.style.display = displayStyle;
        }
        el.style.animationDelay = `${delay}ms`;
        // Force reflow to restart animation
        void el.offsetWidth;
        el.classList.add('tab-transition');
    };

    // Helper to hide
    const hideEl = (el, hideStyle = false) => {
        if (!el) return;
        el.classList.add('hidden');
        if (hideStyle) el.style.display = 'none';
        el.classList.remove('tab-transition');
        el.style.animationDelay = '';
    };

    // Hide all views
    const marketView = document.getElementById('market-view');
    const portfolioView = document.getElementById('portfolio-view');
    const opportunitiesView = document.getElementById('opportunities-view');
    const ledgerView = document.getElementById('ledger-view');
    const aiSection = document.getElementById('ai-section');
    const goldSection = document.getElementById('gold-section');
    const sectionHeader = document.querySelector('.section-header');
    const filterBtn = document.getElementById('filter-toggle-btn');
    const mobileSearchbar = document.getElementById('mobile-searchbar');
    const filterPopover = document.getElementById('filter-popover');

    hideEl(marketView);
    hideEl(portfolioView);
    hideEl(opportunitiesView);
    hideEl(ledgerView);
    hideEl(aiSection);
    hideEl(goldSection);
    hideEl(sectionHeader, true);
    hideEl(mobileSearchbar);
    if (filterPopover) filterPopover.classList.add('hidden');
    if (filterBtn) filterBtn.style.display = 'none';

    if (tab === 'market') {
        showWithAnim(mobileSearchbar, null, 0);
        showWithAnim(sectionHeader, '', 0);
        showWithAnim(aiSection, null, 0);
        showWithAnim(goldSection, null, 0);
        showWithAnim(marketView, null, 0);
        if (filterBtn) filterBtn.style.display = '';
        updateAIShowMore();
    } else if (tab === 'portfolio') {
        showWithAnim(portfolioView, null, 0);
        if (typeof loadPortfolio === 'function') {
            loadPortfolio();
        } else if (typeof renderPortfolio === 'function') {
            renderPortfolio();
        }
    } else if (tab === 'opportunities') {
        showWithAnim(opportunitiesView, null, 0);
        if (typeof renderOpportunitiesPage === 'function') renderOpportunitiesPage();
    } else if (tab === 'ledger') {
        showWithAnim(ledgerView, null, 0);
    }
    // The Portfolio page (js/ledger/ledger-page.js, an ES module) loads its data on this event
    document.dispatchEvent(new CustomEvent('wolfee_tab_changed', { detail: { tab } }));
}

window.openExportModal = function() {
    const modal = document.getElementById('export-modal');
    _modalReturnFocus = document.activeElement;
    const status = document.getElementById('export-status');
    if (status) { status.textContent = ''; status.hidden = true; }
    modal.classList.remove('hidden');
    document.body.classList.add('no-scroll');
    const closeBtn = modal.querySelector('.close-modal');
    if (closeBtn) closeBtn.focus();
}

window.closeExportModal = function() {
    if (!document.getElementById('export-modal').classList.contains('hidden')) closeModalWithAnim();
}

window.updatePortfolioButtonUI = function(symbol) {
    const btn = document.getElementById('btn-portfolio-action');
    if (!btn || !symbol) return;
    
    const cleanSym = symbol.toUpperCase().replace('.IS', '').trim();
    const portfolio = typeof getPortfolio === 'function' ? getPortfolio() : [];
    const inPortfolio = portfolio.some(s => (s.symbol || s.ticker || '').toUpperCase().replace('.IS', '').trim() === cleanSym);
    
    btn.textContent = inPortfolio ? '− Remove from Watchlist' : '+ Add to Watchlist';
    btn.classList.toggle('is-remove', inPortfolio);
}

const MODAL_CLOSE_MS = 150;

function closeModalWithAnim() {
    const activeModals = document.querySelectorAll('.modal:not(.hidden)');
    if (activeModals.length === 0) return;
    activeModals.forEach(m => m.classList.add('is-closing'));

    setTimeout(() => {
        activeModals.forEach(m => {
            m.classList.add('hidden');
            m.classList.remove('is-closing');
        });
        document.body.classList.remove('no-scroll');
        markSelectedCard(null);
        if (_modalReturnFocus && document.contains(_modalReturnFocus)) _modalReturnFocus.focus();
        _modalReturnFocus = null;
    }, MODAL_CLOSE_MS);
}

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.querySelector('.modal:not(.hidden)')) closeModalWithAnim();
});

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
    updateAIShowMore();
};

// ---------- Market insight on small screens ----------
// Below 768px the insight text starts clamped to two lines (CSS) with a
// "Show more" button; the provenance line and the disclaimer stay visible.
const MOBILE_QUERY = window.matchMedia('(max-width: 767px)');

function updateAIShowMore() {
    const card = document.getElementById('ai-section');
    const text = document.querySelector('#ai-text .ai-response-text');
    const btn = document.getElementById('ai-more-btn');
    if (!card || !text || !btn) return;
    const expanded = card.classList.contains('is-expanded');
    const clipped = text.scrollHeight > text.clientHeight + 1;
    btn.hidden = !MOBILE_QUERY.matches || (!expanded && !clipped);
    btn.textContent = expanded ? 'Show less' : 'Show more';
    btn.setAttribute('aria-expanded', String(expanded));
}

window.toggleAIMore = function() {
    const card = document.getElementById('ai-section');
    if (!card) return;
    card.classList.toggle('is-expanded');
    updateAIShowMore();
};

/** Adds the "Show more" button under the insight text rendered in `container`. */
function addAIShowMore(container) {
    const body = container.querySelector('.ai-response-text');
    if (!body) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'ai-more-btn';
    btn.className = 'link-btn ai-more-btn';
    btn.setAttribute('aria-controls', 'ai-text');
    btn.addEventListener('click', window.toggleAIMore);
    body.after(btn);
    updateAIShowMore();
}

MOBILE_QUERY.addEventListener('change', updateAIShowMore);

// ---------- Account (mobile tab bar) ----------
// Signed out: the sign-in dialog. Signed in: a sheet with the email and Log out.
window.openAccount = function() {
    if (!window.currentUser) {
        if (typeof openAuthModal === 'function') openAuthModal('login');
        return;
    }
    const sheet = document.getElementById('account-sheet');
    if (!sheet) return;
    sheet.classList.remove('hidden');
    document.body.classList.add('no-scroll');
    const firstButton = sheet.querySelector('.sheet-panel button');
    if (firstButton) firstButton.focus();
};

window.closeAccountSheet = function() {
    const sheet = document.getElementById('account-sheet');
    if (!sheet || sheet.classList.contains('hidden')) return;
    sheet.classList.add('hidden');
    document.body.classList.remove('no-scroll');
    const tab = document.getElementById('tab-account-m');
    if (tab) tab.focus();
};

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') window.closeAccountSheet();
});
