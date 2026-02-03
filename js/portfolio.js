// -------------------------------------------------------------------------
// PORTFOLIO LOGIC
// -------------------------------------------------------------------------

function getPortfolio() {
    const raw = sessionStorage.getItem('wolfee_portfolio');
    return raw ? JSON.parse(raw) : [];
}

function savePortfolio(list) {
    sessionStorage.setItem('wolfee_portfolio', JSON.stringify(list));
}

window.togglePortfolioItem = function () {
    if (!currentSymbol) return;

    // Find full stock object from cache (using global allStocks from ui.js context)
    // Note: allStocks needs to be accessible. We'll populate it in ui.js/api.js or make it global in main.js
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
    updatePortfolioButtonUI();
    renderPortfolio(); // Update grid in background
}

function loadPortfolio() {
    renderPortfolio();
}

function renderPortfolio() {
    const portfolioGrid = document.getElementById('portfolio-grid');
    const portfolioEmpty = document.getElementById('portfolio-empty');
    const list = getPortfolio();

    portfolioGrid.innerHTML = '';

    if (list.length === 0) {
        portfolioEmpty.classList.remove('hidden');
        return;
    }

    portfolioEmpty.classList.add('hidden');

    list.forEach(stock => {
        // Reuse render logic but append to portfolio grid
        const card = createStockCardElement(stock);
        portfolioGrid.appendChild(card);
    });
}
