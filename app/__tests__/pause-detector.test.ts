import { createPauseDetector } from '@/lib/pause-detector';

/** Feeds a level every 100 ms from `from` to `to` (ms). */
function run(d: ReturnType<typeof createPauseDetector>, level: number, from: number, to: number) {
  let last = { spoke: false, paused: false };
  for (let t = from; t <= to; t += 100) last = d.feed(level, t);
  return last;
}

describe('pause detector', () => {
  it('does not end the answer before anything was said', () => {
    const d = createPauseDetector();
    expect(run(d, 0.03, 0, 5000)).toEqual({ spoke: false, paused: false });
  });

  it('ends the answer after speech followed by a 2 second pause', () => {
    const d = createPauseDetector();
    expect(run(d, 0.4, 0, 1500).spoke).toBe(true);
    expect(run(d, 0.03, 1600, 3400).paused).toBe(false); // 1.9 s of quiet: still waiting
    expect(run(d, 0.03, 3500, 3600).paused).toBe(true); // 2.0 s of quiet: done
  });

  it('keeps going if the shopper starts again inside the pause', () => {
    const d = createPauseDetector();
    run(d, 0.4, 0, 1000);
    run(d, 0.03, 1100, 2500); // 1.5 s gap
    run(d, 0.4, 2600, 3500); // speaks again
    expect(run(d, 0.03, 3600, 5400).paused).toBe(false); // 1.9 s since the last word
    expect(run(d, 0.03, 5500, 5600).paused).toBe(true);
  });

  it('ignores a short blip as speech', () => {
    const d = createPauseDetector();
    d.feed(0.5, 0); // one 100 ms reading: shorter than 150 ms of voice
    expect(run(d, 0.03, 100, 5000)).toEqual({ spoke: false, paused: false });
  });
});
