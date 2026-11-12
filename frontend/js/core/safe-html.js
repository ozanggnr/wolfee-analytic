/**
 * Helpers for putting untrusted text (provider names, AI output, user-typed
 * tickers) into the DOM safely.
 */

const HTML_ENTITIES = Object.freeze({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
});

// API_CONTRACT §1.5
const SYMBOL_PATTERN = /^[A-Za-z0-9]+(?:[.\-=][A-Za-z0-9]+)*$/;
const SYMBOL_MAX_LENGTH = 20;

/**
 * @param {unknown} value
 * @returns {string}
 */
export function escapeHTML(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, (char) => HTML_ENTITIES[char]);
}

/**
 * @param {unknown} symbol
 * @returns {boolean}
 */
export function isValidSymbol(symbol) {
    return typeof symbol === 'string'
        && symbol.length >= 1
        && symbol.length <= SYMBOL_MAX_LENGTH
        && SYMBOL_PATTERN.test(symbol);
}

/**
 * Converts plain AI text to display HTML: markdown emphasis and headings are
 * removed, everything is escaped, line breaks become <br>.
 *
 * @param {unknown} text
 * @param {{ highlightLabels?: string[] }} [options] labels that are wrapped in
 *   <span class="ai-label"> when they start a line, e.g. "Decision"
 * @returns {string}
 */
export function aiTextToHTML(text, options = {}) {
    if (text === null || text === undefined) return '';

    const plain = String(text)
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/#{1,6}\s/g, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim();

    const labels = (options.highlightLabels || []).map(escapeRegExp);
    const escaped = escapeHTML(plain);
    const highlighted = labels.length > 0
        ? escaped.replace(new RegExp(`^(${labels.join('|')}):`, 'gm'), '<span class="ai-label">$1:</span>')
        : escaped;

    return highlighted.replace(/\n/g, '<br>');
}

/**
 * @param {string} value
 * @returns {string}
 */
function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
