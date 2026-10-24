/**
 * Where things are on the camera screen: the item's box (for the focus
 * corners and the pop-up's pointer) and the free area between the top bar and
 * the voice orb (where pop-ups may go).
 */

import { createContext, useContext } from 'react';

import type { NormRect } from '@/lib/api';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface StageLayout {
  /** Screen box of the item the pop-up talks about, or null. */
  itemBox: Rect | null;
  /** Free area for pop-ups: below the top bar, above the orb. Screen coordinates. */
  area: Rect;
  /** The pop-up card reports where it sits, so the focus corners can stay clear of it. */
  reportCard?: (rect: Rect | null) => void;
}

export const StageContext = createContext<StageLayout>({
  itemBox: null,
  area: { x: 0, y: 0, w: 0, h: 0 },
});

export const useStage = () => useContext(StageContext);

/**
 * Map a box given as fractions of the captured photo onto the full-screen
 * preview. The preview shows the camera image scaled to *cover* the screen
 * (cropped at the edges), so the same scale and crop are applied here.
 */
export function photoToScreen(box: NormRect, photo: Size, screen: Size): Rect {
  const scale = Math.max(screen.width / photo.width, screen.height / photo.height);
  const shownW = photo.width * scale;
  const shownH = photo.height * scale;
  const offX = (screen.width - shownW) / 2;
  const offY = (screen.height - shownH) / 2;
  return {
    x: offX + box.x * shownW,
    y: offY + box.y * shownH,
    w: box.w * shownW,
    h: box.h * shownH,
  };
}

/** Grow a box around its center (a barcode is much smaller than the product). */
export function inflate(r: Rect, factor: number, bounds: Size): Rect {
  const w = Math.min(bounds.width - 16, r.w * factor);
  const h = Math.min(bounds.height - 16, r.h * factor);
  const cx = r.x + r.w / 2;
  const cy = r.y + r.h / 2;
  return {
    x: Math.max(8, Math.min(bounds.width - w - 8, cx - w / 2)),
    y: Math.max(8, Math.min(bounds.height - h - 8, cy - h / 2)),
    w,
    h,
  };
}
