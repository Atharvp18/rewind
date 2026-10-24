import type { Invoice } from '@/lib/api';
import { formatCents } from '@/lib/money';

const ELIGIBILITY: Record<string, string> = {
  eligible: 'HSA/FSA eligible',
  not_eligible: 'Not HSA/FSA eligible',
  could_not_confirm: 'Eligibility not confirmed',
};
const CARD: Record<string, string> = { hsa: 'HSA card', fsa: 'FSA card', general: 'Everyday card' };

export const longDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });

/** An item is a "possible reimbursement" when it is HSA/FSA eligible but was paid with an everyday card. */
export const isReimbursable = (l: Invoice['lines'][number]) =>
  l.eligibility_label === 'eligible' && l.card_type === 'general';

/** One invoice as plain text the user can save or send to their HSA/FSA administrator. */
export function invoiceToText(inv: Invoice): string {
  const rows = inv.lines.map(
    (l) =>
      `  ${l.name}\n    Qty ${l.qty} x ${formatCents(l.unit_cents)} = ${formatCents(l.amount_cents)}\n    ${ELIGIBILITY[l.eligibility_label]}; paid with ${CARD[l.card_type]}${isReimbursable(l) ? '; POSSIBLE REIMBURSEMENT' : ''}`,
  );
  return [
    `INVOICE ${inv.invoice_id}`,
    `${inv.store.name}`,
    `${inv.store.address}`,
    `Phone ${inv.store.phone}`,
    `Date ${longDate(inv.date)}`,
    '',
    'ITEMS',
    ...rows,
    '',
    `Subtotal ${formatCents(inv.subtotal_cents)}`,
    `Tax (estimate) ${formatCents(inv.tax_cents)}`,
    `Total ${formatCents(inv.total_cents)}`,
    '',
    'PAID WITH (items, before tax)',
    ...inv.payments.map((p) => `  ${p.nickname}${p.last4 ? ` ending ${p.last4}` : ''}: ${formatCents(p.amount_cents)}`),
    '',
    inv.tax_note,
    'Prepared by Rewind from mock data. Rewind does not file claims. Your HSA/FSA administrator makes the final decision.',
  ].join('\n');
}

/** All invoices with possible reimbursements, in one packet. */
export function packetToText(invoices: Invoice[]): string {
  const rel = invoices.filter((i) => i.reimbursable_cents > 0);
  const total = rel.reduce((s, i) => s + i.reimbursable_cents, 0);
  return [
    'REWIND REIMBURSEMENT PACKET (mock data)',
    `Invoices: ${rel.length}. Possible reimbursement before tax: ${formatCents(total)}.`,
    '',
    ...rel.map((i) => `${invoiceToText(i)}\n\n----------------------------------------\n`),
  ].join('\n');
}
