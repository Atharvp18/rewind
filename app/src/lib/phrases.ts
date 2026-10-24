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
  declinedTitle: 'Payment declined',
  /** The camera could not take a photo (busy, or no camera, as in the simulator). */
  captureFailed: "I couldn't take a photo. Hold the phone steady and tap the screen to try again.",
} as const;

/**
 * Onboarding lines. Onboarding has no endpoint or wording in the tech spec
 * (0.6, 3.11), so the app speaks these itself until the backend owns them.
 */
export const Onboarding = {
  cameraWhy:
    'Rewind uses your camera to read product labels, prices, and your cards. Photos are not saved. Tap Allow camera, then choose Allow.',
  micWhy:
    'Rewind uses your microphone so you can talk to it. It only listens while you tap or hold the round button. Tap Allow microphone, then choose Allow.',
  confirmCardName: (full: string) => `Your name is ${full}. Is that right?`,
  typeName: "I couldn't confirm your name from the card. Please type it, or scan the card again.",
  greet: (first: string) => `Thank you, ${first}.`,
  phoneDemo: (phone: string) =>
    `Hi, I'm Rewind. I tell you what a product is, what it costs, and which card to pay with. This is a prototype, so I'm verifying this phone with the demo number ${phone}. Your phone is verified.`,
  askInsurance:
    'Now your insurance card. Hold it flat, about a hand length from the phone, then tap anywhere on the screen.',
  confirmInsurance: (insurer: string, plan: string | null, hasRx: boolean) =>
    `Your insurance is ${insurer}${plan ? `, ${plan}` : ''}.${hasRx ? ' It shows prescription benefits.' : ''} Is that right?`,
  askPayment: (first: boolean) =>
    first
      ? 'Now your HSA or FSA Visa card. Hold it flat, about a hand length from the phone, then tap anywhere on the screen.'
      : 'Now your everyday Visa card, credit or debit. Hold it flat, about a hand length from the phone, then tap anywhere on the screen.',
  askCardType: 'Is this Visa card an HSA card, an FSA card, a credit card, or a debit card?',
  confirmCard: (label: string, last4: string | null) =>
    `I see ${label}${last4 ? ` ending in ${last4.split('').join(' ')}` : ''}. Is that right?`,
  cardAdded: (label: string) => `${label} added. Do you want to add another card?`,
  unclear: 'I could not read that card. Try again with more light, and hold it still.',
  done: (first: string) =>
    `You're all set, ${first}. Point your phone at a product and tap anywhere to scan. Your profile and settings are at the top right.`,
} as const;
