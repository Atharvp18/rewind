import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { PROFILE_SIZE } from '@/components/profile-button';
import { Motion, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useAgent } from '@/state/agent';

/**
 * Frame 2: the caption pill. When Rewind speaks, a gray pill grows leftward
 * out of the profile button and shows the words (captions, WCAG 1.2.2, on by
 * default). The user's last words show above in smaller text. Tap to repeat
 * the last message with a buzz (decision 12). With Reduce Motion it appears
 * at once. Rendered under the profile button, which sits on top at the right.
 */
export function TranscriptPill() {
  const { palette, settings, reduceMotion, screenReaderOn, themeName } = useA11y();
  const { state, repeat } = useAgent();
  const [rowWidth, setRowWidth] = useState(0);
  const width = useSharedValue(PROFILE_SIZE);
  const textOpacity = useSharedValue(0);

  const lastAgent = [...state.transcript].reverse().find((l) => l.who === 'agent');
  const last = state.transcript[state.transcript.length - 1];
  const userLine = last?.who === 'user' ? last : null;
  const open = settings.captions && !!(lastAgent || userLine) && rowWidth > 0;

  useEffect(() => {
    const target = open ? rowWidth : PROFILE_SIZE;
    if (reduceMotion) {
      width.value = target;
      textOpacity.value = open ? 1 : 0;
    } else {
      width.value = withTiming(target, { duration: Motion.pill });
      textOpacity.value = withTiming(open ? 1 : 0, { duration: open ? Motion.pill * 1.5 : 80 });
    }
  }, [open, rowWidth, reduceMotion, width, textOpacity]);

  const pillStyle = useAnimatedStyle(() => ({ width: width.value }));
  const textStyle = useAnimatedStyle(() => ({ opacity: textOpacity.value }));

  return (
    <View style={styles.row} onLayout={(e) => setRowWidth(e.nativeEvent.layout.width)} pointerEvents="box-none">
      {rowWidth > 0 ? (
        // Stays mounted so collapsing animates too. Collapsed, it is exactly the
        // profile button's size and sits hidden under it.
        <Animated.View
          importantForAccessibility={open ? 'auto' : 'no-hide-descendants'}
          accessibilityElementsHidden={!open}
          style={[
            styles.pill,
            pillStyle,
            {
              backgroundColor: palette.pill,
              borderColor: state.captionIsAlert ? palette.danger : palette.onPill,
              borderWidth: state.captionIsAlert ? 3 : themeName === 'highContrast' ? 2 : 0,
            },
          ]}>
          <Pressable
            onPress={repeat}
            disabled={!open}
            accessibilityRole="button"
            // The screen reader already hears each line via announce(); do not read it twice.
            accessibilityLiveRegion={screenReaderOn ? 'none' : 'polite'}
            accessibilityLabel={`${state.captionIsAlert ? 'Alert. ' : ''}Rewind said: ${lastAgent?.text ?? ''}`}
            accessibilityHint="Tap to hear it again."
            style={styles.press}>
            {open ? (
            // Fixed full width, anchored right: the growing pill reveals the text
            // from the right edge instead of reflowing it every frame.
            <Animated.View style={[styles.text, textStyle, { width: rowWidth }]}>
              {userLine ? (
                <AppText kind="small" color="onPill" accessible={false} numberOfLines={2}>
                  {`You: ${userLine.text}`}
                </AppText>
              ) : null}
              {lastAgent ? (
                <AppText kind="caption" color="onPill" accessible={false}>
                  {state.captionIsAlert ? '⚠ ' : ''}
                  {lastAgent.text}
                </AppText>
              ) : null}
            </Animated.View>
            ) : null}
          </Pressable>
        </Animated.View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flex: 1, alignItems: 'flex-end', minHeight: PROFILE_SIZE },
  pill: { minHeight: PROFILE_SIZE, borderRadius: PROFILE_SIZE / 2, overflow: 'hidden' },
  press: { flex: 1, justifyContent: 'center', alignItems: 'flex-end' },
  // Right padding keeps text clear of the profile button that overlaps the pill's end.
  text: {
    paddingLeft: Spacing.xl,
    paddingRight: PROFILE_SIZE + Spacing.sm,
    paddingVertical: Spacing.md,
    gap: Spacing.xs,
  },
});
