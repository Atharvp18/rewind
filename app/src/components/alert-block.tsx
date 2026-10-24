import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

export type AlertLevel = 'danger' | 'warning';

const LOOK = {
  danger: { icon: 'danger', fg: 'danger', bg: 'dangerBg', edge: 'dangerEdge' },
  warning: { icon: 'alert', fg: 'warning', bg: 'warningBg', edge: 'warningEdge' },
} as const;

/**
 * The two alert levels. Red (danger): declined, error. Orange (warning):
 * low balance, reroute and add-a-card suggestions. Each level has its own
 * icon and title word as well as color, because red and orange are close in
 * lightness and look alike to many color-blind users (WCAG 1.4.1). Always a
 * solid block with dark-on-tint text, so it reads the same over any camera
 * scene.
 */
export function AlertBlock({
  level,
  title,
  children,
}: {
  level: AlertLevel;
  title: string;
  children?: ReactNode;
}) {
  const { palette } = useA11y();
  const look = LOOK[level];
  return (
    <View
      accessibilityRole="alert"
      style={[
        styles.block,
        {
          backgroundColor: palette[look.bg],
          borderColor: palette[look.edge],
          // A slim accent bar on the leading edge; high contrast outlines the whole block.
          borderWidth: palette.controlBorderWidth,
          borderLeftWidth: 6,
        },
      ]}>
      <View style={styles.titleRow}>
        <Icon name={look.icon} size={28} color={look.fg} strokeWidth={2.5} />
        <AppText kind="label" color={look.fg} style={styles.flex}>
          {title}
        </AppText>
      </View>
      {typeof children === 'string' ? <AppText kind="body">{children}</AppText> : children}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.sm },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  flex: { flexShrink: 1 },
});
