/**
 * Reading market and AI fields that the backend may leave out (REQ-27).
 *
 * A value is "not available" when it is null or missing, or when the record
 * lists it in `estimated_fields`. The UI shows NOT_AVAILABLE for it and never
 * substitutes a default, so an estimate is never shown as a measured figure.
 */

export const NOT_AVAILABLE = 'Not available';

// Shown only when an AI response does not carry its own disclaimer (the
// pre-REQ-25 response shape). The backend's text replaces it once sent.
export const DEFAULT_AI_DISCLAIMER = 'AI-generated description of market data. Not investment advice.';

const DECIMAL_STRING = /^-?\d+(?:\.\d+)?$/;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/;

/**
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @returns {unknown} the value, or null when it is not available
 */
export function fieldValue(record, field) {
    if (!record || typeof record !== 'object') return null;
    if (Array.isArray(record.estimated_fields) && record.estimated_fields.includes(field)) return null;

    const value = record[field];
    if (value === null || value === undefined) return null;
    if (typeof value === 'number' && !Number.isFinite(value)) return null;
    if (typeof value === 'string' && value.trim() === '') return null;
    return value;
}

/**
 * Numbers may arrive as JSON numbers or as decimal strings (Python Decimal).
 *
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @returns {number | null}
 */
export function numberField(record, field) {
    const value = fieldValue(record, field);
    if (typeof value === 'number') return value;
    if (typeof value === 'string' && DECIMAL_STRING.test(value.trim())) return Number(value);
    return null;
}

/**
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @param {number} digits
 * @param {string} [suffix] appended to available values only, e.g. " ₺"
 * @returns {string}
 */
export function formatNumberField(record, field, digits, suffix = '') {
    const value = numberField(record, field);
    return value === null ? NOT_AVAILABLE : `${value.toFixed(digits)}${suffix}`;
}

/**
 * @param {Record<string, unknown> | null | undefined} record
 * @returns {string | null} `indicators_as_of` when it is a real YYYY-MM-DD date
 */
export function indicatorsAsOf(record) {
    const value = fieldValue(record, 'indicators_as_of');
    if (typeof value !== 'string') return null;

    const match = ISO_DATE.exec(value);
    if (!match) return null;

    const [, year, month, day] = match.map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    const isRealDate = date.getUTCFullYear() === year
        && date.getUTCMonth() === month - 1
        && date.getUTCDate() === day;
    return isRealDate ? value : null;
}

/**
 * A timestamp without a zone is read as UTC (Python's naive utcnow()).
 *
 * @param {unknown} value ISO 8601 timestamp
 * @returns {string | null} "YYYY-MM-DD HH:MM UTC"
 */
export function formatTimestampUTC(value) {
    if (typeof value !== 'string') return null;

    const trimmed = value.trim();
    const match = ISO_DATETIME.exec(trimmed);
    if (!match) return null;

    const date = new Date(match[1] ? trimmed : `${trimmed}Z`);
    if (Number.isNaN(date.getTime())) return null;
    return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/**
 * @param {Record<string, unknown> | null | undefined} response body of
 *   /api/insight or /api/ai/analyze/{symbol}
 * @param {'insight' | 'analysis'} textField
 * @returns {{ text: string, isPlainText: boolean, disclaimer: string,
 *   generatedAt: string | null, inputsAsOf: string | null, isTemplate: boolean }}
 *   `isPlainText` is true for the REQ-25 shape (which carries a disclaimer);
 *   the older shape may still contain markdown.
 */
export function aiProvenance(response, textField) {
    const body = response && typeof response === 'object' ? response : {};
    const text = typeof body[textField] === 'string' ? body[textField] : '';
    const hasDisclaimerField = typeof body.disclaimer === 'string';
    const disclaimer = hasDisclaimerField && body.disclaimer.trim() !== ''
        ? body.disclaimer.trim()
        : DEFAULT_AI_DISCLAIMER;

    return {
        text,
        isPlainText: hasDisclaimerField,
        disclaimer,
        generatedAt: formatTimestampUTC(body.generated_at),
        inputsAsOf: formatTimestampUTC(body.inputs_as_of),
        isTemplate: body.is_fallback === true || body.generated_by === 'template',
    };
}

/**
 * Splits plain text into lines for DOM rendering with text nodes. A line that
 * starts with one of `labels` followed by ":" is returned with that label.
 *
 * @param {string} text
 * @param {string[]} labels
 * @returns {{ label: string | null, text: string }[]}
 */
export function splitLabelledLines(text, labels) {
    const normalized = String(text ?? '')
        .replace(/\r\n?/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/^\n+|\n+$/g, '');
    if (normalized === '') return [];

    return normalized.split('\n').map((line) => {
        const label = labels.find((candidate) => line.startsWith(`${candidate}:`));
        return label
            ? { label, text: line.slice(label.length + 1) }
            : { label: null, text: line };
    });
}
