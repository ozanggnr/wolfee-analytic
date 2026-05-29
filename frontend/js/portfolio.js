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

    // Find full stock object from cache
    const stock = window.allStocks.find(s => s.symbol === currentSymbol);
    if (!stock) return;

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
