/**
 * Turns an API error body into text a person can read (REQ-34 c).
 *
 * FastAPI sends `{"detail": "text"}` for most errors and
 * `{"detail": [{loc, msg, type}, ...]}` for a 422. Showing `detail` directly
 * would print "[object Object]" for the second form.
 */

const LOCATIONS = new Set(['body', 'query', 'path']);
const VALUE_ERROR_PREFIX = /^Value error,\s*/i;

function capitalise(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

function cleanMessage(msg) {
    return capitalise(msg.replace(VALUE_ERROR_PREFIX, '').trim());
}

/** The form field an error belongs to, or null for a body-level error. */
function fieldName(loc) {
    if (!Array.isArray(loc) || loc.length < 2 || !LOCATIONS.has(loc[0])) return null;
    const last = loc[loc.length - 1];
    return typeof last === 'string' && last !== '' ? last : null;
}

/**
 * @param {unknown} body the parsed JSON error response
 * @param {string} fallback shown when the body has no readable message
 * @returns {{ message: string, fields: Record<string, string> }}
 *   `fields` maps a field name to its message (first message per field);
 *   `message` is a body-level message, a pointer to the fields, or `fallback`.
 */
export function readableApiError(body, fallback) {
    const detail = body && typeof body === 'object' ? body.detail : undefined;
    if (typeof detail === 'string' && detail.trim() !== '') {
        return { message: detail.trim(), fields: {} };
    }
    if (!Array.isArray(detail)) return { message: fallback, fields: {} };

    const fields = {};
    const general = [];
    for (const item of detail) {
        if (!item || typeof item.msg !== 'string' || item.msg.trim() === '') continue;
        const message = cleanMessage(item.msg);
        const field = fieldName(item.loc);
        if (field === null) general.push(message);
        else if (!(field in fields)) fields[field] = message;
    }

    if (general.length > 0) return { message: general[0], fields };
    if (Object.keys(fields).length > 0) return { message: 'Check the highlighted fields.', fields };
    return { message: fallback, fields: {} };
}
