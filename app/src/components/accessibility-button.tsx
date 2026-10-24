import { router } from 'expo-router';
import { Pressable, StyleSheet } from 'react-native';

import { AppText } from '@/components/app-text';
import { Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useAgent } from '@/state/agent';

/**
 * Decision 12: one button on every screen. Short tap repeats the last prompt
 * with haptic feedback; long press (or saying "accessibility settings") opens
 * the settings panel.
 */
export function AccessibilityButton() {
  const { palette } = useA11y();
  const { repeat } = useAgent();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Accessibility"
      accessibilityHint="Tap to repeat the last message. Double tap and hold for settings."
      accessibilityActions={[{ name: 'activate' }, { name: 'longpress', label: 'Open accessibility settings' }]}
      onAccessibilityAction={(e) =>
        e.nativeEvent.actionName === 'longpress' ? router.push('/settings') : repeat()
      }
      onPress={repeat}
      onLongPress={() => router.push('/settings')}
      delayLongPress={450}
      hitSlop={8}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: palette.primary, borderColor: palette.text, opacity: pressed ? 0.8 : 1 },
      ]}>
      <AppText kind="heading" color="onPrimary" accessible={false} style={styles.glyph}>
        ♿︎
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: Target.min,
    height: Target.min,
    borderRadius: Target.min / 2,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Fixed size: the glyph is decorative and must not grow out of its circle.
  glyph: { fontSize: 28, lineHeight: 34 },
});
