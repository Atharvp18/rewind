import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, SlideInDown } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { Elevation, Motion, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

/** `#RRGGBB` + opacity → `rgba(...)`. */
export function withOpacity(hex: string, opacity: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${opacity})`;
}

/**
 * The see-through information panel (wireframe frame 3). Semi-transparent so a
 * low-vision user can keep the item framed while reading and listening. Opacity
 * is a setting (0.75 to 0.95); at 0.75 white text still measures 6.9:1 over a
 * pure white scene behind it (tech spec 1.9).
 */
export function InfoPanel({
  title,
  tone = 'normal',
  children,
  label,
}: {
  title?: string;
  tone?: 'normal' | 'danger';
  children: ReactNode;
  /** Optional screen reader label for the whole panel's purpose. */
  label?: string;
}) {
  const { palette, settings, reduceMotion, themeName } = useA11y();
  const danger = tone === 'danger';
  return (
    <Animated.View
      entering={reduceMotion ? FadeIn.duration(0) : SlideInDown.duration(Motion.panel)}
      accessibilityLabel={label}
      style={[
        styles.panel,
        Elevation.floating,
        {
          backgroundColor: withOpacity(palette.panel, themeName === 'highContrast' ? 1 : settings.panelOpacity),
          borderColor: danger ? palette.danger : themeName === 'highContrast' ? palette.onPanel : 'transparent',
          borderWidth: danger ? 4 : themeName === 'highContrast' ? 2 : 0,
        },
      ]}>
      <ScrollView contentContainerStyle={styles.body} bounces={false}>
        {title ? (
          <View style={styles.titleRow}>
            {danger ? (
              <View style={[styles.dangerChip, { backgroundColor: palette.danger }]}>
                <AppText kind="label" color="onPanel" accessible={false}>
                  ⚠
                </AppText>
              </View>
            ) : null}
            <AppText kind="title" color="onPanel" accessibilityRole="header" style={styles.flex}>
              {title}
            </AppText>
          </View>
        ) : null}
        {children}
      </ScrollView>
    </Animated.View>
  );
}

/** Body text inside a panel, always in the panel's text color. */
export function PanelText({ children, muted, kind = 'body' }: { children: ReactNode; muted?: boolean; kind?: 'body' | 'label' | 'heading' | 'display' | 'small' }) {
  return (
    <AppText kind={kind} color={muted ? 'onPanelMuted' : 'onPanel'}>
      {children}
    </AppText>
  );
}

const styles = StyleSheet.create({
  panel: { borderRadius: Radius.card + 8, overflow: 'hidden', flexShrink: 1 },
  body: { padding: Spacing.xl, gap: Spacing.md },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  dangerChip: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  flex: { flexShrink: 1 },
});
