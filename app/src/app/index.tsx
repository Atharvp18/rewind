import { useCameraPermissions } from 'expo-camera';
import { useIsFocused } from 'expo-router';
import { useCallback, useRef } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CameraStage, type CameraStageHandle } from '@/components/camera-stage';
import { HealthBanner } from '@/components/health-banner';
import { HomePanels } from '@/components/home-panels';
import { OnboardingFlow } from '@/components/onboarding-flow';
import { ProfileButton } from '@/components/profile-button';
import { TranscriptPill } from '@/components/transcript-pill';
import { VoiceDock, type DockAction } from '@/components/voice-dock';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { Phrases } from '@/lib/phrases';
import { useProfile } from '@/lib/profile';
import { useAgent } from '@/state/agent';

/**
 * The one camera screen (wireframe frames 1 to 3). Layers, back to front:
 * live camera → tap-anywhere capture area → top row (caption pill + profile
 * button) and info panel → half-circle dock.
 */
export default function Home() {
  const { palette } = useA11y();
  const { profile, loaded } = useProfile();
  const { state, beginCapture, scanFrame, sayLocal, showView } = useAgent();
  const [camera, requestCamera] = useCameraPermissions();
  const focused = useIsFocused();
  const stage = useRef<CameraStageHandle>(null);
  const onboardingCapture = useRef<(() => void) | null>(null);

  const onboarding = loaded && !profile.onboarded;
  const busy = state.phase === 'capturing' || state.phase === 'awaiting_scan';
  const granted = !!camera?.granted;

  const scan = useCallback(async () => {
    if (onboardingCapture.current) {
      onboardingCapture.current();
      return;
    }
    if (onboarding || busy || !granted) {
      if (!granted && !onboarding) sayLocal(Phrases.cameraDenied);
      return;
    }
    beginCapture();
    const shot = await stage.current?.capture();
    if (!shot) {
      sayLocal(Phrases.offline);
      return;
    }
    await scanFrame(shot.uri, shot.barcode, shot.discard);
  }, [onboarding, busy, granted, beginCapture, scanFrame, sayLocal]);

  const registerCapture = useCallback((fn: (() => void) | null) => {
    onboardingCapture.current = fn;
  }, []);

  const addingCard = state.view === 'add_card';
  const left: DockAction | undefined = onboarding || addingCard
    ? undefined
    : { label: 'Cart', icon: 'cart', hint: 'Shows your cart, grouped by card.', onPress: () => showView('cart') };
  const right: DockAction | undefined = onboarding || addingCard
    ? undefined
    : {
        label: busy ? 'Looking…' : 'Scan',
        icon: 'scan',
        hint: 'Takes a photo of the item in front of the phone.',
        onPress: () => void scan(),
        disabled: busy,
      };

  return (
    <View style={[styles.root, { backgroundColor: palette.bg }]}>
      <CameraStage ref={stage} granted={granted} active={focused} />

      <Pressable
        style={StyleSheet.absoluteFill}
        onPress={() => void scan()}
        disabled={busy}
        accessibilityRole="button"
        accessibilityLabel={onboarding ? 'Camera. Tap anywhere to take the photo.' : 'Camera. Tap anywhere to scan the item in front of the phone.'}
        accessibilityState={{ busy }}
      />

      <SafeAreaView edges={['top', 'left', 'right']} style={styles.overlay} pointerEvents="box-none">
        <View style={styles.topRow} pointerEvents="box-none">
          <TranscriptPill />
          {/* On top of the pill's right end, so the pill grows out of it (wireframe frame 2). */}
          <View style={styles.profile}>
            <ProfileButton />
          </View>
        </View>

        <View style={styles.panelArea} pointerEvents="box-none">
          <HealthBanner />
          {onboarding ? (
            <OnboardingFlow
              camera={camera}
              requestCamera={requestCamera}
              registerCapture={registerCapture}
              capture={async () => (await stage.current?.capture()) ?? null}
            />
          ) : state.view === 'add_card' ? (
            // Business spec 6.4 / 20.6: link another card, reusing the onboarding card steps.
            <OnboardingFlow
              camera={camera}
              requestCamera={requestCamera}
              registerCapture={registerCapture}
              capture={async () => (await stage.current?.capture()) ?? null}
              startAt="payment"
              onDone={() => showView('camera')}
            />
          ) : (
            <HomePanels />
          )}
        </View>
      </SafeAreaView>

      <VoiceDock left={left} right={right} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  overlay: { flex: 1 },
  topRow: {
    flexDirection: 'row',
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.sm,
  },
  profile: { position: 'absolute', top: Spacing.sm, right: Spacing.lg },
  panelArea: {
    flex: 1,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.md,
    gap: Spacing.md,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
});
