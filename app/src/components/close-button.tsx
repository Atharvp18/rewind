import { Pressable, StyleSheet } from 'react-native';

import { Icon } from '@/components/icon';
import { Press, Radius, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

/** One round ✕ for every card, sheet and pop-up: same size, icon, hit area and press feedback. */
export const CLOSE_SIZE = Target.min;

export function CloseButton({ label, onPress }: { label: string; onPress: () => void }) {
  const { palette } = useA11y();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={8}
      style={({ pressed }) => [styles.close, { backgroundColor: palette.surfaceAlt, opacity: pressed ? Press.pressed : 1 }]}>
      <Icon name="close" size={26} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  close: {
    width: CLOSE_SIZE,
    height: CLOSE_SIZE,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
