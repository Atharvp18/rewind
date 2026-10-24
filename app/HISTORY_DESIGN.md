# Purchase history and invoice: design to confirm

Status: **built** (2026-10-24) with the decisions in section 7. Tell me what to change.
Source: business spec 6.6 (stretch), your messages, and the wireframe (dome, circle, bar).

## 0. What changed already
The dome is back to its previous size. The brown bar in the wireframe is now the word
**History** with a small up chevron, drawn on the dome's bottom edge. It does not add height.

## 1. Resting screen (nothing open)

```
┌───────────────────────────┐
│ [cart]            [profile]│  top row + transcript pill
│  ┌─────────────────────┐  │
│  │  pop-up widget      │  │  scan / cart / checkout / invoice
│  └─────────────────────┘  │
│                           │
│        ╭───────────╮      │
│      ╱               ╲    │  dome (same size as before)
│     │       ( 🎤 )    │   │  mic orb (single circle, unchanged)
│     │   status pill   │   │
│      ╲   ︿ History   ╱    │  <- text handle, on the dome's bottom edge
└───────────────────────────┘
```

- Tap **History**, or swipe up from the bottom edge, opens the history page.
- Screen reader: "Open purchase history, button. Swipe up or double tap."

## 2. History page (full screen, not a widget)

```
 swipe up / tap History
        │
        ▼
┌───────────────────────────┐   slides from the bottom edge to the top,
│ Purchase history      [✕] │   covers the camera, dome and orb
│ Simulated · mock data     │
│ ┌───────────────────────┐ │
│ │ Possible reimbursement│ │   summary (only if there is one)
│ │ $20.98   [Share packet]│ │
│ └───────────────────────┘ │
│ ┌───────────────────────┐ │
│ │ CVS Pharmacy   $37.12 ⌄│ │   one collapsible card per invoice, newest first
│ │ Oct 24                 │ │
│ └───────────────────────┘ │
│ ┌ Walmart Pharmacy  ... ┐ │   scroll to see every past invoice
│        ⌄ More             │   scroll cue
└───────────────────────────┘
```
Close: ✕, or swipe down. The camera and orb come back.

## 3. One invoice (expanded)

```
CVS Pharmacy                          Oct 24, 2026
100 Example Ave, Berkeley, CA 94704   (555) 010-0142
────────────────────────────────────────────────
Advil Ibuprofen 200mg                       $12.99
  Qty 1 × $12.99 · paid with Visa credit
  [HSA/FSA eligible] [Possible reimbursement]
Granola bars                                 $4.49
  Qty 1 × $4.49 · paid with Visa credit
  [Not HSA/FSA eligible]
────────────────────────────────────────────────
Subtotal                                    $17.48
Tax (estimate, 7.25%)                        $1.27
Total                                       $18.75
Paid with: Visa credit •••• 1111 · $17.48 (items, before tax)
                                    [ Share invoice ]
```
Possible reimbursement = HSA/FSA-eligible item paid with an everyday card.
Rewind prepares the paperwork. It never files a claim. Administrator decides.

## 4. Checkout → invoice widget → history

```
 Confirm payment
      │
      ▼
 Agent speaks and captions:
 "Payment complete. You paid for your items. Please take them with you.
  Your invoice is saved in History."
      │
      ▼
 Invoice widget appears at the top (same place as checkout / medication cards)
 ┌───────────────────────────┐
 │ Payment complete      [✕] │
 │ CVS Pharmacy · Oct 24     │   modern receipt card: store, items,
 │ Advil ........... $12.99  │   tax estimate, total, paid-with
 │ Total ............ $18.75 │
 │ [ Save to history ]       │
 └───────────────────────────┘
      │ tap Save / ✕ / after the agent finishes + 10 s
      ▼
 widget shrinks and slides DOWN into the History label (about 500 ms);
 History briefly pulses; the invoice is now the newest card in history.
 (Reduce Motion: it just fades out.)
```

## 5. Questions for you (answer yes / change)
1. Handle = chevron + word "History", no bar. OK?
2. History page is full screen and covers the orb. OK, or keep the orb visible?
3. The invoice widget leaves by: your tap **or** automatically 10 s after the agent stops speaking. OK?
4. Spoken line wording above. Change anything?
5. Receipt's "new balances" and the low-balance alert stay inside the invoice widget. OK?

## 6. Spec notes
- All store names, addresses and phones are fake (business spec 6.6).
- Tax: one fixed-rate estimate, labeled estimate.
- New for the backend (not in the tech spec): `GET /v1/payments`, an `invoice` on the checkout result.

## 7. Decisions as built
- Handle: chevron (bobs upward; still with Reduce Motion or when open) + the word **History** (becomes **Close history** when open). 44 pt touch target; tap is the alternative to the swipe (WCAG 2.5.1, 2.5.8).
- History page: full width, from under the status bar down to the dome. The orb stays visible and usable.
- Tapping the orb on the history page: the agent says "You're on your purchase history. You have N invoices. Possible reimbursement: $X. Tap History to go back." then listens.
- History closes itself after inactivity: twice the "Time to answer" setting, at least 60 s. Touch or scroll restarts the clock; it never closes while the agent is speaking or listening (WCAG 2.2.1: adjustable in Settings).
- Checkout: the agent says "Payment complete. You paid for your items, so please take them with you. ... Your invoice is saved in History." The invoice widget flies down to the History label on **Save to history**, the close button, or 10 s after the agent stops speaking.
- Mixed cards: eligible items go to the FSA/HSA, an ineligible item (Kettle corn) goes to the everyday Visa automatically; one payment, one invoice, one "Paid with" line per card.

## 8. Added 2026-10-24
- History is above the cart chip and profile button, with a ✕, swipe-down on its header, a **History** button in the top row (beside Profile), the bottom handle, and the voice command "find invoice history" (also "close history").
- Every invoice has **Download invoice (PDF)**; the summary has **Download packet (PDF)** (all invoices with a possible reimbursement). Uses the phone's share sheet (save to Files, email, upload to the HSA/FSA portal). Rewind never files claims.
- **Store check-in (prototype, SPEC CONFLICT):** tech spec decision 8 and business spec 6.6 / 12 say "never derived from location, no tracked locations". Built because Nak asked, with these limits:
  - asks permission "while using the app"; if denied, nothing happens and the app works as before;
  - position is read **once** at launch, matched on the device to **seeded mock stores** within 150 m, then thrown away. Never stored, never in an invoice (a test checks this);
  - agent: "Are you at Walmart Pharmacy, 2200 Sample Blvd, Oakland, CA 94607? Say yes to check in." Yes: success buzz, "You're officially checked in at Walmart Pharmacy, <address>. Please point your camera at an item to start shopping."; No: "Okay. You can still scan items.";
  - invoices created after a check-in use that store;
  - Profile → Demo → "Pretend I'm at Walmart Pharmacy" runs the same flow without GPS (the simulator has no real position).
  - **Needs a team decision** before it ships, because it contradicts the written spec.
