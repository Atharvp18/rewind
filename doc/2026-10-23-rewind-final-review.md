# Rewind: Final Project Documentation for Team Review

**Status:** Final draft for team review (Cal Hacks 13.0). Not approved by anyone outside the team. Nothing here is an approved institutional or sponsor position.

**Labels used in this document**

- **(unverified):** not checked against a primary source
- **(estimate):** a planning figure, not a measurement
- **(secondary source):** confirmed only through a third-party page

**Terminology rule:** where this document says HSA alone, the feature must work for both HSA and FSA

---

## 1. Overview

| Field | Detail |
|---|---|
| Name | Rewind (working name, see section 17) |
| Pitch | Point your phone at any product and hear what it is, what it costs, and which card to pay with |
| Primary audience | Elderly and low-vision adults who shop independently for groceries and pharmacy items |
| Secondary audience | Older adults, including those with tremor, for whom small buttons and menus are hard (future scope) |
| Platform | Voice-first mobile app (Expo, React Native) |
| Data policy | Mock data only. No real cards, balances (Nessie API), or personal information. Prescriptions use real data for users. Receipts use real data. The user's UnitedHealthcare profile is also mock. United is real insurance; BlueCross insurance is real; the other three providers use mock data (conflicts with the mock-only statements in sections 6.1, 10, and 14; see section 17) |

---

## 2. Problem and Solution

### Problem

- Elderly and low-vision adults who shop on their own can find price tags hard to read
- They can have difficulty telling whether an item may be HSA/FSA eligible
- They may not know which card to use
- A low HSA/FSA balance can be discovered only when the card is declined at the register
- They may not know how much their insurance will cover

### Solution

1. The user points their phone at a product
2. The app captures the image and sends it to the backend, where a vision LLM API determines the product name, whether it is a medical item (boolean), and the price. The agent then speaks this information to the user
3. If the user says yes to buy the product:

**Medical item flow**

- Check if the user has an insurance card added in the app
- If yes, use the scraped or AI-generated data for that specific insurance provider and tier to determine whether insurance covers the item
- If covered, determine the copay from the data
- If the user's plan has a copay for the selected prescription, the agent suggests that the user walk to the pharmacist and confirm the copay

**Payment routing flow** (applies to all products; uses the price from step 2 for non-medical items, or the remaining amount after copay for medical items)

- Check if the item is HSA/FSA eligible (using a curated list of eligible items)
  - **If eligible:** check if the HSA or FSA balance has enough funds
    - **Sufficient balance:** notify the user and add to the HSA/FSA cart
    - **Insufficient balance:** warn the user and ask whether to add it to their normal Visa card cart instead. If yes, add it there
  - **If not eligible:** notify the user and add to their normal Visa card cart

4. When the user finishes adding items, the agent reads a checkout summary

### How This Differs from Existing Checkout Systems

- Retailer registers can already split eligible and non-eligible items (Walmart is one documented example)
- Rewind's difference is voice-first, pre-purchase guidance while the user is still in the aisle, plus a balance warning before the register
- Do not claim that other retailers cannot split payments

---

## 3. Customer Segments

- **Primary:** Blind and low-vision shoppers who shop independently or want to
- **Primary:** Older adults, including those with tremor (for example Parkinson's)
- **Secondary:** Caregivers and family members who shop with or for them
- **Future (B2B, unvalidated):** Pharmacies and grocery stores that want accessible checkout, and HSA or benefits providers

**Notes**

- Wording rule: say "designed for" until there is user feedback and sourced numbers
- HSA contributions are limited to zero for months a person is enrolled in Medicare (IRS Publication 969, quoted by secondary sources). This affects who can add money to an HSA. Rules for spending an existing balance after Medicare enrollment are not verified, so do not make claims about older adults on Medicare in either direction

---

## 4. Tracks and Prizes

Sponsor details come from sponsor announcements. Full track briefs were not read for the tracks below. Confirm each prize and rule at the sponsor's booth.

| Track | Fit | Notes |
|---|---|---|
| Anthropic, Claude for Public Benefit | Main track | Winner receives $5,000 in Claude credits, 1 year of Claude Max 20x, and office hours |
| Cartesia | Strong | Voice in and out |
| Moss | Strong | Eligibility lookup and session recall |
| Visa, Reimagining Shopping | Strong | $5,000 prize. Card routing and simulated checkout |
| Capital One, Best Use of Nessie | Strong | Mock accounts and balances |
| Microsoft, Built for the Real World | Plausible | Accessibility and real-world users |
| MLH Commit Fellowship category | Opt in | Interview for a 3-week sprint. Needs the opt-in checkbox and supplemental form |
| Figma | Plausible | Wireframes and design system |
| Fetch.ai | Integrated | Necessary |
| Meta | Stretch | Community feature only |

**Anthropic judging criteria**

- A named community
- A real problem, lived or heard from someone who has lived it
- It works: one thing done well beats a broad demo
- Thoughtful use of Claude, including where it could go wrong

---

## 5. Scope

### Must

- Expo shell with camera and mic
- Voice loop: Cartesia Ink, Claude, Cartesia Sonic
- Claude vision returning structured product JSON
- Product lookup and eligibility classification (section 19). Moss holds the eligibility rules. No hand-built product catalog
- Cart, card routing, and reroute logic
- Simulated checkout and a seeded database

### Should

- Moss session recall ("what was that cheaper cereal from earlier?")
- Captions, spoken camera framing guidance, large tap targets
- Universal accessibility button with user-adjustable display settings (see section 6.7)
- Spoken low-balance alerts
- Two mock insurer profiles with prescription branches

### Stretch (only after Must is reliable)

- Payment history with a "possible reimbursement" receipt packet
- 2D visual overlay on the camera preview
- Community voice feature (see section 12)
- Sales tax estimate with a fixed rate for one state
- User-set low-balance level

### Cut

- Three-agent Fetch.ai Bureau as the default backend (use plain Python functions; Fetch.ai only as an optional add-on)
- Any hand-built product catalog (products are read at the shelf and looked up live where a retailer source exists; see section 19)
- Five insurers (build two, list the others as planned)
- Coupon payment methods
- True 3D AR (needs ViroReact, which does not run in Expo Go)

---

## 6. Product Flow

### 6.1 Onboarding

- The user links their HSA card and other payment cards once
- The demo uses mock accounts only
- The user picks one of two mock insurer profiles
- Insurance plan data is mock because some prescriptions are restricted under a given insurance plan and are not eligible under it. Plan-specific coverage differs by insurer and tier, so each mock profile carries its own prescription rules
- No real insurance card is scanned, because a card cannot confirm that someone has an HSA

### 6.2 In-Store Scan

1. The user points the phone at a product
2. Claude vision returns product name, price, category, and confidence
3. The app classifies the item as "HSA eligible" or "is not HSA eligible" and displays the confidence with it. The confidence display is required because HSA/FSA eligible items are marked publicly (team assumption: posters and tags on Walmart and Amazon listings). Sources to back this assumption are still needed (unverified)
4. If the item is a medication, the app checks the selected insurer profile
5. The agent speaks item, price, eligibility, and card balance, then asks for confirmation. For a medication with a plan copay, the agent also states the copay and the remaining charge after the copay, and suggests that the remaining charge go to the HSA/FSA. The team's basis is that an item covered through insurance is HSA/FSA eligible (unverified)
6. The user confirms by voice, and the item joins a cart grouped by payment method

**Eligibility confirmation (replaces "may be eligible" wording)**

The agent does not say "this may be eligible." It researches the item first, then states a result and its confidence, or says it could not confirm.

1. Claude vision reads the package and shelf tag for an HSA/FSA eligibility marking, and for the product name, brand, size, and category
2. The backend checks the category and product against the eligibility rules in Moss (source not yet chosen, section 17 item 6)
3. The two results are compared. If they agree, the app states "HSA eligible" or "is not HSA eligible" with a confidence level
4. If they disagree, or either step is unclear, the app does not guess. It says "I could not confirm eligibility" and asks which card to use (third label, section 17 item 20)
5. The user hears the result, and the item joins the cart only after the user confirms

**Medication items (team decision):** eligibility confidence is 100 percent, because medication eligibility is published online. This applies only when the product is matched exactly (name, strength, and form) to a published listing. The claim that every medication is published online is unverified, and the product match itself can still fail, so an unmatched product falls back to "I could not confirm eligibility." The insurance-covered portion is still not eligible (section 23.2), and copays always end with a pharmacist check.

What counts as confirmed for non-medication items (confidence thresholds) is not yet set. Set it by testing on the demo shelf.

**Medication wording** (all estimates; always end with a pharmacist check)

| Scenario | What the agent says |
|---|---|
| OTC item | "This is HSA eligible, 100 percent confidence. Your plan may also have an over-the-counter benefit." If the item could not be confirmed: "I could not confirm eligibility" |
| Prescription item also sold OTC | Give the OTC price, say a prescription version may be covered, and say to check with the pharmacist for the copay |
| Prescription-only item | Say it is a prescription medication and to check with the pharmacist for the copay |
| Prescription with a copay under the selected plan | Say the plan has a copay for this prescription and suggest that the user walk to the pharmacist and confirm the copay |
| Plan without prescription benefits | Say the plan may not include prescription coverage, and that the item may still be HSA eligible |

Prescriptions are scanned from the pill bottle label, then the agent reads the drug name and strength back for the user to confirm. Fallback: the user says the drug name.

### 6.3 Smart Checkout

1. The user says "checkout"
2. The agent reads the split by card and the totals
3. The user confirms, and the app runs a simulated payment and reads the new balances

### 6.4 Balance Protection and Card Suggestions

| Rule | Trigger | Behavior |
|---|---|---|
| Item too large | One item exceeds a card's balance | Suggest another card for that item |
| Group too large | A card's total exceeds its balance | Suggest moving items or adding a second card; say the amounts aloud |
| Nothing covers it | No card has sufficient balance | Say so clearly and say "Please use a credit card for this item" |

- The user confirms every change by voice
- After a purchase, speak an alert when any balance crosses a threshold

### 6.5 Interface and Voice Interaction

This section groups the interface details by screen element so design and build share one reference. Phases are proposed and need confirmation (see section 17). Interface work is shared by the whole team.

**A. Home screen**

- A large circular button sits in a half-moon drawer near the bottom of the screen
- When the user taps the button, the agent greets them by voice: "How may I help you today?"
- A backup button sits at the bottom of the interface. When tapped, the device vibrates and the agent asks its questions again

**B. Scan result presentation** (see section 6.2)

- The screen and the voice both give item, price, eligibility with confidence, and card balance
- For a medication with a plan copay, they also give the copay and the remaining charge after the copay
- "HSA eligible" and "is not HSA eligible" are the two labels, each shown with confidence

**C. Voice commands**

- Core: "add that", "skip it", "read it again", "what's in my cart", "checkout", "remove last item"
- "Repeat that" helps users with memory difficulties
- Eligibility lookup uses Moss only

**D. Memory support**

- If the agent is speaking to the user about a prescription and the user pauses for 5 to 10 seconds, the agent asks "Would you like to purchase anything?" The purpose is to help the user remember and return to the previous conversation

**E. Purchase history pop-up** (depends on the payment history in section 6.6)

- If the user says "I want to buy Tylenol," a pop-up shows how many times the user has bought it in the previous week, month, and year, and where
- When a payment is made, the invoice records the address of the store

| Element | Group | Proposed phase |
|---|---|---|
| Half-moon drawer and circular button | A | Should |
| Greeting by voice | A | Should |
| Backup button with vibration and repeated questions | A | Should |
| Scan result labels with confidence | B | Must |
| Copay and remaining charge speech | B | Should |
| Voice commands | C | Must |
| Pause prompt | D | Should |
| Purchase history pop-up | E | Stretch |
| Invoice store address | E | Stretch |

### 6.6 Payment History and Reimbursement Packet (stretch)

- A mock table of past payments: date, store, items, amount, card, and a per-item "may be HSA/FSA eligible" flag
- Items flagged eligible but paid with another card are marked "possible reimbursement" and gathered into an itemized receipt packet for the user to submit
- The app prepares the packet. It does not file claims or reimburse anyone
- Claude can answer questions such as "what did I spend this week?"
- No real names, phone numbers, or tracked locations, so receipts use fake values
- Tax estimate: fixed rate for one state, labeled as an estimate. Tax treatment of groceries and medicine varies and is unverified
- Reimbursement rules differ by plan and administrator (unverified), so every packet lists each item's eligibility result and confidence, and states that final approval is up to the administrator

### 6.7 Universal Accessibility Button

A persistent accessibility button appears on every screen, including onboarding, scan, cart, and checkout. It opens a settings panel the user can operate by voice or by touch. The design follows WCAG. The target conformance level and the specific success criteria are not yet chosen and must be confirmed against the primary WCAG source (unverified).

| Setting group | Options |
|---|---|
| Color vision | Color-blind-safe palettes (for example red-green and blue-yellow variants), and a mode where no information depends on color alone (status shown with text, icons, or patterns) |
| Contrast | Standard, high contrast, and dark mode |
| Text | Adjustable text size, bold text, adjustable spacing, and a high-legibility font choice |
| Low vision | Magnified controls and tap targets, reduced visual clutter, and a simplified screen option |
| Motion | Reduced motion and no flashing content |
| Audio | Speech rate, volume, and a repeat-everything option |
| Captions | On-screen captions on or off |
| Input | Voice or tap alternatives for every action, and a push-to-talk option |

**Requirements**

- The button is reachable by screen reader (VoiceOver and TalkBack), with a clear spoken label
- The user can open it by voice ("accessibility settings")
- Settings apply immediately across the whole app
- Settings persist between sessions. Storage location (on device or in the database) is not decided (see section 17)
- Each setting is tested against its WCAG criterion before the demo

---

## 7. Technical Stack and Architecture

Owners are listed per layer and follow the ownership split in section 11. Owner assignments are proposed and need confirmation (see section 17).

| Layer | Choice | Owner | Notes |
|---|---|---|---|
| Mobile app | Expo (React Native) in Expo Go | Nak | Camera and mic. No native AR |
| Vision and reasoning | Claude (main), Gemini Flash (fallback if credits run out) | Tiea | Confirm credits at the Anthropic booth |
| Speech to text | Cartesia Ink, streaming | Nak | Idle WebSocket closes after 3 min (secondary source); build reconnect |
| Text to speech | Cartesia Sonic, streaming | Nak | Start speaking before the reply is complete |
| Retrieval | Moss | Tiea | Python SDK is `moss` (import `from moss import MossClient`); JS SDK is `@moss-js/moss` (Moss quickstart). Call from the backend, not the phone. Credentials: `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY` |
| Product lookup | Shelf tag via vision, barcode, local cache, then retailer lookup where one exists | Tiea (lookup), Atharv (cache) | See section 19. Walmart has a documented lookup; Walgreens and CVS have no official public API found (secondary source) |
| Account data | Nessie mock accounts | Atharv | Model the HSA as a Checking or Savings account with an HSA nickname. Confirm at the Capital One booth |
| Database | Supabase (primary), SQLite (backup) | Atharv | One backend setting switches between them |
| Backend | Python 3.12 or 3.13, functions behind an API | Atharv | FastAPI suggested. The app talks to the backend, not the database |
| Optional | Fetch.ai uAgents | Tiea | Only if time allows. In a local check uagents 0.26.1 and uagents-adapter 0.6.2 installed and imported on Python 3.12, 3.13, and 3.14, but another example reports problems on 3.14, so use 3.12 |

### 7.1 Request Flow

```
App (camera frame + mic audio)
  → Backend (FastAPI; the only place API keys live)
      → Cartesia Ink (speech to text)
      → Claude Vision (structured JSON: name, brand, size, shelf price, barcode digits, category, medical flag, confidence)
      → Product lookup (cache first, then retailer lookup where one exists; section 19)
      → Moss (eligibility rules + classification)
      → Payment function (balances, routing, reroute)
      → Cartesia Sonic (audio, sentence by sentence)
  → App (plays audio, shows captions)
  → Session store (scan logged for recall)
```

The phone never calls Cartesia, Claude, Moss, or Nessie directly. Cartesia's docs say browser WebSockets cannot send request headers and recommend a short-lived access token in the query string; they do not mention React Native. Relaying through the backend avoids that question and keeps secret keys out of the app bundle.

### 7.2 Data Model

| Entity | Fields |
|---|---|
| Cards | id, type (HSA or general), nickname, mock balance |
| Product cache | barcode (UPC) when known, normalized name, brand, size, shelf price, retailer price (optional), category, eligibility label, eligibility confidence, source (shelf tag, barcode, retailer, user-spoken, seeded), last updated. Filled by lookups; not a hand-built catalog |
| Cart | items, assigned card, running totals per card |
| Scans | scanned products with timestamps (for session recall) |
| Insurers | two mock profiles with prescription benefit flags |
| Payments (stretch) | mock history rows with a per-item eligibility flag |
| Moss collections | eligibility database and session memory (kept separate) |

**Message formats** (agree before building)

- **ScanResult:** name, price, category, confidence, eligibility
- **PaymentRecommendation:** item, card id, balance before, reroute flag, reason
- **VoiceRequest:** text to speak, priority (alerts before routine replies)

### 7.3 Data Layer Plan

- Supabase is primary and shared
- SQLite holds the same tables and seed data as the backup
- One Python module wraps all data access, with one setting to choose the backend
- A `reset_demo()` function restores the $340 HSA balance for the first run and sets $15.00 for the declined-card run
- Rehearse switching to SQLite before the demo
- Bring a phone hotspot
- If maintaining both backends costs more than about an hour, drop to SQLite only

### 7.4 Latency Target

**Goal:** ~3 seconds from camera frame to first spoken audio (estimate, to be measured early)

| Step | Estimate | Source |
|---|---|---|
| Vision call | ~1 to 1.5 s | estimate |
| Moss lookup | <10 ms | Moss's own claim, to be confirmed |
| Sonic first audio | ~90 ms (vendor), ~188 ms (third-party benchmark) | secondary source, lower reliability |

The earlier 1-second claim is dropped because nothing supports it.

---

## 8. Demo Plan

### Setup

- One small shelf: Advil, bandages, kettle corn
- Mock HSA balance of $340 and a mock Visa credit card
- Label all payments as simulated
- Use a prop pill bottle with a fake label, never a real prescription
- Pre-test lighting and the exact shelf

### Run 1 (happy path)

| Step | Item | What the agent says |
|---|---|---|
| 1 | Advil | "I see Advil, ibuprofen 200mg, $12.99. HSA eligible, 100 percent confidence. Your HSA balance is $340. Want to use your HSA card?" User says yes |
| 2 | Bandages | Same flow, $5.49 (placeholder; set to the real shelf price) |
| 3 | Kettle corn | "Kettle corn, $4.99. Not HSA eligible, high confidence. I'll put this on your Visa credit card" |
| 4 | Checkout | "Two items totaling $18.48 on your HSA card. One item totaling $4.99 on your Visa credit. Ready to check out?" User confirms |
| 5 | Result | "Payment complete. Your HSA balance is now $321.52" |

### Run 2 (declined-card moment)

- Set the HSA balance to $15.00
- At checkout: "Your HSA balance is only $15.00, which doesn't cover $18.48. Want me to keep the Advil on your HSA and move the bandages to your Visa credit?" User says yes

### Live Demo Safeguards

- Warm the Cartesia connection and send a test scan before judges arrive
- Push-to-talk fallback for a noisy hall
- Recorded backup video of a clean run
- If a saved result is replayed after a failed scan, say so

---

## 9. Accessibility and Inclusion

| Feature | Detail |
|---|---|
| Voice first | Every piece of information is spoken |
| High contrast | Large, high-contrast labels; never relying on color alone |
| Universal accessibility button | A persistent button opens user-adjustable settings for color vision, contrast, text, motion, audio, captions, and input (section 6.7) |
| Tremor/dexterity | Large tap targets, tap-anywhere confirm, voice commands in place of small buttons |
| Camera framing | Spoken guidance such as "move left" or "tilt up" |
| Captions | On-screen text of everything the agent says, for deaf and hard-of-hearing users |
| Speech fallback | A tap alternative for users whose speech the model misrecognizes |

**Known gap:** Deaf and speech-impaired users are served only if captions and tap fallbacks are built.

---

## 10. Role of Claude and Failure Modes

### What Claude Does

- Reads messy shelf photos and returns structured product data
- Explains the card choice and reroute in plain, spoken language
- Answers questions about scan history and spending (stretch)
- Routing math stays in plain code, not in Claude

### Where It Could Go Wrong

| Failure | Mitigation |
|---|---|
| Misreading a price or product, so a blind user hears a wrong cost | Read the item back for confirmation |
| Stating eligibility or a copay too confidently | Confirm eligibility by research first (section 6.2), state the confidence, and say "I could not confirm eligibility" when the research does not settle it. Copays always end with a pharmacist check |
| Sounding certain when the image was unclear | Say "I could not confirm" and ask for another scan when unsure |
| Incorrect prescription identification | Read drug name and strength back before any prescription estimate |

All payments use simulated data and mock accounts only.

---

## 11. Team Roles

The team has discussed several splits. Informal preferences were: Nak on Cartesia and Figma, Atharv on Visa and Nessie, and Tiea on Fetch.ai. That version leaves Claude vision, the Expo shell, the database, and cart routing without an owner, and puts Fetch.ai (optional) ahead of the Anthropic work. The split below covers every Must item and the work previously held by Aesha, who is no longer on the team.

| Person | Owns |
|---|---|
| Nak | Expo, camera, mic, Cartesia voice loop, main screens, shared components, design system contrast and tap target rules, accessibility test plan |
| Tiea | Claude vision and tool-calling orchestration, product lookup (section 19), Moss, Fetch.ai (optional), eligibility data and source |
| Atharv | Backend, Supabase and SQLite backup, cart, routing, reroute, Visa (card routing and simulated checkout), Capital One (Nessie) |

**Working rules**

- One owner per file area: screens and shared components (Nak), backend (Atharv), agents and retrieval (Tiea)
- Agree on message formats before building starts
- If a fourth member joins, reassign the design system and the accessibility test plan first
- Nobody adds a feature without removing one

---

## 12. Community Feature (stretch)

- Invoices of previous store visit: name, address, amount, tax-estimation based on state
- Not planned: automatic store assignment from scan history, because it tracks where vulnerable users shop

---

## 13. Build Plan and Gates

| Gate | Milestone | Approx. hour |
|---|---|---|
| 1 | Voice loop: Ink → Claude → Sonic, measure latency | ~8 |
| 2 | Vision: one still photo returns structured JSON | |
| 3 | Moss and eligibility: lookup and eligibility flag | |
| 4 | Cart and routing: card groups, balances, reroute logic | |
| 5 | Simulated checkout and alerts | |
| 6 | Polish: accessibility button and settings, captions, framing guidance, demo rehearsal | |
| 7 | Stretch items, only if the steps above are reliable | |

**Cut order if time runs short:** community → overlay → tax check → payment history → insurer branches → Moss session recall

---

## 14. Risks and Limitations

| Risk | Detail |
|---|---|
| Eligibility accuracy | Build the eligible list from a documented source (not yet chosen) |
| Privacy | Synthetic cards and mock data only |
| Simulated payment | Not a real Visa transaction. Whether Visa offers a test API is unverified |
| Real balances | HSA balance access through an aggregator such as Plaid is a possible future path. Plaid lists HSA as an account type, but provider coverage and sandbox access are unverified |
| Vision accuracy | Keep the demo to one pre-tested shelf |
| Latency and noise | Test in a loud room, with push-to-talk |
| Scope | Too many sponsors for one weekend |
| Voice connection | Cartesia closes idle connections after 3 min (secondary source; confirm in Cartesia's docs) |
| Venue network | Cartesia, Claude, and possibly Moss need internet |
| Team capacity | With three owners, Tiea carries Claude vision, product lookup, Moss, eligibility data, and the optional Fetch.ai work, and Nak carries the voice loop, screens, and accessibility work (see section 17) |
| Product lookup coverage | No official public product API was found for Walgreens or CVS, and the Walmart API's portal status is unverified (secondary sources). Automated lookups may also breach retailer terms (unverified). The shelf tag is therefore the primary price source (section 19) |
| Store Expo Go update | The App Store Expo Go supports SDK 57 today and is expected to move to SDK 58 within weeks (Expo SDK 58 post). Do not update Expo Go on the demo phone, or the SDK 57 app will stop opening (section 21) |

---

## 15. Validation and Research Needed

- [ ] At least one conversation with a blind or low-vision shopper or an accessibility organization, with a quote to use in the pitch
- [ ] Sourced US population counts per segment (CDC disability data, Census American Community Survey, condition organizations)
- [ ] How many people in these groups hold an HSA
- [ ] HSA eligibility rules. Contributions are limited to zero for months enrolled in Medicare (IRS Publication 969, via secondary sources). Rules for spending an existing balance after Medicare are not verified
- [ ] Source for the eligible item list
- [ ] Pharmacy benefit data providers for a future real version (not verified)
- [ ] How HSA and FSA administrators accept reimbursement claims (not verified)

---

## 16. Future Plan (to share with judges)

1. Partner with organizations serving blind and low-vision people and recruit beta testers
2. Reach caregivers through aging-services groups and senior centers
3. Offer one local pharmacy a pilot in exchange for feedback, and partner with CVS or Walmart Pharmacy or other large companies later
4. Link real accounts through the user's provider or an aggregator, with consent and subject to provider support
5. Use that link so eligible purchases made on another card can be reimbursed without the user preparing the claim on the HSA/FSA user portal
6. True AR and a store community are future use cases

---

## 17. Open Decisions (added in this revision, requires team confirmation)

The earlier draft referenced this section but did not include it. The items below are drawn only from conflicts and gaps in the document.

1. **Working name.** Section 1 lists Rewind as a working name. Decide whether to keep it
2. **Data policy conflict.** Section 1 states mock data only, then says prescriptions and receipts use real data and that United and BlueCross insurance are real. Sections 6.1, 10, and 14 state mock data only. Decide which statement is correct and align all sections. The rationale for mock insurance plan data is now stated in section 6.1, but the real-versus-mock statements for United and BlueCross, prescriptions, and receipts remain unresolved
2a. **Restricted prescriptions.** Section 6.1 states that some prescriptions are restricted under an insurance plan and not eligible. The agent's wording for a restricted, not-eligible prescription is not defined. Provide it or approve a draft
3. **Ownership of Aesha's former work.** Stated by Nak: Moss and Fetch.ai to Tiea; backend, Supabase, Visa, Capital One to Atharv; Cartesia, Expo, camera, mic to Nak. Not stated and assigned provisionally: shared components, design system rules, and the accessibility test plan to Nak (follows Expo and screens); eligibility data and source to Tiea (follows Moss). Confirm or reassign
4. **Tiea's workload.** Tiea now holds Claude vision, Moss, eligibility data, and the optional Fetch.ai work
5. **Cart and routing.** Assigned to Atharv with Visa and the backend. Confirm
6. **Eligibility source.** Section 14 states that no documented source has been chosen
7. **WCAG target.** Section 6.7 requires a WCAG conformance level and version, which are not chosen. Confirm against the primary source
8. **Accessibility button scope and owner.** Which setting groups in section 6.7 are Should versus Stretch, and whether Nak owns the build (provisional, follows screens and shared components). The cut order in section 13 does not yet place this feature
9. **Settings storage.** On device or in the database (Atharv). Not decided
10. **Product catalog.** Resolved by the team: there is no hand-built product catalog. Products are looked up live (section 19). Sections 5, 7, 11, 14, and 18 are updated to match
11. **Interface phases.** The table in section 6.5 assigns phases that the team did not state. Confirm or change them
12. **Store address versus the no-tracking rule.** Section 6.5 group E records the store address on the invoice and shows where past purchases were made. Section 6.6 says no tracked locations, and section 12 says no automatic store assignment from scan history. Decide how store address is entered (for example chosen by the user or taken from seeded mock data) so it does not conflict
13. **Eligibility wording.** Section 6.2 now uses "HSA eligible" and "is not HSA eligible" with confidence. Resolved by the team: "may be eligible" wording is not used. Sections 6.2, 8, 10, 6.6, and 20 are aligned to the research-and-confirm flow in section 6.2
14. **Two buttons.** Section 6.7 describes the accessibility button. Section 6.5 group A describes a backup button with vibration. Confirm whether they are the same button or separate
15. **Insurance and HSA/FSA eligibility.** The team basis that an insured item is HSA/FSA eligible is unverified. It needs a source before it is stated to judges
16. **Nothing covers it.** Section 6.4 no longer says "do not choose for the user." Confirm that the credit card suggestion still requires voice confirmation, as the section states for every change
17. **Public eligibility sources.** The assumption about posters and tags on Walmart and Amazon listings needs cited sources
18. **Figma track.** Section 4 rates Figma as plausible (wireframes and design system). Confirm that the team can still cover the design system work
19. **Retailer lookup scope.** Which of Walmart, CVS, and Walgreens are in the build, given that only Walmart has a documented lookup and that scraping may breach terms (section 19). Default proposed in section 19: shelf tag is the price source, retailers are optional enrichment
20. **Third eligibility state.** Sections 6.2 and 6.5 define two labels. Section 20 needs a third, "could not confirm," for ambiguous items. Approve or reject
21. **Fetch.ai status.** Section 4 says "Integrated, necessary." Sections 5 and 7 say optional and off the live path. Pick one
22. **Screen reader overlap.** When VoiceOver or TalkBack is on, the app's own voice and the screen reader can speak at once. Decide whether the app mutes its own speech or uses screen reader announcements (section 20)
23. **Supabase plus SQLite versus SQLite only.** Section 21 proposes SQLite only. Confirm
24. **Camera frame retention.** Section 20 proposes that frames are not stored after processing. Confirm
25. **Weighted and produce items.** Section 20 proposes they are out of scope for v1. Confirm
26. **100 percent confidence for medication.** Team decision in section 6.2. Needs a source showing that medication eligibility is published online (for example the eligible-item list chosen in item 6), and a rule for what happens when the exact product is not in that list

---

## 18. Review Checklist by Person

- **Nak:** voice loop gate, reconnect logic, screen list, one quote from a user, design system contrast and tap target rules, accessibility test plan
- **Tiea:** message formats, Claude vision prompt and failure handling, agent boundaries, product lookup chain and timeouts (section 19), Moss collections, eligibility source
- **Atharv:** schema, `reset_demo()`, simulated checkout, the SQLite switch, Nessie accounts
- **Everyone:** the open decisions in section 17, and that no real personal data appears anywhere

---

## 19. Product Lookup Strategy (added 2026-10-24)

The team decided that products are not pre-loaded into a catalog. Every product is identified at the shelf and, where a source exists, looked up at Walmart, CVS, or Walgreens. This section defines how that works and what to do when a source is missing.

### 19.1 What each source can and cannot give

| Source | What it gives | Availability | Status |
|---|---|---|---|
| Shelf tag and package (Claude vision) | Product name, brand, size, shelf price, barcode digits if visible | Always, if the image is clear | Primary source for price. It is the price the shopper will pay in that store |
| Barcode (UPC) scan | An exact product identity | Needs the barcode in frame. `expo-camera` barcode scanning in SDK 57 is unverified; check the expo-camera docs | Optional. Use it to make the cache and retailer lookups exact |
| Local cache | A prior result for the same UPC or normalized name | After the first scan | Fast, works offline |
| Walmart | A documented product lookup by item ID and UPC exists (secondary source: third-party wrappers; developer portal and key availability unverified) | Needs a developer key | Optional enrichment |
| Walgreens | No official public API found. One third-party scraper listing describes an unofficial route, and says search pages sit behind a client-side verification step (secondary source) | Not sanctioned | Do not depend on it |
| CVS | No product or price API found | None found | Do not depend on it |

### 19.2 Lookup chain

1. Claude vision extracts name, brand, size, shelf price, barcode digits, category, and medical flag, with a confidence for each field
2. If a barcode is present, use it as the key. Otherwise build a normalized key from brand, name, and size
3. Check the cache. A hit returns instantly
4. On a cache miss, run the retailer lookups that are enabled, in parallel, with a hard timeout (proposed 2 seconds, estimate). A slow or failed lookup is skipped, never waited on
5. Classify eligibility with Moss, using category and product name against the eligibility rules (source not yet chosen, section 17 item 6)
6. Write the result to the cache with its source label
7. Speak the result. Speak what is known first. If a retailer result arrives later, offer it only if it changes the answer

### 19.3 Rules

- **Shelf price wins.** If the shelf price and a retailer price differ, speak the shelf price. Mention the retailer price only when the user asks or the difference is large (threshold to be set)
- **Say the source when it matters.** "Shelf price $4.99" versus "Walmart lists $4.49"
- **Never invent a price.** If no source gives one, say so and ask the user to point at the tag or say the price. A price the user says aloud is stored with source "user-spoken"
- **Never block the first spoken answer on a retailer lookup.** The 3-second goal in section 7.4 depends on this
- **Terms of service.** Before any automated lookup of a retailer site, check that retailer's terms (unverified). Do not scrape behind a login. Do not describe an unofficial route to judges as an integration
- **Disclosure for the demo.** The three demo shelf items (Advil, bandages, kettle corn) are pre-resolved in the cache so the demo cannot fail on a blocked lookup. The app still runs the real pipeline. Tell judges the demo items are pre-cached

### 19.4 Result states

| State | Meaning | What the agent does |
|---|---|---|
| Resolved | Name, price, and eligibility known | Normal flow (section 6.2) |
| Partial | Name known, price or eligibility missing | Speak what is known, ask for the rest |
| Unresolved | Product not identified | "I could not confirm this item. Try another angle, or tell me what it is" |

---

## 20. Edge Cases and Scenarios (added 2026-10-24)

No list can cover every possible scenario. This is the known set. When the team finds a new one, add a row and give it an owner. Items marked (open) have no decision yet.

### 20.1 Camera and vision

| Scenario | Expected behavior |
|---|---|
| Dark, blurry, or glare on the image | Low confidence. Spoken framing help ("move closer", "tilt up"). Never guess a price |
| Several products in frame | "I see more than one item. Hold one up." Do not pick one silently |
| No price tag in frame | Say the price was not found. Ask the user to point at the shelf tag or say the price |
| The tag may belong to the neighboring product | Read back "The tag says $X. Is that for this item?" Require a yes before adding (feasibility of detecting this is unverified) |
| Multi-buy or sale text ("2 for $5", unit price) | Speak the shelf price and the condition. Ask for quantity |
| Weighted or produce items (price per pound) | Out of scope for v1 (open, item 25). Say the per-pound price only and that a total needs a weight |
| Same product in several sizes | Size must be read. If it is not visible, ask |
| Damaged, foreign-language, or partly hidden label | "I could not confirm this item" |
| Camera permission denied | Spoken and on-screen instructions to enable it in phone settings. Fall back to the user saying the product name |
| Camera busy or unavailable | Same fallback, plus a retry |
| People or faces in the frame | Frames are not stored after processing (open, item 24) |

### 20.2 Voice and audio

| Scenario | Expected behavior |
|---|---|
| Microphone permission denied | Tap-only mode with captions. Say how to re-enable |
| Loud room | Push-to-talk. Read back any command before it spends or removes anything |
| Transcript is wrong ("add that" heard as something else) | Unknown command gets "I didn't catch that. You can say add that, skip it, or checkout." Never act on a low-confidence transcript |
| User speaks while the agent is speaking | Stop routine speech at once and listen. Replay a low-balance or declined-card alert afterward |
| Long silence | Prompt after 5 to 10 seconds (section 6.5 D). After two prompts go idle. No endless loop |
| Accent or speech difficulty | Tap alternative for every command. Slower speech-rate setting |
| Streaming connection closes after idle (3 minutes, secondary source) | Reconnect before the next utterance without the user noticing. Warm the connection before the demo |
| Silent switch, Bluetooth headphones, speaker routing | Test on the demo phone. Check the audio mode options in the expo-audio docs for playing in silent mode (unverified) |
| Incoming call or app moves to background | Pause. On return, say "Welcome back, you have N items in your cart" and offer to repeat the last message |
| Two people talking | Push-to-talk. Confirmations are always read back |

### 20.3 Eligibility

| Scenario | Expected behavior |
|---|---|
| Eligibility unknown | Do not route to the HSA/FSA automatically. Say "I could not confirm eligibility" and ask which card (needs a third label, open item 20) |
| Ambiguous items (sunscreen, vitamins, protein bars) | Run the confirmation research (section 6.2). If it still cannot settle it, say "I could not confirm eligibility" and ask which card |
| Bundle with eligible and non-eligible parts | Treat as not confirmed. Ask |
| User has only an FSA, or both | Terminology rule: HSA means HSA and FSA. Use the account the user linked. Ask if two |
| User on Medicare | Make no claim in either direction (section 3) |
| Eligibility depends on a plan rule or a letter of medical necessity | State what the research found. If the item needs a plan rule or letter of medical necessity, say eligibility could not be confirmed and ask which card |

### 20.4 Medication and insurance

| Scenario | Expected behavior |
|---|---|
| Pill-bottle label unreadable or partly visible | Ask the user to rotate it. Fallback: the user says the drug name |
| Drug name or strength misread | Read both back. The user corrects by voice. Nothing proceeds until confirmed |
| Same drug in several strengths | Confirm the strength |
| User asks for medical advice (dose, interactions, "is it safe") | Decline: "I can't give medical advice. Please ask the pharmacist." Put this in the Claude system prompt and test it |
| No insurance profile linked | Skip coverage. Say once: "Add your insurance in settings to hear coverage" |
| Plan has no data for this drug, or copay unknown | "I don't have the copay. Please ask the pharmacist." Never estimate silently |
| Restricted prescription under the plan | Wording undefined (section 17 item 2a) |
| Prescription picked up at the counter | The app gives information only. It does not add a counter prescription to the simulated cart (open) |
| Controlled or pharmacy-only item | Direct the user to the pharmacist. No payment routing |

### 20.5 Payment, balances, and cart

| Scenario | Expected behavior |
|---|---|
| No card linked | Prompt to link one. Checkout is blocked |
| Balance exactly equals the total | Counts as sufficient |
| Balance is zero or negative | Treat as insufficient. Use rule 3 in section 6.4 |
| Balance changed since the scan | Fetch balances again at checkout and rerun routing if they differ |
| Nessie slow or down | Use last known balances, say they are last known, and warn. In the demo, fall back to seeded balances |
| Money math | Use whole cents. Totals are before tax and the agent says "before tax" (tax estimate is stretch) |
| Same item scanned twice | Ask "add another, or is it the same item?" |
| Remove, change quantity, clear cart | Support "remove last item" and "clear cart" (with confirmation) |
| Checkout with an empty cart | "Your cart is empty" |
| User says "yes" to a stale question | Each confirmation is tied to one prompt and expires after a short time (proposed 15 seconds, estimate) |
| Double confirm at checkout | Simulated payment is all-or-nothing with an idempotency key, so it cannot run twice |
| Nothing covers the total | Section 6.4 rule 3, with voice confirmation (open item 16) |
| Refunds and returns | Out of scope |
| Non-US currency | Out of scope (USD only) |

### 20.6 Network and services

| Scenario | Expected behavior |
|---|---|
| No internet | Say so. The cart stays readable from local state. No vision or voice without a connection |
| Backend slow | After about 1 second say "Looking." Timeout at about 8 seconds, retry once, then fall back (all estimates) |
| Claude error, rate limit, or no credits | Switch to Gemini Flash (section 7). If both fail, ask the user to say the product and price |
| Cartesia down | Use on-device speech (an Expo speech package; check its docs, unverified) with captions |
| Moss down or slow | Fall back to a plain eligibility rules table in code |
| Retailer lookup slow or blocked | Skip it (section 19) |
| Venue Wi-Fi blocks traffic or needs a login page | Use a phone hotspot. Rehearse it |

### 20.7 Accessibility

| Scenario | Expected behavior |
|---|---|
| VoiceOver or TalkBack on while the app also speaks | Two voices at once. Decide: mute app speech or use screen reader announcements (open item 22) |
| Largest text size | Layouts must not clip or hide controls. Test at the maximum |
| Reduced motion, dark mode, high contrast | Honored by the settings panel (section 6.7) |
| Tremor or accidental touches | Large targets. Confirm destructive actions by voice or a second tap |
| One-handed or left-handed use | Primary controls reachable at the bottom of the screen |
| Deaf or hard of hearing | Captions on, adjustable volume, tap alternatives |

### 20.8 Privacy and data

| Scenario | Expected behavior |
|---|---|
| Camera frames | Not saved after processing (open item 24) |
| Logs | No API keys, card numbers, or full transcripts in logs |
| Real pill-bottle label (patient name on it) | Demo uses a prop label only. A real version would send that image to a third party and needs its own review |
| Session recall | Per session only. No location tracking (sections 6.6 and 12) |
| API keys | Backend `.env`, gitignored. Never in the app |

### 20.9 Demo day

| Scenario | Expected behavior |
|---|---|
| Expo Go updates itself to SDK 58 | The SDK 57 app stops opening. Turn off automatic app updates on the demo phone and do not update Expo Go |
| iOS Expo Go sign-in expires | Log in again at the venue and test beforehand |
| Phone overheats or the battery drains | Keep a charger and a second phone with the same build |
| Lighting differs at the booth | Pre-test the exact shelf under booth light |
| Judges try their own item | Unresolved path must work cleanly ("I could not confirm this item") |
| Balances left from a previous run | Run `reset_demo()` between runs |
| Live failure | Recorded backup video. If a saved result is replayed, say so |

---

## 21. Build and Environment Guide (added 2026-10-24)

Checked on the lead machine on 2026-10-23 and 2026-10-24 in a throwaway directory. Everything below marked verified was installed and imported successfully. Nothing was tested on a phone.

### 21.1 Versions

| Item | Value | Status |
|---|---|---|
| Node | 24.18.0 on the lead machine. SDK 58 asks for 22.13 or newer on 22, or 24.3 or newer on 24 | Verified, [SDK 58 changelog](https://expo.dev/changelog/sdk-58) |
| Python | 3.12 or 3.13. Use 3.12 | Verified |
| Expo SDK | 57. SDK 58 is released but the store Expo Go for it is "within a few weeks" | [Expo SDK 58 post](https://expo.dev/blog/how-to-upgrade-to-sdk-58) |
| Create command | `npx create-expo-app@latest app --template default@sdk-57` | [create-expo docs](https://docs.expo.dev/more/create-expo/) |
| Expo packages (resolved by `npx expo install`) | expo-camera 57.0.6, expo-audio 57.0.5, expo-sqlite 57.0.4 | Verified |
| Python packages | anthropic 2.1.0, cartesia 4.2.0, supabase 2.33.0, fastapi 0.161.1, uvicorn 0.54.0, pydantic 2.14.1, httpx 0.28.1, pytest 9.1.1, uagents 0.26.1, uagents-adapter 0.6.2, moss 1.21.0 | Verified on 3.12 and 3.13 |
| Audio package | `expo-audio` (recording, and raw PCM microphone capture through `useAudioStream`) | [expo-audio docs](https://docs.expo.dev/versions/latest/sdk/audio/) |
| Cartesia JS SDK | `@cartesia/cartesia-js` exists for Node and browsers. React Native is not mentioned. The app does not use it (relay through the backend) | [Cartesia client libraries](https://docs.cartesia.ai/tools/client-libraries) |
| ViroReact | Not installed and not needed | Verified |

### 21.2 Proposed repository layout (not yet created)

```
rewind/
  doc/        this document
  app/        Expo app (SDK 57)
  backend/    FastAPI, data module, routing, lookup, tests
  .gitignore  must ignore .env, node_modules, .venv
```

### 21.3 Setup order

1. Remove the old global expo-cli so `expo` does not point to a broken version. Only with the owner's approval: `npm uninstall -g expo-cli`. Using `npx expo` avoids the problem either way
2. Log in to Expo in the terminal (`npx expo login`) and in the Expo Go app on the phone, same account. Required for SDK 57 on iOS; not yet enforced on Android ([Expo post on SDK 57 login](https://dev.to/expo/running-an-expo-sdk-57-app-in-expo-go-you-now-need-to-be-logged-in-on-both-ends-32ef))
3. Create the app with the command in 21.1, then `cd app && npm install`
4. Install packages with `npx expo install expo-camera expo-audio`. Add `expo-sqlite` only if the phone stores settings or cart offline. Per section 7, the app talks to the backend, so `@supabase/supabase-js` and `react-native-url-polyfill` are not needed in the app
5. Start with `npx expo start`. Scan the QR code with Expo Go. Phone and laptop need the same Wi-Fi, or use `npx expo start --tunnel`
6. Backend: `/opt/homebrew/bin/python3.12 -m venv .venv`, activate it, then `pip install anthropic cartesia fastapi uvicorn pydantic httpx pytest moss`. Add `supabase` only if Supabase is kept. Add `uagents uagents-adapter` only if Fetch.ai is used
7. Run the backend with `uvicorn`. The phone must reach it by the laptop's local address (or a tunnel). Rehearse this on the venue network or a hotspot

### 21.4 Keys

Keys live in a gitignored `.env` in `backend/`. The app holds none.

| Service | Variable | Status |
|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | Standard SDK name |
| Moss | `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY` | From the [Moss quickstart](https://docs.moss.dev/docs/start/quickstart.md) |
| Cartesia | `CARTESIA_API_KEY` | Name not confirmed in docs |
| Nessie | not looked up | Confirm at the Capital One booth |
| Supabase | URL and key | Only if Supabase is kept; service key stays on the backend |
| Walmart (optional) | key name unknown | Only if the Walmart lookup is built |

Expo variables that start with `EXPO_PUBLIC_` are bundled into the app and visible to anyone who has it (check the Expo environment variable docs, unverified). Never use them for secrets.

### 21.5 Proposed defaults for open choices

| Choice | Default | Why |
|---|---|---|
| Database | SQLite only | Section 7.3 already allows it, and it removes one failure point. Open item 23 |
| TTS playback | Backend returns one audio file per sentence; the app plays each as it arrives | Playing a raw streamed audio feed in Expo Go is unverified. Sentence files are a safer first version |
| STT | App sends microphone audio to the backend; the backend relays to Ink | Keeps keys off the phone |
| Tests | `pytest` for routing, reset, and money math using the demo numbers | Cheapest way to protect the demo |

---

## 22. Readiness for the Spec File (added 2026-10-24)

**Verdict: not yet.** The product idea and flows are clear enough. The document still contradicts itself in places and lacks acceptance criteria, so a spec written from it today would copy those problems.

### 22.1 Must be resolved before writing the spec

| Blocker | Where |
|---|---|
| Data policy conflict: "mock only" versus real prescriptions, receipts, and United and BlueCross insurance | Section 1 against sections 6.1, 10, 14 (item 2) |
| Eligibility source not chosen | Item 6, section 14 |
| Retailer lookup scope | Section 19, item 19 |
| Third eligibility label ("could not confirm") | Item 20 |
| Wording of eligibility lines differs between sections 6.2, 8, and 10 | Item 13 |
| Fetch.ai is "necessary" in one section and optional in others | Item 21 |
| Store address versus the no-tracking rule | Item 12 |
| One button or two (accessibility and backup) | Item 14 |
| Restricted prescription wording | Item 2a |
| Workload: Nak and Tiea each carry too much | Items 3 and 4 |
| WCAG level and version | Item 7 |

### 22.2 Acceptance criteria for Must items (proposed; spec to copy these)

| Must item | Done when |
|---|---|
| Expo shell | The app opens in Expo Go on a physical phone by QR code. Camera preview and microphone prompts work. Denied permissions get the fallbacks in section 20 |
| Voice loop | Spoken "what's in my cart" gets a spoken answer. First audio is about 3 seconds or less in most of 10 tries (estimate; measure). The connection recovers after an idle period without user action |
| Vision JSON | 10 photos of the demo shelf return valid `ScanResult` objects. An unclear photo returns low confidence and the "could not confirm" line |
| Lookup and eligibility | The three demo items get the right labels. An unknown item returns "could not confirm," never a guess |
| Cart and routing | `pytest` covers rules 1 to 3 in section 6.4 using the demo numbers ($340, $15.00, $12.99, $5.49, $4.99) |
| Simulated checkout | Run 1 ends at $321.52. Run 2 produces the reroute in section 8. `reset_demo()` can be run twice with the same result |
| Seeded database | Cards, balances, two insurer profiles, and the three cached demo products exist after reset |

### 22.3 What the spec file should contain

Message schemas with example JSON for `ScanResult`, `PaymentRecommendation`, and `VoiceRequest`; the lookup chain and timeouts (section 19); the edge case table (section 20) with owners; the backend endpoint list; the acceptance criteria above; and the cut order from section 13.

---

## 23. Sources and Corrections for Unverified Claims (added 2026-10-24)

Each row says what was checked, what the source says, and what the document should rely on. Primary means the publisher's own page. Pages marked "partial" were only read in part by the research tool, so read the full page before quoting it to judges.

### 23.1 Confirmed by a primary source

| Claim in this document | Source says | Source |
|---|---|---|
| HSA contributions are zero while enrolled in Medicare | "Beginning with the first month you are enrolled in Medicare, your contribution limit is zero" (Limit on Contributions) | [IRS Pub 969](https://www.irs.gov/publications/p969) (partial) |
| Spending an existing HSA balance after Medicare (was unverified) | Pub 969 says "You are permitted to take a distribution from your HSA at any time" and tax-free for qualified medical expenses. It lists Medicare coverage as a permitted premium use for people 65 or older. The excerpt does not say Medicare enrollment blocks spending | [IRS Pub 969](https://www.irs.gov/publications/p969) (partial). Still avoid claims about Medicare users in the pitch |
| OTC medicines are eligible without a prescription | The IRS says the CARES Act made OTC products and medications reimbursable without a prescription, for amounts paid after Dec. 31, 2019, and added menstrual care products | [IRS newsroom](https://www.irs.gov/newsroom/irs-outlines-changes-to-health-care-spending-available-under-cares-act) |
| Bandages are a medical expense | "You can include in medical expenses the cost of medical supplies such as bandages" | [IRS Pub 502](https://www.irs.gov/publications/p502) (partial) |
| WCAG levels and the criteria in section 6.7 | WCAG 2.2 is a W3C Recommendation, published 12 December 2024. Levels A, AA, AAA. Contrast minimum 4.5:1 (AA, 1.4.3); enhanced 7:1 (AAA, 1.4.6); use of color (A, 1.4.1); text spacing (AA, 1.4.12); resize text to 200 percent (AA, 1.4.4); pause, stop, hide (A, 2.2.2); three flashes (A, 2.3.1); captions (A, 1.2.2); target size minimum (AA, 2.5.8, new in 2.2) | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) (partial). Open item 7 can now be closed by choosing a level; proposal: AA |
| `expo-camera` barcode scanning in SDK 57 | `onBarcodeScanned` and `barcodeScannerSettings` exist. Types include `ean13`, `upc_a`, `upc_e` | [expo-camera docs](https://docs.expo.dev/versions/latest/sdk/camera/) |
| Playing audio when the phone is in silent mode | `setAudioModeAsync` has `playsInSilentMode`, default `true`. Other options: `shouldPlayInBackground`, `interruptionMode`, `allowsRecording` (iOS only) | [expo-audio docs](https://docs.expo.dev/versions/latest/sdk/audio/) |
| `EXPO_PUBLIC_` variables are visible | "These variables will be visible in plain-text in your compiled application"; do not store private keys in them | [Expo environment variables](https://docs.expo.dev/guides/environment-variables/) |
| On-device speech fallback | `expo-speech` is included in Expo Go. Install `npx expo install expo-speech`; call `Speech.speak(text, options)` | [expo-speech docs](https://docs.expo.dev/versions/latest/sdk/speech/) |
| Cartesia key for servers, token for clients | "Use an API key when you're calling from a trusted server." "Use a short-lived access token when calling from a browser or client app" | [Cartesia TTS WebSocket reference](https://docs.cartesia.ai/api-reference/tts/websocket) |

### 23.2 Corrected by research (change the document's claim)

| Claim in this document | Finding | Source |
|---|---|---|
| "The team basis that an insured item is HSA/FSA eligible" (section 6.2 step 5, open item 15) | The sources say the opposite for the insured part. Qualified expenses count "only to the extent the amounts are not compensated for by insurance or otherwise," and expenses paid by insurance cannot be included. The part the shopper pays out of pocket (such as a copay) can still be a qualified medical expense, but that must be checked per plan. Do not say that an insured item is eligible. Say the remaining out-of-pocket amount may be eligible | [IRS Pub 969](https://www.irs.gov/publications/p969), [IRS Pub 502](https://www.irs.gov/publications/p502) (both partial) |
| Cartesia idle timeout is "3 minutes (secondary source)" | Three different figures from three sources. Cartesia's own agent (Line) WebSocket docs say 180 seconds, that any client message or ping resets it, and recommend pings every 60 to 90 seconds. Pipecat (third party) says 3 minutes for speech-to-text and 5 minutes for text-to-speech. The Cartesia TTS reference page does not state it. Plan: send a keepalive about every 60 seconds and reconnect on close | [Cartesia Line WebSocket API](https://docs.cartesia.ai/line/integrations/websocket-api.md), [Pipecat Cartesia TTS](https://docs.pipecat.ai/api-reference/server/services/tts/cartesia), [Pipecat Cartesia STT](https://docs.pipecat.ai/api-reference/server/services/stt/cartesia) |
| Sonic first audio "about 90 ms (vendor), about 188 ms (third-party)" | Vendor figure of about 90 ms is model latency. A 50-trial Humanness Index test measured a median of 159 ms including network for Sonic 2. Another comparison page cites 199 ms at the 90th percentile; its method is unclear. Use 90 ms (vendor) and about 160 to 200 ms (measured over a network) | [Humanness Index, Sonic 2](https://humannessindex.vapi.ai/models/cartesia-sonic-2) |
| Moss lookup "under 10 ms, to be confirmed" | Vendor-run only. The Moss repository README reports P50 3.1 ms, P95 4.3 ms, P99 5.4 ms for 100,000 documents on a MacBook Pro M4 Pro. The Moss quickstart makes no latency claim. No independent benchmark was found. Over the network from the backend, expect more | [Moss README mirror](https://awesome.ecosyste.ms/projects/github.com%2Fusemoss%2Fmoss), [Moss quickstart](https://docs.moss.dev/docs/start/quickstart.md) |
| Where eligible items are marked publicly (section 6.2 step 3, open item 17) | Walmart has a "FSA/HSA Eligible" hub and badges, but no official page explains how items are chosen. Sources are guides and a promotional page. Treat the team assumption as plausible, not confirmed | [Walmart FSA/HSA hub](https://www.walmart.com/cp/6120851) |

### 23.3 Backed by a secondary source only

| Claim | What exists | Source | Next step |
|---|---|---|---|
| Nessie account types and key method | Checking, Savings, Credit Card; base URL `http://api.nessieisreal.com`; key as `?key=` query parameter. From a student project's docs. The official docs returned HTTP 403 to the research tool | [Drift project docs](https://deepwiki.com/aadit2805/drift/4.1-nessie-api-integration) | Open the official docs in a browser, or ask at the Capital One booth |
| Visa sandbox | The Visa Acceptance merchant sandbox provides test keys, sample merchant IDs, test card numbers, and a transaction simulator, and needs a verified business email. Visa Direct sandbox uses only the project's Test Data tab. This supports "Visa offers a sandbox"; it does not mean the track expects it | [Visa Acceptance testing guide](https://developer.visaacceptance.com/hello-world/testing-guide.html), [Visa Developer forum](https://community.developer.visa.com:443/t5/Sandbox-Test-Data/Test-cards-for-web-services-testing/m-p/25503) | Keep checkout simulated. Ask the Visa track staff what they accept |
| Plaid and HSA | Plaid's schema, as reproduced by Layer, puts `hsa` under the investment type. Plaid Exchange's definitions put health savings accounts under depository with a `health` subtype. The two disagree | [Layer, Plaid account](https://docs.layerfi.com/api-reference/plaid-account/plaid-account), [Plaid Exchange definitions](https://plaid.com/plaid-exchange/docs/reference/data-definitions/) | Read Plaid's current schema before any future-plan claim |
| How the register blocks ineligible items | HSA/FSA debit cards use IIAS (Inventory Information Approval System), which compares the UPC or SKU of purchased items against an eligible list at certified merchants. Non-certified merchants rely on a merchant category code and manual receipts. Common decline causes: insufficient balance, ineligible item, or a non-IIAS merchant. Mostly employer benefit documents | [Visa, IIAS requirements](https://myanmar.visa.com/supporting-info/healthcare-card-iias-modal.html), [Vanderbilt FSA substantiation](https://hr.vanderbilt.edu/benefits/FSA_Substantiation_Requirements.pdf) | Add to the pitch honestly: at IIAS stores, ineligible items may already be blocked automatically. Rewind's value is telling the shopper before the register, and which card to use |
| Walmart lookup | The Walmart Marketplace Item Search API (`GET /v3/items/walmart/search`, by UPC or GTIN) is documented but needs a seller token, so it is for sellers, not shoppers. The shopper-side Affiliate API is mentioned only by an unofficial wrapper | [Walmart Item Search](https://developer.walmart.com/us-marketplace/docs/item-search-for-the-walmart-catalog), [WIOpy](https://pypi.org/project/WIOpy/) | Treat Walmart lookup as likely unavailable for a hackathon. Do not plan on it |
| Walgreens and CVS | No official public product API found. One third-party scraper listing describes an unofficial Walgreens route | [Apify Walgreens listing](https://apify.com/crawlerbros/walgreens-scraper.md) | Keep out of the build |

### 23.4 Still unverified (no source found)

| Item | Why | Suggested action |
|---|---|---|
| `CARTESIA_API_KEY` variable name | Not stated in any page read | Check the Cartesia quickstart, or choose your own name since the backend reads it |
| Retailer terms of service for automated lookups | Not read | Read each retailer's terms before any automated lookup, or skip lookups |
| Tax treatment of groceries and medicine by state | Not researched | Keep the tax estimate as stretch, or cut it |
| How HSA and FSA administrators accept reimbursement claims | Not researched | Packets state each item's eligibility result and say final approval is up to the administrator |
| Prize amounts and track rules (section 4) | Sponsor pages not read | Confirm at each booth |
| Whether Claude credits reach every team | Not researched | Ask at the Anthropic booth |
| Whether streamed raw audio plays in Expo Go | Docs describe file and URL playback; streamed playback not found | Use sentence files (section 21.5) and test |
| Pharmacy benefit data providers | Not researched | Future-plan item only |
