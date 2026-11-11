// Bridge for the existing non-module scripts (ui.js, main.js, portfolio.js),
// which cannot use `import`. New code imports from ./safe-html.js directly.
import { escapeHTML, isValidSymbol, aiTextToHTML } from './safe-html.js';

window.WolfeeSafe = Object.freeze({ escapeHTML, isValidSymbol, aiTextToHTML });
