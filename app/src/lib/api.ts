/**
 * The only module in app/ that talks to the backend (tech spec 1.6).
 * Types mirror backend/models/schemas.py (tech spec 0.5) field for field.
 * Endpoints are the ones in tech spec 0.6, and nothing else.
 */

import { ApiError, type ErrorEnvelope } from '@/lib/api-error';
import * as mock from '@/lib/mock-backend';

// ---------------------------------------------------------------------------
// Configuration: one line to switch laptop IP, tunnel, or hotspot.
// ---------------------------------------------------------------------------

export const BASE_URL = 'http://192.168.1.10:8000';

/** Serve the demo script from lib/mock-backend.ts instead of the network. */
export const USE_MOCK = true;

/**
 * Test seam: lets tests (and the live-contract suite) exercise the real HTTP
 * path and point it at another server without editing the constants above.
 * Never set this in app code.
 */
export const testing: { live: boolean; baseUrl: string | null } = { live: false, baseUrl: null };
const isMock = () => USE_MOCK && !testing.live;
const baseUrl = () => testing.baseUrl ?? BASE_URL;

// ---------------------------------------------------------------------------
// 0.5 shared message schemas
// ---------------------------------------------------------------------------

export type ResultState = 'resolved' | 'partial' | 'unresolved';
export type EligibilityLabel = 'eligible' | 'not_eligible' | 'could_not_confirm';

export interface ProductResolution {
  product_key: string;
  upc: string | null;
  name: string;
  brand: string | null;
  size: string | null;
  category: string;
  is_medication: boolean;
  is_prescription_only: boolean;
  amount_cents: number | null;
  price_source: 'shelf_tag' | 'cache' | 'user_spoken' | 'seeded' | null;
  state: ResultState;
  warnings: string[];
}

export interface EligibilityResult {
  label: EligibilityLabel;
  confidence: number | null;
  basis:
    | 'upc_match'
    | 'semantic_match'
    | 'irs_category_rule'
    | 'package_disagreement'
    | 'no_match'
    | 'index_unavailable';
  source: 'retailer_index' | 'irs_rules' | 'hand_entered' | null;
  collected_at: string | null;
  matched_name: string | null;
}

/** A box as fractions (0..1) of the captured image: x, y = top-left corner. */
export interface NormRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ScanResult {
  scan_id: string;
  timestamp: string;
  state: ResultState;
  product: ProductResolution;
  eligibility: EligibilityResult;
  warnings: string[];
  /**
   * PROPOSED (not in 0.5): where Claude vision found the item in the photo,
   * so the focus corners and pop-up can sit on it. Null if not located.
   * Needs a matching `item_bbox` in VisionExtract and the vision prompt (Tiea).
   */
  item_bbox?: NormRect | null;
}

export interface Reroute {
  from_card_id: string;
  to_card_id: string;
  reason: 'insufficient_balance' | 'group_exceeds_balance' | 'user_choice';
}

export interface PaymentRecommendation {
  scan_id: string;
  decision: 'route_to_hsa' | 'route_to_general' | 'ask_user' | 'blocked';
  card_id: string | null;
  amount_cents: number;
  amount_basis: 'shelf_price' | 'remaining_after_copay';
  balance_before_cents: number | null;
  balance_after_cents: number | null;
  reroute: Reroute | null;
  requires_confirmation: boolean;
  reason_code: string;
  card_options: string[];
}

export type ResponseScope =
  | 'confirm_add'
  | 'choose_card'
  | 'confirm_checkout'
  | 'confirm_clear_cart'
  | 'confirm_strength'
  | 'none';

export interface VoiceRequest {
  request_id: string;
  prompt_id: string | null;
  text: string;
  priority: 'alert' | 'normal';
  expects_response: boolean;
  response_scope: ResponseScope;
  sentences: string[];
}

export interface ScanResponse {
  scan: ScanResult;
  recommendation: PaymentRecommendation | null;
  voice: VoiceRequest;
}

// ---------------------------------------------------------------------------
// 0.6 endpoint payloads
// ---------------------------------------------------------------------------

export type UpstreamStatus = 'ok' | 'degraded' | 'down';
export type Upstream = 'claude' | 'cartesia' | 'moss' | 'nessie' | 'supabase';

export interface Health {
  status: string;
  upstreams: Record<Upstream, UpstreamStatus>;
}

export interface Card {
  id: string;
  type: 'hsa' | 'fsa' | 'general';
  nickname: string;
  balance_cents: number;
  status: 'active' | 'frozen' | 'closed' | 'expired';
  /** PROPOSED (not in 0.6): last 4 digits for display. The full number never reaches the app. */
  last4?: string | null;
  /** PROPOSED (not in 0.6): card network read from the card face. */
  network?: CardNetwork | null;
}

export type CardNetwork = 'visa' | 'mastercard' | 'amex' | 'discover' | 'other';

export interface CartItem {
  id: string;
  scan_id: string;
  display_name: string;
  amount_cents: number;
  eligibility_label: EligibilityLabel;
}

export interface CartGroup {
  card_id: string;
  nickname: string;
  items: CartItem[];
  subtotal_cents: number;
}

export interface Cart {
  groups: CartGroup[];
  total_cents: number;
}

export interface CartResponse {
  cart: Cart;
  voice: VoiceRequest;
}

export interface CheckoutIssue {
  rule: 'item_too_large' | 'group_too_large' | 'nothing_covers' | 'assignment_changed' | string;
  message: string;
}

export interface CheckoutPreview {
  groups: CartGroup[];
  total_cents: number;
  issues: CheckoutIssue[];
  voice: VoiceRequest;
}

export interface CheckoutResult {
  payment_id: string;
  groups: CartGroup[];
  new_balances: { card_id: string; balance_cents: number }[];
  voice: VoiceRequest;
}

/**
 * Actions /v1/command can return (tech spec 3.8). The backend owns the list;
 * unknown values are treated as "just speak the voice".
 */
export type CommandAction =
  | 'add_item'
  | 'skip'
  | 'repeat'
  | 'read_cart'
  | 'checkout_preview'
  | 'checkout_confirmed'
  | 'remove_last'
  | 'confirm_clear_cart'
  | 'cart_cleared'
  | 'open_settings'
  | 'strength_confirmed'
  | 'unknown'
  | (string & {});

export interface CommandResponse {
  action: CommandAction;
  result: unknown;
  voice: VoiceRequest;
}

// ---------------------------------------------------------------------------
// PROPOSED onboarding endpoints (not in tech spec 0.6; need Atharv and Tiea).
// Card images go through the same never-retained path as shelf frames, and
// responses carry the last 4 digits only, never a full card or member number.
// ---------------------------------------------------------------------------

export type CardScanKind = 'insurance' | 'payment';

/**
 * What is read from an insurance card (team decision 2026-10-24): insurer and
 * plan, the member's name, and prescription benefits. Stored on the phone for
 * suggestions. Member ID: last 4 digits only.
 */
export interface InsuranceCard {
  insurer_name: string;
  plan_name: string | null;
  member_first_name: string | null;
  member_last_name: string | null;
  member_id_last4: string | null;
  /** Pharmacy (Rx) benefit fields as printed on the card; null if the card shows none. */
  rx: {
    bin: string | null;
    pcn: string | null;
    group: string | null;
    /** Copays printed on the card, e.g. { label: 'Generic', amount_cents: 1000 }. */
    copays: { label: string; amount_cents: number }[];
  } | null;
}

/**
 * What is read from a payment card (credit, debit, HSA, FSA): only what adding
 * it as a payment method needs. Never the full number, expiry, or security code.
 */
export interface PaymentCardRead {
  network: CardNetwork | null;
  /** null when the card face does not say HSA or FSA; the app then asks. */
  card_type: Card['type'] | null;
  /** For general cards: printed CREDIT / DEBIT, if shown. */
  funding: 'credit' | 'debit' | null;
  last4: string | null;
}

export interface CardScanResult {
  /** `unclear` means try again; `framing_hint` says how ("move closer", "hold steady"). */
  state: 'read' | 'unclear';
  framing_hint: string | null;
  insurance: InsuranceCard | null;
  payment: PaymentCardRead | null;
}

export interface LinkCardRequest {
  type: Card['type'];
  nickname: string;
  last4: string | null;
  network: CardNetwork | null;
}

/** PROPOSED error code: a simulated charge exceeded a card's balance at confirm time. */
export const E_CARD_DECLINED = 'E_CARD_DECLINED';

export interface SttResponse {
  transcript: string;
  confidence: number;
}

export interface TtsResponse {
  request_id: string;
  sentences: { index: number; text: string; audio_url: string }[];
}

// ---------------------------------------------------------------------------
// Error envelope (0.6): one handler for every 4xx/5xx.
// ---------------------------------------------------------------------------

export { ApiError, type ErrorEnvelope } from '@/lib/api-error';
export type { SttHint } from '@/lib/mock-backend';

/** Raised when the backend cannot be reached at all (no envelope to speak). */
export const E_NETWORK = 'E_NETWORK';

const TIMEOUT_MS = 8000;

/**
 * How long the user has to answer a question, from the "Time to answer"
 * setting (WCAG 2.2.1). PROPOSED: sent as a header so the backend's prompt
 * TTL (tech spec 0.7, 15 s) matches the user's choice.
 */
let promptTtlSeconds = 30;
export function setPromptTtl(seconds: number): void {
  promptTtlSeconds = seconds;
  mock.setPromptTtl(seconds);
}
export const PROMPT_TTL_HEADER = 'X-Rewind-Prompt-TTL';

async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    const headers = { ...(init.headers as Record<string, string> | undefined), [PROMPT_TTL_HEADER]: String(promptTtlSeconds) };
    res = await fetch(`${baseUrl()}${path}`, { ...init, headers, signal: controller.signal });
  } catch {
    throw new ApiError({
      code: E_NETWORK,
      message: `network failure on ${path}`,
      speech: '',
      retryable: false,
    });
  } finally {
    clearTimeout(timer);
  }
  if (res.ok) return (await res.json()) as T;

  let envelope: ErrorEnvelope | null = null;
  try {
    envelope = (await res.json()) as ErrorEnvelope;
  } catch {
    // fall through to a generic error below
  }
  const err = new ApiError(
    envelope?.error ?? {
      code: `HTTP_${res.status}`,
      message: `HTTP ${res.status} on ${path}`,
      speech: '',
      retryable: false,
    },
  );
  // Retry once if retryable (1.6). Never retry a request that spends money:
  // checkout confirm is idempotent, so a retry with the same key is safe.
  if (err.retryable && !retried) return request<T>(path, init, true);
  throw err;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export function getHealth(): Promise<Health> {
  if (isMock()) return mock.getHealth();
  return request('/v1/health');
}

/** `imageUri` is a local file:// JPEG, deleted by the caller right after this resolves. */
export function scan(
  imageUri: string,
  barcode?: string | null,
  hintPriceCents?: number | null,
): Promise<ScanResponse> {
  if (isMock()) return mock.scan(barcode ?? null);
  const form = new FormData();
  // React Native's FormData accepts a { uri, name, type } file descriptor.
  form.append('image', { uri: imageUri, name: 'frame.jpg', type: 'image/jpeg' } as any);
  if (barcode) form.append('barcode', barcode);
  if (hintPriceCents != null) form.append('hint_price_cents', String(hintPriceCents));
  return request('/v1/scan', { method: 'POST', body: form });
}

/** `mockHint` only steers the offline mock, which cannot hear; the real backend ignores it. */
export function stt(audioUri: string, mockHint?: mock.SttHint): Promise<SttResponse> {
  if (isMock()) return mock.stt(mockHint);
  const form = new FormData();
  form.append('audio', { uri: audioUri, name: 'speech.wav', type: 'audio/wav' } as any);
  return request('/v1/stt', { method: 'POST', body: form });
}

export function tts(text: string, priority: VoiceRequest['priority']): Promise<TtsResponse> {
  if (isMock()) return mock.tts();
  return request('/v1/tts', json({ text, priority }));
}

/** Absolute URL for an audio_url returned by /v1/tts. */
export function audioUrl(audioUrlOrPath: string): string {
  return audioUrlOrPath.startsWith('http') ? audioUrlOrPath : `${baseUrl()}${audioUrlOrPath}`;
}

export function command(
  transcript: string,
  confidence: number,
  promptId?: string | null,
): Promise<CommandResponse> {
  if (isMock()) return mock.command(transcript, promptId ?? null);
  return request('/v1/command', json({ transcript, confidence, prompt_id: promptId ?? undefined }));
}

export function getCart(): Promise<Cart> {
  if (isMock()) return mock.getCart();
  return request('/v1/cart');
}

export function addCartItem(scanId: string, cardId: string, promptId: string): Promise<CartResponse> {
  if (isMock()) return mock.addCartItem(scanId, cardId, promptId);
  return request('/v1/cart/items', json({ scan_id: scanId, card_id: cardId, prompt_id: promptId }));
}

export function removeLastCartItem(): Promise<CartResponse> {
  if (isMock()) return mock.removeLastCartItem();
  return request('/v1/cart/items/last', { method: 'DELETE' });
}

export function clearCart(promptId: string): Promise<CartResponse> {
  if (isMock()) return mock.clearCart(promptId);
  return request('/v1/cart', { ...json({ prompt_id: promptId }), method: 'DELETE' });
}

export function getCards(): Promise<Card[]> {
  if (isMock()) return mock.getCards();
  return request('/v1/cards');
}

export function checkoutPreview(): Promise<CheckoutPreview> {
  if (isMock()) return mock.checkoutPreview();
  return request('/v1/checkout/preview', { method: 'POST' });
}

/**
 * `useProposedSplit: false` (PROPOSED field) means the user declined the
 * reroute and wants the original cards charged, which can be declined
 * (E_CARD_DECLINED) when a group exceeds its card's balance.
 */
export function checkoutConfirm(
  idempotencyKey: string,
  promptId: string,
  useProposedSplit = true,
): Promise<CheckoutResult> {
  if (isMock()) return mock.checkoutConfirm(idempotencyKey, promptId, useProposedSplit);
  return request(
    '/v1/checkout/confirm',
    json({ idempotency_key: idempotencyKey, prompt_id: promptId, use_proposed_split: useProposedSplit }),
  );
}

/**
 * PROPOSED: a fresh question for a scan whose question expired, so a late
 * answer is never a dead end (WCAG 2.2.1). The new prompt is bound to the
 * same scan and scope; the user's tap or "yes" is still the confirmation.
 */
export function reissuePrompt(
  scanId: string,
  scope: ResponseScope,
): Promise<{ prompt_id: string; expires_in_s: number }> {
  if (isMock()) return mock.reissuePrompt(scanId, scope);
  return request('/v1/prompts/reissue', json({ scan_id: scanId, scope }));
}

/** PROPOSED: read an insurance or payment card held up to the camera. */
export function scanCard(imageUri: string, kind: CardScanKind): Promise<CardScanResult> {
  if (isMock()) return mock.scanCard(kind);
  const form = new FormData();
  form.append('image', { uri: imageUri, name: 'card.jpg', type: 'image/jpeg' } as any);
  form.append('kind', kind);
  return request('/v1/onboarding/card-scan', { method: 'POST', body: form });
}

/** PROPOSED: link a card confirmed during onboarding. */
export function linkCard(body: LinkCardRequest): Promise<Card> {
  if (isMock()) return mock.linkCard(body);
  return request('/v1/cards', json(body));
}

export function resetDemo(run: 1 | 2): Promise<{ cards: Card[]; cart: Cart }> {
  if (isMock()) return mock.resetDemo(run);
  return request('/v1/demo/reset', json({ run }));
}
