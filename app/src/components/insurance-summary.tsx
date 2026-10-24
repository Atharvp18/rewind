import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Spacing } from '@/constants/theme';
import type { InsuranceCard } from '@/lib/api';
import { formatCents } from '@/lib/money';

/**
 * What Rewind read from an insurance card: insurer and plan, member name,
 * member ID (last 4 only), and prescription benefits. Used for the onboarding
 * read-back and in Profile, so both always show the same fields.
 */
export function InsuranceSummary({ card }: { card: InsuranceCard }) {
  const member = [card.member_first_name, card.member_last_name].filter(Boolean).join(' ');
  return (
    <View style={styles.root}>
      <AppText kind="heading">{card.insurer_name}</AppText>
      {card.plan_name ? <AppText kind="body">{card.plan_name}</AppText> : null}
      {member ? <Row label="Member" value={member} /> : null}
      {card.member_id_last4 ? <Row label="Member ID" value={`ending in ${card.member_id_last4}`} /> : null}

      {card.rx ? (
        <View style={styles.rx} accessibilityLabel="Prescription benefits">
          <AppText kind="label">Prescription benefits</AppText>
          {card.rx.bin ? <Row label="Rx BIN" value={card.rx.bin} /> : null}
          {card.rx.pcn ? <Row label="Rx PCN" value={card.rx.pcn} /> : null}
          {card.rx.group ? <Row label="Rx Group" value={card.rx.group} /> : null}
          {card.rx.copays.map((c) => (
            <Row key={c.label} label={`${c.label} copay`} value={formatCents(c.amount_cents)} />
          ))}
        </View>
      ) : (
        <AppText kind="small" color="textMuted">
          No prescription benefits shown on this card.
        </AppText>
      )}
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row} accessible accessibilityLabel={`${label}: ${value}`}>
      <AppText kind="small" color="textMuted" style={styles.label}>
        {label}
      </AppText>
      <AppText kind="body" style={styles.value}>
        {value}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: Spacing.xs },
  rx: { gap: Spacing.xs, paddingTop: Spacing.sm },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', columnGap: Spacing.md },
  label: { minWidth: 96 },
  value: { flexShrink: 1, fontWeight: '600' },
});
