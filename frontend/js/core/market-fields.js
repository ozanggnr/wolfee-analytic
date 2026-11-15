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
 * The day's direction. A null `change_pct` (no previous close) is unknown,
 * not unchanged, so it has no direction.
 *
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} [field]
 * @returns {'up' | 'down' | 'flat' | null}
 */
export function changeDirection(record, field = 'change_pct') {
    const value = numberField(record, field);
    if (value === null) return null;
    if (value > 0) return 'up';
    return value < 0 ? 'down' : 'flat';
}

/**
 * @param {'up' | 'down' | 'flat' | null} direction from changeDirection
 * @returns {string} the CSS class for that direction; flat and unknown are neutral
 */
export function directionClass(direction) {
    if (direction === 'up') return 'is-gain';
    return direction === 'down' ? 'is-loss' : '';
}

/**
 * A percentage change as display text: "▲ 1.25%" (arrow style) or "+1.25%"
 * (signed style). A missing value is NOT_AVAILABLE, never "0.00%".
 *
 * @param {Record<string, unknown> | null | undefined} record
 * @param {{ field?: string, digits?: number, style?: 'arrow' | 'signed' }} [options]
 * @returns {string}
 */
export function formatChange(record, options = {}) {
    const { field = 'change_pct', digits = 2, style = 'arrow' } = options;
    const value = numberField(record, field);
    if (value === null) return NOT_AVAILABLE;

    if (style === 'signed') return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
    const arrow = value > 0 ? '▲ ' : value < 0 ? '▼ ' : '';
    return `${arrow}${Math.abs(value).toFixed(digits)}%`;
}

/**
 * A price as display text. Missing, zero and negative prices are not
 * available (providers send 0 for values they do not have).
 *
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @param {string} currency symbol appended after the number
 * @param {number} [digits]
 * @returns {string}
 */
export function formatPrice(record, field, currency, digits = 2) {
    const value = numberField(record, field);
    return value !== null && value > 0 ? `${value.toFixed(digits)} ${currency}` : NOT_AVAILABLE;
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
 * An indicator (rsi, ma_20, volatility, volatility_pct) counts only when the
 * record says when it was computed: values without a real `indicators_as_of`
 * are the workers' single-day estimates and are not available (REQ-29).
 *
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @returns {unknown}
 */
export function indicatorField(record, field) {
    return indicatorsAsOf(record) === null ? null : fieldValue(record, field);
}

/**
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @returns {number | null}
 */
export function indicatorNumber(record, field) {
    return indicatorsAsOf(record) === null ? null : numberField(record, field);
}

/**
 * @param {Record<string, unknown> | null | undefined} record
 * @param {string} field
 * @param {number} digits
 * @param {string} [suffix]
 * @returns {string}
 */
export function formatIndicatorField(record, field, digits, suffix = '') {
    const value = indicatorNumber(record, field);
    return value === null ? NOT_AVAILABLE : `${value.toFixed(digits)}${suffix}`;
}

/**
 * Parses an ISO 8601 timestamp. A timestamp without a zone is read as UTC
 * (Python's naive utcnow()), never as the viewer's local time.
 *
 * @param {unknown} value
 * @returns {Date | null}
 */
export function parseTimestamp(value) {
    if (typeof value !== 'string') return null;

    const trimmed = value.trim();
    const match = ISO_DATETIME.exec(trimmed);
    if (!match) return null;

    const date = new Date(match[1] ? trimmed : `${trimmed}Z`);
    return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Formats a timestamp in the viewer's time zone, or in `timeZone` when given.
 * A timestamp without a zone is read as UTC (Python's naive utcnow()).
 *
 * @param {unknown} value ISO 8601 timestamp
 * @param {{ timeZone?: string }} [options] IANA zone; omit for the viewer's
 * @returns {string | null} "YYYY-MM-DD HH:MM <zone>", e.g. "2026-11-14 09:05 GMT+3"
 */
export function formatTimestamp(value, options = {}) {
    const date = parseTimestamp(value);
    if (date === null) return null;

    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
        timeZone: options.timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
        timeZoneName: 'short',
    }).formatToParts(date).map(({ type, value: part }) => [type, part]));
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} ${parts.timeZoneName}`;
}

/**
 * @param {Record<string, unknown> | null | undefined} response body of
 *   /api/insight or /api/ai/analyze/{symbol}
 * @param {'insight' | 'analysis'} textField
 * @param {{ timeZone?: string }} [options] passed to formatTimestamp
 * @returns {{ text: string, isPlainText: boolean, disclaimer: string,
 *   generatedAt: string | null, inputsAsOf: string | null, isTemplate: boolean }}
 *   `isPlainText` is true for the REQ-25 shape (which carries a disclaimer);
 *   the older shape may still contain markdown.
 */
export function aiProvenance(response, textField, options = {}) {
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
        generatedAt: formatTimestamp(body.generated_at, options),
        inputsAsOf: formatTimestamp(body.inputs_as_of, options),
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
