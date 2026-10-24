import { StyleSheet, View } from 'react-native';

import { AlertBlock } from '@/components/alert-block';
import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { CardGroupView } from '@/components/card-group';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Icon } from '@/components/icon';
import { InfoPanel, PanelText, type PanelTone } from '@/components/info-panel';
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
  const live = state.livePrompt?.id === res.voice.prompt_id ? state.livePrompt : null;

  if (res.scan.state === 'unresolved') {
    return (
      <InfoPanel title="Could not confirm this item">
        <PanelText>Try another angle, or tap Talk and say what it is.</PanelText>
        <BigButton label="Scan again" icon="retry" variant="primary" size="primary" onPress={skip} />
      </InfoPanel>
    );
  }

  // Pill bottle: read drug name and strength back; nothing proceeds until confirmed (tech spec 2.3).
  if (res.voice.response_scope === 'confirm_strength') {
    return (
      // Compact on purpose: fits without scrolling at 100–150% text (approved).
      <InfoPanel anchored label="Prescription label read-back">
        <PanelText kind="small" muted>
          From the bottle label · is this right?
        </PanelText>
        <PanelText kind="title">{[product.name, product.size].filter(Boolean).join(' ')}</PanelText>
        <View style={styles.row}>
          <View style={styles.grow}>
            <BigButton label="Yes" icon="check" variant="primary" disabled={!live} onPress={() => answer('yes')} />
          </View>
          <View style={styles.grow}>
            <BigButton label="No" icon="close" onPress={() => answer('no')} />
          </View>
        </View>
        <PanelText kind="small" muted>
          No medical advice. Ask the pharmacist about dosage or safety.
        </PanelText>
      </InfoPanel>
    );
  }

  return (
    <InfoPanel title={product.name} tone={scanTone(rec)} anchored>
      {product.amount_cents != null ? (
        <View style={styles.priceRow}>
          <View accessible accessibilityLabel={`Price ${centsForScreenReader(product.amount_cents)}`}>
            <PanelText kind="display">{formatCents(product.amount_cents)}</PanelText>
          </View>
          <EligibilityBadge eligibility={eligibility} isMedication={product.is_medication} />
        </View>
      ) : (
        <AlertBlock level="warning" title="Price not found">
          Point at the shelf tag, or say the price.
        </AlertBlock>
      )}
      {product.amount_cents == null ? (
        <EligibilityBadge eligibility={eligibility} isMedication={product.is_medication} />
      ) : null}
      {rec ? <Recommendation rec={rec} cards={state.cards} /> : null}
      {rec && needsAnotherCard(rec) ? <AddCardSuggestion /> : null}
      {rec ? (
        <Actions rec={rec} cards={state.cards} enabled={live?.scope === 'confirm_add'} onAdd={addToCart} onSkip={skip} />
      ) : null}
      {rec && rec.decision !== 'blocked' && live?.scope !== 'confirm_add' ? (
        <AlertBlock level="warning" title="Question timed out">
          Tap the caption at the top to hear it again, or scan again.
        </AlertBlock>
      ) : null}
    </InfoPanel>
  );
}

function Recommendation({ rec, cards }: { rec: PaymentRecommendation; cards: Card[] }) {
  const card = cardById(cards, rec.card_id);
  if (rec.decision === 'route_to_hsa' || rec.decision === 'route_to_general') {
    return (
      <PanelText>
        {`Pays with: ${card?.nickname ?? 'card'}`}
        {rec.balance_before_cents != null && card?.type !== 'general'
          ? ` (balance ${formatCents(rec.balance_before_cents)})`
          : ''}
      </PanelText>
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

function Actions({
  rec,
  cards,
  enabled,
  onAdd,
  onSkip,
}: {
  rec: PaymentRecommendation;
  cards: Card[];
  enabled: boolean;
  onAdd: (cardId: string) => void;
  onSkip: () => void;
}) {
  if (rec.decision === 'blocked') {
    return <BigButton label="OK" variant="primary" size="primary" onPress={onSkip} />;
  }
  const options =
    rec.decision === 'ask_user'
      ? rec.card_options.length
        ? rec.card_options
        : rec.reroute
          ? [rec.reroute.to_card_id]
          : []
      : rec.card_id
        ? [rec.card_id]
        : [];
  // One choice: Add and Skip side by side. Several cards: one row each, Skip last.
  return (
    <View style={options.length === 1 ? styles.row : styles.buttons}>
      {options.map((id) => (
        <View key={id} style={options.length === 1 ? styles.grow2 : undefined}>
          <BigButton
            label={rec.decision === 'ask_user' ? `Use ${cardById(cards, id)?.nickname ?? 'this card'}` : 'Add to cart'}
            icon="check"
            variant="primary"
            disabled={!enabled}
            onPress={() => onAdd(id)}
          />
        </View>
      ))}
      <View style={options.length === 1 ? styles.grow : undefined}>
        <BigButton label="Skip" icon="close" onPress={onSkip} />
      </View>
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
        <BigButton label="Close" onPress={dismiss} />
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
      <View style={styles.buttons}>
        <BigButton label="Checkout" icon="next" variant="primary" size="primary" onPress={startCheckout} />
        <BigButton label="Remove last item" icon="undo" onPress={removeLast} />
        {clearPending ? (
          // Destructive: the second tap confirms, bound to the live confirm_clear_cart prompt.
          <BigButton label="Yes, clear everything" icon="alert" variant="danger" onPress={confirmClearCart} />
        ) : (
          <BigButton label="Clear cart" icon="trash" variant="danger" onPress={askClearCart} />
        )}
        <BigButton label="Close" onPress={dismiss} />
      </View>
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
        <BigButton label="Close" onPress={() => showView('camera')} />
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
      <BigButton label="Done" variant="primary" size="primary" onPress={dismiss} />
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
      <View style={styles.buttons}>
        <BigButton label="Move items to another card" icon="next" variant="primary" size="primary" onPress={startCheckout} />
        <BigButton label="Add a card" icon="add" onPress={() => showView('add_card')} />
        <BigButton label="Back to cart" onPress={() => showView('cart')} />
      </View>
    </InfoPanel>
  );
}

const styles = StyleSheet.create({
  buttons: { gap: Spacing.sm },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  grow: { flexGrow: 1, flexBasis: 110 },
  grow2: { flexGrow: 2, flexBasis: 160 },
  priceRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: Spacing.md, rowGap: Spacing.xs },
  done: { borderRadius: Radius.card, padding: Spacing.lg, alignItems: 'center', gap: Spacing.xs },
  balance: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: Spacing.sm },
});
