import { useState, type ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { Elevation, MaxContentWidth, Motion, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useStage } from '@/lib/stage';

/** `#RRGGBB` + opacity → `rgba(...)`. */
export function withOpacity(hex: string, opacity: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${opacity})`;
}

export type PanelTone = 'normal' | 'warning' | 'danger';

const GAP = 14;
const TAIL = 18;

/**
 * The pop-up card (the wireframe's info box). One solid white card over the
 * camera, so text contrast never depends on the scene.
 *
 * `anchored`: the card points at the item the focus corners sit on, above it
 * when there is room, below it otherwise, like a callout. Otherwise it rests
 * just above the voice orb. It sizes to its content and only scrolls when
 * even the whole free area is not enough (large text sizes).
 */
export function InfoPanel({
  title,
  tone = 'normal',
  children,
  label,
  anchored = false,
}: {
  title?: string;
  tone?: PanelTone;
  children: ReactNode;
  /** Optional screen reader label for the card's purpose. */
  label?: string;
  anchored?: boolean;
}) {
  const { palette, reduceMotion } = useA11y();
  const { itemBox, area } = useStage();
  const [cardH, setCardH] = useState(0);
  const [contentH, setContentH] = useState(0);

  const width = Math.min(area.w - Spacing.lg * 2, MaxContentWidth);
  const left = area.x + (area.w - width) / 2;
  const maxH = Math.max(0, area.h);
  const bottomTop = area.y + area.h - Math.min(cardH, maxH);

  // Placement: above the item, else below it, else resting above the orb.
  let top = bottomTop;
  let tail: 'down' | 'up' | null = null;
  if (anchored && itemBox && cardH) {
    const above = itemBox.y - GAP - cardH;
    const below = itemBox.y + itemBox.h + GAP;
    if (above >= area.y) {
      top = above;
      tail = 'down';
    } else if (below + cardH <= area.y + area.h) {
      top = below;
      tail = 'up';
    }
  }
  const tailX = itemBox
    ? Math.max(Radius.card + TAIL, Math.min(width - Radius.card - TAIL, itemBox.x + itemBox.w / 2 - left))
    : width / 2;

  const edge = tone === 'danger' ? palette.dangerEdge : tone === 'warning' ? palette.warningEdge : palette.cardEdge;
  // No outline on a normal card (shadow separates it); warnings and declines get a colored edge.
  const edgeWidth = tone === 'normal' ? palette.controlBorderWidth : 3;

  return (
    <Animated.View
      entering={reduceMotion ? undefined : FadeIn.duration(Motion.panel)}
      accessibilityLabel={label}
      onLayout={(e) => setCardH(e.nativeEvent.layout.height)}
      style={[
        styles.card,
        Elevation.floating,
        {
          width,
          left,
          top,
          maxHeight: maxH,
          backgroundColor: palette.surface,
          borderColor: edge,
          borderWidth: edgeWidth,
          // Hidden for the one frame before its height is known, so it never jumps.
          opacity: cardH ? 1 : 0,
        },
      ]}>
      {tail ? (
        <View
          pointerEvents="none"
          style={[
            styles.tail,
            {
              left: tailX - TAIL / 2,
              backgroundColor: palette.surface,
              borderColor: edge,
              borderRightWidth: edgeWidth,
              borderBottomWidth: edgeWidth,
              ...(tail === 'down'
                ? { bottom: -TAIL / 2 - edgeWidth / 2, transform: [{ rotate: '45deg' }] }
                : { top: -TAIL / 2 - edgeWidth / 2, transform: [{ rotate: '-135deg' }] }),
            },
          ]}
        />
      ) : null}
      <ScrollView
        bounces={false}
        scrollEnabled={contentH > maxH - edgeWidth * 2}
        onContentSizeChange={(_, h) => setContentH(h)}
        contentContainerStyle={styles.body}>
        {title ? (
          <AppText kind="heading" accessibilityRole="header">
            {title}
          </AppText>
        ) : null}
        {children}
      </ScrollView>
    </Animated.View>
  );
}

/** Body text inside the pop-up. */
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
  card: { position: 'absolute', borderRadius: Radius.card + 4 },
  tail: { position: 'absolute', width: TAIL, height: TAIL, zIndex: 1 },
  body: { padding: Spacing.lg, gap: Spacing.sm },
});
