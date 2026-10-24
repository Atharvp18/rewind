/**
 * One responsive system for every screen size (small phone to tablet, portrait
 * or landscape; Android 16 ignores the portrait lock at 600 dp and wider).
 */
import { MaxContentWidth } from '@/constants/theme';
import { responsiveFor } from '@/lib/responsive';

describe('screen classes (by the shorter side)', () => {
  it.each([
    ['iPhone SE', 375, 667, 'compact'],
    ['small Android', 360, 640, 'compact'],
    ['just under the compact limit', 379, 800, 'compact'],
    ['the compact limit itself', 380, 800, 'regular'],
    ['iPhone 17', 393, 852, 'regular'],
    ['iPhone 17 Pro Max', 440, 956, 'regular'],
    ['just under tablet', 599, 900, 'regular'],
    ['foldable / small tablet', 600, 900, 'expanded'],
    ['iPad', 768, 1024, 'expanded'],
  ])('%s (%i × %i) is %s', (_name, w, h, cls) => {
    expect(responsiveFor(w, h).screen).toBe(cls);
  });

  it('uses the shorter side, so a phone turned sideways keeps its class', () => {
    const portrait = responsiveFor(393, 852);
    const landscape = responsiveFor(852, 393);
    expect(landscape.screen).toBe(portrait.screen);
    expect(landscape.landscape).toBe(true);
    expect(portrait.landscape).toBe(false);
  });
});

describe('content column', () => {
  it('is the screen width minus two 16 pt margins on a phone', () => {
    const r = responsiveFor(375, 667);
    expect(r.contentWidth).toBe(375 - 32);
    expect(r.contentLeft).toBe(16);
  });

  it(`never exceeds ${MaxContentWidth} pt, and stays centered, on wide screens`, () => {
    const r = responsiveFor(1024, 768);
    expect(r.contentWidth).toBe(MaxContentWidth);
    expect(r.contentLeft).toBe((1024 - MaxContentWidth) / 2);
  });

  it('is always inside the screen', () => {
    for (const [w, h] of [[320, 568], [375, 667], [393, 852], [600, 900], [1024, 1366], [1366, 1024]]) {
      const r = responsiveFor(w, h);
      expect(r.contentLeft).toBeGreaterThanOrEqual(0);
      expect(r.contentLeft + r.contentWidth).toBeLessThanOrEqual(w);
    }
  });
});

describe('scales', () => {
  it('never shrinks fixed-size controls below 1× (targets stay ≥ 56 pt)', () => {
    expect(responsiveFor(320, 568).ui).toBe(1);
    expect(responsiveFor(375, 667).ui).toBe(1);
  });

  it('grows gently on large screens and stops at 1.25×', () => {
    expect(responsiveFor(440, 956).ui).toBeGreaterThan(1);
    expect(responsiveFor(768, 1024).ui).toBe(1.25);
    expect(responsiveFor(1366, 1024).ui).toBe(1.25);
  });

  it('adds a text bump only on tablets', () => {
    expect(responsiveFor(393, 852).type).toBe(1);
    expect(responsiveFor(768, 1024).type).toBe(1.15);
  });
});
