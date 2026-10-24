# Rewind app (Expo SDK 57)

Voice-first, camera-first shopping assistant for older and low-vision shoppers. Point the phone at a product and hear what it is, what it costs, and which card to pay with. Product rules live in `../specs/`.

**Demo build only.** All payments are simulated. It is not HIPAA compliant and not production ready. Card data is mock except where noted below.

## Run it

Requires Node 22.13+ or 24.3+.

```bash
cd app
npm install
npx expo start            # same Wi-Fi as the phone
npx expo start --tunnel   # if the venue Wi-Fi blocks it
```

Scan the QR code with **Expo Go** (SDK 57). Log in to the same Expo account on the laptop and the phone (needed for SDK 57 on iOS). **Do not update Expo Go on the demo phone**; the SDK 58 store build will not open this app (tech spec 0.4).

Every native module this app uses is included in Expo Go: camera, audio, speech, haptics, image manipulator, file system, linear gradient, AsyncStorage. No development build is needed. Only adding a library with native code that Expo Go does not include would require one (`npx expo run:ios` or EAS).

## Backend or mock

`src/lib/api.ts` is the only file that talks to the backend.

- `USE_MOCK = true` (default): an offline copy of the demo script (`src/lib/mock-backend.ts`). It can't hear, so speech answers are fixed: the name "Alex Rivera", "yes" to questions, "credit card" for the card type. Card photos return synthetic cards.
- `USE_MOCK = false`: set `BASE_URL` to the laptop's IP, port 8000.

**Reading real cards.** Only the real backend reads a card held up to the camera, through the proposed `POST /v1/onboarding/card-scan` endpoint. The app keeps only the last 4 digits and deletes the photo right after upload. The image does go to the backend and its vision model.

## How it works

One camera screen (wireframe frames 1 to 3):

- **Camera** fills the screen. Tap anywhere, or the dock's Scan button, to scan.
- **Top right:** profile button. Opens your cards, insurance, accessibility mode, and settings.
- **Caption pill** grows out of the profile button when Rewind speaks. Tap it to hear the line again.
- **See-through window** keeps the product visible; information sits on a solid card at its bottom edge (onboarding steps, scan results, cart, checkout, red declines, orange warnings, receipt).
- **Dock:** round Talk button (tap to talk, hold to speak, tap to interrupt), with Cart and Scan beside it.

First launch walks through: permissions → name (spoken back) → demo phone check → insurance card → HSA/FSA and Visa cards.

**Demo runs.** Use Profile → Demo controls.

- **Run 1** (HSA $340.00) ends at $321.52.
- **Run 2** (HSA $15.00): Rewind offers to move the bandages to the Visa. "No, keep my cards" shows a simulated decline. "Yes" pays.

## Checks

```bash
npx tsc --noEmit
npx expo lint
npx expo-doctor
node scripts/contrast-audit.mjs   # WCAG contrast + color-vision check of every theme token
```

Accessibility audit with measured contrast: [ACCESSIBILITY.md](ACCESSIBILITY.md).
