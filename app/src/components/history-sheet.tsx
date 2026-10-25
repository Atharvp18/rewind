import { useEffect, useMemo, useState } from 'react';
import { PanResponder, ScrollView, StyleSheet, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  Easing,
  FadeOut,
  SlideOutDown,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { Icon } from '@/components/icon';
import { CloseButton } from '@/components/close-button';
import { InvoiceCard } from '@/components/invoice-view';
import { ScrollCue, useScrollCue } from '@/components/scroll-cue';
import { useDomeHeight } from '@/components/voice-orb';
import { Elevation, Layout, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { getPaymentHistory, type Invoice } from '@/lib/api';
import { shareReimbursementPacketPdf } from '@/lib/invoice-pdf';
import { centsForScreenReader, formatCents } from '@/lib/money';
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
  const { palette, reduceMotion, settings } = useA11y();
  const { showView, state } = useAgent();
  const cue = useScrollCue();
  const insets = useSafeAreaInsets();
  const { width: screenW, height: screenH } = useWindowDimensions();
  const dome = useDomeHeight();
  // A full page: from under the status bar down to the dome, so the orb stays usable.
  // Measured once, when the page opens: the page must not resize while it slides (that reads as a shake).
  const [geo] = useState(() => {
    const t = insets.top + Spacing.sm;
    return { top: t, pageH: Math.max(0, screenH - dome - t - Spacing.sm) };
  });
  const { top, pageH } = geo;

  // One steady slide of the whole page from below the screen to its place: a plain timing
  // curve on a transform, with no spring, no bounce, and nothing else moving.
  const slide = useSharedValue(reduceMotion ? 0 : screenH);
  useEffect(() => {
    slide.value = withTiming(0, { duration: reduceMotion ? 0 : 420, easing: Easing.out(Easing.cubic) });
  }, [reduceMotion, slide]);
  const slideStyle = useAnimatedStyle(() => ({ transform: [{ translateY: slide.value }] }));
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const width = Math.min(screenW - Layout.margin * 2, MaxContentWidth);

  // Swipe down on the header closes the page (the ✕ and the History button do too).
  const pan = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, g) => g.dy > 8 && Math.abs(g.dy) > Math.abs(g.dx),
        onPanResponderRelease: (_, g) => {
          if (g.dy > 40) showView('camera');
        },
      }),
    [showView],
  );

  // Closes itself after a while without use (never while the agent is busy). Any touch or
  // scroll restarts the clock. The wait is twice the "Time to answer" setting, at least 60 s
  // (WCAG 2.2.1: the user can lengthen it in Settings).
  const [touched, setTouched] = useState(0);
  const idle = state.phase === 'idle';
  const waitMs = Math.max(60, settings.answerSeconds * 2) * 1000;
  useEffect(() => {
    if (!idle) return;
    const t = setTimeout(() => showView('camera'), waitMs);
    return () => clearTimeout(t);
  }, [idle, touched, waitMs, showView]);

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
      exiting={reduceMotion ? FadeOut.duration(0) : SlideOutDown.duration(320).easing(Easing.in(Easing.cubic))}
      accessibilityViewIsModal
      style={[
        styles.sheet,
        slideStyle,
        Elevation.floating,
        {
          top,
          left: (screenW - width) / 2,
          width,
          height: pageH,
          backgroundColor: palette.bg,
          borderColor: palette.border,
          borderWidth: palette.controlBorderWidth,
        },
      ]}>
      <View style={[styles.header, { borderBottomColor: palette.surfaceAlt }]} {...pan.panHandlers}>
        <View style={styles.flex}>
          <AppText kind="heading" accessibilityRole="header">
            Purchase history
          </AppText>
          <AppText kind="small" color="textMuted">
            Simulated payments · mock data
          </AppText>
        </View>
        <CloseButton label="Close purchase history" onPress={() => showView('camera')} />
      </View>

      <View style={styles.flex}>
        <ScrollView
          contentContainerStyle={styles.scroll}
          {...cue.scrollProps}
          onTouchStart={() => setTouched((n) => n + 1)}
          onScrollBeginDrag={() => setTouched((n) => n + 1)}>
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
                label="Download packet (PDF)"
                accessibilityLabel="Download reimbursement packet as a PDF"
                icon="download"
                variant="secondary"
                onPress={() => void shareReimbursementPacketPdf(invoices!)}
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

const styles = StyleSheet.create({
  sheet: { position: 'absolute', borderRadius: Radius.card + 4, overflow: 'hidden' },
  header: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md, padding: Spacing.lg, borderBottomWidth: 1 },
  flex: { flex: 1 },
  scroll: { padding: Spacing.md, paddingBottom: Spacing.xxl, gap: Spacing.md },
  inline: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  summary: { borderRadius: Radius.card, borderWidth: 2, padding: Spacing.lg, gap: Spacing.sm },
});
