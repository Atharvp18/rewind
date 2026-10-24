import { LinearGradient } from 'expo-linear-gradient';
import { useEffect } from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { withOpacity } from '@/components/info-panel';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { onMicLevel } from '@/lib/audio';
import { useAgent, type Phase } from '@/state/agent';

export const ORB_SIZE = 104;

type Mode = 'idle' | 'listening' | 'thinking' | 'speaking';

const MODE: Record<Phase, Mode> = {
  idle: 'idle',
  awaiting_confirm: 'idle',
  listening: 'listening',
  interrupted: 'listening',
  capturing: 'thinking',
  awaiting_scan: 'thinking',
  submitting: 'thinking',
  speaking_result: 'speaking',
  speaking_error: 'speaking',
};

const STATUS: Record<Phase, string> = {
  idle: 'Tap to wake Rewind',
  awaiting_confirm: 'Tap and say yes or no',
  listening: 'Listening… tap to send',
  interrupted: 'Listening…',
  capturing: 'Taking photo…',
  awaiting_scan: 'Looking…',
  submitting: 'Working…',
  speaking_result: 'Speaking… tap to interrupt',
  speaking_error: 'Speaking… tap to interrupt',
};

/**
 * The voice agent at the bottom of the screen (business spec 6.5 A, redesigned):
 * a soft mint glow that fades into the camera, and a living orb that wakes the
 * agent. Tap to wake and talk, hold to speak, tap while it speaks to interrupt.
 *
 * The orb breathes when idle, swells with the user's voice while listening,
 * spins faster while thinking, and ripples while Rewind speaks. With Reduce
 * Motion it stays still. State is always written in the status pill, so motion
 * and color are never the only signal.
 */
export function VoiceOrb({ hint }: { hint?: string | null }) {
  const { palette, reduceMotion } = useA11y();
  const { state, talkTap, talkHoldStart, talkHoldEnd } = useAgent();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const mode = MODE[state.phase];

  const spin = useSharedValue(0);
  const breathe = useSharedValue(1);
  const level = useSharedValue(0);
  const ripple = useSharedValue(0);

  // Flowing gradient: one slow turn, faster while thinking.
  useEffect(() => {
    cancelAnimation(spin);
    if (reduceMotion) return;
    spin.value = withRepeat(
      withTiming(spin.value + 360, { duration: mode === 'thinking' ? 1400 : 7000, easing: Easing.linear }),
      -1,
    );
  }, [mode, reduceMotion, spin]);

  // Breathing when idle; ripples while speaking.
  useEffect(() => {
    cancelAnimation(breathe);
    cancelAnimation(ripple);
    breathe.value = 1;
    ripple.value = 0;
    if (reduceMotion) return;
    if (mode === 'idle') {
      breathe.value = withRepeat(withTiming(1.05, { duration: 1800, easing: Easing.inOut(Easing.sin) }), -1, true);
    }
    if (mode === 'speaking') {
      ripple.value = withRepeat(withSequence(withTiming(1, { duration: 1400 }), withDelay(100, withTiming(0, { duration: 0 }))), -1);
    }
  }, [mode, reduceMotion, breathe, ripple]);

  // Swell with the microphone level while listening.
  useEffect(() => {
    if (reduceMotion) return;
    return onMicLevel((l) => {
      level.value = withTiming(l, { duration: 90 });
    });
  }, [reduceMotion, level]);

  const orbStyle = useAnimatedStyle(() => ({
    transform: [{ scale: breathe.value * (1 + level.value * 0.28) }],
  }));
  const spinStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value}deg` }] }));
  const rippleStyle = useAnimatedStyle(() => ({
    opacity: 0.45 * (1 - ripple.value),
    transform: [{ scale: 1 + ripple.value * 0.7 }],
  }));

  const listening = state.phase === 'listening';
  const status = hint && state.phase === 'idle' ? hint : STATUS[state.phase];
  // The glow is a big circle whose top shows as a dome behind the orb (business spec 6.5 A
  // half-moon), filled with a vertical fade so its edge melts into the camera: no outline.
  const glowHeight = Math.min(300, height * 0.3) + insets.bottom;
  const domeD = Math.max(width * 1.35, glowHeight * 2);
  const f = glowHeight / domeD;

  return (
    <View style={[styles.root, { paddingBottom: Math.max(insets.bottom, Spacing.lg) }]} pointerEvents="box-none">
      {/* Seamless glow: fades from clear into mint at the bottom edge. Decorative. */}
      <View
        pointerEvents="none"
        style={[
          styles.dome,
          {
            width: domeD,
            height: domeD,
            borderRadius: domeD / 2,
            left: (width - domeD) / 2,
            bottom: glowHeight - domeD,
            // Thin edge so the dome reads as a shape; the fill still fades into the camera.
            borderWidth: palette.controlBorderWidth ? 3 : 2,
            borderColor: palette.controlBorderWidth ? palette.dockEdge : withOpacity(palette.dockEdge, 0.7),
          },
        ]}>
        <LinearGradient
          colors={[
            withOpacity(palette.dockTop, 0),
            withOpacity(palette.dockTop, 0.6),
            withOpacity(palette.dockBottom, 0.95),
            withOpacity(palette.dockBottom, 0.95),
          ]}
          locations={[0, f * 0.4, f, 1]}
          style={StyleSheet.absoluteFill}
        />
      </View>

      <View style={styles.orbWrap} pointerEvents="box-none">
        {!reduceMotion && mode === 'speaking' ? (
          <Animated.View pointerEvents="none" style={[styles.ripple, { borderColor: palette.accent }, rippleStyle]} />
        ) : null}
        <Animated.View style={orbStyle}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={listening ? 'Stop and send' : 'Wake Rewind'}
            accessibilityHint="Tap to talk to Rewind, or hold while you speak. Tap while Rewind is speaking to interrupt."
            accessibilityState={{ busy: mode === 'thinking' }}
            onPress={talkTap}
            onLongPress={talkHoldStart}
            onPressOut={talkHoldEnd}
            delayLongPress={350}
            style={[
              styles.orb,
              {
                borderColor: palette.controlBorderWidth ? palette.talkRing : withOpacity(palette.talkRing, 0.6),
                borderWidth: palette.controlBorderWidth ? 3 : 2,
              },
            ]}>
            <Animated.View style={[styles.spinner, spinStyle]}>
              <LinearGradient
                colors={[palette.talkTop, palette.accent, palette.talkBottom, palette.talkTop]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={StyleSheet.absoluteFill}
              />
            </Animated.View>
            {/* Steady dark core keeps the icon at a fixed contrast while the gradient moves. */}
            <View style={[styles.core, { backgroundColor: withOpacity(palette.talkBottom, 0.92) }]}>
              <Icon name={listening ? 'stop' : 'mic'} size={30} color="onTalk" strokeWidth={2.5} />
            </View>
          </Pressable>
        </Animated.View>
      </View>

      <View
        accessibilityLiveRegion="polite"
        accessibilityLabel={`Status: ${status}`}
        style={[
          styles.status,
          { backgroundColor: palette.pill, borderColor: palette.pillBorder, borderWidth: palette.controlBorderWidth },
        ]}>
        <AppText kind="small" color="onPill" accessible={false} style={styles.center}>
          {status}
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { alignItems: 'center', gap: Spacing.md, paddingTop: Spacing.md },
  dome: { position: 'absolute', overflow: 'hidden' },
  orbWrap: { width: ORB_SIZE * 1.8, height: ORB_SIZE * 1.25, alignItems: 'center', justifyContent: 'center' },
  ripple: {
    position: 'absolute',
    width: ORB_SIZE,
    height: ORB_SIZE,
    borderRadius: ORB_SIZE / 2,
    borderWidth: 6,
  },
  orb: {
    width: ORB_SIZE,
    height: ORB_SIZE,
    borderRadius: ORB_SIZE / 2,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  spinner: {
    position: 'absolute',
    width: ORB_SIZE * 1.6,
    height: ORB_SIZE * 1.6,
    left: -ORB_SIZE * 0.3,
    top: -ORB_SIZE * 0.3,
  },
  core: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  status: {
    borderRadius: Radius.pill,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.xs,
    maxWidth: '90%',
  },
  center: { textAlign: 'center' },
});
