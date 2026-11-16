import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
    roundDecimalString,
    formatDecimal,
    formatMoney,
    formatQuantity,
    formatRatioAsPercent,
    decimalSign,
    partialTotalText,
    unavailableReasonText,
    freshnessText,
    transactionFieldsForType,
    buildTransactionBody,
    TRANSACTION_TYPES,
} from '../js/core/ledger-format.js';
import { NOT_AVAILABLE } from '../js/core/market-fields.js';

test('roundDecimalString rounds half away from zero without floats', () => {
    assert.equal(roundDecimalString('1234.565000', 2), '1234.57');
    assert.equal(roundDecimalString('1234.564999', 2), '1234.56');
    assert.equal(roundDecimalString('-0.005000', 2), '-0.01');
    assert.equal(roundDecimalString('-0.004000', 2), '0.00');
    assert.equal(roundDecimalString('9.999', 2), '10.00');
    assert.equal(roundDecimalString('12', 2), '12.00');
    assert.equal(roundDecimalString('0.1', 0), '0');
    // Beyond float precision: still exact
    assert.equal(roundDecimalString('12345678901234567.125', 2), '12345678901234567.13');
});

test('roundDecimalString returns null for anything that is not a decimal string', () => {
    for (const value of [null, undefined, '', 'abc', '1e5', '1.2.3', 12.5, '--1']) {
        assert.equal(roundDecimalString(value, 2), null, String(value));
    }
});

test('formatDecimal groups thousands and keeps the sign', () => {
    assert.equal(formatDecimal('1234567.891000', 2), '1,234,567.89');
    assert.equal(formatDecimal('-1234.5', 2), '-1,234.50');
    assert.equal(formatDecimal('999.994', 2), '999.99');
    assert.equal(formatDecimal(null, 2), null);
});

test('formatMoney shows the currency and Not available for null', () => {
    assert.equal(formatMoney('1500.000000', 'TRY'), '1,500.00 ₺');
    assert.equal(formatMoney('-20.5', 'USD'), '-20.50 USD');
    assert.equal(formatMoney(null, 'TRY'), NOT_AVAILABLE);
    assert.equal(formatMoney('x', 'TRY'), NOT_AVAILABLE);
});

test('formatQuantity drops trailing zeros and keeps meaningful decimals', () => {
    assert.equal(formatQuantity('10.00000000'), '10');
    assert.equal(formatQuantity('1250.50000000'), '1,250.5');
    assert.equal(formatQuantity('0.00012300'), '0.000123');
    assert.equal(formatQuantity(null), NOT_AVAILABLE);
});

test('formatRatioAsPercent moves the decimal point as text', () => {
    assert.equal(formatRatioAsPercent('0.2500000000'), '25.00%');
    assert.equal(formatRatioAsPercent('1.0000000000'), '100.00%');
    assert.equal(formatRatioAsPercent('0.0012345000'), '0.12%');
    assert.equal(formatRatioAsPercent('0.0000500000'), '0.01%');
    assert.equal(formatRatioAsPercent(null), NOT_AVAILABLE);
});

test('decimalSign reads the sign from the text', () => {
    assert.equal(decimalSign('12.50'), 1);
    assert.equal(decimalSign('-0.010000'), -1);
    assert.equal(decimalSign('0.000000'), 0);
    assert.equal(decimalSign('-0.000'), 0);
    assert.equal(decimalSign(null), null);
});

test('partialTotalText names how many positions are not valued', () => {
    assert.equal(partialTotalText({ is_complete: true, unvalued_symbols: [] }), null);
    assert.equal(partialTotalText({ is_complete: false, unvalued_symbols: ['AAPL'] }), 'Partial total, 1 position not valued');
    assert.equal(partialTotalText({ is_complete: false, unvalued_symbols: ['AAPL', 'NVDA'] }), 'Partial total, 2 positions not valued');
    assert.equal(partialTotalText(null), null);
});

test('unavailableReasonText explains each reason and never estimates', () => {
    assert.equal(unavailableReasonText('missing_fx_rate'), 'No exchange rate to TRY');
    assert.equal(unavailableReasonText('missing_quote'), 'No price yet');
    assert.equal(unavailableReasonText('something_new'), 'Could not be valued');
    assert.equal(unavailableReasonText(null), null);
});

test('freshnessText labels delayed and stale quotes', () => {
    assert.equal(freshnessText('delayed'), 'Delayed');
    assert.equal(freshnessText('stale'), 'Stale');
    assert.equal(freshnessText('end_of_day'), 'End of day');
    assert.equal(freshnessText('realtime'), 'Real time');
    assert.equal(freshnessText(undefined), null);
});

test('transactionFieldsForType follows the ledger rules', () => {
    assert.deepEqual(TRANSACTION_TYPES, ['BUY', 'SELL', 'DIVIDEND', 'SPLIT', 'FEE', 'DEPOSIT', 'WITHDRAWAL']);
    const buy = transactionFieldsForType('BUY');
    assert.equal(buy.symbol, 'required');
    assert.equal(buy.price, 'required');
    assert.equal(buy.fee, 'optional');
    const deposit = transactionFieldsForType('DEPOSIT');
    assert.equal(deposit.symbol, 'hidden');
    assert.equal(deposit.price, 'hidden');
    assert.equal(deposit.fee, 'hidden');
    assert.equal(deposit.currency, 'required');
    const fee = transactionFieldsForType('FEE');
    assert.equal(fee.quantity, 'hidden');
    assert.equal(fee.fee, 'required');
    assert.equal(fee.symbol, 'optional');
    assert.equal(transactionFieldsForType('SPLIT').price, 'hidden');
});

test('buildTransactionBody sends decimal strings and only the fields of the type', () => {
    const { body, errors } = buildTransactionBody({
        type: 'BUY', symbol: ' thyao ', quantity: '10', price: '320.25', fee: '', currency: 'TRY',
        fx_rate_to_base: '', trade_date: '2026-11-14', note: '  first lot ',
    });
    assert.deepEqual(errors, {});
    assert.deepEqual(body, {
        type: 'BUY', symbol: 'THYAO', quantity: '10', price: '320.25', trade_date: '2026-11-14', note: 'first lot',
    });
});

test('buildTransactionBody keeps the comma typed as a decimal separator out', () => {
    const { errors } = buildTransactionBody({ type: 'BUY', symbol: 'THYAO', quantity: '10', price: '320,25', trade_date: '2026-11-14' });
    assert.match(errors.price, /point/);
});

test('buildTransactionBody reports missing and invalid fields per field', () => {
    const { body, errors } = buildTransactionBody({ type: 'SELL', symbol: '', quantity: '0', price: '', trade_date: '' });
    assert.equal(body, null);
    assert.ok(errors.symbol);
    assert.ok(errors.quantity);
    assert.ok(errors.price);
    assert.ok(errors.trade_date);

    const deposit = buildTransactionBody({ type: 'DEPOSIT', quantity: '5000', currency: 'try', trade_date: '2026-11-14' });
    assert.deepEqual(deposit.errors, {});
    assert.deepEqual(deposit.body, { type: 'DEPOSIT', quantity: '5000', currency: 'TRY', trade_date: '2026-11-14' });

    const fee = buildTransactionBody({ type: 'FEE', fee: '', currency: 'TRY', trade_date: '2026-11-14' });
    assert.ok(fee.errors.fee);
    const noCurrency = buildTransactionBody({ type: 'FEE', fee: '12', trade_date: '2026-11-14' });
    assert.ok(noCurrency.errors.currency);
});
