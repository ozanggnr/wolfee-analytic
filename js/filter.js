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

function applyFilters() {
    const priceMin = parseFloat(document.getElementById('filter-price-min')?.value) || 0;
    const priceMax = parseFloat(document.getElementById('filter-price-max')?.value) || Infinity;
    const rsiMin = parseFloat(document.getElementById('filter-rsi-min')?.value) || 0;
    const rsiMax = parseFloat(document.getElementById('filter-rsi-max')?.value) || 100;

    // New parameters
    const changeMin = parseFloat(document.getElementById('filter-change-min')?.value) || -Infinity;
    const changeMax = parseFloat(document.getElementById('filter-change-max')?.value) || Infinity;
    const volMin = parseFloat(document.getElementById('filter-vol-min')?.value) || 0;

    // Get current region from switch
    const toggle = document.getElementById('region-toggle');
    const isGlobalMode = toggle ? toggle.checked : false; // true = GLOBAL

    const stockGrid = document.getElementById('stock-grid');
    if (!stockGrid) return;
    stockGrid.innerHTML = '';

    if (!window.allStocks) return;

    // 1. Filter by Region
    let filtered = window.allStocks.filter(stock => {
        const isStockGlobal = !stock.symbol.endsWith('.IS');

        if (isGlobalMode) {
            return isStockGlobal;
        } else {
            return !isStockGlobal;
        }
    });

    // 2. Filter by Values
    filtered = filtered.filter(stock => {
        // Price
        if (stock.price < priceMin || stock.price > priceMax) return false;
        // RSI
        if (stock.rsi < rsiMin || stock.rsi > rsiMax) return false;
        // Change %
        if (stock.change_pct < changeMin || stock.change_pct > changeMax) return false;
        // Volume
        if (stock.volume < volMin) return false;

        return true;
    });

    // 3. Sort
    if (isGlobalMode) {
        filtered.sort((a, b) => a.symbol.localeCompare(b.symbol));
    } else {
        // Keep default server sort
    }

    if (filtered.length === 0) {
        stockGrid.innerHTML = '<p style="color:var(--text-secondary); text-align:center; grid-column:1/-1;">No stocks match your filters.</p>';
        return;
    }

    filtered.forEach(stock => {
        renderStockCard(stock);
    });

    // Close popover after applying
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
