import { AlertBlock } from '@/components/alert-block';
import type { Upstream } from '@/lib/api';
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
    <AlertBlock level="danger" title={unreachable ? 'Offline' : 'Service down'}>
      {lines.join(' ')}
    </AlertBlock>
  );
}
