import { Pressable, StyleSheet, View, type PressableProps } from 'react-native';

import { AppText } from '@/components/app-text';
import { Icon, type IconName } from '@/components/icon';
import { Press, Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

type Variant = 'primary' | 'secondary' | 'danger' | 'accent';

export type BigButtonProps = Omit<PressableProps, 'children' | 'style'> & {
  label: string;
  /** Icon before the label. Decorative: the label carries the meaning. */
  icon?: IconName;
  variant?: Variant;
  /** `primary` is 72pt tall for the one main action on a screen; `normal` is 56pt. */
  size?: 'primary' | 'normal';
  fill?: boolean;
  /** Grow to fill the parent's height (equal-height buttons side by side). */
  stretch?: boolean;
};

export function BigButton({
  label,
  icon,
  variant = 'secondary',
  size = 'normal',
  fill = true,
  stretch = false,
  disabled,
  accessibilityLabel,
  ...rest
}: BigButtonProps) {
  const { palette, settings } = useA11y();
  const iconSize = Math.round(22 * Math.min(settings.textScale, 1.5));
  const colors = {
    primary: { bg: palette.primary, fg: 'onPrimary', border: palette.primary },
    accent: { bg: palette.accent, fg: 'onAccent', border: palette.text },
    danger: { bg: palette.dangerBg, fg: 'danger', border: palette.danger },
    // Tonal: a tint of the brand with a brand-colored label, like the transcript pill.
    secondary: { bg: palette.surfaceAlt, fg: 'primary', border: palette.border },
  }[variant] as { bg: string; fg: 'onPrimary' | 'onAccent' | 'danger' | 'primary'; border: string };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      hitSlop={6}
      style={({ pressed }) => [
        styles.base,
        {
          minHeight: size === 'primary' ? Target.primary : Target.min,
          backgroundColor: colors.bg,
          borderColor: colors.border,
          // Soft by default: the label identifies the button (WCAG 1.4.11 needs no outline then).
          // High contrast draws an edge on every control.
          borderWidth: palette.controlBorderWidth,
          opacity: disabled ? Press.disabled : pressed ? Press.pressed : 1,
          alignSelf: fill ? 'stretch' : 'auto',
          flexGrow: stretch ? 1 : 0,
        },
      ]}
      {...rest}>
      <View style={styles.row}>
        {icon ? <Icon name={icon} size={iconSize} color={colors.fg} /> : null}
        <AppText kind="label" color={colors.fg} style={styles.label}>
          {label}
        </AppText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    // Pill: the same shape as the orb, the chips and the transcript.
    borderRadius: Radius.pill,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    justifyContent: 'center',
  },
  // Icon and label always share one row; a long label wraps inside its own text.
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
  },
  label: { textAlign: 'center', flexShrink: 1 },
});
