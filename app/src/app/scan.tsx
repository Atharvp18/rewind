import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import { File } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { useIsFocused } from 'expo-router';
import { useEffect, useRef } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { SlideInDown } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { EligibilityBadge } from '@/components/eligibility-badge';
import { Screen } from '@/components/screen';
import { Radius, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import type { Card, PaymentRecommendation, ScanResponse } from '@/lib/api';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { Phrases } from '@/lib/phrases';
import { useAgent } from '@/state/agent';

const LONGEST_EDGE = 1280;
const JPEG_QUALITY = 0.7;
const BARCODE_FRESH_MS = 5000;

export default function Scan() {
  const [permission, requestPermission] = useCameraPermissions();
  const focused = useIsFocused();
  const { state, beginCapture, scanFrame, sayLocal } = useAgent();
  const camera = useRef<CameraView>(null);
  const barcode = useRef<{ data: string; at: number } | null>(null);
  const toldDenied = useRef(false);

  const denied = permission && !permission.granted && !permission.canAskAgain;

  useEffect(() => {
    if (denied && !toldDenied.current) {
      toldDenied.current = true;
      sayLocal(Phrases.cameraDenied);
    }
  }, [denied, sayLocal]);

  const busy = state.phase === 'capturing' || state.phase === 'awaiting_scan';

  const onBarcode = (r: BarcodeScanningResult) => {
    barcode.current = { data: r.data.replace(/\D/g, ''), at: Date.now() };
  };

  const capture = async () => {
    if (busy || !camera.current) return;
    beginCapture();
    const toDelete: string[] = [];
    const discard = () => {
      // Frames are never retained (decision 14): delete every temp file now.
      for (const uri of toDelete) {
        try {
          new File(uri).delete();
        } catch {
          // already gone
        }
      }
    };
    try {
      const shot = await camera.current.takePictureAsync({ quality: JPEG_QUALITY });
      toDelete.push(shot.uri);
      const scale = LONGEST_EDGE / Math.max(shot.width, shot.height);
      const ctx = ImageManipulator.manipulate(shot.uri);
      if (scale < 1) ctx.resize({ width: Math.round(shot.width * scale) });
      const img = await (await ctx.renderAsync()).saveAsync({ compress: JPEG_QUALITY, format: SaveFormat.JPEG });
      toDelete.push(img.uri);
      const code = barcode.current && Date.now() - barcode.current.at < BARCODE_FRESH_MS ? barcode.current.data : null;
      barcode.current = null;
      await scanFrame(img.uri, code, discard);
    } catch {
      discard();
      sayLocal(Phrases.offline);
    }
  };

  return (
    <Screen
      title="Scan"
      scroll={false}
      dockLeft={{ label: 'Cart', icon: '🛒', href: '/cart' }}
      dockRight={{ label: 'Home', icon: '⌂', href: '/' }}>
      {!permission ? null : !permission.granted ? (
        <PermissionPanel canAsk={permission.canAskAgain} onAsk={requestPermission} />
      ) : (
        <View style={styles.cameraWrap}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={capture}
            disabled={busy}
            accessibilityRole="button"
            accessibilityLabel="Camera. Tap anywhere to scan the item in front of the phone."
            accessibilityState={{ busy }}>
            <CameraView
              ref={camera}
              style={StyleSheet.absoluteFill}
              facing="back"
              active={focused}
              animateShutter={false}
              barcodeScannerSettings={{ barcodeTypes: ['ean13', 'upc_a', 'upc_e'] }}
              onBarcodeScanned={onBarcode}
            />
            <ScanHint busy={busy} />
          </Pressable>
          {state.lastScan && !busy ? <ResultCard res={state.lastScan} /> : null}
        </View>
      )}
    </Screen>
  );
}

function ScanHint({ busy }: { busy: boolean }) {
  const { palette } = useA11y();
  return (
    <View style={styles.hintWrap} pointerEvents="none">
      <View style={[styles.hint, { backgroundColor: palette.scrim }]}>
        <AppText kind="label" style={{ color: '#FFFFFF', textAlign: 'center' }}>
          {busy ? 'Looking…' : 'Tap anywhere to scan'}
        </AppText>
      </View>
    </View>
  );
}

function PermissionPanel({ canAsk, onAsk }: { canAsk: boolean; onAsk: () => void }) {
  const { palette } = useA11y();
  return (
    <View style={[styles.panel, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      <AppText kind="heading" accessibilityRole="header">
        📷 Camera is off
      </AppText>
      <AppText kind="body">{Phrases.cameraDenied}</AppText>
      {canAsk ? (
        <BigButton label="Allow camera" variant="primary" size="primary" onPress={onAsk} />
      ) : (
        <BigButton
          label="Open phone settings"
          variant="primary"
          size="primary"
          onPress={() => Linking.openSettings()}
        />
      )}
    </View>
  );
}

function cardById(cards: Card[], id: string | null | undefined) {
  return cards.find((c) => c.id === id);
}

function ResultCard({ res }: { res: ScanResponse }) {
  const { palette, reduceMotion } = useA11y();
  const { state, addToCart, skip } = useAgent();
  const { product, eligibility } = res.scan;
  const rec = res.recommendation;
  const promptLive = state.livePrompt?.scope === 'confirm_add' && state.livePrompt.id === res.voice.prompt_id;

  return (
    <Animated.View
      entering={reduceMotion ? undefined : SlideInDown.duration(200)}
      style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.text }]}
      accessibilityViewIsModal={false}>
      <ScrollView contentContainerStyle={styles.cardBody}>
      {res.scan.state === 'unresolved' ? (
        <>
          <AppText kind="title" accessibilityRole="header">
            Could not confirm this item
          </AppText>
          <AppText kind="body">Try another angle, or tap Talk and say what it is.</AppText>
          <BigButton label="Scan again" icon="↻" variant="primary" size="primary" onPress={skip} />
        </>
      ) : (
        <>
          <AppText kind="title" accessibilityRole="header">
            {product.name}
          </AppText>
          {product.amount_cents != null ? (
            <AppText kind="display" accessibilityLabel={`Price ${centsForScreenReader(product.amount_cents)}`}>
              {formatCents(product.amount_cents)}
            </AppText>
          ) : (
            <AppText kind="heading" color="danger">
              ⚠ Price not found. Point at the shelf tag, or say the price.
            </AppText>
          )}
          <EligibilityBadge eligibility={eligibility} isMedication={product.is_medication} />
          {rec ? <Recommendation rec={rec} cards={state.cards} /> : null}
          {rec ? (
            <Actions rec={rec} cards={state.cards} enabled={promptLive} onAdd={addToCart} onSkip={skip} />
          ) : null}
          {!promptLive && rec && rec.decision !== 'blocked' ? (
            <AppText kind="small" color="textMuted">
              The question timed out. Tap Talk and say “repeat that”, or scan again.
            </AppText>
          ) : null}
        </>
      )}
      </ScrollView>
    </Animated.View>
  );
}

function Recommendation({ rec, cards }: { rec: PaymentRecommendation; cards: Card[] }) {
  const card = cardById(cards, rec.card_id);
  if (rec.decision === 'route_to_hsa' || rec.decision === 'route_to_general') {
    return (
      <AppText kind="body">
        Pays with: <AppText kind="label">{card?.nickname ?? 'card'}</AppText>
        {rec.balance_before_cents != null && card?.type !== 'general'
          ? ` (balance ${formatCents(rec.balance_before_cents)})`
          : ''}
      </AppText>
    );
  }
  if (rec.decision === 'blocked') {
    return (
      <AppText kind="body" color="danger">
        ⚠ This item can’t be added. Listen to Rewind for what to do next.
      </AppText>
    );
  }
  if (rec.reroute) {
    const from = cardById(cards, rec.reroute.from_card_id);
    return (
      <AppText kind="body" color="danger">
        ⚠ Your {from?.nickname ?? 'HSA card'} balance
        {rec.balance_before_cents != null ? ` of ${formatCents(rec.balance_before_cents)}` : ''} does not cover
        this item.
      </AppText>
    );
  }
  return <AppText kind="body">Which card would you like to use?</AppText>;
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

  return (
    <View style={styles.actions}>
      {options.map((id) => {
        const c = cardById(cards, id);
        const label = rec.decision === 'ask_user' ? `Use ${c?.nickname ?? id}` : 'Add to cart';
        return (
          <BigButton
            key={id}
            label={label}
            icon="✓"
            variant="primary"
            size="primary"
            disabled={!enabled}
            onPress={() => onAdd(id)}
          />
        );
      })}
      <BigButton label="Skip" icon="✕" onPress={onSkip} />
    </View>
  );
}

const styles = StyleSheet.create({
  cameraWrap: {
    flex: 1,
    minHeight: 280,
    borderRadius: Radius.card,
    overflow: 'hidden',
    backgroundColor: '#000000',
  },
  hintWrap: { position: 'absolute', top: Spacing.lg, left: 0, right: 0, alignItems: 'center' },
  hint: { borderRadius: Radius.pill, paddingVertical: Spacing.sm, paddingHorizontal: Spacing.xl },
  panel: { borderWidth: 2, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.lg },
  card: {
    position: 'absolute',
    left: Spacing.sm,
    right: Spacing.sm,
    bottom: Spacing.sm,
    maxHeight: '92%',
    borderWidth: 3,
    borderRadius: Radius.card,
    overflow: 'hidden',
  },
  cardBody: { padding: Spacing.lg, gap: Spacing.md },
  actions: { gap: Spacing.md },
});
