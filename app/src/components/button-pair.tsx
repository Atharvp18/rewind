import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { Children } from 'react';

import { BigButton } from '@/components/big-button';
import { Layout } from '@/constants/theme';

/**
 * Two equal pills side by side: the same width, height, shape, and icon
 * position. Used for every yes / no answer and for matched action pairs.
 */
export function ButtonRow({ children }: { children: ReactNode }) {
  return (
    <View style={styles.row}>
      {Children.toArray(children).map((c, i) => (
        <View key={i} style={styles.cell}>
          {c}
        </View>
      ))}
    </View>
  );
}

/**
 * Every yes / no answer in the app. Yes is solid teal (red for a destructive
 * yes); No is the tonal pill.
 *
 * The visible words are short ("Yes", "No") because the card already says what
 * is being asked ("Pays with FSA card · $25.00 left"). Screen readers get the
 * full phrase ("Yes, use FSA card"); it contains the visible word, so the
 * spoken name matches the label (WCAG 2.5.3).
 */
export function ButtonPair({
  yes = 'Yes',
  no = 'No',
  yesA11y,
  noA11y,
  yesVariant = 'primary',
  onYes,
  onNo,
  busy,
}: {
  yes?: string;
  no?: string;
  /** Full spoken names, e.g. "Yes, use FSA card". Must start with the visible label. */
  yesA11y?: string;
  noA11y?: string;
  yesVariant?: 'primary' | 'danger';
  onYes: () => void;
  onNo: () => void;
  busy?: boolean;
}) {
  return (
    <ButtonRow>
      <BigButton label={yes} accessibilityLabel={yesA11y} icon="check" variant={yesVariant} disabled={busy} onPress={onYes} stretch />
      <BigButton label={no} accessibilityLabel={noA11y} icon="close" variant="secondary" disabled={busy} onPress={onNo} stretch />
    </ButtonRow>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'stretch', gap: Layout.stack },
  // Equal width, never wrapping to a second row (the labels are short).
  cell: { flex: 1, flexDirection: 'column' },
});
