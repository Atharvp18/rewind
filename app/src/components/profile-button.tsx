import { router } from 'expo-router';
import { Pressable, StyleSheet } from 'react-native';

import { AppText } from '@/components/app-text';
import { Icon } from '@/components/icon';
import { Elevation, Target } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';
import { initials, useProfile } from '@/lib/profile';

export const PROFILE_SIZE = 64;

/**
 * Top-right dark circle (wireframe): opens Profile, which holds the user's
 * cards, accessibility mode, and settings. Shows the user's initial, like a
 * phone's account picture. The light ring keeps it visible on any camera image.
 */
export function ProfileButton() {
  const { palette } = useA11y();
  const { profile } = useProfile();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={profile.firstName ? `Profile, ${profile.firstName}` : 'Profile'}
      accessibilityHint="Opens your cards, accessibility mode, and settings."
      onPress={() => router.push('/profile')}
      hitSlop={8}
      style={({ pressed }) => [
        styles.btn,
        Elevation.floating,
        {
          backgroundColor: palette.profileBg,
          borderColor: palette.controlBorderWidth ? palette.profileRing : 'rgba(255,255,255,0.35)',
          borderWidth: palette.controlBorderWidth ? 3 : 1.5,
          opacity: pressed ? 0.85 : 1,
        },
      ]}>
      {initials(profile) === '?' ? (
        <Icon name="user" size={30} color="onProfile" />
      ) : (
        <AppText color="onProfile" accessible={false} style={styles.initial}>
          {initials(profile)}
        </AppText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: PROFILE_SIZE,
    height: PROFILE_SIZE,
    minWidth: Target.min,
    borderRadius: PROFILE_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Fixed size: it must fit its circle at every text setting. The label carries the meaning.
  initial: { fontSize: 28, lineHeight: 34, fontWeight: '800' },
});
