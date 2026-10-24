import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Screen } from '@/components/screen';
import { Radius, Spacing, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { useAgent } from '@/state/agent';

export default function Home() {
  const { palette } = useA11y();
  const { state } = useAgent();
  const itemCount = state.cart.groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <Screen
      title="Rewind"
      back={false}
      dockLeft={{ label: 'Cart', icon: '🛒', href: '/cart' }}
      dockRight={{ label: 'Scan', icon: '📷', href: '/scan' }}>
      {!state.caption ? (
        <AppText kind="body" color="textMuted">
          Point your phone at a product to hear what it is, what it costs, and which card to pay with.
        </AppText>
      ) : null}

      <View style={styles.tiles}>
        <Tile
          icon="📷"
          label="Scan item"
          hint="Opens the camera"
          onPress={() => router.push('/scan')}
          primary
        />
        <Tile
          icon="🛒"
          label={itemCount ? `Cart · ${itemCount}` : 'Cart'}
          a11yLabel={`Cart, ${itemCount} ${itemCount === 1 ? 'item' : 'items'}`}
          onPress={() => router.push('/cart')}
        />
      </View>

      <View
        style={[styles.balances, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <AppText kind="heading" accessibilityRole="header">
          Your cards
        </AppText>
        {state.cards.length === 0 ? (
          <AppText kind="body" color="textMuted">
            No cards linked yet.
          </AppText>
        ) : (
          state.cards.map((c) => (
            <View
              key={c.id}
              style={styles.balanceRow}
              accessible
              accessibilityLabel={`${c.nickname}, balance ${centsForScreenReader(c.balance_cents)}`}>
              <AppText kind="body" style={styles.flex}>
                {c.type === 'general' ? '💳' : '✚'} {c.nickname}
              </AppText>
              <AppText kind="heading">{formatCents(c.balance_cents)}</AppText>
            </View>
          ))
        )}
      </View>

      <AppText kind="small" color="textMuted">
        Simulated payments. All card and insurance data is mock.
      </AppText>
    </Screen>
  );
}

function Tile({
  icon,
  label,
  a11yLabel,
  hint,
  onPress,
  primary,
}: {
  icon: string;
  label: string;
  a11yLabel?: string;
  hint?: string;
  onPress: () => void;
  primary?: boolean;
}) {
  const { palette } = useA11y();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={a11yLabel ?? label}
      accessibilityHint={hint}
      onPress={onPress}
      style={({ pressed }) => [
        styles.tile,
        {
          backgroundColor: primary ? palette.primary : palette.surface,
          borderColor: primary ? palette.primary : palette.border,
          opacity: pressed ? 0.85 : 1,
        },
      ]}>
      <AppText kind="title" color={primary ? 'onPrimary' : 'text'} accessible={false}>
        {icon}
      </AppText>
      <AppText kind="label" color={primary ? 'onPrimary' : 'text'} style={styles.center} accessible={false}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tiles: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.md },
  tile: {
    flexGrow: 1,
    flexBasis: 140,
    minHeight: Target.tile,
    borderRadius: Radius.card,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
    gap: Spacing.sm,
  },
  balances: { borderWidth: 2, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.md },
  balanceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.sm,
  },
  flex: { flexShrink: 1, flexGrow: 1 },
  center: { textAlign: 'center' },
});
