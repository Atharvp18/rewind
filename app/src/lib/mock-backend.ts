/**
 * Offline stand-in for the FastAPI backend, used only when api.ts has
 * USE_MOCK = true. It replays the demo shelf (Advil, bandages, kettle corn,
 * then one unknown item) and follows the run 1 / run 2 script in tech spec 4.4.
 *
 * This file must never be imported by anything except lib/api.ts. In
 * production, backend/speech/compose.py is the only source of spoken wording;
 * the lines here are copies of the spec's demo script so the UI can be built
 * before the backend is ready.
 */

import { randomUUID } from 'expo-crypto';

import type {
  Card,
  CardScanKind,
  CardScanResult,
  LinkCardRequest,
  Cart,
  CartGroup,
  CartItem,
  CartResponse,
  CheckoutPreview,
  CheckoutResult,
  CommandResponse,
  EligibilityResult,
  Health,
  PaymentRecommendation,
  ProductResolution,
  ResponseScope,
  ScanResponse,
  SttResponse,
  TtsResponse,
  VoiceRequest,
} from '@/lib/api';
import { ApiError } from '@/lib/api-error';
import { formatCents } from '@/lib/money';

const LATENCY_MS = 700;
const PROMPT_TTL_MS = 15_000;
const LOW_BALANCE_CENTS = 2000;

const wait = (ms = LATENCY_MS) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Seed data (tech spec 3.3)
// ---------------------------------------------------------------------------

const seedCards = (hsaCents: number): Card[] => [
  { id: 'card_hsa_1', type: 'hsa', nickname: 'HSA card', balance_cents: hsaCents, status: 'active' },
  { id: 'card_visa_1', type: 'general', nickname: 'Visa credit', balance_cents: 500000, status: 'active' },
];

type DemoItem = {
  product: Omit<ProductResolution, 'product_key' | 'warnings'>;
  eligibility: EligibilityResult;
  spokenName: string;
};

const SHELF: DemoItem[] = [
  {
    spokenName: 'Advil, ibuprofen 200mg',
    product: {
      upc: 'REPLACE_ADVIL', name: 'Advil Ibuprofen 200mg', brand: 'Advil', size: '200mg',
      category: 'pain_relief', is_medication: true, is_prescription_only: false,
      amount_cents: 1299, price_source: 'seeded', state: 'resolved',
    },
    eligibility: {
      label: 'eligible', confidence: null, basis: 'upc_match', source: 'hand_entered',
      collected_at: '2026-10-24', matched_name: 'Advil Ibuprofen 200mg',
    },
  },
  {
    spokenName: 'Bandages',
    product: {
      upc: 'REPLACE_BANDAGES', name: 'Bandages', brand: null, size: null,
      category: 'first_aid', is_medication: false, is_prescription_only: false,
      amount_cents: 549, price_source: 'seeded', state: 'resolved',
    },
    eligibility: {
      label: 'eligible', confidence: null, basis: 'upc_match', source: 'hand_entered',
      collected_at: '2026-10-24', matched_name: 'Bandages',
    },
  },
  {
    spokenName: 'Kettle corn',
    product: {
      upc: 'REPLACE_KETTLE_CORN', name: 'Kettle Corn', brand: null, size: null,
      category: 'grocery', is_medication: false, is_prescription_only: false,
      amount_cents: 499, price_source: 'seeded', state: 'resolved',
    },
    eligibility: {
      label: 'not_eligible', confidence: null, basis: 'irs_category_rule', source: 'irs_rules',
      collected_at: null, matched_name: null,
    },
  },
];

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

type StoredItem = CartItem & { card_id: string; seq: number };
type Prompt = { scope: ResponseScope; scan_id: string | null; expiresAt: number; consumed: boolean };
type ProposedSplit = { item_id: string; card_id: string }[];

const state = {
  cards: seedCards(34000),
  items: [] as StoredItem[],
  seq: 0,
  scanIndex: 0,
  scans: new Map<string, { item: DemoItem; rec: PaymentRecommendation | null }>(),
  prompts: new Map<string, Prompt>(),
  payments: new Map<string, CheckoutResult>(),
  proposedSplit: null as ProposedSplit | null,
  lastVoice: null as VoiceRequest | null,
};

const card = (id: string) => state.cards.find((c) => c.id === id)!;
const hsa = () => card('card_hsa_1');
const visa = () => card('card_visa_1');

function voice(
  text: string,
  opts: { prompt?: { scope: ResponseScope; scan_id?: string | null }; priority?: 'alert' | 'normal' } = {},
): VoiceRequest {
  let prompt_id: string | null = null;
  if (opts.prompt) {
    prompt_id = randomUUID();
    state.prompts.set(prompt_id, {
      scope: opts.prompt.scope,
      scan_id: opts.prompt.scan_id ?? null,
      expiresAt: Date.now() + PROMPT_TTL_MS,
      consumed: false,
    });
  }
  const v: VoiceRequest = {
    request_id: randomUUID(),
    prompt_id,
    text,
    priority: opts.priority ?? 'normal',
    expects_response: !!opts.prompt,
    response_scope: opts.prompt?.scope ?? 'none',
    sentences: text.split(/(?<=[.?!])\s+/).filter(Boolean),
  };
  state.lastVoice = v;
  return v;
}

function consumePrompt(promptId: string | null, scope: ResponseScope): Prompt {
  const p = promptId ? state.prompts.get(promptId) : undefined;
  if (!p || p.consumed || p.scope !== scope || Date.now() > p.expiresAt) {
    throw new ApiError({
      code: 'E_PROMPT_EXPIRED',
      message: 'prompt missing, expired, consumed, or wrong scope',
      speech: "I didn't catch that in time. Shall I ask again?",
      retryable: false,
    });
  }
  p.consumed = true;
  return p;
}

function livePrompt(): [string, Prompt] | null {
  for (const [id, p] of [...state.prompts.entries()].reverse()) {
    if (!p.consumed && Date.now() <= p.expiresAt) return [id, p];
  }
  return null;
}

/** "$340" for whole dollars, as in the demo script; otherwise "$12.99". */
const spokenBalance = (cents: number) =>
  cents % 100 === 0 ? formatCents(cents).replace(/\.00$/, '') : formatCents(cents);

const countWord = (n: number) =>
  ['No items', 'One item', 'Two items', 'Three items', 'Four items', 'Five items'][n] ?? `${n} items`;

function buildCart(split?: ProposedSplit | null): Cart {
  const assign = (it: StoredItem) => split?.find((s) => s.item_id === it.id)?.card_id ?? it.card_id;
  const groups: CartGroup[] = [];
  for (const c of state.cards) {
    const items = state.items.filter((it) => assign(it) === c.id);
    if (!items.length) continue;
    groups.push({
      card_id: c.id,
      nickname: c.nickname,
      items: items.map(({ id, scan_id, display_name, amount_cents, eligibility_label }) => ({
        id, scan_id, display_name, amount_cents, eligibility_label,
      })),
      subtotal_cents: items.reduce((s, it) => s + it.amount_cents, 0),
    });
  }
  return { groups, total_cents: groups.reduce((s, g) => s + g.subtotal_cents, 0) };
}

function cartSummary(cart: Cart): string {
  if (!cart.groups.length) return 'Your cart is empty.';
  const parts = cart.groups.map(
    (g) => `${countWord(g.items.length)} totaling ${formatCents(g.subtotal_cents)} on your ${g.nickname}.`,
  );
  return `${parts.join(' ')} Total ${formatCents(cart.total_cents)} before tax.`;
}

// ---------------------------------------------------------------------------
// Routing (a tiny copy of tech spec 3.5, enough for the demo shelf)
// ---------------------------------------------------------------------------

function route(scanId: string, item: DemoItem): PaymentRecommendation {
  const amount = item.product.amount_cents ?? 0;
  const base = {
    scan_id: scanId, amount_cents: amount, amount_basis: 'shelf_price' as const,
    requires_confirmation: true, reroute: null, card_options: [] as string[],
  };
  if (item.eligibility.label === 'not_eligible') {
    return { ...base, decision: 'route_to_general', card_id: visa().id, reason_code: 'not_eligible',
      balance_before_cents: visa().balance_cents, balance_after_cents: visa().balance_cents - amount };
  }
  if (item.eligibility.label === 'could_not_confirm') {
    return { ...base, decision: 'ask_user', card_id: null, reason_code: 'eligibility_unconfirmed',
      balance_before_cents: null, balance_after_cents: null, card_options: state.cards.map((c) => c.id) };
  }
  if (hsa().balance_cents >= amount) {
    return { ...base, decision: 'route_to_hsa', card_id: hsa().id, reason_code: 'eligible_sufficient_balance',
      balance_before_cents: hsa().balance_cents, balance_after_cents: hsa().balance_cents - amount };
  }
  return { ...base, decision: 'ask_user', card_id: null, reason_code: 'eligible_insufficient_balance',
    balance_before_cents: hsa().balance_cents, balance_after_cents: null,
    reroute: { from_card_id: hsa().id, to_card_id: visa().id, reason: 'insufficient_balance' },
    card_options: [visa().id] };
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<Health> {
  return {
    status: 'ok',
    upstreams: { claude: 'ok', cartesia: 'ok', moss: 'ok', nessie: 'ok', supabase: 'ok' },
  };
}

export async function scan(_barcode: string | null): Promise<ScanResponse> {
  await wait(1200);
  const scanId = randomUUID();
  const idx = state.scanIndex++ % (SHELF.length + 1);
  const timestamp = new Date().toISOString();

  if (idx === SHELF.length) {
    // A judge's own item: the unresolved path must work cleanly (4.6).
    state.scans.set(scanId, { item: null as any, rec: null });
    return {
      scan: {
        scan_id: scanId, timestamp, state: 'unresolved', warnings: ['E_PRODUCT_UNRESOLVED'],
        product: {
          product_key: 'n:unknown', upc: null, name: 'Unknown item', brand: null, size: null,
          category: 'other', is_medication: false, is_prescription_only: false, amount_cents: null,
          price_source: null, state: 'unresolved', warnings: [],
        },
        eligibility: { label: 'could_not_confirm', confidence: null, basis: 'no_match', source: null,
          collected_at: null, matched_name: null },
      },
      recommendation: null,
      voice: voice('I could not confirm this item. Try another angle, or tell me what it is.'),
    };
  }

  const item = SHELF[idx];
  const rec = route(scanId, item);
  state.scans.set(scanId, { item, rec });
  const price = formatCents(item.product.amount_cents!);
  const text =
    item.eligibility.label === 'eligible'
      ? `I see ${item.spokenName}, ${price}. HSA eligible. Your HSA balance is ${spokenBalance(hsa().balance_cents)}. Want to use your HSA card?`
      : `${item.spokenName}, ${price}. Not HSA eligible, high confidence. I'll put this on your Visa credit card.`;

  return {
    scan: {
      scan_id: scanId, timestamp, state: 'resolved', warnings: [],
      product: { ...item.product, product_key: `upc:${item.product.upc}`, warnings: [] },
      eligibility: item.eligibility,
    },
    recommendation: rec,
    voice: voice(text, { prompt: { scope: 'confirm_add', scan_id: scanId } }),
  };
}

/** What the caller is listening for, so the mock (which cannot hear) can answer sensibly. */
export type SttHint = 'name' | 'yes_no' | 'card_type';

export async function stt(hint?: SttHint): Promise<SttResponse> {
  // No real speech recognition offline: answer with a fixed demo name, "yes"
  // to a live question, otherwise ask about the cart.
  await wait(400);
  if (hint === 'name') return { transcript: 'Alex Rivera', confidence: 0.93 };
  if (hint === 'yes_no') return { transcript: 'yes', confidence: 0.95 };
  if (hint === 'card_type') return { transcript: 'credit card', confidence: 0.95 };
  return { transcript: livePrompt() ? 'yes' : "what's in my cart", confidence: 0.95 };
}

// ---------------------------------------------------------------------------
// PROPOSED onboarding endpoints. Fixed synthetic results; a real card held up
// to the camera is only read by the real backend.
// ---------------------------------------------------------------------------

let paymentScans = 0;

export async function scanCard(kind: CardScanKind): Promise<CardScanResult> {
  await wait(1200);
  if (kind === 'insurance') {
    return {
      state: 'read',
      framing_hint: null,
      insurance: { insurer_name: 'Mock Plan A (synthetic)', plan_name: null, member_id_last4: '0042' },
      payment: null,
    };
  }
  const first = paymentScans++ % 2 === 0;
  return {
    state: 'read',
    framing_hint: null,
    insurance: null,
    payment: first
      ? { network: 'visa', card_type: 'hsa', last4: '4821' }
      : { network: 'visa', card_type: null, last4: '1234' },
  };
}

export async function linkCard(body: LinkCardRequest): Promise<Card> {
  await wait(300);
  // Reuse the seeded card of the same type so the demo balances (3.3) still apply.
  const seeded = state.cards.find((c) => c.type === body.type || (body.type === 'fsa' && c.type === 'hsa'));
  if (seeded) {
    Object.assign(seeded, { last4: body.last4, network: body.network, nickname: body.nickname, type: body.type });
    return { ...seeded };
  }
  const card: Card = {
    id: `card_${body.type}_${state.cards.length + 1}`,
    type: body.type,
    nickname: body.nickname,
    balance_cents: body.type === 'general' ? 500000 : 34000,
    status: 'active',
    last4: body.last4,
    network: body.network,
  };
  state.cards.push(card);
  return { ...card };
}

export async function tts(): Promise<TtsResponse> {
  // Forces the app onto its expo-speech fallback, which is what we want offline.
  throw new ApiError({ code: 'E_UPSTREAM_TIMEOUT', message: 'mock has no TTS', speech: '', retryable: false });
}

function insertItem(scanId: string, cardId: string): void {
  const entry = state.scans.get(scanId);
  if (!entry?.item) throw new ApiError({ code: 'E_PRODUCT_UNRESOLVED', message: 'unknown scan',
    speech: 'I could not confirm this item. Try another angle, or tell me what it is.', retryable: false });
  state.items.push({
    id: randomUUID(), seq: ++state.seq, scan_id: scanId, card_id: cardId,
    display_name: entry.item.product.name, amount_cents: entry.item.product.amount_cents!,
    eligibility_label: entry.item.eligibility.label,
  });
  state.proposedSplit = null;
}

export async function addCartItem(scanId: string, cardId: string, promptId: string): Promise<CartResponse> {
  await wait(300);
  consumePrompt(promptId, 'confirm_add');
  insertItem(scanId, cardId);
  const cart = buildCart();
  return { cart, voice: voice(`Added. You have ${countWord(state.items.length).toLowerCase()} in your cart.`) };
}

export async function getCart(): Promise<Cart> {
  return buildCart();
}

export async function removeLastCartItem(): Promise<CartResponse> {
  await wait(300);
  const last = state.items.sort((a, b) => a.seq - b.seq).pop();
  const cart = buildCart();
  return { cart, voice: voice(last ? `Removed ${last.display_name}.` : 'Your cart is empty.') };
}

export async function clearCart(promptId: string): Promise<CartResponse> {
  await wait(300);
  consumePrompt(promptId, 'confirm_clear_cart');
  state.items = [];
  return { cart: buildCart(), voice: voice('Your cart is cleared.') };
}

export async function getCards(): Promise<Card[]> {
  return state.cards.map((c) => ({ ...c }));
}

export async function checkoutPreview(): Promise<CheckoutPreview> {
  await wait(600);
  if (!state.items.length) {
    return { groups: [], total_cents: 0, issues: [], voice: voice('Your cart is empty.') };
  }
  // Group rule 2 (3.5): keep items in descending amount order while they fit, move the rest.
  const hsaItems = state.items.filter((it) => it.card_id === hsa().id);
  const hsaTotal = hsaItems.reduce((s, it) => s + it.amount_cents, 0);
  if (hsaTotal > hsa().balance_cents) {
    let room = hsa().balance_cents;
    const split: ProposedSplit = [];
    const kept: string[] = [];
    const moved: string[] = [];
    for (const it of [...hsaItems].sort((a, b) => b.amount_cents - a.amount_cents)) {
      if (it.amount_cents <= room) {
        room -= it.amount_cents;
        kept.push(it.display_name.split(' ')[0]);
      } else {
        split.push({ item_id: it.id, card_id: visa().id });
        moved.push(it.display_name.toLowerCase());
      }
    }
    state.proposedSplit = split;
    const cart = buildCart(split);
    const msg = `Your HSA balance is only ${formatCents(hsa().balance_cents)}, which doesn't cover ${formatCents(hsaTotal)}. Want me to keep the ${kept.join(' and the ')} on your HSA and move the ${moved.join(' and the ')} to your Visa credit?`;
    return {
      ...cart,
      issues: [{ rule: 'group_too_large', message: msg }],
      voice: voice(msg, { prompt: { scope: 'confirm_checkout' }, priority: 'alert' }),
    };
  }
  state.proposedSplit = null;
  const cart = buildCart();
  const parts = cart.groups.map(
    (g) => `${countWord(g.items.length)} totaling ${formatCents(g.subtotal_cents)} on your ${g.nickname}.`,
  );
  return {
    ...cart,
    issues: [],
    voice: voice(`${parts.join(' ')} Ready to check out?`, { prompt: { scope: 'confirm_checkout' } }),
  };
}

export async function checkoutConfirm(
  idempotencyKey: string,
  promptId: string,
  useProposedSplit = true,
): Promise<CheckoutResult> {
  await wait(800);
  const existing = state.payments.get(idempotencyKey);
  if (existing) return existing;
  consumePrompt(promptId, 'confirm_checkout');

  const cart = buildCart(useProposedSplit ? state.proposedSplit : null);

  // Simulated decline: a group larger than its card's balance is refused,
  // all or nothing, and nothing is charged (3.6).
  const over = cart.groups.find((g) => g.subtotal_cents > card(g.card_id).balance_cents);
  if (over) {
    const c = card(over.card_id);
    const nickname = c.nickname;
    throw new ApiError({
      code: 'E_CARD_DECLINED',
      message: `simulated decline on ${c.id}`,
      speech: `Your ${nickname} was declined. The balance is ${formatCents(c.balance_cents)} and these items total ${formatCents(over.subtotal_cents)}. Nothing was charged. Want me to move some items to another card?`,
      retryable: false,
    });
  }

  for (const g of cart.groups) card(g.card_id).balance_cents -= g.subtotal_cents;
  state.items = [];
  state.proposedSplit = null;

  const hsaAfter = hsa().balance_cents;
  const result: CheckoutResult = {
    payment_id: randomUUID(),
    groups: cart.groups,
    new_balances: state.cards.map((c) => ({ card_id: c.id, balance_cents: c.balance_cents })),
    voice: voice(`Payment complete. Your HSA balance is now ${formatCents(hsaAfter)}.`, {
      priority: hsaAfter < LOW_BALANCE_CENTS ? 'alert' : 'normal',
    }),
  };
  state.payments.set(idempotencyKey, result);
  return result;
}

export async function resetDemo(run: 1 | 2): Promise<{ cards: Card[]; cart: Cart }> {
  state.cards = seedCards(run === 1 ? 34000 : 1500);
  state.items = [];
  state.scanIndex = 0;
  state.scans.clear();
  state.prompts.clear();
  state.payments.clear();
  state.proposedSplit = null;
  return { cards: await getCards(), cart: buildCart() };
}

const has = (t: string, ...words: string[]) => words.some((w) => t.includes(w));

export async function command(transcript: string, promptId: string | null): Promise<CommandResponse> {
  await wait(400);
  const t = transcript.toLowerCase().trim();
  const live = promptId ? state.prompts.get(promptId) : livePrompt()?.[1];
  const liveId = promptId ?? livePrompt()?.[0] ?? null;

  if (has(t, 'repeat', 'read it again')) {
    return { action: 'repeat', result: null, voice: state.lastVoice ?? voice("I haven't said anything yet.") };
  }
  if (has(t, 'accessibility')) {
    return { action: 'open_settings', result: null, voice: voice('Opening accessibility settings.') };
  }
  if (has(t, 'yes', 'add that', 'add it')) {
    if (live?.scope === 'confirm_add' && live.scan_id) {
      const rec = state.scans.get(live.scan_id)?.rec;
      const cardId = rec?.card_id ?? rec?.card_options[0];
      if (cardId) {
        const res = await addCartItem(live.scan_id, cardId, liveId!);
        return { action: 'add_item', result: res.cart, voice: res.voice };
      }
    }
    if (live?.scope === 'confirm_checkout') {
      const res = await checkoutConfirm(randomUUID(), liveId!);
      return { action: 'checkout_confirmed', result: res, voice: res.voice };
    }
    if (live?.scope === 'confirm_clear_cart') {
      const res = await clearCart(liveId!);
      return { action: 'cart_cleared', result: res.cart, voice: res.voice };
    }
  }
  if (live?.scope === 'confirm_checkout' && state.proposedSplit && has(t, 'no', 'keep')) {
    // The user turned down the reroute: charge the original cards, which declines.
    const res = await checkoutConfirm(randomUUID(), liveId!, false);
    return { action: 'checkout_confirmed', result: res, voice: res.voice };
  }
  if (has(t, 'skip', 'no')) {
    if (liveId && live) live.consumed = true;
    return { action: 'skip', result: null, voice: voice('Skipped.') };
  }
  if (has(t, 'checkout', 'check out')) {
    const preview = await checkoutPreview();
    return { action: 'checkout_preview', result: preview, voice: preview.voice };
  }
  if (has(t, 'remove last')) {
    const res = await removeLastCartItem();
    return { action: 'remove_last', result: res.cart, voice: res.voice };
  }
  if (has(t, 'clear cart')) {
    return {
      action: 'confirm_clear_cart',
      result: null,
      voice: voice('Clear every item from your cart?', { prompt: { scope: 'confirm_clear_cart' } }),
    };
  }
  if (has(t, 'cart')) {
    const cart = buildCart();
    return { action: 'read_cart', result: cart, voice: voice(cartSummary(cart)) };
  }
  return {
    action: 'unknown',
    result: null,
    voice: voice("I didn't catch that. You can say add that, skip it, or checkout."),
  };
}
