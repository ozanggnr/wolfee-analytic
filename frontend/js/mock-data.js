// Mock stock data for local testing (Yahoo Finance blocks CORS)

function generateMockStocks() {
    const turkishStocks = [
        { symbol: "AKBNK.IS", name: "Akbank", basePrice: 52.50 },
        { symbol: "GARAN.IS", name: "Garanti BBVA", basePrice: 110.20 },
        { symbol: "HALKB.IS", name: "Halkbank", basePrice: 17.85 },
        { symbol: "ISCTR.IS", name: "İş Bankası", basePrice: 9.45 },
        { symbol: "YKBNK.IS", name: "Yapı Kredi", basePrice: 28.90 },
        { symbol: "THYAO.IS", name: "Türk Hava Yolları", basePrice: 285.50 },
        { symbol: "SAHOL.IS", name: "Sabancı Holding", basePrice: 75.30 },
        { symbol: "EREGL.IS", name: "Ereğli Demir Çelik", basePrice: 48.20 },
        { symbol: "TUPRS.IS", name: "Tüpraş", basePrice: 142.80 },
        { symbol: "KCHOL.IS", name: "Koç Holding", basePrice: 185.40 }
    ];

    const usStocks = [
        { symbol: "AAPL", name: "Apple Inc.", basePrice: 189.50 },
        { symbol: "MSFT", name: "Microsoft Corporation", basePrice: 415.30 },
        { symbol: "GOOGL", name: "Alphabet Inc.", basePrice: 142.80 },
        { symbol: "AMZN", name: "Amazon.com Inc.", basePrice: 178.25 },
        { symbol: "NVDA", name: "NVIDIA Corporation", basePrice: 722.40 },
        { symbol: "TSLA", name: "Tesla, Inc.", basePrice: 248.50 },
        { symbol: "META", name: "Meta Platforms Inc.", basePrice: 468.90 },
        { symbol: "JPM", name: "JPMorgan Chase & Co.", basePrice: 192.30 },
        { symbol: "V", name: "Visa Inc.", basePrice: 282.70 },
        { symbol: "WMT", name: "Walmart Inc.", basePrice: 64.85 }
    ];

    const allSymbols = [...turkishStocks, ...usStocks];
    const mockStocks = [];

    allSymbols.forEach(stock => {
        const changePercent = (Math.random() * 10 - 5); // -5% to +5%
        const price = stock.basePrice * (1 + changePercent / 100);
        const volume = Math.floor(Math.random() * 50000000) + 1000000;
        const rsi = Math.floor(Math.random() * 60) + 20; // 20-80
        const ma20 = price * (1 + (Math.random() * 0.1 - 0.05));

        mockStocks.push({
            symbol: stock.symbol,
            name: stock.name,
            price: parseFloat(price.toFixed(2)),
            change_pct: parseFloat(changePercent.toFixed(2)),
            currency: stock.symbol.endsWith('.IS') ? 'TRY' : 'USD',
            market_cap: Math.floor(Math.random() * 100000000000),
            volume: volume,
            rsi: rsi,
            ma_20: parseFloat(ma20.toFixed(2)),
            prediction: changePercent > 2 ? "Strong upward trend" : changePercent > 0 ? "Positive momentum" : "Neutral",
            reason: changePercent > 2 ? "Strong momentum" : changePercent > 0 ? "Slight gain" : "Stable",
            buy_signals: [],
            is_favorable: changePercent > 0,
            volatility: rsi > 70 ? "HIGH" : rsi < 30 ? "LOW" : "MEDIUM"
        });
    });

    return mockStocks;
}

// Export for use in main.js
window.generateMockStocks = generateMockStocks;
