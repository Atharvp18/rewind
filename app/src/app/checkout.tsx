import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { CardGroupView } from '@/components/card-group';
import { Screen } from '@/components/screen';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { formatCents } from '@/lib/money';
import { useAgent } from '@/state/agent';

export default function Checkout() {
  const { palette } = useA11y();
  const { state, confirmCheckout, startCheckout } = useAgent();
  const { preview, receipt } = state;
  const busy = state.phase === 'submitting';
  const promptLive = !!preview?.voice.prompt_id && state.livePrompt?.id === preview.voice.prompt_id;

  if (receipt) {
    return (
      <Screen
        title="Paid"
        dockLeft={{ label: 'Home', icon: '⌂', href: '/' }}
        dockRight={{ label: 'Scan', icon: '📷', href: '/scan' }}
        action={<BigButton label="Done" variant="primary" size="primary" onPress={() => router.dismissTo('/')} />}>
        <View style={[styles.success, { borderColor: palette.eligible, backgroundColor: palette.eligibleBg }]}>
          <AppText kind="display" color="eligible" accessible={false}>
            ✓
          </AppText>
          <AppText kind="title" color="eligible" accessibilityRole="header">
            Payment complete
          </AppText>
          <AppText kind="small" color="text">
            This was a simulated payment.
          </AppText>
        </View>

        <AppText kind="heading" accessibilityRole="header">
          New balances
        </AppText>
        {receipt.new_balances.map((b) => {
          const card = state.cards.find((c) => c.id === b.card_id);
          return (
            <View key={b.card_id} style={[styles.row, { borderColor: palette.border, backgroundColor: palette.surface }]}>
              <AppText kind="body" style={styles.flex}>
                {card?.nickname ?? b.card_id}
              </AppText>
              <AppText kind="heading">{formatCents(b.balance_cents)}</AppText>
            </View>
          );
        })}
      </Screen>
    );
  }

  return (
    <Screen
      title="Checkout"
      dockLeft={{ label: 'Cart', icon: '🛒', href: '/cart' }}
      dockRight={{ label: 'Home', icon: '⌂', href: '/' }}
      action={
        preview && preview.groups.length ? (
          promptLive ? (
            <BigButton
              label="Confirm payment"
              icon="✓"
              variant="primary"
              size="primary"
              disabled={busy}
              onPress={confirmCheckout}
            />
          ) : (
            <BigButton label="Read the split again" icon="↻" variant="primary" size="primary" onPress={startCheckout} />
          )
        ) : null
      }>
      {!preview ? (
        <AppText kind="body" color="textMuted">
          Getting your split…
        </AppText>
      ) : preview.groups.length === 0 ? (
        <AppText kind="heading">Your cart is empty.</AppText>
      ) : (
        <>
          {preview.issues.map((issue) => (
            <View
              key={issue.rule + issue.message}
              accessibilityRole="alert"
              style={[styles.issue, { borderColor: palette.danger, backgroundColor: palette.dangerBg }]}>
              <AppText kind="label" color="danger">
                ⚠ Card change suggested
              </AppText>
              <AppText kind="body">{issue.message}</AppText>
            </View>
          ))}

          {preview.groups.map((g) => (
            <CardGroupView key={g.card_id} group={g} card={state.cards.find((c) => c.id === g.card_id)} />
          ))}

          <View style={[styles.row, { borderColor: palette.text, backgroundColor: palette.surface, borderWidth: 3 }]}>
            <AppText kind="heading" style={styles.flex}>
              Total, before tax
            </AppText>
            <AppText kind="display">{formatCents(preview.total_cents)}</AppText>
          </View>
          <AppText kind="small" color="textMuted">
            This is a simulated payment. No real card is charged.
          </AppText>
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  success: { borderWidth: 3, borderRadius: Radius.card, padding: Spacing.xl, alignItems: 'center', gap: Spacing.sm },
  issue: { borderWidth: 3, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.sm },
  row: {
    borderWidth: 2,
    borderRadius: Radius.card,
    padding: Spacing.lg,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.sm,
  },
  flex: { flexShrink: 1, flexGrow: 1 },
});
