/**
 * The only spoken lines the app writes itself. Everything else comes from the
 * backend (speech/compose.py, or error.speech in the envelope). Each line here
 * is either assigned to the app by the tech spec or covers a case where the
 * backend cannot be reached and so cannot supply wording.
 */

export const Phrases = {
  /** Spoken if /v1/scan has not answered after 1000 ms (0.7). */
  looking: 'Looking.',
  /** Talk button tap (business spec 6.5 A). */
  greeting: 'How may I help you today?',
  /** Return from background (1.2). */
  welcomeBack: (n: number) =>
    `Welcome back, you have ${n} ${n === 1 ? 'item' : 'items'} in your cart. Say repeat that to hear the last message.`,
  /** No envelope to speak because the backend is unreachable. */
  offline: "I can't reach Rewind right now. Please check the connection and try again.",
  cameraDenied:
    'Camera access is off. To scan, open your phone settings and allow camera for Expo Go. You can also tap Talk and say the product name.',
  micDenied:
    'Microphone access is off. You can still use every button on screen. To talk, allow the microphone in your phone settings.',
  nothingToRepeat: "I haven't said anything yet. Tap Talk to start.",
} as const;
