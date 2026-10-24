# Rewind accessibility audit (WCAG 2.2 AA)

Target: WCAG 2.2 Level AA (tech spec decision 11). Status as of 2026-10-24.

✅ = done in code and checked by measurement or code review. ☐ = still has to be tested on a real phone. Nothing in this app has been tested on a device yet.

## Measured contrast

Computed with the WCAG 2.2 relative luminance formula from the tokens in `src/constants/theme.ts`. The camera image behind the overlays can be anything, so see-through and floating parts are measured against both a pure white scene and a pure black scene (the worst cases). The panel is measured at its lowest opacity setting (0.75; high contrast is always solid).

| Element | Standard | Dark | High contrast | Needs |
|---|---|---|---|---|
| Dock text (both gradient ends, worst) | 10.90 | 14.12 | 21.00 | 4.5:1 |
| Talk button vs dock (fill or ring, worst end) | 6.75 | 7.73 | 21.00 | 3:1 |
| Talk label on button (worst end) | 8.86 | 8.86 | 15.91 | 4.5:1 |
| Caption pill text | 13.89 | 11.13 | 21.00 | 4.5:1 |
| Caption pill edge vs white scene (fill or border) | 17.79 | 12.25 | 21.00 | 3:1 |
| Caption pill edge vs black scene (fill or border) | 16.40 | 19.08 | 21.00 | 3:1 |
| Profile initial on disc | 17.79 | 17.79 | 21.00 | 4.5:1 |
| Profile button vs white scene (disc or ring) | 17.79 | 17.79 | 21.00 | 3:1 |
| Profile button vs black scene (disc or ring) | 21.00 | 21.00 | 15.91 | 3:1 |
| Panel text, min opacity, white scene | 6.94 | 6.94 | 21.00 | 4.5:1 |
| Panel text, min opacity, black scene | 17.33 | 17.33 | 21.00 | 4.5:1 |
| Panel secondary text, min opacity, white scene | 5.41 | 5.41 | 21.00 | 4.5:1 |
| Amber button vs panel (white scene) | 3.45 | 4.30 | 15.91 | 3:1 |
| Card inside panel vs panel (fill or border) | 6.94 | 3.78 | 21.00 | 3:1 |
| Decline panel border (white scene) | 4.09 | 4.09 | 10.44 | 3:1 |

Earlier tokens (screens, badges, status colors) are measured in tech spec 1.9.

Fixed during this audit, each failing before the change:

- Caption pill edge: 1.28:1 on a white scene. Added a 2px border in the text color.
- Decline border: dark red measured 1.06:1 on the brown panel. Changed to `#FFB4AB`.
- Dark-theme cards inside the panel: 2.29:1. Border changed to `#B8C0CC`.
- The wireframe's gray ring on the gray dock measured 2.80:1, so it was not used.

## Checklist

**Perceivable**

- ✅ 1.2.2 Captions: every spoken line shows in the caption pill; on by default. The caption is `VoiceRequest.text`, so it always matches the speech.
- ✅ 1.4.1 Use of color: eligibility uses icon + words + color (✓ / ✕ / ?). The decline shows ⚠ and the title "Payment declined". Selected settings show ✓, a thick border, and bold text.
- ✅ 1.4.3 / 1.4.11 Contrast: see the table above.
- ✅ 1.4.4 Resize text: in-app text size from 100% to 200%, on top of the phone's own text size. Layouts wrap and scroll; nothing has a fixed height except the fixed-size glyphs inside round buttons, whose text labels are separate.
- ☐ 1.4.4 Check every screen at 200% with the phone's largest text size, on the demo phone.

**Operable**

- ✅ 2.5.8 Target size: every control is at least 56pt (WCAG minimum 24px; Apple 44pt; Material 48dp). Talk is 104pt, the profile button 64pt.
- ✅ Every action works by tap or by voice. Tap anywhere on the camera to scan (helps with tremor).
- ✅ Destructive actions need a second step: Clear cart asks first. Checkout needs a confirm bound to a live prompt.
- ✅ 2.2.2 / 2.3.1: nothing flashes. With Reduce Motion (phone or in-app setting) the pill and panel appear instantly.
- ✅ Primary controls at the bottom, within thumb reach; safe-area insets respected.

**Understandable**

- ✅ Onboarding explains each permission in plain words before the phone asks.
- ✅ The name, insurance and cards are read back and need a yes before they are saved.
- ✅ A pill-bottle drug name and strength are read back; nothing proceeds until confirmed. No medical advice is given.

**Robust / assistive tech**

- ✅ Every control has `accessibilityRole` and `accessibilityLabel`; most have `accessibilityHint`. Toggles use role `switch`; choices use `radio` inside a `radiogroup`.
- ✅ With VoiceOver or TalkBack on, Rewind mutes its own voice and sends each line as an announcement (decision 13).
- ☐ Walk every flow with VoiceOver (iOS) and TalkBack (Android): focus order, labels, and the announcements.

**Haptics**

- ✅ Talk tap: medium impact. Answer finished: success. Decline, alert, error: error. Camera capture: heavy impact.
- ✅ Never the only signal: each buzz comes with speech and on-screen text. Can be turned off in Profile → Screen → Vibration.
- Note: Android haptic strength varies by device, and some devices have no motor.

**Device tests (tech spec 4.5)**

- ☐ Permission denied paths (camera, microphone)
- ☐ Silent switch and Bluetooth headphones
- ☐ Incoming call mid-sentence
- ☐ 3-minute idle reconnect
- ☐ Barge-in (tap Talk while Rewind is speaking)
