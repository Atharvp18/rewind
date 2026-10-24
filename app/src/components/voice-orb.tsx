import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { PanResponder, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
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
import { responsiveFor } from '@/lib/responsive';
import { useAgent, type Phase } from '@/state/agent';

/**
 * Orb diameter: 12% of the screen height (96–112 pt on phones), times the UI
 * scale on tablets (up to 140 pt). Uses the shorter side in landscape.
 */
export function orbSizeFor(width: number, height: number): number {
  // Height is the long side in portrait and the short side in landscape: right in both.
  return Math.round(Math.min(112, Math.max(96, height * 0.12)) * responsiveFor(width, height).ui);
}

/**
 * Lift above the bottom safe area so the orb sits in the one-handed thumb zone
 * (its center about 20–23% up the screen on every phone): 16–48 pt, growing with height.
 */
function thumbLiftFor(screenHeight: number): number {
  // Small phones need less lift: their bottom edge is already in easy reach.
  return Math.round(Math.min(48, Math.max(16, (screenHeight - 600) * 0.1 + 16)));
}

// Measured height of the orb block (orb + status + lift). The dome and the
// card's free area are sized from it, so the orb always sits inside the dome
// at every screen size and text size.
let blockHeight = 0;
const blockListeners = new Set<() => void>();
function setBlockHeight(h: number) {
  if (Math.abs(h - blockHeight) < 1) return;
  blockHeight = h;
  blockListeners.forEach((l) => l());
}
function subscribeBlock(l: () => void) {
  blockListeners.add(l);
  return () => {
    blockListeners.delete(l);
  };
}

/** Strength of the edge shared by the dome and the orb ring (3.2:1 on the brightest scene). */
const EDGE_ALPHA = 0.85;

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
  awaiting_confirm: 'Say yes or no, or tap a button',
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
/**
 * The dome behind the orb (business spec 6.5 A half-moon): a big circle whose
 * top shows above the bottom edge, filled with a fade from clear to mint and a
 * thin edge. Rendered as its own background layer, *behind* pop-ups, so it
 * never draws over a card. Decorative.
 */
/** Visible height of the dome above the bottom edge. Pop-ups stop above this line. */
export function useDomeHeight(): number {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const block = useSyncExternalStore(subscribeBlock, () => blockHeight);
  // The measured orb block plus a little headroom above the orb; a formula until first layout.
  return block ? block + orbSizeFor(width, height) * 0.18 : Math.min(260, height * 0.28) + insets.bottom;
}

export function OrbGlow() {
  const { palette } = useA11y();
  const { width } = useWindowDimensions();
  const glowHeight = useDomeHeight();
  // Capped on wide screens (tablets) so it stays a dome, not a flat band.
  const domeD = Math.max(Math.min(width * 1.35, 900), glowHeight * 2);
  const f = glowHeight / domeD;
  return (
    <View pointerEvents="none" style={styles.glowLayer}>
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
            borderColor: palette.controlBorderWidth ? palette.dockEdge : withOpacity(palette.dockEdge, EDGE_ALPHA),
          },
        ]}>
        <LinearGradient
          colors={[
            // Clear → deep teal → mint: a light mint fading over a dark scene reads as gray,
            // so the middle of the fade is the brand teal.
            withOpacity(palette.dockEdge, 0),
            withOpacity(palette.dockEdge, 0.55),
            withOpacity(palette.dockBottom, 0.95),
            withOpacity(palette.dockBottom, 0.95),
          ]}
          locations={[0, f * 0.4, f, 1]}
          style={StyleSheet.absoluteFill}
        />
      </View>

    </View>
  );
}

/**
 * The pull-up handle under the orb (business spec 6.6): swipe up from the bottom edge, or tap,
 * to open the purchase history. A grabber bar, a chevron, and the word, so it is never
 * just a gesture: the tap and the label cover screen readers and switch users.
 */
function HistoryHandle() {
  const { state, showView } = useAgent();
  const open = state.view === 'history';
  const toggle = () => showView(open ? 'camera' : 'history');
  const pan = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dy) > 8 && Math.abs(g.dy) > Math.abs(g.dx),
        onPanResponderRelease: (_, g) => {
          if (g.dy < -30) showView('history');
          else if (g.dy > 30) showView('camera');
        },
      }),
    [showView],
  );
  return (
    <Pressable
      {...pan.panHandlers}
      onPress={toggle}
      hitSlop={{ top: 8, bottom: 4, left: 40, right: 40 }}
      accessibilityRole="button"
      accessibilityLabel={open ? 'Close purchase history' : 'Open purchase history'}
      accessibilityHint="Swipe up or double tap to see your past purchases and invoices"
      style={styles.handle}>
      <Icon name={open ? 'chevronDown' : 'chevronUp'} size={18} color="onDock" />
      <AppText kind="small" color="onDock" accessible={false} style={styles.handleText}>
        History
      </AppText>
    </Pressable>
  );
}

export function VoiceOrb({ hint, historyEnabled = false }: { hint?: string | null; historyEnabled?: boolean }) {
  const { palette, reduceMotion } = useA11y();
  const { state, talkTap, talkHoldStart, talkHoldEnd } = useAgent();
  const insets = useSafeAreaInsets();
  const { width: screenW, height } = useWindowDimensions();
  const orb = orbSizeFor(screenW, height);
  const size = { width: orb, height: orb, borderRadius: orb / 2 };
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

  return (
    <View
      style={[styles.root, { paddingBottom: insets.bottom + thumbLiftFor(height) }]}
      pointerEvents="box-none"
      onLayout={(e) => setBlockHeight(e.nativeEvent.layout.height)}>
      <View style={[styles.orbWrap, { width: orb * 1.8, height: orb * 1.12 }]} pointerEvents="box-none">
        {!reduceMotion && mode === 'speaking' ? (
          <Animated.View pointerEvents="none" style={[styles.ripple, size, { borderColor: palette.accent }, rippleStyle]} />
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
              size,
              {
                // Light theme: the dome's edge shade at the dome's strength (see OrbGlow).
                // Dark and high contrast: a solid dark ring (see Palette.talkRing).
                borderColor: palette.talkRing === palette.dockEdge ? withOpacity(palette.talkRing, EDGE_ALPHA) : palette.talkRing,
                borderWidth: palette.controlBorderWidth ? 3 : 2,
              },
            ]}>
            <Animated.View
              style={[
                styles.spinner,
                { width: orb * 1.6, height: orb * 1.6, left: -orb * 0.3, top: -orb * 0.3 },
                spinStyle,
              ]}>
              <LinearGradient
                // The flowing gradient: teal, mint, deep teal (unchanged).
                colors={[palette.talkTop, palette.accent, palette.talkBottom, palette.talkTop]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={StyleSheet.absoluteFill}
              />
            </Animated.View>
            {/* One circle: the icon sits straight on the gradient, large, with its own thin outline. */}
            <Icon
              name={listening ? 'stop' : 'mic'}
              size={Math.round(orb * 0.46)}
              color="onTalk"
              outline={palette.talkIconOutline}
              strokeWidth={2.75}
            />
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
      {historyEnabled ? <HistoryHandle /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { alignItems: 'center', gap: Spacing.md, paddingTop: Spacing.md },
  glowLayer: { position: 'absolute', left: 0, right: 0, bottom: 0, top: 0 },
  dome: { position: 'absolute', overflow: 'hidden' },
  orbWrap: { alignItems: 'center', justifyContent: 'center' },
  ripple: { position: 'absolute', borderWidth: 6 },
  orb: { overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  spinner: { position: 'absolute' },
  status: {
    borderRadius: Radius.pill,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.xs,
    maxWidth: '90%',
  },
  center: { textAlign: 'center' },
  // Drawn over the dome's bottom edge, outside the layout flow: the dome keeps its old height.
  handle: { position: 'absolute', bottom: 4, flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, minHeight: 28 },
  handleText: { fontWeight: '700' },
});
