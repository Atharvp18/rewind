import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Icon, type IconName } from '@/components/icon';
import { Radius, Spacing } from '@/constants/theme';
import type { EligibilityLabel, EligibilityResult } from '@/lib/api';
import { useA11y } from '@/lib/a11y';

const LOOK: Record<
  EligibilityLabel,
  { icon: IconName; text: string; fg: 'eligible' | 'notEligible' | 'unconfirmed'; bg: 'eligibleBg' | 'notEligibleBg' | 'unconfirmedBg' }
> = {
  // "HSA/FSA": the spec's terminology rule says "HSA" alone must cover both accounts.
  eligible: { icon: 'eligible', text: 'HSA/FSA eligible', fg: 'eligible', bg: 'eligibleBg' },
  not_eligible: { icon: 'notEligible', text: 'Not HSA/FSA eligible', fg: 'notEligible', bg: 'notEligibleBg' },
  could_not_confirm: { icon: 'unconfirmed', text: 'Could not confirm eligibility', fg: 'unconfirmed', bg: 'unconfirmedBg' },
};

/** Always icon + words + color (WCAG 1.4.1). Never color alone. */
export function EligibilityBadge({
  eligibility,
  isMedication = false,
  compact = false,
}: {
  eligibility: EligibilityResult | { label: EligibilityLabel };
  isMedication?: boolean;
  compact?: boolean;
}) {
  const { palette } = useA11y();
  const look = LOOK[eligibility.label];
  const text = look.text; // no confidence wording, on screen or read aloud

  return (
    <View
      accessible
      accessibilityLabel={text.replace('HSA/FSA', 'HSA and FSA')}
      style={[
        styles.badge,
        compact && styles.compact,
        { backgroundColor: palette[look.bg], borderColor: palette[look.fg], borderWidth: palette.controlBorderWidth },
      ]}>
      <Icon name={look.icon} size={compact ? 22 : 28} color={look.fg} strokeWidth={2.5} />
      <AppText kind={compact ? 'small' : 'label'} color={look.fg} style={styles.text}>
        {text}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    borderRadius: Radius.button,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    alignSelf: 'flex-start',
    maxWidth: '100%',
  },
  compact: { paddingVertical: Spacing.xs, gap: Spacing.sm },
  text: { flexShrink: 1 },
});
