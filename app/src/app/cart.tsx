import { router, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { CardGroupView } from '@/components/card-group';
import { Screen } from '@/components/screen';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { useAgent } from '@/state/agent';

export default function CartScreen() {
  const { palette } = useA11y();
  const { state, refreshCart, removeLast, askClearCart, confirmClearCart, startCheckout } = useAgent();
  const { cart } = state;
  const empty = cart.groups.length === 0;
  const clearPending = state.livePrompt?.scope === 'confirm_clear_cart';

  useFocusEffect(
    useCallback(() => {
      void refreshCart();
    }, [refreshCart]),
  );

  return (
    <Screen
      title="Cart"
      dockLeft={{ label: 'Home', icon: '⌂', href: '/' }}
      dockRight={{ label: 'Scan', icon: '📷', href: '/scan' }}
      action={
        empty ? (
          <BigButton label="Scan an item" icon="📷" variant="primary" size="primary" onPress={() => router.push('/scan')} />
        ) : (
          <BigButton
            label="Checkout"
            icon="→"
            variant="primary"
            size="primary"
            onPress={async () => {
              await startCheckout();
              router.push('/checkout');
            }}
          />
        )
      }>
      {empty ? (
        <AppText kind="heading">Your cart is empty.</AppText>
      ) : (
        <>
          {cart.groups.map((g) => (
            <CardGroupView key={g.card_id} group={g} card={state.cards.find((c) => c.id === g.card_id)} />
          ))}

          <View
            style={[styles.total, { borderColor: palette.text, backgroundColor: palette.surface }]}
            accessible
            accessibilityLabel={`Total ${centsForScreenReader(cart.total_cents)}, before tax`}>
            <AppText kind="heading">Total</AppText>
            <AppText kind="display">{formatCents(cart.total_cents)}</AppText>
            <AppText kind="small" color="textMuted">
              Before tax
            </AppText>
          </View>

          <View style={styles.secondary}>
            <BigButton label="Remove last item" icon="↩" onPress={removeLast} />
            {clearPending ? (
              // Destructive: second tap confirms, bound to the live confirm_clear_cart prompt.
              <BigButton label="Yes, clear everything" icon="⚠" variant="danger" onPress={confirmClearCart} />
            ) : (
              <BigButton label="Clear cart" icon="🗑" variant="danger" onPress={askClearCart} />
            )}
          </View>
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  total: { borderWidth: 3, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.xs },
  secondary: { gap: Spacing.md },
});
