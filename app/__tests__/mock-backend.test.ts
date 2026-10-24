/**
 * Scenarios and edge cases from the technical spec, run against the app's
 * mock backend (the stand-in for Atharv's API while it is unfinished).
 *
 * Spec sources are named in each test: 0.5 money, 0.7 timeouts and prompts,
 * 2.3 prescriptions, 3.4 reset, 3.5 routing, 3.6 checkout, 3.8 commands,
 * 4.4 demo script, 20.x edge cases. The team decision FSA → HSA → Visa
 * (spec 1.10) replaces the HSA-only wording of 4.4; tests say where.
 */
import * as m from '@/lib/mock-backend';
import type { Cart, ScanResponse } from '@/lib/api';

// ---- helpers -------------------------------------------------------------

let clock = 0;
const realNow = Date.now.bind(Date);

beforeEach(async () => {
  // Latency timers fire at once; the clock is ours to move (prompt expiry).
  jest.spyOn(global, 'setTimeout').mockImplementation(((fn: () => void) => {
    fn();
    return 0 as unknown as ReturnType<typeof setTimeout>;
  }) as typeof setTimeout);
  clock = 0;
  jest.spyOn(Date, 'now').mockImplementation(() => realNow() + clock);
  m.setPromptTtl(30);
  await m.resetDemo(1);
});

afterEach(() => jest.restoreAllMocks());

const scanN = async (n: number): Promise<ScanResponse> => {
  let r!: ScanResponse;
  for (let i = 0; i < n; i++) r = await m.scan(null);
  return r;
};
/** Scan the next item and add it where Rewind suggests. */
const scanAndAdd = async () => {
  const r = await m.scan(null);
  const rec = r.recommendation!;
  const cart = await m.addCartItem(r.scan.scan_id, rec.card_id ?? rec.card_options[0], r.voice.prompt_id!);
  return { r, cart };
};
const FSA = 'card_fsa_1';
const HSA = 'card_hsa_1';
const VISA = 'card_visa_1';

/** Every `*_cents` number anywhere in `value` must be an integer (spec 0.5). */
function expectIntegerMoney(value: unknown, path = 'result') {
  if (Array.isArray(value)) return value.forEach((v, i) => expectIntegerMoney(v, `${path}[${i}]`));
  if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      if (k.endsWith('_cents') && typeof v === 'number') {
        if (!Number.isInteger(v)) throw new Error(`${path}.${k} = ${v} is not an integer`);
      }
      expectIntegerMoney(v, `${path}.${k}`);
    }
  }
}

// ---- the demo shelf --------------------------------------------------------

describe('the demo shelf (spec 4.4, 4.6)', () => {
  it('cycles Advil, bandages, kettle corn, an unknown item, a prescription bottle, then repeats', async () => {
    const names: string[] = [];
    for (let i = 0; i < 6; i++) names.push((await m.scan(null)).scan.product.name);
    expect(names).toEqual(['Advil Ibuprofen 200mg', 'Bandages', 'Kettle Corn', 'Unknown item', 'Omeprazole', 'Advil Ibuprofen 200mg']);
  });

  it('Advil: eligible by exact UPC, a prescription-free medication, $12.99, asks to confirm', async () => {
    const r = await scanN(1);
    expect(r.scan.state).toBe('resolved');
    expect(r.scan.product.amount_cents).toBe(1299);
    expect(r.scan.eligibility).toMatchObject({ label: 'eligible', basis: 'upc_match' });
    expect(r.voice.expects_response).toBe(true);
    expect(r.voice.response_scope).toBe('confirm_add');
    expect(r.voice.prompt_id).toBeTruthy();
    expect(r.voice.text).toBe(
      'I see Advil, ibuprofen 200mg, $12.99. HSA eligible. Your FSA balance is $25. Want to use your FSA card?',
    );
  });

  it('kettle corn: the exact spec 4.4 line, routed to the Visa, never eligible', async () => {
    const r = await scanN(3);
    expect(r.voice.text).toBe("Kettle corn, $4.99. Not HSA eligible, high confidence. I'll put this on your Visa credit card.");
    expect(r.scan.eligibility.label).toBe('not_eligible');
    expect(r.recommendation).toMatchObject({ decision: 'route_to_general', card_id: VISA, reason_code: 'not_eligible' });
  });

  it('an item the shelf does not know: "I could not confirm this item", no recommendation, no question (spec 2.6, 4.6)', async () => {
    const r = await scanN(4);
    expect(r.scan.state).toBe('unresolved');
    expect(r.recommendation).toBeNull();
    expect(r.voice.text).toBe('I could not confirm this item. Try another angle, or tell me what it is.');
    expect(r.voice.expects_response).toBe(false);
    expect(r.scan.product.amount_cents).toBeNull(); // never a guessed price
  });

  it('never states a medication eligible without an exact UPC match, and never a non-eligible item eligible (spec 2.7, 2.10)', async () => {
    for (let i = 0; i < 10; i++) {
      const r = await m.scan(null);
      const { product, eligibility } = r.scan;
      if (product.is_medication && eligibility.label !== 'could_not_confirm') expect(eligibility.basis).toBe('upc_match');
      if (product.name === 'Kettle Corn') expect(eligibility.label).not.toBe('eligible');
    }
  });

  it('locates the item in the photo with fractions between 0 and 1, for the focus corners', async () => {
    for (let i = 0; i < 5; i++) {
      const r = await m.scan(null);
      const box = r.scan.item_bbox;
      if (r.scan.state === 'unresolved') continue;
      expect(box).toBeTruthy();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.w).toBeLessThanOrEqual(1);
      expect(box!.y + box!.h).toBeLessThanOrEqual(1);
    }
  });

  it('splits the spoken text into sentences for sentence-by-sentence playback (spec 1.4)', async () => {
    const r = await scanN(1);
    expect(r.voice.sentences.length).toBeGreaterThan(1);
    expect(r.voice.sentences.join(' ')).toBe(r.voice.text);
  });

  it('every money value is an integer number of cents (spec 0.5)', async () => {
    for (let i = 0; i < 5; i++) expectIntegerMoney(await m.scan(null));
    expectIntegerMoney(await m.getCards());
  });
});

// ---- routing: FSA, then HSA, then the everyday Visa --------------------------

describe('routing for eligible items: FSA first, then HSA, then Visa (spec 3.5 + decision of 2026-10-24)', () => {
  it('suggests the FSA first when it can cover the item', async () => {
    const r = await scanN(1);
    expect(r.recommendation).toMatchObject({
      decision: 'route_to_hsa',
      card_id: FSA,
      reason_code: 'eligible_sufficient_balance',
      balance_before_cents: 2500,
      balance_after_cents: 2500 - 1299,
      amount_cents: 1299,
      amount_basis: 'shelf_price',
    });
  });

  it('a balance exactly equal to the price counts as sufficient (spec 20.6)', async () => {
    m.__testing.setBalance(FSA, 1299);
    expect((await scanN(1)).recommendation).toMatchObject({ decision: 'route_to_hsa', card_id: FSA, balance_after_cents: 0 });
  });

  it('one cent short: asks, and proposes the HSA (spec 3.5 "insufficient")', async () => {
    m.__testing.setBalance(FSA, 1298);
    const r = await scanN(1);
    expect(r.recommendation).toMatchObject({
      decision: 'ask_user',
      reason_code: 'eligible_insufficient_balance',
      reroute: { from_card_id: FSA, to_card_id: HSA, reason: 'insufficient_balance' },
      card_options: [HSA],
    });
    expect(r.voice.text).toContain("Your FSA balance of $12.98 doesn't cover it. Want to use your HSA card instead?");
  });

  it('a zero balance counts as insufficient (spec 20.6)', async () => {
    m.__testing.setBalance(FSA, 0);
    expect((await scanN(1)).recommendation).toMatchObject({ decision: 'ask_user', reroute: { to_card_id: HSA } });
  });

  it('FSA and HSA both too small: proposes the everyday Visa', async () => {
    m.__testing.setBalance(FSA, 100);
    m.__testing.setBalance(HSA, 100);
    expect((await scanN(1)).recommendation).toMatchObject({
      decision: 'ask_user',
      reroute: { from_card_id: FSA, to_card_id: VISA },
      card_options: [VISA],
    });
  });

  it('nothing covers it: blocked with no_card_covers (spec 3.5 step 5)', async () => {
    for (const id of [FSA, HSA, VISA]) m.__testing.setBalance(id, 0);
    expect((await scanN(1)).recommendation).toMatchObject({ decision: 'blocked', card_id: null, reason_code: 'no_card_covers' });
  });

  it.each(['frozen', 'closed', 'expired'] as const)(
    'a %s HSA/FSA card is treated as no card linked: routed to the Visa (spec 20.6)',
    async (status) => {
      m.__testing.setStatus(FSA, status);
      m.__testing.setStatus(HSA, status);
      expect((await scanN(1)).recommendation).toMatchObject({
        decision: 'route_to_general',
        card_id: VISA,
        reason_code: 'no_health_card_linked',
      });
    },
  );

  it('a frozen FSA is skipped and the HSA is used (spec 20.6)', async () => {
    m.__testing.setStatus(FSA, 'frozen');
    expect((await scanN(1)).recommendation).toMatchObject({ decision: 'route_to_hsa', card_id: HSA });
  });

  it('a not-eligible item never goes to the FSA or HSA, even when they have plenty (spec 3.5 step 3)', async () => {
    m.__testing.setBalance(FSA, 999999);
    m.__testing.setBalance(HSA, 999999);
    const r = await scanN(3);
    expect(r.recommendation!.card_id).toBe(VISA);
    expect(r.recommendation!.card_options).not.toContain(FSA);
    expect(r.recommendation!.card_options).not.toContain(HSA);
  });

  it('every recommendation requires a confirmation (spec 3.5)', async () => {
    for (let i = 0; i < 3; i++) expect((await m.scan(null)).recommendation!.requires_confirmation).toBe(true);
  });
});

// ---- prompts ----------------------------------------------------------------

describe('confirmation prompts (spec 0.7, 3.7)', () => {
  it('expire after the answer time: default 30 s, 15 s when set to 15 (spec 0.7)', async () => {
    m.setPromptTtl(15);
    const r = await scanN(1);
    clock = 14_900;
    await expect(m.addCartItem(r.scan.scan_id, FSA, r.voice.prompt_id!)).resolves.toBeTruthy();
    m.setPromptTtl(15);
    const r2 = await m.scan(null);
    clock += 15_100;
    await expect(m.addCartItem(r2.scan.scan_id, FSA, r2.voice.prompt_id!)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
  });

  it('are single use: a second "yes" with the same prompt is rejected', async () => {
    const r = await scanN(1);
    await m.addCartItem(r.scan.scan_id, FSA, r.voice.prompt_id!);
    await expect(m.addCartItem(r.scan.scan_id, FSA, r.voice.prompt_id!)).rejects.toMatchObject({
      code: 'E_PROMPT_EXPIRED',
      retryable: false,
    });
  });

  it('are bound to their scope: a confirm_add prompt cannot clear the cart or pay', async () => {
    const r = await scanN(1);
    await expect(m.clearCart(r.voice.prompt_id!)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
    await expect(m.checkoutConfirm('k', r.voice.prompt_id!)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
  });

  it('an unknown prompt id is rejected, and the rejection carries speech that is safe to speak', async () => {
    const r = await scanN(1);
    const err = await m.addCartItem(r.scan.scan_id, FSA, 'not-a-real-prompt').catch((e) => e);
    expect(err.code).toBe('E_PROMPT_EXPIRED');
    expect(err.speech).toBe("I didn't catch that in time. Shall I ask again?");
  });

  it('a late answer can be re-asked for the same item, with no rescan (WCAG 2.2.1)', async () => {
    const r = await scanN(1);
    clock = 60_000;
    await expect(m.addCartItem(r.scan.scan_id, FSA, r.voice.prompt_id!)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
    const fresh = await m.reissuePrompt(r.scan.scan_id, 'confirm_add');
    expect(fresh.prompt_id).not.toBe(r.voice.prompt_id);
    expect(fresh.expires_in_s).toBe(30);
    const cart = await m.addCartItem(r.scan.scan_id, FSA, fresh.prompt_id);
    expect(cart.cart.groups[0].items[0].display_name).toBe('Advil Ibuprofen 200mg');
  });

  it('re-asking for a scan that was never resolved fails cleanly', async () => {
    const r = await scanN(4); // the unknown item
    await expect(m.reissuePrompt(r.scan.scan_id, 'confirm_add')).rejects.toMatchObject({ code: 'E_PRODUCT_UNRESOLVED' });
    await expect(m.reissuePrompt('no-such-scan', 'confirm_add')).rejects.toMatchObject({ code: 'E_PRODUCT_UNRESOLVED' });
  });
});

// ---- cart -------------------------------------------------------------------

describe('cart (spec 3.8, 4.4, 20.7)', () => {
  it('groups items by card in the order FSA, HSA, Visa, with subtotals and a before-tax total', async () => {
    await scanAndAdd(); // Advil → FSA
    await scanAndAdd(); // bandages → FSA
    const { cart } = await scanAndAdd(); // kettle corn → Visa
    expect(cart.cart.groups.map((g) => [g.card_id, g.subtotal_cents])).toEqual([
      [FSA, 1848],
      [VISA, 499],
    ]);
    expect(cart.cart.total_cents).toBe(2347);
    expectIntegerMoney(cart);
  });

  it('confirms an add with the count in words (spec 4.4 shape)', async () => {
    expect((await scanAndAdd()).cart.voice.text).toBe('Added. You have one item in your cart.');
    expect((await scanAndAdd()).cart.voice.text).toBe('Added. You have two items in your cart.');
  });

  it('"what\'s in my cart" speaks the cart grouped by card, with the before-tax total', async () => {
    await scanAndAdd();
    await scanAndAdd();
    await scanAndAdd();
    const res = await m.command("what's in my cart", null);
    expect(res.action).toBe('read_cart');
    expect(res.voice.text).toBe(
      'Two items totaling $18.48 on your FSA card. One item totaling $4.99 on your Visa credit. Total $23.47 before tax.',
    );
  });

  it('an empty cart says so, in the cart and at checkout (spec 3.6, 20.7)', async () => {
    expect((await m.command("what's in my cart", null)).voice.text).toBe('Your cart is empty.');
    const preview = await m.checkoutPreview();
    expect(preview.groups).toEqual([]);
    expect(preview.voice.text).toBe('Your cart is empty.');
  });

  it('"remove last item" removes the most recent item; with nothing in the cart it says so', async () => {
    await scanAndAdd(); // Advil
    await scanAndAdd(); // bandages
    const res = await m.removeLastCartItem();
    expect(res.voice.text).toBe('Removed Bandages.');
    expect(res.cart.groups[0].items.map((i) => i.display_name)).toEqual(['Advil Ibuprofen 200mg']);
    await m.removeLastCartItem();
    expect((await m.removeLastCartItem()).voice.text).toBe('Your cart is empty.');
  });

  it('"clear cart" asks first, and only a yes bound to that question clears it (spec 3.8)', async () => {
    await scanAndAdd();
    const ask = await m.command('clear cart', null);
    expect(ask.action).toBe('confirm_clear_cart');
    expect(ask.voice.response_scope).toBe('confirm_clear_cart');
    expect((await m.getCart()).groups).toHaveLength(1); // nothing cleared yet
    const yes = await m.command('yes', ask.voice.prompt_id);
    expect(yes.action).toBe('cart_cleared');
    expect((yes.result as Cart).groups).toEqual([]);
  });
});

// ---- checkout ---------------------------------------------------------------

describe('checkout run 1 (spec 4.4, FSA-first seed)', () => {
  it('reads the split, then pays: FSA ends at $6.52 and the low balance is an alert', async () => {
    await scanAndAdd();
    await scanAndAdd();
    await scanAndAdd();
    const preview = await m.checkoutPreview();
    expect(preview.issues).toEqual([]);
    expect(preview.total_cents).toBe(2347);
    expect(preview.voice.text).toBe(
      'Two items totaling $18.48 on your FSA card. One item totaling $4.99 on your Visa credit. Ready to check out?',
    );
    const paid = await m.checkoutConfirm('run1', preview.voice.prompt_id!);
    // Wording extended by Nak (2026-10-24): take your items; invoice is in History. The balance line stays.
    expect(paid.voice.text).toMatch(/^Payment complete\. You paid for your items, so please take them with you\. Your FSA balance is now \$6.52\. Your invoice is saved in History\.$/);
    expect(paid.voice.priority).toBe('alert'); // $6.52 is under the $20 low-balance level
    expect(paid.new_balances).toEqual([
      { card_id: FSA, balance_cents: 652 },
      { card_id: HSA, balance_cents: 34000 },
      { card_id: VISA, balance_cents: 500000 - 499 },
    ]);
    expectIntegerMoney(paid);
  });

  it('a repeated idempotency key returns the original payment and charges nothing twice (spec 3.6, 20.7)', async () => {
    await scanAndAdd();
    const preview = await m.checkoutPreview();
    const first = await m.checkoutConfirm('same-key', preview.voice.prompt_id!);
    const second = await m.checkoutConfirm('same-key', preview.voice.prompt_id!);
    expect(second.payment_id).toBe(first.payment_id);
    expect((await m.getCards()).find((c) => c.id === FSA)!.balance_cents).toBe(2500 - 1299);
  });

  it('after paying, the cart is empty', async () => {
    await scanAndAdd();
    const preview = await m.checkoutPreview();
    await m.checkoutConfirm('k', preview.voice.prompt_id!);
    expect((await m.getCart()).groups).toEqual([]);
  });

  it('a health card that stays healthy after paying is not an alert', async () => {
    m.__testing.setBalance(FSA, 100_000);
    await scanAndAdd();
    const preview = await m.checkoutPreview();
    expect((await m.checkoutConfirm('k', preview.voice.prompt_id!)).voice.priority).toBe('normal');
  });
});

describe('checkout run 2: the card that cannot cover its group (spec 3.5 group rule 2, 4.4)', () => {
  beforeEach(async () => {
    await m.resetDemo(2); // FSA $15.00, HSA $5.00
    await scanAndAdd();
    await scanAndAdd();
    await scanAndAdd();
  });

  it('keeps the largest item on the FSA and moves the rest to the Visa when the HSA is too small too', async () => {
    const preview = await m.checkoutPreview();
    expect(preview.issues).toHaveLength(1);
    expect(preview.issues[0].rule).toBe('group_too_large');
    expect(preview.voice.text).toBe(
      "Your FSA balance is only $15.00, which doesn't cover $18.48. Want me to keep the Advil on your FSA and move the bandages to your Visa credit?",
    );
    expect(preview.voice.priority).toBe('alert');
    expect(preview.groups.map((g) => [g.card_id, g.subtotal_cents])).toEqual([
      [FSA, 1299],
      [VISA, 549 + 499],
    ]);
  });

  it('moves the overflow to the HSA when the HSA has room', async () => {
    m.__testing.setBalance(HSA, 34000);
    const preview = await m.checkoutPreview();
    expect(preview.voice.text).toContain('move the bandages to your HSA card?');
    expect(preview.groups.map((g) => [g.card_id, g.subtotal_cents])).toEqual([
      [FSA, 1299],
      [HSA, 549],
      [VISA, 499],
    ]);
  });

  it('"yes" to the proposed move pays it, and the amounts add up', async () => {
    const preview = await m.checkoutPreview();
    const paid = await m.checkoutConfirm('k', preview.voice.prompt_id!, true);
    // Wording extended by Nak (2026-10-24): take your items; invoice is in History. The balance line stays.
    expect(paid.voice.text).toMatch(/^Payment complete\. You paid for your items, so please take them with you\. Your FSA balance is now \$2.01\. Your invoice is saved in History\.$/);
    expect(paid.new_balances.find((b) => b.card_id === FSA)!.balance_cents).toBe(201);
    const total = paid.groups.reduce((s, g) => s + g.subtotal_cents, 0);
    expect(total).toBe(1299 + 549 + 499);
  });

  it('"no, keep my cards" is a simulated decline: all or nothing, nothing charged (spec 3.6)', async () => {
    const before = await m.getCards();
    const preview = await m.checkoutPreview();
    const err = await m.checkoutConfirm('k', preview.voice.prompt_id!, false).catch((e) => e);
    expect(err.code).toBe('E_CARD_DECLINED');
    expect(err.retryable).toBe(false);
    expect(err.speech).toContain('declined');
    expect(err.speech).toContain('Nothing was charged');
    expect(await m.getCards()).toEqual(before); // balances untouched
    expect((await m.getCart()).groups.length).toBeGreaterThan(0); // cart kept
  });

  it('after a decline the old question is spent; a fresh preview can be paid (spec 20.7 double confirm)', async () => {
    const preview = await m.checkoutPreview();
    await m.checkoutConfirm('d1', preview.voice.prompt_id!, false).catch(() => {});
    await expect(m.checkoutConfirm('d2', preview.voice.prompt_id!, true)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
    const again = await m.checkoutPreview();
    await expect(m.checkoutConfirm('d3', again.voice.prompt_id!, true)).resolves.toBeTruthy();
  });
});

describe('a balance that changed between the scan and checkout (spec 3.6, 20.6)', () => {
  it('is caught at preview: routing is re-run against the fresh balance and the move is proposed', async () => {
    await scanAndAdd(); // Advil on the FSA (balance $25.00 at scan time)
    m.__testing.setBalance(FSA, 500); // the balance dropped before checkout
    const preview = await m.checkoutPreview();
    expect(preview.issues[0]?.rule).toBe('group_too_large');
    expect(preview.voice.text).toContain("Your FSA balance is only $5.00, which doesn't cover $12.99");
    expect(preview.voice.expects_response).toBe(true); // re-confirmation required
  });
});

// ---- voice commands ---------------------------------------------------------

describe('command interpreter: a deterministic keyword matcher (spec 3.8)', () => {
  it.each([
    ['skip it', 'skip'],
    ['Skip it!', 'skip'],
    ['no', 'skip'],
    ['read it again', 'repeat'],
    ['repeat that', 'repeat'],
    ['checkout', 'checkout_preview'],
    ['check out', 'checkout_preview'],
    ["what's in my cart", 'read_cart'],
    ['  WHAT IS IN MY CART  ', 'read_cart'],
    ['remove last item', 'remove_last'],
    ['clear cart', 'confirm_clear_cart'],
    ['accessibility settings', 'open_settings'],
  ])('"%s" → %s', async (said, action) => {
    await scanAndAdd(); // something in the cart so cart commands have work to do
    expect((await m.command(said, null)).action).toBe(action);
  });

  it('"add that" / "add it" / "yes" add the scanned item only while its question is live', async () => {
    for (const phrase of ['add that', 'add it', 'yes']) {
      await m.resetDemo(1);
      const r = await scanN(1);
      const res = await m.command(phrase, r.voice.prompt_id);
      expect(res.action).toBe('add_item');
    }
  });

  it('"yes" with no live question does nothing (spec 3.8: yes needs a live confirm_add prompt)', async () => {
    const res = await m.command('yes', null);
    expect(res.action).toBe('unknown');
    expect((await m.getCart()).groups).toEqual([]);
  });

  it('"yes" after the question expired is refused with E_PROMPT_EXPIRED (the app then asks again) and adds nothing', async () => {
    const r = await scanN(1);
    clock = 120_000;
    await expect(m.command('yes', r.voice.prompt_id)).rejects.toMatchObject({
      code: 'E_PROMPT_EXPIRED',
      speech: "I didn't catch that in time. Shall I ask again?",
    });
    expect((await m.getCart()).groups).toEqual([]);
  });

  it.each([
    ["I don't know"],
    ['what is in my cart now'],
    ['another one please'],
    ['nothing'],
    ['note that down'],
  ])('"%s" is not mistaken for "no" (whole words only)', async (said) => {
    expect((await m.command(said, null)).action).not.toBe('skip');
  });

  it('"read it again" re-speaks the last line word for word', async () => {
    const r = await scanN(1);
    const again = await m.command('repeat that', null);
    expect(again.voice.text).toBe(r.voice.text);
  });

  it('with nothing said yet, "repeat that" admits it', async () => {
    expect((await m.command('repeat that', null)).voice.text).toBe("I haven't said anything yet.");
  });

  it('an unknown phrase gets the spec wording and no action (spec 0.7 E_STT_LOW_CONFIDENCE)', async () => {
    const res = await m.command('purple monkey dishwasher', null);
    expect(res.action).toBe('unknown');
    expect(res.voice.text).toBe("I didn't catch that. You can say add that, skip it, or checkout.");
  });

  it('"skip it" discards the question so a later "yes" cannot add the skipped item', async () => {
    const r = await scanN(1);
    await m.command('skip it', r.voice.prompt_id);
    await expect(m.command('yes', r.voice.prompt_id)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
    expect((await m.getCart()).groups).toEqual([]);
  });
});

// ---- prescriptions ----------------------------------------------------------

describe('prescription bottle (spec 2.3, 20.4, 20.5)', () => {
  it('reads the drug name and strength back and asks before anything proceeds', async () => {
    const r = await scanN(5);
    expect(r.voice.response_scope).toBe('confirm_strength');
    expect(r.voice.text).toBe('I see a prescription label. Omeprazole, 20 milligrams. Is that right?');
    expect(r.scan.product).toMatchObject({ name: 'Omeprazole', size: '20 mg', is_medication: true, is_prescription_only: true });
    expect(r.recommendation).toBeNull(); // no payment routing for a prescription
  });

  it('never states eligibility for a medication with no exact UPC match (decision 3)', async () => {
    expect((await scanN(5)).scan.eligibility.label).toBe('could_not_confirm');
  });

  it('after "yes": the plan copay and a pharmacist check, and nothing is added to any card (decision 4)', async () => {
    const r = await scanN(5);
    const res = await m.command('yes', r.voice.prompt_id);
    expect(res.action).toBe('strength_confirmed');
    expect(res.voice.text).toContain('$10.00 copay');
    expect(res.voice.text).toContain('Please confirm the copay with the pharmacist');
    expect((await m.getCart()).groups).toEqual([]);
  });

  it('"no" lets the shopper scan again; nothing is confirmed', async () => {
    const r = await scanN(5);
    expect((await m.command('no', r.voice.prompt_id)).action).toBe('skip');
    expect((await m.getCart()).groups).toEqual([]);
  });

  it('the confirmation is single use', async () => {
    const r = await scanN(5);
    await m.command('yes', r.voice.prompt_id);
    await expect(m.command('yes', r.voice.prompt_id)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
  });
});

// ---- reset ------------------------------------------------------------------

describe('reset_demo (spec 3.4, 3.12)', () => {
  it('run twice, gives identical output', async () => {
    const a = await m.resetDemo(1);
    const b = await m.resetDemo(1);
    expect(b).toEqual(a);
  });

  it('run 1 and run 2 set the documented balances; the Visa is always $5,000.00', async () => {
    const one = await m.resetDemo(1);
    const two = await m.resetDemo(2);
    const bal = (cards: typeof one.cards) => Object.fromEntries(cards.map((c) => [c.id, c.balance_cents]));
    expect(bal(one.cards)).toEqual({ [FSA]: 2500, [HSA]: 34000, [VISA]: 500000 });
    expect(bal(two.cards)).toEqual({ [FSA]: 1500, [HSA]: 500, [VISA]: 500000 });
  });

  it('empties the cart, restarts the shelf, and spends every open question', async () => {
    const r = await scanN(1);
    await m.addCartItem(r.scan.scan_id, FSA, r.voice.prompt_id!);
    const open = await m.scan(null);
    await m.resetDemo(1);
    expect((await m.getCart()).groups).toEqual([]);
    expect((await m.scan(null)).scan.product.name).toBe('Advil Ibuprofen 200mg'); // shelf restarted
    await expect(m.addCartItem(open.scan.scan_id, FSA, open.voice.prompt_id!)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
  });
});

// ---- cards and onboarding ---------------------------------------------------

describe('cards and onboarding data (business spec 6.1, tech spec 3.3)', () => {
  it('seeds an FSA, an HSA, and a Visa credit, all Visa cards, FSA first', async () => {
    const cards = await m.getCards();
    expect(cards.map((c) => [c.id, c.type, c.network])).toEqual([
      [FSA, 'fsa', 'visa'],
      [HSA, 'hsa', 'visa'],
      [VISA, 'general', 'visa'],
    ]);
    expect(cards.every((c) => c.status === 'active')).toBe(true);
  });

  it('an insurance card read has the member name, plan, Rx benefits, and only the last 4 of the member ID', async () => {
    const res = await m.scanCard('insurance');
    expect(res.state).toBe('read');
    expect(res.insurance).toMatchObject({ member_first_name: 'Alex', member_last_name: 'Rivera' });
    expect(res.insurance!.member_id_last4).toMatch(/^\d{4}$/);
    expect(res.insurance!.rx!.copays.length).toBeGreaterThan(0);
    expectIntegerMoney(res);
  });

  it('a payment card read has the network, type, and only the last 4 digits (never a full number)', async () => {
    const res = await m.scanCard('payment');
    expect(res.payment!.last4).toMatch(/^\d{4}$/);
    expect(JSON.stringify(res)).not.toMatch(/\d{8,}/); // no long digit run anywhere
  });

  it('adding a card of a type already linked updates it instead of duplicating (no duplicate cards)', async () => {
    await m.linkCard({ type: 'fsa', nickname: 'FSA card', last4: '9999', network: 'visa' });
    const cards = await m.getCards();
    expect(cards).toHaveLength(3);
    expect(cards.find((c) => c.id === FSA)!.last4).toBe('9999');
  });
});

// Proposed (approved by Nak 2026-10-24, not in the spec yet): tap a cart item to review it.
describe('cart item review', () => {
  const threeItems = async () => {
    let cart: Cart = { groups: [], total_cents: 0 };
    for (let i = 0; i < 3; i++) cart = (await scanAndAdd()).cart.cart;
    return cart;
  };
  const items = (c: Cart) => c.groups.flatMap((g) => g.items);

  it('reads the item back and asks; yes removes it, then offers the other items', async () => {
    const cart = await threeItems();
    const first = items(cart)[0];
    const ask = await m.reviewCartItem(first.id);
    expect(ask.voice.response_scope).toBe('confirm_remove_item');
    expect(ask.voice.text).toContain(first.display_name);
    const res = await m.command('yes', ask.voice.prompt_id);
    expect(items(res.result as Cart)).toHaveLength(2);
    expect(res.voice.response_scope).toBe('confirm_review_rest');
    expect(res.voice.text).toMatch(/two other items/);
  });

  it('no keeps the item; answering no to the rest closes with the checkout line', async () => {
    const cart = await threeItems();
    const ask = await m.reviewCartItem(items(cart)[0].id);
    const kept = await m.command('no', ask.voice.prompt_id);
    expect(items(kept.result as Cart)).toHaveLength(3);
    const done = await m.command('no', kept.voice.prompt_id);
    expect(done.action).toBe('review_done');
    expect(done.voice.text).toMatch(/ready to checkout/i);
  });

  it('yes to the rest reviews the next unreviewed item', async () => {
    const cart = await threeItems();
    const ask = await m.reviewCartItem(items(cart)[0].id);
    const kept = await m.command('no', ask.voice.prompt_id);
    const next = await m.command('yes', kept.voice.prompt_id);
    expect(next.voice.response_scope).toBe('confirm_remove_item');
    expect(next.voice.text).not.toContain(items(cart)[0].display_name);
  });

  it('an answer after the prompt expires is E_PROMPT_EXPIRED', async () => {
    const cart = await threeItems();
    const ask = await m.reviewCartItem(items(cart)[0].id);
    clock = 31_000;
    await expect(m.command('yes', ask.voice.prompt_id)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
  });
});

// Proposed (business spec 6.6, stretch): invoices for the purchase history.
describe('payment history', () => {
  it('seeds mock invoices with store details, integer money, and a fixed-rate tax estimate', async () => {
    const list = await m.getPaymentHistory();
    expect(list.length).toBeGreaterThan(0);
    for (const inv of list) {
      expect(inv.store.phone).toMatch(/555/); // fictional numbers only (business spec 6.6)
      expect(inv.total_cents).toBe(inv.subtotal_cents + inv.tax_cents);
      expect(inv.tax_cents).toBe(Math.round((inv.subtotal_cents * 725) / 10000));
      expectIntegerMoney(inv);
    }
  });

  it('marks eligible items paid with an everyday card as possible reimbursement', async () => {
    const list = await m.getPaymentHistory();
    const inv = list.find((i) => i.invoice_id === 'inv_seed_4')!;
    expect(inv.reimbursable_cents).toBe(899); // Tylenol on Visa; the granola bars are not eligible
  });

  it('adds an invoice after a completed payment and resets with the demo', async () => {
    await scanAndAdd();
    const before = (await m.getPaymentHistory()).length;
    const prev = await m.checkoutPreview();
    await m.checkoutConfirm('key-1', prev.voice.prompt_id!);
    const after = await m.getPaymentHistory();
    expect(after).toHaveLength(before + 1);
    expect(after[0].lines.length).toBeGreaterThan(0);
    await m.resetDemo(1);
    expect(await m.getPaymentHistory()).toHaveLength(before);
  });
});

describe('checkout invoice and mixed cards', () => {
  it('pays eligible items with the FSA and the ineligible one with the everyday Visa in one payment', async () => {
    await scanAndAdd(); // Advil (eligible) -> FSA
    await scanAndAdd(); // Bandages (eligible) -> FSA
    const kettle = await scanAndAdd(); // Kettle corn (not eligible) -> everyday Visa, automatically
    expect(kettle.r.recommendation!.card_id).toBe(VISA);
    const preview = await m.checkoutPreview();
    const paid = await m.checkoutConfirm('mixed-1', preview.voice.prompt_id!);
    expect(paid.groups.map((g) => g.card_id).sort()).toEqual([FSA, VISA].sort());
    expect(paid.invoice!.payments.map((p) => p.card_id).sort()).toEqual([FSA, VISA].sort());
    expect(paid.invoice!.lines.find((l) => l.eligibility_label === 'not_eligible')!.card_type).toBe('general');
    expect(paid.invoice!.total_cents).toBe(paid.invoice!.subtotal_cents + paid.invoice!.tax_cents);
  });
});

// Prototype only (not in the specs, which say "no tracked locations"; see HISTORY_DESIGN.md).
describe('store check-in', () => {
  const WALMART = { lat: 37.8044, lng: -122.2712 };

  it('asks only when the phone is within 150 m of a seeded store', async () => {
    expect(await m.nearbyStore({ lat: 37.0, lng: -122.0 })).toBeNull();
    const near = await m.nearbyStore({ lat: WALMART.lat + 0.0005, lng: WALMART.lng }); // about 55 m
    expect(near!.store.name).toBe('Walmart Pharmacy');
    expect(near!.voice.response_scope).toBe('confirm_checkin');
    expect(near!.voice.text).toContain(near!.store.address);
  });

  it('yes checks in, speaks the address and the next step; invoices then use that store', async () => {
    const ask = (await m.nearbyStore(null, 'store_walmart'))!;
    const res = await m.command('yes', ask.voice.prompt_id);
    expect(res.action).toBe('checked_in');
    expect(res.voice.text).toMatch(/officially checked in at Walmart Pharmacy, 2200 Sample Blvd/);
    expect(res.voice.text).toMatch(/point your camera at an item/i);
    await scanAndAdd();
    const prev = await m.checkoutPreview();
    const paid = await m.checkoutConfirm('checkin-1', prev.voice.prompt_id!);
    expect(paid.invoice!.store.name).toBe('Walmart Pharmacy');
    expect(await m.nearbyStore(null, 'store_walmart')).toBeNull(); // already checked in
  });

  it('no does not check in', async () => {
    const ask = (await m.nearbyStore(null, 'store_walmart'))!;
    const res = await m.command('no', ask.voice.prompt_id);
    expect(res.action).toBe('skip');
  });

  it('the invoice never carries coordinates', async () => {
    for (const inv of await m.getPaymentHistory()) expect(Object.keys(inv.store).sort()).toEqual(['address', 'name', 'phone']);
  });
});
