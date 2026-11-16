/**
 * Wolfee Analytics - Authentication & Session Client
 * - Server-side session verification via HttpOnly cookies
 * - Automatic CSRF token handling for state-changing requests
 * - Password policy validation (>= 10 characters, common password prevention)
 * - Anti-enumeration generic feedback messaging
 * - CAPTCHA integration
 */

(function () {
    // Immediately restore cached session from localStorage for instant, zero-flicker UI
    let initialUser = null;
    try {
        const rawUser = localStorage.getItem('wolfee_cached_user');
        if (rawUser) {
            initialUser = JSON.parse(rawUser);
        }
    } catch (e) {
        console.warn('Failed to parse cached user:', e);
    }
    window.currentUser = initialUser;

    // ============================================================
    // CSRF & SECURE FETCH HELPERS
    // ============================================================
    function getCookie(name) {
        const matches = document.cookie.match(new RegExp(
            '(?:^|; )' + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + '=([^;]*)'
        ));
        return matches ? decodeURIComponent(matches[1]) : null;
    }

    window.getCSRFToken = function () {
        return getCookie('csrf_token') || '';
    };

    /**
     * Enhanced fetch that automatically includes credentials (cookies)
     * and sets X-CSRF-Token on state-changing requests.
     */
    window.authFetch = async function (url, options = {}) {
        const opts = Object.assign({}, options);
        opts.credentials = 'include'; // Ensure httpOnly cookies are sent
        opts.headers = Object.assign({}, opts.headers);

        const method = (opts.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            let token = getCSRFToken();
            if (!token) {
                // Pre-fetch token if missing
                try {
                    const res = await fetch(`${API_URL}/api/auth/csrf`, { credentials: 'include' });
                    const d = await res.json();
                    token = d.csrf_token || getCSRFToken();
                } catch (e) {
                    console.warn('Failed to pre-fetch CSRF token:', e);
                }
            }
            if (token) {
                opts.headers['X-CSRF-Token'] = token;
            }
        }

        return fetch(url, opts);
    };

    // ============================================================
    // AUTH STATUS CHECK (with session caching)
    // ============================================================
    window.checkAuthStatus = async function () {
        try {
            const res = await authFetch(`${API_URL}/api/auth/me`);
            if (res.ok) {
                const user = await res.json();
                window.currentUser = user;
                try {
                    localStorage.setItem('wolfee_cached_user', JSON.stringify(user));
                } catch (e) {}
                updateAuthUI(user);
                document.dispatchEvent(new CustomEvent('wolfee_auth_changed', { detail: { user } }));
                return user;
            } else if (res.status === 401) {
                // Session expired or invalidated on server
                window.currentUser = null;
                try {
                    localStorage.removeItem('wolfee_cached_user');
                    localStorage.removeItem('wolfee_cached_watchlist');
                } catch (e) {}
                updateAuthUI(null);
                document.dispatchEvent(new CustomEvent('wolfee_auth_changed', { detail: { user: null } }));
                return null;
            } else {
                // Other server response: preserve cached user if available
                if (window.currentUser) {
                    updateAuthUI(window.currentUser);
                    return window.currentUser;
                }
                updateAuthUI(null);
                return null;
            }
        } catch (err) {
            console.warn('Auth check network warning:', err);
            // On temporary network disconnection, preserve cached user so session is not lost
            if (window.currentUser) {
                updateAuthUI(window.currentUser);
                return window.currentUser;
            }
            updateAuthUI(null);
            return null;
        }
    };

    // ============================================================
    // HTML ESCAPING HELPER (DOM XSS Mitigation)
    // ============================================================
    function escapeHTML(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
    window.escapeHTML = escapeHTML;

    // ============================================================
    // UI UPDATES (Navbar buttons, profile badge)
    // ============================================================
    function updateAuthUI(user) {
        const desktopContainer = document.getElementById('nav-auth-container');
        const mobileContainer = document.getElementById('mobile-auth-container');

        const safeEmail = user ? escapeHTML(user.email) : '';
        const safeName = user ? escapeHTML(user.email.split('@')[0]) : '';

        const signInHTML = `
            <button type="button" class="nav-auth-btn gradient-btn" onclick="openAuthModal('login')">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                Sign in
            </button>
        `;

        // Header (desktop): name and a log-out icon button
        const desktopHTML = user ? `
            <div class="user-chip" id="user-profile-chip" title="${safeEmail}">
                <span class="user-email-text">${safeName}</span>
                <button type="button" class="icon-btn logout-btn" onclick="logoutUser()" title="Log out" aria-label="Log out">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                </button>
            </div>
        ` : signInHTML;

        // Account sheet (mobile): the full email and a Log out button
        const mobileHTML = user ? `
            <div class="account-details">
                <span class="account-label">Signed in as</span>
                <span class="account-email">${safeEmail}</span>
            </div>
            <button type="button" class="btn-secondary account-logout" onclick="logoutUser(); if (typeof closeAccountSheet === 'function') closeAccountSheet();">Log out</button>
        ` : signInHTML;

        if (desktopContainer) desktopContainer.innerHTML = desktopHTML;
        if (mobileContainer) mobileContainer.innerHTML = mobileHTML;

        // If on portfolio tab, re-render portfolio to show cloud watchlist vs session
        if (typeof renderPortfolio === 'function') {
            renderPortfolio();
        }
    }

    // ============================================================
    // AUTH MODAL MANAGEMENT
    // ============================================================
    window.openAuthModal = function (tab = 'login') {
        const modal = document.getElementById('auth-modal');
        if (!modal) return;
        if (modal.classList.contains('hidden') && typeof _modalReturnFocus !== 'undefined') {
            _modalReturnFocus = document.activeElement;
        }
        modal.classList.remove('hidden');
        document.body.classList.add('no-scroll');
        switchAuthTab(tab);
        // Focus the first field of the open form
        const firstField = modal.querySelector('.auth-form-view:not(.hidden) input:not([type="hidden"])');
        if (firstField) firstField.focus();
    };

    window.closeAuthModal = function () {
        const modal = document.getElementById('auth-modal');
        if (modal && !modal.classList.contains('hidden') && typeof closeModalWithAnim === 'function') closeModalWithAnim();
        else if (modal) modal.classList.add('hidden');
        clearAuthAlerts();
    };

    window.switchAuthTab = function (tab) {
        document.querySelectorAll('.auth-tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.auth-form-view').forEach(view => view.classList.add('hidden'));

        const targetBtn = document.getElementById(`auth-tab-${tab}`);
        const targetView = document.getElementById(`${tab}-form`) || document.getElementById(`auth-view-${tab}`);

        document.querySelectorAll('.auth-tab-btn').forEach(btn => btn.setAttribute('aria-pressed', String(btn === targetBtn)));
        if (targetBtn) targetBtn.classList.add('active');
        if (targetView) targetView.classList.remove('hidden');

        const titleEl = document.getElementById('auth-modal-title');
        const subEl = document.getElementById('auth-modal-subtitle');
        if (titleEl && subEl) {
            if (tab === 'login') {
                titleEl.textContent = 'Sign in';
                subEl.textContent = 'Sign in to sync your watchlist across devices.';
            } else if (tab === 'register') {
                titleEl.textContent = 'Create an account';
                subEl.textContent = 'An account keeps your watchlist on every device you sign in on.';
            } else if (tab === 'forgot') {
                titleEl.textContent = 'Reset your password';
                subEl.textContent = 'Enter the email address of your account.';
            } else if (tab === 'resend') {
                titleEl.textContent = 'Resend verification email';
                subEl.textContent = 'We send a new activation link to this address.';
            } else if (tab === 'reset') {
                titleEl.textContent = 'Set a new password';
                subEl.textContent = 'Choose a password of at least 10 characters.';
            }
        }

        clearAuthAlerts();
    };

    function showAuthAlert(message, isSuccess = false) {
        const alertEl = document.getElementById('auth-alert');
        if (!alertEl) return;
        alertEl.textContent = message;
        alertEl.className = 'auth-alert ' + (isSuccess ? 'auth-alert-success' : 'auth-alert-error');
        alertEl.setAttribute('role', isSuccess ? 'status' : 'alert');
        alertEl.classList.remove('hidden');
    }

    function clearAuthAlerts() {
        const alertEl = document.getElementById('auth-alert');
        if (alertEl) {
            alertEl.textContent = '';
            alertEl.classList.add('hidden');
        }
        document.querySelectorAll('#auth-modal [data-api-field]').forEach((wrap) => {
            const error = wrap.querySelector('.field-error');
            if (error) { error.textContent = ''; error.hidden = true; }
            wrap.querySelectorAll('input').forEach((input) => input.removeAttribute('aria-invalid'));
        });
    }

    /** Reads a JSON error body; null when the body is not JSON. */
    async function readJSON(res) {
        try { return await res.json(); } catch (e) { return null; }
    }

    /**
     * Shows an API error as readable text (REQ-34 c): a 422 message goes under
     * its field in `form`, other messages in the alert. Never "[object Object]".
     */
    function showApiError(form, data, fallback) {
        const api = window.WolfeeApiErrors;
        const result = api
            ? api.readableApiError(data, fallback)
            : { message: data && typeof data.detail === 'string' ? data.detail : fallback, fields: {} };
        const unplaced = [];
        let firstInvalid = null;
        Object.entries(result.fields).forEach(([field, message]) => {
            const wrap = form ? form.querySelector(`[data-api-field="${field}"]`) : null;
            const error = wrap ? wrap.querySelector('.field-error') : null;
            const input = wrap ? wrap.querySelector('input') : null;
            if (!error) { unplaced.push(message); return; }
            error.textContent = message;
            error.hidden = false;
            if (input) {
                input.setAttribute('aria-invalid', 'true');
                firstInvalid = firstInvalid || input;
            }
        });
        showAuthAlert(unplaced[0] || result.message);
        if (firstInvalid) firstInvalid.focus();
    }

    // ============================================================
    // PASSWORD POLICY CLIENT VALIDATION
    // ============================================================
    window.checkPasswordPolicyClient = function (password) {
        if (!password) return { valid: false, message: 'Password required' };
        if (password.length < 10) {
            return { valid: false, message: 'Minimum 10 characters required' };
        }
        const lower = password.toLowerCase();
        const commonList = ['1234567890', 'password123', 'admin12345', 'qwerty1234', 'welcome123', 'iloveyou12'];
        if (commonList.some(c => lower.includes(c))) {
            return { valid: false, message: 'Password is too common and easily guessed' };
        }
        return { valid: true, message: 'Strong password' };
    };

    // ============================================================
    // ACTIONS: REGISTER, LOGIN, LOGOUT, FORGOT
    // ============================================================
    window.handleRegisterSubmit = async function (event) {
        event.preventDefault();
        clearAuthAlerts();

        const email = document.getElementById('reg-email')?.value?.trim();
        const password = document.getElementById('reg-password')?.value;
        const confirm = document.getElementById('reg-confirm')?.value;
        const inviteCode = document.getElementById('reg-invite')?.value?.trim() || '';

        if (!email || !password) {
            showAuthAlert('Please fill in all required fields.');
            return;
        }

        // Registration is invite-only; no CAPTCHA (decision D1). Agent 2 checks the code.
        if (inviteCode === '') {
            showApiError(document.getElementById('register-form'),
                { detail: [{ loc: ['body', 'invite_code'], msg: 'Enter your invite code.' }] },
                'Enter your invite code.');
            return;
        }

        if (password !== confirm) {
            showAuthAlert('Passwords do not match.');
            return;
        }

        const policy = checkPasswordPolicyClient(password);
        if (!policy.valid) {
            showAuthAlert(policy.message);
            return;
        }

        const btn = document.getElementById('reg-submit-btn');
        if (btn) btn.disabled = true;

        try {
            const res = await authFetch(`${API_URL}/api/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, invite_code: inviteCode })
            });

            const data = await readJSON(res);

            if (res.ok) {
                // Anti-enumeration generic confirmation
                showAuthAlert((data && data.message) || 'Verification link sent! Please check your email inbox.', true);
                document.getElementById('register-form')?.reset();
            } else {
                showApiError(document.getElementById('register-form'), data, 'Registration failed. Please try again.');
            }
        } catch (err) {
            showAuthAlert('Network error. Please try again later.');
        } finally {
            if (btn) btn.disabled = false;
        }
    };

    window.handleLoginSubmit = async function (event) {
        event.preventDefault();
        clearAuthAlerts();

        const email = document.getElementById('login-email')?.value?.trim();
        const password = document.getElementById('login-password')?.value;

        if (!email || !password) {
            showAuthAlert('Please enter both email and password.');
            return;
        }

        const btn = document.getElementById('login-submit-btn');
        if (btn) btn.disabled = true;

        try {
            const res = await authFetch(`${API_URL}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await readJSON(res);

            if (res.ok && data && data.user) {
                window.currentUser = data.user;
                try {
                    localStorage.setItem('wolfee_cached_user', JSON.stringify(data.user));
                } catch (e) {}
                updateAuthUI(data.user);
                closeAuthModal();
                // Watchlist and the Portfolio page (ledger-page.js) refresh on this event
                document.dispatchEvent(new CustomEvent('wolfee_auth_changed', { detail: { user: data.user } }));
                if (typeof renderPortfolio === 'function') renderPortfolio();
            } else {
                showApiError(document.getElementById('login-form'), data, 'Invalid email or password.');
            }
        } catch (err) {
            showAuthAlert('Network error. Please try again later.');
        } finally {
            if (btn) btn.disabled = false;
        }
    };

    window.handleForgotPasswordSubmit = async function (event) {
        event.preventDefault();
        clearAuthAlerts();

        const email = document.getElementById('forgot-email')?.value?.trim();
        if (!email) {
            showAuthAlert('Please enter your email address.');
            return;
        }

        const btn = document.getElementById('forgot-submit-btn');
        if (btn) btn.disabled = true;

        try {
            const res = await authFetch(`${API_URL}/api/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });

            const data = await readJSON(res);
            if (res.ok) {
                showAuthAlert((data && data.message) || 'If registered, reset instructions have been sent.', true);
            } else {
                showApiError(document.getElementById('forgot-form'), data, 'The reset link could not be sent. Try again later.');
            }
        } catch (err) {
            showAuthAlert('Network error. Please try again later.');
        } finally {
            if (btn) btn.disabled = false;
        }
    };

    window.handleResendVerificationSubmit = async function (event) {
        event.preventDefault();
        clearAuthAlerts();

        const form = document.getElementById('resend-form');
        const email = document.getElementById('resend-email')?.value?.trim();
        if (!email) {
            showAuthAlert('Please enter your email address.');
            return;
        }

        try {
            const res = await authFetch(`${API_URL}/api/auth/resend-verification`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const data = await readJSON(res);
            if (res.ok) {
                showAuthAlert((data && data.message) || 'If the address needs verifying, a new link has been sent.', true);
            } else {
                showApiError(form, data, 'The verification email could not be sent. Try again later.');
            }
        } catch (err) {
            showAuthAlert('Network error. Please try again later.');
        }
    };

    window.handleResetPasswordSubmit = async function (event) {
        event.preventDefault();
        clearAuthAlerts();

        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('reset_token');
        const new_password = document.getElementById('reset-new-password')?.value;
        const confirm = document.getElementById('reset-confirm-password')?.value;

        if (!token) {
            showAuthAlert('Reset token missing or expired from URL.');
            return;
        }

        if (new_password !== confirm) {
            showAuthAlert('Passwords do not match.');
            return;
        }

        const policy = checkPasswordPolicyClient(new_password);
        if (!policy.valid) {
            showAuthAlert(policy.message);
            return;
        }

        try {
            const res = await authFetch(`${API_URL}/api/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password })
            });

            const data = await readJSON(res);
            if (res.ok) {
                showAuthAlert((data && data.message) || 'Password successfully reset. Please log in.', true);
                setTimeout(() => switchAuthTab('login'), 2000);
            } else {
                showApiError(document.getElementById('reset-form'), data, 'Password reset failed.');
            }
        } catch (err) {
            showAuthAlert('Network error. Please try again.');
        }
    };

    window.logoutUser = async function () {
        try {
            await authFetch(`${API_URL}/api/auth/logout`, { method: 'POST' });
        } catch (e) {
            console.warn('Logout error:', e);
        }
        window.currentUser = null;
        try {
            localStorage.removeItem('wolfee_cached_user');
            localStorage.removeItem('wolfee_cached_watchlist');
            localStorage.removeItem('wolfee_cached_summary');
        } catch (e) {}
        updateAuthUI(null);
        document.dispatchEvent(new CustomEvent('wolfee_auth_changed', { detail: { user: null } }));
        if (typeof renderPortfolio === 'function') renderPortfolio();
    };

    // ============================================================
    // URL PARAMETER DETECTION & PERSISTENT SESSION RESTORE
    // ============================================================
    document.addEventListener('DOMContentLoaded', () => {
        // Apply cached user immediately on DOM ready (zero delay)
        if (window.currentUser) {
            updateAuthUI(window.currentUser);
        }

        // Validate/refresh session in background
        checkAuthStatus();

        const params = new URLSearchParams(window.location.search);
        if (params.get('verified') === 'true') {
            openAuthModal('login');
            showAuthAlert('Email verified successfully! You may now sign in.', true);
        } else if (params.get('reset_token')) {
            openAuthModal('reset');
        }
    });

})();
