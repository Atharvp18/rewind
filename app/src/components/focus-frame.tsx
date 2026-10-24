import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';

import { useA11y } from '@/lib/a11y';
import type { Rect } from '@/lib/stage';

/** 'locked' plays one pulse when a result lands; the color never changes. */
export type FrameTone = 'guide' | 'locked';

const THICK = 6;
const HALO = 2;

/**
 * Camera-app style focus corners: four L-shaped corners, no edges, sitting on
 * the item. They glide to the item's box when it moves or a scan locks on.
 *
 * Same color and shape everywhere: mint bars with a dark halo, so one of the
 * two contrasts with any scene (mint 12.5:1 on black, halo 16:1 on white).
 * Decorative and hidden from screen readers: the pop-up and voice carry the
 * meaning.
 */
export function FocusFrame({ box, tone = 'guide' }: { box: Rect; tone?: FrameTone }) {
  const { palette, reduceMotion } = useA11y();
  const x = useSharedValue(box.x);
  const y = useSharedValue(box.y);
  const w = useSharedValue(box.w);
  const h = useSharedValue(box.h);

  useEffect(() => {
    if (reduceMotion) {
      x.value = box.x;
      y.value = box.y;
      w.value = box.w;
      h.value = box.h;
      return;
    }
    const spring = { damping: 18, stiffness: 160, mass: 0.8 };
    x.value = withSpring(box.x, spring);
    y.value = withSpring(box.y, spring);
    w.value = withSpring(box.w, spring);
    h.value = withSpring(box.h, spring);
  }, [box.x, box.y, box.w, box.h, reduceMotion, x, y, w, h]);

  const pulse = useSharedValue(1);
  useEffect(() => {
    if (reduceMotion || tone === 'guide') return;
    // A single "lock" pulse when a result arrives.
    pulse.value = 1.08;
    pulse.value = withTiming(1, { duration: 260 });
  }, [tone, reduceMotion, pulse]);

  const frameStyle = useAnimatedStyle(() => ({
    left: x.value,
    top: y.value,
    width: w.value,
    height: h.value,
    transform: [{ scale: pulse.value }],
  }));

  // One color everywhere (scan, lock-on, card onboarding): mint with a dark halo.
  const color = palette.accent;
  const arm = Math.max(24, Math.min(56, Math.min(box.w, box.h) * 0.22));

  return (
    <Animated.View
      pointerEvents="none"
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={[styles.frame, frameStyle]}>
      {(['tl', 'tr', 'bl', 'br'] as const).map((c) => (
        <Corner key={c} corner={c} arm={arm} color={color} halo={palette.profileBg} />
      ))}
    </Animated.View>
  );
}

function Corner({
  corner,
  arm,
  color,
  halo,
}: {
  corner: 'tl' | 'tr' | 'bl' | 'br';
  arm: number;
  color: string;
  halo: string;
}) {
  const top = corner[0] === 't';
  const left = corner[1] === 'l';
  const pos = {
    [top ? 'top' : 'bottom']: 0,
    [left ? 'left' : 'right']: 0,
  };
  const bar = (horizontal: boolean) => ({
    position: 'absolute' as const,
    [top ? 'top' : 'bottom']: 0,
    [left ? 'left' : 'right']: 0,
    width: horizontal ? arm : THICK + HALO * 2,
    height: horizontal ? THICK + HALO * 2 : arm,
    borderRadius: (THICK + HALO * 2) / 2,
    backgroundColor: halo,
    padding: HALO,
  });
  return (
    <View style={[styles.corner, pos, { width: arm, height: arm }]}>
      <View style={bar(true)}>
        <View style={[styles.fill, { backgroundColor: color, borderRadius: THICK / 2 }]} />
      </View>
      <View style={bar(false)}>
        <View style={[styles.fill, { backgroundColor: color, borderRadius: THICK / 2 }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { position: 'absolute' },
  corner: { position: 'absolute' },
  fill: { flex: 1 },
});
