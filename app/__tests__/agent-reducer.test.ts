// The reducer is pure; the native audio, sensor and location modules it sits beside are not loaded here.
jest.mock('@/lib/audio', () => ({ speaker: {}, configureAudio: jest.fn(), useMic: jest.fn() }));
jest.mock('expo-location', () => ({}));
jest.mock('expo-audio', () => ({ getRecordingPermissionsAsync: jest.fn() }));

import { initial, reducer } from '@/state/agent';
import type { ScanResponse } from '@/lib/api';

const scan = (warnings: string[]) =>
  ({ scan: { scan_id: 's', state: 'unresolved', warnings }, recommendation: null, voice: {} }) as unknown as ScanResponse;
const photo = { width: 1280, height: 960 };

describe('agent reducer: scan edge cases', () => {
  it('turns the camera light on after a scan that was too dark, and keeps it on', () => {
    const dark = reducer(initial, { type: 'scan_received', res: scan(['E_VISION_UNCLEAR', 'E_TOO_DARK']), photo });
    expect(dark.torch).toBe(true);
    const next = reducer(dark, { type: 'scan_received', res: scan([]), photo });
    expect(next.torch).toBe(true);
  });

  it('leaves the light off for other unclear photos', () => {
    expect(reducer(initial, { type: 'scan_received', res: scan(['E_GLARE']), photo }).torch).toBe(false);
  });

  it('a restart puts everything back, light included', () => {
    const dark = reducer(initial, { type: 'scan_received', res: scan(['E_TOO_DARK']), photo });
    const reset = reducer(dark, { type: 'reset_all', cards: [], cart: { groups: [], total_cents: 0 } });
    expect(reset).toEqual({ ...initial, cards: [], cart: { groups: [], total_cents: 0 } });
  });
});
