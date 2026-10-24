import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, {
  Easing,
  FadeInDown,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { AlertBlock } from '@/components/alert-block';
import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { ButtonPair } from '@/components/button-pair';
import { CardArt } from '@/components/card-art';
import { CardGroupView } from '@/components/card-group';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Icon, Notice } from '@/components/icon';
import { InvoiceDetail } from '@/components/invoice-view';
import { InfoPanel, PanelActions, PanelText, type PanelTone } from '@/components/info-panel';
import { Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import type { Card, PaymentRecommendation, ScanResponse } from '@/lib/api';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { Phrases } from '@/lib/phrases';
import { useAgent } from '@/state/agent';

/**
 * Frame 3: what the see-through panel shows after onboarding, most urgent
 * first. Nothing when there is nothing to show, so the camera stays clear.
 */
export function HomePanels() {
  const { state } = useAgent();
  if (state.declined) return <DeclinedPanel message={state.declined} />;
  if (state.receipt) return <ReceiptPanel />;
  if (state.view === 'checkout') return <CheckoutPanel />;
  if (state.view === 'cart') return <CartPanel />;
  if (state.lastScan && state.phase !== 'awaiting_scan' && state.phase !== 'capturing') {
    return <ScanPanel res={state.lastScan} />;
  }
  return null;
}

const cardById = (cards: Card[], id: string | null | undefined) => cards.find((c) => c.id === id);

/**
 * Reason codes (tech spec 3.5) where linking another card would help.
 * Business spec 6.4: "suggest moving items or adding a second card";
 * 20.6: "No HSA/FSA card linked: prompt to link one".
 */
const ADD_CARD_REASONS = new Set(['no_card_linked', 'no_card_covers', 'no_health_card_linked']);

function needsAnotherCard(rec: PaymentRecommendation): boolean {
  if (ADD_CARD_REASONS.has(rec.reason_code)) return true;
  // HSA/FSA balance too low and no other card to move the item to.
  return rec.reason_code === 'eligible_insufficient_balance' && !rec.reroute && rec.card_options.length === 0;
}

function scanTone(rec: PaymentRecommendation | null): PanelTone {
  if (!rec) return 'normal';
  return rec.decision === 'blocked' || rec.reroute || needsAnotherCard(rec) ? 'warning' : 'normal';
}

/** Orange suggestion to link another card (business spec 6.4 rule 2, 20.6). */
function AddCardSuggestion() {
  const { showView } = useAgent();
  return (
    <AlertBlock level="warning" title="Suggestion">
      <AppText kind="body">Add another Visa card, like your everyday credit or debit card, so Rewind can split the payment.</AppText>
      <BigButton label="Add a card" icon="add" variant="primary" onPress={() => showView('add_card')} />
    </AlertBlock>
  );
}

// ---------------------------------------------------------------------------
// Scan result
// ---------------------------------------------------------------------------

function ScanPanel({ res }: { res: ScanResponse }) {
  const { state, addToCart, skip, answer } = useAgent();
  const { product, eligibility } = res.scan;
  const rec = res.recommendation;
  // Answers stay active after the question's window: a late answer re-asks for the same item.
  const busy = state.phase === 'submitting';

  if (res.scan.state === 'unresolved') {
    return (
      <InfoPanel title="Could not confirm this item">
        <PanelText>Try another angle, or tap Talk and say what it is.</PanelText>
        <PanelActions>
          <BigButton label="Scan again" icon="retry" variant="primary" size="primary" onPress={skip} />
        </PanelActions>
      </InfoPanel>
    );
  }

  // Pill bottle: read drug name and strength back; nothing proceeds until confirmed (tech spec 2.3).
  if (res.voice.response_scope === 'confirm_strength') {
    return <PrescriptionPanel name={product.name} strength={product.size} busy={busy} onAnswer={answer} />;
  }

  return (
    <InfoPanel tone={scanTone(rec)}>
      {/* Product card order: name (full width), then price + eligibility side by side. */}
      <AppText kind="heading" accessibilityRole="header">
        {product.name}
      </AppText>
      {product.amount_cents != null ? (
        <View style={styles.priceRow}>
          <View accessible accessibilityLabel={`Price ${centsForScreenReader(product.amount_cents)}`}>
            <PanelText kind="display">{formatCents(product.amount_cents)}</PanelText>
          </View>
          <EligibilityBadge eligibility={eligibility} isMedication={product.is_medication} />
        </View>
      ) : null}
      {product.amount_cents == null ? (
        <AlertBlock level="warning" title="Price not found">
          Point at the shelf tag, or say the price.
        </AlertBlock>
      ) : null}
      {product.amount_cents == null ? (
        <EligibilityBadge eligibility={eligibility} isMedication={product.is_medication} />
      ) : null}
      {rec ? <Recommendation rec={rec} cards={state.cards} /> : null}
      {rec && needsAnotherCard(rec) ? <AddCardSuggestion /> : null}
      {rec && rec.decision !== 'blocked' ? (
        <CardChooser
          rec={rec}
          cards={state.cards}
          priceCents={product.amount_cents ?? rec.amount_cents}
          eligible={eligibility.label === 'eligible'}
          busy={busy}
          onAdd={addToCart}
        />
      ) : null}
      {rec ? (
        <PanelActions>
          {rec.decision === 'blocked' ? (
            <BigButton label="OK" variant="primary" size="primary" onPress={skip} />
          ) : (
            <BigButton label="Skip this item" accessibilityLabel="No, skip this item" icon="close" variant="secondary" disabled={busy} onPress={skip} />
          )}
        </PanelActions>
      ) : null}
    </InfoPanel>
  );
}

/**
 * Prescription read-back (tech spec 2.3, business spec 20.4): what the label
 * says, the strength called out on its own, one plain question, and the
 * pharmacist note. Nothing proceeds until the shopper confirms; no dosage or
 * safety advice is ever given.
 */
function PrescriptionPanel({
  name,
  strength,
  busy,
  onAnswer,
}: {
  name: string;
  strength: string | null;
  busy: boolean;
  onAnswer: (text: string) => void;
}) {
  const { palette } = useA11y();
  return (
    <InfoPanel label="Prescription label read-back">
      <View style={styles.rxHeader}>
        <View style={[styles.rxIcon, { backgroundColor: palette.surfaceAlt }]}>
          <Icon name="pill" size={22} color="primary" />
        </View>
        <AppText kind="small" color="textMuted" style={styles.name}>
          Prescription · from the bottle label
        </AppText>
      </View>
      <View style={styles.rxNameRow} accessible accessibilityLabel={`${name}${strength ? `, ${strength}` : ''}`}>
        <AppText kind="title" accessible={false}>
          {name}
        </AppText>
        {strength ? (
          <View style={[styles.rxStrength, { backgroundColor: palette.primary }]}>
            <AppText kind="label" color="onPrimary" accessible={false}>
              {strength}
            </AppText>
          </View>
        ) : null}
      </View>
      <PanelText>Is this the right medicine and strength?</PanelText>
      <View style={[styles.rxNote, { backgroundColor: palette.surfaceAlt }]}>
        <Icon name="health" size={20} color="textMuted" />
        <AppText kind="small" color="textMuted" style={styles.name}>
          Rewind can’t give medical advice. Ask the pharmacist about dosage or safety.
        </AppText>
      </View>
      <PanelActions>
        <ButtonPair
          yesA11y="Yes, that's right"
          noA11y="No, scan again"
          onYes={() => onAnswer('yes')}
          onNo={() => onAnswer('no')}
          busy={busy}
        />
      </PanelActions>
    </InfoPanel>
  );
}

function Recommendation({ rec, cards }: { rec: PaymentRecommendation; cards: Card[] }) {
  const card = cardById(cards, rec.card_id);
  if (rec.decision === 'route_to_hsa' || rec.decision === 'route_to_general') {
    const balance =
      rec.balance_before_cents != null && card?.type !== 'general' ? ` · ${formatCents(rec.balance_before_cents)} left` : '';
    return (
      <View style={styles.paysWith} accessible accessibilityLabel={`Pays with ${card?.nickname ?? 'card'}${balance}`}>
        {card ? <CardArt type={card.type} size="swatch" /> : null}
        <AppText kind="body" accessible={false} style={styles.name}>
          {`Pays with ${card?.nickname ?? 'card'}${balance}`}
        </AppText>
      </View>
    );
  }
  if (rec.decision === 'blocked') {
    return (
      <AlertBlock level="warning" title="Can’t add this item">
        Listen to Rewind for what to do next.
      </AlertBlock>
    );
  }
  if (rec.reroute) {
    const from = cardById(cards, rec.reroute.from_card_id);
    return (
      <AlertBlock level="warning" title="Balance too low">
        {`Your ${from?.nickname ?? 'HSA card'} balance${
          rec.balance_before_cents != null ? ` of ${formatCents(rec.balance_before_cents)}` : ''
        } does not cover this item.`}
      </AlertBlock>
    );
  }
  return <PanelText>Which card would you like to use?</PanelText>;
}

/**
 * "Which card?" instead of yes / no: every Visa card linked in the profile, listed top to
 * bottom with its balance, the suggested one first and marked. Tapping a card adds the item to
 * it. A card that cannot pay for this item is shown but disabled, with the reason in words.
 * (Saying "yes" still adds the item to the suggested card.)
 */
function CardChooser({
  rec,
  cards,
  priceCents,
  eligible,
  busy,
  onAdd,
}: {
  rec: PaymentRecommendation;
  cards: Card[];
  priceCents: number;
  eligible: boolean;
  busy: boolean;
  onAdd: (cardId: string) => void;
}) {
  const { palette, reduceMotion } = useA11y();
  const suggested = rec.card_id ?? rec.card_options[0] ?? rec.reroute?.to_card_id ?? null;
  const ordered = [...cards].sort((a, b) => Number(b.id === suggested) - Number(a.id === suggested));

  return (
    <View style={styles.chooser} accessibilityRole="radiogroup" accessibilityLabel="Choose a card">
      {ordered.map((c, i) => {
        const health = c.type !== 'general';
        const reason =
          c.status !== 'active'
            ? `Card is ${c.status}`
            : health && !eligible
              ? 'This item is not HSA/FSA eligible'
              : c.balance_cents < priceCents
                ? 'Balance too low'
                : null;
        const isSuggested = c.id === suggested && !reason;
        return (
          <Animated.View
            key={c.id}
            entering={reduceMotion ? undefined : FadeInDown.delay(i * 110).duration(280)}>
            <Pressable
              disabled={busy || !!reason}
              onPress={() => onAdd(c.id)}
              accessibilityRole="button"
              accessibilityLabel={`${c.nickname}, balance ${centsForScreenReader(c.balance_cents)}${isSuggested ? ', suggested' : ''}${reason ? `. ${reason}` : ''}`}
              accessibilityHint={reason ? undefined : 'Add this item to this card'}
              accessibilityState={{ disabled: busy || !!reason }}
              style={({ pressed }) => [
                styles.cardRow,
                {
                  backgroundColor: isSuggested ? palette.surface : palette.surfaceAlt,
                  borderColor: isSuggested ? palette.primary : palette.border,
                  borderWidth: isSuggested ? 2 : 1,
                  opacity: reason ? 0.6 : pressed ? 0.85 : 1,
                },
              ]}>
              <CardArt type={c.type} size="swatch" />
              <View style={styles.cardInfo}>
                <PanelText kind="label">{c.nickname}</PanelText>
                <PanelText kind="small" muted>
                  {reason ?? `Balance ${formatCents(c.balance_cents)}`}
                </PanelText>
              </View>
              {isSuggested ? (
                <View style={[styles.suggestedTag, { backgroundColor: palette.primary }]}>
                  <AppText kind="small" color="onPrimary">Suggested</AppText>
                </View>
              ) : null}
              <Icon name={reason ? 'notEligible' : 'next'} size={20} color="textMuted" />
            </Pressable>
          </Animated.View>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Cart
// ---------------------------------------------------------------------------

/** The total, pinned beside the primary action so it is always in view. */
function TotalRow({ cents }: { cents: number }) {
  return (
    <View style={styles.totalRow} accessible accessibilityLabel={`Total ${centsForScreenReader(cents)}, before tax`}>
      <View>
        <PanelText kind="label">Total</PanelText>
        <PanelText kind="small" muted>
          Before tax
        </PanelText>
      </View>
      <PanelText kind="title">{formatCents(cents)}</PanelText>
    </View>
  );
}

function CartPanel() {
  const { state, startCheckout, reviewItem, answer, dismiss } = useAgent();
  const { cart } = state;
  const scope = state.livePrompt?.scope;

  if (!cart.groups.length) {
    return (
      <InfoPanel title="Your cart is empty" onClose={dismiss}>
        <PanelText>Point your phone at a product and it will appear here.</PanelText>
      </InfoPanel>
    );
  }
  return (
    <InfoPanel title="Your cart" onClose={dismiss}>
      <PanelText kind="small" muted>
        Tap an item to hear it again and choose whether to remove it.
      </PanelText>
      {cart.groups.map((g) => (
        <CardGroupView key={g.card_id} group={g} card={cardById(state.cards, g.card_id)} onItemPress={reviewItem}
          openItemId={scope === 'confirm_remove_item' ? state.reviewId : null}
          onKeep={() => answer('no')}
          onRemove={() => answer('yes')}
        />
      ))}
      <PanelActions>
        <TotalRow cents={cart.total_cents} />
        {scope === 'confirm_review_rest' ? (
          <ButtonPair yesA11y="Yes, check the rest" noA11y="No, I'm done" onYes={() => answer('yes')} onNo={() => answer('no')} />
        ) : (
          <BigButton label="Checkout" icon="next" variant="primary" size="primary" onPress={startCheckout} />
        )}
      </PanelActions>
    </InfoPanel>
  );
}

// ---------------------------------------------------------------------------
// Checkout, receipt, decline
// ---------------------------------------------------------------------------

function CheckoutPanel() {
  const { state, confirmCheckout, startCheckout, showView } = useAgent();
  const { preview } = state;
  const busy = state.phase === 'submitting';
  const back = () => showView('cart');

  if (!preview) {
    return (
      <InfoPanel title="Checkout" onClose={back}>
        <PanelText>Getting your split…</PanelText>
      </InfoPanel>
    );
  }
  if (!preview.groups.length) {
    return (
      <InfoPanel title="Your cart is empty" onClose={() => showView('camera')}>
        <PanelText>Point your phone at a product and it will appear here.</PanelText>
      </InfoPanel>
    );
  }

  const live = !!preview.voice.prompt_id && state.livePrompt?.id === preview.voice.prompt_id;
  const reroute = preview.issues.length > 0;

  return (
    <InfoPanel title="Checkout" tone={reroute ? 'warning' : 'normal'} onClose={back}>
      {preview.issues.map((issue) => (
        <AlertBlock key={issue.rule + issue.message} level="warning" title="Suggestion: change cards">
          {issue.message}
        </AlertBlock>
      ))}
      {preview.issues.some((i) => i.rule === 'nothing_covers') ? <AddCardSuggestion /> : null}
      {preview.groups.map((g) => (
        <CardGroupView key={g.card_id} group={g} card={cardById(state.cards, g.card_id)} />
      ))}
      <PanelText kind="small" muted>
        This is a simulated payment. No real card is charged.
      </PanelText>
      <PanelActions>
        <TotalRow cents={preview.total_cents} />
        {!live ? (
          <BigButton label="Read the split again" icon="retry" variant="primary" size="primary" onPress={startCheckout} />
        ) : reroute ? (
          <ButtonPair
            yesA11y="Yes, move the items"
            noA11y="No, keep my cards"
            onYes={() => confirmCheckout(true)}
            onNo={() => confirmCheckout(false)}
            busy={busy}
          />
        ) : (
          <BigButton label="Confirm payment" icon="check" variant="primary" size="primary" disabled={busy} onPress={() => confirmCheckout(true)} />
        )}
      </PanelActions>
    </InfoPanel>
  );
}

/**
 * After checkout: the invoice as a widget (same place as the checkout and medication cards).
 * It stays while the agent speaks, then flies down into the History label at the bottom and
 * becomes the newest invoice in the history. It leaves on the user's tap (Save to history, or
 * the close button) or 10 seconds after the agent stops speaking.
 */
function ReceiptPanel() {
  const { state, dismiss } = useAgent();
  const { reduceMotion } = useA11y();
  const { height } = useWindowDimensions();
  const receipt = state.receipt!;
  const lowBalance = receipt.voice.priority === 'alert';
  const y = useSharedValue(0);
  const k = useSharedValue(1);
  const [leaving, setLeaving] = useState(false);

  const leave = useCallback(() => setLeaving(true), []);

  useEffect(() => {
    if (!leaving) return;
    if (reduceMotion) {
      dismiss();
      return;
    }
    y.value = withTiming(height * 0.7, { duration: 520, easing: Easing.in(Easing.cubic) });
    k.value = withTiming(0, { duration: 520, easing: Easing.in(Easing.cubic) }, (done) => {
      if (done) runOnJS(dismiss)();
    });
  }, [leaving, reduceMotion, height, y, k, dismiss]);

  // 10 s after the agent has finished speaking.
  const quiet = state.phase === 'idle' || state.phase === 'awaiting_confirm';
  useEffect(() => {
    if (!quiet) return;
    const t = setTimeout(leave, 10_000);
    return () => clearTimeout(t);
  }, [quiet, leave]);

  const fly = useAnimatedStyle(() => ({
    opacity: 0.2 + 0.8 * k.value,
    transform: [{ translateY: y.value }, { scale: 0.25 + 0.75 * k.value }],
  }));

  return (
    <Animated.View style={[StyleSheet.absoluteFill, fly]} pointerEvents={leaving ? 'none' : 'box-none'}>
      <InfoPanel title="Payment complete" tone={lowBalance ? 'warning' : 'normal'} onClose={leave}>
        <Notice icon="eligible" color="eligible" kind="body">
          You paid for your items. Please take them with you.
        </Notice>
        {lowBalance ? (
          <AlertBlock level="warning" title="Low balance">
            {receipt.voice.text}
          </AlertBlock>
        ) : null}
        {receipt.invoice ? <InvoiceDetail invoice={receipt.invoice} bordered={false} share={false} /> : null}
        <PanelText kind="label">New balances</PanelText>
        {receipt.new_balances.map((b) => {
          const card = cardById(state.cards, b.card_id);
          return (
            <View key={b.card_id} style={styles.balance} accessible accessibilityLabel={`${card?.nickname ?? b.card_id}, ${centsForScreenReader(b.balance_cents)}`}>
              <View style={styles.paysWith}>
                {card ? <CardArt type={card.type} size="swatch" /> : null}
                <PanelText>{card?.nickname ?? b.card_id}</PanelText>
              </View>
              <PanelText kind="heading">{formatCents(b.balance_cents)}</PanelText>
            </View>
          );
        })}
        <PanelText kind="small" muted>
          Simulated payment. No real card was charged.
        </PanelText>
        <PanelActions>
          <BigButton label="Save to history" icon="receipt" variant="primary" size="primary" onPress={leave} />
        </PanelActions>
      </InfoPanel>
    </Animated.View>
  );
}

/** Declined simulated payment: red edge, red block, error buzz, and the same words spoken. */
function DeclinedPanel({ message }: { message: string }) {
  const { startCheckout, showView } = useAgent();
  return (
    <InfoPanel title={Phrases.declinedTitle} tone="danger" onClose={() => showView('cart')}>
      <AlertBlock level="danger" title="Declined">
        {message}
      </AlertBlock>
      <PanelActions>
        <BigButton label="Move items to another card" icon="next" variant="primary" size="primary" onPress={startCheckout} />
        <BigButton label="Add a card" icon="add" variant="secondary" onPress={() => showView('add_card')} />
      </PanelActions>
    </InfoPanel>
  );
}

const styles = StyleSheet.create({
  buttons: { gap: Spacing.sm },
  // Paired buttons: same height (cells stretch), wrap to two rows at large text.
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'stretch', gap: Spacing.md },
  cell: { flexDirection: 'column' },
  name: { flexShrink: 1, flexGrow: 1 },
  paysWith: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  chooser: { gap: Spacing.sm },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md, borderRadius: Radius.card, padding: Spacing.md, minHeight: Target.min },
  cardInfo: { flex: 1 },
  suggestedTag: { borderRadius: Radius.pill, paddingHorizontal: Spacing.sm, paddingVertical: 2 },
  totalRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.md },
  rxHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  rxIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  rxNameRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: Spacing.sm },
  rxStrength: { borderRadius: Radius.pill, paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs },
  rxNote: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm, borderRadius: Radius.button, padding: Spacing.md },
  grow: { flexGrow: 1, flexBasis: 110 },
  grow2: { flexGrow: 2, flexBasis: 160 },
  priceRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: Spacing.md, rowGap: Spacing.xs },
  done: { borderRadius: Radius.card, padding: Spacing.lg, alignItems: 'center', gap: Spacing.xs },
  balance: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: Spacing.sm },
});
