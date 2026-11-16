import { test } from 'node:test';
import assert from 'node:assert/strict';

import { authFeatures, SAFE_AUTH_FEATURES } from '../js/core/auth-config.js';

test('the config from GET /api/auth/config is used as sent', () => {
    assert.deepEqual(authFeatures({ email_enabled: true, registration_open: true }), { emailEnabled: true, registrationOpen: true });
    assert.deepEqual(authFeatures({ email_enabled: false, registration_open: false }), { emailEnabled: false, registrationOpen: false });
    assert.deepEqual(authFeatures({ email_enabled: true, registration_open: false }), { emailEnabled: true, registrationOpen: false });
});

test('a failed call hides the email features and keeps register visible (REQ-37)', () => {
    assert.deepEqual(SAFE_AUTH_FEATURES, { emailEnabled: false, registrationOpen: true });
    for (const body of [null, undefined, 'error', 42, [], { detail: 'Not Found' }]) {
        assert.deepEqual(authFeatures(body), SAFE_AUTH_FEATURES, JSON.stringify(body));
    }
});

test('only a real true turns email on, and only a real false closes registration', () => {
    assert.deepEqual(authFeatures({ email_enabled: 'true', registration_open: 'false' }), { emailEnabled: false, registrationOpen: true });
    assert.deepEqual(authFeatures({ email_enabled: 1, registration_open: 0 }), { emailEnabled: false, registrationOpen: true });
    assert.deepEqual(authFeatures({ registration_open: false }), { emailEnabled: false, registrationOpen: false });
});

test('the result is frozen so callers cannot change shared state', () => {
    assert.ok(Object.isFrozen(authFeatures({ email_enabled: true, registration_open: true })));
    assert.ok(Object.isFrozen(SAFE_AUTH_FEATURES));
});
