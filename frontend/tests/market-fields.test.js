import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
    NOT_AVAILABLE,
    DEFAULT_AI_DISCLAIMER,
    fieldValue,
    numberField,
    formatNumberField,
    indicatorsAsOf,
    indicatorField,
    indicatorNumber,
    formatIndicatorField,
    formatTimestamp,
    aiProvenance,
    splitLabelledLines,
    changeDirection,
    formatChange,
    formatPrice,
    directionClass,
    parseTimestamp,
} from '../js/core/market-fields.js';

test('fieldValue returns null for null, undefined, blank strings and non-finite numbers', () => {
    const stock = { rsi: null, ma_20: undefined, prediction: '  ', volatility_pct: Number.NaN };

    for (const field of ['rsi', 'ma_20', 'prediction', 'volatility_pct', 'missing']) {
        assert.equal(fieldValue(stock, field), null, field);
    }
});

test('fieldValue keeps real values, including zero and false', () => {
    const stock = { rsi: 0, is_buyable: false, prediction: 'Above its 20-day average' };

    assert.equal(fieldValue(stock, 'rsi'), 0);
    assert.equal(fieldValue(stock, 'is_buyable'), false);
    assert.equal(fieldValue(stock, 'prediction'), 'Above its 20-day average');
});

test('fieldValue treats a field listed in estimated_fields as not available', () => {
    const stock = { rsi: 61.2, ma_20: 318.5, estimated_fields: ['rsi'] };

    assert.equal(fieldValue(stock, 'rsi'), null);
    assert.equal(fieldValue(stock, 'ma_20'), 318.5);
});

test('fieldValue ignores an estimated_fields value that is not an array', () => {
    assert.equal(fieldValue({ rsi: 40, estimated_fields: 'rsi' }, 'rsi'), 40);
});

test('fieldValue returns null when the record is missing', () => {
    assert.equal(fieldValue(null, 'rsi'), null);
    assert.equal(fieldValue(undefined, 'rsi'), null);
});

test('numberField accepts numbers and decimal strings and rejects anything else', () => {
    const stock = { rsi: 53.8, ma_20: '316.97', volatility: 'HIGH', day_low: '1e3', day_high: true };

    assert.equal(numberField(stock, 'rsi'), 53.8);
    assert.equal(numberField(stock, 'ma_20'), 316.97);
    assert.equal(numberField(stock, 'volatility'), null);
    assert.equal(numberField(stock, 'day_low'), null);
    assert.equal(numberField(stock, 'day_high'), null);
});

test('formatNumberField shows Not available instead of a substitute value', () => {
    const stock = { rsi: null, ma_20: 316.974, estimated_fields: ['day_low'], day_low: 315.5 };

    assert.equal(formatNumberField(stock, 'rsi', 1), NOT_AVAILABLE);
    assert.equal(formatNumberField(stock, 'day_low', 2), NOT_AVAILABLE);
    assert.equal(formatNumberField(stock, 'ma_20', 2), '316.97');
    assert.equal(formatNumberField(stock, 'ma_20', 2, ' ₺'), '316.97 ₺');
});

test('indicatorsAsOf accepts only a real YYYY-MM-DD date', () => {
    assert.equal(indicatorsAsOf({ indicators_as_of: '2026-11-13' }), '2026-11-13');

    for (const value of ['2026-11-13T10:00:00Z', '2026-13-01', '2026-02-30', '13.11.2026', '<b>x</b>', 20261113, null]) {
        assert.equal(indicatorsAsOf({ indicators_as_of: value }), null, String(value));
    }
});

test('indicator values are shown only when indicators_as_of is a real date (REQ-29)', () => {
    // The workers' single-day estimates carry no indicators_as_of
    const estimate = { rsi: 53.3, ma_20: 16.5, volatility: 'LOW', volatility_pct: 12.5 };
    const computed = { ...estimate, indicators_as_of: '2026-11-13' };
    const badDate = { ...estimate, indicators_as_of: '2026-02-30' };

    for (const field of ['rsi', 'ma_20', 'volatility_pct']) {
        assert.equal(indicatorNumber(estimate, field), null, field);
        assert.equal(indicatorNumber(badDate, field), null, field);
    }
    assert.equal(indicatorField(estimate, 'volatility'), null);

    assert.equal(indicatorNumber(computed, 'rsi'), 53.3);
    assert.equal(indicatorNumber(computed, 'ma_20'), 16.5);
    assert.equal(indicatorNumber(computed, 'volatility_pct'), 12.5);
    assert.equal(indicatorField(computed, 'volatility'), 'LOW');
});

test('indicator values still respect null and estimated_fields when dated', () => {
    const stock = { rsi: null, ma_20: 16.5, indicators_as_of: '2026-11-13', estimated_fields: ['ma_20'] };

    assert.equal(indicatorNumber(stock, 'rsi'), null);
    assert.equal(indicatorNumber(stock, 'ma_20'), null);
});

test('formatIndicatorField shows Not available without indicators_as_of', () => {
    const stock = { rsi: 41.27, ma_20: 18.234 };

    assert.equal(formatIndicatorField(stock, 'rsi', 1), NOT_AVAILABLE);
    assert.equal(formatIndicatorField({ ...stock, indicators_as_of: '2026-11-13' }, 'rsi', 1), '41.3');
    assert.equal(formatIndicatorField({ ...stock, indicators_as_of: '2026-11-13' }, 'ma_20', 2, ' ₺'), '18.23 ₺');
});

test('formatTimestamp shows the instant in the requested time zone', () => {
    const istanbul = { timeZone: 'Europe/Istanbul' };

    assert.equal(formatTimestamp('2026-11-14T06:05:00Z', istanbul), '2026-11-14 09:05 GMT+3');
    assert.equal(formatTimestamp('2026-11-14T09:05:00+03:00', { timeZone: 'UTC' }), '2026-11-14 06:05 UTC');
    assert.equal(formatTimestamp('2026-11-14T22:30:00Z', istanbul), '2026-11-15 01:30 GMT+3');
});

test('formatTimestamp reads a timestamp without a zone as UTC', () => {
    assert.equal(formatTimestamp('2026-11-14T06:05:00.123456', { timeZone: 'Europe/Istanbul' }), '2026-11-14 09:05 GMT+3');
});

test('formatTimestamp without a time zone uses the runtime zone', () => {
    const value = '2026-11-14T06:05:00Z';
    const runtimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

    assert.equal(formatTimestamp(value), formatTimestamp(value, { timeZone: runtimeZone }));
});

test('formatTimestamp rejects anything that is not an ISO timestamp', () => {
    for (const value of ['', 'yesterday', '2026-11-14', '2026-11-14T25:99:00Z', null, undefined, 42]) {
        assert.equal(formatTimestamp(value), null, String(value));
    }
});

test('aiProvenance reads the new response shape', () => {
    const result = aiProvenance({
        analysis: 'Price is above its 20-day average.',
        generated_by: 'gemini-x',
        generated_at: '2026-11-14T06:05:00Z',
        inputs_as_of: '2026-11-13T15:00:00Z',
        is_fallback: false,
        disclaimer: 'Descriptive only. Not investment advice.',
        violations: ['should never surface'],
    }, 'analysis', { timeZone: 'Europe/Istanbul' });

    assert.deepEqual(result, {
        text: 'Price is above its 20-day average.',
        isPlainText: true,
        disclaimer: 'Descriptive only. Not investment advice.',
        generatedAt: '2026-11-14 09:05 GMT+3',
        inputsAsOf: '2026-11-13 18:00 GMT+3',
        isTemplate: false,
    });
});

test('aiProvenance marks template output from is_fallback or generated_by', () => {
    const base = { insight: 'x', disclaimer: 'd', generated_at: '2026-11-14T06:05:00Z' };

    assert.equal(aiProvenance({ ...base, is_fallback: true, generated_by: 'gemini-x' }, 'insight').isTemplate, true);
    assert.equal(aiProvenance({ ...base, is_fallback: false, generated_by: 'template' }, 'insight').isTemplate, true);
    assert.equal(aiProvenance({ ...base, is_fallback: false, generated_by: 'gemini-x' }, 'insight').isTemplate, false);
});

test('aiProvenance falls back to a default disclaimer for the legacy shape', () => {
    const result = aiProvenance({ insight: '**Legacy** text' }, 'insight');

    assert.equal(result.isPlainText, false);
    assert.equal(result.disclaimer, DEFAULT_AI_DISCLAIMER);
    assert.equal(result.generatedAt, null);
    assert.equal(result.isTemplate, false);
});

test('aiProvenance uses the default disclaimer when the given one is blank', () => {
    assert.equal(aiProvenance({ insight: 'x', disclaimer: '   ' }, 'insight').disclaimer, DEFAULT_AI_DISCLAIMER);
});

test('aiProvenance returns empty text when the text field is missing or not a string', () => {
    assert.equal(aiProvenance({ disclaimer: 'd' }, 'analysis').text, '');
    assert.equal(aiProvenance({ analysis: 42, disclaimer: 'd' }, 'analysis').text, '');
    assert.equal(aiProvenance(null, 'analysis').text, '');
});

test('splitLabelledLines splits on line breaks and picks out only known line-leading labels', () => {
    const lines = splitLabelledLines('Decision: hold\r\nNo Decision: here\n\nRisk to watch: <b>x</b>', ['Decision', 'Risk to watch']);

    assert.deepEqual(lines, [
        { label: 'Decision', text: ' hold' },
        { label: null, text: 'No Decision: here' },
        { label: null, text: '' },
        { label: 'Risk to watch', text: ' <b>x</b>' },
    ]);
});

test('splitLabelledLines collapses runs of blank lines and trims the ends', () => {
    assert.deepEqual(splitLabelledLines('\n\nA\n\n\n\nB\n\n', []), [
        { label: null, text: 'A' },
        { label: null, text: '' },
        { label: null, text: 'B' },
    ]);
});

test('changeDirection reads up, down and flat, and null when change_pct is not available', () => {
    assert.equal(changeDirection({ change_pct: 1.25 }), 'up');
    assert.equal(changeDirection({ change_pct: -0.4 }), 'down');
    assert.equal(changeDirection({ change_pct: 0 }), 'flat');
    assert.equal(changeDirection({ change_pct: '0.50' }), 'up');
    assert.equal(changeDirection({ change_pct: null }), null);
    assert.equal(changeDirection({}), null);
    assert.equal(changeDirection({ selling: 1, pct: -2 }, 'pct'), 'down');
});

test('formatChange shows a null change_pct as not available, never as 0.00%', () => {
    assert.equal(formatChange({ change_pct: null }), NOT_AVAILABLE);
    assert.equal(formatChange({}), NOT_AVAILABLE);
    assert.equal(formatChange({ change_pct: null }, { style: 'signed' }), NOT_AVAILABLE);
});

test('formatChange writes an arrow for the direction, or a sign in the signed style', () => {
    assert.equal(formatChange({ change_pct: 1.234 }), '▲ 1.23%');
    assert.equal(formatChange({ change_pct: -0.5 }), '▼ 0.50%');
    assert.equal(formatChange({ change_pct: 0 }), '0.00%');
    assert.equal(formatChange({ change_pct: 2 }, { style: 'signed' }), '+2.00%');
    assert.equal(formatChange({ change_pct: -2 }, { style: 'signed' }), '-2.00%');
    assert.equal(formatChange({ change_pct: 0 }, { style: 'signed' }), '0.00%');
    assert.equal(formatChange({ change_pct: 1.26 }, { digits: 1 }), '▲ 1.3%');
    assert.equal(formatChange({ pct: -3 }, { field: 'pct' }), '▼ 3.00%');
});

test('formatPrice shows missing and zero prices as not available', () => {
    assert.equal(formatPrice({ price: 12.5 }, 'price', '₺'), '12.50 ₺');
    assert.equal(formatPrice({ price: '7.125' }, 'price', '$', 3), '7.125 $');
    assert.equal(formatPrice({ price: 0 }, 'price', '₺'), NOT_AVAILABLE);
    assert.equal(formatPrice({ price: null }, 'price', '₺'), NOT_AVAILABLE);
    assert.equal(formatPrice({ price: -1 }, 'price', '₺'), NOT_AVAILABLE);
});

test('directionClass maps up to gain and down to loss; flat and unknown are neutral', () => {
    assert.equal(directionClass('up'), 'is-gain');
    assert.equal(directionClass('down'), 'is-loss');
    assert.equal(directionClass('flat'), '');
    assert.equal(directionClass(null), '');
});

test('parseTimestamp reads a timestamp without a zone as UTC', () => {
    assert.equal(parseTimestamp('2026-11-15T17:11:00').toISOString(), '2026-11-15T17:11:00.000Z');
    assert.equal(parseTimestamp('2026-11-15T20:11:00+03:00').toISOString(), '2026-11-15T17:11:00.000Z');
    assert.equal(parseTimestamp('2026-11-15T17:11:00.250Z').toISOString(), '2026-11-15T17:11:00.250Z');
});

test('parseTimestamp returns null for anything that is not an ISO timestamp', () => {
    for (const value of [null, undefined, '', 'yesterday', '2026-11-15', 42, '2026-13-45T99:00:00']) {
        assert.equal(parseTimestamp(value), null, String(value));
    }
});
