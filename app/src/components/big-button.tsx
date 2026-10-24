import { Pressable, StyleSheet, View, type PressableProps } from 'react-native';

import { AppText } from '@/components/app-text';
import { Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

type Variant = 'primary' | 'secondary' | 'danger' | 'accent';

export type BigButtonProps = Omit<PressableProps, 'children' | 'style'> & {
  label: string;
  /** A short glyph shown before the label. Decorative: the label carries the meaning. */
  icon?: string;
  variant?: Variant;
  /** `primary` is 72pt tall for the one main action on a screen; `normal` is 56pt. */
  size?: 'primary' | 'normal';
  fill?: boolean;
};

export function BigButton({
  label,
  icon,
  variant = 'secondary',
  size = 'normal',
  fill = true,
  disabled,
  accessibilityLabel,
  ...rest
}: BigButtonProps) {
  const { palette } = useA11y();
  const colors = {
    primary: { bg: palette.primary, fg: 'onPrimary', border: palette.primary },
    accent: { bg: palette.accent, fg: 'onAccent', border: palette.text },
    danger: { bg: palette.surface, fg: 'danger', border: palette.danger },
    secondary: { bg: palette.surface, fg: 'text', border: palette.border },
  }[variant] as { bg: string; fg: 'onPrimary' | 'onAccent' | 'danger' | 'text'; border: string };

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
          // Secondary buttons always draw an edge (1.4.11 needs 3:1 against the background).
          borderWidth: variant === 'primary' ? Math.max(palette.controlBorderWidth, 0) : 2,
          opacity: disabled ? 0.45 : pressed ? 0.8 : 1,
          alignSelf: fill ? 'stretch' : 'auto',
        },
      ]}
      {...rest}>
      <View style={styles.row}>
        {icon ? (
          <AppText kind="label" color={colors.fg} importantForAccessibility="no" accessible={false}>
            {icon}
          </AppText>
        ) : null}
        <AppText kind="label" color={colors.fg} style={styles.label}>
          {label}
        </AppText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: Radius.button,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    justifyContent: 'center',
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
  },
  label: { textAlign: 'center', flexShrink: 1 },
});
