import { Children, Fragment, isValidElement, useEffect, useState, type ReactElement, type ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { ScrollCue, useScrollCue } from '@/components/scroll-cue';
import { Elevation, Layout, MaxContentWidth, Motion, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { useStage } from '@/lib/stage';

export { withOpacity } from '@/lib/color';

export type PanelTone = 'normal' | 'warning' | 'danger';

/**
 * Wrap a card's buttons in this: they are pinned to the card's bottom edge and
 * always visible. Only the content above them scrolls, and only when it can't
 * fit (small phones, large text). The primary action is never hidden.
 */
export function PanelActions({ children }: { children: ReactNode }) {
  return <View style={styles.actions}>{children}</View>;
}

/** Split children into content and the PanelActions footer (looks inside fragments too). */
function splitActions(children: ReactNode): { content: ReactNode[]; actions: ReactElement[] } {
  const content: ReactNode[] = [];
  const actions: ReactElement[] = [];
  const walk = (nodes: ReactNode) =>
    Children.toArray(nodes).forEach((n) => {
      if (isValidElement(n) && n.type === PanelActions) actions.push(n);
      else if (isValidElement<{ children?: ReactNode }>(n) && n.type === Fragment) walk(n.props.children);
      else content.push(n);
    });
  walk(children);
  return { content, actions };
}

/**
 * The answer card (wireframe frame 3's info box). One solid white card,
 * attached 12 pt under the transcript; the product stays visible in the
 * camera view between the card and the dome.
 * It sizes to its content and only scrolls when even the whole free area
 * is not enough (very large text).
 */
export function InfoPanel({
  title,
  tone = 'normal',
  children,
  label,
  onClose,
}: {
  title?: string;
  tone?: PanelTone;
  children: ReactNode;
  /** Optional screen reader label for the card's purpose. */
  label?: string;
  /** Adds a fixed header with the title and a round ✕ (same as the profile pop-up). */
  onClose?: () => void;
}) {
  const { palette, reduceMotion } = useA11y();
  const { area, reportCard } = useStage();
  const [stackH, setStackH] = useState(0);
  const cue = useScrollCue();
  const { content, actions } = splitActions(children);

  const width = Math.min(area.w - Layout.margin * 2, MaxContentWidth);
  const left = area.x + (area.w - width) / 2;
  // Attached right under the transcript (12 pt, Layout.stack); the camera view
  // below it, down to the dome, stays free for the product.
  const top = area.y;
  const cardMaxH = Math.max(0, area.h);

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
      // The layout animation owns this view's opacity, so the
      // hide-until-measured opacity lives on the inner card (Reanimated rule).
      style={[styles.stack, { width, left, top, maxHeight: area.h }]}>
      <View
        accessibilityLabel={label}
        style={[
          styles.card,
          Elevation.floating,
          {
            // Hidden for the one frame before its height is known, so it never jumps.
            opacity: stackH ? 1 : 0,
            maxHeight: cardMaxH,
            backgroundColor: palette.surface,
            borderColor: edge,
            borderWidth: edgeWidth,
          },
        ]}>
        {onClose ? (
          // Fixed header: the title stays put and the ✕ is always reachable.
          <View style={styles.header}>
            <AppText kind="heading" accessibilityRole="header" style={styles.headerTitle}>
              {title}
            </AppText>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Close ${title ?? 'panel'}`}
              onPress={onClose}
              hitSlop={6}
              style={({ pressed }) => [styles.close, { backgroundColor: palette.surfaceAlt, opacity: pressed ? 0.8 : 1 }]}>
              <Icon name="close" size={24} />
            </Pressable>
          </View>
        ) : null}
        <View style={styles.scrollWrap}>
          <ScrollView
            bounces={false}
            scrollEnabled={cue.overflowing}
            {...cue.scrollProps}
            contentContainerStyle={styles.body}>
            {title && !onClose ? (
              <AppText kind="heading" accessibilityRole="header">
                {title}
              </AppText>
            ) : null}
            {content}
          </ScrollView>
          <ScrollCue visible={cue.more} bg={palette.surface} />
        </View>
        {actions.length ? (
          <View style={styles.footer}>
            {actions}
          </View>
        ) : null}
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
  card: { borderRadius: Radius.card + 4, overflow: 'hidden' },
  body: { padding: Spacing.lg, gap: Spacing.sm },
  scrollWrap: { flexShrink: 1, minHeight: 0 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingTop: Spacing.lg,
    paddingLeft: Spacing.lg,
    paddingRight: Spacing.md,
  },
  headerTitle: { flex: 1 },
  close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  // Pinned footer: same side padding as the body, so buttons line up with the text.
  footer: { paddingHorizontal: Spacing.lg, paddingBottom: Spacing.lg },
  actions: { gap: Spacing.md },
});
