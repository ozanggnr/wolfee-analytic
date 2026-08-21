// -------------------------------------------------------------------------
// PORTFOLIO LOGIC
// -------------------------------------------------------------------------

window.getPortfolio = function() {
    const raw = sessionStorage.getItem('wolfee_portfolio');
    return raw ? JSON.parse(raw) : [];
}

window.savePortfolio = function(list) {
    sessionStorage.setItem('wolfee_portfolio', JSON.stringify(list));
}

window.togglePortfolioItem = function () {
    if (!currentSymbol) return;

    // Use the modal stock object (always set when modal opens), fallback to allStocks cache
    let stock = window.currentModalStock || null;
    if (!stock || stock.symbol !== currentSymbol) {
        stock = (window.allStocks || []).find(s => s.symbol === currentSymbol);
    }
    if (!stock) {
        // Last resort: build a minimal stock object from the modal DOM
        stock = {
            symbol: currentSymbol,
            name: currentSymbol,
            price: parseFloat(document.getElementById('stat-last')?.textContent) || 0,
            change_pct: parseFloat(document.getElementById('stat-change')?.textContent) || 0,
            currency: 'TRY'
        };
    }

    let list = getPortfolio();
    const existingIndex = list.findIndex(s => s.symbol === currentSymbol);

    if (existingIndex >= 0) {
        // Remove
        list.splice(existingIndex, 1);
    } else {
        // Add
        list.push(stock);
    }

    savePortfolio(list);
    
    // Update the button UI using the newly saved portfolio state
    if (typeof updatePortfolioButtonUI === 'function') {
        updatePortfolioButtonUI(currentSymbol);
    }
    
    // Update the portfolio tab grid if it's currently loaded
    renderPortfolio(); 
}

window.loadPortfolio = function() {
    renderPortfolio();
}

window.renderPortfolio = function() {
    const portfolioGrid = document.getElementById('portfolio-grid');
    const portfolioEmpty = document.getElementById('portfolio-empty');
    if (!portfolioGrid || !portfolioEmpty) return;
    
    const list = getPortfolio();

    portfolioGrid.innerHTML = '';

    if (list.length === 0) {
        portfolioEmpty.classList.remove('hidden');
        return;
    }

    portfolioEmpty.classList.add('hidden');

    list.forEach(stock => {
        // Render it into the portfolio grid using the global render function
        stock.inPortfolio = true;
        if (typeof renderStockCard === 'function') {
            renderStockCard(stock);
        }
    });
}
