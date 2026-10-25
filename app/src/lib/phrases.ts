/**
 * The only spoken lines the app writes itself. Everything else comes from the
 * backend (speech/compose.py, or error.speech in the envelope). Each line here
 * is either assigned to the app by the tech spec or covers a case where the
 * backend cannot be reached and so cannot supply wording.
 */

/**
 * What the agent is doing while it works, in plain words. Captioned (and spoken once for a scan) instead
 * of a bare "Looking.", and chosen from what the shopper actually asked for.
 */
export const Working = {
  /** Scan progress: the first line is spoken, the later ones only update the caption. */
  scan: [
    'Checking what this item is.',
    'Finding its price and whether it is HSA eligible.',
    'Almost there. Choosing the best card.',
  ],
  /** A line for what the shopper just said. */
  forRequest(said: string): string {
    const t = said.toLowerCase();
    if (/\b(check ?out|pay|i'?m done|ready)\b/.test(t)) return 'Getting your total ready.';
    if (/\b(history|invoices?|receipts?)\b/.test(t)) return 'Opening your purchase history.';
    if (/\b(clear|empty)\b.*\bcart\b/.test(t)) return 'Checking before I clear your cart.';
    if (/\bcart\b/.test(t)) return 'Opening your cart.';
    if (/\b(remove|delete|undo)\b/.test(t)) return 'Taking that off your cart.';
    if (/\bbalance\b/.test(t)) return 'Checking what I can tell you about that.';
    if (/\b(repeat|again)\b/.test(t)) return 'Getting that again.';
    if (/^\W*(no|nope|nah|skip|cancel|never ?mind)\b/.test(t)) return 'Okay, skipping that.';
    if (/^\W*(yes|yeah|yep|sure|ok|okay|please|add)\b|\bgo ahead\b|\b(hsa|fsa|visa|credit|debit)\b/.test(t))
      return 'Adding that for you.';
    return 'Working on that.';
  },
} as const;

export const Phrases = {
  /** Talk button tap (business spec 6.5 A). */
  greeting: 'How may I help you today?',
  /** Every launch after onboarding: say it and caption it. */
  launchWelcome: 'Welcome back. Please place your item on the frame.',
  /** Paused after a scan with the item still in view. */
  askRepeat: 'Would you like me to repeat?',
  /** Paused after a scan and the item moved out of the frame. */
  askMore: "Is there anything else you'd like me to scan?",
  okay: 'Okay.',
  /** The scan found nothing to read: no panel, just this line. */
  noItem: 'I do not see an item in the frame. Please hold the item steady in front of the camera.',
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
  /** The cart review went unanswered: the cart closes. */
  readyToCheckout: "Okay. Let me know when you're ready to checkout.",
  /** Orb tapped while the purchase history is open. */
  onHistory: (invoices: number, reimbursable: string | null) =>
    `You're on your purchase history. You have ${invoices} ${invoices === 1 ? 'invoice' : 'invoices'}.${
      reimbursable ? ` Possible reimbursement: ${reimbursable}.` : ''
    } Tap History to go back.`,
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
  /** The first thing a new shopper hears: who Rewind is and how to use it. */
  welcome:
    "Welcome to Rewind. I help you shop with your HSA, FSA, and everyday cards. Hold a product steady in front of the camera, and I'll tell you what it is, what it costs, and which card to use. Say yes to add it to your cart, and say checkout when you're ready to pay. Tap the round button any time to talk to me. Let's get you set up.",
  askInsurance:
    "Now your insurance card. Hold it flat inside the corners, about a hand length from the phone, and keep still. I'll take the photo for you.",
  confirmInsurance: (insurer: string, plan: string | null, hasRx: boolean) =>
    `Your insurance is ${insurer}${plan ? `, ${plan}` : ''}.${hasRx ? ' It shows prescription benefits.' : ''} Is that right?`,
  askPayment: (first: boolean) =>
    first
      ? "Now your HSA or FSA Visa card. Hold it flat inside the corners, about a hand length from the phone, and keep still. I'll take the photo for you."
      : "Now your everyday Visa card, credit or debit. Hold it flat inside the corners, about a hand length from the phone, and keep still. I'll take the photo for you.",
  askCardType: 'Is this Visa card an HSA card, an FSA card, a credit card, or a debit card?',
  confirmCard: (label: string, last4: string | null) =>
    `I see ${label}${last4 ? ` ending in ${last4.split('').join(' ')}` : ''}. Is that right?`,
  cardAdded: (label: string) => `${label} added. Do you want to add another card?`,
  unclear: 'I could not read that card. Try again with more light, and hold it still.',
  done: (first: string) =>
    `You're all set, ${first}. Point your phone at a product and tap anywhere to scan. Your profile and settings are at the top right.`,
} as const;
