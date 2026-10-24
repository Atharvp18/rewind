import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { A11yProvider, useA11y } from '@/lib/a11y';
import { ProfileProvider, useProfile } from '@/lib/profile';
import { AgentProvider } from '@/state/agent';

SplashScreen.preventAutoHideAsync();

function Navigator() {
  const { palette, themeName, reduceMotion, loaded } = useA11y();
  const profile = useProfile();

  useEffect(() => {
    if (loaded && profile.loaded) SplashScreen.hideAsync();
  }, [loaded, profile.loaded]);

  // One camera screen plus Profile (top-right button). No tabs.
  return (
    <>
      <StatusBar style={themeName === 'standard' ? 'dark' : 'light'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.bg },
          animation: reduceMotion ? 'none' : 'slide_from_right',
        }}>
        <Stack.Screen name="index" />
        <Stack.Screen
          name="profile"
          options={{ presentation: 'modal', animation: reduceMotion ? 'none' : 'slide_from_bottom' }}
        />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <A11yProvider>
        <ProfileProvider>
          <AgentProvider>
            <Navigator />
          </AgentProvider>
        </ProfileProvider>
      </A11yProvider>
    </SafeAreaProvider>
  );
}
