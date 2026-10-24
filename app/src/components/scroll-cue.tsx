import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';
import Animated, {
  Easing,
  FadeIn,
  FadeOut,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { withOpacity } from '@/lib/color';

/** Within this many points of the end, there is nothing left to hint at. */
const NEAR_END = 24;

/**
 * Tracks a ScrollView so the cue knows whether there is more below.
 * Spread `scrollProps` onto the ScrollView; use `more` for <ScrollCue visible>.
 * `overflowing` is true when the content is taller than the view at all.
 */
export function useScrollCue() {
  const [viewport, setViewport] = useState(0);
  const [content, setContent] = useState(0);
  const [offset, setOffset] = useState(0);
  return {
    more: viewport > 0 && content - viewport - offset > NEAR_END,
    overflowing: viewport > 0 && content > viewport + 1,
    content,
    scrollProps: {
      onLayout: (e: LayoutChangeEvent) => setViewport(e.nativeEvent.layout.height),
      onContentSizeChange: (_w: number, h: number) => setContent(h),
      onScroll: (e: NativeSyntheticEvent<NativeScrollEvent>) => setOffset(e.nativeEvent.contentOffset.y),
      scrollEventThrottle: 32,
    },
  };
}

/**
 * "There is more below": a soft fade at the bottom edge with a small pill whose
 * chevron bobs gently. Shown only while there is more to scroll; it fades away
 * once the end is near. With Reduce Motion it is a still chevron. Decorative:
 * screen readers move through the content natively, so it is hidden from them.
 *
 * `bg` is the surface color behind the scrolling content, so the fade blends in.
 */
export function ScrollCue({ visible, bg }: { visible: boolean; bg: string }) {
  const { palette, reduceMotion } = useA11y();
  const bob = useSharedValue(0);

  useEffect(() => {
    if (!visible || reduceMotion) {
      bob.value = 0;
      return;
    }
    bob.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 650, easing: Easing.inOut(Easing.quad) }),
        withTiming(0, { duration: 650, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
    );
  }, [visible, reduceMotion, bob]);

  const chevron = useAnimatedStyle(() => ({ transform: [{ translateY: bob.value * 5 }] }));

  if (!visible) return null;
  return (
    <Animated.View
      pointerEvents="none"
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      entering={reduceMotion ? undefined : FadeIn.duration(200)}
      exiting={reduceMotion ? undefined : FadeOut.duration(150)}
      style={styles.wrap}>
      <LinearGradient colors={[withOpacity(bg, 0), bg]} style={StyleSheet.absoluteFill} />
      <View style={[styles.pill, { backgroundColor: palette.primary }]}>
        <AppText kind="small" color="onPrimary" accessible={false} style={styles.label}>
          More
        </AppText>
        <Animated.View style={chevron}>
          <Icon name="chevronDown" size={18} color="onPrimary" strokeWidth={3} />
        </Animated.View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 64, justifyContent: 'flex-end', alignItems: 'center' },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    borderRadius: Radius.pill,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  label: { fontWeight: '800' },
});
