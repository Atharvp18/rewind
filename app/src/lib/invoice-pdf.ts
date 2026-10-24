import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

import type { Invoice } from '@/lib/api';
import { longDate, isReimbursable } from '@/lib/invoice-text';
import { formatCents } from '@/lib/money';

const ELIGIBILITY: Record<string, string> = {
  eligible: 'HSA/FSA eligible',
  not_eligible: 'Not HSA/FSA eligible',
  could_not_confirm: 'Eligibility not confirmed',
};
const CARD: Record<string, string> = { hsa: 'HSA card', fsa: 'FSA card', general: 'Everyday card' };

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function invoiceHtml(inv: Invoice): string {
  const rows = inv.lines
    .map(
      (l) => `<tr>
        <td>${esc(l.name)}<div class="s">${esc(ELIGIBILITY[l.eligibility_label])}${isReimbursable(l) ? ' · <b>Possible reimbursement</b>' : ''}</div></td>
        <td class="n">${l.qty}</td><td class="n">${formatCents(l.unit_cents)}</td>
        <td>${esc(CARD[l.card_type])}</td><td class="n">${formatCents(l.amount_cents)}</td></tr>`,
    )
    .join('');
  return `<section class="inv">
    <h2>${esc(inv.store.name)}</h2>
    <p class="s">${esc(inv.store.address)}<br/>Phone ${esc(inv.store.phone)}<br/>Invoice ${esc(inv.invoice_id)} · ${esc(longDate(inv.date))}</p>
    <table><thead><tr><th>Item</th><th class="n">Qty</th><th class="n">Price</th><th>Paid with</th><th class="n">Amount</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <table class="t"><tr><td>Subtotal</td><td class="n">${formatCents(inv.subtotal_cents)}</td></tr>
    <tr><td>Tax (estimate)</td><td class="n">${formatCents(inv.tax_cents)}</td></tr>
    <tr><td><b>Total</b></td><td class="n"><b>${formatCents(inv.total_cents)}</b></td></tr></table>
    <p class="s">Paid with: ${inv.payments.map((p) => `${esc(p.nickname)}${p.last4 ? ` ending ${esc(p.last4)}` : ''} ${formatCents(p.amount_cents)}`).join('; ')} (items, before tax)</p>
    <p class="s">${esc(inv.tax_note)}</p>
  </section>`;
}

const PAGE = (body: string, title: string) => `<html><head><meta charset="utf-8"/><style>
  body{font-family:-apple-system,Helvetica,Arial,sans-serif;color:#0B2427;padding:28px;font-size:13px}
  h1{font-size:18px;margin:0 0 4px} h2{font-size:17px;margin:0 0 2px}
  .s{color:#3E5A5E;font-size:11.5px;margin:2px 0} table{width:100%;border-collapse:collapse;margin:12px 0}
  th,td{border-bottom:1px solid #C9D8D6;padding:6px 4px;text-align:left;vertical-align:top} .n{text-align:right}
  .t{width:55%;margin-left:auto} .inv{page-break-inside:avoid;margin-bottom:28px}
  .note{border:1px solid #C46A00;background:#FFF3E2;padding:8px;font-size:11.5px;margin-top:16px}
</style><title>${esc(title)}</title></head><body>${body}
  <div class="note">Prepared by Rewind from mock data for your records. Rewind does not file claims or reimburse anyone.
  Your HSA/FSA administrator makes the final decision on eligibility.</div></body></html>`;

async function sharePdf(html: string, dialogTitle: string): Promise<void> {
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle });
  }
}

/** One invoice as a PDF the user can save or upload to their own HSA/FSA portal. */
export const shareInvoicePdf = (inv: Invoice) =>
  sharePdf(PAGE(`<h1>Invoice</h1>${invoiceHtml(inv)}`, `Invoice ${inv.invoice_id}`), `Invoice ${inv.invoice_id}`);

/** Every invoice with a possible reimbursement, in one PDF. */
export function shareReimbursementPacketPdf(invoices: Invoice[]) {
  const rel = invoices.filter((i) => i.reimbursable_cents > 0);
  const total = rel.reduce((s, i) => s + i.reimbursable_cents, 0);
  const head = `<h1>Reimbursement packet</h1><p class="s">${rel.length} invoice(s). Possible reimbursement before tax: ${formatCents(total)}.</p>`;
  return sharePdf(PAGE(head + rel.map(invoiceHtml).join(''), 'Reimbursement packet'), 'Reimbursement packet');
}
