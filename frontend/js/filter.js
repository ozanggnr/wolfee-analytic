// Filter Logic

function initFilterListeners() {
    // Remove auto-filtering on input - now manual with button
    // const inputs = document.querySelectorAll('.filter-input, .filter-input-small');
    // inputs.forEach(input => {
    //     input.addEventListener('input', applyFilters);
    // });
}

function toggleFilterPopover() {
    const popover = document.getElementById('filter-popover');
    if (popover) {
        popover.classList.toggle('hidden');
    }
}

// Close popover when clicking outside
document.addEventListener('click', (e) => {
    const popover = document.getElementById('filter-popover');
    const btn = document.getElementById('filter-toggle-btn');
    if (!popover || !btn) return;

    if (!popover.contains(e.target) && !btn.contains(e.target) && !popover.classList.contains('hidden')) {
        popover.classList.add('hidden');
    }
});

function getNumVal(id, defaultVal) {
    const el = document.getElementById(id);
    if (!el || !el.value || el.value.trim() === '') return defaultVal;
    const parsed = parseFloat(el.value);
    return isNaN(parsed) ? defaultVal : parsed;
}

window.getFilteredStocks = function(baseStocks, query = '') {
    const priceMin = getNumVal('filter-price-min', 0);
    const priceMax = getNumVal('filter-price-max', Infinity);
    const rsiMin = getNumVal('filter-rsi-min', 0);
    const rsiMax = getNumVal('filter-rsi-max', 100);
    const changeMin = getNumVal('filter-change-min', -Infinity);
    const changeMax = getNumVal('filter-change-max', Infinity);
    const volMin = getNumVal('filter-vol-min', 0);

    const toggle = document.getElementById('region-toggle');
    const isGlobalMode = toggle ? toggle.checked : false;

    return baseStocks.filter(stock => {
        if (!stock.price || stock.price <= 0) return false;

        const sym = stock.symbol || '';
        const isStockGlobal = !sym.endsWith('.IS') && stock.market_type !== 'BIST';
        if (isGlobalMode !== isStockGlobal) return false;

        if (stock.price < priceMin || stock.price > priceMax) return false;
        if (stock.rsi < rsiMin || stock.rsi > rsiMax) return false;
        if (stock.change_pct < changeMin || stock.change_pct > changeMax) return false;
        if (stock.volume < volMin) return false;

        if (query) {
            const lowerQuery = query.toLowerCase().trim();
            if (!sym.toLowerCase().includes(lowerQuery) && !(stock.name || '').toLowerCase().includes(lowerQuery)) {
                return false;
            }
        }

        return true;
    });
};

function applyFilters() {
    const stockGrid = document.getElementById('stock-grid');
    if (!stockGrid) return;
    stockGrid.innerHTML = '';

    if (!window.allStocks) return;

    let filtered = window.getFilteredStocks(window.allStocks);

    const toggle = document.getElementById('region-toggle');
    const isGlobalMode = toggle ? toggle.checked : false;
    
    if (isGlobalMode) {
        filtered.sort((a, b) => (a.symbol||'').localeCompare(b.symbol||''));
    }

    if (filtered.length === 0) {
        stockGrid.innerHTML = '<p style="color:var(--text-secondary); text-align:center; grid-column:1/-1;">No stocks match your filters.</p>';
        return;
    }

    filtered.forEach(stock => {
        renderStockCard(stock);
    });

    const popover = document.getElementById('filter-popover');
    if (popover) popover.classList.add('hidden');
}

function clearFilters() {
    document.getElementById('filter-price-min').value = '';
    document.getElementById('filter-price-max').value = '';
    document.getElementById('filter-rsi-min').value = '';
    document.getElementById('filter-rsi-max').value = '';
    document.getElementById('filter-change-min').value = '';
    document.getElementById('filter-change-max').value = '';
    document.getElementById('filter-vol-min').value = '';

    // Re-render all stocks in current region
    applyFilters();
}

// Toggle Region (Exported for HTML onclick)
window.toggleRegion = function () {
    const toggle = document.getElementById('region-toggle');
    const label = document.getElementById('region-label');

    if (toggle.checked) {
        label.textContent = "GLOBAL";
        label.style.color = "#f472b6"; // Pinkish
    } else {
        label.textContent = "TR";
        label.style.color = "#38bdf8"; // Blue
    }

    applyFilters();

    // Reset search
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.value = '';
        searchInput.dispatchEvent(new Event('input'));
    }
};

// Expose to window for onclick
window.toggleFilterPopover = toggleFilterPopover;
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;
