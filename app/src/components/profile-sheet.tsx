import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

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
import { useStage } from '@/lib/stage';
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
  const { area } = useStage();
  const cue = useScrollCue();

  const width = Math.min(area.w - Layout.margin * 2, MaxContentWidth);
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
          top: area.y,
          left: area.x + (area.w - width) / 2,
          width,
          height: area.h,
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

      <View style={styles.scrollWrap}>
      <ScrollView contentContainerStyle={styles.scroll} {...cue.scrollProps}>
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

        <Section title="Demo (presenter)">
          <BigButton
            label="Pretend I'm at Walmart Pharmacy"
            icon="pin"
            onPress={() => {
              showView('camera');
              void startCheckin('store_walmart');
            }}
          />
          <BigButton
            label="Pretend I left the store"
            icon="next"
            onPress={() => {
              leaveStore();
              showView('camera');
            }}
          />
          <BigButton
            label="Decline the next payment"
            icon="danger"
            onPress={() => {
              demoDecline();
              showView('camera');
            }}
          />
          <ConfirmButton label="Reset · run 1 (HSA $340.00)" onConfirm={() => restart(1)} />
          <ConfirmButton label="Reset · run 2 (HSA $15.00)" onConfirm={() => restart(2)} />
          <ConfirmButton label="Set up again" variant="danger" onConfirm={() => restart(1)} />
        </Section>
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
  scroll: { padding: Spacing.md, paddingBottom: Spacing.xxl, gap: Spacing.md },
  block: { gap: Spacing.xs },
});

/**
 * Erases everything, so it takes two taps (spec 20.9, Apple HIG for destructive actions): the first tap
 * asks, the second within 5 seconds does it. The question is also said out loud.
 */
function ConfirmButton({ label, variant, onConfirm }: { label: string; variant?: 'danger'; onConfirm: () => void }) {
  const { sayLocal } = useAgent();
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 5000);
    return () => clearTimeout(t);
  }, [armed]);
  return (
    <BigButton
      label={armed ? 'Tap again to erase everything' : label}
      accessibilityHint={armed ? undefined : 'Erases your cart, history and setup. Asks you to tap again first.'}
      variant={armed ? 'danger' : variant}
      onPress={() => {
        if (armed) {
          setArmed(false);
          onConfirm();
        } else {
          setArmed(true);
          sayLocal('This erases your cart, history and setup. Tap again to confirm.');
        }
      }}
    />
  );
}
