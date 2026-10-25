import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, useWindowDimensions, View } from 'react-native';

import { ScrollCue, useScrollCue } from '@/components/scroll-cue';
import Animated, { FadeIn, SlideInDown } from 'react-native-reanimated';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { CardArt } from '@/components/card-art';
import { Icon } from '@/components/icon';
import { CloseButton } from '@/components/close-button';
import { Choice, Section, SettingRow, Stepper, Toggle } from '@/components/settings-controls';
import { Elevation, Layout, MaxContentWidth, Motion, Radius, Spacing } from '@/constants/theme';
import { ANSWER_SECONDS, TEXT_SCALES, useA11y, type SpeechRate, type ThemeChoice } from '@/lib/a11y';
import type { Card } from '@/lib/api';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { initials, useProfile } from '@/lib/profile';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDomeHeight } from '@/components/voice-orb';
import { useAgent } from '@/state/agent';

const TYPE_LABEL: Record<Card['type'], string> = {
  hsa: 'Visa HSA',
  fsa: 'Visa FSA',
  general: 'Visa credit or debit',
};

/**
 * Profile (top-right button) as a pop-up over the camera, not a full screen:
 * it fills the space between the top row and the dome and scrolls, so the
 * voice orb stays visible and usable. Order: insurance and prescription
 * benefits, cards, then accessibility (tech spec 1.5), all one line each.
 */
export function ProfileSheet() {
  const { palette, settings, update, reduceMotion } = useA11y();
  const { profile } = useProfile();
  const { state, restart, sayLocal, showView, startCheckin, leaveStore, demoDecline } = useAgent();
  const cue = useScrollCue();
  const insets = useSafeAreaInsets();
  const { width: screenW, height: screenH } = useWindowDimensions();
  const dome = useDomeHeight();
  // A full page like the purchase history (status bar down to the dome), so nothing is cramped.
  const [geo] = useState(() => {
    const t = insets.top + Spacing.sm;
    return { top: t, pageH: Math.max(0, screenH - dome - t - Spacing.sm) };
  });
  const width = Math.min(screenW - Layout.margin * 2, MaxContentWidth);
  // Three short tabs instead of one long scroll.
  const [tab, setTab] = useState<'you' | 'settings' | 'demo'>('you');
  const ins = profile.insurance;
  const health = state.cards.filter((c) => c.type !== 'general');
  const everyday = state.cards.filter((c) => c.type === 'general');

  return (
    <Animated.View
      entering={reduceMotion ? FadeIn.duration(0) : SlideInDown.duration(Motion.panel)}
      accessibilityViewIsModal
      style={[
        styles.sheet,
        Elevation.floating,
        {
          top: geo.top,
          left: (screenW - width) / 2,
          width,
          height: geo.pageH,
          backgroundColor: palette.bg,
          borderColor: palette.border,
          borderWidth: palette.controlBorderWidth,
        },
      ]}>
      {/* Fixed header: who, verified phone, close. */}
      <View style={[styles.header, { borderBottomColor: palette.surfaceAlt }]}>
        <View style={[styles.avatar, { backgroundColor: palette.profileBg }]}>
          {initials(profile) === '?' ? (
            <Icon name="user" size={26} color="onProfile" />
          ) : (
            <AppText color="onProfile" accessible={false} style={styles.avatarText}>
              {initials(profile)}
            </AppText>
          )}
        </View>
        <View style={styles.flex}>
          <AppText kind="heading" accessibilityRole="header">
            {`${profile.firstName} ${profile.lastName}`.trim() || 'Your profile'}
          </AppText>
          {profile.phoneVerified && profile.phone ? (
            <View style={styles.inline} accessible accessibilityLabel={`Verified phone ${profile.phone}`}>
              <Icon name="verified" size={18} color="eligible" />
              <AppText kind="small" color="textMuted" accessible={false}>
                {profile.phone}
              </AppText>
            </View>
          ) : null}
        </View>
        <CloseButton label="Close profile" onPress={() => showView('camera')} />
      </View>

      {/* The tabs stay put while the page scrolls, so switching is always one tap away. */}
      <View style={[styles.tabs, { borderBottomColor: palette.surfaceAlt }]}>
          <Choice<'you' | 'settings' | 'demo'>
            label="Profile section"
            value={tab}
            onChange={setTab}
            options={[
              { value: 'you', label: 'You' },
              { value: 'settings', label: 'Settings' },
              { value: 'demo', label: 'Demo' },
            ]}
          />
      </View>
      <View style={styles.scrollWrap}>
      <ScrollView contentContainerStyle={styles.scroll} {...cue.scrollProps}>
        {tab === 'you' ? (
        <>
        <Section title="Insurance">
          {ins ? (
            <View style={styles.block} accessible>
              <AppText kind="label">{[ins.insurer_name, ins.plan_name].filter(Boolean).join(' · ')}</AppText>
              {ins.member_id_last4 ? (
                <AppText kind="small" color="textMuted">{`Member ID •••• ${ins.member_id_last4}`}</AppText>
              ) : null}
              <AppText kind="small" color="textMuted">
                {ins.rx
                  ? ins.rx.copays.length
                    ? `Prescriptions: ${ins.rx.copays.map((c) => `${c.label} ${formatCents(c.amount_cents)}`).join(' · ')}`
                    : 'Prescription benefits on this plan'
                  : 'No prescription benefits shown'}
              </AppText>
            </View>
          ) : (
            <AppText kind="body" color="textMuted">
              No insurance added.
            </AppText>
          )}
        </Section>

        <Section title="Cards">
          {[...health, ...everyday].map((c) => (
            <CardLine key={c.id} card={c} />
          ))}
          <BigButton label="Add a card" icon="add" onPress={() => showView('add_card')} />
        </Section>

        </>
        ) : null}
        {tab === 'settings' ? (
        <Section title="Accessibility">
          <SettingRow label="Colors">
            <Stepper<ThemeChoice>
              label="Colors"
              value={settings.theme}
              onChange={(theme) => update({ theme })}
              options={[
                { value: 'system', label: 'Match phone' },
                { value: 'standard', label: 'Light' },
                { value: 'dark', label: 'Dark' },
                { value: 'highContrast', label: 'High contrast' },
              ]}
            />
          </SettingRow>
          <SettingRow label="Text size">
            <Stepper<number>
              label="Text size"
              value={settings.textScale}
              onChange={(textScale) => update({ textScale })}
              options={TEXT_SCALES.map((s) => ({ value: s, label: `${Math.round(s * 100)}%` }))}
            />
          </SettingRow>
          <SettingRow label="Speech speed">
            <Choice<SpeechRate>
              label="Speech speed"
              value={settings.speechRate}
              onChange={(speechRate) => {
                update({ speechRate });
                sayLocal('This is how fast I will speak.');
              }}
              options={[
                { value: 'slow', label: 'Slow' },
                { value: 'normal', label: 'Normal' },
                { value: 'fast', label: 'Fast' },
              ]}
            />
          </SettingRow>
          <SettingRow label="Volume">
            <Stepper<number>
              label="Volume"
              value={settings.volume}
              onChange={(volume) => update({ volume })}
              options={[0.25, 0.5, 0.75, 1].map((v) => ({ value: v, label: `${v * 100}%` }))}
            />
          </SettingRow>
          <SettingRow label="Time to answer">
            <Stepper<number>
              label="Time to answer"
              value={settings.answerSeconds}
              onChange={(answerSeconds) => update({ answerSeconds })}
              options={ANSWER_SECONDS.map((v) => ({ value: v, label: `${v} seconds` }))}
            />
          </SettingRow>
          <Toggle label="Captions" value={settings.captions} onChange={(captions) => update({ captions })} />
          <Toggle label="Reduce motion" value={settings.reduceMotion} onChange={(reduceMotion) => update({ reduceMotion })} />
          <Toggle label="Vibration" value={settings.haptics} onChange={(haptics) => update({ haptics })} />
          <Toggle
            label="Interrupt by speaking (use headphones)"
            value={settings.interruptBySpeaking}
            onChange={(interruptBySpeaking) => update({ interruptBySpeaking })}
          />
        </Section>

        ) : null}
        {tab === 'demo' ? (
        <Section title="Demo scenarios">
          <PanelNote>Store</PanelNote>
          <BigButton
            label="Arrive at the pharmacy"
            accessibilityHint="Checks in to Walmart Pharmacy, as if you just walked in"
            icon="pin"
            onPress={() => {
              showView('camera');
              void startCheckin('store_walmart');
            }}
          />
          <BigButton
            label="Leave the pharmacy"
            accessibilityHint="Checks out of the store"
            icon="next"
            onPress={() => {
              leaveStore();
              showView('camera');
            }}
          />
          <PanelNote>Accounts (clears the cart and history, keeps your setup)</PanelNote>
          <ConfirmButton
            label="3 accounts: FSA, HSA, and Visa"
            note="Eligible items go to the FSA card first."
            onConfirm={() => restart(1, true)}
          />
          <ConfirmButton
            label="2 accounts: HSA and Visa"
            note="The HSA has $5.00, so items it cannot cover move to the Visa."
            onConfirm={() => restart(3, true)}
          />
          <PanelNote>Payment</PanelNote>
          <BigButton
            label="Decline a card at the next checkout"
            accessibilityHint="At the next checkout the first card is declined and its items move to the next card."
            icon="danger"
            onPress={() => {
              demoDecline();
              showView('camera');
            }}
          />
          <PanelNote>The first card charged is declined; its items move to the next card (FSA, then HSA, then Visa).</PanelNote>
          <PanelNote>Reset</PanelNote>
          <ConfirmButton
            label="Reset everything"
            note="Erases the cart, history, and setup, and starts onboarding again."
            variant="danger"
            onConfirm={() => restart(1)}
          />
        </Section>
        ) : null}
      </ScrollView>
      {/* "More below": a soft fade and a bobbing chevron until the end is near. */}
      <ScrollCue visible={cue.more} bg={palette.bg} />
      </View>
    </Animated.View>
  );
}

/** One card on one line: icon, name, last 4 · type, balance on the right. */
/** One card as a mini card in its colors (Visa Blue, HSA green, FSA plum), balance in the corner. */
function CardLine({ card }: { card: Card }) {
  return (
    <View
      accessible
      accessibilityLabel={`${card.nickname}${card.last4 ? ` ending in ${card.last4.split('').join(' ')}` : ''}, ${
        TYPE_LABEL[card.type]
      }, balance ${centsForScreenReader(card.balance_cents)}${card.status !== 'active' ? `, ${card.status}` : ''}`}>
      <CardArt type={card.type} nickname={card.nickname} last4={card.last4} value={formatCents(card.balance_cents)} />
      {card.status !== 'active' ? (
        <AppText kind="small" color="danger" accessible={false}>
          {`Card ${card.status}`}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: 'absolute', borderRadius: Radius.card + 4, overflow: 'hidden' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    padding: Spacing.lg,
    borderBottomWidth: 1,
  },
  avatar: { width: 48, height: 48, borderRadius: Radius.pill, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 22, lineHeight: 28, fontWeight: '800' },
  inline: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  flex: { flex: 1 },
  scrollWrap: { flex: 1 },
  tabs: { paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, borderBottomWidth: 1 },
  scroll: { padding: Spacing.md, paddingBottom: Spacing.xxl, gap: Spacing.md },
  block: { gap: Spacing.xs },
});

/**
 * Erases everything, so it takes two taps (spec 20.9, Apple HIG for destructive actions): the first tap
 * asks, the second within 5 seconds does it. The question is also said out loud.
 */
function ConfirmButton({
  label,
  note,
  variant,
  onConfirm,
}: {
  label: string;
  /** What the button does, shown under it and said before the second tap. */
  note?: string;
  variant?: 'danger';
  onConfirm: () => void;
}) {
  const { sayLocal } = useAgent();
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 5000);
    return () => clearTimeout(t);
  }, [armed]);
  const what = note ?? 'This erases your cart, history, and setup.';
  return (
    <View style={styles.block}>
      <BigButton
        label={armed ? 'Tap again to confirm' : label}
        accessibilityHint={armed ? undefined : `${what} Asks you to tap again first.`}
        variant={armed ? 'danger' : variant}
        onPress={() => {
          if (armed) {
            setArmed(false);
            onConfirm();
          } else {
            setArmed(true);
            sayLocal(`${what} Tap again to confirm.`);
          }
        }}
      />
      {note ? <PanelNote>{note}</PanelNote> : null}
    </View>
  );
}

/** A short muted line: a group heading or what a button does. */
function PanelNote({ children }: { children: string }) {
  return (
    <AppText kind="small" color="textMuted">
      {children}
    </AppText>
  );
}
