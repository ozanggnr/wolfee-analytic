/**
 * Requests for the Portfolio page: /api/v1/portfolios (API_CONTRACT §5.1.1,
 * §5.2.1). Every call goes through window.authFetch, which sends the session
 * cookie and the CSRF header on writes.
 *
 * Each function resolves to { ok: true, data } or { ok: false, status, error },
 * where error is { message, fields } from readableApiError. Nothing throws.
 */

import { readableApiError } from '../core/api-errors.js';

const PAGE_LIMIT = 50;
const PORTFOLIO_LIMIT = 200;
const NETWORK_ERROR = 'The server could not be reached. Try again in a moment.';

function baseUrl() {
    // API_URL is a global const from config.js (a classic script)
    return typeof API_URL !== 'undefined' ? API_URL : '';
}

function fallbackFor(status) {
    if (status === 401) return 'Your session has ended. Sign in again.';
    if (status === 404) return 'This portfolio was not found.';
    if (status === 429) return 'Too many requests. Wait a moment and try again.';
    return 'The request failed. Try again in a moment.';
}

async function request(path, options = {}) {
    const fetchFn = window.authFetch || fetch;
    let response;
    try {
        response = await fetchFn(`${baseUrl()}${path}`, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        });
    } catch (err) {
        console.error('Portfolio request failed:', path, err);
        return { ok: false, status: 0, error: { message: NETWORK_ERROR, fields: {} } };
    }

    let data = null;
    try {
        data = await response.json();
    } catch (err) {
        data = null;
    }
    if (response.ok) return { ok: true, status: response.status, data };
    return { ok: false, status: response.status, error: readableApiError(data, fallbackFor(response.status)) };
}

function portfolioPath(portfolioId, suffix = '') {
    return `/api/v1/portfolios/${encodeURIComponent(String(portfolioId))}${suffix}`;
}

export function listPortfolios() {
    return request(`/api/v1/portfolios?limit=${PORTFOLIO_LIMIT}`);
}

export function createPortfolio(name) {
    // Base currency is TRY only (decision D3)
    return request('/api/v1/portfolios', {
        method: 'POST',
        body: JSON.stringify({ name, base_currency: 'TRY', kind: 'real' }),
    });
}

export function getHoldings(portfolioId) {
    return request(portfolioPath(portfolioId, '/holdings'));
}

export function getPerformance(portfolioId) {
    return request(portfolioPath(portfolioId, '/performance'));
}

export function listTransactions(portfolioId, offset = 0) {
    return request(portfolioPath(portfolioId, `/transactions?limit=${PAGE_LIMIT}&offset=${Number(offset) || 0}`));
}

export function addTransaction(portfolioId, body) {
    return request(portfolioPath(portfolioId, '/transactions'), { method: 'POST', body: JSON.stringify(body) });
}

export function voidTransaction(portfolioId, transactionId) {
    return request(portfolioPath(portfolioId, `/transactions/${encodeURIComponent(String(transactionId))}/void`), {
        method: 'POST',
        body: JSON.stringify({}),
    });
}
