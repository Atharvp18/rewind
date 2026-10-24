import { LinearGradient } from 'expo-linear-gradient';
import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import type { Card } from '@/lib/api';

/**
 * Card colors by type. They are card colors, like physical cards in a wallet,
 * so they stay the same in every theme.
 *
 * Everyday Visa uses Visa's own colors: Visa Blue #1A1F71 and Visa Gold
 * #F7B600 (Visa POS guidelines; Pantone 280 / 130), fading into Visa's newer
 * digital blue #1434CB. HSA and FSA are account types, not brands, so they
 * get their own colors: deep health green and plum.
 *
 * "VISA" is plain text, not the Visa logo: Visa's guidelines restrict how the
 * mark is reproduced. White text measures 5.3:1 or better on every card.
 */
export const CardBrand = {
  general: { from: '#1A1F71', to: '#1434CB', stripe: '#F7B600', icon: 'card' as const },
  hsa: { from: '#0B5E44', to: '#0E7A57', stripe: null, icon: 'health' as const },
  fsa: { from: '#4E2470', to: '#6B3394', stripe: null, icon: 'health' as const },
};

const TYPE_LABEL: Record<Card['type'], string> = {
  hsa: 'HSA · eligible health items',
  fsa: 'FSA · eligible health items',
  general: 'Credit or debit · everyday',
};

export function cardTypeLabel(type: Card['type']): string {
  return TYPE_LABEL[type];
}

/**
 * A card drawn in its colors.
 *   tile:   a mini card (Profile, onboarding confirm): name, icon, last 4,
 *           network, and an optional value in the corner (e.g. balance).
 *   swatch: a small card chip beside text (cart groups, "Pays with").
 */
export function CardArt({
  type,
  nickname,
  last4,
  size = 'tile',
  value,
}: {
  type: Card['type'];
  nickname?: string;
  last4?: string | null;
  size?: 'tile' | 'swatch';
  /** Tile only: shown large at the bottom left (a balance). */
  value?: ReactNode;
}) {
  const { themeName } = useA11y();
  const b = CardBrand[type];
  // On dark backgrounds the dark card colors need an edge to read as a shape.
  const edge = themeName === 'standard' ? undefined : { borderWidth: 1, borderColor: 'rgba(255,255,255,0.45)' };

  if (size === 'swatch') {
    return (
      <View accessible={false} importantForAccessibility="no-hide-descendants" style={[styles.swatch, edge]}>
        <LinearGradient colors={[b.from, b.to]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
        {b.stripe ? <View style={[styles.swatchStripe, { backgroundColor: b.stripe }]} /> : null}
      </View>
    );
  }

  return (
    <View style={[styles.tile, edge]}>
      <LinearGradient colors={[b.from, b.to]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
      <View style={styles.row}>
        <AppText kind="label" accessible={false} style={[styles.white, styles.flex]} numberOfLines={1}>
          {nickname ?? (type === 'general' ? 'Visa' : type.toUpperCase())}
        </AppText>
        <Icon name={b.icon} size={24} color="onPrimary" />
      </View>
      <AppText kind="small" accessible={false} style={styles.whiteMuted}>
        {TYPE_LABEL[type]}
      </AppText>
      <View style={[styles.row, styles.bottom]}>
        <View style={styles.flex}>
          {value != null ? (
            <AppText kind="title" accessible={false} style={styles.white}>
              {value}
            </AppText>
          ) : null}
          {last4 ? (
            <AppText kind="small" accessible={false} style={styles.whiteMuted}>
              {`•••• ${last4}`}
            </AppText>
          ) : null}
        </View>
        <AppText accessible={false} style={styles.network}>
          VISA
        </AppText>
      </View>
      {b.stripe ? <View style={[styles.tileStripe, { backgroundColor: b.stripe }]} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  tile: { borderRadius: Radius.card, overflow: 'hidden', padding: Spacing.lg, gap: Spacing.xs, minHeight: 112 },
  row: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  bottom: { alignItems: 'flex-end', marginTop: Spacing.sm },
  flex: { flex: 1 },
  white: { color: '#FFFFFF' },
  whiteMuted: { color: 'rgba(255,255,255,0.92)' },
  // Plain-text network label (not the Visa logo).
  network: { color: '#FFFFFF', fontSize: 18, lineHeight: 22, fontWeight: '900', fontStyle: 'italic', letterSpacing: 1 },
  tileStripe: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 5 },
  swatch: { width: 40, height: 26, borderRadius: 5, overflow: 'hidden' },
  swatchStripe: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 4 },
});
