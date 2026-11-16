/**
 * Portfolio page controller (REQ-32): create and select a portfolio, record
 * and void transactions, and show holdings and performance from
 * /api/v1/portfolios. Loaded as an ES module from index.html; ui.js switchTab
 * announces the tab with the `wolfee_tab_changed` event.
 *
 * The page never computes a figure: everything shown comes from the API.
 */

import * as api from './ledger-api.js';
import * as render from './ledger-render.js';
import { buildTransactionBody, transactionFieldsForType, QUANTITY_LABELS } from '../core/ledger-format.js';

const SELECTED_KEY = 'wolfee_ledger_selected';
const NAME_MAX_LENGTH = 100;
const TX_FIELDS = ['type', 'symbol', 'quantity', 'price', 'fee', 'currency', 'fx_rate_to_base', 'trade_date', 'note'];

const $ = (id) => document.getElementById(id);

let state = Object.freeze({
    loadedFor: null,          // user id the portfolios were loaded for
    portfolios: [],
    selectedId: null,
    transactions: { items: [], total: 0 },
    confirmingVoid: null,
});

function setState(patch) {
    state = Object.freeze({ ...state, ...patch });
}

function isVisible() {
    const view = $('ledger-view');
    return Boolean(view) && !view.classList.contains('hidden');
}

function currentUser() {
    return window.currentUser || null;
}

function readStoredSelection() {
    try { return localStorage.getItem(SELECTED_KEY); } catch (err) { return null; }
}

function storeSelection(id) {
    try { localStorage.setItem(SELECTED_KEY, String(id)); } catch (err) { /* per-viewer convenience only */ }
}

function todayISO() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function announce(text) {
    const status = $('ledger-announce');
    if (status) status.textContent = text;
}

// ---------- Field errors ----------

function setFieldError(form, field, message) {
    const wrap = form.querySelector(`[data-field="${field}"]`);
    if (!wrap) return false;
    const input = wrap.querySelector('input, select, textarea');
    const error = wrap.querySelector('.field-error');
    if (input) input.setAttribute('aria-invalid', message ? 'true' : 'false');
    if (error) {
        error.textContent = message || '';
        error.hidden = !message;
    }
    return true;
}

function clearFormErrors(form) {
    form.querySelectorAll('[data-field]').forEach(wrap => setFieldError(form, wrap.dataset.field, null));
    const alert = form.querySelector('.form-alert');
    if (alert) { alert.textContent = ''; alert.hidden = true; }
}

/** Shows per-field messages; returns the messages that have no field on this form. */
function showFieldErrors(form, fields) {
    const unplaced = [];
    for (const [field, message] of Object.entries(fields)) {
        if (!setFieldError(form, field, message)) unplaced.push(message);
    }
    const firstInvalid = form.querySelector('[aria-invalid="true"]');
    if (firstInvalid) firstInvalid.focus();
    return unplaced;
}

function showFormAlert(form, message) {
    const alert = form.querySelector('.form-alert');
    if (!alert) return;
    alert.textContent = message;
    alert.hidden = !message;
}

function setBusy(button, busy, busyLabel) {
    if (!button) return;
    if (busy) {
        button.dataset.label = button.textContent;
        button.textContent = busyLabel;
    } else if (button.dataset.label) {
        button.textContent = button.dataset.label;
    }
    button.disabled = busy;
    button.setAttribute('aria-busy', busy ? 'true' : 'false');
}

// ---------- Layout states ----------

function showSignedOut() {
    $('ledger-signed-out').classList.remove('hidden');
    $('ledger-app').classList.add('hidden');
}

function showApp() {
    $('ledger-signed-out').classList.add('hidden');
    $('ledger-app').classList.remove('hidden');
}

function setHasPortfolio(has) {
    $('ledger-toolbar').hidden = !has;
    $('ledger-content').hidden = !has;
    $('ledger-no-portfolio').hidden = has;
}

function showLoading() {
    $('ledger-summary').innerHTML = render.loadingHTML('Loading summary');
    $('ledger-holdings').innerHTML = render.loadingHTML('Loading holdings');
    $('ledger-transactions').innerHTML = render.loadingHTML('Loading transactions');
}

// ---------- Portfolios ----------

async function loadPortfolios() {
    const user = currentUser();
    if (!user) { showSignedOut(); return; }
    showApp();
    $('ledger-page-error').innerHTML = '';
    $('ledger-portfolio-select').innerHTML = '';

    const result = await api.listPortfolios();
    if (!result.ok) {
        setHasPortfolio(false);
        $('ledger-no-portfolio').hidden = true;
        $('ledger-page-error').innerHTML = render.errorHTML(result.error.message, 'reload');
        return;
    }

    const portfolios = result.data.items || [];
    const stored = readStoredSelection();
    const selected = portfolios.find(p => String(p.id) === stored) || portfolios[0] || null;
    setState({ loadedFor: user.id ?? user.email ?? true, portfolios, selectedId: selected ? selected.id : null });
    renderPortfolioSelect();

    setHasPortfolio(portfolios.length > 0);
    if (selected) await loadPortfolioData();
}

function renderPortfolioSelect() {
    $('ledger-portfolio-select').innerHTML = render.portfolioOptionsHTML(state.portfolios, state.selectedId);
}

async function selectPortfolio(id) {
    const found = state.portfolios.find(p => String(p.id) === String(id));
    if (!found) return;
    setState({ selectedId: found.id, confirmingVoid: null });
    storeSelection(found.id);
    await loadPortfolioData();
}

function openCreateForm() {
    const form = $('ledger-create-form');
    form.hidden = false;
    clearFormErrors(form);
    $('ledger-new-name').focus();
}

function closeCreateForm() {
    const form = $('ledger-create-form');
    form.reset();
    clearFormErrors(form);
    form.hidden = true;
    $('ledger-new-btn').focus();
}

async function submitCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    clearFormErrors(form);
    const name = $('ledger-new-name').value.trim();
    if (name === '' || name.length > NAME_MAX_LENGTH) {
        showFieldErrors(form, { name: name === '' ? 'Required.' : `At most ${NAME_MAX_LENGTH} characters.` });
        return;
    }

    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true, 'Creating');
    const result = await api.createPortfolio(name);
    setBusy(button, false);

    if (!result.ok) {
        if (result.status === 409) {
            showFieldErrors(form, { name: 'You already have a portfolio with this name.' });
            return;
        }
        const unplaced = showFieldErrors(form, result.error.fields);
        showFormAlert(form, unplaced[0] || result.error.message);
        return;
    }

    const created = result.data;
    setState({ portfolios: [...state.portfolios, created], selectedId: created.id, confirmingVoid: null });
    storeSelection(created.id);
    form.reset();
    form.hidden = true;
    renderPortfolioSelect();
    setHasPortfolio(true);
    announce(`Portfolio ${created.name} created.`);
    await loadPortfolioData();
}

// ---------- Holdings, performance, transactions ----------

async function loadPortfolioData() {
    const id = state.selectedId;
    if (id === null) return;
    showLoading();

    const [holdings, performance, transactions] = await Promise.all([
        api.getHoldings(id), api.getPerformance(id), api.listTransactions(id, 0),
    ]);
    if (state.selectedId !== id) return; // another portfolio was chosen meanwhile

    if (holdings.ok) {
        $('ledger-summary').innerHTML = render.summaryHTML(holdings.data, performance.ok ? performance.data : null);
        $('ledger-holdings').innerHTML = render.holdingsHTML(holdings.data);
        if (!performance.ok) {
            $('ledger-summary').insertAdjacentHTML('beforeend', render.errorHTML(`Realised figures: ${performance.error.message}`, 'reload-data'));
        }
    } else {
        $('ledger-summary').innerHTML = render.errorHTML(holdings.error.message, 'reload-data');
        $('ledger-holdings').innerHTML = '';
    }

    if (transactions.ok) {
        setState({ transactions: { items: transactions.data.items || [], total: transactions.data.total || 0 } });
        renderTransactions();
    } else {
        $('ledger-transactions').innerHTML = render.errorHTML(transactions.error.message, 'reload-data');
    }
}

function renderTransactions() {
    $('ledger-transactions').innerHTML = render.transactionsHTML(state.transactions, state.confirmingVoid);
}

async function loadMoreTransactions(button) {
    setBusy(button, true, 'Loading');
    const id = state.selectedId;
    const result = await api.listTransactions(id, state.transactions.items.length);
    if (state.selectedId !== id) return;
    if (!result.ok) {
        setBusy(button, false);
        $('ledger-transactions').insertAdjacentHTML('beforeend', render.errorHTML(result.error.message, null));
        return;
    }
    setState({
        transactions: {
            items: [...state.transactions.items, ...(result.data.items || [])],
            total: result.data.total || state.transactions.total,
        },
    });
    renderTransactions();
}

async function confirmVoid(txId, button) {
    setBusy(button, true, 'Voiding');
    const result = await api.voidTransaction(state.selectedId, txId);
    if (!result.ok) {
        setState({ confirmingVoid: null });
        renderTransactions();
        $('ledger-transactions').insertAdjacentHTML('afterbegin', render.errorHTML(result.error.message, null));
        return;
    }
    setState({ confirmingVoid: null });
    announce(`Transaction ${txId} voided.`);
    await loadPortfolioData();
}

// ---------- Transaction form ----------

function applyTypeRules() {
    const type = $('ledger-tx-type').value;
    const rules = transactionFieldsForType(type);
    for (const [field, rule] of Object.entries(rules)) {
        const wrap = document.querySelector(`#ledger-tx-form [data-field="${field}"]`);
        if (!wrap) continue;
        wrap.hidden = rule === 'hidden';
        const optional = wrap.querySelector('.field-optional');
        if (optional) optional.hidden = rule !== 'optional';
    }
    $('ledger-tx-quantity-label').firstChild.textContent = `${QUANTITY_LABELS[type] || 'Quantity'} `;
    $('ledger-tx-price-label').firstChild.textContent = type === 'DIVIDEND' ? 'Dividend per share ' : 'Price per unit ';
}

function readTransactionForm(form) {
    const values = {};
    for (const field of TX_FIELDS) {
        const input = form.elements[field];
        const wrap = form.querySelector(`[data-field="${field}"]`);
        values[field] = input && !(wrap && wrap.hidden) ? input.value : '';
    }
    return values;
}

function resetTransactionForm(form) {
    const type = $('ledger-tx-type').value;
    form.reset();
    $('ledger-tx-type').value = type;
    $('ledger-tx-date').value = todayISO();
    applyTypeRules();
}

async function submitTransaction(event) {
    event.preventDefault();
    const form = event.currentTarget;
    clearFormErrors(form);

    const { body, errors } = buildTransactionBody(readTransactionForm(form));
    if (body === null) {
        showFieldErrors(form, errors);
        showFormAlert(form, 'Check the highlighted fields.');
        return;
    }

    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true, 'Saving');
    const result = await api.addTransaction(state.selectedId, body);
    setBusy(button, false);

    if (!result.ok) {
        const unplaced = showFieldErrors(form, result.error.fields);
        showFormAlert(form, unplaced[0] || result.error.message);
        return;
    }
    resetTransactionForm(form);
    announce('Transaction added.');
    showFormAlert(form, '');
    await loadPortfolioData();
}

// ---------- Events ----------

function onContentClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const { action, tx } = button.dataset;
    if (action === 'void-ask') { setState({ confirmingVoid: tx }); renderTransactions(); focusAction('void-confirm'); }
    else if (action === 'void-cancel') { const id = state.confirmingVoid; setState({ confirmingVoid: null }); renderTransactions(); focusVoidButton(id); }
    else if (action === 'void-confirm') confirmVoid(tx, button);
    else if (action === 'more') loadMoreTransactions(button);
    else if (action === 'reload-data') loadPortfolioData();
    else if (action === 'reload') loadPortfolios();
}

function focusAction(action) {
    const button = document.querySelector(`#ledger-view button[data-action="${action}"]`);
    if (button) button.focus();
}

function focusVoidButton(txId) {
    const button = document.querySelector(`#ledger-view button[data-action="void-ask"][data-tx="${CSS.escape(String(txId))}"]`);
    if (button) button.focus();
}

function refreshIfVisible() {
    if (!isVisible()) return;
    const user = currentUser();
    if (!user) { showSignedOut(); return; }
    const userKey = user.id ?? user.email ?? true;
    if (state.loadedFor !== userKey) loadPortfolios();
}

function onAuthChanged(event) {
    const user = event.detail && event.detail.user;
    if (!user) {
        setState({ loadedFor: null, portfolios: [], selectedId: null, transactions: { items: [], total: 0 }, confirmingVoid: null });
    }
    refreshIfVisible();
}

function init() {
    if (!$('ledger-view')) return;
    $('ledger-tx-type').innerHTML = render.typeOptionsHTML();
    $('ledger-tx-date').value = todayISO();
    $('ledger-tx-date').max = todayISO();
    applyTypeRules();

    $('ledger-tx-type').addEventListener('change', () => { clearFormErrors($('ledger-tx-form')); applyTypeRules(); });
    $('ledger-tx-form').addEventListener('submit', submitTransaction);
    $('ledger-create-form').addEventListener('submit', submitCreate);
    $('ledger-cancel-create').addEventListener('click', closeCreateForm);
    $('ledger-new-btn').addEventListener('click', openCreateForm);
    $('ledger-first-btn').addEventListener('click', openCreateForm);
    $('ledger-signin-btn').addEventListener('click', () => window.openAuthModal && window.openAuthModal('login'));
    $('ledger-portfolio-select').addEventListener('change', (e) => selectPortfolio(e.target.value));
    $('ledger-view').addEventListener('click', onContentClick);

    document.addEventListener('wolfee_auth_changed', onAuthChanged);
    document.addEventListener('wolfee_tab_changed', (e) => { if (e.detail && e.detail.tab === 'ledger') refreshIfVisible(); });
    refreshIfVisible();
}

init();
