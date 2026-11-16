/**
 * Which account features to show, from GET /api/auth/config (REQ-37):
 * {"email_enabled": bool, "registration_open": bool}.
 *
 * When the call fails or the body is not that shape, the email features
 * (forgot password, resend verification) are hidden and register stays
 * visible: a link that cannot send mail is worse than no link, and the
 * server still decides whether a registration is accepted.
 */

export const SAFE_AUTH_FEATURES = Object.freeze({ emailEnabled: false, registrationOpen: true });

/**
 * @param {unknown} body the parsed response, or null when the call failed
 * @returns {Readonly<{ emailEnabled: boolean, registrationOpen: boolean }>}
 */
export function authFeatures(body) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) return SAFE_AUTH_FEATURES;
    return Object.freeze({
        emailEnabled: body.email_enabled === true,
        registrationOpen: body.registration_open !== false,
    });
}
