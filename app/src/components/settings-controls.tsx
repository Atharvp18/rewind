import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

export function Section({ title, children, hint }: { title: string; hint?: string; children: ReactNode }) {
  const { palette } = useA11y();
  return (
    <View style={[styles.section, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      <AppText kind="heading" accessibilityRole="header">
        {title}
      </AppText>
      {hint ? (
        <AppText kind="small" color="textMuted">
          {hint}
        </AppText>
      ) : null}
      {children}
    </View>
  );
}

/** Radio group. The selected option shows ✓, a thick border, and bold text: never color alone. */
export function Choice<T extends string | number>({
  label,
  value,
  options,
  onChange,
  row,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  row?: boolean;
}) {
  const { palette } = useA11y();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={[styles.choices, row && styles.row]}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            accessibilityRole="radio"
            accessibilityLabel={`${label}: ${o.label}`}
            accessibilityState={{ checked: selected }}
            onPress={() => onChange(o.value)}
            style={({ pressed }) => [
              styles.choice,
              row && styles.choiceRow,
              {
                borderColor: selected ? palette.primary : palette.border,
                borderWidth: selected ? 4 : 2,
                backgroundColor: selected ? palette.surfaceAlt : palette.surface,
                opacity: pressed ? 0.8 : 1,
              },
            ]}>
            <AppText kind={selected ? 'label' : 'body'} style={styles.center} accessible={false}>
              {selected ? `✓ ${o.label}` : o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

/** Full-row switch: the whole row is the target and the state is written as On / Off. */
export function Toggle({
  label,
  detail,
  value,
  onChange,
}: {
  label: string;
  detail?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  const { palette } = useA11y();
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityHint={detail}
      accessibilityState={{ checked: value }}
      onPress={() => onChange(!value)}
      style={({ pressed }) => [
        styles.toggle,
        { borderColor: value ? palette.primary : palette.border, borderWidth: value ? 4 : 2, opacity: pressed ? 0.8 : 1 },
      ]}>
      <View style={styles.flex}>
        <AppText kind="label" accessible={false}>
          {label}
        </AppText>
        {detail ? (
          <AppText kind="small" color="textMuted" accessible={false}>
            {detail}
          </AppText>
        ) : null}
      </View>
      <View
        style={[
          styles.pill,
          { backgroundColor: value ? palette.primary : palette.surface, borderColor: value ? palette.primary : palette.border },
        ]}>
        <AppText kind="label" color={value ? 'onPrimary' : 'text'} accessible={false}>
          {value ? 'On' : 'Off'}
        </AppText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { borderWidth: 2, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.md },
  choices: { gap: Spacing.md },
  row: { flexDirection: 'row', flexWrap: 'wrap' },
  choice: {
    minHeight: Target.min,
    borderRadius: Radius.button,
    justifyContent: 'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  choiceRow: { flexGrow: 1, flexBasis: 96 },
  toggle: {
    minHeight: Target.min,
    borderRadius: Radius.button,
    padding: Spacing.md,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.md,
  },
  pill: { borderWidth: 2, borderRadius: Radius.pill, paddingHorizontal: Spacing.lg, paddingVertical: Spacing.xs },
  flex: { flexShrink: 1, flexGrow: 1 },
  center: { textAlign: 'center' },
});
