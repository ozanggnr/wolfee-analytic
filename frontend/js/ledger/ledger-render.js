/**
 * Markup for the Portfolio page (REQ-32). Every value from the API is escaped;
 * figures are shown as the API sends them, only rounded for display
 * (ledger-format.js). A null figure is "Not available", never estimated.
 */

import { escapeHTML as esc } from '../core/safe-html.js';
import { NOT_AVAILABLE, formatTimestamp } from '../core/market-fields.js';
import {
    formatMoney, formatQuantity, formatRatioAsPercent, decimalSign,
    partialTotalText, unavailableReasonText, freshnessText, TRANSACTION_TYPES,
} from '../core/ledger-format.js';

const TYPE_LABELS = {
    BUY: 'Buy', SELL: 'Sell', DIVIDEND: 'Dividend', SPLIT: 'Split',
    FEE: 'Fee', DEPOSIT: 'Deposit', WITHDRAWAL: 'Withdrawal',
};

function notAvailable(reasonText) {
    return `<span class="not-available">${NOT_AVAILABLE}</span>`
        + (reasonText ? `<small class="na-reason">${esc(reasonText)}</small>` : '');
}

function moneyHTML(value, currency, reasonText = null) {
    if (value === null || value === undefined) return notAvailable(reasonText);
    return `<span class="num">${esc(formatMoney(value, currency))}</span>`;
}

function pnlHTML(value, currency, reasonText = null) {
    if (value === null || value === undefined) return notAvailable(reasonText);
    const sign = decimalSign(value);
    const cls = sign === 1 ? 'is-gain' : sign === -1 ? 'is-loss' : '';
    const text = formatMoney(value, currency);
    return `<span class="num ${cls}">${sign === 1 ? '+' : ''}${esc(text)}</span>`;
}

// ---------- States ----------

export function messageHTML({ title, text, action = '' }) {
    return `<div class="empty-state">
        <p class="empty-title">${esc(title)}</p>
        <p>${esc(text)}</p>
        ${action}
    </div>`;
}

export function errorHTML(message, retryAction) {
    return `<div class="inline-error ledger-error" role="alert">
        <span>${esc(message)}</span>
        ${retryAction ? `<button type="button" class="link-btn" data-action="${esc(retryAction)}">Try again</button>` : ''}
    </div>`;
}

export function loadingHTML(label) {
    return `<p class="grid-message" role="status">${esc(label)}</p>`;
}

// ---------- Toolbar ----------

export function portfolioOptionsHTML(portfolios, selectedId) {
    return portfolios.map(p => `<option value="${esc(String(p.id))}"${String(p.id) === String(selectedId) ? ' selected' : ''}>${esc(p.name)}</option>`).join('');
}

// ---------- Summary ----------

function partialNoticeHTML(header) {
    const text = partialTotalText(header);
    if (text === null) return '';
    const symbols = (header.unvalued_symbols || []).map(s => `<span class="num">${esc(s)}</span>`).join(', ');
    return `<div class="partial-notice" role="status">
        <p class="partial-title">${esc(text)}</p>
        <p>Not valued: ${symbols}. The totals cover the valued positions only.</p>
    </div>`;
}

function kpiHTML(label, valueHTML) {
    return `<div class="summary-metric"><span class="sm-label">${esc(label)}</span><span class="kpi-value ledger-kpi">${valueHTML}</span></div>`;
}

function amountsHTML(title, list, { signed = false } = {}) {
    if (!Array.isArray(list) || list.length === 0) return '';
    const items = list.map(a => `<li>${signed ? pnlHTML(a.amount, a.currency) : moneyHTML(a.amount, a.currency)}</li>`).join('');
    return `<div class="amount-group"><h3 class="sm-label">${esc(title)}</h3><ul>${items}</ul></div>`;
}

export function summaryHTML(holdings, performance) {
    const base = holdings.base_currency || 'TRY';
    const computed = formatTimestamp(holdings.computed_at);
    const noBaseCost = NO_TRADE_RATE;
    const groups = [
        amountsHTML('Realised P/L by currency', performance && performance.realized_pnl, { signed: true }),
        amountsHTML('Dividends', performance && performance.dividends),
        amountsHTML('Fees', performance && performance.fees),
        amountsHTML('Net deposits', performance && performance.net_deposits),
        amountsHTML('Cash balances', performance && performance.cash_balances),
    ].join('');

    return `<div class="summary-head">
            <h2 class="section-title" id="ledger-summary-title">Summary</h2>
            ${computed ? `<span class="summary-cache">Valued ${esc(computed)}</span>` : ''}
        </div>
        ${partialNoticeHTML(holdings)}
        <div class="summary-metrics">
            ${kpiHTML(`Market value (${base})`, moneyHTML(holdings.total_market_value, base))}
            ${kpiHTML(`Cost basis (${base})`, moneyHTML(holdings.total_cost_basis, base, holdings.total_market_value ? noBaseCost : null))}
            ${kpiHTML(`Unrealised P/L (${base})`, pnlHTML(holdings.total_unrealized_pnl, base, holdings.total_market_value ? noBaseCost : null))}
            ${kpiHTML(`Realised P/L (${base})`, performance ? pnlHTML(performance.realized_pnl_base, base, noBaseCost) : notAvailable(null))}
        </div>
        ${groups ? `<div class="amount-groups">${groups}</div>` : ''}`;
}

// ---------- Holdings ----------

function quoteHTML(position) {
    const quote = position.quote;
    if (!quote) return notAvailable(unavailableReasonText(position.unavailable_reason));
    const freshness = freshnessText(quote.freshness);
    const asOf = formatTimestamp(quote.as_of);
    return `${moneyHTML(quote.price, quote.currency)}
        <small class="na-reason">${esc([freshness, asOf].filter(Boolean).join(', '))}</small>`;
}

function valueBaseHTML(position, base) {
    if (position.market_value_base !== null && position.market_value_base !== undefined) {
        return moneyHTML(position.market_value_base, base);
    }
    const reason = unavailableReasonText(position.unavailable_reason);
    const local = position.market_value && position.currency !== base
        ? `<small class="na-reason">${esc(formatMoney(position.market_value, position.currency))}</small>` : '';
    return notAvailable(reason) + local;
}

const NO_TRADE_RATE = 'A trade has no stored rate to TRY';

/** Unrealised P/L in TRY; without it, the API's figure in the instrument currency, labelled. */
function unrealizedBaseHTML(p, base) {
    if (p.unrealized_pnl_base !== null && p.unrealized_pnl_base !== undefined) return pnlHTML(p.unrealized_pnl_base, base);
    const reason = unavailableReasonText(p.unavailable_reason)
        || (p.cost_basis_base === null || p.cost_basis_base === undefined ? NO_TRADE_RATE : null);
    const local = p.unrealized_pnl !== null && p.unrealized_pnl !== undefined && p.currency !== base
        ? `<small class="na-reason">${pnlHTML(p.unrealized_pnl, p.currency)}</small>` : '';
    return notAvailable(reason) + local;
}

function holdingRowHTML(p, base) {
    return `<tr>
        <th scope="row" data-label="Instrument">
            <span class="ledger-symbol">${esc(p.symbol)}</span>
            <small class="na-reason">${esc([p.name, `${p.exchange} · ${p.currency}`].filter(Boolean).join(', '))}</small>
        </th>
        <td data-label="Quantity"><span class="num">${esc(formatQuantity(p.quantity))}</span></td>
        <td data-label="Average cost">${moneyHTML(p.average_cost, p.currency)}</td>
        <td data-label="Price">${quoteHTML(p)}</td>
        <td data-label="Market value (${esc(base)})">${valueBaseHTML(p, base)}</td>
        <td data-label="Unrealised P/L (${esc(base)})">${unrealizedBaseHTML(p, base)}</td>
        <td data-label="Weight">${p.weight === null || p.weight === undefined ? notAvailable(null) : `<span class="num">${esc(formatRatioAsPercent(p.weight))}</span>`}</td>
    </tr>`;
}

export function holdingsHTML(holdings) {
    const positions = holdings.positions || [];
    if (positions.length === 0) {
        return messageHTML({ title: 'No positions yet', text: 'Add a Buy transaction below to open a position.' });
    }
    const base = holdings.base_currency || 'TRY';
    return `<div class="table-wrap"><table class="ledger-table">
        <thead><tr>
            <th scope="col">Instrument</th><th scope="col">Quantity</th><th scope="col">Average cost</th>
            <th scope="col">Price</th><th scope="col">Market value (${esc(base)})</th>
            <th scope="col">Unrealised P/L (${esc(base)})</th><th scope="col">Weight</th>
        </tr></thead>
        <tbody>${positions.map(p => holdingRowHTML(p, base)).join('')}</tbody>
    </table></div>`;
}

// ---------- Transactions ----------

function statusCellHTML(tx, confirmingId) {
    if (tx.voids_transaction_id) return `<span class="status-chip">Reversal of #${esc(String(tx.voids_transaction_id))}</span>`;
    if (tx.voided_by_transaction_id) return '<span class="status-chip is-void">Voided</span>';
    if (String(confirmingId) === String(tx.id)) {
        return `<span class="void-confirm">Void this transaction?
            <button type="button" class="link-btn is-danger" data-action="void-confirm" data-tx="${esc(String(tx.id))}">Void</button>
            <button type="button" class="link-btn is-quiet" data-action="void-cancel">Cancel</button></span>`;
    }
    return `<button type="button" class="link-btn" data-action="void-ask" data-tx="${esc(String(tx.id))}" aria-label="Void transaction ${esc(String(tx.id))}">Void</button>`;
}

function transactionRowHTML(tx, confirmingId) {
    const ignored = tx.voids_transaction_id || tx.voided_by_transaction_id;
    const amountLabel = ['DEPOSIT', 'WITHDRAWAL'].includes(tx.type) ? 'Amount' : 'Quantity';
    return `<tr class="${ignored ? 'is-ignored' : ''}">
        <td data-label="Date"><span class="num">${esc(tx.trade_date)}</span></td>
        <th scope="row" data-label="Type">${esc(TYPE_LABELS[tx.type] || tx.type)} <small class="na-reason">#${esc(String(tx.id))}</small></th>
        <td data-label="Instrument">${tx.symbol ? `<span class="ledger-symbol">${esc(tx.symbol)}</span>` : ''}</td>
        <td data-label="${amountLabel}">${tx.type === 'FEE' ? '' : `<span class="num">${esc(formatQuantity(tx.quantity))}</span>`}</td>
        <td data-label="Price">${tx.price === null || tx.price === undefined ? '' : moneyHTML(tx.price, tx.currency)}</td>
        <td data-label="Fee">${decimalSign(tx.fee) === 0 ? '' : moneyHTML(tx.fee, tx.currency)}</td>
        <td data-label="Note" class="ledger-note">${tx.note ? esc(tx.note) : ''}</td>
        <td data-label="Status">${statusCellHTML(tx, confirmingId)}</td>
    </tr>`;
}

export function transactionsHTML({ items, total }, confirmingId) {
    if (!items || items.length === 0) {
        return messageHTML({ title: 'No transactions yet', text: 'Record a deposit, a buy or another transaction with the form above.' });
    }
    const more = items.length < total
        ? `<button type="button" class="secondary-btn ledger-more" data-action="more">Show more (${items.length} of ${total})</button>` : '';
    return `<p class="ledger-count">${esc(String(total))} ${total === 1 ? 'transaction' : 'transactions'}, newest first. A voided transaction and its reversal are both left out of the figures.</p>
        <div class="table-wrap"><table class="ledger-table ledger-tx-table">
        <thead><tr>
            <th scope="col">Date</th><th scope="col">Type</th><th scope="col">Instrument</th><th scope="col">Quantity</th>
            <th scope="col">Price</th><th scope="col">Fee</th><th scope="col">Note</th><th scope="col">Status</th>
        </tr></thead>
        <tbody>${items.map(tx => transactionRowHTML(tx, confirmingId)).join('')}</tbody>
    </table></div>${more}`;
}

export function typeOptionsHTML() {
    return TRANSACTION_TYPES.map(t => `<option value="${t}">${TYPE_LABELS[t]}</option>`).join('');
}
