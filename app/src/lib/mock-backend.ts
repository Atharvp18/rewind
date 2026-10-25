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
  NearbyStore,
  Store,
  Invoice,
  InvoiceLine,
  EligibilityLabel,
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
  DemoRun,
  VoiceRequest,
} from '@/lib/api';
import { ApiError } from '@/lib/api-error';
import { formatCents } from '@/lib/money';

const LATENCY_MS = 700;
let promptTtlMs = 30_000;

/** Mirrors the user's "Time to answer" setting (proposed TTL header). */
export function setPromptTtl(seconds: number): void {
  promptTtlMs = seconds * 1000;
}

const wait = (ms = LATENCY_MS) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Seed data (tech spec 3.3)
// ---------------------------------------------------------------------------

/**
 * Demo seed (PROPOSED update to tech spec 3.3): an FSA, an HSA, and an
 * everyday Visa credit, all Visa cards.
 *   run 1: FSA $25.00, HSA $340.00 → eligible items go to the FSA first
 *   run 2: FSA $15.00, HSA $5.00   → at checkout the FSA can't cover $18.48;
 *          the overflow can't fit the HSA either, so it moves to the Visa
 */
const SEED: Record<1 | 2, { fsa: number; hsa: number }> = {
  1: { fsa: 2500, hsa: 34000 },
  2: { fsa: 1500, hsa: 500 },
};

/** Run 3 is the two-account setup: HSA ($5.00, same as run 2) and Visa, no FSA card. */
const seedCards = (run: DemoRun): Card[] =>
  [
    { id: 'card_fsa_1', type: 'fsa' as const, nickname: 'FSA card', balance_cents: SEED[run === 3 ? 2 : run].fsa, status: 'active' as const, network: 'visa' as const, last4: '4417' },
    { id: 'card_hsa_1', type: 'hsa' as const, nickname: 'HSA card', balance_cents: SEED[run === 3 ? 2 : run].hsa, status: 'active' as const, network: 'visa' as const },
    { id: 'card_visa_1', type: 'general' as const, nickname: 'Visa credit', balance_cents: 500000, status: 'active' as const, network: 'visa' as const },
  ].filter((c) => !(run === 3 && c.type === 'fsa'));

// ---- invoices (PROPOSED, business spec 6.6) ------------------------------------

/** Fixed-rate tax ESTIMATE, one state, labeled as an estimate. 7.25% as integer basis points. */
const TAX_BP = 725;
const TAX_NOTE = 'Estimated sales tax at 7.25% (one fixed rate). Estimate only: tax on medicine varies.';

/** Fake stores and contact details: 555-01xx numbers are reserved for fiction. */
const STORES = [
  { id: 'store_cvs', name: 'CVS Pharmacy', address: '100 Example Ave, Berkeley, CA 94704', phone: '(555) 010-0142', lat: 37.8716, lng: -122.2727 },
  { id: 'store_walmart', name: 'Walmart Pharmacy', address: '2200 Sample Blvd, Oakland, CA 94607', phone: '(555) 010-0178', lat: 37.8044, lng: -122.2712 },
  { id: 'store_walgreens', name: 'Walgreens', address: '55 Mockingbird Ln, Emeryville, CA 94608', phone: '(555) 010-0119', lat: 37.8313, lng: -122.2852 },
];
const publicStore = (s: (typeof STORES)[number]): Store => ({ id: s.id, name: s.name, address: s.address, phone: s.phone });

const CARD_LAST4: Record<string, string> = { card_fsa_1: '9999', card_hsa_1: '4242', card_visa_1: '1111' };

type SeedLine = [name: string, cents: number, label: EligibilityLabel, cardId: string];

function buildInvoice(id: string, date: string, store: (typeof STORES)[number], seed: SeedLine[]): Invoice {
  const cardsById = seedCards(1);
  const lines: InvoiceLine[] = seed.map(([name, cents, label, cardId]) => ({
    name, qty: 1, unit_cents: cents, amount_cents: cents, eligibility_label: label, card_id: cardId,
    card_type: cardsById.find((c) => c.id === cardId)!.type,
  }));
  const subtotal = lines.reduce((s, l) => s + l.amount_cents, 0);
  const tax = Math.round((subtotal * TAX_BP) / 10000);
  const payments = [...new Set(lines.map((l) => l.card_id))].map((cid) => {
    const c = cardsById.find((x) => x.id === cid)!;
    return {
      card_id: cid, nickname: c.nickname, type: c.type, last4: CARD_LAST4[cid] ?? null,
      amount_cents: lines.filter((l) => l.card_id === cid).reduce((s, l) => s + l.amount_cents, 0),
    };
  });
  return {
    invoice_id: id, date, store: { name: store.name, address: store.address, phone: store.phone }, lines, subtotal_cents: subtotal, tax_cents: tax, tax_note: TAX_NOTE,
    total_cents: subtotal + tax, payments,
    reimbursable_cents: lines
      .filter((l) => l.eligibility_label === 'eligible' && l.card_type === 'general')
      .reduce((s, l) => s + l.amount_cents, 0),
  };
}

/** Earlier purchases, so the history is not empty on first open. Some eligible items sit on the everyday Visa. */
function seedInvoices(): Invoice[] {
  return [
    buildInvoice('inv_seed_4', '2026-10-21T16:42:00', STORES[1], [
      ['Tylenol Extra Strength 500mg', 899, 'eligible', 'card_visa_1'],
      ['Granola bars', 449, 'not_eligible', 'card_visa_1'],
    ]),
    buildInvoice('inv_seed_3', '2026-10-17T10:05:00', STORES[0], [
      ['Omeprazole 20 mg (prescription copay)', 1000, 'eligible', 'card_hsa_1'],
      ['Bandages', 549, 'eligible', 'card_hsa_1'],
    ]),
    buildInvoice('inv_seed_2', '2026-10-09T13:18:00', STORES[2], [
      ['Advil Ibuprofen 200mg', 1299, 'eligible', 'card_visa_1'],
      ['Sunscreen SPF 50', 1149, 'eligible', 'card_fsa_1'],
      ['Chewing gum', 249, 'not_eligible', 'card_visa_1'],
    ]),
    buildInvoice('inv_seed_1', '2026-09-30T18:51:00', STORES[0], [
      ['Allergy relief tablets', 1599, 'eligible', 'card_fsa_1'],
    ]),
  ];
}

/** An invoice for a payment the user just completed in the app (store cycles through the mock list). */
function invoiceFromGroups(id: string, date: string, groups: CartGroup[]): Invoice {
  // The store the user checked in at; otherwise one from the mock list.
  const store = STORES.find((s) => s.id === state.checkedInStoreId) ?? STORES[(state.invoices.length + 1) % STORES.length];
  const seed: SeedLine[] = groups.flatMap((g) =>
    g.items.map((it): SeedLine => [it.display_name, it.amount_cents, it.eligibility_label, g.card_id]),
  );
  return buildInvoice(id, date, store, seed);
}

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

/** Prop pill bottle for the demo (Mock Plan A copay from tech spec 3.3: omeprazole_20mg). */
const RX = { name: 'Omeprazole', strength: '20 mg', spoken: 'Omeprazole, 20 milligrams', copayCents: 1000 };

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

type StoredItem = CartItem & { card_id: string; seq: number };
type Prompt = { scope: ResponseScope; scan_id: string | null; item_id?: string; store_id?: string; expiresAt: number; consumed: boolean };
type ProposedSplit = { item_id: string; card_id: string }[];

const state = {
  cards: seedCards(1),
  items: [] as StoredItem[],
  seq: 0,
  scanIndex: 0,
  scans: new Map<string, { item: DemoItem; rec: PaymentRecommendation | null }>(),
  prompts: new Map<string, Prompt>(),
  payments: new Map<string, CheckoutResult>(),
  invoices: seedInvoices(),
  proposedSplit: null as ProposedSplit | null,
  /** Items already looked at in the current cart review (tap an item, or answer "look at the rest"). */
  reviewed: new Set<string>(),
  /** The store the user confirmed they are at (check-in). */
  checkedInStoreId: null as string | null,
  /** Presenter demo: the next checkout is declined once (spec 3.6 simulated decline). */
  forceDecline: false,
  lastVoice: null as VoiceRequest | null,
};

const card = (id: string) => state.cards.find((c) => c.id === id)!;
const visa = () => card('card_visa_1');

/**
 * Spending order for HSA/FSA-eligible items (team decision 2026-10-24):
 * FSA first (employer money that can be lost when the person leaves that job),
 * then HSA, then the everyday card. Every choice still needs the user's yes.
 */
const HEALTH_ORDER: Card['type'][] = ['fsa', 'hsa'];
const healthCards = () =>
  HEALTH_ORDER.flatMap((t) => state.cards.filter((c) => c.type === t && c.status === 'active'));
/** "FSA card" → "FSA", "Visa credit" stays. For "your FSA balance". */
const short = (c: Card) => c.nickname.replace(/ card$/, '');

function voice(
  text: string,
  opts: { prompt?: { scope: ResponseScope; scan_id?: string | null; item_id?: string; store_id?: string }; priority?: 'alert' | 'normal' } = {},
): VoiceRequest {
  let prompt_id: string | null = null;
  if (opts.prompt) {
    prompt_id = randomUUID();
    state.prompts.set(prompt_id, {
      scope: opts.prompt.scope,
      scan_id: opts.prompt.scan_id ?? null,
      item_id: opts.prompt.item_id,
      store_id: opts.prompt.store_id,
      expiresAt: Date.now() + promptTtlMs,
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
  const health = healthCards();
  if (!health.length) {
    return { ...base, decision: 'route_to_general', card_id: visa().id, reason_code: 'no_health_card_linked',
      balance_before_cents: visa().balance_cents, balance_after_cents: visa().balance_cents - amount };
  }
  const first = health[0];
  if (first.balance_cents >= amount) {
    return { ...base, decision: 'route_to_hsa', card_id: first.id, reason_code: 'eligible_sufficient_balance',
      balance_before_cents: first.balance_cents, balance_after_cents: first.balance_cents - amount };
  }
  // The first card cannot cover it: go straight to the next card in order (FSA, HSA, then the
  // everyday Visa). Nothing is said about the balance; the user still confirms the card.
  const next = health.slice(1).find((c) => c.balance_cents >= amount) ?? (visa().balance_cents >= amount ? visa() : null);
  if (!next) {
    return { ...base, decision: 'blocked', card_id: null, reason_code: 'no_card_covers',
      balance_before_cents: first.balance_cents, balance_after_cents: null };
  }
  return { ...base, decision: next.type === 'general' ? 'route_to_general' : 'route_to_hsa', card_id: next.id,
    reason_code: 'routed_to_next_card', balance_before_cents: next.balance_cents,
    balance_after_cents: next.balance_cents - amount };
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** Presenter demo: decline the next payment once. */
export function demoForceDecline(): void {
  state.forceDecline = true;
}

export async function getHealth(): Promise<Health> {
  return {
    status: 'ok',
    upstreams: { claude: 'ok', cartesia: 'ok', moss: 'ok', nessie: 'ok', supabase: 'ok' },
  };
}

export async function scan(_barcode: string | null): Promise<ScanResponse> {
  await wait(1200);
  const scanId = randomUUID();
  // Shelf order: Advil, bandages, kettle corn, an unknown item, then the prop pill bottle.
  const idx = state.scanIndex++ % (SHELF.length + 2);
  const timestamp = new Date().toISOString();

  if (idx === SHELF.length + 1) {
    // Prop prescription label (business spec 8: never a real one). Read drug name and
    // strength back; nothing proceeds until confirmed (tech spec 2.3).
    state.scans.set(scanId, { item: RX as unknown as DemoItem, rec: null });
    return {
      scan: {
        scan_id: scanId, timestamp, state: 'resolved', warnings: [],
        item_bbox: { x: 0.34, y: 0.28, w: 0.32, h: 0.42 },
        product: {
          product_key: 'n:omeprazole-20mg', upc: null, name: RX.name, brand: null, size: RX.strength,
          category: 'digestive_health', is_medication: true, is_prescription_only: true, amount_cents: null,
          price_source: null, state: 'resolved', warnings: [],
        },
        // Medication without an exact UPC match: never stated eligible (decision 3).
        eligibility: { label: 'could_not_confirm', confidence: null, basis: 'no_match', source: null,
          collected_at: null, matched_name: null },
      },
      recommendation: null,
      voice: voice(`I see a prescription label. ${RX.spoken}. Is that right?`, {
        prompt: { scope: 'confirm_strength', scan_id: scanId },
      }),
    };
  }

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
      voice: voice('I do not see an item in the frame. Please hold the item steady in front of the camera.'),
    };
  }

  const item = SHELF[idx];
  const rec = route(scanId, item);
  state.scans.set(scanId, { item, rec });
  const price = formatCents(item.product.amount_cents!);
  const suggested = rec.card_id ? card(rec.card_id) : null;
  const text =
    item.eligibility.label !== 'eligible'
      ? `${item.spokenName}, ${price}. Not HSA eligible. I'll put this on your Visa credit card.`
      : suggested && rec.reason_code === 'routed_to_next_card'
        ? `I see ${item.spokenName}, ${price}. HSA eligible. Want to use your ${suggested.nickname}?`
        : suggested
          ? `I see ${item.spokenName}, ${price}. HSA eligible. Your ${short(suggested)} balance is ${spokenBalance(suggested.balance_cents)}. Want to use your ${suggested.nickname}?`
          : `I see ${item.spokenName}, ${price}. HSA eligible. I couldn't find a card for this one yet. Would you like to add another card?`;

  return {
    scan: {
      scan_id: scanId, timestamp, state: 'resolved', warnings: [],
      // Synthetic location so the focus corners have something to sit on offline.
      item_bbox: { x: 0.28, y: 0.3, w: 0.44, h: 0.36 },
      product: { ...item.product, product_key: `upc:${item.product.upc}`, warnings: [] },
      eligibility: item.eligibility,
    },
    recommendation: rec,
    voice: voice(text, { prompt: { scope: 'confirm_add', scan_id: scanId } }),
  };
}

/** What the caller is listening for, so the mock (which cannot hear) can answer sensibly. */
export type SttHint = 'yes_no' | 'card_type';

export async function stt(hint?: SttHint): Promise<SttResponse> {
  // No real speech recognition offline: "yes" to a live question, a card type
  // when asked, otherwise ask about the cart.
  await wait(400);
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
      insurance: {
        insurer_name: 'Mock Plan A (synthetic)',
        plan_name: 'PPO Silver',
        member_first_name: 'Alex',
        member_last_name: 'Rivera',
        member_id_last4: '0042',
        rx: {
          bin: '610014',
          pcn: 'MOCKRX',
          group: 'RWND01',
          copays: [
            { label: 'Generic', amount_cents: 1000 },
            { label: 'Brand', amount_cents: 3500 },
          ],
        },
      },
      payment: null,
    };
  }
  const first = paymentScans++ % 2 === 0;
  return {
    state: 'read',
    framing_hint: null,
    insurance: null,
    payment: first
      ? { network: 'visa', card_type: 'hsa', funding: null, last4: '4821' }
      : { network: 'visa', card_type: 'general', funding: 'credit', last4: '1234' },
  };
}

export async function linkCard(body: LinkCardRequest): Promise<Card> {
  await wait(300);
  // Reuse the seeded card of the same type so the demo balances (3.3) still apply.
  const seeded = state.cards.find((c) => c.type === body.type);
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
    speech: 'I do not see an item in the frame. Please hold the item steady in front of the camera.', retryable: false });
  state.items.push({
    id: randomUUID(), seq: ++state.seq, scan_id: scanId, card_id: cardId,
    display_name: entry.item.product.name, amount_cents: entry.item.product.amount_cents!,
    eligibility_label: entry.item.eligibility.label,
  });
  state.proposedSplit = null;
}

export async function reissuePrompt(
  scanId: string,
  scope: ResponseScope,
): Promise<{ prompt_id: string; expires_in_s: number }> {
  await wait(150);
  const entry = state.scans.get(scanId);
  if (!entry?.item) {
    throw new ApiError({ code: 'E_PRODUCT_UNRESOLVED', message: 'unknown scan',
      speech: 'I do not see an item in the frame. Please hold the item steady in front of the camera.', retryable: false });
  }
  const prompt_id = randomUUID();
  state.prompts.set(prompt_id, { scope, scan_id: scanId, expiresAt: Date.now() + promptTtlMs, consumed: false });
  return { prompt_id, expires_in_s: promptTtlMs / 1000 };
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

/** "You also have two other items." (with the reviewed ones left out). */
const otherItems = () => state.items.filter((it) => !state.reviewed.has(it.id));

/** Read one item back and ask whether to remove it. */
export async function reviewCartItem(itemId: string): Promise<CartResponse> {
  state.reviewed.clear(); // a tap starts a fresh review
  return reviewNext(itemId);
}

async function reviewNext(itemId: string): Promise<CartResponse> {
  await wait(200);
  const it = state.items.find((i) => i.id === itemId);
  if (!it) return { cart: buildCart(), voice: voice('That item is no longer in your cart.') };
  state.reviewed.add(it.id);
  return {
    cart: buildCart(),
    item_id: it.id,
    voice: voice(`${it.display_name}, ${spokenBalance(it.amount_cents)}. Do you want to remove it from your cart?`, {
      prompt: { scope: 'confirm_remove_item', item_id: it.id },
    }),
  };
}

/** After an item is settled: offer the rest, or close the review. */
function afterReview(prefix: string): CommandResponse {
  const rest = otherItems();
  if (!rest.length) {
    state.reviewed.clear();
    return { action: 'review_done', result: buildCart(), voice: voice(`${prefix} Let me know when you're ready to checkout.`.trim()) };
  }
  const n = rest.length;
  const word = ['no', 'one', 'two', 'three', 'four', 'five'][n] ?? String(n);
  const text = `${prefix} You also have ${word} other ${n === 1 ? 'item' : 'items'}. Would you like to check ${n === 1 ? 'it' : 'them'} too?`;
  return {
    action: 'review_item',
    result: buildCart(),
    voice: voice(text.trim(), { prompt: { scope: 'confirm_review_rest' } }),
  };
}

export async function clearCart(promptId: string): Promise<CartResponse> {
  await wait(300);
  consumePrompt(promptId, 'confirm_clear_cart');
  state.items = [];
  return { cart: buildCart(), voice: voice('Your cart is cleared.') };
}

const metersBetween = (a: { lat: number; lng: number }, b: { lat: number; lng: number }) => {
  const R = 6371000;
  const rad = (d: number) => (d * Math.PI) / 180;
  const h =
    Math.sin(rad(b.lat - a.lat) / 2) ** 2 +
    Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(rad(b.lng - a.lng) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

/** Within this distance of a seeded store counts as "at the store". */
const AT_STORE_METERS = 150;

export async function nearbyStore(
  coords: { lat: number; lng: number } | null,
  simulateStoreId?: string,
): Promise<NearbyStore | null> {
  await wait(300);
  const found = simulateStoreId
    ? STORES.find((s) => s.id === simulateStoreId)
    : coords
      ? STORES.map((s) => ({ s, d: metersBetween(coords, s) }))
          .filter((x) => x.d <= AT_STORE_METERS)
          .sort((a, b) => a.d - b.d)[0]?.s
      : undefined;
  if (!found || state.checkedInStoreId === found.id) return null;
  return {
    store: publicStore(found),
    voice: voice(`Are you at ${found.name}, ${found.address}? Say yes to check in.`, {
      prompt: { scope: 'confirm_checkin', store_id: found.id },
    }),
  };
}

/** Leaving is judged at a wider radius than arriving, so standing at the edge does not flicker. */
const LEFT_STORE_METERS = 250;

export async function stillAtStore(storeId: string, coords: { lat: number; lng: number }): Promise<boolean> {
  const s = STORES.find((x) => x.id === storeId);
  return !!s && metersBetween(coords, s) <= LEFT_STORE_METERS;
}

export async function getPaymentHistory(): Promise<Invoice[]> {
  return state.invoices.map((i) => ({ ...i }));
}

export async function getCards(): Promise<Card[]> {
  return state.cards.map((c) => ({ ...c }));
}

export async function checkoutPreview(): Promise<CheckoutPreview> {
  await wait(600);
  if (!state.items.length) {
    return { groups: [], total_cents: 0, issues: [], voice: voice('Your cart is empty.') };
  }
  // Group rule 2 (3.5), in spending order: for each HSA/FSA card whose items exceed its
  // balance, keep items (largest first) while they fit; move the rest to the next card
  // in order that has room (HSA, then the everyday Visa).
  const order = [...healthCards(), visa()];
  const room = new Map(order.map((c) => [c.id, c.balance_cents]));
  for (const it of state.items) room.set(it.card_id, (room.get(it.card_id) ?? 0) - it.amount_cents);
  const split: ProposedSplit = [];
  let message: string | null = null;
  for (const [i, c] of order.entries()) {
    if (c.type === 'general') continue;
    const items = state.items.filter((it) => it.card_id === c.id);
    const total = items.reduce((sum, it) => sum + it.amount_cents, 0);
    if (total <= c.balance_cents) continue;
    let left = c.balance_cents;
    room.set(c.id, c.balance_cents);
    for (const it of [...items].sort((x, y) => y.amount_cents - x.amount_cents)) {
      if (it.amount_cents <= left) {
        left -= it.amount_cents;
        continue;
      }
      const dest = order.slice(i + 1).find((d) => (room.get(d.id) ?? 0) >= it.amount_cents) ?? visa();
      room.set(dest.id, (room.get(dest.id) ?? 0) - it.amount_cents);
      split.push({ item_id: it.id, card_id: dest.id });
    }
    message ??= 'redirected';
  }
  if (message) {
    // Redirected to the next card in order, with no talk of balances: the cart simply shows where each item goes.
    state.proposedSplit = split;
    const cart = buildCart(split);
    const parts = cart.groups.map(
      (g) => `${countWord(g.items.length)} totaling ${formatCents(g.subtotal_cents)} on your ${g.nickname}.`,
    );
    return {
      ...cart,
      issues: [],
      voice: voice(`${parts.join(' ')} Ready to check out?`, { prompt: { scope: 'confirm_checkout' } }),
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
  const over = state.forceDecline
    ? cart.groups[0]
    : cart.groups.find((g) => g.subtotal_cents > card(g.card_id).balance_cents);
  state.forceDecline = false;
  if (over) {
    const c = card(over.card_id);
    const nickname = c.nickname;
    throw new ApiError({
      code: 'E_CARD_DECLINED',
      message: `simulated decline on ${c.id}`,
      speech: `Your ${nickname} was declined. The balance is ${formatCents(c.balance_cents)} and these items total ${formatCents(over.subtotal_cents)}. Nothing was charged. Say checkout, or tap Move items, to choose another card.`,
      retryable: false,
    });
  }

  for (const g of cart.groups) card(g.card_id).balance_cents -= g.subtotal_cents;
  state.items = [];
  state.proposedSplit = null;

  // Read back every HSA/FSA card that was charged. A small balance is never flagged or shamed.
  const charged = cart.groups.map((g) => card(g.card_id)).filter((c) => c.type !== 'general');
  const lines = charged.map((c) => `Your ${short(c)} balance is now ${formatCents(c.balance_cents)}.`);
  const paymentId = randomUUID();
  const invoice = invoiceFromGroups(paymentId, new Date().toISOString(), cart.groups);
  const result: CheckoutResult = {
    payment_id: paymentId,
    invoice,
    groups: cart.groups,
    new_balances: state.cards.map((c) => ({ card_id: c.id, balance_cents: c.balance_cents })),
    voice: voice(
      `Thank you. Your payment went through. Please remember to take your items with you. ${lines.join(' ')} Your receipt is saved in History.`.replace(/\s+/g, ' '),
      { priority: 'normal' },
    ),
  };
  state.payments.set(idempotencyKey, result);
  state.invoices.unshift(invoice);
  return result;
}

export async function resetDemo(run: DemoRun): Promise<{ cards: Card[]; cart: Cart }> {
  state.cards = seedCards(run);
  state.lastVoice = null; // a reset is a fresh start: "repeat that" must not replay the last session
  state.items = [];
  state.reviewed.clear();
  state.checkedInStoreId = null;
  state.scanIndex = 0;
  state.scans.clear();
  state.prompts.clear();
  state.payments.clear();
  state.invoices = seedInvoices();
  state.proposedSplit = null;
  return { cards: await getCards(), cart: buildCart() };
}

/**
 * Whole words and phrases only (tech spec 3.8: a deterministic keyword matcher).
 * "no" must not match "know" or "now", and "cart" must not match "carton".
 */
const has = (t: string, ...phrases: string[]) =>
  phrases.some((p) => new RegExp(`(^|[^a-z])${p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^a-z])`).test(t));

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
  if (has(t, 'yes', 'right', 'correct') && live?.scope === 'confirm_strength') {
    // Confirmed: give the plan's copay and send the shopper to the pharmacist (2.3, 20.5).
    // Nothing is added to a card: the copay path is gated (decision 4).
    consumePrompt(liveId, 'confirm_strength');
    return {
      action: 'strength_confirmed',
      result: null,
      voice: voice(
        `Thank you. ${RX.spoken}. Mock Plan A shows a ${formatCents(RX.copayCents)} copay for this prescription. Please confirm the copay with the pharmacist.`,
      ),
    };
  }
  if (live?.scope === 'confirm_remove_item' && has(t, 'yes', 'no', 'keep', 'remove')) {
    const p = consumePrompt(liveId!, 'confirm_remove_item');
    const it = state.items.find((i) => i.id === p.item_id);
    if (has(t, 'yes', 'remove') && it) {
      state.items = state.items.filter((i) => i.id !== it.id);
      state.proposedSplit = null;
      return afterReview(`Removed ${it.display_name}.`);
    }
    return afterReview(it ? `Keeping ${it.display_name}.` : '');
  }
  if (live?.scope === 'confirm_review_rest' && has(t, 'yes', 'no')) {
    consumePrompt(liveId!, 'confirm_review_rest');
    if (has(t, 'yes')) {
      const next = otherItems()[0];
      if (next) {
        const res = await reviewNext(next.id);
        return { action: 'review_item', result: res.cart, voice: res.voice, item_id: res.item_id };
      }
    }
    state.reviewed.clear();
    return { action: 'review_done', result: buildCart(), voice: voice("Okay. Let me know when you're ready to checkout.") };
  }
  if (live?.scope === 'confirm_checkin' && has(t, 'yes', 'no')) {
    const p = consumePrompt(liveId!, 'confirm_checkin');
    const found = STORES.find((s) => s.id === p.store_id);
    if (has(t, 'yes') && found) {
      state.checkedInStoreId = found.id;
      return {
        action: 'checked_in',
        result: publicStore(found),
        voice: voice(
          `You're officially checked in at ${found.name}, ${found.address}. Please point your camera at an item to start shopping.`,
        ),
      };
    }
    return { action: 'skip', result: null, voice: voice('Okay. You can still scan items.') };
  }
  if (has(t, 'close history', 'hide history', 'go back')) {
    return { action: 'close_history', result: null, voice: voice('Closing your purchase history.') };
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
  if (has(t, 'history', 'invoice', 'invoices', 'past purchases', 'receipts', 'past transactions')) {
    return { action: 'open_history', result: null, voice: voice('Here is your purchase history. Swipe or scroll to see every invoice.') };
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


/** Test seam: arrange states the demo script cannot reach on its own. Never used by the app. */
export const __testing = {
  setBalance(id: string, cents: number) {
    card(id).balance_cents = cents;
  },
  setStatus(id: string, status: Card['status']) {
    card(id).status = status;
  },
};
