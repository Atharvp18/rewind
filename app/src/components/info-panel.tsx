import { useEffect, useState, type ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { CaptionLayer, LAYER_OVERLAP } from '@/components/transcript-pill';
import { Elevation, MaxContentWidth, Motion, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useStage } from '@/lib/stage';

/** `#RRGGBB` + opacity → `rgba(...)`. */
export function withOpacity(hex: string, opacity: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${opacity})`;
}

export type PanelTone = 'normal' | 'warning' | 'danger';

/**
 * The main widget (wireframe frame 3): two layers stacked as one.
 *   top layer, mint:  what Rewind is saying (the caption)
 *   under it, white:  the information card (item, cart, checkout, onboarding)
 *
 * The stack is centered in the free area between the cart/profile row and
 * the dome, with a standard gap to both, and never overlaps the dome. It
 * sizes to its content; the card scrolls only if the whole stack cannot fit
 * (very large text).
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
  /** Optional screen reader label for the card's purpose. */
  label?: string;
}) {
  const { palette, reduceMotion } = useA11y();
  const { area, reportCard } = useStage();
  const [stackH, setStackH] = useState(0);
  const [captionH, setCaptionH] = useState(0);
  const [contentH, setContentH] = useState(0);

  const width = Math.min(area.w - Spacing.lg * 2, MaxContentWidth);
  const left = area.x + (area.w - width) / 2;
  const top = area.y + Math.max(0, (area.h - stackH) / 2);
  // The card gets whatever the caption leaves; it tucks LAYER_OVERLAP under the caption.
  const cardMaxH = Math.max(0, area.h - captionH + (captionH ? LAYER_OVERLAP : 0));

  // Tell the screen where the widget is, so the focus corners never hide behind it.
  useEffect(() => {
    if (stackH) reportCard?.({ x: left, y: top, w: width, h: stackH });
  }, [reportCard, left, top, width, stackH]);
  useEffect(() => () => reportCard?.(null), [reportCard]);

  const edge = tone === 'danger' ? palette.dangerEdge : tone === 'warning' ? palette.warningEdge : palette.cardEdge;
  const edgeWidth = tone === 'normal' ? palette.controlBorderWidth : 3;

  return (
    <Animated.View
      entering={reduceMotion ? undefined : FadeIn.duration(Motion.panel)}
      onLayout={(e) => setStackH(e.nativeEvent.layout.height)}
      style={[
        styles.stack,
        // Hidden for the one frame before its height is known, so it never jumps.
        { width, left, top, maxHeight: area.h, opacity: stackH ? 1 : 0 },
      ]}>
      <View style={styles.captionLayer} onLayout={(e) => setCaptionH(e.nativeEvent.layout.height)}>
        <CaptionLayer />
      </View>

      <View
        accessibilityLabel={label}
        style={[
          styles.card,
          Elevation.floating,
          {
            marginTop: captionH ? -LAYER_OVERLAP : 0,
            maxHeight: cardMaxH,
            backgroundColor: palette.surface,
            borderColor: edge,
            borderWidth: edgeWidth,
          },
        ]}>
        <ScrollView
          bounces={false}
          scrollEnabled={contentH > cardMaxH - edgeWidth * 2}
          onContentSizeChange={(_, h) => setContentH(h)}
          // Extra top padding so the first line clears the caption layer's edge.
          contentContainerStyle={[styles.body, captionH ? { paddingTop: Spacing.lg + LAYER_OVERLAP } : null]}>
          {title ? (
            <AppText kind="heading" accessibilityRole="header">
              {title}
            </AppText>
          ) : null}
          {children}
        </ScrollView>
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
  kind?: 'body' | 'label' | 'heading' | 'display' | 'small' | 'title';
}) {
  return (
    <AppText kind={kind} color={muted ? 'textMuted' : 'text'}>
      {children}
    </AppText>
  );
}

const styles = StyleSheet.create({
  stack: { position: 'absolute' },
  // The caption sits above the card (the card's top edge tucks under it).
  captionLayer: { zIndex: 2, ...Elevation.floating },
  card: { zIndex: 1, borderRadius: Radius.card + 4, overflow: 'hidden' },
  body: { padding: Spacing.lg, gap: Spacing.sm },
});
