import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { A11yProvider, useA11y } from '@/lib/a11y';
import { AgentProvider } from '@/state/agent';

SplashScreen.preventAutoHideAsync();

function Navigator() {
  const { palette, themeName, reduceMotion, loaded } = useA11y();

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  // Stack, not tabs: no small icons, a large Back button on every screen (1.8).
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
        <Stack.Screen name="scan" />
        <Stack.Screen name="cart" />
        <Stack.Screen name="checkout" />
        <Stack.Screen
          name="settings"
          options={{ animation: reduceMotion ? 'none' : 'slide_from_bottom' }}
        />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <A11yProvider>
        <AgentProvider>
          <Navigator />
        </AgentProvider>
      </A11yProvider>
    </SafeAreaProvider>
  );
}
