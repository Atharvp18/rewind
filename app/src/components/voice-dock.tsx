import { router, type Href } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from '@/components/app-text';
import { Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useAgent, type Phase } from '@/state/agent';

export type DockLink = { label: string; icon: string; href: Href; hint?: string };

const STATUS: Record<Phase, string> = {
  idle: 'Tap to talk · hold to speak',
  listening: 'Listening… tap to send',
  capturing: 'Taking photo…',
  awaiting_scan: 'Looking…',
  speaking_result: 'Speaking… tap to interrupt',
  speaking_error: 'Speaking… tap to interrupt',
  awaiting_confirm: 'Tap and say yes or skip',
  submitting: 'Working…',
  interrupted: 'Listening…',
};

/**
 * The half-moon drawer at the bottom of every screen (business spec 6.5 A).
 * The round Talk button is always in the same place: center, bottom.
 * State is written under the button; never shown by color alone.
 */
export function VoiceDock({ left, right }: { left?: DockLink; right?: DockLink }) {
  const { palette, themeName } = useA11y();
  const { state, talkTap, talkHoldStart, talkHoldEnd } = useAgent();
  const insets = useSafeAreaInsets();
  const listening = state.phase === 'listening';

  return (
    <View
      style={[
        styles.dock,
        {
          backgroundColor: palette.dock,
          borderColor: palette.border,
          borderTopWidth: themeName === 'standard' ? 0 : 2,
          paddingBottom: Math.max(insets.bottom, Spacing.lg),
        },
      ]}>
      <View style={styles.row}>
        <DockSide link={left} />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={listening ? 'Stop and send' : 'Talk'}
          accessibilityHint="Tap to talk to Rewind, or hold while you speak."
          accessibilityState={{ busy: state.phase === 'awaiting_scan' || state.phase === 'submitting' }}
          onPress={talkTap}
          onLongPress={talkHoldStart}
          onPressOut={talkHoldEnd}
          delayLongPress={350}
          style={({ pressed }) => [
            styles.talk,
            {
              backgroundColor: palette.accent,
              borderColor: listening ? palette.onDock : palette.onAccent,
              borderWidth: listening ? 6 : 3,
              transform: [{ scale: pressed ? 0.96 : 1 }],
            },
          ]}>
          <AppText kind="heading" color="onAccent" accessible={false} style={styles.talkGlyph}>
            {listening ? '■' : '🎙'}
          </AppText>
          <AppText kind="label" color="onAccent" accessible={false} style={styles.talkLabel}>
            {listening ? 'Send' : 'Talk'}
          </AppText>
        </Pressable>
        <DockSide link={right} />
      </View>
      <AppText
        kind="small"
        color="onDock"
        style={styles.status}
        accessibilityLiveRegion="polite"
        accessibilityLabel={`Status: ${STATUS[state.phase]}`}>
        {STATUS[state.phase]}
      </AppText>
    </View>
  );
}

function DockSide({ link }: { link?: DockLink }) {
  const { palette } = useA11y();
  if (!link) return <View style={styles.side} />;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={link.label}
      accessibilityHint={link.hint}
      onPress={() => router.push(link.href)}
      hitSlop={6}
      style={({ pressed }) => [
        styles.side,
        styles.sideBtn,
        { borderColor: palette.onDock, opacity: pressed ? 0.75 : 1 },
      ]}>
      <AppText kind="heading" color="onDock" accessible={false} style={styles.sideGlyph}>
        {link.icon}
      </AppText>
      <AppText kind="small" color="onDock" accessible={false} style={styles.sideLabel}>
        {link.label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  dock: {
    borderTopLeftRadius: 180,
    borderTopRightRadius: 180,
    paddingTop: Spacing.xl,
    paddingHorizontal: Spacing.lg,
    gap: Spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.md,
  },
  talk: {
    width: Target.talk,
    height: Target.talk,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Glyph and label inside the fixed circle stay a fixed size so they never clip;
  // the readable status line below scales with the text setting instead.
  talkGlyph: { fontSize: 30, lineHeight: 36 },
  talkLabel: { fontSize: 20, lineHeight: 24 },
  side: { flex: 1, minHeight: Target.min },
  sideBtn: {
    borderWidth: 2,
    borderRadius: Radius.button,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.xs,
  },
  sideGlyph: { fontSize: 24, lineHeight: 30 },
  sideLabel: { textAlign: 'center' },
  status: { textAlign: 'center' },
});
