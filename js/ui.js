// UI & DOM Logic

function renderStockCard(stock) { // globalize for init
    const stockGrid = document.getElementById('stock-grid');
    const card = createStockCardElement(stock);
    stockGrid.appendChild(card);
}

function createStockCardElement(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';

    // Determine badge if buyable
    let badgeHtml = '';
    if (stock.is_buyable) {
        badgeHtml = `<div class="prediction-mini">Signal: ${stock.prediction}</div>`;
    }

    // Formatting
    const priceColor = stock.change_pct >= 0 ? '#4ade80' : '#f87171';
    const cleanName = stock.name.replace('.IS', '');

    card.innerHTML = `
        <div class="stock-header">
            <div class="symbol-group">
                <div class="stock-symbol">${stock.symbol.replace('.IS', '')}</div>
                <div class="stock-name">${cleanName}</div>
            </div>
            <div>
                <div class="stock-price">₺${stock.price.toFixed(2)}</div>
                <div class="price-change" style="color: ${priceColor}">
                    ${stock.change_pct > 0 ? '+' : ''}${stock.change_pct}%
                </div>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-item">
                <span>MA(20)</span>
                <span>${stock.ma_20 ? stock.ma_20.toFixed(2) : '-'}</span>
            </div>
            <div class="stat-item">
                <span>RSI</span>
                <span style="color: ${getRsiColor(stock.rsi)}">${stock.rsi || '-'}</span>
            </div>
            <div class="stat-item">
                <span>Vol</span>
                <span>${stock.volatility || 'N/A'}</span>
            </div>
        </div>
        
        ${badgeHtml}
    `;

    card.addEventListener('click', () => openModal(stock));
    return card;
}

function renderOpportunities(opportunities) {
    const opportunitiesList = document.getElementById('opportunities-list');
    opportunitiesList.innerHTML = '';
    if (opportunities.length === 0) {
        opportunitiesList.innerHTML = '<p style="color: grey;">No strong signals right now.</p>';
        return;
    }

    opportunities.forEach(opp => {
        const div = document.createElement('div');
        div.className = 'opportunity-card';

        // Classify badge
        let badgeClass = 'badge-trend';
        let badgeText = 'TREND';
        if (opp.reason.includes('Golden')) { badgeClass = 'badge-golden'; badgeText = 'GOLDEN CROSS'; }
        if (opp.reason.includes('Oversold')) { badgeClass = 'badge-oversold'; badgeText = 'OVERSOLD'; }

        div.innerHTML = `
            <span class="opp-badge ${badgeClass}">${badgeText}</span>
            <div style="display:flex; justify-content:space-between; font-weight:bold; color: #fff;">
                <span>${opp.symbol.replace('.IS', '')}</span>
                <span>₺${opp.price.toFixed(2)}</span>
            </div>
            <div class="reason-text" style="color: #94a3b8; font-size: 0.8rem; margin-top: 5px;">
                ${opp.prediction}
            </div>
        `;
        div.addEventListener('click', () => {
            openModal(opp);
            // Mobile Optimization: Close sidebar if open so modal is visible
            const sidebar = document.getElementById('sidebar');
            if (sidebar.classList.contains('sidebar-open')) {
                toggleSidebar();
            }
        });
        opportunitiesList.appendChild(div);
    });
}

function getRsiColor(rsi) {
    if (rsi > 70) return '#f87171';
    if (rsi < 30) return '#4ade80';
    return '#94a3b8';
}

function openModal(stock) {
    const stockModal = document.getElementById('stock-modal');
    currentSymbol = stock.symbol;
    document.getElementById('modal-title').textContent = stock.name + " (" + stock.symbol.replace('.IS', '') + ")";
    document.getElementById('modal-prediction').textContent = "Analysis: " + stock.prediction;

    // Populate Detailed Stats
    // Map fields. Use - if undefined.
    const f = (val) => val !== undefined && val !== null ? val : '-';

    document.getElementById('stat-symbol').textContent = stock.symbol.replace('.IS', '');
    document.getElementById('stat-last').textContent = f(stock.price);
    document.getElementById('stat-bid').textContent = f(stock.bid);
    document.getElementById('stat-ask').textContent = f(stock.ask);
    document.getElementById('stat-change').textContent = f(stock.change_pct) + '%';
    document.getElementById('stat-change').style.color = stock.change_pct >= 0 ? '#4ade80' : '#f87171';

    document.getElementById('stat-low').textContent = f(stock.day_low || stock.low);
    document.getElementById('stat-high').textContent = f(stock.day_high || stock.high);
    document.getElementById('stat-vwap').textContent = f(stock.vwap);
    document.getElementById('stat-vol-tl').textContent = f(stock.volume_tl); // Check API field name match
    document.getElementById('stat-vol-lot').textContent = f(stock.volume_lot || stock.volume);

    stockModal.classList.remove('hidden');
    loadChart(stock.symbol, '1y'); // Default view

    updatePortfolioButtonUI();
}

function updatePortfolioButtonUI() {
    const btn = document.getElementById('btn-portfolio-action');
    if (!currentSymbol) return;

    const portfolio = getPortfolio();
    const isIn = portfolio.some(s => s.symbol === currentSymbol);

    if (isIn) {
        btn.innerHTML = "❌ Remove";
        btn.style.borderColor = "var(--danger-color)";
        btn.style.color = "var(--danger-color)";
    } else {
        btn.innerHTML = "+ Add to Portfolio";
        btn.style.borderColor = "var(--accent-color)";
        btn.style.color = "var(--accent-color)";
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('sidebar-open');
    document.body.classList.toggle('no-scroll');
}

// Tab Switching
window.switchTab = function (tab) {
    // Buttons
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');

    // Views
    const marketView = document.getElementById('market-view');
    const portfolioView = document.getElementById('portfolio-view');
    const aiSection = document.getElementById('ai-section');

    if (tab === 'market') {
        marketView.classList.remove('hidden');
        portfolioView.classList.add('hidden');
        // Show AI Section if switching back
        if (aiSection) aiSection.classList.remove('slide-up-hide');
    } else {
        marketView.classList.add('hidden');
        portfolioView.classList.remove('hidden');
        renderPortfolio(); // Refresh view

        // Hide AI Section with animation
        if (aiSection && !aiSection.classList.contains('hidden')) {
            aiSection.classList.add('slide-up-hide');
        }
    }
}

// Export Modal
const exportModal = document.getElementById('export-modal');
function openExportModal() { exportModal.classList.remove('hidden'); }
function closeExportModal() { exportModal.classList.add('hidden'); }
window.addEventListener('click', (e) => {
    if (e.target == exportModal) closeExportModal();
    const stockModal = document.getElementById('stock-modal');
    if (e.target == stockModal) stockModal.classList.add('hidden');
});
const stockCloseBtn = document.querySelector('#stock-modal .close-modal');
if (stockCloseBtn) stockCloseBtn.onclick = () => document.getElementById('stock-modal').classList.add('hidden');
