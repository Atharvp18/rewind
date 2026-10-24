import { Pressable, StyleSheet } from 'react-native';

import { Icon } from '@/components/icon';
import { Elevation, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useResponsive } from '@/lib/responsive';
import { useAgent } from '@/state/agent';

/**
 * Top row, beside Profile: opens the purchase history from where the thumb can reach it
 * (the bottom handle is the swipe-up way; voice "find invoice history" is the third).
 */
export function HistoryButton() {
  const { palette } = useA11y();
  const { state, showView } = useAgent();
  const { ui } = useResponsive();
  const open = state.view === 'history';
  const size = 56 * ui;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Purchase history"
      accessibilityHint="Opens your past invoices."
      accessibilityState={{ expanded: open }}
      onPress={() => showView(open ? 'camera' : 'history')}
      hitSlop={8}
      style={({ pressed }) => [
        styles.btn,
        { width: size, height: size, borderRadius: size / 2 },
        Elevation.floating,
        {
          backgroundColor: palette.surface,
          borderColor: palette.controlBorderWidth ? palette.border : 'rgba(11,36,39,0.35)',
          borderWidth: palette.controlBorderWidth ? 3 : 1.5,
          opacity: pressed ? 0.85 : 1,
        },
      ]}>
      <Icon name="history" size={28} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: { minWidth: Target.min, alignItems: 'center', justifyContent: 'center' },
});
