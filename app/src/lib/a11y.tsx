/**
 * Accessibility settings (tech spec 1.5). Settings apply at once across the
 * app and persist on the phone in AsyncStorage; the backend never sees them.
 * Also detects VoiceOver / TalkBack (decision 13) and Reduce Motion.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AccessibilityInfo, useColorScheme } from 'react-native';

import { PanelOpacity, Palettes, type Palette, type ThemeName } from '@/constants/theme';
import { setHapticsEnabled } from '@/lib/haptics';

export type ThemeChoice = 'system' | ThemeName;
export type SpeechRate = 'slow' | 'normal' | 'fast';

export interface Settings {
  theme: ThemeChoice;
  /** Multiplies every type size. 1.0 to 2.0 (WCAG 1.4.4 resize to 200%). */
  textScale: number;
  captions: boolean;
  speechRate: SpeechRate;
  /** 0.0 to 1.0 */
  volume: number;
  /** Push-to-talk is the default because the venue is loud (1.4). */
  continuousListening: boolean;
  reduceMotion: boolean;
  /** Info panel opacity, PanelOpacity.min to max. */
  panelOpacity: number;
  /** Haptics are never the only feedback; this turns them off entirely. */
  haptics: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: 'system',
  textScale: 1,
  captions: true,
  speechRate: 'normal',
  volume: 1,
  continuousListening: false,
  reduceMotion: false,
  panelOpacity: PanelOpacity.default,
  haptics: true,
};

export const TEXT_SCALES = [1, 1.25, 1.5, 1.75, 2] as const;

/** expo-speech rate multipliers. */
export const SPEECH_RATE: Record<SpeechRate, number> = { slow: 0.8, normal: 1.0, fast: 1.2 };

const STORAGE_KEY = 'rewind.settings.v1';

interface A11yContextValue {
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  themeName: ThemeName;
  palette: Palette;
  screenReaderOn: boolean;
  /** True when either the OS or the in-app setting asks for reduced motion. */
  reduceMotion: boolean;
  loaded: boolean;
}

const A11yContext = createContext<A11yContextValue | null>(null);

export function A11yProvider({ children }: { children: ReactNode }) {
  const scheme = useColorScheme();
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);
  const [screenReaderOn, setScreenReaderOn] = useState(false);
  const [osReduceMotion, setOsReduceMotion] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (raw) setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(raw) });
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    AccessibilityInfo.isScreenReaderEnabled().then(setScreenReaderOn);
    AccessibilityInfo.isReduceMotionEnabled().then(setOsReduceMotion);
    const a = AccessibilityInfo.addEventListener('screenReaderChanged', setScreenReaderOn);
    const b = AccessibilityInfo.addEventListener('reduceMotionChanged', setOsReduceMotion);
    return () => {
      a.remove();
      b.remove();
    };
  }, []);

  useEffect(() => {
    setHapticsEnabled(settings.haptics);
  }, [settings.haptics]);

  const value = useMemo<A11yContextValue>(() => {
    const themeName: ThemeName =
      settings.theme === 'system' ? (scheme === 'dark' ? 'dark' : 'standard') : settings.theme;
    return {
      settings,
      update: (patch) =>
        setSettings((prev) => {
          const next = { ...prev, ...patch };
          AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
          return next;
        }),
      themeName,
      palette: Palettes[themeName],
      screenReaderOn,
      reduceMotion: osReduceMotion || settings.reduceMotion,
      loaded,
    };
  }, [settings, scheme, screenReaderOn, osReduceMotion, loaded]);

  return <A11yContext.Provider value={value}>{children}</A11yContext.Provider>;
}

export const THEME_LABEL: Record<ThemeName, string> = {
  standard: 'Standard',
  dark: 'Dark',
  highContrast: 'High contrast',
};

export function useA11y(): A11yContextValue {
  const ctx = useContext(A11yContext);
  if (!ctx) throw new Error('useA11y must be used inside <A11yProvider>');
  return ctx;
}

/** Send text through VoiceOver / TalkBack instead of the app's own voice (decision 13). */
export function announce(text: string): void {
  AccessibilityInfo.announceForAccessibility(text);
}
