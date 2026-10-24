import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Radius, Spacing } from '@/constants/theme';
import type { EligibilityLabel, EligibilityResult } from '@/lib/api';
import { useA11y } from '@/lib/a11y';

const LOOK: Record<
  EligibilityLabel,
  { icon: string; text: string; fg: 'eligible' | 'notEligible' | 'unconfirmed'; bg: 'eligibleBg' | 'notEligibleBg' | 'unconfirmedBg' }
> = {
  eligible: { icon: '✓', text: 'HSA eligible', fg: 'eligible', bg: 'eligibleBg' },
  not_eligible: { icon: '✕', text: 'Not HSA eligible', fg: 'notEligible', bg: 'notEligibleBg' },
  could_not_confirm: { icon: '?', text: 'Could not confirm eligibility', fg: 'unconfirmed', bg: 'unconfirmedBg' },
};

/**
 * Confidence wording follows tech spec 3.11: medication on an exact UPC match
 * gets no confidence phrase; other confirmed results say "high confidence"
 * (or "moderate" for a weaker semantic match).
 */
function confidenceText(e: EligibilityResult, isMedication: boolean): string | null {
  if (e.label === 'could_not_confirm') return null;
  if (isMedication && e.basis === 'upc_match') return null;
  if (e.basis === 'semantic_match' && e.confidence != null && e.confidence < 0.85) return 'moderate confidence';
  return 'high confidence';
}

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
  const conf = 'basis' in eligibility ? confidenceText(eligibility, isMedication) : null;
  const text = conf ? `${look.text}, ${conf}` : look.text;

  return (
    <View
      accessible
      accessibilityLabel={text}
      style={[
        styles.badge,
        compact && styles.compact,
        { backgroundColor: palette[look.bg], borderColor: palette[look.fg] },
      ]}>
      <View style={[styles.icon, { backgroundColor: palette[look.fg] }]}>
        <AppText kind="label" color="surface" style={styles.iconText}>
          {look.icon}
        </AppText>
      </View>
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
    borderWidth: 2,
    borderRadius: Radius.button,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    alignSelf: 'flex-start',
    maxWidth: '100%',
  },
  compact: { paddingVertical: Spacing.xs, gap: Spacing.sm },
  icon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  iconText: { fontSize: 20, lineHeight: 24 },
  text: { flexShrink: 1 },
});
