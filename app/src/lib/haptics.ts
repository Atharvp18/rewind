/**
 * Haptic feedback, behind the user's haptics setting. Haptics are never the
 * only signal: every buzz here goes with speech and on-screen text.
 * Android intensity varies by device and some devices have no motor.
 */

import * as Haptics from 'expo-haptics';

let enabled = true;

export function setHapticsEnabled(on: boolean) {
  enabled = on;
}

export const haptic = {
  /** Primary (Talk) button tap. */
  tap: () => enabled && void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}),
  /** Camera capture. */
  capture: () => enabled && void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {}),
  /** The agent finished a response, or the user asked for a repeat. */
  done: () =>
    enabled && void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}),
  /** Declined payment, alert, or error envelope. */
  error: () =>
    enabled && void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {}),
};
