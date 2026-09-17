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

        const loggedInHTML = user ? `
            <div class="user-chip" id="user-profile-chip" title="${safeEmail}">
                <span class="user-avatar">👤</span>
                <span class="user-email-text">${safeName}</span>
                <button class="icon-btn logout-btn" onclick="logoutUser()" title="Log out">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                </button>
            </div>
        ` : `
            <button class="nav-auth-btn gradient-btn" onclick="openAuthModal('login')">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                Sign In
            </button>
        `;

        if (desktopContainer) desktopContainer.innerHTML = loggedInHTML;
        if (mobileContainer) mobileContainer.innerHTML = loggedInHTML;

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
        modal.classList.remove('hidden');
        switchAuthTab(tab);
    };

    window.closeAuthModal = function () {
        const modal = document.getElementById('auth-modal');
        if (modal) modal.classList.add('hidden');
        clearAuthAlerts();
    };

    window.switchAuthTab = function (tab) {
        document.querySelectorAll('.auth-tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.auth-form-view').forEach(view => view.classList.add('hidden'));

        const targetBtn = document.getElementById(`auth-tab-${tab}`);
        const targetView = document.getElementById(`${tab}-form`) || document.getElementById(`auth-view-${tab}`);

        if (targetBtn) targetBtn.classList.add('active');
        if (targetView) targetView.classList.remove('hidden');

        const titleEl = document.getElementById('auth-modal-title');
        const subEl = document.getElementById('auth-modal-subtitle');
        if (titleEl && subEl) {
            if (tab === 'login') {
                titleEl.textContent = 'Welcome Back';
                subEl.textContent = 'Sign in to access your cloud watchlist and live analytics.';
            } else if (tab === 'register') {
                titleEl.textContent = 'Create Account';
                subEl.textContent = 'Create a secure Wolfee account to sync your portfolio anywhere.';
            } else if (tab === 'forgot') {
                titleEl.textContent = 'Reset Password';
                subEl.textContent = 'Enter your account email to receive secure recovery instructions.';
            } else if (tab === 'resend') {
                titleEl.textContent = 'Resend Verification';
                subEl.textContent = 'Enter your email to request a new account activation link.';
            } else if (tab === 'reset') {
                titleEl.textContent = 'New Password';
                subEl.textContent = 'Create a strong, secure password for your Wolfee account.';
            }
        }

        clearAuthAlerts();
    };

    function showAuthAlert(message, isSuccess = false) {
        const alertEl = document.getElementById('auth-alert');
        if (!alertEl) return;
        alertEl.textContent = message;
        alertEl.className = 'auth-alert ' + (isSuccess ? 'auth-alert-success' : 'auth-alert-error');
        alertEl.classList.remove('hidden');
    }

    function clearAuthAlerts() {
        const alertEl = document.getElementById('auth-alert');
        if (alertEl) {
            alertEl.textContent = '';
            alertEl.classList.add('hidden');
        }
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
        const captcha = document.getElementById('reg-captcha')?.value || 'dev-captcha-pass';

        if (!email || !password) {
            showAuthAlert('Please fill in all required fields.');
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
                body: JSON.stringify({ email, password, captcha_token: captcha })
            });

            const data = await res.json();

            if (res.ok) {
                // Anti-enumeration generic confirmation
                showAuthAlert(data.message || 'Verification link sent! Please check your email inbox.', true);
                document.getElementById('register-form')?.reset();
            } else {
                showAuthAlert(data.detail || 'Registration failed. Please try again.');
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
        const captcha = document.getElementById('login-captcha')?.value || 'dev-captcha-pass';

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
                body: JSON.stringify({ email, password, captcha_token: captcha })
            });

            const data = await res.json();

            if (res.ok) {
                window.currentUser = data.user;
                try {
                    localStorage.setItem('wolfee_cached_user', JSON.stringify(data.user));
                } catch (e) {}
                updateAuthUI(data.user);
                closeAuthModal();
                // Refresh portfolio page
                if (typeof renderPortfolio === 'function') renderPortfolio();
            } else {
                // Show generic error
                showAuthAlert(data.detail || 'Invalid email or password.');

                // Check if CAPTCHA was requested
                if (res.headers.get('X-Captcha-Required') === 'true' || res.status === 400) {
                    const captchaWrap = document.getElementById('login-captcha-wrap');
                    if (captchaWrap) captchaWrap.classList.remove('hidden');
                }
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

            const data = await res.json();
            showAuthAlert(data.message || 'If registered, reset instructions have been sent.', true);
        } catch (err) {
            showAuthAlert('Network error. Please try again later.');
        } finally {
            if (btn) btn.disabled = false;
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

            const data = await res.json();
            if (res.ok) {
                showAuthAlert(data.message || 'Password successfully reset. Please log in.', true);
                setTimeout(() => switchAuthTab('login'), 2000);
            } else {
                showAuthAlert(data.detail || 'Password reset failed.');
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
