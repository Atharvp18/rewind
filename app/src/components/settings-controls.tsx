import { useEffect, useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { Elevation, Radius, Spacing, Type } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

const SLIDE_MS = 220;
const PAD = 4;
const TRACK_W = 64;
const KNOB = 30;

export function Section({ title, children }: { title: string; children: ReactNode }) {
  const { palette } = useA11y();
  return (
    <View
      style={[
        styles.section,
        { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: palette.controlBorderWidth },
      ]}>
      <AppText kind="heading" accessibilityRole="header">
        {title}
      </AppText>
      {children}
    </View>
  );
}

/** One labeled setting: a single-line label above its control. */
export function SettingRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={styles.settingRow}>
      <AppText kind="label" accessible={false}>
        {label}
      </AppText>
      {children}
    </View>
  );
}

/**
 * Segmented control: one row, the selected option sits on a highlight that
 * slides horizontally to it. Selection is shown by the filled highlight and
 * bold label, not color alone (WCAG 1.4.1). If the labels can't fit on one
 * row at the user's text size, it becomes a vertical list instead of breaking
 * words or shrinking text (1.4.4, 1.4.10).
 */
export function Choice<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  /** Kept for older call sites; layout is decided by what fits. */
  row?: boolean;
}) {
  const { palette, settings, reduceMotion } = useA11y();
  const [width, setWidth] = useState(0);
  const index = Math.max(0, options.findIndex((o) => o.value === value));

  // Does every label fit on one row at this text size? (~0.58 em per character, plus padding.)
  const fontSize = Type.label.fontSize * settings.textScale;
  const needed = options.reduce((sum, o) => sum + o.label.length * fontSize * 0.58 + Spacing.md * 2, 0);
  const horizontal = width > 0 && needed <= width - PAD * 2;

  const segW = horizontal ? (width - PAD * 2) / options.length : 0;
  const x = useSharedValue(index * segW);
  useEffect(() => {
    const to = index * segW;
    x.value = reduceMotion ? to : withTiming(to, { duration: SLIDE_MS });
  }, [index, segW, reduceMotion, x]);
  const thumbStyle = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }] }));

  return (
    <View
      accessibilityRole="radiogroup"
      accessibilityLabel={label}
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
      style={[
        horizontal ? styles.track : styles.list,
        { backgroundColor: palette.surfaceAlt, borderColor: palette.border, borderWidth: palette.controlBorderWidth },
      ]}>
      {horizontal ? (
        <Animated.View
          pointerEvents="none"
          style={[styles.thumb, Elevation.floating, { width: segW, backgroundColor: palette.primary }, thumbStyle]}
        />
      ) : null}
      {options.map((o, i) => {
        const selected = i === index;
        return (
          <Pressable
            key={String(o.value)}
            accessibilityRole="radio"
            accessibilityLabel={`${label}: ${o.label}`}
            accessibilityState={{ checked: selected }}
            onPress={() => onChange(o.value)}
            style={({ pressed }) => [
              horizontal ? styles.segment : styles.listItem,
              !horizontal && selected ? { backgroundColor: palette.primary } : null,
              { opacity: pressed ? 0.8 : 1 },
            ]}>
            <AppText
              kind={selected ? 'label' : 'body'}
              color={selected ? 'onPrimary' : 'text'}
              accessible={false}
              numberOfLines={horizontal ? 1 : undefined}
              style={styles.center}>
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

function StepButton({ icon, disabled, onPress }: { icon: 'minus' | 'add'; disabled: boolean; onPress: () => void }) {
  const { palette } = useA11y();
  return (
    // Hidden from screen readers: the stepper itself is one adjustable control.
    <Pressable
      accessible={false}
      disabled={disabled}
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => [
        styles.stepBtn,
        { backgroundColor: palette.primary, opacity: disabled ? 0.35 : pressed ? 0.8 : 1 },
      ]}>
      <Icon name={icon} size={24} color="onPrimary" strokeWidth={2.75} />
    </Pressable>
  );
}

/**
 * Stepper: one row, [ − ]  value  [ + ]. For settings with more options than
 * fit as segments on a small phone (text size, colors, volume, time). Screen
 * readers get one adjustable control (swipe up / down to change).
 */
export function Stepper<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  const { palette } = useA11y();
  const i = Math.max(0, options.findIndex((o) => o.value === value));
  const go = (d: number) => {
    const n = i + d;
    if (n >= 0 && n < options.length) onChange(options[n].value);
  };
  return (
    <View
      accessible
      accessibilityRole="adjustable"
      accessibilityLabel={label}
      accessibilityValue={{ text: options[i]?.label }}
      accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
      onAccessibilityAction={(e) => go(e.nativeEvent.actionName === 'increment' ? 1 : -1)}
      style={[styles.stepper, { backgroundColor: palette.surfaceAlt, borderColor: palette.border, borderWidth: palette.controlBorderWidth }]}>
      <StepButton icon="minus" disabled={i === 0} onPress={() => go(-1)} />
      <AppText kind="label" accessible={false} style={styles.stepValue}>
        {options[i]?.label}
      </AppText>
      <StepButton icon="add" disabled={i === options.length - 1} onPress={() => go(1)} />
    </View>
  );
}

/**
 * On/off switch: the knob slides right for on, left for off, so position (not
 * just color) carries the state. The whole row is the target.
 */
export function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  const { palette, reduceMotion } = useA11y();
  const knob = useSharedValue(value ? 1 : 0);
  useEffect(() => {
    knob.value = reduceMotion ? (value ? 1 : 0) : withTiming(value ? 1 : 0, { duration: SLIDE_MS });
  }, [value, reduceMotion, knob]);
  const knobStyle = useAnimatedStyle(() => ({ transform: [{ translateX: knob.value * (TRACK_W - KNOB - 8) }] }));

  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityState={{ checked: value }}
      onPress={() => onChange(!value)}
      style={({ pressed }) => [styles.toggleRow, { opacity: pressed ? 0.8 : 1 }]}>
      <AppText kind="label" accessible={false} style={styles.flex}>
        {label}
      </AppText>
      <View
        style={[
          styles.switchTrack,
          {
            backgroundColor: value ? palette.primary : palette.surfaceAlt,
            // The off-state track needs a visible edge (1.4.11): border is 4.6:1 on white.
            borderColor: value ? palette.primary : palette.border,
          },
        ]}>
        <Animated.View style={[styles.knob, Elevation.floating, { backgroundColor: palette.surface }, knobStyle]} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.md },
  settingRow: { gap: Spacing.sm },
  // Segmented
  track: { flexDirection: 'row', borderRadius: Radius.pill, padding: PAD, minHeight: 60 },
  thumb: { position: 'absolute', top: PAD, bottom: PAD, left: PAD, borderRadius: Radius.pill },
  segment: { flex: 1, minHeight: 52, alignItems: 'center', justifyContent: 'center', paddingHorizontal: Spacing.sm },
  // Vertical fallback
  list: { borderRadius: Radius.card, padding: PAD, gap: PAD },
  listItem: { minHeight: 56, borderRadius: Radius.button, justifyContent: 'center', paddingHorizontal: Spacing.lg },
  center: { textAlign: 'center' },
  // Stepper
  stepper: { flexDirection: 'row', alignItems: 'center', borderRadius: Radius.pill, padding: PAD, gap: Spacing.sm },
  stepBtn: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center' },
  stepValue: { flex: 1, textAlign: 'center' },
  // Switch
  toggleRow: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  flex: { flexShrink: 1, flexGrow: 1 },
  switchTrack: { width: TRACK_W, height: KNOB + 8, borderRadius: Radius.pill, borderWidth: 2, padding: 2, justifyContent: 'center' },
  knob: { width: KNOB, height: KNOB, borderRadius: KNOB / 2 },
});
