import {
  ArrowRight,
  Camera,
  Check,
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
}: {
  name: IconName;
  size?: number;
  color?: keyof Palette;
  strokeWidth?: number;
}) {
  const { palette } = useA11y();
  const Glyph = ICONS[name];
  return (
    <View accessible={false} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
      <Glyph size={size} color={palette[color] as string} strokeWidth={strokeWidth} />
    </View>
  );
}

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
