/**
 * The user's profile from onboarding: name, verified phone, insurance.
 * Stored on the phone only (AsyncStorage). No endpoint for it exists in tech
 * spec 0.6. Payment cards are not stored here; they come from /v1/cards.
 * Only the last 4 digits of any card or member ID ever reach the app.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import type { InsuranceCard } from '@/lib/api';

/** Prototype: phone verification is skipped and one preset mock number is used. */
export const DEMO_MODE = true;
/** 555-0100 to 555-0199 are reserved for fiction; this number reaches no one. */
export const DEMO_PHONE = '+1 (415) 555-0100';

/** Read from the insurance card at onboarding (see InsuranceCard). */
export type Insurance = InsuranceCard;

export interface Profile {
  onboarded: boolean;
  firstName: string;
  lastName: string;
  phone: string | null;
  phoneVerified: boolean;
  insurance: Insurance | null;
}

const EMPTY: Profile = {
  onboarded: false,
  firstName: '',
  lastName: '',
  phone: null,
  phoneVerified: false,
  insurance: null,
};

const STORAGE_KEY = 'rewind.profile.v1';

interface ProfileContextValue {
  profile: Profile;
  loaded: boolean;
  update: (patch: Partial<Profile>) => void;
  /** Start onboarding again from the first step. */
  reset: () => void;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile>(EMPTY);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (raw) setProfile({ ...EMPTY, ...JSON.parse(raw) });
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const value = useMemo<ProfileContextValue>(() => {
    const save = (next: Profile) => {
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    };
    return {
      profile,
      loaded,
      update: (patch) => setProfile((prev) => save({ ...prev, ...patch })),
      reset: () => setProfile(save(EMPTY)),
    };
  }, [profile, loaded]);

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfile must be used inside <ProfileProvider>');
  return ctx;
}

export function initials(p: Profile): string {
  return (p.firstName[0] ?? '').toUpperCase() || '?';
}
