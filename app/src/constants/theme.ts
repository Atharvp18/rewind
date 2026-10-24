/**
 * Rewind design tokens (tech spec 1.9). Every text pair here is checked against
 * WCAG 2.2 AA (4.5:1 text, 3:1 UI boundaries); the ratios are listed in the spec.
 * Rule: amber `accent` never sits directly on the light `bg` (1.8:1). It only
 * appears on the navy dock or inside a `text`-colored ring.
 */

export type ThemeName = 'standard' | 'dark' | 'highContrast';

export type Palette = {
  bg: string;
  surface: string;
  surfaceAlt: string;
  text: string;
  textMuted: string;
  border: string;
  primary: string;
  onPrimary: string;
  accent: string;
  onAccent: string;
  dock: string;
  onDock: string;
  focus: string;
  eligible: string;
  eligibleBg: string;
  notEligible: string;
  notEligibleBg: string;
  unconfirmed: string;
  unconfirmedBg: string;
  danger: string;
  dangerBg: string;
  scrim: string;
  /** Width of control borders. High contrast draws a visible edge on everything. */
  controlBorderWidth: number;
};

export const Palettes: Record<ThemeName, Palette> = {
  standard: {
    bg: '#F7F5F0',
    surface: '#FFFFFF',
    surfaceAlt: '#EEEBE4',
    text: '#14181F',
    textMuted: '#4A5260',
    border: '#6B7280',
    primary: '#123E6B',
    onPrimary: '#FFFFFF',
    accent: '#F2A900',
    onAccent: '#14181F',
    dock: '#123E6B',
    onDock: '#FFFFFF',
    focus: '#123E6B',
    eligible: '#0B6E4F',
    eligibleBg: '#E3F4EC',
    notEligible: '#B23A0E',
    notEligibleBg: '#FCEBE3',
    unconfirmed: '#4C4F9A',
    unconfirmedBg: '#ECECF8',
    danger: '#B3261E',
    dangerBg: '#FCE8E6',
    scrim: 'rgba(20,24,31,0.55)',
    controlBorderWidth: 0,
  },
  dark: {
    bg: '#0E141B',
    surface: '#1A232E',
    surfaceAlt: '#243040',
    text: '#F3F4F6',
    textMuted: '#B8C0CC',
    border: '#8A94A3',
    primary: '#8CC4FF',
    onPrimary: '#0E141B',
    accent: '#FFC233',
    onAccent: '#14181F',
    dock: '#1A232E',
    onDock: '#F3F4F6',
    focus: '#FFC233',
    eligible: '#5BD6A6',
    eligibleBg: '#0F2E24',
    notEligible: '#FF9B73',
    notEligibleBg: '#3A1B10',
    unconfirmed: '#B7B9FF',
    unconfirmedBg: '#24264A',
    danger: '#FF8A80',
    dangerBg: '#3A1614',
    scrim: 'rgba(0,0,0,0.6)',
    controlBorderWidth: 0,
  },
  highContrast: {
    bg: '#000000',
    surface: '#000000',
    surfaceAlt: '#000000',
    text: '#FFFFFF',
    textMuted: '#FFFFFF',
    border: '#FFFFFF',
    primary: '#FFE000',
    onPrimary: '#000000',
    accent: '#FFE000',
    onAccent: '#000000',
    dock: '#000000',
    onDock: '#FFFFFF',
    focus: '#FFE000',
    eligible: '#7CFFB2',
    eligibleBg: '#000000',
    notEligible: '#FFB38A',
    notEligibleBg: '#000000',
    unconfirmed: '#C9CBFF',
    unconfirmedBg: '#000000',
    danger: '#FF9C94',
    dangerBg: '#000000',
    scrim: 'rgba(0,0,0,0.85)',
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
