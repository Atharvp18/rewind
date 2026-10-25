/**
 * Audio (tech spec 1.4): microphone capture and the playback queue.
 *
 * Playback: the backend returns one audio file per sentence from /v1/tts; we
 * play them in order. If /v1/tts fails or Cartesia is down we speak the same
 * sentences with expo-speech on the phone. Captions are handled by the caller.
 *
 * Queue rules:
 *   normal → enqueued after whatever is playing
 *   alert  → interrupts, plays at once, then the interrupted message replays
 *   interrupt() (barge-in) → stops everything and returns what was cut off
 */

import {
  createAudioPlayer,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioStream,
  type AudioPlayer,
} from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import * as Speech from 'expo-speech';
import { useCallback, useRef } from 'react';

import * as api from '@/lib/api';
import type { VoiceRequest } from '@/lib/api';

export async function configureAudio(): Promise<void> {
  // Default is already true; set it anyway (1.4).
  await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
}

/** How long Cartesia audio gets to start before the phone's own voice takes over. */
const START_TIMEOUT_MS = 6000;

export interface SpeakOptions {
  rate: number;
  volume: number;
}

type Listener = {
  onStart?: (v: VoiceRequest) => void;
  onDone?: (v: VoiceRequest) => void;
};

class Speaker {
  private queue: VoiceRequest[] = [];
  private current: VoiceRequest | null = null;
  private player: AudioPlayer | null = null;
  private token = 0;
  private listener: Listener = {};
  opts: SpeakOptions = { rate: 1, volume: 1 };

  setListener(l: Listener) {
    this.listener = l;
  }

  get speaking() {
    return this.current !== null;
  }

  speak(v: VoiceRequest) {
    if (v.priority === 'alert' && this.current) {
      const cut = this.current;
      this.stopPlayback();
      this.queue = [v, cut, ...this.queue];
      this.next();
      return;
    }
    this.queue.push(v);
    if (!this.current) this.next();
  }

  /** Barge-in: stop at once. Returns the message that was cut off, if any. */
  interrupt(): VoiceRequest | null {
    const cut = this.current;
    this.queue = [];
    this.stopPlayback();
    return cut;
  }

  private stopPlayback() {
    this.token++;
    this.current = null;
    Speech.stop();
    this.player?.pause();
  }

  private async next() {
    const v = this.queue.shift();
    if (!v) return;
    this.current = v;
    const token = ++this.token;
    this.listener.onStart?.(v);
    try {
      await this.play(v, token);
    } finally {
      if (token === this.token) {
        this.current = null;
        this.listener.onDone?.(v);
        this.next();
      }
    }
  }

  private async play(v: VoiceRequest, token: number) {
    const sentences = v.sentences.length ? v.sentences : [v.text];
    let urls: string[] | null = null;
    // One retry: a slow first Cartesia sentence should not drop the whole line to the phone's voice.
    for (let attempt = 0; attempt < 2 && !urls; attempt++) {
      try {
        const res = await api.tts(v.text, v.priority);
        urls = res.sentences.sort((a, b) => a.index - b.index).map((s) => api.audioUrl(s.audio_url));
      } catch (e) {
        console.warn(`[voice] /v1/tts failed (attempt ${attempt + 1}): ${e instanceof Error ? e.message : String(e)}`);
      }
    }
    if (!urls) console.warn('[voice] using the on-device voice for this line');
    for (let i = 0; i < sentences.length; i++) {
      if (token !== this.token) return;
      if (urls?.[i]) {
        const ok = await this.playUrl(urls[i], token);
        if (ok) continue;
        console.warn(`[voice] Cartesia audio would not play (sentence ${i + 1}); using the on-device voice`);
      }
      await this.speakDevice(sentences[i], token);
    }
  }

  private playUrl(url: string, token: number): Promise<boolean> {
    return new Promise((resolve) => {
      let sub: { remove: () => void } | null = null;
      let started = false;
      // If the audio never starts (bad download, decoder), give up so the line is still spoken.
      const giveUp = setTimeout(() => {
        if (started) return;
        sub?.remove();
        console.warn(`[voice] no audio started within ${START_TIMEOUT_MS / 1000}s for ${url}`);
        resolve(false);
      }, START_TIMEOUT_MS);
      try {
        if (!this.player) this.player = createAudioPlayer(null);
        const player = this.player;
        // Expo Go's native player exposes playbackRate as read-only: use the setter method.
        player.volume = this.opts.volume;
        player.setPlaybackRate(this.opts.rate);
        sub = player.addListener('playbackStatusUpdate', (s) => {
          if (s.playing) started = true;
          if (token !== this.token || s.didJustFinish) {
            clearTimeout(giveUp);
            sub?.remove();
            resolve(true);
          }
        });
        player.replace({ uri: url });
        player.play();
      } catch (e) {
        clearTimeout(giveUp);
        console.warn(`[voice] player error: ${e instanceof Error ? e.message : String(e)}`);
        resolve(false);
      }
    });
  }

  private speakDevice(text: string, token: number): Promise<void> {
    return new Promise((resolve) => {
      if (token !== this.token) return resolve();
      Speech.speak(text, {
        rate: this.opts.rate,
        volume: this.opts.volume,
        onDone: () => resolve(),
        onStopped: () => resolve(),
        onError: () => resolve(),
      });
    });
  }
}

export const speaker = new Speaker();

// ---------------------------------------------------------------------------
// Microphone: raw PCM capture (useAudioStream), wrapped as WAV for /v1/stt.
// ---------------------------------------------------------------------------

const SAMPLE_RATE = 16000;

// Live microphone level (0..1) for the voice orb. Never stored or sent.
type LevelListener = (level: number) => void;
const levelListeners = new Set<LevelListener>();

export function onMicLevel(fn: LevelListener): () => void {
  levelListeners.add(fn);
  return () => levelListeners.delete(fn);
}

function emitLevel(pcm: ArrayBuffer) {
  if (!levelListeners.size) return;
  const samples = new Int16Array(pcm);
  let sum = 0;
  for (let i = 0; i < samples.length; i += 4) sum += samples[i] * samples[i];
  const rms = Math.sqrt(sum / Math.max(1, samples.length / 4)) / 32768;
  // Speech RMS sits around 0.02 to 0.2; stretch it to fill 0..1.
  const level = Math.min(1, rms * 6);
  levelListeners.forEach((fn) => fn(level));
}

function wavFromPcm(chunks: ArrayBuffer[], sampleRate: number): Uint8Array {
  const dataLen = chunks.reduce((n, c) => n + c.byteLength, 0);
  const out = new Uint8Array(44 + dataLen);
  const view = new DataView(out.buffer);
  const str = (o: number, s: string) => [...s].forEach((ch, i) => view.setUint8(o + i, ch.charCodeAt(0)));
  str(0, 'RIFF');
  view.setUint32(4, 36 + dataLen, true);
  str(8, 'WAVE');
  str(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  str(36, 'data');
  view.setUint32(40, dataLen, true);
  let offset = 44;
  for (const c of chunks) {
    out.set(new Uint8Array(c), offset);
    offset += c.byteLength;
  }
  return out;
}

export type MicPermission = 'granted' | 'denied';

/**
 * Push-to-talk capture. `start()` begins streaming; `stop()` returns a temp
 * WAV file and a `discard()` that deletes it once the upload is done.
 */
export function useMic() {
  const chunks = useRef<ArrayBuffer[]>([]);
  const rate = useRef(SAMPLE_RATE);
  const { stream } = useAudioStream({
    sampleRate: SAMPLE_RATE,
    channels: 1,
    encoding: 'int16',
    onBuffer: (b) => {
      rate.current = b.sampleRate;
      chunks.current.push(b.data);
      emitLevel(b.data);
    },
  });

  const start = useCallback(async (): Promise<MicPermission> => {
    const perm = await requestRecordingPermissionsAsync();
    if (!perm.granted) return 'denied';
    chunks.current = [];
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    await stream.start();
    return 'granted';
  }, [stream]);

  const stop = useCallback(async (): Promise<{ uri: string; discard: () => void } | null> => {
    stream.stop();
    levelListeners.forEach((fn) => fn(0));
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
    const captured = chunks.current;
    chunks.current = [];
    if (!captured.length) return null;
    const file = new File(Paths.cache, `ptt-${Date.now()}.wav`);
    file.write(wavFromPcm(captured, rate.current));
    return {
      uri: file.uri,
      discard: () => {
        try {
          file.delete();
        } catch {
          // already gone
        }
      },
    };
  }, [stream]);

  return { start, stop };
}
