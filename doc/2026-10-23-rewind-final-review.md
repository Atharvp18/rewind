# Rewind: Final Project Documentation for Team Review

Status: Final draft for team review (Cal Hacks 13.0). Not approved by anyone outside the team. Nothing here is an approved institutional or sponsor position.

Labels used in this document

- (unverified): not checked against a primary source
- (estimate): a planning figure, not a measurement
- (secondary source): confirmed only through a third-party page

## 1. Overview

- Name: Rewind (working name, see section 17)
- One-line pitch: Point your phone at any product and hear what it is, what it costs, and which card to pay with
- Named community: Blind and low-vision adults who shop independently for groceries and pharmacy items
- Secondary group: Older adults, including those with tremor, for whom small buttons and menus are hard
- Platform: Voice-first mobile app (Expo, React Native)
- Data policy: Mock data only. No real cards, balances, prescriptions, receipts, or personal information

## 2. Problem and Solution

Problem

- Blind and low-vision adults who shop on their own can find price tags hard to read
- They can have difficulty telling whether an item may be HSA/FSA eligible
- They may not know which card to use
- A low HSA/FSA balance can be discovered only when the card is declined at the register

These statements are assumptions until we hear from a blind or low-vision shopper (see section 15). Replace them with that person's words once we have them

Solution

- The user points their phone at a product
- The agent speaks the product name, price, whether it may be HSA/FSA eligible, and which card to use
- The app builds a cart grouped by payment method and reads back the split at checkout
- The app warns the user before a card is declined and suggests another card

Where this differs from existing checkout systems

- Retailer registers can already split eligible and non-eligible items (Walmart is one documented example)
- Rewind's difference is voice-first, pre-purchase guidance while the user is still in the aisle, plus a balance warning before the register
- Do not claim that other retailers cannot split payments

## 3. Customer Segments

- Primary: Blind and low-vision shoppers who shop independently or want to
- Primary: Older adults, including those with tremor (for example Parkinson's)
- Secondary: Caregivers and family members who shop with or for them
- Future (B2B, unvalidated): Pharmacies and grocery stores that want accessible checkout, and HSA or benefits providers

Notes

- Wording rule: say "designed for" until there is user feedback and sourced numbers
- HSA contributions are limited to zero for months a person is enrolled in Medicare (IRS Publication 969, quoted by secondary sources). This affects who can add money to an HSA. Rules for spending an existing balance after Medicare enrollment are not verified, so do not make claims about older adults on Medicare in either direction

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
| MLH Commit Fellowship category | Opt in | Interview for a 3-week sprint. Needs the opt-in checkbox and the supplemental form |
| Figma | Plausible | Wireframes and design system |
| Mana | Ask first | $5,000 for best project. Unknown whether our own stack qualifies |
| Apify, Bright Data, Context.dev | Optional, pick at most one | Offline catalog only |
| Fetch.ai | Optional, off the live path | Only if the core is reliable |
| Spacetime | Not planned | Expo and Python support unconfirmed |
| Meta | Stretch | Community feature only |
| Hyphenate | Dropped | Organizers said corporate payments only |
| CRS | Dropped | Does not match card verification |
| Bitdeer, Atlassian, Wajo, Greptile | Not planned | Not on the demo path |

Anthropic judging criteria

- A named community
- A real problem, lived or heard from someone who has lived it
- It works: one thing done well beats a broad demo
- Thoughtful use of Claude, including where it could go wrong

## 5. Scope

Must

- Expo shell with camera and mic
- Voice loop: Cartesia Ink, Claude, Cartesia Sonic
- Claude vision returning structured product JSON
- Eligibility lookup (Moss, or a plain table first)
- Cart, card routing, and reroute logic
- Simulated checkout and a seeded database

Should

- Moss session recall ("what was that cheaper cereal from earlier?")
- Captions, spoken camera framing guidance, large tap targets
- Spoken low-balance alerts
- Two mock insurer profiles with prescription branches

Stretch (only after Must is reliable)

- Payment history with a "possible reimbursement" receipt packet
- 2D visual overlay on the camera preview
- Community voice feature (see section 12)
- Sales tax estimate with a fixed rate for one state
- User-set low-balance level

Cut

- Three-agent Fetch.ai Bureau as the default backend (use plain Python functions, Fetch.ai only as an optional add-on)
- Apify catalog as a requirement (hand-build about 30 products instead)
- Five insurers (build two, list the others as planned)
- Coupon payment methods
- True 3D AR (needs ViroReact, which does not run in Expo Go)

## 6. Product Flow

### 6.1 Onboarding

- The user links their HSA card and other payment cards once
- The demo uses mock accounts only
- The user picks one of two mock insurer profiles
- No real insurance card is scanned, because a card cannot confirm that someone has an HSA

### 6.2 In-Store Scan

- The user points the phone at a product
- Claude vision returns product name, price, category, and confidence
- The app classifies the item as "may be HSA eligible" or "not likely HSA eligible"
- If the item is a medication, the app checks the selected insurer profile
- The agent speaks item, price, eligibility, and card balance, then asks for confirmation
- The user confirms by voice, and the item joins a cart grouped by payment method

Medication wording (all estimates, always end with a pharmacist check)

- OTC item: "This may be HSA eligible. Some plans include an over-the-counter benefit, so check your plan"
- Prescription item also sold OTC: give the OTC price, say a prescription version may be covered, and say to check with the pharmacist for the copay
- Prescription-only item: say it is a prescription medication and to check with the pharmacist for the copay
- Plan without prescription benefits: say the plan may not include prescription coverage, and that the item may still be HSA eligible
- Prescriptions are scanned from the pill bottle label, then the agent reads the drug name and strength back for the user to confirm. Fallback: the user says the drug name

### 6.3 Smart Checkout

- The user says "checkout"
- The agent reads the split by card and the totals
- The user confirms, and the app runs a simulated payment and reads the new balances

### 6.4 Balance Protection and Card Suggestions

- Rule 1, item too large: if one item exceeds a card's balance, suggest another card for that item
- Rule 2, group too large: if a card's total exceeds its balance, suggest moving items or adding a second card, and say the amounts aloud
- Rule 3, nothing covers it: say so clearly, and do not choose for the user
- The user confirms every change by voice
- After a purchase, speak an alert when any balance crosses a threshold

### 6.5 Voice Commands

- Core: "add that", "skip it", "read it again", "what's in my cart", "checkout", "remove last item"
- "Repeat that" helps users with memory difficulties

### 6.6 Payment History and Reimbursement Packet (stretch)

- A mock table of past payments: date, store, items, amount, card, and a per-item "may be HSA/FSA eligible" flag
- Items flagged eligible but paid with another card are marked "possible reimbursement" and gathered into an itemized receipt packet for the user to submit
- The app prepares the packet. It does not file claims or reimburse anyone
- Claude can answer questions such as "what did I spend this week?"
- No real names, phone numbers, or tracked locations, so receipts use fake values
- Tax estimate: fixed rate for one state, labeled as an estimate. Tax treatment of groceries and medicine varies and is unverified
- Reimbursement rules differ by plan and administrator (unverified), so every packet carries "may be eligible, check your plan"

## 7. Technical Stack and Architecture

| Layer | Choice | Notes |
|---|---|---|
| Mobile app | Expo (React Native) in Expo Go | Camera and mic. No native AR |
| Vision and reasoning | Claude (main), Gemini Flash (fallback if credits run out) | Confirm credits at the Anthropic booth |
| Speech to text | Cartesia Ink, streaming | Idle WebSocket closes after 3 minutes (secondary source), so build reconnect |
| Text to speech | Cartesia Sonic, streaming | Start speaking before the reply is complete |
| Retrieval | Moss | JavaScript and Python SDKs. React Native support unconfirmed, so call it from the backend |
| Account data | Nessie mock accounts | Account types found in third-party docs are Checking, Savings, and Credit Card, so model the HSA as a Checking or Savings account with an HSA nickname. Confirm at the Capital One booth |
| Database | Supabase (primary), SQLite (backup) | One backend setting switches between them |
| Backend | Python 3.12 or 3.13, functions behind an API | FastAPI suggested. The app talks to the backend, not the database |
| Optional | Fetch.ai uAgents, one catalog scraper | Only if time allows. One uAgents example reports problems on Python 3.14 |

### 7.1 Request Flow

1. The app captures a camera frame and streams voice to Cartesia Ink
2. The backend sends the frame to Claude vision and receives structured JSON
3. The backend queries Moss for the item's eligibility record and classifies it
4. The payment function reads balances, runs routing, and reroutes when a balance is insufficient
5. The voice function calls Cartesia Sonic and streams audio back to the app
6. The session store records each scan for later recall

### 7.2 Data Model

- Cards: id, type (HSA or general), nickname, mock balance
- Products: name, brand, price, category, eligibility flag, source, last updated
- Cart: items, assigned card, running totals per card
- Scans: scanned products with timestamps, for session recall
- Insurers: two mock profiles with prescription benefit flags
- Payments (stretch): mock history rows with a per-item eligibility flag
- Moss collections: eligibility database and session memory, kept separate

Message formats (agree before building)

- ScanResult: name, price, category, confidence, eligibility
- PaymentRecommendation: item, card id, balance before, reroute flag, reason
- VoiceRequest: text to speak, priority (alerts before routine replies)

### 7.3 Data Layer Plan

- Supabase is primary and shared
- SQLite holds the same tables and seed data as the backup
- One Python module wraps all data access, with one setting to choose the backend
- A `reset_demo()` function restores the $340 HSA balance for the first run and sets $15.00 for the declined-card run
- Rehearse switching to SQLite before the demo
- Bring a phone hotspot
- If maintaining both backends costs more than about an hour, drop to SQLite only

### 7.4 Latency Target

- Goal: about 3 seconds from camera frame to first spoken audio (estimate, to be measured early)
- Vision call: about 1 to 1.5 seconds (estimate)
- Moss lookup: under 10 ms per Moss's own claim, to be confirmed
- Sonic first audio: vendor claims about 90 ms, and third-party blogs report about 188 ms from an independent benchmark (lower reliability)
- The earlier 1-second claim is dropped because nothing supports it

## 8. Demo Plan

Setup

- One small shelf: Advil, bandages, kettle corn
- Mock HSA balance of $340 and a mock Visa credit card
- Label all payments as simulated
- Use a prop pill bottle with a fake label, never a real prescription
- Pre-test lighting and the exact shelf

Run 1

1. Advil: "I see Advil, ibuprofen 200mg, $12.99. This may be HSA eligible. Your HSA balance is $340. Want to use your HSA card?" User says yes
2. Bandages: same flow, $5.49 (placeholder, set to the real shelf price)
3. Kettle corn: "Kettle corn, $4.99. Not likely HSA eligible. I'll put this on your Visa credit card"
4. Checkout: "Two items totaling $18.48 on your HSA card. One item totaling $4.99 on your Visa credit. Ready to check out?" User confirms
5. Result: "Payment complete. Your HSA balance is now $321.52"

Run 2 (declined-card moment)

- Set the HSA balance to $15.00
- At checkout: "Your HSA balance is only $15.00, which doesn't cover $18.48. Want me to keep the Advil on your HSA and move the bandages to your Visa credit?" User says yes

Live demo safeguards

- Warm the Cartesia connection and send a test scan before judges arrive
- Push-to-talk fallback for a noisy hall
- Recorded backup video of a clean run
- If a saved result is replayed after a failed scan, say so

## 9. Accessibility and Inclusion

- Voice first: every piece of information is spoken
- Large, high-contrast labels, never relying on color alone
- Tremor and dexterity: large tap targets, tap-anywhere confirm, voice commands in place of small buttons
- Camera framing: spoken guidance such as "move left" or "tilt up"
- Captions: on-screen text of everything the agent says, for deaf and hard of hearing users
- Speech fallback: a tap alternative for users whose speech the model misrecognizes
- Known gaps: deaf and speech-impaired users are served only if captions and tap fallbacks are built

## 10. Role of Claude and Failure Modes

What Claude does

- Reads messy shelf photos and returns structured product data
- Explains the card choice and reroute in plain, spoken language
- Answers questions about scan history and spending (stretch)
- Routing math stays in plain code, not in Claude

Where it could go wrong

- Misreading a price or product, so a blind user hears a wrong cost
- Stating eligibility or a copay too confidently
- Sounding certain when the image was unclear, when the user cannot check the screen

Mitigations

- Read the item back for confirmation
- Say "may be eligible, check your plan"
- Say "I could not confirm" and ask for another scan when unsure
- Read drug name and strength back before any prescription estimate
- Simulated payments and mock data only

## 11. Team Roles (proposed, pending team agreement)

The team has discussed several splits. The informal preferences were: Nak on Cartesia and Figma, Aesha on Moss, Atharv on Visa and Nessie, and Tiea on Fetch.ai. That version leaves Claude vision, the Expo shell, the database, and cart routing without an owner, and puts Fetch.ai (optional) ahead of the Anthropic work. The split below covers every Must item.

| Person | Owns |
|---|---|
| Nak | Expo shell, camera, mic, Cartesia voice loop, main screens |
| Tiea | Claude vision and tool-calling orchestration, Fetch.ai only if there is spare time |
| Aesha | Figma design system, shared Expo components, captions and accessibility testing, catalog and Moss eligibility data |
| Atharv (not yet confirmed as joined) | Database, cart, routing, reroute, Nessie, simulated checkout |

Working rules

- One owner per file area: screens (Nak), shared components (Aesha), backend (Atharv), agents (Tiea)
- Agree on message formats before building starts
- If no fourth member joins, Tiea and Nak split cart and routing, and Aesha pairs on the eligibility data
- Nobody adds a feature without removing one

## 12. Community Feature (stretch)

- Idea: opt-in voice messages tied to a store, played when the app opens
- Parked until the voice loop and shelf scan are reliable (checkpoint: about hour 16)
- Cheap version: pre-recorded demo messages for one fake store, user picks the store, opt-in, captions, and a spoken "report this message" command
- Not planned: automatic store assignment from scan history, because it tracks where vulnerable users shop

## 13. Build Plan and Gates

1. Voice loop: Ink to Claude to Sonic, measure latency (gate at about hour 8)
2. Vision: one still photo returns structured JSON
3. Moss and eligibility: lookup and eligibility flag
4. Cart and routing: card groups, balances, reroute logic
5. Simulated checkout and alerts
6. Polish: captions, framing guidance, demo rehearsal
7. Stretch items, only if the steps above are reliable

Cut order if time runs short: community, overlay, tax check, payment history, insurer branches, Moss session recall

## 14. Risks and Limitations

- Eligibility accuracy: build the eligible list from a documented source (not yet chosen)
- Privacy: synthetic cards and mock data only
- Simulated payment: not a real Visa transaction. Whether Visa offers a test API is unverified
- Real balances: HSA balance access through an aggregator such as Plaid is a possible future path. Plaid lists HSA as an account type, but provider coverage and sandbox access are unverified
- Vision accuracy: keep the demo to one pre-tested shelf
- Latency and noise: test in a loud room, with push-to-talk
- Scope: too many sponsors for one weekend
- Voice connection: Cartesia closes idle connections after 3 minutes (secondary source, confirm in Cartesia's docs)
- Venue network: Cartesia, Claude, and possibly Moss need internet

## 15. Validation and Research Needed

- At least one conversation with a blind or low-vision shopper or an accessibility organization, with a quote to use in the pitch
- Sourced US population counts per segment (CDC disability data, Census American Community Survey, condition organizations)
- How many people in these groups hold an HSA
- HSA eligibility rules. Contributions are limited to zero for months enrolled in Medicare (IRS Publication 969, via secondary sources). Rules for spending an existing balance after Medicare are not verified
- Source for the eligible item list
- Pharmacy benefit data providers for a future real version (not verified)
- How HSA and FSA administrators accept reimbursement claims (not verified)

## 16. Future Plan (to share with judges)

- Partner with organizations serving blind and low-vision people and recruit beta testers
- Reach caregivers through aging-services groups and senior centers
- Offer one local pharmacy a pilot in exchange for feedback
- Link real accounts through the user's provider or an aggregator, with consent and subject to provider support
- Use that link so eligible purchases made on another card can be reimbursed without the user preparing the claim
- True AR and a store community are future use cases

## 17. Open Decisions

1. Final role split (section 11), and who owns Claude vision, the Expo shell, the database, and cart routing
2. Atharv's confirmation that he is joining
3. Final project name (Rewind, or Tally or Clearcart as alternatives), and a collision search
4. Whether the Supabase plus SQLite backup is worth the upkeep, or SQLite alone
5. Who talks to a blind or low-vision shopper
6. Whether every teammate can commit to the 3-week Commit Fellowship sprint before opting in
7. Whether Mana's prize applies to a project built in our own repo
8. Whether Claude credits are available to every team
9. Which eligible-item source to use
10. The submission deadline and any rule on code written before kickoff
11. Submission checklist: Devpost entry, demo video, opt-in checkbox and supplemental form for Commit Fellowship

## 18. Review Checklist by Person

- Nak: voice loop gate, reconnect logic, screen list, and one quote from a user
- Tiea: message formats, Claude vision prompt and failure handling, agent boundaries
- Aesha: design system contrast and tap target rules, eligibility source, accessibility test plan
- Atharv: schema, `reset_demo()`, simulated checkout, the SQLite switch
- Everyone: the open decisions in section 17, and that no real personal data appears anywhere
