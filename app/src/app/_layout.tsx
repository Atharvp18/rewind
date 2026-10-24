import { Stack, type ErrorBoundaryProps } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
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

  // Never leave the user on the splash: hide it after 4 s even if storage is slow.
  useEffect(() => {
    const t = setTimeout(() => SplashScreen.hideAsync().catch(() => {}), 4000);
    return () => clearTimeout(t);
  }, []);

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

/**
 * Shown instead of a frozen splash when anything throws while rendering.
 * Plain React Native views only, so it works even if the theme providers failed.
 */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {});
  }, []);
  return (
    <View style={errorStyles.root} accessibilityRole="alert">
      <Text style={errorStyles.title}>Rewind could not start</Text>
      <Text style={errorStyles.body} selectable>
        {error.message}
      </Text>
      <Pressable accessibilityRole="button" onPress={retry} style={errorStyles.button}>
        <Text style={errorStyles.buttonText}>Try again</Text>
      </Pressable>
    </View>
  );
}

const errorStyles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F2FAF6', padding: 24, paddingTop: 96, gap: 16 },
  title: { color: '#0B2427', fontSize: 28, fontWeight: '700' },
  body: { color: '#0B2427', fontSize: 18, lineHeight: 26 },
  button: {
    minHeight: 56,
    borderRadius: 14,
    backgroundColor: '#0E5A63',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { color: '#FFFFFF', fontSize: 20, fontWeight: '700' },
});

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
