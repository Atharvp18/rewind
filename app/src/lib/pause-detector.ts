/**
 * Decides when the shopper has finished talking: they have spoken, and then paused.
 * Fed the live microphone level (0..1, from lib/audio.ts) with the time of each reading, so it is
 * plain logic that a test can drive with made-up numbers.
 */

/** Mic level that counts as a voice. Room noise sits around 0.02 to 0.08; speech is 0.15 and up. */
export const VOICE_LEVEL = 0.12;
/** A pause this long after speaking ends the answer (push-to-talk / auto-listen). */
export const PAUSE_MS = 2000;
/** Shorter pause for conversation mode: feels like a natural turn boundary (~750ms). */
export const CONVO_PAUSE_MS = 750;
/** A voice must last this long to count as speech (a cough or a tap on the phone does not). */
export const MIN_VOICE_MS = 150;

export interface PauseDetector {
  /** Feed one level reading taken at `now` (ms). Returns what is known after it. */
  feed(level: number, now: number): { spoke: boolean; paused: boolean };
}

export function createPauseDetector(
  opts: { voiceLevel?: number; pauseMs?: number; minVoiceMs?: number } = {},
): PauseDetector {
  const voiceLevel = opts.voiceLevel ?? VOICE_LEVEL;
  const pauseMs = opts.pauseMs ?? PAUSE_MS;
  const minVoiceMs = opts.minVoiceMs ?? MIN_VOICE_MS;
  let voicedSince: number | null = null;
  let lastVoiced = 0;
  let spoke = false;

  return {
    feed(level, now) {
      if (level >= voiceLevel) {
        voicedSince ??= now;
        lastVoiced = now;
        if (now - voicedSince >= minVoiceMs) spoke = true;
      } else {
        voicedSince = null;
      }
      return { spoke, paused: spoke && level < voiceLevel && now - lastVoiced >= pauseMs };
    },
  };
}
