import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { CardArt } from '@/components/card-art';
import { Icon } from '@/components/icon';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Radius, Spacing } from '@/constants/theme';
import type { Card, CartGroup } from '@/lib/api';
import { useA11y } from '@/lib/a11y';
import { centsForScreenReader, formatCents } from '@/lib/money';

/** One payment card's items and subtotal (Cart and Checkout screens). */
export function CardGroupView({
  group,
  card,
  onItemPress,
}: {
  group: CartGroup;
  card?: Card;
  /** Makes each item a button (Cart: tap to hear it and decide whether to keep it). */
  onItemPress?: (itemId: string) => void;
}) {
  const { palette } = useA11y();
  const count = `${group.items.length} ${group.items.length === 1 ? 'item' : 'items'}`;
  return (
    <View
      style={[styles.group, { backgroundColor: palette.surfaceAlt, borderColor: palette.border, borderWidth: palette.controlBorderWidth }]}
      accessibilityLabel={`${group.nickname}. ${count}. Subtotal ${centsForScreenReader(group.subtotal_cents)}.`}>
      <View style={styles.head}>
        <View style={styles.titleRow}>
          {card ? <CardArt type={card.type} size="swatch" /> : null}
          <AppText kind="heading" accessibilityRole="header" style={styles.itemName}>
            {group.nickname}
          </AppText>
        </View>
        {card ? (
          <AppText kind="small" color="textMuted">
            Balance {formatCents(card.balance_cents)}
          </AppText>
        ) : null}
      </View>

      {group.items.map((it) => (
        <Pressable
          key={it.id}
          disabled={!onItemPress}
          onPress={() => onItemPress?.(it.id)}
          style={({ pressed }) => [
            styles.item,
            { borderTopColor: palette.border, opacity: pressed ? 0.7 : 1 },
          ]}
          accessibilityRole={onItemPress ? 'button' : undefined}
          accessibilityLabel={`${it.display_name}, ${centsForScreenReader(it.amount_cents)}`}
          accessibilityHint={onItemPress ? 'Hear this item and choose whether to remove it' : undefined}>
          <View style={styles.itemRow}>
            <AppText kind="body" style={styles.itemName}>
              {it.display_name}
            </AppText>
            <View style={styles.price}>
              <AppText kind="label">{formatCents(it.amount_cents)}</AppText>
              {onItemPress ? <Icon name="next" size={18} color="textMuted" /> : null}
            </View>
          </View>
          <EligibilityBadge eligibility={{ label: it.eligibility_label }} compact />
        </Pressable>
      ))}

      <View style={[styles.subtotal, { borderTopColor: palette.text }]}>
        <AppText kind="label">Subtotal · {count}</AppText>
        <AppText kind="heading">{formatCents(group.subtotal_cents)}</AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: { borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.md },
  head: { gap: Spacing.xs },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  item: { borderTopWidth: 1, paddingTop: Spacing.md, gap: Spacing.sm },
  itemRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: Spacing.sm },
  price: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  itemName: { flexShrink: 1, flexGrow: 1 },
  subtotal: {
    borderTopWidth: 2,
    paddingTop: Spacing.md,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: Spacing.sm,
  },
});
