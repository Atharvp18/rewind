# Rewind: Final Project Documentation for Team Review

**Status:** Final draft for team review (Cal Hacks 13.0). Not approved by anyone outside the team. Nothing here is an approved institutional or sponsor position.

**Labels used in this document**

- **(unverified):** not checked against a primary source
- **(estimate):** a planning figure, not a measurement
- **(secondary source):** confirmed only through a third-party page

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

Sponsor details come from sponsor announcements. Full track briefs were read only for Hyphenate. Confirm each prize and rule at the sponsor's booth.

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
| Mana | Ask first | $5,000 for best project. Unknown whether our own stack qualifies |
| Apify, Bright Data, Context.dev | Optional | Pick at most one. Offline catalog only |
| Fetch.ai | Integrated | Necessary |
| Spacetime | Not planned | Expo and Python support unconfirmed |
| Meta | Stretch | Community feature only |
| Hyphenate | Dropped | Organizers said corporate payments only |
| CRS | Dropped | Does not match card verification |
| Bitdeer, Atlassian, Wajo, Greptile | Not planned | Not on the demo path |

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
- Eligibility lookup (Moss, or a plain table first)
- Cart, card routing, and reroute logic
- Simulated checkout and a seeded database

### Should

- Moss session recall ("what was that cheaper cereal from earlier?")
- Captions, spoken camera framing guidance, large tap targets
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
- Apify catalog as a requirement (hand-build about 30 products instead)
- Five insurers (build two, list the others as planned)
- Coupon payment methods
- True 3D AR (needs ViroReact, which does not run in Expo Go)

---

## 6. Product Flow

### 6.1 Onboarding

- The user links their HSA card and other payment cards once
- The demo uses mock accounts only
- The user picks one of two mock insurer profiles
- No real insurance card is scanned, because a card cannot confirm that someone has an HSA

### 6.2 In-Store Scan

1. The user points the phone at a product
2. Claude vision returns product name, price, category, and confidence
3. The app classifies the item as "may be HSA eligible" or "not likely HSA eligible"
4. If the item is a medication, the app checks the selected insurer profile
5. The agent speaks item, price, eligibility, and card balance, then asks for confirmation
6. The user confirms by voice, and the item joins a cart grouped by payment method

**Medication wording** (all estimates; always end with a pharmacist check)

| Scenario | What the agent says |
|---|---|
| OTC item | "This may be HSA eligible. Some plans include an over-the-counter benefit, so check your plan" |
| Prescription item also sold OTC | Give the OTC price, say a prescription version may be covered, and say to check with the pharmacist for the copay |
| Prescription-only item | Say it is a prescription medication and to check with the pharmacist for the copay |
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
| Nothing covers it | No card has sufficient balance | Say so clearly; do not choose for the user |

- The user confirms every change by voice
- After a purchase, speak an alert when any balance crosses a threshold

### 6.5 Voice Commands

Core: "add that", "skip it", "read it again", "what's in my cart", "checkout", "remove last item"

"Repeat that" helps users with memory difficulties.

### 6.6 Payment History and Reimbursement Packet (stretch)

- A mock table of past payments: date, store, items, amount, card, and a per-item "may be HSA/FSA eligible" flag
- Items flagged eligible but paid with another card are marked "possible reimbursement" and gathered into an itemized receipt packet for the user to submit
- The app prepares the packet. It does not file claims or reimburse anyone
- Claude can answer questions such as "what did I spend this week?"
- No real names, phone numbers, or tracked locations, so receipts use fake values
- Tax estimate: fixed rate for one state, labeled as an estimate. Tax treatment of groceries and medicine varies and is unverified
- Reimbursement rules differ by plan and administrator (unverified), so every packet carries "may be eligible, check your plan"

---

## 7. Technical Stack and Architecture

Owners are listed per layer and follow the ownership split in section 11. Owner assignments are proposed and need confirmation (see section 17).

| Layer | Choice | Owner | Notes |
|---|---|---|---|
| Mobile app | Expo (React Native) in Expo Go | Nak | Camera and mic. No native AR |
| Vision and reasoning | Claude (main), Gemini Flash (fallback if credits run out) | Tiea | Confirm credits at the Anthropic booth |
| Speech to text | Cartesia Ink, streaming | Nak | Idle WebSocket closes after 3 min (secondary source); build reconnect |
| Text to speech | Cartesia Sonic, streaming | Nak | Start speaking before the reply is complete |
| Retrieval | Moss | Tiea | JS and Python SDKs. React Native support unconfirmed; call from the backend |
| Account data | Nessie mock accounts | Atharv | Model the HSA as a Checking or Savings account with an HSA nickname. Confirm at the Capital One booth |
| Database | Supabase (primary), SQLite (backup) | Atharv | One backend setting switches between them |
| Backend | Python 3.12 or 3.13, functions behind an API | Atharv | FastAPI suggested. The app talks to the backend, not the database |
| Optional | Fetch.ai uAgents, one catalog scraper | Tiea | Only if time allows. One uAgents example reports problems on Python 3.14 |

### 7.1 Request Flow

```
App (camera frame + voice)
  → Cartesia Ink (speech to text)
  → Claude Vision (structured JSON)
  → Moss (eligibility lookup + classification)
  → Payment function (balances, routing, reroute)
  → Cartesia Sonic (streaming audio response)
  → Session store (scan logged for recall)
```

### 7.2 Data Model

| Entity | Fields |
|---|---|
| Cards | id, type (HSA or general), nickname, mock balance |
| Products | name, brand, price, category, eligibility flag, source, last updated |
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
| 1 | Advil | "I see Advil, ibuprofen 200mg, $12.99. This may be HSA eligible. Your HSA balance is $340. Want to use your HSA card?" User says yes |
| 2 | Bandages | Same flow, $5.49 (placeholder; set to the real shelf price) |
| 3 | Kettle corn | "Kettle corn, $4.99. Not likely HSA eligible. I'll put this on your Visa credit card" |
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
| Stating eligibility or a copay too confidently | Say "may be eligible, check your plan" |
| Sounding certain when the image was unclear | Say "I could not confirm" and ask for another scan when unsure |
| Incorrect prescription identification | Read drug name and strength back before any prescription estimate |

All payments use simulated data and mock accounts only.

---

## 11. Team Roles

The team has discussed several splits. Informal preferences were: Nak on Cartesia and Figma, Atharv on Visa and Nessie, and Tiea on Fetch.ai. That version leaves Claude vision, the Expo shell, the database, and cart routing without an owner, and puts Fetch.ai (optional) ahead of the Anthropic work. The split below covers every Must item and the work previously held by Aesha, who is no longer on the team.

| Person | Owns |
|---|---|
| Nak | Expo, camera, mic, Cartesia voice loop, main screens, shared components, design system contrast and tap target rules, accessibility test plan |
| Tiea | Claude vision and tool-calling orchestration, Moss, Apify (optional catalog), Fetch.ai (optional), eligibility data and source |
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
| 6 | Polish: captions, framing guidance, demo rehearsal | |
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
| Team capacity | With three owners, Tiea carries Claude vision, Moss, eligibility data, and the optional Fetch.ai and Apify work, and Nak carries the voice loop, screens, and accessibility work (see section 17) |

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
2. **Data policy conflict.** Section 1 states mock data only, then says prescriptions and receipts use real data and that United and BlueCross insurance are real. Sections 6.1, 10, and 14 state mock data only. Decide which statement is correct and align all sections
3. **Ownership of Aesha's former work.** Stated by Nak: Moss, Fetch.ai, Apify to Tiea; backend, Supabase, Visa, Capital One to Atharv; Cartesia, Expo, camera, mic to Nak. Not stated and assigned provisionally: shared components, design system rules, and the accessibility test plan to Nak (follows Expo and screens); eligibility data and source to Tiea (follows Moss). Confirm or reassign
4. **Tiea's workload.** Tiea now holds Claude vision, Moss, eligibility data, and the optional Fetch.ai and Apify work
5. **Cart and routing.** Assigned to Atharv with Visa and the backend. Confirm
6. **Eligibility source.** Section 14 states that no documented source has been chosen
7. **Figma track.** Section 4 rates Figma as plausible (wireframes and design system). Confirm that the team can still cover the design system work

---

## 18. Review Checklist by Person

- **Nak:** voice loop gate, reconnect logic, screen list, one quote from a user, design system contrast and tap target rules, accessibility test plan
- **Tiea:** message formats, Claude vision prompt and failure handling, agent boundaries, Moss collections, eligibility source
- **Atharv:** schema, `reset_demo()`, simulated checkout, the SQLite switch, Nessie accounts
- **Everyone:** the open decisions in section 17, and that no real personal data appears anywhere
