import type { Invoice } from '@/lib/api';
import { Screens } from '@/lib/phrases';

const inv = (over: Partial<Invoice> = {}): Invoice => ({
  invoice_id: 'i1',
  date: new Date().toISOString(),
  store: { name: 'Rewind Demo Store', address: '', phone: '' },
  lines: [
    { name: 'Advil', qty: 1, unit_cents: 1299, amount_cents: 1299, eligibility_label: 'eligible', card_id: 'f', card_type: 'fsa' },
    { name: 'Tums', qty: 2, unit_cents: 548, amount_cents: 1096, eligibility_label: 'eligible', card_id: 'v', card_type: 'general' },
  ],
  subtotal_cents: 2395,
  tax_cents: 174,
  tax_note: '',
  total_cents: 2569,
  payments: [
    { card_id: 'f', nickname: 'FSA card', type: 'fsa', last4: null, amount_cents: 1299 },
    { card_id: 'v', nickname: 'Visa credit', type: 'general', last4: null, amount_cents: 1096 },
  ],
  reimbursable_cents: 1096,
  ...over,
});

describe('screens read out loud', () => {
  it('reads one receipt naturally', () => {
    expect(Screens.invoice(inv())).toBe(
      'Today at Rewind Demo Store, you bought Advil and 2 Tums, for $25.69 with estimated tax. You paid $12.99 on your FSA card and $10.96 on your Visa credit.',
    );
  });

  it('summarises the history and reads the newest receipt', () => {
    const text = Screens.history([inv(), inv({ invoice_id: 'i2' })]);
    expect(text.startsWith('You have 2 purchases. You may be able to get $21.92 back from your HSA or FSA.')).toBe(true);
    expect(text).toContain('The most recent: Today at Rewind Demo Store');
    expect(text.endsWith('Tap any other receipt to hear it.')).toBe(true);
  });

  it('an empty history says what will appear', () => {
    expect(Screens.history([])).toContain('Your receipts will show up here');
  });

  it('reads the cart by card', () => {
    const text = Screens.cart({
      groups: [{ nickname: 'FSA card', items: [{ display_name: 'Advil', amount_cents: 1299 }] }],
      total_cents: 1299,
    });
    expect(text).toBe("Your cart has 1 item, $12.99 before tax. On your FSA card: Advil, $12.99. Tap an item to remove it, or say checkout when you're ready.");
  });
});
