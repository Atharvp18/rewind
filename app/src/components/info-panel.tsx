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

export type PanelTone = 'normal' | 'warning' | 'danger';

/**
 * Frame 3: the see-through window (the wireframe's rectangle).
 *
 * The window itself is clear, so the shopper keeps seeing and framing the
 * product, like Google Lens or Apple Live Text. Its two-tone edge (one light,
 * one dark stroke) is visible on any shelf, and turns orange or red for the
 * two alert levels. Information sits on a solid card at the bottom of the
 * window, so text contrast never depends on what the camera sees.
 *
 * The clear area is also where the "2D visual overlay on the camera preview"
 * stretch item (business spec §5) would pin labels onto the text the camera
 * reads, so it is kept free of content.
 */
export function InfoPanel({
  title,
  tone = 'normal',
  children,
  label,
}: {
  title?: string;
  tone?: PanelTone;
  children: ReactNode;
  /** Optional screen reader label for the panel's purpose. */
  label?: string;
}) {
  const { palette, settings, reduceMotion } = useA11y();
  const inner = tone === 'danger' ? palette.dangerEdge : tone === 'warning' ? palette.warningEdge : palette.frameInner;

  return (
    <Animated.View
      entering={reduceMotion ? FadeIn.duration(0) : FadeIn.duration(Motion.panel)}
      pointerEvents="box-none"
      style={[styles.window, { borderColor: palette.frameOuter }]}>
      <View
        pointerEvents="box-none"
        style={[
          styles.windowInner,
          {
            borderColor: inner,
            backgroundColor: settings.cameraDim ? withOpacity('#000000', settings.cameraDim) : 'transparent',
          },
        ]}>
        {/* Clear viewfinder: the product stays visible here. */}
        <View style={styles.clear} pointerEvents="none" />

        <Animated.View
          entering={reduceMotion ? undefined : SlideInDown.duration(Motion.panel)}
          accessibilityLabel={label}
          style={[styles.card, Elevation.floating, { backgroundColor: palette.surface, borderColor: palette.cardEdge }]}>
          <ScrollView contentContainerStyle={styles.body} bounces={false}>
            {title ? (
              <AppText kind="title" accessibilityRole="header">
                {title}
              </AppText>
            ) : null}
            {children}
          </ScrollView>
        </Animated.View>
      </View>
    </Animated.View>
  );
}

/** Body text inside the info card. */
export function PanelText({
  children,
  muted,
  kind = 'body',
}: {
  children: ReactNode;
  muted?: boolean;
  kind?: 'body' | 'label' | 'heading' | 'display' | 'small';
}) {
  return (
    <AppText kind={kind} color={muted ? 'textMuted' : 'text'}>
      {children}
    </AppText>
  );
}

const styles = StyleSheet.create({
  // Outer stroke + inner stroke of the opposite lightness: one always contrasts with the scene.
  window: { flex: 1, borderWidth: 2, borderRadius: Radius.card + 10 },
  windowInner: {
    flex: 1,
    borderWidth: 4,
    borderRadius: Radius.card + 8,
    padding: Spacing.sm,
    justifyContent: 'flex-end',
  },
  clear: { flexGrow: 1, minHeight: 96 },
  card: { borderWidth: 2, borderRadius: Radius.card, maxHeight: '78%', overflow: 'hidden' },
  body: { padding: Spacing.xl, gap: Spacing.md },
});
