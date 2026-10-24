import { requestRecordingPermissionsAsync, getRecordingPermissionsAsync } from 'expo-audio';
import type { PermissionResponse } from 'expo-camera';
import { useEffect, useRef, useState } from 'react';
import { Linking, StyleSheet, TextInput, View } from 'react-native';

import { BigButton } from '@/components/big-button';
import type { Capture } from '@/components/camera-stage';
import { Notice } from '@/components/icon';
import { InfoPanel, PanelText } from '@/components/info-panel';
import { Radius, Spacing, Target, Type } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import * as api from '@/lib/api';
import type { Card, CardNetwork, CardScanResult } from '@/lib/api';
import { haptic } from '@/lib/haptics';
import { Onboarding as Say } from '@/lib/phrases';
import { DEMO_MODE, DEMO_PHONE, useProfile, type Insurance } from '@/lib/profile';
import { useAgent } from '@/state/agent';

type Step =
  | 'perm_camera'
  | 'perm_mic'
  | 'name'
  | 'name_confirm'
  | 'phone'
  | 'insurance'
  | 'insurance_confirm'
  | 'payment'
  | 'payment_type'
  | 'payment_confirm'
  | 'payment_more'
  | 'done';

type Payment = NonNullable<CardScanResult['payment']>;

const YES = /\b(yes|yeah|yep|correct|right|sure|ok|okay|continue)\b/i;
const NO = /\b(no|nope|wrong|not)\b/i;

const NETWORK_NAME: Record<CardNetwork, string> = {
  visa: 'Visa',
  mastercard: 'Mastercard',
  amex: 'American Express',
  discover: 'Discover',
  other: 'card',
};

function spokenCard(p: Payment): string {
  if (p.card_type === 'hsa') return 'an HSA card';
  if (p.card_type === 'fsa') return 'an FSA card';
  return p.network && p.network !== 'other' ? `a ${NETWORK_NAME[p.network]} card` : 'a payment card';
}

function nicknameFor(type: Card['type'], network: CardNetwork | null, kind?: 'credit' | 'debit'): string {
  if (type === 'hsa') return 'HSA card';
  if (type === 'fsa') return 'FSA card';
  const brand = network && network !== 'other' ? NETWORK_NAME[network] : 'Card';
  return `${brand} ${kind ?? 'credit'}`;
}

function splitName(transcript: string): { first: string; last: string } | null {
  const words = transcript
    .replace(/^(my name is|i am|i'm|it's|this is)\s+/i, '')
    .replace(/[^\p{L}\s'-]/gu, '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
  if (!words.length) return null;
  return { first: words[0], last: words.slice(1).join(' ') };
}

/**
 * Frame 1: voice-guided first launch. Every step is spoken, captioned, and has
 * tap buttons, so it works by voice, by touch, or with a screen reader.
 * The camera stays live underneath so cards can be framed.
 */
export function OnboardingFlow({
  camera,
  requestCamera,
  registerCapture,
  capture,
  startAt,
  onDone,
}: {
  camera: PermissionResponse | null;
  requestCamera: () => Promise<PermissionResponse>;
  /** Lets a tap anywhere on the camera take the card photo. */
  registerCapture: (fn: (() => void) | null) => void;
  capture: () => Promise<Capture | null>;
  /** Add-a-card mode: start at card capture and call onDone instead of finishing onboarding. */
  startAt?: 'payment';
  onDone?: () => void;
}) {
  const { sayLocal, setListenHandler, refreshCards } = useAgent();
  const { profile, update } = useProfile();
  const [chosen, setStep] = useState<Step | null>(null);
  // The first step depends on whether camera permission is already granted.
  const step: Step | null =
    chosen ?? startAt ?? (camera ? (camera.granted ? 'perm_mic' : 'perm_camera') : null);
  // During onboarding the first card asked for is the HSA/FSA card; when adding later it can be any card.
  const firstCard = !startAt;
  const [name, setName] = useState<{ first: string; last: string } | null>(null);
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState('');
  const [insurance, setInsurance] = useState<Insurance | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [debitOrCredit, setDebitOrCredit] = useState<'credit' | 'debit' | undefined>();
  const [cardsAdded, setCardsAdded] = useState(0);
  const [reading, setReading] = useState(false);
  const busy = useRef(false);

  // Skip the mic step when already granted.
  useEffect(() => {
    if (step !== 'perm_mic') return;
    getRecordingPermissionsAsync().then((p) => p.granted && setStep('name'));
  }, [step]);

  // Speak each step as it appears.
  useEffect(() => {
    if (!step) return;
    if (step === 'done' && onDone) {
      onDone();
      return;
    }
    const first = name?.first ?? profile.firstName;
    const line: Partial<Record<Step, string>> = {
      perm_camera: Say.cameraWhy,
      perm_mic: Say.micWhy,
      name: Say.askName,
      name_confirm: name ? Say.confirmName(`${name.first} ${name.last}`.trim()) : undefined,
      phone: DEMO_MODE ? Say.phoneDemo(DEMO_PHONE) : undefined,
      insurance: Say.askInsurance,
      insurance_confirm: insurance ? Say.confirmInsurance(insurance.insurer_name, insurance.plan_name) : undefined,
      payment: Say.askPayment(cardsAdded === 0 && firstCard),
      payment_type: Say.askCardType,
      payment_confirm: payment ? Say.confirmCard(spokenCard(payment), payment.last4) : undefined,
      done: Say.done(first),
    };
    const text = line[step];
    if (text) sayLocal(text);
    // Only on step change; the data a line uses is set before the step changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // What a spoken answer means at each step.
  useEffect(() => {
    if (!step) return;
    const yesNo = (onYes: () => void, onNo: () => void) => (t: string) =>
      YES.test(t) ? onYes() : NO.test(t) ? onNo() : sayLocal("Please say yes or no.");
    const handlers: Partial<Record<Step, [api.SttHint | undefined, (t: string) => void]>> = {
      name: ['name', (t) => onName(t)],
      name_confirm: ['yes_no', yesNo(confirmName, () => setStep('name'))],
      phone: ['yes_no', () => setStep('insurance')],
      insurance_confirm: ['yes_no', yesNo(confirmInsurance, () => setStep('insurance'))],
      payment_type: [
        'card_type',
        (t) => {
          const s = t.toLowerCase();
          if (s.includes('hsa')) chooseType('hsa');
          else if (s.includes('fsa')) chooseType('fsa');
          else if (s.includes('debit')) chooseType('general', 'debit');
          else if (s.includes('credit') || s.includes('regular') || s.includes('visa')) chooseType('general', 'credit');
          else sayLocal(Say.askCardType);
        },
      ],
      payment_confirm: ['yes_no', yesNo(confirmPayment, () => setStep('payment'))],
      payment_more: ['yes_no', yesNo(() => setStep('payment'), () => setStep('done'))],
    };
    const h = handlers[step];
    setListenHandler(h?.[0], h?.[1] ?? null);
    registerCapture(step === 'insurance' || step === 'payment' ? () => void takeCard() : null);
    return () => {
      setListenHandler(undefined, null);
      registerCapture(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, name, insurance, payment, cardsAdded]);

  // --- step actions ---------------------------------------------------------

  function onName(t: string) {
    const n = splitName(t);
    if (!n) {
      sayLocal(Say.nameAgain);
      return;
    }
    setName(n);
    setTyping(false);
    setStep('name_confirm');
  }

  function confirmName() {
    if (!name) return;
    update({ firstName: name.first, lastName: name.last });
    // Say the user's name out loud the first time they onboard.
    sayLocal(Say.greet(name.first));
    if (DEMO_MODE) update({ phone: DEMO_PHONE, phoneVerified: true });
    setStep('phone');
  }

  async function takeCard() {
    if (busy.current) return;
    busy.current = true;
    setReading(true);
    haptic.capture();
    const kind = step === 'insurance' ? 'insurance' : 'payment';
    const shot = await capture();
    try {
      if (!shot) throw new Error('no capture');
      const res = await api.scanCard(shot.uri, kind);
      if (res.state === 'unclear') {
        sayLocal(res.framing_hint ?? Say.unclear);
        return;
      }
      if (kind === 'insurance' && res.insurance) {
        setInsurance(res.insurance);
        setStep('insurance_confirm');
      } else if (kind === 'payment' && res.payment) {
        setPayment(res.payment);
        setDebitOrCredit(undefined);
        setStep(res.payment.card_type ? 'payment_confirm' : 'payment_type');
      } else {
        sayLocal(Say.unclear);
      }
    } catch (e) {
      haptic.error();
      sayLocal(e instanceof api.ApiError && e.speech ? e.speech : Say.unclear);
    } finally {
      shot?.discard(); // card images are never retained
      busy.current = false;
      setReading(false);
    }
  }

  function confirmInsurance() {
    update({ insurance });
    setStep('payment');
  }

  function chooseType(type: Card['type'], kind?: 'credit' | 'debit') {
    if (!payment) return;
    setPayment({ ...payment, card_type: type });
    setDebitOrCredit(kind);
    setStep('payment_confirm');
  }

  async function confirmPayment() {
    if (!payment?.card_type) return;
    try {
      await api.linkCard({
        type: payment.card_type,
        nickname: nicknameFor(payment.card_type, payment.network, debitOrCredit),
        last4: payment.last4,
        network: payment.network,
      });
      await refreshCards();
      setCardsAdded((n) => n + 1);
      sayLocal(Say.cardAdded(nicknameFor(payment.card_type, payment.network, debitOrCredit)));
      setStep('payment_more');
    } catch (e) {
      haptic.error();
      sayLocal(e instanceof api.ApiError && e.speech ? e.speech : Say.unclear);
    }
  }

  function finish() {
    update({ onboarded: true });
  }

  // --- render ---------------------------------------------------------------

  if (!step) return null;

  const yesNoButtons = (onYes: () => void, onNo: () => void, noLabel = 'No, try again') => (
    <View style={styles.buttons}>
      <BigButton label="Yes, that's right" icon="check" variant="accent" size="primary" onPress={onYes} />
      <BigButton label={noLabel} icon="retry" onPress={onNo} />
    </View>
  );

  const step1of = (n: number) => <PanelText kind="small" muted>{`Step ${n} of 5`}</PanelText>;

  switch (step) {
    case 'perm_camera':
      return (
        <InfoPanel title="Camera">
          <PanelText>{Say.cameraWhy}</PanelText>
          {camera && !camera.granted && !camera.canAskAgain ? (
            <>
              <PanelText>Camera access is off for Rewind. You can turn it on in your phone settings.</PanelText>
              <BigButton label="Open phone settings" variant="accent" size="primary" onPress={() => Linking.openSettings()} />
              <BigButton label="Continue without camera" onPress={() => setStep('perm_mic')} />
            </>
          ) : (
            <BigButton
              label="Allow camera"
              icon="camera"
              variant="accent"
              size="primary"
              onPress={async () => {
                await requestCamera();
                setStep('perm_mic');
              }}
            />
          )}
        </InfoPanel>
      );

    case 'perm_mic':
      return (
        <InfoPanel title="Microphone">
          <PanelText>{Say.micWhy}</PanelText>
          <BigButton
            label="Allow microphone"
            icon="mic"
            variant="accent"
            size="primary"
            onPress={async () => {
              await requestRecordingPermissionsAsync();
              setStep('name');
            }}
          />
          <BigButton label="Use buttons only" onPress={() => setStep('name')} />
        </InfoPanel>
      );

    case 'name':
      return (
        <InfoPanel title="Welcome to Rewind">
          {step1of(1)}
          <PanelText>What’s your first and last name? Tap the round Talk button below and say it.</PanelText>
          {typing ? (
            <>
              <NameInput value={typed} onChange={setTyped} onSubmit={() => onName(typed)} />
              <BigButton label="Done" variant="accent" size="primary" onPress={() => onName(typed)} disabled={!typed.trim()} />
            </>
          ) : (
            <BigButton label="Type my name instead" icon="keyboard" onPress={() => setTyping(true)} />
          )}
        </InfoPanel>
      );

    case 'name_confirm':
      return (
        <InfoPanel title="Is this your name?">
          {step1of(1)}
          <PanelText kind="display">{`${name?.first ?? ''} ${name?.last ?? ''}`.trim()}</PanelText>
          {yesNoButtons(confirmName, () => setStep('name'))}
        </InfoPanel>
      );

    case 'phone':
      return (
        <InfoPanel title={`Nice to meet you, ${profile.firstName || name?.first || ''}`}>
          {step1of(2)}
          <Notice icon="verified" color="eligible" kind="label">
            This phone is verified.
          </Notice>
          <PanelText kind="small" muted>
            {`Prototype: verified with the demo number ${DEMO_PHONE}. No text message is sent.`}
          </PanelText>
          <BigButton label="Continue" icon="next" variant="accent" size="primary" onPress={() => setStep('insurance')} />
        </InfoPanel>
      );

    case 'insurance':
      return (
        <InfoPanel title="Your insurance card">
          {step1of(3)}
          <PanelText>Hold your insurance card flat, about a hand length from the phone. Then tap anywhere on the screen.</PanelText>
          <BigButton label={reading ? 'Reading card…' : 'Take photo'} icon="camera" variant="accent" size="primary" disabled={reading} onPress={() => void takeCard()} />
          <BigButton label="Skip for now" onPress={() => setStep('payment')} />
        </InfoPanel>
      );

    case 'insurance_confirm':
      return (
        <InfoPanel title="Is this your insurance?">
          {step1of(3)}
          <PanelText kind="heading">{insurance?.insurer_name}</PanelText>
          {insurance?.plan_name ? <PanelText>{insurance.plan_name}</PanelText> : null}
          {insurance?.member_id_last4 ? (
            <PanelText muted>{`Member ID ending in ${insurance.member_id_last4}`}</PanelText>
          ) : null}
          {yesNoButtons(confirmInsurance, () => setStep('insurance'))}
        </InfoPanel>
      );

    case 'payment':
      return (
        <InfoPanel title={cardsAdded === 0 && firstCard ? 'Your HSA or FSA card' : 'Your next card'}>
          {startAt ? null : step1of(4)}
          <PanelText>
            {cardsAdded === 0 && firstCard
              ? 'Hold your HSA or FSA card flat, about a hand length from the phone. Then tap anywhere on the screen.'
              : 'Hold up your next card, like your Visa card. Then tap anywhere on the screen.'}
          </PanelText>
          <BigButton label={reading ? 'Reading card…' : 'Take photo'} icon="camera" variant="accent" size="primary" disabled={reading} onPress={() => void takeCard()} />
          <BigButton
            label={startAt ? 'Cancel' : cardsAdded === 0 ? 'Skip for now' : "I'm done adding cards"}
            onPress={() => setStep('done')}
          />
        </InfoPanel>
      );

    case 'payment_type':
      return (
        <InfoPanel title="What kind of card is this?">
          {step1of(4)}
          <View style={styles.buttons}>
            <BigButton label="HSA card" variant="accent" onPress={() => chooseType('hsa')} />
            <BigButton label="FSA card" variant="accent" onPress={() => chooseType('fsa')} />
            <BigButton label="Credit card" onPress={() => chooseType('general', 'credit')} />
            <BigButton label="Debit card" onPress={() => chooseType('general', 'debit')} />
          </View>
        </InfoPanel>
      );

    case 'payment_confirm':
      return (
        <InfoPanel title="Is this your card?">
          {step1of(4)}
          <PanelText kind="heading">
            {payment?.card_type ? nicknameFor(payment.card_type, payment.network, debitOrCredit) : ''}
          </PanelText>
          {payment?.last4 ? <PanelText kind="display">{`•••• ${payment.last4}`}</PanelText> : null}
          <PanelText kind="small" muted>
            Rewind keeps only the last 4 digits.
          </PanelText>
          {yesNoButtons(() => void confirmPayment(), () => setStep('payment'))}
        </InfoPanel>
      );

    case 'payment_more':
      return (
        <InfoPanel title="Card added">
          {step1of(4)}
          <PanelText>Do you want to add another card?</PanelText>
          <View style={styles.buttons}>
            <BigButton label="Add another card" icon="add" variant="accent" size="primary" onPress={() => setStep('payment')} />
            <BigButton label="No, I'm done" onPress={() => setStep('done')} />
          </View>
        </InfoPanel>
      );

    case 'done':
      return (
        <InfoPanel title={`You're all set, ${profile.firstName || name?.first || ''}`}>
          {step1of(5)}
          <PanelText>Point your phone at a product and tap anywhere to scan. Your cards and settings are under the round button at the top right.</PanelText>
          <BigButton label="Start shopping" icon="next" variant="accent" size="primary" onPress={finish} />
        </InfoPanel>
      );
  }
}

function NameInput({ value, onChange, onSubmit }: { value: string; onChange: (s: string) => void; onSubmit: () => void }) {
  const { palette, settings } = useA11y();
  const size = Math.round(Type.body.fontSize * settings.textScale);
  return (
    <TextInput
      value={value}
      onChangeText={onChange}
      onSubmitEditing={onSubmit}
      autoFocus
      autoComplete="name"
      textContentType="name"
      returnKeyType="done"
      placeholder="First and last name"
      placeholderTextColor={palette.textMuted}
      accessibilityLabel="Your first and last name"
      style={[
        styles.input,
        { fontSize: size, color: palette.text, backgroundColor: palette.surface, borderColor: palette.accent },
      ]}
    />
  );
}

const styles = StyleSheet.create({
  buttons: { gap: Spacing.md },
  input: {
    minHeight: Target.min,
    borderWidth: 3,
    borderRadius: Radius.button,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
});
