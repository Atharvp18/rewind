# Rewind accessibility audit (WCAG 2.2 AA)

Target: WCAG 2.2 Level AA (tech spec decision 11). Brand: **Mint Teal** (tech spec 1.9). Status as of 2026-10-24.

✅ = done in code and checked by measurement or code review. ☐ = still has to be tested on a real phone. Nothing has been tested on a device yet.

Re-run the measurements any time a color changes:

```bash
node scripts/contrast-audit.mjs        # exits 1 on any failure
node scripts/contrast-audit.mjs --md   # the tables below
```

## Who this covers: low vision by type

| Condition | What it does to the screen | How Rewind handles it |
|---|---|---|
| Reduced sharpness (acuity) | Small text and thin lines blur | Text 20pt base, up to 200% in-app on top of the phone's size. Prices 44pt. Targets 56pt+. Icons 2.25 to 2.5pt strokes. Everything is also spoken |
| Low contrast sensitivity (cataract, diabetic retinopathy) | Pale-on-pale disappears | All text ≥4.5:1, most ≥7:1 (AAA). High-contrast theme: black, white and bright mint only, 2px edges everywhere |
| Color blindness (protan, deutan, tritan, total) | Status colors look alike | Every status has its own icon shape and words: ✓ HSA eligible, ✕ Not HSA eligible, ? Could not confirm. Alerts: octagon "Declined/Error" (red) vs triangle "Warning/Suggestion" (orange). Simulation results below |
| Glare and light sensitivity | Bright screens hurt; white washes out | Mint-mist background instead of pure white; dark theme; optional camera dimming inside the see-through window |
| Central field loss (macular degeneration) | The center is missing; reads with the edges | Same fixed positions on every screen. Big blocks, not fine detail. Voice reads everything; captions repeat it |
| Peripheral field loss (glaucoma, RP) | Only the center is visible | Main controls cluster at bottom center (Talk, Cart, Scan). Info card sits low in the window, near the dock. Nothing important lives only at the far edges; Profile also opens by voice ("accessibility settings") |
| Blindness | No screen | VoiceOver / TalkBack: Rewind mutes its own voice and announces every line. Every control has a role, label and hint |
| Tremor (secondary audience) | Mis-taps | Tap anywhere on the camera to scan. 56pt+ targets. Destructive actions need a second step |

## The see-through window

The wireframe's rectangle stays **transparent** so the shopper keeps seeing and framing the product, like Google Lens or Apple Live Text.

- **Readable text whatever the camera sees:** text never sits on the camera image. It sits on a solid card at the bottom of the window.
- **A frame that shows up on any shelf:** the window has two strokes, one light and one dark, so one of them always stands out against the scene.
- **Alert colors on the frame:** the inner stroke turns orange for warnings and red for a decline.
- **Room for AR later:** the clear area is reserved for the "2D visual overlay on the camera preview" stretch item (business spec §5).

## Measured contrast

Overlays on the live camera are measured against the two worst cases, a pure white and a pure black scene. For each, at least one edge must pass.

| Element | standard | dark | highContrast | Needs |
|---|---|---|---|---|
| Body text on background | 15.26 | 16.36 | 21.00 | 4.5:1 |
| Body text on card | 16.21 | 14.45 | 21.00 | 4.5:1 |
| Secondary text on card | 7.42 | 8.60 | 21.00 | 4.5:1 |
| Secondary text on background | 6.99 | 9.73 | 21.00 | 4.5:1 |
| Control border on card | 4.63 | 5.45 | 21.00 | 3:1 |
| Primary button label | 7.89 | 10.89 | 16.73 | 4.5:1 |
| Primary button vs card | 7.89 | 9.61 | 21.00 | 3:1 |
| Mint button label | 9.63 | 10.89 | 16.73 | 4.5:1 |
| Mint button edge vs card (fill or text-color border) | 16.21 | 14.45 | 21.00 | 3:1 |
| Dock text, light end | 14.64 | 12.64 | 21.00 | 4.5:1 |
| Dock text, dark end | 10.75 | 7.15 | 21.00 | 4.5:1 |
| Talk button vs dock, top | 4.58 | 10.43 | 21.00 | 3:1 |
| Talk button vs dock, bottom | 7.28 | 4.76 | 21.00 | 3:1 |
| Talk icon and label, light end | 5.07 | 13.49 | 16.73 | 4.5:1 |
| Talk icon and label, dark end | 10.97 | 10.89 | 16.73 | 4.5:1 |
| Dock edge vs white scene | 7.89 | 14.16 | 21.00 | 3:1 |
| Dock edge vs black scene | 18.97 | 12.48 | 21.00 | 3:1 |
| Caption pill text | 14.64 | 12.51 | 21.00 | 4.5:1 |
| Caption pill vs white scene | 16.21 | 14.01 | 21.00 | 3:1 |
| Caption pill vs black scene | 18.97 | 18.75 | 21.00 | 3:1 |
| Profile initial | 16.21 | 16.21 | 21.00 | 4.5:1 |
| Profile button vs white scene | 16.21 | 16.21 | 21.00 | 3:1 |
| Profile button vs black scene | 21.00 | 21.00 | 16.73 | 3:1 |
| Window frame vs white scene | 7.89 | 18.32 | 21.00 | 3:1 |
| Window frame vs black scene | 21.00 | 12.48 | 21.00 | 3:1 |
| Window frame (warning) vs either scene | 3.88 | 12.32 | 13.51 | 3:1 |
| Window frame (danger) vs either scene | 6.54 | 9.20 | 10.44 | 3:1 |
| Info card vs white scene | 16.21 | 16.18 | 21.00 | 3:1 |
| Info card vs black scene | 21.00 | 11.16 | 21.00 | 3:1 |
| HSA eligible label | 5.73 | 9.25 | 16.73 | 4.5:1 |
| Not HSA eligible label | 6.13 | 8.64 | 21.00 | 4.5:1 |
| Could not confirm label | 6.20 | 7.85 | 13.47 | 4.5:1 |
| Red alert title | 5.72 | 7.05 | 10.44 | 4.5:1 |
| Red alert body text | 14.17 | 14.37 | 21.00 | 4.5:1 |
| Red alert edge vs card | 6.54 | 7.09 | 10.44 | 3:1 |
| Orange alert title | 6.21 | 9.43 | 13.51 | 4.5:1 |
| Orange alert body text | 14.79 | 14.35 | 21.00 | 4.5:1 |
| Orange alert edge vs card | 3.88 | 9.49 | 13.51 | 3:1 |
| Selected option border vs card | 7.89 | 9.61 | 16.73 | 3:1 |

### Color-vision simulation

Machado et al. 2009 (severity 1) for protanopia, deuteranopia and tritanopia, plus achromatopsia (no color at all). Values are CIE76 color differences; under 15 the two colors read as about the same.

| Status colors (ΔE, standard theme) | normal | protanopia | deuteranopia | tritanopia | achromatopsia |
|---|---|---|---|---|---|
| Eligible vs not eligible | 35 | 20 | 14 (merges) | 21 | 2 (merges) |
| Eligible vs could not confirm | 73 | 55 | 49 | 19 | 3 (merges) |
| Not eligible vs could not confirm | 40 | 34 | 35 | 11 (merges) | 1 (merges) |
| Red alert vs orange alert | 36 | 32 | 21 | 25 | 14 (merges) |

Every status label must reach 4.5:1 on a light tint, so they end up at similar lightness. That's why some pairs merge for some people, and why color is never the only signal: each status and alert level has its own icon shape and its own words (WCAG 1.4.1).

## Checklist

**Perceivable**

- ✅ 1.1.1: icons are decorative and hidden from screen readers; the text next to them, or the control's label, carries the meaning. Icon library: Lucide (no emoji).
- ✅ 1.2.2 Captions: every spoken line shows in the caption pill; on by default; the caption is exactly the spoken text.
- ✅ 1.4.1 Use of color: icon + words + color for statuses and alerts. Selected settings show a check icon, a thick border and bold text.
- ✅ 1.4.3 / 1.4.6 / 1.4.11: see the tables; most text is AAA.
- ✅ 1.4.4: text up to 200% in-app, on top of the phone's text size. Layouts wrap and scroll. Fixed-size items are only icons and initials inside round buttons, whose labels are separate.
- ☐ 1.4.4 on the demo phone: every screen at 200% with the phone's largest text.

**Operable**

- ✅ 2.5.8: every target 56pt or larger (WCAG 24px, Apple 44pt, Material 48dp). Talk is 104pt, Profile 64pt.
- ✅ Every action works by tap or by voice. Tap anywhere on the camera to scan.
- ✅ Destructive actions need a second step (Clear cart). Payments need a confirmation tied to a live prompt.
- ✅ 2.2.2 / 2.3.1: nothing flashes. With Reduce Motion the pill and window appear instantly.
- ✅ Main controls at the bottom within thumb reach; safe areas respected.

**Understandable**

- ✅ Each permission is explained in plain words before the phone asks.
- ✅ The name, insurance and cards are read back and confirmed before saving. Pill-bottle name and strength are read back before anything proceeds; no medical advice.
- ✅ Two alert levels, always with a title word: red "Declined" / "Error" / "Service down"; orange "Warning" / "Suggestion" / "Balance too low" / "Low balance".

**Robust and assistive tech**

- ✅ Roles, labels and hints on every control; switches and radio groups for settings.
- ✅ With VoiceOver or TalkBack on, Rewind's voice is muted and each line is announced (decision 13).
- ☐ Walk every flow with VoiceOver and TalkBack.

**Haptics**

- ✅ Talk tap: medium impact. Answer finished: success. Orange alert: warning. Red (decline, error): error. Capture: heavy.
- ✅ Never the only signal, and can be turned off (Profile → Screen → Vibration). Android strength varies by device.

**Device tests (tech spec 4.5)**

- ☐ Permission denied paths
- ☐ Silent switch and Bluetooth
- ☐ Incoming call mid-sentence
- ☐ 3-minute idle reconnect
- ☐ Barge-in
- ☐ Window frame over a bright shelf and a dark shelf
