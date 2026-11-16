import { test } from 'node:test';
import assert from 'node:assert/strict';

import { readableApiError } from '../js/core/api-errors.js';

const FALLBACK = 'Something went wrong. Try again.';

test('a string detail is shown as it is', () => {
    assert.deepEqual(readableApiError({ detail: 'Invalid email or password.' }, FALLBACK), {
        message: 'Invalid email or password.', fields: {},
    });
});

test('a 422 detail array becomes one message per field, never [object Object]', () => {
    const body = {
        detail: [
            { loc: ['body', 'email'], msg: 'value is not a valid email address: An email address must have an @-sign.', type: 'value_error' },
            { loc: ['body', 'password'], msg: 'String should have at least 10 characters', type: 'string_too_short' },
        ],
    };
    const result = readableApiError(body, FALLBACK);
    assert.equal(result.fields.email, 'Value is not a valid email address: An email address must have an @-sign.');
    assert.equal(result.fields.password, 'String should have at least 10 characters');
    assert.equal(result.message, 'Check the highlighted fields.');
    assert.ok(!JSON.stringify(result).includes('[object Object]'));
});

test('a body-level validation error is the message, without the "Value error," prefix', () => {
    const body = { detail: [{ loc: ['body'], msg: 'Value error, symbol is required for BUY', type: 'value_error' }] };
    assert.deepEqual(readableApiError(body, FALLBACK), { message: 'Symbol is required for BUY', fields: {} });
});

test('missing or unknown shapes fall back to the generic line', () => {
    for (const body of [null, undefined, {}, { detail: null }, { detail: 42 }, { detail: [] }, { detail: [{}] }, { detail: { a: 1 } }]) {
        const result = readableApiError(body, FALLBACK);
        assert.equal(result.message, FALLBACK, JSON.stringify(body));
    }
});

test('field names can be renamed for the form, e.g. a nested query field', () => {
    const body = { detail: [{ loc: ['query', 'limit'], msg: 'Input should be less than or equal to 200' }] };
    assert.deepEqual(readableApiError(body, FALLBACK).fields, { limit: 'Input should be less than or equal to 200' });
});
