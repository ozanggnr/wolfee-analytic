import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
    NOT_AVAILABLE,
    DEFAULT_AI_DISCLAIMER,
    fieldValue,
    numberField,
    formatNumberField,
    indicatorsAsOf,
    formatTimestampUTC,
    aiProvenance,
    splitLabelledLines,
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

test('formatTimestampUTC formats ISO timestamps in UTC and rejects anything else', () => {
    assert.equal(formatTimestampUTC('2026-11-14T09:05:00+03:00'), '2026-11-14 06:05 UTC');
    assert.equal(formatTimestampUTC('2026-11-14T06:05:00Z'), '2026-11-14 06:05 UTC');
    assert.equal(formatTimestampUTC('2026-11-14T06:05:00.123456'), '2026-11-14 06:05 UTC');

    for (const value of ['', 'yesterday', null, undefined, 42]) {
        assert.equal(formatTimestampUTC(value), null, String(value));
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
    }, 'analysis');

    assert.deepEqual(result, {
        text: 'Price is above its 20-day average.',
        isPlainText: true,
        disclaimer: 'Descriptive only. Not investment advice.',
        generatedAt: '2026-11-14 06:05 UTC',
        inputsAsOf: '2026-11-13 15:00 UTC',
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
