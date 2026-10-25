import { Pressable, StyleSheet } from 'react-native';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { PROFILE_SIZE } from '@/components/profile-button';
import { Elevation, Press, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { useResponsive } from '@/lib/responsive';
import { useAgent } from '@/state/agent';

/**
 * Top-left cart chip, mirrored across from the profile button: item count and
 * before-tax total, always in view. Opens the cart in the see-through window.
 * "What's in my cart" does the same by voice (tech spec 3.8).
 */
export function CartChip() {
  const { palette, settings } = useA11y();
  const { state, showView } = useAgent();
  const count = state.cart.groups.reduce((n, g) => n + g.items.length, 0);
  const label = count
    ? `Cart, ${count} ${count === 1 ? 'item' : 'items'}, ${centsForScreenReader(state.cart.total_cents)} before tax`
    : 'Cart, empty';
  // The chip's text grows to 150% at most so it never pushes the profile button off screen;
  // the full cart in the window follows the user's text size up to 200%.
  const { ui, type } = useResponsive();
  const scale = Math.min(settings.textScale, 1.5) * type;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint="Opens your cart."
      onPress={() => showView('cart')}
      hitSlop={8}
      style={({ pressed }) => [
        styles.chip,
        { minHeight: PROFILE_SIZE * ui, minWidth: PROFILE_SIZE * ui },
        Elevation.floating,
        { backgroundColor: palette.profileBg, borderColor: palette.controlBorderWidth ? palette.profileRing : 'rgba(255,255,255,0.35)',
          borderWidth: palette.controlBorderWidth ? 3 : 1.5, opacity: pressed ? Press.pressed : 1 },
      ]}>
      <Icon name="cart" size={26} color="onProfile" />
      <AppText color="onProfile" accessible={false} style={[styles.text, { fontSize: Math.round(20 * scale) }]}>
        {count ? `Cart ${count} · ${formatCents(state.cart.total_cents)}` : 'Cart'}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    minHeight: PROFILE_SIZE,
    minWidth: PROFILE_SIZE,
    borderRadius: Radius.pill,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  text: { fontWeight: '800' },
});
