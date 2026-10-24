import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useAgent } from '@/state/agent';

/**
 * On-screen text of everything the agent says (WCAG 1.2.2, on by default).
 * The caption is exactly VoiceRequest.text, so it always matches the speech.
 */
export function CaptionBar() {
  const { palette, settings, screenReaderOn } = useA11y();
  const { state } = useAgent();
  if (!settings.captions || !state.caption) return null;

  const alert = state.captionIsAlert;
  return (
    <View
      // The screen reader already hears the text via announce(); avoid reading it twice.
      accessibilityLiveRegion={screenReaderOn ? 'none' : 'polite'}
      accessibilityLabel={`${alert ? 'Alert. ' : ''}Rewind said: ${state.caption}`}
      style={[
        styles.bar,
        {
          backgroundColor: alert ? palette.dangerBg : palette.surface,
          borderColor: alert ? palette.danger : palette.border,
          borderWidth: alert ? 3 : 2,
        },
      ]}>
      <AppText kind="small" color={alert ? 'danger' : 'textMuted'} accessible={false}>
        {alert ? '⚠ Alert' : '🔊 Rewind said'}
      </AppText>
      <AppText kind="caption" accessible={false}>
        {state.caption}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    borderRadius: Radius.card,
    padding: Spacing.lg,
    gap: Spacing.xs,
  },
});
