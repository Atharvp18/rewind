/**
 * One responsive system for every screen size: small phones (iPhone SE,
 * 375 × 667) through tablets and foldables, portrait or landscape (Android 16
 * ignores the portrait lock on screens 600 dp and wider).
 *
 * Components size from these values instead of fixed numbers, so the layout
 * scales as one piece.
 */

import { useWindowDimensions } from 'react-native';

import { Layout, MaxContentWidth } from '@/constants/theme';

export type ScreenClass = 'compact' | 'regular' | 'expanded';

/** Design baseline: a standard phone's shorter side (iPhone 15/16/17, Pixel 9). */
const BASE = 390;

export interface Responsive {
  width: number;
  height: number;
  /** compact: shorter side < 380 (SE, small Android); expanded: ≥ 600 (tablets, foldables). */
  screen: ScreenClass;
  landscape: boolean;
  /** Width of the centered content column (top row, transcript, cards, profile). */
  contentWidth: number;
  /** Left edge of that column. */
  contentLeft: number;
  /** Scale for fixed-size controls: 1 on phones, up to 1.25 on tablets. */
  ui: number;
  /** Extra text scale for large screens, on top of the user's text-size setting. */
  type: number;
}

export function responsiveFor(width: number, height: number): Responsive {
  const shorter = Math.min(width, height);
  const screen: ScreenClass = shorter >= 600 ? 'expanded' : shorter < 380 ? 'compact' : 'regular';
  const contentWidth = Math.min(width - Layout.margin * 2, MaxContentWidth);
  return {
    width,
    height,
    screen,
    landscape: width > height,
    contentWidth,
    contentLeft: (width - contentWidth) / 2,
    ui: Math.min(1.25, Math.max(1, shorter / BASE)),
    type: screen === 'expanded' ? 1.15 : 1,
  };
}

export function useResponsive(): Responsive {
  const { width, height } = useWindowDimensions();
  return responsiveFor(width, height);
}
