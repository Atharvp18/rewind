import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import type { Invoice } from '@/lib/api';
import { Icon } from '@/components/icon';
import { isReimbursable, longDate } from '@/lib/invoice-text';
import { shareInvoicePdf } from '@/lib/invoice-pdf';
import { centsForScreenReader, formatCents } from '@/lib/money';

/**
 * An invoice's body: store, items, tax estimate, total, and which card paid. Used by the
 * purchase history and by the checkout invoice widget, so both look the same.
 */
export function InvoiceDetail({ invoice: inv, share = true }: { invoice: Invoice; share?: boolean }) {
  const { palette } = useA11y();
  return (
        <View style={[styles.detail, { borderTopColor: palette.border }]}>
          <View accessible accessibilityLabel={`${inv.store.name}. ${inv.store.address}. Phone ${inv.store.phone}.`}>
            <AppText kind="small" color="textMuted" accessible={false}>
              {inv.store.address}
            </AppText>
            <AppText kind="small" color="textMuted" accessible={false}>
              {inv.store.phone}
            </AppText>
          </View>

          {inv.lines.map((l, i) => (
            <View key={i} style={[styles.line, { borderTopColor: palette.surfaceAlt }]}>
              <View style={styles.lineTop}>
                <AppText style={styles.flex}>{l.name}</AppText>
                <AppText kind="label">{formatCents(l.amount_cents)}</AppText>
              </View>
              <AppText kind="small" color="textMuted">
                {`Qty ${l.qty} × ${formatCents(l.unit_cents)} · paid with ${l.card_type === 'general' ? 'everyday card' : l.card_type.toUpperCase() + ' card'}`}
              </AppText>
              <View style={styles.tags}>
                <EligibilityBadge eligibility={{ label: l.eligibility_label }} compact />
                {isReimbursable(l) ? (
                  <View style={[styles.tag, { backgroundColor: palette.warningBg, borderColor: palette.warningEdge }]}>
                    <AppText kind="small" color="warning">
                      Possible reimbursement
                    </AppText>
                  </View>
                ) : null}
              </View>
            </View>
          ))}

          <View style={[styles.totals, { borderTopColor: palette.text }]}>
            <Row label="Subtotal" cents={inv.subtotal_cents} />
            <Row label="Tax (estimate)" cents={inv.tax_cents} />
            <Row label="Total" cents={inv.total_cents} strong />
            <AppText kind="small" color="textMuted">
              {inv.tax_note}
            </AppText>
          </View>

          <AppText kind="label">Paid with</AppText>
          {inv.payments.map((p) => (
            <View key={p.card_id} style={styles.lineTop}>
              <AppText style={styles.flex}>{`${p.nickname}${p.last4 ? ` •••• ${p.last4}` : ''}`}</AppText>
              <AppText>{formatCents(p.amount_cents)}</AppText>
            </View>
          ))}
          <AppText kind="small" color="textMuted">
            Card amounts are for the items, before tax.
          </AppText>

          {share ? (
          <BigButton
            label="Download invoice (PDF)"
            accessibilityLabel="Download invoice as a PDF"
            icon="download"
            variant="secondary"
            onPress={() => void shareInvoicePdf(inv)}
          />
          ) : null}
        </View>
  );
}

function Row({ label, cents, strong }: { label: string; cents: number; strong?: boolean }) {
  return (
    <View style={styles.lineTop} accessible accessibilityLabel={`${label} ${centsForScreenReader(cents)}`}>
      <AppText kind={strong ? 'heading' : 'body'} style={styles.flex} accessible={false}>
        {label}
      </AppText>
      <AppText kind={strong ? 'heading' : 'body'} accessible={false}>
        {formatCents(cents)}
      </AppText>
    </View>
  );
}

/**
 * One invoice as a card: store, date and total on top (with the possible-reimbursement note),
 * then the full detail. The purchase history lists these (collapsible); the checkout widget shows
 * the same card, always open, so the two always look the same.
 */
export function InvoiceCard({
  invoice: inv,
  open,
  onToggle,
}: {
  invoice: Invoice;
  open: boolean;
  /** Omit for a card that is always open (the checkout widget). */
  onToggle?: () => void;
}) {
  const { palette } = useA11y();
  return (
    <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: palette.controlBorderWidth || 1 }]}>
      <Pressable
        disabled={!onToggle}
        onPress={onToggle}
        accessibilityRole={onToggle ? 'button' : 'header'}
        accessibilityState={onToggle ? { expanded: open } : undefined}
        accessibilityLabel={`${inv.store.name}, ${longDate(inv.date)}, total ${centsForScreenReader(inv.total_cents)}${inv.reimbursable_cents ? ', possible reimbursement' : ''}`}
        accessibilityHint={onToggle ? (open ? 'Collapse invoice' : 'Show invoice details') : undefined}
        style={styles.cardHead}>
        <View style={styles.flex}>
          <AppText kind="label">{inv.store.name}</AppText>
          <AppText kind="small" color="textMuted">
            {longDate(inv.date)}
          </AppText>
          {inv.reimbursable_cents ? (
            <View style={styles.inline}>
              <Icon name="alert" size={16} color="warning" />
              <AppText kind="small" color="warning">
                Possible reimbursement {formatCents(inv.reimbursable_cents)}
              </AppText>
            </View>
          ) : null}
        </View>
        <AppText kind="heading">{formatCents(inv.total_cents)}</AppText>
        {onToggle ? <Icon name={open ? 'chevronUp' : 'chevronDown'} size={22} color="textMuted" /> : null}
      </Pressable>

      {open ? <InvoiceDetail invoice={inv} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: Radius.card, overflow: 'hidden' },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, padding: Spacing.lg },
  inline: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  detail: { borderTopWidth: 1, padding: Spacing.lg, gap: Spacing.sm },
  flex: { flex: 1 },
  line: { borderTopWidth: 1, paddingTop: Spacing.sm, gap: Spacing.xs },
  lineTop: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.xs, alignItems: 'center' },
  tag: { borderRadius: Radius.pill, borderWidth: 1, paddingHorizontal: Spacing.sm, paddingVertical: 2 },
  totals: { borderTopWidth: 2, paddingTop: Spacing.sm, gap: Spacing.xs },
});
