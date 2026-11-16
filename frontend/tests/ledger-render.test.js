import { test } from 'node:test';
import assert from 'node:assert/strict';

import { summaryHTML, holdingsHTML, transactionsHTML } from '../js/ledger/ledger-render.js';

const header = { portfolio_id: 1, base_currency: 'TRY', cost_basis_method: 'weighted_average', computed_at: '2026-11-16T01:17:24+00:00' };

const thyao = {
    symbol: 'THYAO', exchange: 'BIST', name: null, currency: 'TRY', quantity: '60.00000000',
    average_cost: '280.625000', cost_basis: '16837.500000', cost_basis_base: '16837.500000',
    market_value: '19215.000000', unrealized_pnl: '2377.500000', market_value_base: '19215.000000',
    unrealized_pnl_base: '2377.500000', weight: '1.0000000000',
    quote: { price: '320.250000', currency: 'TRY', as_of: '2026-11-16T01:17:24+00:00', freshness: 'delayed', source: 'wolfee_quote_cache' },
    fx_rate: null, unavailable_reason: null,
};

const aaplNoRate = {
    symbol: 'AAPL', exchange: 'US', name: null, currency: 'USD', quantity: '5.00000000',
    average_cost: '190.100000', cost_basis: '950.500000', cost_basis_base: null,
    market_value: '1781.349945', unrealized_pnl: '830.849945', market_value_base: null,
    unrealized_pnl_base: null, weight: null,
    quote: { price: '356.269989', currency: 'USD', as_of: '2026-11-16T01:17:24+00:00', freshness: 'delayed', source: 'wolfee_quote_cache' },
    fx_rate: null, unavailable_reason: 'missing_fx_rate',
};

const partial = {
    ...header, is_complete: false, unvalued_symbols: ['AAPL'],
    positions: [thyao, aaplNoRate],
    total_market_value: '19215.000000', total_cost_basis: '16837.500000', total_unrealized_pnl: '2377.500000',
};

test('a partial total says so and names the positions not valued', () => {
    const html = summaryHTML(partial, null);
    assert.match(html, /Partial total, 1 position not valued/);
    assert.match(html, /Not valued: <span class="num">AAPL<\/span>/);
    assert.match(html, /19,215\.00 ₺/);
});

test('a complete total shows no partial notice', () => {
    const html = summaryHTML({ ...partial, is_complete: true, unvalued_symbols: [] }, null);
    assert.doesNotMatch(html, /Partial total/);
});

test('missing_fx_rate shows Not available with the reason, never an estimate in TRY', () => {
    const html = holdingsHTML(partial);
    const aaplRow = html.split('<tr>').find(row => row.includes('AAPL'));
    assert.match(aaplRow, /Not available/);
    assert.match(aaplRow, /No exchange rate to TRY/);
    // The API's own USD figure is shown, labelled with its currency
    assert.match(aaplRow, /<small class="na-reason">1,781\.35 USD<\/small>/);
    assert.match(aaplRow, /\+830\.85 USD/);
    assert.doesNotMatch(aaplRow, /₺/);
});

test('realised P/L in TRY comes from the API as it is', () => {
    const performance = {
        ...header, is_complete: true, unvalued_symbols: [],
        realized_pnl: [{ currency: 'TRY', amount: '816.900000' }], realized_pnl_base: '816.900000',
        unrealized_pnl_base: null, dividends: [], fees: [{ currency: 'TRY', amount: '20.750000' }],
        net_deposits: [], cash_balances: [], realized_lots: [],
    };
    const html = summaryHTML({ ...partial, is_complete: true, unvalued_symbols: [] }, performance);
    assert.match(html, /\+816\.90 ₺/);
    // A fee is an amount, not a gain: no plus sign, no gain colour
    assert.match(html, /<span class="num">20\.75 ₺<\/span>/);
});

test('names and notes from the API are escaped', () => {
    const html = transactionsHTML({
        total: 1,
        items: [{ id: 7, type: 'DEPOSIT', symbol: null, quantity: '10.00000000', price: null, fee: '0.000000', currency: 'TRY', trade_date: '2026-11-02', note: '<img src=x onerror=alert(1)>', voids_transaction_id: null, voided_by_transaction_id: null }],
    }, null);
    assert.doesNotMatch(html, /<img/);
    assert.match(html, /&lt;img/);
});

test('a voided row and its reversal are marked, with no void action', () => {
    const base = { type: 'BUY', symbol: 'THYAO', quantity: '1.00000000', price: '1.000000', fee: '0.000000', currency: 'TRY', trade_date: '2026-11-03', note: null };
    const html = transactionsHTML({
        total: 2,
        items: [
            { ...base, id: 9, voids_transaction_id: 8, voided_by_transaction_id: null },
            { ...base, id: 8, voids_transaction_id: null, voided_by_transaction_id: 9 },
        ],
    }, null);
    assert.match(html, /Reversal of #8/);
    assert.match(html, /Voided/);
    assert.doesNotMatch(html, /data-action="void-ask"/);
});

test('empty holdings and transactions show empty states', () => {
    assert.match(holdingsHTML({ ...partial, positions: [] }), /No positions yet/);
    assert.match(transactionsHTML({ items: [], total: 0 }, null), /No transactions yet/);
});
