// Bridge for the existing non-module scripts (ui.js, main.js, portfolio.js),
// which cannot use `import`. New code imports from ./safe-html.js directly.
// The ?v= stamps follow the asset version in index.html; bump them together so
// browsers do not keep a cached copy of a changed module.
import { escapeHTML, isValidSymbol, aiTextToHTML } from './safe-html.js?v=16.1';
import * as fields from './market-fields.js?v=16.1';

window.WolfeeSafe = Object.freeze({ escapeHTML, isValidSymbol, aiTextToHTML });
window.WolfeeFields = Object.freeze({ ...fields });
