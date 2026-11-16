/**
 * Loads GET /api/auth/config once and marks <html> with the result (REQ-37):
 *   data-email-enabled="true|false"      css/auth.css hides [data-needs-email] unless "true"
 *   data-registration-open="true|false"  css/auth.css swaps the register form for a notice
 * Until the response arrives the safe state applies: no email features, register visible.
 */

import { authFeatures, SAFE_AUTH_FEATURES } from './core/auth-config.js?v=16.2';

function apply(features) {
    const root = document.documentElement;
    root.dataset.emailEnabled = String(features.emailEnabled);
    root.dataset.registrationOpen = String(features.registrationOpen);
    // If a now-hidden email view is open, fall back to sign in
    if (!features.emailEnabled && typeof window.switchAuthTab === 'function') {
        const open = ['forgot-form', 'resend-form'].some(id => {
            const el = document.getElementById(id);
            return el && !el.classList.contains('hidden');
        });
        if (open) window.switchAuthTab('login');
    }
}

async function loadAuthConfig() {
    apply(SAFE_AUTH_FEATURES);
    const base = typeof API_URL !== 'undefined' ? API_URL : '';
    try {
        const res = await fetch(`${base}/api/auth/config`, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        apply(authFeatures(await res.json()));
    } catch (err) {
        console.warn('Account config unavailable; email features hidden:', err.message);
        apply(SAFE_AUTH_FEATURES);
    }
}

loadAuthConfig();
