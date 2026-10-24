import { useFocusEffect } from 'expo-router';
import { useCallback, type ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { Screen } from '@/components/screen';
import { Radius, Spacing, Target } from '@/constants/theme';
import { TEXT_SCALES, useA11y, type SpeechRate, type ThemeChoice } from '@/lib/a11y';
import { formatCents } from '@/lib/money';
import { useAgent } from '@/state/agent';

export default function Settings() {
  const { settings, update } = useA11y();
  const { state, refreshCards, resetDemo, sayLocal } = useAgent();

  useFocusEffect(
    useCallback(() => {
      void refreshCards();
    }, [refreshCards]),
  );

  return (
    <Screen
      title="Accessibility"
      dockLeft={{ label: 'Home', icon: '⌂', href: '/' }}
      dockRight={{ label: 'Scan', icon: '📷', href: '/scan' }}>
      <Section title="Display">
        <Choice<ThemeChoice>
          label="Colors"
          value={settings.theme}
          onChange={(theme) => update({ theme })}
          options={[
            { value: 'system', label: 'Match phone' },
            { value: 'standard', label: 'Standard' },
            { value: 'dark', label: 'Dark' },
            { value: 'highContrast', label: 'High contrast' },
          ]}
        />
      </Section>

      <Section title="Text size">
        <Choice<number>
          label="Text size"
          value={settings.textScale}
          onChange={(textScale) => update({ textScale })}
          options={TEXT_SCALES.map((s) => ({ value: s, label: `${Math.round(s * 100)}%` }))}
          row
        />
        <AppText kind="body">Preview: Advil Ibuprofen 200mg, $12.99</AppText>
      </Section>

      <Section title="Captions">
        <Toggle
          label="Show captions"
          detail="On-screen text of everything Rewind says"
          value={settings.captions}
          onChange={(captions) => update({ captions })}
        />
      </Section>

      <Section title="Voice">
        <Choice<SpeechRate>
          label="Speech speed"
          value={settings.speechRate}
          onChange={(speechRate) => {
            update({ speechRate });
            sayLocal('This is how fast I will speak.');
          }}
          options={[
            { value: 'slow', label: 'Slow' },
            { value: 'normal', label: 'Normal' },
            { value: 'fast', label: 'Fast' },
          ]}
          row
        />
        <Choice<number>
          label="Volume"
          value={settings.volume}
          onChange={(volume) => update({ volume })}
          options={[0.25, 0.5, 0.75, 1].map((v) => ({ value: v, label: `${v * 100}%` }))}
          row
        />
      </Section>

      <Section title="Motion">
        <Toggle
          label="Reduce motion"
          detail="No sliding cards or screen animations"
          value={settings.reduceMotion}
          onChange={(reduceMotion) => update({ reduceMotion })}
        />
      </Section>

      <Section title="Cards (mock)">
        {state.cards.map((c) => (
          <View key={c.id} style={styles.cardRow}>
            <AppText kind="body" style={styles.flex}>
              {c.nickname}
              {c.status !== 'active' ? ` · ${c.status}` : ''}
            </AppText>
            <AppText kind="label">{formatCents(c.balance_cents)}</AppText>
          </View>
        ))}
        <AppText kind="small" color="textMuted">
          Demo accounts only. No real cards are linked.
        </AppText>
      </Section>

      <Section title="Demo controls (presenter)">
        <BigButton label="Reset demo · run 1 (HSA $340.00)" onPress={() => resetDemo(1)} />
        <BigButton label="Reset demo · run 2 (HSA $15.00)" onPress={() => resetDemo(2)} />
      </Section>
    </Screen>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const { palette } = useA11y();
  return (
    <View style={[styles.section, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      <AppText kind="heading" accessibilityRole="header">
        {title}
      </AppText>
      {children}
    </View>
  );
}

/** Radio group. The selected option is marked with ✓, a thick border, and bold text, not color alone. */
function Choice<T extends string | number>({
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
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={[styles.choices, row && styles.choicesRow]}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            accessibilityRole="radio"
            accessibilityLabel={o.label}
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

/** Full-row switch: the whole row is the 56pt+ target and the state is written out. */
function Toggle({
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
  choicesRow: { flexDirection: 'row', flexWrap: 'wrap' },
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
  cardRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: Spacing.sm },
  flex: { flexShrink: 1, flexGrow: 1 },
  center: { textAlign: 'center' },
});
