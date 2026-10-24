import {
  ArrowRight,
  Camera,
  Check,
  ChevronDown,
  CircleCheck,
  CircleHelp,
  CircleX,
  CreditCard,
  HeartPulse,
  Keyboard,
  Mic,
  Pill,
  Minus,
  OctagonAlert,
  Plus,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  ShoppingCart,
  Square,
  Trash2,
  TriangleAlert,
  Undo2,
  UserRound,
  X,
  type LucideIcon,
} from 'lucide-react-native';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Spacing, type Palette } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

/**
 * The app's icon set (Lucide, stroke icons drawn with react-native-svg).
 * Screens name an icon by meaning, never by glyph. Icons are decorative:
 * the text next to them, or the control's accessibilityLabel, carries the
 * meaning (WCAG 1.1.1, 1.4.1).
 */
const ICONS = {
  check: Check,
  chevronDown: ChevronDown,
  close: X,
  retry: RotateCcw,
  camera: Camera,
  scan: ScanLine,
  mic: Mic,
  stop: Square,
  keyboard: Keyboard,
  next: ArrowRight,
  add: Plus,
  minus: Minus,
  undo: Undo2,
  trash: Trash2,
  alert: TriangleAlert,
  danger: OctagonAlert,
  cart: ShoppingCart,
  user: UserRound,
  card: CreditCard,
  health: HeartPulse,
  pill: Pill,
  verified: ShieldCheck,
  eligible: CircleCheck,
  notEligible: CircleX,
  unconfirmed: CircleHelp,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;

export function Icon({
  name,
  size = 24,
  color = 'text',
  strokeWidth = 2.25,
  outline,
}: {
  name: IconName;
  size?: number;
  color?: keyof Palette;
  strokeWidth?: number;
  /**
   * A thin outline in this palette color, drawn behind the glyph. Keeps the icon
   * legible on a background that moves between light and dark (the voice orb's
   * gradient) without a shape behind it.
   */
  outline?: keyof Palette | null;
}) {
  const { palette } = useA11y();
  const Glyph = ICONS[name];

  if (!outline) {
    return (
      <View accessible={false} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
        <Glyph size={size} color={palette[color] as string} strokeWidth={strokeWidth} />
      </View>
    );
  }

  // Outlined: both layers share a canvas with room around the 24 × 24 glyph, because a
  // thicker stroke would otherwise be clipped at the SVG's edge (the mic's top and bottom
  // touch it). The canvas is centered on the icon, so the icon keeps its size and place.
  const span = 24 + OUTLINE_ROOM * 2;
  const canvas = (size * span) / 24;
  const inset = -(size * OUTLINE_ROOM) / 24;
  const layer = { size: canvas, viewBox: `${-OUTLINE_ROOM} ${-OUTLINE_ROOM} ${span} ${span}` };
  return (
    <View
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={{ width: size, height: size }}>
      <View style={{ position: 'absolute', left: inset, top: inset, width: canvas, height: canvas }}>
        <View style={StyleSheet.absoluteFill}>
          <Glyph {...layer} color={palette[outline] as string} strokeWidth={strokeWidth + OUTLINE_WIDTH} />
        </View>
        <Glyph {...layer} color={palette[color] as string} strokeWidth={strokeWidth} />
      </View>
    </View>
  );
}

/** Room around the glyph for the outline, in glyph units (a 24-unit glyph gets 4 on each side). */
const OUTLINE_ROOM = 4;
/** How much thicker the outline stroke is than the glyph's own, in glyph units. */
const OUTLINE_WIDTH = 2.4;

/** Icon + words in one row, e.g. a warning line. The words carry the meaning. */
export function Notice({
  icon,
  children,
  color = 'text',
  kind = 'body',
}: {
  icon: IconName;
  children: string;
  color?: keyof Palette;
  kind?: 'body' | 'label' | 'heading' | 'small';
}) {
  const { settings } = useA11y();
  const size = Math.round((kind === 'small' ? 18 : kind === 'heading' ? 26 : 22) * Math.min(settings.textScale, 1.5));
  return (
    <View style={styles.row} accessible accessibilityLabel={children}>
      <View style={styles.iconBox}>
        <Icon name={icon} size={size} color={color} />
      </View>
      <AppText kind={kind} color={color} style={styles.text} accessible={false}>
        {children}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  iconBox: { paddingTop: 2 },
  text: { flexShrink: 1 },
});
