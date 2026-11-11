import { test } from 'node:test';
import assert from 'node:assert/strict';

import { escapeHTML, isValidSymbol, aiTextToHTML } from '../js/core/safe-html.js';

test('escapeHTML neutralises markup characters', () => {
    const result = escapeHTML(`<img src=x onerror="alert('x')">&`);

    assert.equal(result, '&lt;img src=x onerror=&quot;alert(&#039;x&#039;)&quot;&gt;&amp;');
});

test('escapeHTML returns an empty string for null and undefined', () => {
    assert.equal(escapeHTML(null), '');
    assert.equal(escapeHTML(undefined), '');
});

test('escapeHTML keeps zero and other falsy non-null values', () => {
    assert.equal(escapeHTML(0), '0');
});

test('isValidSymbol accepts the symbol forms defined in API_CONTRACT 1.5', () => {
    for (const symbol of ['THYAO', 'THYAO.IS', 'AAPL', 'GC=F', 'BRK-B', 'USDTRY=X', 'a1']) {
        assert.equal(isValidSymbol(symbol), true, symbol);
    }
});

test('isValidSymbol rejects markup, separators at the edges and overlong input', () => {
    const invalid = ['', ' ', '"><img>', 'A B', '.IS', 'THYAO.', 'A..B', "A'B", 'A'.repeat(21), null, undefined, 42];

    for (const symbol of invalid) {
        assert.equal(isValidSymbol(symbol), false, String(symbol));
    }
});

test('aiTextToHTML escapes markup that arrives in model output', () => {
    const result = aiTextToHTML('Buy <script>alert(1)</script> now');

    assert.equal(result, 'Buy &lt;script&gt;alert(1)&lt;/script&gt; now');
});

test('aiTextToHTML strips markdown emphasis and headings and keeps line breaks', () => {
    const result = aiTextToHTML('## Title\n**Bold** and *italic*\n\n\n\nNext');

    assert.equal(result, 'Title<br>Bold and italic<br><br>Next');
});

test('aiTextToHTML highlights only the requested line-leading labels', () => {
    const result = aiTextToHTML('Decision: wait\nNo Decision: here', { highlightLabels: ['Decision'] });

    assert.equal(result, '<span class="ai-label">Decision:</span> wait<br>No Decision: here');
});

test('aiTextToHTML returns an empty string for missing text', () => {
    assert.equal(aiTextToHTML(null), '');
});
