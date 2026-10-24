import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { useEffect } from 'react';

import { AppText } from '@/components/app-text';
import { CardArt } from '@/components/card-art';
import { Icon } from '@/components/icon';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Motion, Radius, Spacing } from '@/constants/theme';
import type { Card, CartGroup, CartItem } from '@/lib/api';
import { useA11y } from '@/lib/a11y';
import { centsForScreenReader, formatCents } from '@/lib/money';

/** Width of the Keep / Remove actions revealed when a row slides left. */
const ACTIONS_W = 176;

/**
 * One cart line. Opening it slides the line to the left (the cart stays where it is) and
 * reveals Keep and Remove at the right edge, like a swipe action in Mail or Messages.
 */
function ItemRow({
  item: it,
  open,
  onPress,
  onKeep,
  onRemove,
}: {
  item: CartItem;
  open: boolean;
  onPress?: (id: string) => void;
  onKeep?: () => void;
  onRemove?: () => void;
}) {
  const { palette, reduceMotion } = useA11y();
  const x = useSharedValue(0);
  useEffect(() => {
    x.value = withTiming(open ? -ACTIONS_W : 0, { duration: reduceMotion ? 0 : Motion.panel });
  }, [open, reduceMotion, x]);
  const slide = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }] }));

  return (
    <View style={[styles.itemWrap, { borderTopColor: palette.border }]}>
      {open ? (
        <View style={[styles.actions, { width: ACTIONS_W }]}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Keep ${it.display_name}`}
            onPress={onKeep}
            style={[styles.action, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Icon name="check" size={22} />
            <AppText kind="small" style={styles.actionText}>Keep</AppText>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Remove ${it.display_name}`}
            onPress={onRemove}
            style={[styles.action, { backgroundColor: palette.dangerBg, borderColor: palette.dangerEdge }]}>
            <Icon name="trash" size={22} color="danger" />
            <AppText kind="small" color="danger" style={styles.actionText}>Remove</AppText>
          </Pressable>
        </View>
      ) : null}
      <Animated.View style={[styles.item, { backgroundColor: palette.surfaceAlt }, slide]}>
        <Pressable
          disabled={!onPress}
          onPress={() => (open ? onKeep?.() : onPress?.(it.id))}
          accessibilityRole={onPress ? 'button' : undefined}
          accessibilityLabel={`${it.display_name}, ${centsForScreenReader(it.amount_cents)}`}
          accessibilityHint={onPress ? 'Hear this item and choose whether to remove it' : undefined}
          style={styles.itemPress}>
          <View style={styles.itemRow}>
            <AppText kind="body" style={styles.itemName}>
              {it.display_name}
            </AppText>
            <View style={styles.price}>
              <AppText kind="label">{formatCents(it.amount_cents)}</AppText>
              {onPress ? <Icon name="next" size={18} color="textMuted" /> : null}
            </View>
          </View>
          <EligibilityBadge eligibility={{ label: it.eligibility_label }} compact />
        </Pressable>
      </Animated.View>
    </View>
  );
}

/** One payment card's items and subtotal (Cart and Checkout screens). */
export function CardGroupView({
  group,
  card,
  onItemPress,
  openItemId,
  onKeep,
  onRemove,
}: {
  group: CartGroup;
  card?: Card;
  /** Makes each item a button (Cart: tap to hear it and decide whether to keep it). */
  onItemPress?: (itemId: string) => void;
  /** The item whose row is slid open to Keep / Remove. */
  openItemId?: string | null;
  onKeep?: () => void;
  onRemove?: () => void;
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
        <ItemRow
          key={it.id}
          item={it}
          open={openItemId === it.id}
          onPress={onItemPress}
          onKeep={onKeep}
          onRemove={onRemove}
        />
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
  itemWrap: { borderTopWidth: 1, overflow: 'hidden' },
  item: { paddingVertical: Spacing.md },
  itemPress: { gap: Spacing.sm },
  actions: { position: 'absolute', right: 0, top: 0, bottom: 0, flexDirection: 'row', gap: Spacing.xs, alignItems: 'center' },
  action: { flex: 1, alignSelf: 'stretch', marginVertical: Spacing.xs, borderRadius: Radius.card, borderWidth: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
  actionText: { fontWeight: '700' },
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
