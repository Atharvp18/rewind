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

import { randomUUID } from 'expo-crypto';
import { router } from 'expo-router';
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
  type SttHint,
  type VoiceRequest,
} from '@/lib/api';
import { announce, SPEECH_RATE, useA11y } from '@/lib/a11y';
import { configureAudio, speaker, useMic } from '@/lib/audio';
import { haptic } from '@/lib/haptics';
import { Phrases } from '@/lib/phrases';

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
export type PanelView = 'camera' | 'cart' | 'checkout';

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
  lastScan: ScanResponse | null;
  cart: Cart;
  cards: Card[];
  /** undefined until the first check; null when the backend is unreachable. */
  health: Health | null | undefined;
  preview: CheckoutPreview | null;
  receipt: CheckoutResult | null;
  micDenied: boolean;
}

type Action =
  | { type: 'listen' }
  | { type: 'capture' }
  | { type: 'scan_sent' }
  | { type: 'scan_received'; res: ScanResponse }
  | { type: 'error' }
  | { type: 'submit' }
  | { type: 'interrupted' }
  | { type: 'idle' }
  | { type: 'speak_start'; voice: VoiceRequest; remember: boolean; interim: boolean }
  | { type: 'speak_done'; voice: VoiceRequest }
  | { type: 'prompt_expired'; id: string }
  | { type: 'clear_prompt' }
  | { type: 'cart'; cart: Cart }
  | { type: 'cards'; cards: Card[] }
  | { type: 'health'; health: Health | null }
  | { type: 'preview'; preview: CheckoutPreview | null }
  | { type: 'receipt'; receipt: CheckoutResult | null }
  | { type: 'clear_scan' }
  | { type: 'mic_denied' }
  | { type: 'user_said'; text: string }
  | { type: 'declined'; message: string | null }
  | { type: 'view'; view: PanelView };

const PROMPT_TTL_MS = 15_000;
const SILENCE_MS = 8_000;
const LOOKING_MS = 1_000;
const LISTEN_WINDOW_MS = 6_000;

/** Phases an interim line may finish in without ending them. */
const BUSY: Phase[] = ['listening', 'capturing', 'awaiting_scan', 'submitting'];

const TRANSCRIPT_MAX = 30;

const pushLine = (t: TranscriptLine[], line: TranscriptLine) =>
  t[t.length - 1]?.id === line.id ? t : [...t, line].slice(-TRANSCRIPT_MAX);

const initial: AgentState = {
  phase: 'idle',
  view: 'camera',
  transcript: [],
  declined: null,
  caption: null,
  captionIsAlert: false,
  lastVoice: null,
  livePrompt: null,
  lastScan: null,
  cart: { groups: [], total_cents: 0 },
  cards: [],
  health: undefined,
  preview: null,
  receipt: null,
  micDenied: false,
};

function reducer(s: AgentState, a: Action): AgentState {
  switch (a.type) {
    case 'listen':
      return { ...s, phase: 'listening' };
    case 'capture':
      return { ...s, phase: 'capturing' };
    case 'scan_sent':
      return { ...s, phase: 'awaiting_scan' };
    case 'scan_received':
      return { ...s, phase: 'speaking_result', lastScan: a.res, view: 'camera' };
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
        ? { id: a.voice.prompt_id!, scope: a.voice.response_scope, expiresAt: Date.now() + PROMPT_TTL_MS }
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
  setListenHandler: (hint: SttHint | undefined, fn: ((transcript: string) => void) | null) => void;
  beginCapture: () => void;
  scanFrame: (imageUri: string, barcode: string | null, discard: () => void) => Promise<void>;
  addToCart: (cardId: string) => Promise<void>;
  skip: () => Promise<void>;
  refreshCart: () => Promise<void>;
  refreshCards: () => Promise<void>;
  removeLast: () => Promise<void>;
  askClearCart: () => Promise<void>;
  confirmClearCart: () => Promise<void>;
  startCheckout: () => Promise<void>;
  /** `useProposedSplit: false` charges the original cards, which can be declined. */
  confirmCheckout: (useProposedSplit?: boolean) => Promise<void>;
  resetDemo: (run: 1 | 2) => Promise<void>;
  showView: (view: PanelView) => void;
  /** Tap equivalent of saying something (e.g. "yes" to a strength read-back); goes through /v1/command. */
  answer: (text: string) => Promise<void>;
  /** Close the current panel and return to the plain camera. */
  dismiss: () => void;
  sayLocal: (text: string, priority?: 'alert' | 'normal') => void;
}

const AgentContext = createContext<AgentApi | null>(null);

export const isLocalVoice = (v: VoiceRequest) => v.request_id.startsWith('local-');

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
  const listenHandler = useRef<{ hint?: SttHint; fn: (t: string) => void } | null>(null);

  // --- speech -------------------------------------------------------------

  useEffect(() => {
    speaker.opts = { rate: SPEECH_RATE[settings.speechRate], volume: settings.volume };
  }, [settings.speechRate, settings.volume]);

  const clearSilence = () => {
    if (silenceTimer.current) clearTimeout(silenceTimer.current);
    silenceTimer.current = null;
  };

  const say = useCallback(
    (voice: VoiceRequest, remember = true, interim = false) => {
      clearSilence();
      dispatch({ type: 'speak_start', voice, remember, interim });
      // Only a new prompt resets the silence count and expiry timer. Re-asking
      // the same question must not, or the silence prompt would loop (1.2).
      if (voice.expects_response && voice.prompt_id && voice.prompt_id !== stateRef.current.livePrompt?.id) {
        silencePrompts.current = 0;
        if (promptTimer.current) clearTimeout(promptTimer.current);
        const id = voice.prompt_id;
        promptTimer.current = setTimeout(() => dispatch({ type: 'prompt_expired', id }), PROMPT_TTL_MS);
      }
      if (voice.priority === 'alert') haptic.error();
      if (screenReaderOn) {
        // Decision 13: mute our own voice, send the text through the screen reader.
        announce(voice.text);
        setTimeout(() => onDoneRef.current(voice), 0);
      } else {
        speaker.speak(voice);
      }
    },
    [screenReaderOn],
  );

  const sayLocal = useCallback(
    (text: string, priority: 'alert' | 'normal' = 'normal') => say(localVoice(text, priority)),
    [say],
  );

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
      // Alerts buzz inside say(); other errors buzz here. One buzz either way.
      if (!declined) haptic.error();
      say(localVoice(e instanceof ApiError && e.speech ? e.speech : Phrases.offline, declined ? 'alert' : 'normal'));
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
      dispatch({ type: 'health', health: await api.getHealth() });
    } catch {
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
      } else if (next === 'active' && wasBackground) {
        wasBackground = false;
        const n = stateRef.current.cart.groups.reduce((k, g) => k + g.items.length, 0);
        say(localVoice(Phrases.welcomeBack(n)), false);
      }
    });
    return () => sub.remove();
  }, [say]);

  // --- commands -------------------------------------------------------------

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
          dispatch({ type: 'clear_scan' });
          dispatch({ type: 'clear_prompt' });
          break;
        case 'open_settings':
          router.push('/profile');
          break;
      }
      say(res.voice);
    },
    [say, refreshCards],
  );

  const sendTranscript = useCallback(
    async (transcript: string, confidence: number) => {
      dispatch({ type: 'submit' });
      try {
        const res = await api.command(transcript, confidence, stateRef.current.livePrompt?.id);
        applyCommand(res);
      } catch (e) {
        handleError(e);
      }
    },
    [applyCommand, handleError],
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
    if (autoStop) {
      if (listenTimer.current) clearTimeout(listenTimer.current);
      listenTimer.current = setTimeout(() => void stopListening(), LISTEN_WINDOW_MS);
    }
  };

  const stopListening = async () => {
    if (listenTimer.current) clearTimeout(listenTimer.current);
    listenTimer.current = null;
    if (stateRef.current.phase !== 'listening') return;
    const rec = await mic.stop();
    if (!rec) {
      dispatch({ type: 'idle' });
      return;
    }
    dispatch({ type: 'submit' });
    try {
      const handler = listenHandler.current;
      const { transcript, confidence } = await api.stt(rec.uri, handler?.hint);
      dispatch({ type: 'user_said', text: transcript });
      if (handler) {
        dispatch({ type: 'idle' });
        handler.fn(transcript);
      } else {
        await sendTranscript(transcript, confidence);
      }
    } catch (e) {
      handleError(e);
    } finally {
      rec.discard();
    }
  };

  const onSpeechDone = (voice: VoiceRequest) => {
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
    speaker.setListener({ onDone: (v) => onDoneRef.current(v) });
    void configureAudio();
  }, []);

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
      bargeIn();
      void startListening(true);
      return;
    }
    if (s.livePrompt || listenHandler.current) {
      void startListening(true);
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
    (hint: SttHint | undefined, fn: ((transcript: string) => void) | null) => {
      listenHandler.current = fn ? { hint, fn } : null;
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
    async (imageUri: string, barcode: string | null, discard: () => void) => {
      dispatch({ type: 'scan_sent' });
      const looking = setTimeout(() => say(localVoice(Phrases.looking), false, true), LOOKING_MS);
      try {
        const res = await api.scan(imageUri, barcode);
        clearTimeout(looking);
        speaker.interrupt(); // cut "Looking." short if it is still playing
        dispatch({ type: 'scan_received', res });
        say(res.voice);
      } catch (e) {
        clearTimeout(looking);
        handleError(e);
      } finally {
        discard(); // frames are never retained (decision 14)
      }
    },
    [say, handleError],
  );

  const addToCart = useCallback(
    async (cardId: string) => {
      const s = stateRef.current;
      if (!s.lastScan || !s.livePrompt) return;
      dispatch({ type: 'submit' });
      try {
        const res = await api.addCartItem(s.lastScan.scan.scan_id, cardId, s.livePrompt.id);
        dispatch({ type: 'cart', cart: res.cart });
        dispatch({ type: 'clear_scan' });
        dispatch({ type: 'clear_prompt' });
        say(res.voice);
      } catch (e) {
        handleError(e);
      }
    },
    [say, handleError],
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

  const showView = useCallback((view: PanelView) => {
    if (view === 'cart') void refreshCart();
    dispatch({ type: 'view', view });
  }, [refreshCart]);

  const answer = useCallback((text: string) => sendTranscript(text, 1), [sendTranscript]);

  const dismiss = useCallback(() => {
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
      removeLast,
      askClearCart,
      confirmClearCart,
      startCheckout,
      confirmCheckout,
      resetDemo,
      sayLocal,
    }),
    [
      state, talkTap, talkHoldStart, talkHoldEnd, repeat, setListenHandler, beginCapture, scanFrame, addToCart, skip,
      refreshCart, refreshCards, removeLast, askClearCart, confirmClearCart, startCheckout,
      confirmCheckout, resetDemo, sayLocal, showView, answer, dismiss,
    ],
  );

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}

export function useAgent(): AgentApi {
  const ctx = useContext(AgentContext);
  if (!ctx) throw new Error('useAgent must be used inside <AgentProvider>');
  return ctx;
}
