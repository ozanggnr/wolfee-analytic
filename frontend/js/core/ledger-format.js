/**
 * Display helpers for the Portfolio page (REQ-32, API_CONTRACT §5).
 *
 * The API sends money, quantities, rates and weights as decimal strings. The
 * frontend does no portfolio arithmetic (TEAM_STRUCTURE H10, API_CONTRACT §7):
 * these functions only round and group the text for display, exactly, with
 * BigInt and string operations, never with binary floats.
 */

import { NOT_AVAILABLE } from './market-fields.js';
import { isValidSymbol } from './safe-html.js';

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
const UNSIGNED_DECIMAL_INPUT = /^\d+(?:\.\d+)?$/;
const CURRENCY = /^[A-Za-z]{3}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const NOTE_MAX_LENGTH = 500;
const CURRENCY_SYMBOLS = { TRY: '₺' };

/**
 * Rounds a decimal string to `places` decimals, half away from zero.
 *
 * @param {unknown} value e.g. "1234.565000"
 * @param {number} places
 * @returns {string | null} e.g. "1234.57"; null when value is not a decimal string
 */
export function roundDecimalString(value, places) {
    if (typeof value !== 'string') return null;
    const match = DECIMAL.exec(value.trim());
    if (!match) return null;

    const [, sign, whole, fraction = ''] = match;
    const kept = fraction.slice(0, places).padEnd(places, '0');
    let scaled = BigInt(whole + kept);
    if ((fraction[places] || '0') >= '5') scaled += 1n;

    const digits = scaled.toString().padStart(places + 1, '0');
    const integerPart = places === 0 ? digits : digits.slice(0, -places);
    const decimals = places === 0 ? '' : `.${digits.slice(-places)}`;
    const negative = sign === '-' && scaled !== 0n;
    return `${negative ? '-' : ''}${integerPart}${decimals}`;
}

function groupThousands(integerDigits) {
    return integerDigits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function groupDecimalText(text) {
    const negative = text.startsWith('-');
    const [whole, fraction] = (negative ? text.slice(1) : text).split('.');
    return `${negative ? '-' : ''}${groupThousands(whole)}${fraction !== undefined ? `.${fraction}` : ''}`;
}

/**
 * @param {unknown} value decimal string
 * @param {number} places
 * @returns {string | null} rounded and grouped, e.g. "1,234,567.89"
 */
export function formatDecimal(value, places) {
    const rounded = roundDecimalString(value, places);
    return rounded === null ? null : groupDecimalText(rounded);
}

/**
 * @param {unknown} value money as a decimal string, or null
 * @param {string} currency ISO 4217 code
 * @returns {string} e.g. "1,500.00 ₺"; NOT_AVAILABLE when the value is missing
 */
export function formatMoney(value, currency, places = 2) {
    const text = formatDecimal(value, places);
    if (text === null) return NOT_AVAILABLE;
    return `${text} ${CURRENCY_SYMBOLS[currency] || currency || ''}`.trim();
}

/** A quantity without trailing zeros, e.g. "1,250.5". */
export function formatQuantity(value) {
    if (typeof value !== 'string' || !DECIMAL.test(value.trim())) return NOT_AVAILABLE;
    const trimmed = value.trim().replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
    return groupDecimalText(trimmed);
}

/**
 * A ratio ("0.2500000000") as a percentage ("25.00%"): the decimal point is
 * moved two places as text, then rounded for display.
 */
export function formatRatioAsPercent(value, places = 2) {
    if (typeof value !== 'string') return NOT_AVAILABLE;
    const match = DECIMAL.exec(value.trim());
    if (!match) return NOT_AVAILABLE;
    const [, sign, whole, fraction = ''] = match;
    const shiftedWhole = `${whole}${fraction.slice(0, 2).padEnd(2, '0')}`.replace(/^0+(?=\d)/, '');
    const shiftedFraction = fraction.slice(2);
    const text = formatDecimal(`${sign}${shiftedWhole}${shiftedFraction ? `.${shiftedFraction}` : ''}`, places);
    return `${text}%`;
}

/**
 * @param {unknown} value decimal string
 * @returns {1 | -1 | 0 | null} the sign read from the text; null when not a decimal
 */
export function decimalSign(value) {
    if (typeof value !== 'string' || !DECIMAL.test(value.trim())) return null;
    const text = value.trim();
    if (!/[1-9]/.test(text)) return 0;
    return text.startsWith('-') ? -1 : 1;
}

/**
 * @param {{ is_complete?: boolean, unvalued_symbols?: string[] } | null} header
 *   AnalyticsHeader of holdings or performance
 * @returns {string | null} e.g. "Partial total, 2 positions not valued"; null when complete
 */
export function partialTotalText(header) {
    if (!header || header.is_complete !== false) return null;
    const count = Array.isArray(header.unvalued_symbols) ? header.unvalued_symbols.length : 0;
    return `Partial total, ${count} ${count === 1 ? 'position' : 'positions'} not valued`;
}

const UNAVAILABLE_REASONS = {
    missing_fx_rate: 'No exchange rate to TRY',
    missing_quote: 'No price yet',
    quote_currency_mismatch: 'Price is in another currency',
    quote_symbol_mismatch: 'Price is for another symbol',
    invalid_quote_price: 'Price is not usable',
};

/** Why a position has no value; the value itself is shown as NOT_AVAILABLE. */
export function unavailableReasonText(reason) {
    if (typeof reason !== 'string' || reason === '') return null;
    return UNAVAILABLE_REASONS[reason] || 'Could not be valued';
}

const FRESHNESS = { realtime: 'Real time', delayed: 'Delayed', end_of_day: 'End of day', stale: 'Stale' };

export function freshnessText(freshness) {
    return FRESHNESS[freshness] || null;
}

// ---------- Transactions ----------

export const TRANSACTION_TYPES = ['BUY', 'SELL', 'DIVIDEND', 'SPLIT', 'FEE', 'DEPOSIT', 'WITHDRAWAL'];

const PRICED = { symbol: 'required', quantity: 'required', price: 'required', fee: 'optional', currency: 'hidden', fx_rate_to_base: 'optional' };
const FIELD_RULES = {
    BUY: PRICED,
    SELL: PRICED,
    DIVIDEND: PRICED,
    SPLIT: { symbol: 'required', quantity: 'required', price: 'hidden', fee: 'hidden', currency: 'hidden', fx_rate_to_base: 'hidden' },
    FEE: { symbol: 'optional', quantity: 'hidden', price: 'hidden', fee: 'required', currency: 'optional', fx_rate_to_base: 'optional' },
    DEPOSIT: { symbol: 'hidden', quantity: 'required', price: 'hidden', fee: 'hidden', currency: 'required', fx_rate_to_base: 'optional' },
    WITHDRAWAL: { symbol: 'hidden', quantity: 'required', price: 'hidden', fee: 'hidden', currency: 'required', fx_rate_to_base: 'optional' },
};

/** Field label for `quantity`, which means something different per type. */
export const QUANTITY_LABELS = {
    BUY: 'Quantity', SELL: 'Quantity', DIVIDEND: 'Shares held',
    SPLIT: 'New units per old unit', DEPOSIT: 'Amount', WITHDRAWAL: 'Amount',
};

/**
 * @param {string} type one of TRANSACTION_TYPES
 * @returns {Record<'symbol'|'quantity'|'price'|'fee'|'currency'|'fx_rate_to_base', 'required'|'optional'|'hidden'>}
 */
export function transactionFieldsForType(type) {
    return { ...(FIELD_RULES[type] || FIELD_RULES.BUY) };
}

function readDecimal(raw, field, errors, { required, positive }) {
    const text = typeof raw === 'string' ? raw.trim() : '';
    if (text === '') {
        if (required) errors[field] = 'Required.';
        return undefined;
    }
    if (/^\d+,\d+$/.test(text)) {
        errors[field] = 'Use a point as the decimal separator, for example 320.25.';
        return undefined;
    }
    if (!UNSIGNED_DECIMAL_INPUT.test(text)) {
        errors[field] = 'Enter a number, for example 10 or 320.25.';
        return undefined;
    }
    if (positive && decimalSign(text) !== 1) {
        errors[field] = 'Must be greater than zero.';
        return undefined;
    }
    return text;
}

/**
 * Builds a TransactionCreate body from form values. Amounts stay strings, so
 * no binary rounding enters the ledger. Only the fields of the type are sent.
 *
 * @param {Record<string, string | undefined>} values raw form values
 * @returns {{ body: Record<string, string> | null, errors: Record<string, string> }}
 */
export function buildTransactionBody(values) {
    const errors = {};
    const type = TRANSACTION_TYPES.includes(values.type) ? values.type : null;
    if (type === null) return { body: null, errors: { type: 'Choose a transaction type.' } };

    const rules = FIELD_RULES[type];
    const body = { type };

    if (rules.symbol !== 'hidden') {
        const symbol = (values.symbol || '').trim().toUpperCase();
        if (symbol === '') {
            if (rules.symbol === 'required') errors.symbol = 'Required.';
        } else if (!isValidSymbol(symbol)) {
            errors.symbol = 'Enter a ticker, for example THYAO or AAPL.';
        } else {
            body.symbol = symbol;
        }
    }

    const quantity = rules.quantity === 'hidden' ? undefined
        : readDecimal(values.quantity, 'quantity', errors, { required: true, positive: true });
    if (quantity !== undefined) body.quantity = quantity;

    const price = rules.price === 'hidden' ? undefined
        : readDecimal(values.price, 'price', errors, { required: rules.price === 'required', positive: false });
    if (price !== undefined) body.price = price;

    const fee = rules.fee === 'hidden' ? undefined
        : readDecimal(values.fee, 'fee', errors, { required: rules.fee === 'required', positive: rules.fee === 'required' });
    if (fee !== undefined) body.fee = fee;

    if (rules.currency !== 'hidden') {
        const currency = (values.currency || '').trim().toUpperCase();
        const needed = rules.currency === 'required' || !body.symbol;
        if (currency === '') {
            if (needed) errors.currency = 'Required without a symbol.';
        } else if (!CURRENCY.test(currency)) {
            errors.currency = 'Use a three-letter code, for example TRY or USD.';
        } else {
            body.currency = currency;
        }
    }

    const fxRate = rules.fx_rate_to_base === 'hidden' ? undefined
        : readDecimal(values.fx_rate_to_base, 'fx_rate_to_base', errors, { required: false, positive: true });
    if (fxRate !== undefined) body.fx_rate_to_base = fxRate;

    const tradeDate = (values.trade_date || '').trim();
    if (!ISO_DATE.test(tradeDate)) errors.trade_date = 'Required.';
    else body.trade_date = tradeDate;

    const note = (values.note || '').trim();
    if (note.length > NOTE_MAX_LENGTH) errors.note = `At most ${NOTE_MAX_LENGTH} characters.`;
    else if (note !== '') body.note = note;

    return Object.keys(errors).length > 0 ? { body: null, errors } : { body, errors };
}
