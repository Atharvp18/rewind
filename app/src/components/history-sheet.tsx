import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Share, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, SlideInDown } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Icon } from '@/components/icon';
import { ScrollCue, useScrollCue } from '@/components/scroll-cue';
import { Elevation, Layout, MaxContentWidth, Motion, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { getPaymentHistory, type Invoice } from '@/lib/api';
import { invoiceToText, isReimbursable, longDate, packetToText } from '@/lib/invoice-text';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { useStage } from '@/lib/stage';
import { useAgent } from '@/state/agent';

/**
 * Purchase history (business spec 6.6, stretch): pulled up from the bottom edge, under the
 * voice orb. One collapsible invoice per payment, newest first, with the store's name,
 * address and phone, every item with quantity and amount, estimated tax, the total, and
 * which card paid. Eligible items paid with an everyday card are marked "Possible
 * reimbursement" so the user can send the invoice to their own HSA/FSA administrator.
 * Rewind prepares the paperwork; it never files a claim. All values are mock.
 */
export function HistorySheet() {
  const { palette, reduceMotion } = useA11y();
  const { showView, state } = useAgent();
  const { area } = useStage();
  const cue = useScrollCue();
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const width = Math.min(area.w - Layout.margin * 2, MaxContentWidth);

  useEffect(() => {
    let live = true;
    getPaymentHistory()
      .then((list) => {
        if (!live) return;
        setInvoices(list);
        setOpen(list[0]?.invoice_id ?? null);
      })
      .catch(() => live && setInvoices([]));
    return () => {
      live = false;
    };
  }, [state.receipt]);

  const reimbursable = (invoices ?? []).filter((i) => i.reimbursable_cents > 0);
  const reimbursableTotal = reimbursable.reduce((s, i) => s + i.reimbursable_cents, 0);

  return (
    <Animated.View
      entering={reduceMotion ? FadeIn.duration(0) : SlideInDown.duration(Motion.panel)}
      accessibilityViewIsModal
      style={[
        styles.sheet,
        Elevation.floating,
        {
          top: area.y,
          left: area.x + (area.w - width) / 2,
          width,
          height: area.h,
          backgroundColor: palette.bg,
          borderColor: palette.border,
          borderWidth: palette.controlBorderWidth,
        },
      ]}>
      <View style={[styles.header, { borderBottomColor: palette.surfaceAlt }]}>
        <View style={styles.flex}>
          <AppText kind="heading" accessibilityRole="header">
            Purchase history
          </AppText>
          <AppText kind="small" color="textMuted">
            Simulated payments · mock data
          </AppText>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close purchase history"
          onPress={() => showView('camera')}
          hitSlop={8}
          style={({ pressed }) => [styles.close, { backgroundColor: palette.surfaceAlt, opacity: pressed ? 0.8 : 1 }]}>
          <Icon name="close" size={26} />
        </Pressable>
      </View>

      <View style={styles.flex}>
        <ScrollView contentContainerStyle={styles.scroll} {...cue.scrollProps}>
          {invoices === null ? <AppText color="textMuted">Loading…</AppText> : null}
          {invoices?.length === 0 ? <AppText color="textMuted">No purchases yet.</AppText> : null}

          {reimbursable.length ? (
            <View
              style={[styles.summary, { backgroundColor: palette.warningBg, borderColor: palette.warningEdge }]}
              accessible
              accessibilityLabel={`Possible reimbursement ${centsForScreenReader(reimbursableTotal)} on ${reimbursable.length} invoices`}>
              <View style={styles.inline}>
                <Icon name="alert" size={22} color="warning" />
                <AppText kind="label" color="warning" accessible={false}>
                  Possible reimbursement
                </AppText>
              </View>
              <AppText kind="title" color="warning" accessible={false}>
                {formatCents(reimbursableTotal)}
              </AppText>
              <AppText kind="small" color="warning" accessible={false}>
                {`HSA/FSA-eligible items on ${reimbursable.length} ${reimbursable.length === 1 ? 'invoice' : 'invoices'} were paid with an everyday card. Send the invoices to your HSA/FSA administrator; they make the final decision. Rewind does not file claims.`}
              </AppText>
              <BigButton
                label="Share packet"
                accessibilityLabel="Share reimbursement packet"
                icon="share"
                variant="secondary"
                onPress={() => void Share.share({ title: 'Rewind reimbursement packet', message: packetToText(invoices!) })}
              />
            </View>
          ) : null}

          {invoices?.map((inv) => (
            <InvoiceCard
              key={inv.invoice_id}
              invoice={inv}
              open={open === inv.invoice_id}
              onToggle={() => setOpen(open === inv.invoice_id ? null : inv.invoice_id)}
            />
          ))}
        </ScrollView>
        <ScrollCue visible={cue.more} bg={palette.bg} />
      </View>
    </Animated.View>
  );
}

function InvoiceCard({ invoice: inv, open, onToggle }: { invoice: Invoice; open: boolean; onToggle: () => void }) {
  const { palette } = useA11y();
  return (
    <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: palette.controlBorderWidth || 1 }]}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`${inv.store.name}, ${longDate(inv.date)}, total ${centsForScreenReader(inv.total_cents)}${inv.reimbursable_cents ? ', possible reimbursement' : ''}`}
        accessibilityHint={open ? 'Collapse invoice' : 'Show invoice details'}
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
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={22} color="textMuted" />
      </Pressable>

      {open ? (
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

          <BigButton
            label="Share invoice"
            icon="share"
            variant="secondary"
            onPress={() => void Share.share({ title: `Invoice ${inv.invoice_id}`, message: invoiceToText(inv) })}
          />
        </View>
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

const styles = StyleSheet.create({
  sheet: { position: 'absolute', borderRadius: Radius.card + 4, overflow: 'hidden' },
  header: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md, padding: Spacing.lg, borderBottomWidth: 1 },
  close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  flex: { flex: 1 },
  scroll: { padding: Spacing.md, paddingBottom: Spacing.xxl, gap: Spacing.md },
  inline: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  summary: { borderRadius: Radius.card, borderWidth: 2, padding: Spacing.lg, gap: Spacing.sm },
  card: { borderRadius: Radius.card, overflow: 'hidden' },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, padding: Spacing.lg },
  detail: { borderTopWidth: 1, padding: Spacing.lg, gap: Spacing.sm },
  line: { borderTopWidth: 1, paddingTop: Spacing.sm, gap: Spacing.xs },
  lineTop: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.xs, alignItems: 'center' },
  tag: { borderRadius: Radius.pill, borderWidth: 1, paddingHorizontal: Spacing.sm, paddingVertical: 2 },
  totals: { borderTopWidth: 2, paddingTop: Spacing.sm, gap: Spacing.xs },
});
