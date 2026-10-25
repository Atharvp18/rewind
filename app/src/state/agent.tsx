/**
 * The app state machine (tech spec 1.2), implemented as an explicit reducer,
 * plus the provider that drives speech, captions, prompts, and the API.
 *
 *   idle → listening | capturing
 *   capturing → awaiting_scan → speaking_result | speaking_error
 *   speaking_result → awaiting_confirm (expects_response) | idle
 *   awaiting_confirm → submitting | idle (skip or prompt expired)
 *   submitting → speaking_result
 *   any → interrupted (user speaks while the agent is speaking)
 */

import { formatCents } from '@/lib/money';
import { randomUUID } from 'expo-crypto';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react';
import * as Location from 'expo-location';
import { getRecordingPermissionsAsync } from 'expo-audio';
import { AppState } from 'react-native';

import * as api from '@/lib/api';
import {
  ApiError,
  E_CARD_DECLINED,
  type Card,
  type Cart,
  type CheckoutPreview,
  type CheckoutResult,
  type CommandResponse,
  type Health,
  type ResponseScope,
  type ScanResponse,
  type Store,
  type SttHint,
  type VoiceRequest,
} from '@/lib/api';
import { announce, SPEECH_RATE, useA11y } from '@/lib/a11y';
import { configureAudio, onMicLevel, speaker, useMic } from '@/lib/audio';
import { haptic } from '@/lib/haptics';
import { Phrases, Working } from '@/lib/phrases';
import { useProfile } from '@/lib/profile';

export type Phase =
  | 'idle'
  | 'listening'
  | 'capturing'
  | 'awaiting_scan'
  | 'speaking_result'
  | 'speaking_error'
  | 'awaiting_confirm'
  | 'submitting'
  | 'interrupted';

export interface LivePrompt {
  id: string;
  scope: ResponseScope;
  expiresAt: number;
}

export interface TranscriptLine {
  id: string;
  who: 'agent' | 'user';
  text: string;
}

/** Which content the info panel shows over the camera (one screen, tech spec 1.8 redesign). */
export type PanelView = 'camera' | 'cart' | 'checkout' | 'add_card' | 'profile' | 'history';

export interface AgentState {
  phase: Phase;
  view: PanelView;
  /** Everything said, both sides, newest last (captions, WCAG 1.2.2). Never logged or sent anywhere. */
  transcript: TranscriptLine[];
  /** Spoken text of a declined simulated payment, shown in a red panel until the next checkout. */
  declined: string | null;
  caption: string | null;
  captionIsAlert: boolean;
  lastVoice: VoiceRequest | null;
  livePrompt: LivePrompt | null;
  /** The cart item the agent is asking about; its row slides open to Keep / Remove. */
  reviewId: string | null;
  /** Store check-in (prototype): asking → in. `toast` keeps the confirmation card up briefly. */
  checkin: { store: Store; status: 'asking' | 'in'; toast: boolean } | null;
  lastScan: ScanResponse | null;
  /** Size of the photo behind lastScan, to place its item_bbox on screen. */
  lastPhoto: { width: number; height: number } | null;
  cart: Cart;
  cards: Card[];
  /** undefined until the first check; null when the backend is unreachable. */
  health: Health | null | undefined;
  preview: CheckoutPreview | null;
  receipt: CheckoutResult | null;
  micDenied: boolean;
  /** The camera light: on after a scan that was too dark, until the app restarts or the shopper turns it off. */
  torch: boolean;
}

export type Action =
  | { type: 'listen' }
  | { type: 'listen_done' }
  | { type: 'capture' }
  | { type: 'scan_sent' }
  | { type: 'scan_received'; res: ScanResponse; photo: { width: number; height: number } }
  | { type: 'error' }
  | { type: 'submit' }
  | { type: 'interrupted' }
  | { type: 'idle' }
  | { type: 'speak_start'; voice: VoiceRequest; remember: boolean; interim: boolean; ttlMs: number }
  | { type: 'speak_done'; voice: VoiceRequest }
  | { type: 'prompt_expired'; id: string }
  | { type: 'clear_prompt' }
  | { type: 'set_prompt'; prompt: LivePrompt }
  | { type: 'cart'; cart: Cart }
  | { type: 'cards'; cards: Card[] }
  | { type: 'health'; health: Health | null }
  | { type: 'preview'; preview: CheckoutPreview | null }
  | { type: 'receipt'; receipt: CheckoutResult | null }
  | { type: 'clear_scan' }
  | { type: 'mic_denied' }
  | { type: 'user_said'; text: string }
  | { type: 'declined'; message: string | null }
  | { type: 'review'; id: string | null }
  | { type: 'status'; id: string; text: string }
  | { type: 'reset_all'; cards: Card[]; cart: Cart }
  | { type: 'caption_clear' }
  | { type: 'checkin'; checkin: AgentState['checkin'] }
  | { type: 'view'; view: PanelView };

const SILENCE_MS = 8_000;
const LOOKING_MS = 1_000;
const LISTEN_WINDOW_MS = 6_000;
/** Interrupt by speaking: mic level (0..1) that counts as a voice, how long it must last, and how much to keep. */
const VOICE_LEVEL = 0.3;
const VOICE_HOLD_MS = 250;
const VOICE_KEEP_MS = 1_200;

/** Quiet listening while Rewind talks (interrupt by speaking). One agent per app, so module state is fine. */
const voiceMonitor: { on: boolean; loudSince: number | null; onStart: () => void } = {
  on: false,
  loudSince: null,
  onStart: () => {},
};

/** Phases an interim line may finish in without ending them. */
const BUSY: Phase[] = ['listening', 'capturing', 'awaiting_scan', 'submitting'];

const TRANSCRIPT_MAX = 30;

const pushLine = (t: TranscriptLine[], line: TranscriptLine) =>
  t[t.length - 1]?.id === line.id ? t : [...t, line].slice(-TRANSCRIPT_MAX);

export const initial: AgentState = {
  phase: 'idle',
  view: 'camera',
  transcript: [],
  declined: null,
  caption: null,
  captionIsAlert: false,
  lastVoice: null,
  livePrompt: null,
  reviewId: null,
  checkin: null,
  lastScan: null,
  lastPhoto: null,
  cart: { groups: [], total_cents: 0 },
  cards: [],
  health: undefined,
  preview: null,
  receipt: null,
  micDenied: false,
  torch: false,
};

export function reducer(s: AgentState, a: Action): AgentState {
  switch (a.type) {
    case 'listen':
      return { ...s, phase: 'listening' };
    case 'listen_done':
      // Heard nothing usable: back to waiting for the open question, or idle.
      return { ...s, phase: s.livePrompt ? 'awaiting_confirm' : 'idle' };
    case 'capture':
      return { ...s, phase: 'capturing' };
    case 'scan_sent':
      return { ...s, phase: 'awaiting_scan' };
    case 'scan_received':
      return {
        ...s,
        phase: 'speaking_result',
        lastScan: a.res,
        lastPhoto: a.photo,
        view: 'camera',
        // Too dark to read: turn the light on for the next try (the spoken line says so).
        torch: s.torch || a.res.scan.warnings.includes('E_TOO_DARK'),
      };
    case 'error':
      return { ...s, phase: 'speaking_error' };
    case 'submit':
      return { ...s, phase: 'submitting' };
    case 'interrupted':
      return { ...s, phase: 'interrupted' };
    case 'idle':
      return { ...s, phase: 'idle' };
    case 'speak_start': {
      // A repeated question keeps its original expiry; only a new prompt starts the clock.
      const isNewPrompt = a.voice.expects_response && a.voice.prompt_id && a.voice.prompt_id !== s.livePrompt?.id;
      const prompt = isNewPrompt
        ? { id: a.voice.prompt_id!, scope: a.voice.response_scope, expiresAt: Date.now() + a.ttlMs }
        : s.livePrompt;
      return {
        ...s,
        caption: a.voice.text,
        transcript: pushLine(s.transcript, { id: a.voice.request_id, who: 'agent', text: a.voice.text }),
        captionIsAlert: a.voice.priority === 'alert',
        lastVoice: a.remember ? a.voice : s.lastVoice,
        livePrompt: prompt,
        // An interim line ("Looking.") must not end a busy phase; a real response always does.
        phase: a.interim || s.phase === 'speaking_error' || s.phase === 'listening' ? s.phase : 'speaking_result',
      };
    }
    case 'speak_done':
      // "Looking." can finish while the scan is still in flight; stay busy.
      if (BUSY.includes(s.phase)) return s;
      return { ...s, phase: s.livePrompt ? 'awaiting_confirm' : 'idle' };
    case 'prompt_expired':
      if (s.livePrompt?.id !== a.id) return s;
      return { ...s, livePrompt: null, phase: s.phase === 'awaiting_confirm' ? 'idle' : s.phase };
    case 'clear_prompt':
      return { ...s, livePrompt: null };
    case 'set_prompt':
      return { ...s, livePrompt: a.prompt };
    case 'checkin':
      return { ...s, checkin: a.checkin };
    case 'reset_all':
      // Back to the very start: nothing said, scanned, asked or carried over. Only the fresh cards and cart remain.
      return { ...initial, cards: a.cards, cart: a.cart };
    case 'status':
      // What the agent is doing right now: shown as the caption, not an answer to remember or repeat.
      return {
        ...s,
        caption: a.text,
        captionIsAlert: false,
        transcript: pushLine(s.transcript, { id: a.id, who: 'agent', text: a.text }),
      };
    case 'caption_clear':
      return { ...s, caption: null, captionIsAlert: false };
    case 'review':
      return { ...s, reviewId: a.id };
    case 'cart':
      return { ...s, cart: a.cart };
    case 'cards':
      return { ...s, cards: a.cards };
    case 'health':
      return { ...s, health: a.health };
    case 'preview':
      return { ...s, preview: a.preview };
    case 'receipt':
      return { ...s, receipt: a.receipt };
    case 'clear_scan':
      return { ...s, lastScan: null };
    case 'mic_denied':
      return { ...s, micDenied: true, phase: 'idle' };
    case 'user_said':
      return { ...s, transcript: pushLine(s.transcript, { id: `user-${Date.now()}`, who: 'user', text: a.text }) };
    case 'declined':
      return { ...s, declined: a.message };
    case 'view':
      return { ...s, view: a.view };
  }
}

export interface AgentApi {
  state: AgentState;
  /** Talk button: short tap. Barge-in if speaking, otherwise greet and listen. */
  talkTap: () => void;
  /** Talk button: hold to talk. */
  talkHoldStart: () => void;
  talkHoldEnd: () => void;
  /** Caption pill tap: repeat the last prompt with a haptic pulse (decision 12). */
  repeat: () => void;
  /**
   * Onboarding: route the next thing the user says to `fn` instead of
   * /v1/command. Pass null to restore normal commands.
   */
  /**
   * Route the next thing the user says to `fn` (onboarding). `auto` (default true) opens the mic by
   * itself after the step's line is spoken; card-photo steps pass false so listening never delays the photo.
   */
  setListenHandler: (hint: SttHint | undefined, fn: ((transcript: string) => void) | null, auto?: boolean) => void;
  beginCapture: () => void;
  scanFrame: (
    imageUri: string,
    barcode: string | null,
    discard: () => void,
    photo: { width: number; height: number },
  ) => Promise<void>;
  addToCart: (cardId: string) => Promise<void>;
  skip: () => Promise<void>;
  refreshCart: () => Promise<void>;
  refreshCards: () => Promise<void>;
  /** Ask "Are you at <store>?" (position used once, on the device, never stored). `simulateStoreId` skips GPS for the demo. */
  startCheckin: (simulateStoreId?: string) => Promise<void>;
  /** Presenter demo: the next payment is declined once. */
  demoDecline: () => void;
  /** The user left the store (or the demo says so): the checkout alert and invoice go to History. */
  leaveStore: () => void;
  /** Tap an item in the cart: the agent reads it back and asks whether to remove it. */
  reviewItem: (itemId: string) => Promise<void>;
  removeLast: () => Promise<void>;
  askClearCart: () => Promise<void>;
  confirmClearCart: () => Promise<void>;
  startCheckout: () => Promise<void>;
  /** `useProposedSplit: false` charges the original cards, which can be declined. */
  confirmCheckout: (useProposedSplit?: boolean) => Promise<void>;
  resetDemo: (run: 1 | 2) => Promise<void>;
  /** Start over as a new shopper: server data, everything on screen, the transcript and the profile. */
  restart: (run?: 1 | 2) => Promise<void>;
  showView: (view: PanelView) => void;
  /** Tap equivalent of saying something (e.g. "yes" to a strength read-back); goes through /v1/command. */
  answer: (text: string) => Promise<void>;
  /** Close the current panel and return to the plain camera. */
  dismiss: () => void;
  sayLocal: (text: string, priority?: 'alert' | 'normal') => void;
  /** After an item was scanned and the shopper paused: ask whether to repeat it (a yes repeats it). */
  offerRepeat: () => void;
  /** After an item was scanned and moved out of the frame: ask if there is anything else to scan. */
  askAnythingElse: () => void;
  /** A demo restart: the shopper counts as new, so no "welcome back" until the app is relaunched. */
  markFresh: () => void;
}

const AgentContext = createContext<AgentApi | null>(null);

export const isLocalVoice = (v: VoiceRequest) => v.request_id.startsWith('local-') || v.request_id.startsWith('declined-');

const localVoice = (text: string, priority: 'alert' | 'normal' = 'normal'): VoiceRequest => ({
  request_id: `local-${Date.now()}`,
  prompt_id: null,
  text,
  priority,
  expects_response: false,
  response_scope: 'none',
  sentences: text.split(/(?<=[.?!])\s+/).filter(Boolean),
});

export function AgentProvider({ children }: { children: ReactNode }) {
  const { settings, screenReaderOn } = useA11y();
  const [state, dispatch] = useReducer(reducer, initial);
  const mic = useMic();

  // Refs mirror state for use inside async callbacks and timers.
  const stateRef = useRef(state);
  const insurerRef = useRef<string | null>(null);
  const insurer = useProfile().profile.insurance?.insurer_name || null;
  useEffect(() => {
    insurerRef.current = insurer;
  }, [insurer]);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const silenceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const silencePrompts = useRef(0);
  const promptTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listenTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingAlert = useRef<VoiceRequest | null>(null);
  const listenAfterSpeech = useRef(false);
  const holding = useRef(false);
  const checkoutKey = useRef<string | null>(null);
  const onDoneRef = useRef<(v: VoiceRequest) => void>(() => {});
  const listenHandler = useRef<{ hint?: SttHint; fn: (t: string) => void; auto: boolean } | null>(null);
  /** The mic opened by itself after a question (not a tap): silence there stays quiet. */
  const autoListening = useRef(false);
  /** Unanswered automatic listens in a row; after two the agent waits for a tap (no endless loop). */
  const autoMisses = useRef(0);
  /** A local question was just asked (repeat? anything else?): listen for the answer. */
  const answerNext = useRef(false);

  // --- speech -------------------------------------------------------------

  useEffect(() => {
    speaker.opts = { rate: SPEECH_RATE[settings.speechRate], volume: settings.volume };
  }, [settings.speechRate, settings.volume]);

  const clearSilence = () => {
    if (silenceTimer.current) clearTimeout(silenceTimer.current);
    silenceTimer.current = null;
  };

  const sayRef = useRef<(v: VoiceRequest) => void>(() => {});
  /** A scan answer that arrived while the app was in the background: spoken after "welcome back". */
  const heldVoice = useRef<VoiceRequest | null>(null);

  const say = useCallback(
    (voice: VoiceRequest, remember = true, interim = false) => {
      clearSilence();
      dispatch({ type: 'speak_start', voice, remember, interim, ttlMs: settings.answerSeconds * 1000 });
      // Only a new prompt resets the silence count and expiry timer. Re-asking
      // the same question must not, or the silence prompt would loop (1.2).
      if (voice.expects_response && voice.prompt_id && voice.prompt_id !== stateRef.current.livePrompt?.id) {
        silencePrompts.current = 0;
        if (promptTimer.current) clearTimeout(promptTimer.current);
        const id = voice.prompt_id;
        promptTimer.current = setTimeout(() => {
          // An ignored cart review closes the cart and says how to come back.
          const open = stateRef.current.livePrompt;
          if (open?.id === id && open.scope === 'confirm_checkin') dispatch({ type: 'checkin', checkin: null });
          const ignoredReview =
            open?.id === id && (open.scope === 'confirm_remove_item' || open.scope === 'confirm_review_rest');
          dispatch({ type: 'prompt_expired', id });
          if (ignoredReview) {
            dispatch({ type: 'view', view: 'camera' });
            sayRef.current(localVoice(Phrases.readyToCheckout));
          }
        }, settings.answerSeconds * 1000);
      }
      // Orange level buzz for alerts (low balance, reroute); declines buzz red in handleError.
      if (voice.priority === 'alert' && !voice.request_id.startsWith('declined-')) haptic.warning();
      if (screenReaderOn) {
        // Decision 13: mute our own voice, send the text through the screen reader.
        announce(voice.text);
        setTimeout(() => onDoneRef.current(voice), 0);
      } else {
        speaker.speak(voice);
      }
    },
    [screenReaderOn, settings.answerSeconds],
  );

  useEffect(() => {
    sayRef.current = say;
  });

  const sayLocal = useCallback(
    (text: string, priority: 'alert' | 'normal' = 'normal') => say(localVoice(text, priority)),
    [say],
  );

  /** Say what the agent is doing in the caption (and to a screen reader), without speaking or remembering it. */
  const showStatus = useCallback(
    (text: string) => {
      dispatch({ type: 'status', id: `status-${Date.now()}`, text });
      if (screenReaderOn) announce(text);
    },
    [screenReaderOn],
  );

  // Idle questions are not remembered, so "repeat" still repeats the item, not the question.
  const repeatOffer = useRef(false);
  const fresh = useRef(false);
  const moreOffer = useRef(false);
  const offerRepeat = useCallback(() => {
    repeatOffer.current = true;
    answerNext.current = true;
    say(localVoice(Phrases.askRepeat), false);
  }, [say]);
  const askAnythingElse = useCallback(() => {
    moreOffer.current = true;
    answerNext.current = true;
    say(localVoice(Phrases.askMore), false);
  }, [say]);
  const markFresh = useCallback(() => {
    fresh.current = true;
  }, []);

  // --- errors ---------------------------------------------------------------

  const handleError = useCallback(
    (e: unknown) => {
      dispatch({ type: 'error' });
      if (e instanceof ApiError && e.code === E_CARD_DECLINED) {
        dispatch({ type: 'declined', message: e.speech });
        dispatch({ type: 'preview', preview: null });
        dispatch({ type: 'clear_prompt' });
        checkoutKey.current = null;
      }
      // The envelope's speech is always safe to speak (0.6). Without one the
      // backend was unreachable, so the app supplies the line.
      const declined = e instanceof ApiError && e.code === E_CARD_DECLINED;
      haptic.error();
      const v = localVoice(e instanceof ApiError && e.speech ? e.speech : Phrases.offline, declined ? 'alert' : 'normal');
      // Mark declines so say() doesn't add the orange buzz on top of the red one.
      say(declined ? { ...v, request_id: `declined-${v.request_id}` } : v);
    },
    [say],
  );

  // --- data refresh ---------------------------------------------------------

  const refreshCart = useCallback(async () => {
    try {
      dispatch({ type: 'cart', cart: await api.getCart() });
    } catch {
      // the cart screen shows the last known cart
    }
  }, []);

  const refreshCards = useCallback(async () => {
    try {
      dispatch({ type: 'cards', cards: await api.getCards() });
    } catch {
      // keep last known
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const health = await api.getHealth();
      console.log(`[backend] reachable: ${health.status}`);
      dispatch({ type: 'health', health });
    } catch (e) {
      console.warn('[backend] health check failed:', e instanceof api.ApiError ? e.message : e);
      dispatch({ type: 'health', health: null });
    }
  }, []);

  useEffect(() => {
    void refreshCart();
    void refreshCards();
    void refreshHealth();
    const t = setInterval(refreshHealth, 60_000);
    return () => clearInterval(t);
  }, [refreshCart, refreshCards, refreshHealth]);

  // Backgrounding (1.2): welcome back with the cart count, offer to repeat.
  useEffect(() => {
    let wasBackground = false;
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'background') {
        wasBackground = true;
        speaker.interrupt();
      } else if (next === 'active') {
        const held = heldVoice.current;
        heldVoice.current = null;
        // After a demo restart the shopper is new: no "welcome back".
        if (wasBackground && !fresh.current) {
          const n = stateRef.current.cart.groups.reduce((k, g) => k + g.items.length, 0);
          say(localVoice(Phrases.welcomeBack(n)), false);
        }
        wasBackground = false;
        // The scan finished while away (a call, the home screen): say its answer now, after the welcome.
        if (held) say(held);
      }
    });
    return () => sub.remove();
  }, [say]);

  // --- commands -------------------------------------------------------------

  // While checked in, watch for leaving the store (foreground only, position never kept).
  const watcher = useRef<{ remove: () => void } | null>(null);
  const stopWatch = useCallback(() => {
    watcher.current?.remove();
    watcher.current = null;
  }, []);
  const leaveStore = useCallback(() => {
    stopWatch();
    dispatch({ type: 'checkin', checkin: null });
    dispatch({ type: 'caption_clear' });
  }, [stopWatch]);
  const startWatch = useCallback(
    async (storeId: string) => {
      stopWatch();
      try {
        watcher.current = await Location.watchPositionAsync(
          { accuracy: Location.Accuracy.Balanced, distanceInterval: 30 },
          (pos) => {
            void api
              .stillAtStore(storeId, { lat: pos.coords.latitude, lng: pos.coords.longitude })
              .then((still) => !still && leaveStore())
              .catch(() => {});
          },
        );
      } catch {
        /* no location updates: the card stays until the user closes it */
      }
    },
    [stopWatch, leaveStore],
  );
  useEffect(() => stopWatch, [stopWatch]);

  const applyCommand = useCallback(
    (res: CommandResponse) => {
      switch (res.action) {
        case 'repeat': {
          const last = stateRef.current.lastVoice;
          say(last ?? localVoice(Phrases.nothingToRepeat), false);
          return;
        }
        case 'add_item':
        case 'remove_last':
        case 'cart_cleared':
          if (res.result) dispatch({ type: 'cart', cart: res.result as Cart });
          if (res.action === 'add_item') dispatch({ type: 'clear_scan' });
          break;
        case 'review_item':
          if (res.result) dispatch({ type: 'cart', cart: res.result as Cart });
          dispatch({ type: 'review', id: res.item_id ?? null });
          break;
        case 'review_done':
          // The review is over (or the cart emptied): close the cart and leave the camera clear.
          if (res.result) dispatch({ type: 'cart', cart: res.result as Cart });
          dispatch({ type: 'review', id: null });
          dispatch({ type: 'view', view: 'camera' });
          break;
        case 'read_cart':
          if (res.result) dispatch({ type: 'cart', cart: res.result as Cart });
          dispatch({ type: 'view', view: 'cart' });
          break;
        case 'checkout_preview':
          checkoutKey.current = randomUUID();
          dispatch({ type: 'declined', message: null });
          dispatch({ type: 'preview', preview: res.result as CheckoutPreview });
          dispatch({ type: 'receipt', receipt: null });
          dispatch({ type: 'view', view: 'checkout' });
          break;
        case 'checkout_confirmed':
          dispatch({ type: 'receipt', receipt: res.result as CheckoutResult });
          dispatch({ type: 'preview', preview: null });
          dispatch({ type: 'cart', cart: { groups: [], total_cents: 0 } });
          void refreshCards();
          break;
        case 'skip':
          if (stateRef.current.checkin?.status === 'asking') dispatch({ type: 'checkin', checkin: null });
        // falls through
        case 'strength_confirmed':
          // Prescription confirmed: the copay line is spoken; the card closes.
          dispatch({ type: 'clear_scan' });
          dispatch({ type: 'clear_prompt' });
          break;
        case 'checked_in':
          {
            const store = res.result as Store;
            dispatch({ type: 'checkin', checkin: { store, status: 'in', toast: true } });
            haptic.done(); // the check-in buzz
            void startWatch(store.id);
            // The confirmation card closes by itself after a few seconds; the check-in stays.
            setTimeout(() => dispatch({ type: 'checkin', checkin: { store, status: 'in', toast: false } }), 7000);
          }
          break;
        case 'open_history':
          dispatch({ type: 'view', view: 'history' });
          break;
        case 'close_history':
          dispatch({ type: 'view', view: 'camera' });
          break;
        case 'open_settings':
          dispatch({ type: 'view', view: 'profile' });
          break;
      }
      say(res.voice);
    },
    [say, refreshCards, startWatch],
  );

  /**
   * The live question for the shown scan. If its window has passed, ask the
   * backend for a fresh one for the same item (WCAG 2.2.1: a late answer is
   * never a dead end, and nothing needs rescanning).
   */
  const ensurePrompt = useCallback(async (): Promise<string | null> => {
    const s = stateRef.current;
    const scan = s.lastScan;
    const scope = scan?.voice.response_scope;
    if (!scan || !scope || scope === 'none') return s.livePrompt?.id ?? null;
    if (s.livePrompt?.scope === scope && s.livePrompt.expiresAt > Date.now()) return s.livePrompt.id;
    try {
      const r = await api.reissuePrompt(scan.scan.scan_id, scope);
      const prompt = { id: r.prompt_id, scope, expiresAt: Date.now() + r.expires_in_s * 1000 };
      dispatch({ type: 'set_prompt', prompt });
      stateRef.current = { ...stateRef.current, livePrompt: prompt };
      return prompt.id;
    } catch {
      return s.livePrompt?.id ?? null;
    }
  }, []);

  const sendTranscript = useCallback(
    async (transcript: string, confidence: number) => {
      if (moreOffer.current) {
        // "Is there anything else you'd like me to scan?"
        moreOffer.current = false;
        if (/^\W*(yes|yeah|yep|yup|sure|ok|okay)\b/i.test(transcript)) {
          say(localVoice(Phrases.nextItem), false);
          return;
        }
        if (/^\W*(no|nope|nah|that'?s (it|all)|i'?m (done|good))\b/i.test(transcript)) {
          say(localVoice(Phrases.whenReady), false);
          return;
        }
      }
      if (repeatOffer.current) {
        // "Would you like me to repeat?" is answered here; anything else is a normal command.
        repeatOffer.current = false;
        if (/^\W*(yes|yeah|yep|yup|sure|please|ok|okay|repeat)\b/i.test(transcript)) {
          haptic.done();
          say(stateRef.current.lastVoice ?? localVoice(Phrases.nothingToRepeat), false);
          return;
        }
        if (/^\W*(no|nope|nah|not now)\b/i.test(transcript)) {
          say(localVoice(Phrases.okay), false);
          return;
        }
      }
      dispatch({ type: 'submit' });
      showStatus(Working.forRequest(transcript));
      try {
        const promptId = stateRef.current.lastScan ? await ensurePrompt() : stateRef.current.livePrompt?.id;
        const res = await api.command(transcript, confidence, promptId);
        applyCommand(res);
      } catch (e) {
        handleError(e);
      }
    },
    [applyCommand, handleError, ensurePrompt, say, showStatus],
  );

  // --- listening ------------------------------------------------------------

  const startListening = async (autoStop: boolean) => {
    clearSilence();
    const perm = await mic.start().catch(() => 'denied' as const);
    if (perm === 'denied') {
      dispatch({ type: 'mic_denied' });
      say(localVoice(Phrases.micDenied), false);
      return;
    }
    dispatch({ type: 'listen' });
    if (autoListening.current) haptic.tap(); // the mic opened by itself: a tap-like buzz says "go ahead"
    if (autoStop) {
      if (listenTimer.current) clearTimeout(listenTimer.current);
      listenTimer.current = setTimeout(() => void stopListening(), LISTEN_WINDOW_MS);
    }
  };

  const stopListening = async () => {
    if (listenTimer.current) clearTimeout(listenTimer.current);
    listenTimer.current = null;
    if (stateRef.current.phase !== 'listening') return;
    const auto = autoListening.current;
    autoListening.current = false;
    // The mic opened by itself and heard nothing: stay quiet, wait for the question's silence prompt.
    const heardNothing = () => {
      autoMisses.current += 1;
      dispatch({ type: 'listen_done' });
      if (stateRef.current.livePrompt) armSilence();
    };
    const rec = await mic.stop();
    if (!rec) {
      if (auto) heardNothing();
      else dispatch({ type: 'idle' });
      return;
    }
    dispatch({ type: 'submit' });
    try {
      const handler = listenHandler.current;
      const { transcript, confidence } = await api.stt(rec.uri, handler?.hint);
      if (auto && !transcript.trim()) {
        heardNothing();
        return;
      }
      autoMisses.current = 0;
      dispatch({ type: 'user_said', text: transcript });
      if (handler) {
        dispatch({ type: 'idle' });
        handler.fn(transcript);
      } else {
        await sendTranscript(transcript, confidence);
      }
    } catch (e) {
      if (auto && e instanceof ApiError && e.code === 'E_STT_LOW_CONFIDENCE') heardNothing();
      else handleError(e);
    } finally {
      rec.discard();
    }
  };

  const onSpeechDone = (voice: VoiceRequest) => {
    if (voiceMonitor.on && speaker.quiet) {
      // Stop the quiet listening, then carry on (the next step may open the mic again).
      void stopMonitor().then(() => onSpeechDone(voice));
      return;
    }
    dispatch({ type: 'speak_done', voice });
    if (!isLocalVoice(voice)) haptic.done();
    if (pendingAlert.current && pendingAlert.current.request_id !== voice.request_id) {
      // Never drop an alert: replay it in full after the interruption (1.2).
      const alert = pendingAlert.current;
      pendingAlert.current = null;
      say(alert);
      return;
    }
    if (listenAfterSpeech.current) {
      listenAfterSpeech.current = false;
      void startListening(true);
      return;
    }
    // A question was asked: open the mic by itself so the shopper can just answer (no tap needed).
    const handler = listenHandler.current;
    const asks = voice.expects_response || answerNext.current || (handler !== null && handler.auto);
    answerNext.current = false;
    if (asks && !screenReaderOn && autoMisses.current < 2 && speaker.quiet) {
      void (async () => {
        const perm = await getRecordingPermissionsAsync().catch(() => null);
        // Never pop the permission prompt from here, and never listen over the next line.
        if (!perm?.granted || !speaker.quiet || stateRef.current.phase === 'listening') {
          if (voice.expects_response) armSilence();
          return;
        }
        autoListening.current = true;
        await startListening(true);
      })();
      return;
    }
    if (voice.expects_response) armSilence();
  };

  // Silence: prompt once after a pause; after two unanswered prompts, go idle. Never loop.
  const armSilence = () => {
    clearSilence();
    silenceTimer.current = setTimeout(() => {
      const s = stateRef.current;
      if (s.phase !== 'awaiting_confirm' || !s.lastVoice) return;
      silencePrompts.current += 1;
      if (silencePrompts.current >= 2) {
        dispatch({ type: 'idle' });
        return;
      }
      say(s.lastVoice);
    }, SILENCE_MS);
  };

  // The speaker listener is registered once; route it through a ref so it
  // always sees the latest render's callbacks.
  useEffect(() => {
    onDoneRef.current = onSpeechDone;
  });

  useEffect(() => {
    speaker.setListener({ onStart: () => voiceMonitor.onStart(), onDone: (v) => onDoneRef.current(v) });
    void configureAudio();
  }, []);

  // --- interrupt by speaking (headphones) -------------------------------------------------
  // While Rewind talks, the mic listens quietly. A voice held for VOICE_HOLD_MS cuts Rewind off and that
  // same recording becomes the answer. Off by default and only with headphones (no echo cancellation).
  const onSpeechStart = () => {
    if (!settings.interruptBySpeaking || screenReaderOn || voiceMonitor.on) return;
    if (stateRef.current.phase === 'listening') return;
    void (async () => {
      const perm = await getRecordingPermissionsAsync().catch(() => null);
      if (!perm?.granted || !speaker.speaking || voiceMonitor.on) return;
      voiceMonitor.on = true;
      voiceMonitor.loudSince = null;
      await mic.start().catch(() => {
        voiceMonitor.on = false;
      });
    })();
  };
  useEffect(() => {
    voiceMonitor.onStart = onSpeechStart;
  });
  const voiceCutIn = () => {
    voiceMonitor.on = false;
    voiceMonitor.loudSince = null;
    const cut = speaker.interrupt();
    if (cut?.priority === 'alert') pendingAlert.current = cut;
    mic.keepRecent(VOICE_KEEP_MS); // keep the words that cut in
    haptic.tap();
    dispatch({ type: 'listen' });
    if (listenTimer.current) clearTimeout(listenTimer.current);
    listenTimer.current = setTimeout(() => void stopListening(), LISTEN_WINDOW_MS);
  };
  useEffect(
    () =>
      onMicLevel((level) => {
        if (!voiceMonitor.on) return;
        if (level < VOICE_LEVEL) {
          voiceMonitor.loudSince = null;
          return;
        }
        voiceMonitor.loudSince ??= Date.now();
        if (Date.now() - voiceMonitor.loudSince >= VOICE_HOLD_MS) voiceCutIn();
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  /** Rewind finished without being cut off: stop the quiet listening (the answer mic opens as usual). */
  const stopMonitor = async () => {
    if (!voiceMonitor.on) return;
    voiceMonitor.on = false;
    const rec = await mic.stop();
    rec?.discard();
  };

  const bargeIn = () => {
    const cut = speaker.interrupt();
    if (cut?.priority === 'alert') pendingAlert.current = cut;
    dispatch({ type: 'interrupted' });
  };

  const talkTap = useCallback(() => {
    haptic.tap();
    const s = stateRef.current;
    if (s.phase === 'listening') {
      void stopListening();
      return;
    }
    if (speaker.speaking) {
      if (voiceMonitor.on) {
        voiceCutIn(); // the mic is already open: use it
        return;
      }
      bargeIn();
      void startListening(true);
      return;
    }
    if (s.livePrompt || listenHandler.current) {
      void startListening(true);
      return;
    }
    if (s.view === 'history') {
      // Say where the user is, then open the mic.
      void api
        .getPaymentHistory()
        .catch(() => [])
        .then((list) => {
          const cents = list.reduce((sum, i) => sum + i.reimbursable_cents, 0);
          listenAfterSpeech.current = true;
          say(localVoice(Phrases.onHistory(list.length, cents ? formatCents(cents) : null)), false);
        });
      return;
    }
    // Greeting first, then the mic opens when it finishes.
    listenAfterSpeech.current = true;
    say(localVoice(Phrases.greeting), false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [say]);

  const talkHoldStart = useCallback(() => {
    holding.current = true;
    haptic.tap();
    if (speaker.speaking) bargeIn();
    void startListening(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const talkHoldEnd = useCallback(() => {
    if (!holding.current) return;
    holding.current = false;
    void stopListening();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setListenHandler = useCallback(
    (hint: SttHint | undefined, fn: ((transcript: string) => void) | null, auto = true) => {
      listenHandler.current = fn ? { hint, fn, auto } : null;
      autoMisses.current = 0; // a new step or question gets fresh tries
    },
    [],
  );

  const repeat = useCallback(() => {
    haptic.done();
    const last = stateRef.current.lastVoice;
    if (speaker.speaking) speaker.interrupt();
    say(last ?? localVoice(Phrases.nothingToRepeat), false);
  }, [say]);

  // --- scanning -------------------------------------------------------------

  const beginCapture = useCallback(() => {
    if (speaker.speaking) bargeIn();
    haptic.capture();
    dispatch({ type: 'capture' });
  }, []);

  const scanFrame = useCallback(
    async (imageUri: string, barcode: string | null, discard: () => void, photo: { width: number; height: number }) => {
      dispatch({ type: 'scan_sent' });
      // Say what is happening: the first line is spoken, the next two only change the caption.
      const progress = [
        setTimeout(() => say(localVoice(Working.scan[0]), false, true), LOOKING_MS),
        setTimeout(() => showStatus(Working.scan[1]), LOOKING_MS * 4),
        setTimeout(() => showStatus(Working.scan[2]), LOOKING_MS * 9),
      ];
      const looking = { clear: () => progress.forEach(clearTimeout) };
      try {
        const res = await api.scan(imageUri, barcode, null, insurerRef.current);
        looking.clear();
        speaker.interrupt(); // cut "Looking." short if it is still playing
        dispatch({ type: 'scan_received', res, photo });
        // A call or the home screen came up mid-scan: keep the answer for when the shopper is back.
        if (AppState.currentState !== 'active') heldVoice.current = res.voice;
        else say(res.voice);
      } catch (e) {
        looking.clear();
        handleError(e);
      } finally {
        discard(); // frames are never retained (decision 14)
      }
    },
    [say, handleError, showStatus],
  );

  const addToCart = useCallback(
    async (cardId: string) => {
      const scan = stateRef.current.lastScan;
      if (!scan) return;
      dispatch({ type: 'submit' });
      try {
        const promptId = await ensurePrompt();
        if (!promptId) return;
        const res = await api.addCartItem(scan.scan.scan_id, cardId, promptId);
        dispatch({ type: 'cart', cart: res.cart });
        dispatch({ type: 'clear_scan' });
        dispatch({ type: 'clear_prompt' });
        say(res.voice);
      } catch (e) {
        handleError(e);
      }
    },
    [say, handleError, ensurePrompt],
  );

  // Tap equivalents of spoken commands go through /v1/command so the backend
  // still owns the wording.
  const skip = useCallback(() => sendTranscript('skip it', 1), [sendTranscript]);
  const askClearCart = useCallback(() => sendTranscript('clear cart', 1), [sendTranscript]);

  const removeLast = useCallback(async () => {
    try {
      const res = await api.removeLastCartItem();
      dispatch({ type: 'cart', cart: res.cart });
      say(res.voice);
    } catch (e) {
      handleError(e);
    }
  }, [say, handleError]);

  const startCheckin = useCallback(
    async (simulateStoreId?: string) => {
      try {
        let coords: { lat: number; lng: number } | null = null;
        if (!simulateStoreId) {
          const perm = await Location.requestForegroundPermissionsAsync();
          if (perm.status !== 'granted') return; // never nag; the app works without it
          const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
          coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        }
        const found = await api.nearbyStore(coords, simulateStoreId);
        coords = null; // not kept
        if (!found) return;
        dispatch({ type: 'view', view: 'camera' });
        dispatch({ type: 'checkin', checkin: { store: found.store, status: 'asking', toast: false } });
        say(found.voice);
      } catch {
        /* no location, no check-in */
      }
    },
    [say],
  );


  const reviewItem = useCallback(
    async (itemId: string) => {
      dispatch({ type: 'submit' });
      try {
        const res = await api.reviewCartItem(itemId);
        dispatch({ type: 'cart', cart: res.cart });
        dispatch({ type: 'review', id: res.item_id ?? null });
        say(res.voice);
      } catch (e) {
        handleError(e);
      }
    },
    [say, handleError],
  );

  const confirmClearCart = useCallback(async () => {
    const p = stateRef.current.livePrompt;
    if (p?.scope !== 'confirm_clear_cart') return;
    try {
      const res = await api.clearCart(p.id);
      dispatch({ type: 'cart', cart: res.cart });
      dispatch({ type: 'clear_prompt' });
      say(res.voice);
    } catch (e) {
      handleError(e);
    }
  }, [say, handleError]);

  const startCheckout = useCallback(async () => {
    dispatch({ type: 'submit' });
    dispatch({ type: 'receipt', receipt: null });
    dispatch({ type: 'declined', message: null });
    dispatch({ type: 'view', view: 'checkout' });
    try {
      const preview = await api.checkoutPreview();
      checkoutKey.current = randomUUID();
      dispatch({ type: 'preview', preview });
      say(preview.voice);
    } catch (e) {
      handleError(e);
    }
  }, [say, handleError]);

  const confirmCheckout = useCallback(async (useProposedSplit = true) => {
    const s = stateRef.current;
    const promptId = s.preview?.voice.prompt_id;
    if (!promptId || s.livePrompt?.id !== promptId) return;
    if (!checkoutKey.current) checkoutKey.current = randomUUID();
    dispatch({ type: 'submit' });
    try {
      const receipt = await api.checkoutConfirm(checkoutKey.current, promptId, useProposedSplit);
      dispatch({ type: 'receipt', receipt });
      dispatch({ type: 'preview', preview: null });
      dispatch({ type: 'clear_prompt' });
      dispatch({ type: 'cart', cart: { groups: [], total_cents: 0 } });
      checkoutKey.current = null;
      void refreshCards();
      say(receipt.voice);
    } catch (e) {
      handleError(e);
    }
  }, [say, handleError, refreshCards]);

  const resetDemo = useCallback(
    async (run: 1 | 2) => {
      try {
        const res = await api.resetDemo(run);
        fresh.current = true;
        dispatch({ type: 'cards', cards: res.cards });
        dispatch({ type: 'cart', cart: res.cart });
        dispatch({ type: 'preview', preview: null });
        dispatch({ type: 'receipt', receipt: null });
        dispatch({ type: 'declined', message: null });
        dispatch({ type: 'clear_scan' });
        dispatch({ type: 'clear_prompt' });
        dispatch({ type: 'view', view: 'camera' });
      } catch (e) {
        handleError(e);
      }
    },
    [handleError],
  );

  const profileApi = useProfile();
  const restart = useCallback(
    async (run: 1 | 2 = 1) => {
      speaker.interrupt();
      void stopMonitor();
      clearSilence();
      if (promptTimer.current) clearTimeout(promptTimer.current);
      if (listenTimer.current) clearTimeout(listenTimer.current);
      repeatOffer.current = false;
      moreOffer.current = false;
      answerNext.current = false;
      autoMisses.current = 0;
      heldVoice.current = null;
      fresh.current = true; // a new shopper is never "back"
      let reset: { cards: Card[]; cart: Cart } = { cards: stateRef.current.cards, cart: { groups: [], total_cents: 0 } };
      try {
        reset = await api.resetDemo(run);
      } catch (e) {
        handleError(e); // the screen still resets; the server data stays as it was
      }
      dispatch({ type: 'reset_all', cards: reset.cards, cart: reset.cart });
      profileApi.reset();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [handleError, profileApi.reset],
  );

  const showView = useCallback((view: PanelView) => {
    if (view === 'cart') void refreshCart();
    dispatch({ type: 'view', view });
  }, [refreshCart]);

  const answer = useCallback((text: string) => sendTranscript(text, 1), [sendTranscript]);

  const dismiss = useCallback(() => {
    // The payment alert's caption goes away with the invoice that carried it.
    if (stateRef.current.receipt) dispatch({ type: 'caption_clear' });
    dispatch({ type: 'receipt', receipt: null });
    dispatch({ type: 'declined', message: null });
    dispatch({ type: 'preview', preview: null });
    dispatch({ type: 'clear_scan' });
    dispatch({ type: 'view', view: 'camera' });
  }, []);

  const value = useMemo<AgentApi>(
    () => ({
      showView,
      answer,
      dismiss,
      state,
      talkTap,
      talkHoldStart,
      talkHoldEnd,
      repeat,
      setListenHandler,
      beginCapture,
      scanFrame,
      addToCart,
      skip,
      refreshCart,
      refreshCards,
      startCheckin,
      demoDecline: api.demoForceDecline,
      leaveStore,
      reviewItem,
      removeLast,
      askClearCart,
      confirmClearCart,
      startCheckout,
      confirmCheckout,
      resetDemo,
      restart,
      sayLocal,
      offerRepeat,
      askAnythingElse,
      markFresh,
    }),
    [
      state, talkTap, talkHoldStart, talkHoldEnd, repeat, setListenHandler, beginCapture, scanFrame, addToCart, skip,
      refreshCart, refreshCards, startCheckin, leaveStore, reviewItem, removeLast, askClearCart, confirmClearCart, startCheckout,
      confirmCheckout, resetDemo, restart, sayLocal, offerRepeat, askAnythingElse, markFresh, showView, answer, dismiss,
    ],
  );

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}

export function useAgent(): AgentApi {
  const ctx = useContext(AgentContext);
  if (!ctx) throw new Error('useAgent must be used inside <AgentProvider>');
  return ctx;
}
