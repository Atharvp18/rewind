import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AccessibilityButton } from '@/components/accessibility-button';
import { AppText } from '@/components/app-text';
import { CaptionBar } from '@/components/caption-bar';
import { HealthBanner } from '@/components/health-banner';
import { VoiceDock, type DockLink } from '@/components/voice-dock';
import { MaxContentWidth, Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

type Props = {
  title: string;
  back?: boolean;
  children: ReactNode;
  /** The one primary action, rendered full width directly above the dock. */
  action?: ReactNode;
  dockLeft?: DockLink;
  dockRight?: DockLink;
  /** Set false for the camera screen, which manages its own layout. */
  scroll?: boolean;
};

/**
 * Persistent frame (tech spec 1.8). Three things never move:
 * the accessibility button (top right), the caption bar (under the header),
 * and the Talk dock (bottom).
 */
export function Screen({ title, back = true, children, action, dockLeft, dockRight, scroll = true }: Props) {
  const { palette } = useA11y();

  const body = (
    <View style={styles.body}>
      <HealthBanner />
      <CaptionBar />
      {children}
    </View>
  );

  return (
    <View style={[styles.root, { backgroundColor: palette.bg }]}>
      <SafeAreaView edges={['top', 'left', 'right']} style={styles.root}>
        <View style={styles.header}>
          {back && router.canGoBack() ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Back"
              onPress={() => router.back()}
              hitSlop={8}
              style={({ pressed }) => [
                styles.back,
                { borderColor: palette.border, backgroundColor: palette.surface, opacity: pressed ? 0.8 : 1 },
              ]}>
              <AppText kind="label">‹ Back</AppText>
            </Pressable>
          ) : null}
          <AppText kind="title" accessibilityRole="header" style={styles.title}>
            {title}
          </AppText>
          <AccessibilityButton />
        </View>

        {scroll ? (
          <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
            {body}
          </ScrollView>
        ) : (
          <View style={[styles.scroll, styles.fill]}>{body}</View>
        )}

        {action ? <View style={styles.action}>{action}</View> : null}
      </SafeAreaView>
      <VoiceDock left={dockLeft} right={dockRight} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  fill: { flex: 1 },
  header: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  back: {
    minHeight: Target.min,
    minWidth: Target.min,
    paddingHorizontal: Spacing.lg,
    borderWidth: 2,
    borderRadius: Radius.button,
    justifyContent: 'center',
  },
  title: { flex: 1, minWidth: 120 },
  scroll: {
    paddingHorizontal: Spacing.lg,
    paddingBottom: Spacing.xl,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  body: { flex: 1, gap: Spacing.lg },
  action: {
    paddingHorizontal: Spacing.lg,
    paddingBottom: Spacing.md,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    gap: Spacing.md,
  },
});
