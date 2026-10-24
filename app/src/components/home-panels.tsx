import { StyleSheet, View } from 'react-native';

import { AlertBlock } from '@/components/alert-block';
import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { CardArt } from '@/components/card-art';
import { CardGroupView } from '@/components/card-group';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Icon } from '@/components/icon';
import { InfoPanel, PanelActions, PanelText, type PanelTone } from '@/components/info-panel';
import { Radius, Spacing } from '@/constants/theme';
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
    return (
      <InfoPanel label="Prescription label read-back">
        <PanelText kind="small" muted>
          From the bottle label · is this right?
        </PanelText>
        <PanelText kind="title">{[product.name, product.size].filter(Boolean).join(' ')}</PanelText>
        <PanelText kind="small" muted>
          No medical advice. Ask the pharmacist about dosage or safety.
        </PanelText>
        <PanelActions>
          <YesNo yes="Yes, that's right" onYes={() => answer('yes')} onNo={() => answer('no')} busy={busy} />
        </PanelActions>
      </InfoPanel>
    );
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
      {rec ? (
        <PanelActions>
          <Actions rec={rec} cards={state.cards} busy={busy} onAdd={addToCart} onSkip={skip} />
        </PanelActions>
      ) : null}
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

/** Yes / No side by side: the primary answer wider, 12 pt apart so they are hard to mis-tap (2.5.8). */
function YesNo({
  yes,
  no = 'No',
  onYes,
  onNo,
  busy,
}: {
  yes: string;
  no?: string;
  onYes: () => void;
  onNo: () => void;
  busy?: boolean;
}) {
  return (
    <View style={styles.row}>
      <View style={[styles.grow2, styles.cell]}>
        <BigButton label={yes} icon="check" variant="primary" disabled={busy} onPress={onYes} stretch />
      </View>
      <View style={[styles.grow, styles.cell]}>
        <BigButton label={no} icon="close" disabled={busy} onPress={onNo} stretch />
      </View>
    </View>
  );
}

/**
 * Buttons use the same words as the spoken question (WCAG 3.2.4):
 * "Want to use your HSA card?" → "Yes, use HSA card" / "No".
 */
function Actions({
  rec,
  cards,
  busy,
  onAdd,
  onSkip,
}: {
  rec: PaymentRecommendation;
  cards: Card[];
  busy: boolean;
  onAdd: (cardId: string) => void;
  onSkip: () => void;
}) {
  if (rec.decision === 'blocked') {
    return <BigButton label="OK" variant="primary" size="primary" onPress={onSkip} />;
  }
  const nick = (id: string | null | undefined) => cardById(cards, id)?.nickname ?? 'this card';
  if (rec.decision === 'route_to_hsa' && rec.card_id) {
    return <YesNo yes={`Yes, use ${nick(rec.card_id)}`} onYes={() => onAdd(rec.card_id!)} onNo={onSkip} busy={busy} />;
  }
  if (rec.decision === 'route_to_general' && rec.card_id) {
    return <YesNo yes={`Yes, add to ${nick(rec.card_id)}`} onYes={() => onAdd(rec.card_id!)} onNo={onSkip} busy={busy} />;
  }
  const options = rec.card_options.length ? rec.card_options : rec.reroute ? [rec.reroute.to_card_id] : [];
  if (options.length === 1) {
    return <YesNo yes={`Yes, use ${nick(options[0])}`} onYes={() => onAdd(options[0])} onNo={onSkip} busy={busy} />;
  }
  return (
    <View style={styles.buttons}>
      {options.map((id) => (
        <BigButton key={id} label={`Use ${nick(id)}`} icon="check" variant="primary" disabled={busy} onPress={() => onAdd(id)} />
      ))}
      <BigButton label="Skip" icon="close" disabled={busy} onPress={onSkip} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Cart
// ---------------------------------------------------------------------------

function CartPanel() {
  const { state, startCheckout, removeLast, askClearCart, confirmClearCart, dismiss } = useAgent();
  const { cart } = state;
  const clearPending = state.livePrompt?.scope === 'confirm_clear_cart';

  if (!cart.groups.length) {
    return (
      <InfoPanel title="Your cart is empty">
        <PanelText>Point your phone at a product and tap anywhere to scan.</PanelText>
        <PanelActions>
          <BigButton label="Close" onPress={dismiss} />
        </PanelActions>
      </InfoPanel>
    );
  }
  return (
    <InfoPanel title="Your cart">
      {cart.groups.map((g) => (
        <CardGroupView key={g.card_id} group={g} card={cardById(state.cards, g.card_id)} />
      ))}
      <View accessible accessibilityLabel={`Total ${centsForScreenReader(cart.total_cents)}, before tax`}>
        <PanelText kind="label">Total, before tax</PanelText>
        <PanelText kind="display">{formatCents(cart.total_cents)}</PanelText>
      </View>
      <PanelActions>
        <BigButton label="Checkout" icon="next" variant="primary" size="primary" onPress={startCheckout} />
        <BigButton label="Remove last item" icon="undo" onPress={removeLast} />
        {clearPending ? (
          // Destructive: the second tap confirms, bound to the live confirm_clear_cart prompt.
          <BigButton label="Yes, clear everything" icon="alert" variant="danger" onPress={confirmClearCart} />
        ) : (
          <BigButton label="Clear cart" icon="trash" variant="danger" onPress={askClearCart} />
        )}
        <BigButton label="Close" onPress={dismiss} />
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

  if (!preview) {
    return (
      <InfoPanel title="Checkout">
        <PanelText>Getting your split…</PanelText>
      </InfoPanel>
    );
  }
  if (!preview.groups.length) {
    return (
      <InfoPanel title="Your cart is empty">
        <PanelActions>
          <BigButton label="Close" onPress={() => showView('camera')} />
        </PanelActions>
      </InfoPanel>
    );
  }

  const live = !!preview.voice.prompt_id && state.livePrompt?.id === preview.voice.prompt_id;
  const reroute = preview.issues.length > 0;

  return (
    <InfoPanel title="Checkout" tone={reroute ? 'warning' : 'normal'}>
      {preview.issues.map((issue) => (
        <AlertBlock key={issue.rule + issue.message} level="warning" title="Suggestion: change cards">
          {issue.message}
        </AlertBlock>
      ))}
      {preview.issues.some((i) => i.rule === 'nothing_covers') ? <AddCardSuggestion /> : null}
      {preview.groups.map((g) => (
        <CardGroupView key={g.card_id} group={g} card={cardById(state.cards, g.card_id)} />
      ))}
      <View accessible accessibilityLabel={`Total ${centsForScreenReader(preview.total_cents)}, before tax`}>
        <PanelText kind="label">Total, before tax</PanelText>
        <PanelText kind="display">{formatCents(preview.total_cents)}</PanelText>
      </View>
      <PanelText kind="small" muted>
        This is a simulated payment. No real card is charged.
      </PanelText>
      <PanelActions>
      {!live ? (
        <BigButton label="Read the split again" icon="retry" variant="primary" size="primary" onPress={startCheckout} />
      ) : reroute ? (
        <View style={styles.buttons}>
          <BigButton label="Yes, move the items" icon="check" variant="primary" size="primary" disabled={busy} onPress={() => confirmCheckout(true)} />
          <BigButton label="No, keep my cards" disabled={busy} onPress={() => confirmCheckout(false)} />
        </View>
      ) : (
        <View style={styles.buttons}>
          <BigButton label="Confirm payment" icon="check" variant="primary" size="primary" disabled={busy} onPress={() => confirmCheckout(true)} />
          <BigButton label="Not now" onPress={() => showView('cart')} />
        </View>
      )}
      </PanelActions>
    </InfoPanel>
  );
}

function ReceiptPanel() {
  const { palette } = useA11y();
  const { state, dismiss } = useAgent();
  const receipt = state.receipt!;
  const lowBalance = receipt.voice.priority === 'alert';
  return (
    <InfoPanel title="Payment complete" tone={lowBalance ? 'warning' : 'normal'}>
      <View style={[styles.done, { backgroundColor: palette.eligibleBg, borderColor: palette.eligible, borderWidth: palette.controlBorderWidth }]}>
        <Icon name="eligible" size={56} color="eligible" strokeWidth={2.5} />
        <AppText kind="small" color="text">
          This was a simulated payment.
        </AppText>
      </View>
      {lowBalance ? (
        <AlertBlock level="warning" title="Low balance">
          {receipt.voice.text}
        </AlertBlock>
      ) : null}
      <PanelText kind="heading">New balances</PanelText>
      {receipt.new_balances.map((b) => (
        <View key={b.card_id} style={styles.balance}>
          <PanelText>{cardById(state.cards, b.card_id)?.nickname ?? b.card_id}</PanelText>
          <PanelText kind="heading">{formatCents(b.balance_cents)}</PanelText>
        </View>
      ))}
      <PanelActions>
        <BigButton label="Done" variant="primary" size="primary" onPress={dismiss} />
      </PanelActions>
    </InfoPanel>
  );
}

/** Declined simulated payment: red edge, red block, error buzz, and the same words spoken. */
function DeclinedPanel({ message }: { message: string }) {
  const { startCheckout, showView } = useAgent();
  return (
    <InfoPanel title={Phrases.declinedTitle} tone="danger">
      <AlertBlock level="danger" title="Declined">
        {message}
      </AlertBlock>
      <PanelActions>
        <BigButton label="Move items to another card" icon="next" variant="primary" size="primary" onPress={startCheckout} />
        <BigButton label="Add a card" icon="add" onPress={() => showView('add_card')} />
        <BigButton label="Back to cart" onPress={() => showView('cart')} />
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
  grow: { flexGrow: 1, flexBasis: 110 },
  grow2: { flexGrow: 2, flexBasis: 160 },
  priceRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: Spacing.md, rowGap: Spacing.xs },
  done: { borderRadius: Radius.card, padding: Spacing.lg, alignItems: 'center', gap: Spacing.xs },
  balance: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: Spacing.sm },
});
