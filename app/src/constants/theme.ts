/**
 * Rewind design tokens (tech spec 1.9): "Mint Teal".
 *
 * Mint for calm (health), deep teal for trust (money). Light mint where the
 * eye rests, one deep teal control to find (Talk), and a mint-tinted off-white
 * instead of pure white to cut glare under store lights. The brand teal is
 * deliberately not the "HSA eligible" green, so brand never reads as status.
 *
 * Alerts have two levels, each with its own color, icon, and title word:
 * red = danger (declined, error), orange = warning / suggestion.
 *
 * Every pair is measured (WCAG 2.2 AA, most AAA) by scripts/contrast-audit.mjs,
 * including overlays against pure white and pure black camera scenes.
 */

export type ThemeName = 'standard' | 'dark' | 'highContrast';

export type Palette = {
  bg: string;
  surface: string;
  surfaceAlt: string;
  text: string;
  textMuted: string;
  border: string;
  focus: string;
  primary: string;
  onPrimary: string;
  /** Mint action button. */
  accent: string;
  onAccent: string;
  /** Half-circle dock: light-to-mint gradient, with an edge line so it shows on a bright scene. */
  dockTop: string;
  dockBottom: string;
  dockEdge: string;
  onDock: string;
  /** Talk button gradient, its icon color, and ring. */
  talkTop: string;
  talkBottom: string;
  onTalk: string;
  talkRing: string;
  /** Caption pill (frame 2). Border covers whichever scene the fill can't contrast with. */
  pill: string;
  onPill: string;
  pillBorder: string;
  /** See-through window (frame 3): two-tone edge, one light and one dark, visible on any scene. */
  frameOuter: string;
  frameInner: string;
  /** Edge of the solid info cards inside the window. */
  cardEdge: string;
  /** Top-right profile button: disc and ring of opposite lightness. */
  profileBg: string;
  onProfile: string;
  profileRing: string;
  eligible: string;
  eligibleBg: string;
  notEligible: string;
  notEligibleBg: string;
  unconfirmed: string;
  unconfirmedBg: string;
  /** Red alert level: declined payment, errors, frozen cards, service down. */
  danger: string;
  dangerBg: string;
  dangerEdge: string;
  /** Orange alert level: low balance, reroute and add-a-card suggestions, timeouts. */
  warning: string;
  warningBg: string;
  warningEdge: string;
  /** Width of control borders. High contrast draws a visible edge on everything. */
  controlBorderWidth: number;
};

export const Palettes: Record<ThemeName, Palette> = {
  standard: {
    bg: '#F2FAF6', // mint mist
    surface: '#FFFFFF',
    surfaceAlt: '#E4F4EE',
    text: '#0B2427', // ink teal
    textMuted: '#3E5A5E',
    border: '#5C7A7E',
    focus: '#0E5A63',
    primary: '#0E5A63', // deep teal
    onPrimary: '#FFFFFF',
    accent: '#5EDDB4', // mint
    onAccent: '#0B2427',
    dockTop: '#E4F8EF',
    dockBottom: '#8FE3C2',
    dockEdge: '#0E5A63',
    onDock: '#0B2427',
    talkTop: '#137A84',
    talkBottom: '#0A434A',
    onTalk: '#FFFFFF',
    talkRing: '#FFFFFF',
    pill: '#E4F8EF',
    onPill: '#0B2427',
    pillBorder: '#0B2427',
    frameOuter: '#FFFFFF',
    frameInner: '#0E5A63',
    cardEdge: '#0B2427',
    profileBg: '#0B2427',
    onProfile: '#FFFFFF',
    profileRing: '#FFFFFF',
    eligible: '#0A6B4F',
    eligibleBg: '#E2F5EC',
    notEligible: '#4F5B66', // slate: informational, not an alert
    notEligibleBg: '#EEF1F4',
    unconfirmed: '#4C4F9A',
    unconfirmedBg: '#ECECF8',
    danger: '#B3261E',
    dangerBg: '#FDECEA',
    dangerEdge: '#B3261E',
    warning: '#8A4B00',
    warningBg: '#FFF3E2',
    warningEdge: '#C46A00',
    controlBorderWidth: 0,
  },
  dark: {
    bg: '#0A1715',
    surface: '#12241F',
    surfaceAlt: '#1A3029',
    text: '#E8F5F0',
    textMuted: '#A7C3BA',
    border: '#7E9C94',
    focus: '#5EDDB4',
    primary: '#5EDDB4',
    onPrimary: '#0A1715',
    accent: '#5EDDB4',
    onAccent: '#0A1715',
    dockTop: '#12302B',
    dockBottom: '#1E5A4C',
    dockEdge: '#5EDDB4',
    onDock: '#E8F5F0',
    talkTop: '#8FF0C8',
    talkBottom: '#5EDDB4',
    onTalk: '#0A1715',
    talkRing: '#0A1715',
    pill: '#1A3029',
    onPill: '#E8F5F0',
    pillBorder: '#E8F5F0',
    frameOuter: '#0A1715',
    frameInner: '#5EDDB4',
    cardEdge: '#A7C3BA',
    profileBg: '#0B2427',
    onProfile: '#FFFFFF',
    profileRing: '#FFFFFF',
    eligible: '#6BE3B5',
    eligibleBg: '#0E2E25',
    notEligible: '#B8C4CE',
    notEligibleBg: '#1E262C',
    unconfirmed: '#B7B9FF',
    unconfirmedBg: '#24264A',
    danger: '#FF8A80',
    dangerBg: '#3A1614',
    dangerEdge: '#FF8A80',
    warning: '#FFB86B',
    warningBg: '#2E1E0A',
    warningEdge: '#FFB86B',
    controlBorderWidth: 0,
  },
  highContrast: {
    bg: '#000000',
    surface: '#000000',
    surfaceAlt: '#000000',
    text: '#FFFFFF',
    textMuted: '#FFFFFF',
    border: '#FFFFFF',
    focus: '#6BFFC4',
    primary: '#6BFFC4',
    onPrimary: '#000000',
    accent: '#6BFFC4',
    onAccent: '#000000',
    dockTop: '#000000',
    dockBottom: '#000000',
    dockEdge: '#FFFFFF',
    onDock: '#FFFFFF',
    talkTop: '#6BFFC4',
    talkBottom: '#6BFFC4',
    onTalk: '#000000',
    talkRing: '#FFFFFF',
    pill: '#000000',
    onPill: '#FFFFFF',
    pillBorder: '#FFFFFF',
    frameOuter: '#000000',
    frameInner: '#FFFFFF',
    cardEdge: '#FFFFFF',
    profileBg: '#000000',
    onProfile: '#FFFFFF',
    profileRing: '#6BFFC4',
    eligible: '#6BFFC4',
    eligibleBg: '#000000',
    notEligible: '#FFFFFF',
    notEligibleBg: '#000000',
    unconfirmed: '#C9CBFF',
    unconfirmedBg: '#000000',
    danger: '#FF9C94',
    dangerBg: '#000000',
    dangerEdge: '#FF9C94',
    warning: '#FFC48A',
    warningBg: '#000000',
    warningEdge: '#FFC48A',
    controlBorderWidth: 2,
  },
};

/** Sizes at 100%. The in-app text size setting multiplies these (1.0 to 2.0). */
export const Type = {
  display: { fontSize: 44, fontWeight: '800' },
  title: { fontSize: 30, fontWeight: '700' },
  heading: { fontSize: 24, fontWeight: '700' },
  body: { fontSize: 20, fontWeight: '400' },
  label: { fontSize: 20, fontWeight: '700' },
  caption: { fontSize: 22, fontWeight: '500' },
  small: { fontSize: 17, fontWeight: '500' },
} as const;

export type TypeRole = keyof typeof Type;

export const LineHeight = 1.35;

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

/** Touch target sizes in pt. WCAG 2.5.8 needs 24; we never go below 56. */
export const Target = {
  min: 56,
  primary: 72,
  talk: 104,
  tile: 120,
} as const;

export const Radius = {
  card: 16,
  button: 14,
  pill: 999,
} as const;

export const MaxContentWidth = 640;

export const Motion = {
  /** Caption pill grow / shrink. */
  pill: 260,
  /** Info panel slide in. */
  panel: 200,
} as const;

export const Elevation = {
  floating: {
    shadowColor: '#000000',
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
} as const;
