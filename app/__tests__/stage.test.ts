/**
 * Where things sit on the camera screen. The preview shows the photo scaled to
 * COVER the screen (cropped at the edges), so a box found in the photo has to be
 * mapped with the same scale and crop for the focus corners to land on the item.
 */
import { inflate, photoToScreen } from '@/lib/stage';

const close = (a: number, b: number) => expect(a).toBeCloseTo(b, 2);

describe('photoToScreen', () => {
  it('is the identity when the photo and the screen have the same shape', () => {
    const r = photoToScreen({ x: 0.25, y: 0.5, w: 0.5, h: 0.25 }, { width: 400, height: 800 }, { width: 400, height: 800 });
    expect(r).toEqual({ x: 100, y: 400, w: 200, h: 200 });
  });

  it('scales a same-shaped photo of any resolution to the screen (1280 px photo, 400 pt screen)', () => {
    const r = photoToScreen({ x: 0.5, y: 0.5, w: 0.1, h: 0.1 }, { width: 960, height: 1920 }, { width: 400, height: 800 });
    close(r.x, 200);
    close(r.y, 400);
    close(r.w, 40);
    close(r.h, 80);
  });

  it('accounts for the crop of a wider photo (the sides are cut off)', () => {
    // 4:3 landscape photo on a tall screen: scaled by height, cropped left and right.
    const photo = { width: 1280, height: 960 };
    const screen = { width: 400, height: 800 };
    const scale = Math.max(400 / 1280, 800 / 960);
    const shownW = photo.width * scale;
    const offX = (400 - shownW) / 2;
    const r = photoToScreen({ x: 0.5, y: 0.5, w: 0.1, h: 0.1 }, photo, screen);
    close(r.x, offX + 0.5 * shownW);
    close(r.y, 400);
    // The photo's center stays at the screen's center.
    const center = photoToScreen({ x: 0.45, y: 0.45, w: 0.1, h: 0.1 }, photo, screen);
    close(center.x + center.w / 2, 200);
    close(center.y + center.h / 2, 400);
  });

  it('accounts for the crop of a taller photo (the top and bottom are cut off)', () => {
    const r = photoToScreen({ x: 0.45, y: 0.45, w: 0.1, h: 0.1 }, { width: 600, height: 1600 }, { width: 400, height: 800 });
    close(r.x + r.w / 2, 200);
    close(r.y + r.h / 2, 400);
  });

  it('puts a box that lies in the cropped-away strip off the screen (negative x)', () => {
    const r = photoToScreen({ x: 0, y: 0, w: 0.1, h: 0.1 }, { width: 1280, height: 960 }, { width: 400, height: 800 });
    expect(r.x).toBeLessThan(0);
  });
});

describe('inflate (a barcode is much smaller than the product it sits on)', () => {
  const bounds = { width: 400, height: 800 };

  it('grows around the center', () => {
    const r = inflate({ x: 100, y: 100, w: 50, h: 50 }, 2.4, bounds);
    close(r.w, 120);
    close(r.h, 120);
    close(r.x + r.w / 2, 125);
    close(r.y + r.h / 2, 125);
  });

  it('stays at least 8 pt inside the screen at the edges', () => {
    const r = inflate({ x: 0, y: 0, w: 20, h: 20 }, 5, bounds);
    expect(r.x).toBe(8);
    expect(r.y).toBe(8);
    const far = inflate({ x: 390, y: 790, w: 10, h: 10 }, 5, bounds);
    expect(far.x + far.w).toBeLessThanOrEqual(bounds.width - 8);
    expect(far.y + far.h).toBeLessThanOrEqual(bounds.height - 8);
  });

  it('is never larger than the screen minus the margins', () => {
    const r = inflate({ x: 10, y: 10, w: 300, h: 600 }, 10, bounds);
    expect(r.w).toBe(bounds.width - 16);
    expect(r.h).toBe(bounds.height - 16);
  });
});
