/**
 * Test environment: stand-ins for the native modules the app imports.
 * Nothing here changes app behavior; it only lets the code load without a phone.
 */
jest.mock('expo-crypto', () => ({ randomUUID: () => require('node:crypto').randomUUID() }));

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(async () => {}),
  notificationAsync: jest.fn(async () => {}),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium', Heavy: 'heavy' },
  NotificationFeedbackType: { Success: 'success', Warning: 'warning', Error: 'error' },
}));
