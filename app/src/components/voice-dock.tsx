import { LinearGradient } from 'expo-linear-gradient';
import { router, type Href } from 'expo-router';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from '@/components/app-text';
import { Icon, type IconName } from '@/components/icon';
import { Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useAgent, type Phase } from '@/state/agent';

export type DockAction = {
  label: string;
  icon: IconName;
  hint?: string;
  href?: Href;
  onPress?: () => void;
  disabled?: boolean;
};

const STATUS: Record<Phase, string> = {
  idle: 'Tap to talk · hold to speak',
  listening: 'Listening… tap to send',
  capturing: 'Taking photo…',
  awaiting_scan: 'Looking…',
  speaking_result: 'Speaking… tap to interrupt',
  speaking_error: 'Speaking… tap to interrupt',
  awaiting_confirm: 'Tap and say yes or no',
  submitting: 'Working…',
  interrupted: 'Listening…',
};

/**
 * Half-circle dock (wireframe, business spec 6.5 A): brand gradient, accent
 * Talk button with a dark ring in the center, within thumb reach. The Talk
 * button starts and stops the voice agent. State is written under it, never
 * shown by color alone.
 */
export function VoiceDock({ left, right }: { left?: DockAction; right?: DockAction }) {
  const { palette } = useA11y();
  const { state, talkTap, talkHoldStart, talkHoldEnd } = useAgent();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const listening = state.phase === 'listening';

  return (
    <LinearGradient
      colors={[palette.dockTop, palette.dockBottom]}
      style={[
        styles.dock,
        {
          borderTopLeftRadius: width / 2,
          borderTopRightRadius: width / 2,
          minHeight: width * 0.5,
          paddingBottom: Math.max(insets.bottom, Spacing.lg),
          // Edge line along the curve: the light top of the gradient alone is 1.11:1 on a white scene.
          borderColor: palette.dockEdge,
          borderWidth: 3,
          borderBottomWidth: 0,
        },
      ]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={listening ? 'Stop and send' : 'Talk to Rewind'}
        accessibilityHint="Tap to talk, or hold while you speak. Tap while Rewind is speaking to interrupt."
        accessibilityState={{ busy: state.phase === 'awaiting_scan' || state.phase === 'submitting' }}
        onPress={talkTap}
        onLongPress={talkHoldStart}
        onPressOut={talkHoldEnd}
        delayLongPress={350}
        style={({ pressed }) => [
          styles.talkRing,
          {
            borderColor: listening ? palette.onDock : palette.talkRing,
            borderWidth: listening ? 6 : 4,
            transform: [{ scale: pressed ? 0.96 : 1 }],
          },
        ]}>
        <LinearGradient colors={[palette.talkTop, palette.talkBottom]} style={styles.talk}>
          <Icon name={listening ? 'stop' : 'mic'} size={34} color="onTalk" strokeWidth={2.5} />
          <AppText color="onTalk" accessible={false} style={styles.talkLabel}>
            {listening ? 'Send' : 'Talk'}
          </AppText>
        </LinearGradient>
      </Pressable>

      <AppText
        kind="small"
        color="onDock"
        style={styles.status}
        accessibilityLiveRegion="polite"
        accessibilityLabel={`Status: ${STATUS[state.phase]}`}>
        {STATUS[state.phase]}
      </AppText>

      <View style={styles.sides}>
        <DockButton action={left} />
        <DockButton action={right} />
      </View>
    </LinearGradient>
  );
}

function DockButton({ action }: { action?: DockAction }) {
  const { palette } = useA11y();
  if (!action) return <View style={styles.side} />;
  const onPress = action.onPress ?? (() => action.href && router.push(action.href));
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={action.label}
      accessibilityHint={action.hint}
      accessibilityState={{ disabled: !!action.disabled }}
      disabled={action.disabled}
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => [
        styles.side,
        styles.sideBtn,
        { borderColor: palette.onDock, opacity: action.disabled ? 0.5 : pressed ? 0.75 : 1 },
      ]}>
      <Icon name={action.icon} size={26} color="onDock" />
      <AppText kind="label" color="onDock" accessible={false} style={styles.center}>
        {action.label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  dock: {
    alignItems: 'center',
    paddingTop: Spacing.xxl,
    paddingHorizontal: Spacing.lg,
    gap: Spacing.sm,
  },
  talkRing: {
    width: Target.talk,
    height: Target.talk,
    borderRadius: Radius.pill,
    overflow: 'hidden',
  },
  talk: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  // Glyph and label inside the fixed circle stay fixed so they never clip;
  // the status line below scales with the text setting instead.
  talkLabel: { fontSize: 20, lineHeight: 24, fontWeight: '800' },
  status: { textAlign: 'center' },
  sides: { flexDirection: 'row', gap: Spacing.md, alignSelf: 'stretch' },
  side: { flex: 1, minHeight: Target.min },
  sideBtn: {
    borderWidth: 2,
    borderRadius: Radius.button,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.xs,
  },
  center: { textAlign: 'center' },
});
