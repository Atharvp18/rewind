import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { PROFILE_SIZE } from '@/components/profile-button';
import { Motion, Spacing, Type } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useAgent } from '@/state/agent';

/** Screens shorter than this (pt) cap the caption at 3 lines (iPhone SE, small Androids). */
const SHORT_SCREEN = 760;
const VERY_SHORT_SCREEN = 700;

/**
 * Frame 2: the caption pill. When Rewind speaks, a gray pill grows leftward
 * out of the profile button and shows the words (captions, WCAG 1.2.2, on by
 * default). The user's last words show above in smaller text. Tap to repeat
 * the last message with a buzz (decision 12). With Reduce Motion it appears
 * at once. It grows from the right edge, under the profile button.
 */
export function TranscriptPill() {
  const { palette, settings, reduceMotion, screenReaderOn } = useA11y();
  const { state, repeat } = useAgent();
  const { height } = useWindowDimensions();
  const [rowWidth, setRowWidth] = useState(0);
  // Which line the user expanded (a new line starts collapsed again).
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const width = useSharedValue(0);
  const textOpacity = useSharedValue(0);

  const lastAgent = [...state.transcript].reverse().find((l) => l.who === 'agent');
  const last = state.transcript[state.transcript.length - 1];
  const userLine = last?.who === 'user' ? last : null;
  // Alert lines use the two levels: red for a decline, orange for warnings.
  const level = state.declined ? 'danger' : 'warning';
  const open = settings.captions && !!(lastAgent || userLine) && rowWidth > 0;

  // Short screens: cap the line at 3 rows so the answer card keeps room for its
  // Yes/No without scrolling. Tap shows the rest; screen readers always get it all.
  const fontSize = Type.caption.fontSize * settings.textScale;
  // 2 lines on very short screens (iPhone SE), 3 on medium ones.
  const maxLines = height < VERY_SHORT_SCREEN ? 2 : 3;
  const charsPerCap = ((rowWidth - Spacing.xl * 2) / (fontSize * 0.52)) * maxLines;
  const capped =
    height < SHORT_SCREEN && !!lastAgent && expandedId !== lastAgent.id && lastAgent.text.length > charsPerCap;

  useEffect(() => {
    const target = open ? rowWidth : 0;
    if (reduceMotion) {
      width.value = target;
      textOpacity.value = open ? 1 : 0;
    } else {
      width.value = withTiming(target, { duration: Motion.pill });
      textOpacity.value = withTiming(open ? 1 : 0, { duration: open ? Motion.pill * 1.5 : 80 });
    }
  }, [open, rowWidth, reduceMotion, width, textOpacity]);

  // Fully hidden when collapsed: zero width and no paint.
  const pillStyle = useAnimatedStyle(() => ({ width: width.value, opacity: width.value > 1 ? 1 : 0 }));
  const textStyle = useAnimatedStyle(() => ({ opacity: textOpacity.value }));

  return (
    <View style={styles.row} onLayout={(e) => setRowWidth(e.nativeEvent.layout.width)} pointerEvents="box-none">
      {rowWidth > 0 ? (
        // Stays mounted so collapsing animates too; collapsed it has zero width.
        <Animated.View
          importantForAccessibility={open ? 'auto' : 'no-hide-descendants'}
          accessibilityElementsHidden={!open}
          style={[
            styles.pill,
            pillStyle,
            {
              backgroundColor: palette.pill,
              borderColor: state.captionIsAlert
                ? level === 'danger'
                  ? palette.dangerEdge
                  : palette.warningEdge
                : palette.pillBorder,
              borderWidth: state.captionIsAlert ? 2 : palette.controlBorderWidth,
            },
          ]}>
          <Pressable
            onPress={() => (capped && lastAgent ? setExpandedId(lastAgent.id) : repeat())}
            disabled={!open}
            accessibilityRole="button"
            // The screen reader already hears each line via announce(); do not read it twice.
            accessibilityLiveRegion={screenReaderOn ? 'none' : 'polite'}
            accessibilityLabel={`${state.captionIsAlert ? 'Alert. ' : ''}Rewind said: ${lastAgent?.text ?? ''}`}
            accessibilityHint={capped ? 'Tap to show the whole line.' : 'Tap to hear it again.'}
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
                <View style={styles.line}>
                  {state.captionIsAlert ? (
                    <Icon name={level === 'danger' ? 'danger' : 'alert'} size={24} color={level} />
                  ) : null}
                  <AppText
                    kind="caption"
                    color="onPill"
                    accessible={false}
                    numberOfLines={capped ? maxLines : undefined}
                    style={styles.lineText}>
                    {lastAgent.text}
                  </AppText>
                </View>
              ) : null}
              {capped ? (
                <AppText kind="small" color="onPill" accessible={false} style={styles.more}>
                  Tap for more
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
  line: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  lineText: { flexShrink: 1 },
  more: { fontWeight: '700', textDecorationLine: 'underline' },
  row: { flex: 1, alignItems: 'flex-end' },
  pill: { minHeight: PROFILE_SIZE, borderRadius: PROFILE_SIZE / 2, overflow: 'hidden' },
  press: { flex: 1, justifyContent: 'center', alignItems: 'flex-end' },
  // Right padding keeps text clear of the profile button that overlaps the pill's end.
  text: {
    paddingLeft: Spacing.xl,
    paddingRight: Spacing.xl,
    paddingVertical: Spacing.md,
    gap: Spacing.xs,
  },
});

