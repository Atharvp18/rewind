import { router, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/app-text';
import { BigButton } from '@/components/big-button';
import { Icon, Notice } from '@/components/icon';
import { Choice, Section, Toggle } from '@/components/settings-controls';
import { CameraDim, MaxContentWidth, Radius, Spacing, Target } from '@/constants/theme';
import { TEXT_SCALES, THEME_LABEL, useA11y, type SpeechRate, type ThemeChoice } from '@/lib/a11y';
import type { Card } from '@/lib/api';
import { centsForScreenReader, formatCents } from '@/lib/money';
import { initials, useProfile } from '@/lib/profile';
import { useAgent } from '@/state/agent';

const TYPE_LABEL: Record<Card['type'], string> = {
  hsa: 'HSA · for eligible health items',
  fsa: 'FSA · for eligible health items',
  general: 'Everyday card',
};

/**
 * Profile (top-right button): who you are, your linked cards, which
 * accessibility mode is on, and every setting (tech spec 1.5). Changes apply
 * at once and persist on the phone.
 */
export default function ProfileScreen() {
  const { palette, settings, update, themeName, reduceMotion } = useA11y();
  const { profile, reset } = useProfile();
  const { state, refreshCards, resetDemo, sayLocal, showView } = useAgent();

  useFocusEffect(
    useCallback(() => {
      void refreshCards();
    }, [refreshCards]),
  );

  const health = state.cards.filter((c) => c.type !== 'general');
  const everyday = state.cards.filter((c) => c.type === 'general');
  const fullName = `${profile.firstName} ${profile.lastName}`.trim();
  const mode = [
    THEME_LABEL[themeName],
    `Text ${Math.round(settings.textScale * 100)}%`,
    settings.captions ? 'Captions on' : 'Captions off',
    reduceMotion ? 'Reduced motion' : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <View style={[styles.root, { backgroundColor: palette.bg }]}>
      <SafeAreaView edges={['top', 'left', 'right']} style={styles.root}>
        {/* Done sits where the profile button was, so the way back is in the same place. */}
        <View style={styles.header}>
          <View style={[styles.avatar, { backgroundColor: palette.profileBg, borderColor: palette.border }]}>
            {initials(profile) === '?' ? (
              <Icon name="user" size={30} color="onProfile" />
            ) : (
              <AppText color="onProfile" style={styles.avatarText} accessible={false}>
                {initials(profile)}
              </AppText>
            )}
          </View>
          <View style={styles.flex}>
            <AppText kind="title" accessibilityRole="header">
              {fullName || 'Your profile'}
            </AppText>
            {profile.phoneVerified ? (
              <Notice icon="verified" kind="small" color="textMuted">
                {`Phone verified (demo number ${profile.phone})`}
              </Notice>
            ) : null}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Done, back to camera"
            onPress={() => router.back()}
            hitSlop={8}
            style={({ pressed }) => [
              styles.done,
              { backgroundColor: palette.primary, borderColor: palette.text, opacity: pressed ? 0.85 : 1 },
            ]}>
            <AppText kind="label" color="onPrimary">
              Done
            </AppText>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.scroll}>
          <View
            accessible
            accessibilityLabel={`Accessibility mode: ${mode}`}
            style={[styles.modeBanner, { backgroundColor: palette.surfaceAlt, borderColor: palette.primary }]}>
            <AppText kind="small" color="textMuted">
              Accessibility mode
            </AppText>
            <AppText kind="heading">{mode}</AppText>
          </View>

          <Section title="Your cards" hint="Demo accounts only. Payments are simulated. Rewind keeps only the last 4 digits.">
            {state.cards.length === 0 ? (
              <AppText kind="body" color="textMuted">
                No cards linked yet.
              </AppText>
            ) : (
              [...health, ...everyday].map((c) => <CardRow key={c.id} card={c} />)
            )}
            <BigButton
              label="Add a card"
              icon="add"
              variant="primary"
              onPress={() => {
                showView('add_card');
                router.back();
              }}
            />
          </Section>

          <Section title="Insurance">
            {profile.insurance ? (
              <>
                <AppText kind="label">{profile.insurance.insurer_name}</AppText>
                {profile.insurance.plan_name ? <AppText kind="body">{profile.insurance.plan_name}</AppText> : null}
                {profile.insurance.member_id_last4 ? (
                  <AppText kind="small" color="textMuted">
                    {`Member ID ending in ${profile.insurance.member_id_last4}`}
                  </AppText>
                ) : null}
              </>
            ) : (
              <AppText kind="body" color="textMuted">
                No insurance added.
              </AppText>
            )}
          </Section>

          <Section title="Colors">
            <Choice<ThemeChoice>
              label="Colors"
              value={settings.theme}
              onChange={(theme) => update({ theme })}
              options={[
                { value: 'system', label: 'Match phone' },
                { value: 'standard', label: 'Standard' },
                { value: 'dark', label: 'Dark' },
                { value: 'highContrast', label: 'High contrast' },
              ]}
            />
          </Section>

          <Section title="Text size">
            <Choice<number>
              label="Text size"
              value={settings.textScale}
              onChange={(textScale) => update({ textScale })}
              options={TEXT_SCALES.map((s) => ({ value: s, label: `${Math.round(s * 100)}%` }))}
              row
            />
            <AppText kind="body">Preview: Advil Ibuprofen 200mg, $12.99</AppText>
          </Section>

          <Section title="Voice">
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
              row
            />
            <Choice<number>
              label="Volume"
              value={settings.volume}
              onChange={(volume) => update({ volume })}
              options={[0.25, 0.5, 0.75, 1].map((v) => ({ value: v, label: `${v * 100}%` }))}
              row
            />
          </Section>

          <Section title="Screen">
            <Toggle
              label="Captions"
              detail="Shows everything Rewind says at the top of the screen"
              value={settings.captions}
              onChange={(captions) => update({ captions })}
            />
            <AppText kind="label">Dim the camera behind info</AppText>
            <AppText kind="small" color="textMuted">
              Helps with glare. Text is always on a solid card.
            </AppText>
            <Choice<number>
              label="Camera dimming"
              value={settings.cameraDim}
              onChange={(cameraDim) => update({ cameraDim })}
              options={CameraDim.options.map((v) => ({
                value: v,
                label: v === 0 ? 'Off' : v < 0.3 ? 'Some' : 'More',
              }))}
              row
            />
            <Toggle
              label="Reduce motion"
              detail="No sliding or growing animations"
              value={settings.reduceMotion}
              onChange={(v) => update({ reduceMotion: v })}
            />
            <Toggle
              label="Vibration"
              detail="Buzzes on taps, answers, and declined payments. Strength varies on Android phones."
              value={settings.haptics}
              onChange={(haptics) => update({ haptics })}
            />
          </Section>

          <Section title="Demo controls (presenter)">
            <BigButton label="Reset demo · run 1 (HSA $340.00)" onPress={() => resetDemo(1)} />
            <BigButton label="Reset demo · run 2 (HSA $15.00)" onPress={() => resetDemo(2)} />
            <BigButton
              label="Set up again"
              variant="danger"
              onPress={() => {
                reset();
                router.back();
              }}
            />
          </Section>
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

function CardRow({ card }: { card: Card }) {
  const { palette } = useA11y();
  const isHealth = card.type !== 'general';
  return (
    <View
      accessible
      accessibilityLabel={`${card.nickname}${card.last4 ? ` ending in ${card.last4.split('').join(' ')}` : ''}. ${
        TYPE_LABEL[card.type]
      }. Balance ${centsForScreenReader(card.balance_cents)}.${card.status !== 'active' ? ` ${card.status}.` : ''}`}
      style={[styles.card, { borderColor: isHealth ? palette.eligible : palette.border }]}>
      <View style={styles.cardTop}>
        <Icon name={isHealth ? 'health' : 'card'} size={26} color={isHealth ? 'eligible' : 'text'} />
        <AppText kind="heading" accessible={false} style={styles.flex}>
          {card.nickname}
        </AppText>
        {card.last4 ? (
          <AppText kind="label" accessible={false}>
            {`•••• ${card.last4}`}
          </AppText>
        ) : null}
      </View>
      <AppText kind="small" color={isHealth ? 'eligible' : 'textMuted'} accessible={false}>
        {TYPE_LABEL[card.type]}
      </AppText>
      <View style={styles.cardTop}>
        <AppText kind="body" accessible={false} style={styles.flex}>
          Balance
        </AppText>
        <AppText kind="title" accessible={false}>
          {formatCents(card.balance_cents)}
        </AppText>
      </View>
      {card.status !== 'active' ? (
        <Notice icon="alert" kind="label" color="danger">
          {`Card ${card.status}`}
        </Notice>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flex: { flexShrink: 1, flexGrow: 1 },
  header: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { fontSize: 28, lineHeight: 34, fontWeight: '800' },
  done: {
    minHeight: Target.min,
    minWidth: 88,
    borderRadius: Radius.pill,
    borderWidth: 2,
    paddingHorizontal: Spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scroll: {
    padding: Spacing.lg,
    gap: Spacing.lg,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  modeBanner: { borderWidth: 3, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.xs },
  card: { borderWidth: 3, borderRadius: Radius.card, padding: Spacing.lg, gap: Spacing.xs },
  cardTop: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: Spacing.sm },
});
