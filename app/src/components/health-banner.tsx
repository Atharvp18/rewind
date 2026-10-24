import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/app-text';
import { Radius, Spacing } from '@/constants/theme';
import type { Upstream } from '@/lib/api';
import { useA11y } from '@/lib/a11y';
import { useAgent } from '@/state/agent';

const NAMES: Record<Upstream, string> = {
  claude: 'Product reading',
  cartesia: 'Voice service',
  moss: 'Eligibility search',
  nessie: 'Card balances',
  supabase: 'Cart storage',
};

const EFFECT: Partial<Record<Upstream, string>> = {
  cartesia: 'Using phone voice.',
  nessie: 'Showing last known balances.',
  moss: 'Using category rules.',
};

/** Names any upstream reported `down` by /v1/health, in words (never color alone). */
export function HealthBanner() {
  const { palette } = useA11y();
  const { state } = useAgent();
  const down = state.health
    ? (Object.entries(state.health.upstreams) as [Upstream, string][]).filter(([, s]) => s === 'down')
    : [];
  const unreachable = state.health === null;
  if (!down.length && !unreachable) return null;

  const lines = unreachable
    ? ['Rewind server is not reachable.']
    : down.map(([u]) => `${NAMES[u]} is down. ${EFFECT[u] ?? ''}`.trim());

  return (
    <View
      accessibilityRole="alert"
      style={[styles.banner, { borderColor: palette.danger, backgroundColor: palette.dangerBg }]}>
      {lines.map((l) => (
        <AppText key={l} kind="small" color="danger">
          ⚠ {l}
        </AppText>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { borderWidth: 2, borderRadius: Radius.button, padding: Spacing.md, gap: Spacing.xs },
});
