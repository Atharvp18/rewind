# Rewind: Technical Specification

**Derived from:** `specs/business_specs.md` (business spec, sections 1–24; formerly `doc/2026-10-23-rewind-final-review.md`)
**Based on:** Atharv's technical spec draft, adapted for a Supabase-only database and trimmed to what a three-person team can build in one weekend.
**Status:** Implementation-ready. Each owner can build their part in parallel without blocking the others.
**Audience:** Nak, Tiea, Atharv.

---

## How to read this document

| Part | Contents | Who must read it |
|---|---|---|
| **Part 0** | Decisions applied, scope, repo layout, shared contracts, error codes, timeouts | **Everyone, before writing any code** |
| **Part 1** | Mobile app (Expo) | Nak (owner), others for reference |
| **Part 2** | Vision, product lookup, eligibility | Tiea (owner) |
| **Part 3** | Backend, Supabase, cart, routing, checkout, voice relay | Atharv (owner) |
| **Part 4** | Integration, tests, build order, demo runbook | **Everyone** |

Part 0 is a contract. Nothing in Parts 1–3 may change a schema, endpoint, or field name defined in Part 0 without all three owners agreeing. Every other decision inside your own part is yours.

---

# PART 0 — SHARED FOUNDATION

## 0.1 Decisions this spec applies

The business spec still lists open items (section 17). This spec applies the defaults below. Each row can be overturned, but only deliberately and by all three owners.

| # | Open item | Decision applied here | Source |
|---|---|---|---|
| 1 | Data policy conflict | **All data is mock.** No real prescriptions, receipts, or insurer plan data. Insurer profiles are two synthetic plans, visibly labeled mock in the UI and the pitch | Sections 6.1, 10, 14 |
| 2 | Eligibility data source | **Retailer-listed data collected with Apify before the demo** (fsastore.com, per business spec section 19.5), loaded into a Moss index. The IRS category rule table is the fallback and must stand alone | Sections 19.5, 24 |
| 3 | Medication eligibility stated plainly | **Revised 2026-10-24 (Tiea): no barcodes.** Claude Vision reads the product and its category; a shelf (OTC) medicine in an IRS-backed category (CARES Act) is `eligible`. A medicine in any other category falls back to `could_not_confirm`. Scope: shelf medicines only, nothing that needs a doctor's letter | Section 6.2 |
| 4 | Copay and insurance (revised 2026-10-24) | **Insurance applies only to counter prescriptions; shelf items never mention it.** Prescriptions are read back (drug + strength) first. Copay amounts are an **estimate** from the plan's published tier table, labelled as one, only for flat-copay plans with the exact drug and strength listed; coinsurance, deductible-first, prior-auth, off-formulary, and unknown-plan cases give no number and send the user to the pharmacist, whose amount always wins. Only the estimated copay enters the cart (`remaining_after_copay`), never the full price. Copays are generally HSA/FSA-qualified (IRS Pub 502), so the agent **suggests** the HSA ("Copays are usually HSA eligible") but never routes it automatically. Five mock plans; one modeled on UnitedHealthcare Student Resources + OptumRx. A card scan keeps only the plan profile in storage; the cardholder's name is held in memory for the conversation; member ID, group, RxBIN/PCN, and DOB have no field in the extraction schema. Drug names are dropped from the session after each answer. Rewind never files a claim | Sections 20.5, 23; `backend/agents/insurance.py` |
| 5 | Third eligibility label | **Approved.** The label is `could_not_confirm` everywhere: API, database, tests, and app | Sections 20, 24 |
| 7 | Retailer lookup scope | **The shelf tag is the only price source in v1.** No retailer API is built | Sections 19.3, 23.3 |
| 8 | Store address versus no-tracking | **User-entered or seeded mock only.** Never derived from scan history or location | Sections 6.6, 12 |
| 9 | Fetch.ai status | **Second front door, off the phone's live path.** Three ACP agents on Agentverse (orchestrator, product, payment) run the same scan → eligibility → routing → simulated checkout workflow inside an ASI:One chat, with a shelf photo attached in place of the camera. This meets the Fetch.ai track's "primary workflow inside ASI:One" rule without touching the Expo app. Moss is removed; eligibility uses the UPC table and IRS rules. The Fetch.ai Payment Protocol is **not** used for checkout (it cannot express the HSA/Visa split) and is stretch-only as agent monetization. Updated 2026-10-24 | Sections 5, 7; `backend/agents/README.md` | **History (added 2026-10-24):** a fourth read-only agent answers questions about past purchases. Claude fills a fixed form (kind, period, card, medicine_only, category, item); code resolves dates and adds up amounts; a Moss memory of `purchase_items` rows (over-the-counter only) is queried with exact filters, with the table as fallback. Checked live: filters on date, card, amount and flags were exact and complete, recall takes milliseconds once loaded, and a purchase written by another process is visible in about a second.
| 10 | Database | **Supabase only. No SQLite, no local fallback** | Team decision, section 7.3 |
| 11 | WCAG target | **WCAG 2.2 Level AA** | Section 23.1 |
| 12 | One accessibility button or two | **One button.** Short tap repeats the last prompt with haptic feedback. Long press, or saying "accessibility settings," opens the panel | Reconciles 6.5-A and 6.7 |
| 13 | Screen reader overlap | **The app mutes its own speech when a screen reader is on** and sends text through screen reader announcements | Section 20.9 |
| 14 | Camera frame retention | **Frames are never stored.** Held in memory for the request, then discarded | Section 20.10 |
| 15 | Weighted and produce items | **Out of scope for v1** | Section 20.1 |

**Two rules that must not be softened (section 23.2):**

1. The insurance-covered portion of any item is **never** HSA/FSA eligible. Only the shopper's out-of-pocket remainder can be, and even that is gated by decision 4.
2. Never claim that other retailers cannot split eligible and non-eligible payments. IIAS stores already do this at the register (section 23.3). Rewind's claim is **guidance in the aisle, before the register**.

## 0.2 Scope tiers for this build

Build in this order. A tier starts only when the one above it is reliable.

| Tier | Items |
|---|---|
| **Must (demo fails without it)** | Expo shell with camera and mic; voice loop; Claude vision JSON; eligibility label (IRS rules plus seeded demo rows at minimum); cart and routing; simulated checkout; `reset_demo()` |
| **Should** | Apify eligibility index in Moss (gated by the go/no-go test, 2.9); captions; spoken framing guidance; the demo-critical accessibility settings (1.5); spoken low-balance alerts; mock insurer copay branch |
| **Stretch** | Gemini fallback; the rest of the accessibility panel; Moss session recall; payment history; tax estimate; Fetch.ai wrapper |

**Cut order when time runs short:** scraped eligibility index (fall back to IRS rules plus hand-entered demo rows) → community feature → visual overlay → tax estimate → payment history → insurer copay branches → Moss session recall.

## 0.3 Repository layout

```
rewind/
  doc/
    2026-10-23-rewind-final-review.md     business spec
    2026-10-23-rewind-technical-spec.md   this file
  app/                                     NAK owns everything here (Expo Router, SDK 57)
    src/
      app/              routes: index (the one camera screen), profile, _layout (see 1.10)
      components/       shared UI (Screen, VoiceDock, CaptionBar, AccessibilityButton, ...)
      constants/
        theme.ts        color tokens per theme, type scale, spacing, target sizes (1.9)
      lib/
        api.ts          the only file that talks to the backend (0.5 types, 0.6 endpoints)
        api-error.ts    the 0.6 error envelope
        mock-backend.ts offline stand-in used by api.ts when USE_MOCK is true
        audio.ts        mic capture, playback queue
        a11y.tsx        screen reader detection, settings context
        money.ts        integer-cents formatting
        phrases.ts      the only lines the app speaks itself (Looking., welcome back, offline)
      state/
        agent.tsx       the 1.2 state machine (reducer) and its provider
  backend/
    main.py                               ATHARV  FastAPI app + router registration
    models/
      schemas.py                          ATHARV creates, ALL THREE agree (0.5)
    api/
      scan.py                             ATHARV  orchestration endpoint
      voice.py                            ATHARV  STT/TTS relay to Cartesia
      cart.py                             ATHARV
      checkout.py                         ATHARV
      demo.py                             ATHARV  reset endpoint
    speech/
      compose.py                          ATHARV  the only place spoken wording is built
    vision/                               TIEA
      claude_vision.py
      prompts.py
      gemini_fallback.py                  stretch, behind a flag
    lookup/                               TIEA
      chain.py
      normalize.py
    eligibility/                          TIEA
      moss_index.py
      irs_rules.py
      classify.py
    prefetch/                             TIEA  offline, never imported by the API
      apify_run.py
      build_index.py
    payments/                             ATHARV
      routing.py
      cart_store.py
      checkout.py
      nessie.py
    data/                                 ATHARV
      db.py              the only public interface; everything else imports this
      schema.sql         Supabase (Postgres) DDL
      functions.sql      Postgres functions called by RPC (checkout, reset)
      seed.py
      reset_demo.py
    tests/                                owner of the module owns its tests
      fakes/fake_db.py   in-memory test double of db.py (tests only, never used at runtime)
  .env.example
  .gitignore            must contain: .env  node_modules  .venv  audio_tmp/
```

**File ownership is absolute.** If you need a change in someone else's directory, ask them. Do not edit it.

**Voice ownership, stated once to avoid a gap:** Nak owns microphone capture, playback, and captions in the app. Atharv owns the backend relay to Cartesia (`api/voice.py`) and all spoken wording (`speech/compose.py`). Tiea owns nothing in the voice path. Gate 1 (voice loop) is Nak plus Atharv.

## 0.4 Environment and versions

Fixed by business spec section 21.1. Do not upgrade anything mid-build.

| Item | Value | Note |
|---|---|---|
| Expo SDK | **57** | Do **not** update Expo Go on the demo phone. The store's SDK 58 build will stop the SDK 57 app from opening |
| Node | 22.13+ or 24.3+ | |
| Python | **3.12** | |
| Create app | `npx create-expo-app@latest app --template default@sdk-57` | |
| Expo packages | `npx expo install expo-camera expo-audio expo-speech` | Settings persist with AsyncStorage (1.5) |
| Python packages | `anthropic==2.1.0 cartesia==4.2.0 fastapi==0.161.1 uvicorn==0.54.0 pydantic==2.14.1 httpx==0.28.1 pytest==9.1.1 moss==1.21.0 supabase==2.33.0` | Add `apify-client==3.3.0` for the offline prefetch only |

Both the laptop and the phone must be logged in to the **same Expo account** (required for SDK 57 on iOS).

### Environment variables

All keys live in `backend/.env`, gitignored. **The app holds no keys.** Never use `EXPO_PUBLIC_*` for a secret; those values are visible in plain text in the compiled app (section 23.1).

```
ANTHROPIC_API_KEY=
CARTESIA_API_KEY=               name not confirmed in Cartesia's docs; the backend reads it, so this name is ours
MOSS_PROJECT_ID=
MOSS_PROJECT_KEY=
NESSIE_API_KEY=                 confirm the parameter style at the Capital One booth
NESSIE_BASE_URL=http://api.nessieisreal.com
APIFY_TOKEN=                    offline prefetch only
GEMINI_API_KEY=                 stretch fallback only; leave empty unless built

SUPABASE_URL=
SUPABASE_SERVICE_KEY=           backend only, never in the app
REWIND_DEMO_MODE=true
```

`REWIND_DEMO_MODE=true` makes Nessie failures fall back to seeded balances instead of surfacing an error. It does **not** hide a Supabase outage (3.2). Leave it on for the demo.

## 0.5 Shared message schemas

Defined as Pydantic models in `backend/models/schemas.py` and mirrored as TypeScript types in `app/src/lib/api.ts`.

**Money is always an integer number of cents.** No floats or decimals anywhere, in any language, at any layer, including the database. A float in a money field is a bug even if the demo passes.

### VisionExtract — Tiea's vision output, internal

```python
class VisionExtract(BaseModel):
    name: str | None                  # "Advil Ibuprofen 200mg Tablets"
    brand: str | None                 # "Advil"
    size: str | None                  # "200mg, 50 count"
    upc: str | None                   # digits only, from the barcode in frame or the app's barcode hint
    shelf_price_cents: int | None     # 1299
    category: str | None              # one of the controlled values in 2.5
    is_medication: bool
    is_prescription_only: bool | None
    package_eligibility_marking: Literal["eligible", "none_seen"] | None
    field_confidence: dict[str, float]   # per field, 0.0-1.0
    warnings: list[str]                  # codes from 0.7
    raw_model: Literal["claude", "gemini"]
```

### ProductResolution — after the lookup chain, internal

```python
class ProductResolution(BaseModel):
    product_key: str                  # upc if known, else normalized key (2.4)
    upc: str | None
    name: str
    brand: str | None
    size: str | None
    category: str
    is_medication: bool
    is_prescription_only: bool
    amount_cents: int | None           # the shelf price; None means unknown
    price_source: Literal["shelf_tag","cache","user_spoken","seeded"] | None
    state: Literal["resolved","partial","unresolved"]
    warnings: list[str]
```

### EligibilityResult — Tiea's classifier output

```python
class EligibilityResult(BaseModel):
    label: Literal["eligible","not_eligible","could_not_confirm"]
    confidence: float | None            # None when basis is upc_match or irs_category_rule
    basis: Literal["upc_match","semantic_match","irs_category_rule",
                   "package_disagreement","no_match","index_unavailable"]
    source: Literal["retailer_index","irs_rules","hand_entered"] | None
    collected_at: str | None            # ISO 8601 date the source data was collected
    matched_name: str | None            # what it matched against, for the spoken explanation
```

### ScanResult — the object the app receives

```python
class ScanResult(BaseModel):
    scan_id: str                        # uuid4
    timestamp: str                      # ISO 8601
    state: Literal["resolved","partial","unresolved"]
    product: ProductResolution
    eligibility: EligibilityResult
    warnings: list[str]
```

### PaymentRecommendation — Atharv's routing output

```python
class Reroute(BaseModel):
    from_card_id: str
    to_card_id: str
    reason: Literal["insufficient_balance","group_exceeds_balance","user_choice"]

class PaymentRecommendation(BaseModel):
    scan_id: str
    decision: Literal["route_to_hsa","route_to_general","ask_user","blocked"]
    card_id: str | None                 # null when decision is ask_user or blocked
    amount_cents: int
    amount_basis: Literal["shelf_price","remaining_after_copay"]
    balance_before_cents: int | None
    balance_after_cents: int | None
    reroute: Reroute | None
    requires_confirmation: bool          # always true before anything enters the cart
    reason_code: str                     # from the table in 3.5
    card_options: list[str]              # card ids offered when decision == ask_user
```

### VoiceRequest — what the app speaks

```python
class VoiceRequest(BaseModel):
    request_id: str
    prompt_id: str | None                # binds a user "yes" to this exact question (3.7)
    text: str                            # also used verbatim as the caption
    priority: Literal["alert","normal"]  # alert interrupts and is replayed after interruption
    expects_response: bool
    response_scope: Literal["confirm_add","choose_card","confirm_checkout",
                            "confirm_clear_cart","confirm_strength","none"]
    sentences: list[str]                 # pre-split for sentence-by-sentence playback
```

### ScanResponse — the single payload returned by `POST /v1/scan`

```python
class ScanResponse(BaseModel):
    scan: ScanResult
    recommendation: PaymentRecommendation | None   # null when state == "unresolved"
    voice: VoiceRequest
```

## 0.6 Backend HTTP API

Base URL: `http://<laptop-ip>:8000`. Atharv implements all of these. Nak consumes them and calls nothing else.

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| GET | `/v1/health` | — | `{status, upstreams:{claude,cartesia,moss,nessie,supabase}}` | Each upstream is `ok`, `degraded`, or `down`. Nak shows a banner on `down` |
| POST | `/v1/scan` | multipart: `image` (jpeg), optional `barcode`, optional `hint_price_cents` | `ScanResponse` | The main endpoint |
| POST | `/v1/stt` | multipart: `audio` (pcm or wav) | `{transcript, confidence}` | Relays to Cartesia Ink |
| POST | `/v1/tts` | `{text, priority}` | `{request_id, sentences:[{index,text,audio_url}]}` | One short audio file per sentence |
| GET | `/v1/audio/{audio_id}` | — | audio bytes | Served from `audio_tmp/`, deleted after 10 minutes |
| POST | `/v1/command` | `{transcript, confidence, prompt_id?}` | `{action, result, voice: VoiceRequest}` | Interprets a spoken command (3.8) |
| GET | `/v1/cart` | — | `{groups:[{card_id,nickname,items,subtotal_cents}], total_cents}` | |
| POST | `/v1/cart/items` | `{scan_id, card_id, prompt_id}` | `{cart, voice}` | Rejects an expired or mismatched `prompt_id` |
| DELETE | `/v1/cart/items/last` | — | `{cart, voice}` | |
| DELETE | `/v1/cart` | `{prompt_id}` | `{cart, voice}` | Requires confirmation |
| GET | `/v1/cards` | — | `[{id,type,nickname,balance_cents,status}]` | |
| POST | `/v1/checkout/preview` | — | `{groups, total_cents, issues:[...], voice}` | Refetches balances and reruns routing |
| POST | `/v1/checkout/confirm` | `{idempotency_key, prompt_id}` | `{payment_id, groups, new_balances, voice}` | Idempotent and atomic (3.6) |
| POST | `/v1/demo/reset` | `{run: 1 \| 2}` | `{cards, cart}` | Run 1 sets HSA to $340.00; run 2 sets $15.00 |

### Error envelope

Every 4xx and 5xx returns the same shape, so Nak writes one handler:

```json
{
  "error": {
    "code": "E_PROMPT_EXPIRED",
    "message": "human readable, safe to log",
    "speech": "I didn't catch that in time. Shall I ask again?",
    "retryable": true
  }
}
```

`speech` is always present and always safe to speak aloud. Nak speaks it and shows it as a caption, and never writes error wording in the app.

## 0.7 Shared code tables

### Error and warning codes

| Code | Meaning | Raised by | Spoken behavior |
|---|---|---|---|
| `E_VISION_UNCLEAR` | Low confidence on name or price | Tiea | Framing help: "move closer," "tilt up" |
| `E_NO_PRICE` | No price found in frame | Tiea | Ask the user to point at the tag or say the price |
| `E_MULTIPLE_PRODUCTS` | More than one product detected | Tiea | "I see more than one item. Hold one up" |
| `E_PRODUCT_UNRESOLVED` | Cannot identify the product | Tiea | "I could not confirm this item. Try another angle, or tell me what it is" |
| `E_ELIGIBILITY_UNCONFIRMED` | Classifier returned `could_not_confirm` | Tiea | "I could not confirm eligibility" and ask which card |
| `E_MOSS_UNAVAILABLE` | Index down or timed out | Tiea | Silent. Falls back to the IRS category rules |
| `E_NESSIE_UNAVAILABLE` | Balance fetch failed | Atharv | "These are your last known balances" |
| `E_DB_UNAVAILABLE` | Supabase failed or exceeded its budget | Atharv | "I can't reach your cart right now. Let me try again" |
| `E_NO_CARD` | No card linked | Atharv | Prompt to link one; checkout blocked |
| `E_INSUFFICIENT_ALL` | No card covers the amount | Atharv | "Please use another card for this item" (never state the balance) |
| `E_PROMPT_EXPIRED` | A "yes" arrived after the prompt expired | Atharv | Ask the question again |
| `E_STT_LOW_CONFIDENCE` | Transcript below threshold | Atharv | "I didn't catch that. You can say add that, skip it, or checkout" |
| `E_UPSTREAM_TIMEOUT` | Any upstream exceeded its budget | whoever called it | "Sorry, that took too long. Let me try again" |
| `E_MEDICAL_ADVICE_REQUESTED` | User asked about dosage or safety | Tiea | "I can't give medical advice. Please ask the pharmacist" |

### Timeout budget

The target is about 3 seconds from frame to first audio (section 7.4). Do not raise one budget without lowering another. All figures are starting estimates; replace them with measurements at Gate 1.

| Step | Budget | On timeout |
|---|---|---|
| Claude vision | 2500 ms soft, 6000 ms hard | Soft: continue with a partial result. Hard: `E_UPSTREAM_TIMEOUT` |
| Product cache read (Supabase) | 300 ms | Treat as a miss |
| Moss query | 1000 ms | `E_MOSS_UNAVAILABLE`, use category rules |
| Nessie balance | 2000 ms | Use last known, set `E_NESSIE_UNAVAILABLE` |
| Other Supabase reads and writes | 1500 ms | Retry once, then `E_DB_UNAVAILABLE` |
| Routing | in-process, under 5 ms | n/a |
| Cartesia Sonic, first sentence | 1500 ms | Fall back to `expo-speech` on the phone |
| **Whole `/v1/scan`** | **8000 ms** | Return a partial `ScanResponse` with a spoken fallback |

Nak speaks "Looking." if no response has arrived after **1000 ms**.

### Confirmation and session rules

- Every prompt that spends, adds, or removes anything carries a `prompt_id` and **expires 15 seconds** after it is spoken.
- A `prompt_id` is single-use. Reusing it returns `E_PROMPT_EXPIRED`.
- Nothing enters the cart, and no payment runs, without a voice or tap confirmation bound to a live `prompt_id`.
- Cartesia idle connections close at about 180 seconds (Cartesia's agent WebSocket docs; section 23.2). Send a **keepalive every 60 seconds** and reconnect on close.

---

# PART 1 — MOBILE APP (NAK)

Scope: the Expo app, camera, microphone, audio playback, captions, accessibility, and all screens. You call only `app/src/lib/api.ts`, which calls only the endpoints in 0.6.

## 1.1 Screens

| Screen | Purpose | Tier |
|---|---|---|
| `Scan` | Camera preview, capture, result card with item, price, eligibility label, and balance. Captions area | **Must** |
| `Cart` | Items grouped by card with per-card subtotals. "Before tax" is shown and spoken | **Must** |
| `Checkout` | The split read aloud, confirm, then the result and new balances | **Must** |
| `Home` | Large circular button in a half-moon drawer near the bottom. Tapping it says "How may I help you today?" | Should |
| `Settings` | Accessibility panel (1.5) and card list | Should |

The accessibility button (decision 12) is on every screen.

## 1.2 App state machine

Implement it explicitly as a reducer.

```
idle
  → listening            (push-to-talk held, or wake tap)
  → capturing            (shutter pressed)
capturing
  → awaiting_scan        (POST /v1/scan in flight)
awaiting_scan
  → speaking_result      (ScanResponse received)
  → speaking_error       (error envelope received)
speaking_result
  → awaiting_confirm     (voice.expects_response == true)
  → idle                 (expects_response == false)
awaiting_confirm
  → submitting           (user said yes / tapped confirm)
  → idle                 (user said skip, or the prompt expired)
submitting
  → speaking_result      (cart or checkout response)
any
  → interrupted          (user speaks while the agent is speaking)
```

Rules:

- **Barge-in.** If the user speaks while the agent is speaking, stop routine speech at once and listen. If the interrupted message had `priority == "alert"`, replay it in full afterwards. Never drop an alert.
- **Backgrounding.** On return, say "Welcome back, you have N items in your cart" and offer to repeat the last message.
- **Silence.** Prompt once after 5 to 10 seconds. After two unanswered prompts, return to `idle`. Never loop.

## 1.3 Camera

- `expo-camera`, SDK 57. Barcode scanning with `onBarcodeScanned` and `barcodeScannerSettings`, types `ean13`, `upc_a`, `upc_e` (confirmed in section 23.1).
- When a barcode is read, send the digits as the `barcode` field of `/v1/scan`. This turns a fuzzy match into an exact one, so build it.
- Compress to JPEG, longest edge **1280 px**, quality 0.7, before upload. Frame size is the biggest latency cost.
- **Frames are never written to disk.**
- Permission denied: spoken and on-screen instructions to enable it in phone settings, then fall back to the user saying the product name.

## 1.4 Audio

**Microphone.** `expo-audio`, raw PCM capture with `useAudioStream`. Push-to-talk is the default because the venue is loud; continuous listening is a setting.

**Playback.** The backend returns one audio file per sentence. Keep a first-in, first-out queue and play each file as it arrives.

```
sentences arrive → enqueue → play head → on finish, play next
alert priority   → flush queue, play immediately, re-enqueue flushed items after
```

**Audio session.** Call `setAudioModeAsync({ playsInSilentMode: true })` (confirmed in the expo-audio docs; the default is already true, set it anyway).

**Fallback.** If `/v1/tts` fails or Cartesia is down, speak with `expo-speech` on the phone and keep captions on.

**Test on the demo phone:** silent switch, Bluetooth headphones, speaker routing, and an incoming call mid-sentence.

## 1.5 Accessibility (WCAG 2.2 AA)

Settings apply at once across the app and persist between sessions in AsyncStorage on the phone. The backend does not store them.

**Demo-critical (Should tier):**

| Setting | Detail | WCAG criterion |
|---|---|---|
| Captions | On-screen text of everything the agent says, on by default | 1.2.2 (A) |
| Contrast | Standard, high contrast, and dark mode. Minimum **4.5:1** | 1.4.3 (AA) |
| Text size | Up to **200%** without clipping on any screen | 1.4.4 (AA) |
| No color-only information | Labels always carry text or an icon, never color alone | 1.4.1 (A) |
| Speech rate and volume | Adjustable | — |
| Input | Voice or tap for **every** action; push-to-talk | — |
| Screen reader behavior | Detect VoiceOver or TalkBack, mute app speech, send text through announcements (decision 13) | — |
| Targets | At least **24×24 px**; primary controls reachable one-handed at the bottom | 2.5.8 (AA) |

**Stretch:** color-blind palette variants, text spacing (1.4.12), bold and high-legibility fonts, magnified controls, simplified screen, reduced motion (2.2.2), repeat-everything mode.

Also required:

- The accessibility button has a clear spoken label for VoiceOver and TalkBack and opens by voice ("accessibility settings").
- Destructive actions (clear cart) need a voice confirmation or a second tap.
- Test the largest text size against every screen before the demo.

## 1.6 `api.ts` requirements

- One module. No other file in `app/` makes a network request.
- Mirror the 0.5 types exactly as TypeScript interfaces.
- One handler for the 0.6 error envelope: speak `error.speech`, caption it, and retry once if `retryable`.
- The base URL is one constant, so switching between laptop IP, tunnel, and hotspot is a one-line change.

## 1.7 Nak's definition of done

- The app opens in Expo Go on a physical phone by QR code. Camera preview and mic prompts work. Denied permissions reach the fallbacks.
- "What's in my cart" spoken in, spoken answer out. First audio in about 3 seconds or less in most of 10 tries.
- The connection recovers from a 3-minute idle period with no user action.
- Captions match every spoken line.
- The largest text size clips nothing on any screen.

## 1.8 Interface plan

> **Superseded by 1.10 (camera-first redesign, 2026-10-24).** The layout below was the first plan. The colors, type scale, and target sizes in 1.9 still apply.

### Layout principles

1. **Voice first, screen second.** Every screen works with the eyes closed. The screen exists for partial sight, captions, and tap fallbacks.
2. **Same place, every screen.** Low-vision users navigate by position. Three things never move:
   - **Top right:** the accessibility button (decision 12).
   - **Top, below the header:** the caption bar (what the agent last said).
   - **Bottom:** the half-moon dock with the round **Talk** button in the center.
3. **One primary action per screen**, full width, directly above the dock, within thumb reach.
4. **No tabs, no small icons.** Navigation is a stack. Every screen has a large labeled Back button top left, and "go to cart", "checkout" and similar spoken commands navigate too.
5. **Nothing scrolls horizontally, nothing has a fixed height.** Text wraps at 200%; long screens scroll vertically.

### Persistent frame (every screen)

```
┌────────────────────────────────────┐
│ [‹ Back]      Screen title    [⚙ A]│  header: Back 56pt, accessibility button 56pt
├────────────────────────────────────┤
│ 🔊 "I see Advil, ibuprofen 200mg,   │  caption bar: last spoken line, live region
│    $12.99. HSA eligible..."         │
├────────────────────────────────────┤
│                                    │
│          screen content            │
│                                    │
│ [      PRIMARY ACTION (72pt)     ] │
│    ╭──────────────────────────╮    │
│   ╱   [Cart]   ( TALK )  [Scan] ╲  │  half-moon dock, navy; Talk is a 104pt amber circle
└────────────────────────────────────┘
```

**Talk button behavior:** tap = agent asks "How may I help you today?" and listens (push-to-talk window); hold = push-to-talk while held. While the agent speaks, a tap interrupts it (barge-in). State is shown with text under the button ("Tap to talk", "Listening…", "Speaking…", "Looking…"), never by color alone.

**Accessibility button:** short tap repeats the last prompt with a haptic pulse; long press opens Settings. VoiceOver label: "Accessibility. Tap to repeat the last message. Double tap and hold for settings."

### Screens

**Home (`/`)**
```
│ Rewind                         [A] │
│ caption: "How may I help you today?"│
│ ┌───────────────┐┌───────────────┐ │
│ │  📷 Scan item  ││ 🛒 Cart · 2   │ │  two 120pt tiles
│ └───────────────┘└───────────────┘ │
│ HSA card   $340.00                  │  balances, large type
│ Visa credit $5,000.00               │
│ "Simulated payments · mock data"    │  always visible, required by 0.1 #1
│            dock                     │
```

**Scan (`/scan`)**: the camera fills the content area. Tapping anywhere on the preview captures (tap-anywhere for tremor). The barcode reader runs continuously and attaches the digits to the next capture. After a scan, a result card slides over the lower half of the preview:

```
│ ┌────────────────────────────────┐ │
│ │ Advil Ibuprofen 200mg          │ │  name, 28pt bold
│ │ $12.99                         │ │  price, 44pt
│ │ [✓ HSA eligible · high conf.]  │ │  badge: icon + text + color
│ │ Pays with: HSA card ($340.00)  │ │
│ │ [ ✓ Add to cart ] [ ✕ Skip ]   │ │  72pt, tap equivalents of "add that"/"skip it"
│ └────────────────────────────────┘ │
```

A badge is always icon + words: ✓ "HSA eligible", ✕ "Not HSA eligible", ? "Could not confirm eligibility". When `decision == ask_user`, the card shows one large button per card in `card_options`. A `partial` result says "Price not found" in place of a price, never a guessed number. Permission denied shows a full-screen explanation, an "Open settings" button, and a "Say the product name" fallback.

**Cart (`/cart`)**: one block per card group: card nickname and balance, items (name and price, one per row), subtotal. Footer line "Total $23.47 before tax". Primary action: **Checkout**. Secondary: "Remove last item" and "Clear cart" (the second asks again, by voice and a second tap).

**Checkout (`/checkout`)**: the preview split read aloud and shown as the same groups, plus any `issues` (reroute proposals) in a bordered warning block with a ⚠ icon and the amounts written out. Primary action: **Confirm payment**. After success: a large ✓ "Payment complete", new balances, "This was a simulated payment". A low-balance alert renders as a bordered alert block and is announced with priority.

**Settings (`/settings`)**: grouped, each option a full-width row with a 56pt control: Display (Standard / Dark / High contrast; Text size 100–200% in 25% steps with live preview), Captions (on/off), Voice (speech rate slow/normal/fast; volume), Input (push-to-talk vs. continuous), Motion (reduce motion), Cards (read-only list from `/v1/cards`, labeled mock). Changes apply instantly and persist in AsyncStorage.

**Health banner**: if `/v1/health` reports any upstream `down`, a bordered banner under the caption bar names it in words ("Voice service is down. Using phone voice.").

## 1.9 Design system and color (WCAG 2.2 AA)

### Brand direction: "Mint Teal"

Mint for calm (health), deep teal for trust (money). Light mint where the eye rests; one deep teal control to find, the Talk button. The background is a mint-tinted off-white, not pure white, to cut glare under store lights. The brand teal is deliberately **not** the "HSA eligible" green, so brand color never reads as an eligibility claim.

**Icons:** Lucide (`lucide-react-native` + `react-native-svg`, both in Expo Go). No emoji. Icons are decorative; words carry the meaning.

### Tokens (standard theme)

All ratios measured by `app/scripts/contrast-audit.mjs`; full tables for all three themes are in `app/ACCESSIBILITY.md`.

| Token | Hex | Measured |
|---|---|---|
| `bg` (mint mist) | `#F2FAF6` | ink text 15.26:1 |
| `text` (ink teal) / `textMuted` | `#0B2427` / `#3E5A5E` | 16.21 / 7.42 on white |
| `border` | `#5C7A7E` | 4.63 (UI 3:1) |
| `primary` (deep teal), white label | `#0E5A63` | 7.89 |
| `accent` (mint button), ink label | `#5EDDB4` | 9.63 |
| Dock gradient, light mint → mint | `#E4F8EF` → `#8FE3C2` | ink text 14.64 / 10.75 |
| Dock edge line (required: light dock is 1.11:1 on a white scene) | `#0E5A63` | 7.89 vs white |
| Talk button gradient, white icon, white ring | `#137A84` → `#0A434A` | vs dock 4.58 / 7.28; icon 5.07 / 10.97 |
| Caption pill, ink text, ink border | `#E4F8EF` | 14.64 |
| See-through window: two strokes, light outer + teal inner | `#FFFFFF` + `#0E5A63` | 7.89 / 21 vs white / black scenes |
| Info card (solid), ink edge | `#FFFFFF` | text 16.21 |
| HSA eligible | `#0A6B4F` on `#E2F5EC` | 5.73 |
| Not HSA eligible (slate, informational) | `#4F5B66` on `#EEF1F4` | 6.13 |
| Could not confirm | `#4C4F9A` on `#ECECF8` | 6.20 |

### Alert levels

| Level | Use | Colors | Icon + title |
|---|---|---|---|
| Red: danger | Declined payment, errors, card frozen or closed, service down | `#B3261E` on `#FDECEA` (5.72), edge `#B3261E` | Octagon, "Declined" / "Error" / "Service down" |
| Orange: warning / suggestion | Balance too low, reroute (6.4 rule 2), low balance after payment, add another card (6.4, 20.6), price not found, question timed out | `#8A4B00` on `#FFF3E2` (6.21), edge `#C46A00` (3.88) | Triangle, "Warning" / "Suggestion" |

- Red and orange are close in lightness, so the icon and title word always differ.
- Alerts are solid blocks, so they read the same over any camera image.
- Haptics also differ: error buzz for red, warning buzz for orange.

**Dark and high contrast** follow the same roles:
- Dark: dock `#12302B` → `#1E5A4C` with a mint Talk button.
- High contrast: black and white with bright mint `#6BFFC4` and 2px white edges.

### Type scale

System font (San Francisco / Roboto). Sizes are at 100%; the in-app text size setting multiplies them (100–200%), on top of the OS Dynamic Type setting.

| Role | Size / weight | Use |
|---|---|---|
| `display` | 44 / 800 | Price on the result card |
| `title` | 30 / 700 | Screen titles, product name |
| `heading` | 24 / 700 | Group headings |
| `body` | 20 / 400 | Default text (larger than platform default, for older eyes) |
| `label` | 20 / 700 | Button labels |
| `caption` | 22 / 500 | Caption bar |
| `small` | 17 / 500 | Footnotes ("simulated", "before tax"); never smaller |

Line height 1.35×. Never all-caps for meaning; never italic for meaning.

### Size and spacing

| Element | Size | WCAG minimum |
|---|---|---|
| Any tappable control | ≥ 56 × 56 pt | 24 × 24 (2.5.8 AA) |
| Primary action button | 72 pt tall, full width | |
| Talk button | 104 pt circle | |
| Spacing between targets | ≥ 12 pt | |
| Focus indicator | 3 pt ring in `focus` color | 2.4.7 (AA), 2.4.13 (AAA) guidance |

Spacing scale 4 / 8 / 12 / 16 / 24 / 32 / 48. Corner radius 16 for cards, full round for the Talk button.

### Motion

Result card slides in over 200 ms; with Reduce Motion (OS or in-app) it appears instantly. Nothing flashes (2.3.1). The listening indicator is a static ring plus text, not a pulse, when Reduce Motion is on.

### Implementation notes (deviations to agree)

- **Camera frames:** `expo-camera` `takePictureAsync` writes the capture to the app cache, and the resize step writes another. The app deletes both files immediately after upload, so frames are not kept, but strictly they touch disk for under a second. Decision 14 should read "never retained" unless the team wants to research an in-memory path.
- **Contract gaps in 0.6 (need Atharv's agreement, not changed here):**
  1. The shape of a cart item inside `groups[].items` is not defined. The app assumes `{id, scan_id, display_name, amount_cents, eligibility_label}`, taken from the `cart_items` table.
  2. `/v1/command` returns `action` but the values are not listed. The app handles `add_item`, `skip`, `repeat`, `read_cart`, `checkout_preview`, `checkout_confirmed`, `remove_last`, `confirm_clear_cart`, `cart_cleared`, `open_settings`, `unknown`, and treats anything else as "just speak the voice".
  3. Saying "yes" at checkout: 3.8 lists "yes" only for a live `confirm_add` prompt. The app sends "yes" with a live `confirm_checkout` or `confirm_clear_cart` prompt to `/v1/command` too, and expects `checkout_confirmed` / `cart_cleared` back.
  4. Checkout `issues[]` items are not defined. The app assumes `{rule, message}` and shows `message` verbatim.
- **Mock backend:** `lib/api.ts` has a `USE_MOCK` switch that serves the run 1 / run 2 demo script from `lib/mock-backend.ts` so the app can be built and tested before the backend is up. All wording in the mock is copied from 4.4; the real backend's `compose.py` remains the only source of spoken wording in production.

## 1.10 Camera-first redesign (2026-10-24, Nak)

Follows the team's 3-frame wireframe. One camera screen replaces the Home / Scan / Cart / Checkout stack.

| Wireframe | Built as |
|---|---|
| Full-screen camera, all frames | Live `CameraView` behind everything. Tap anywhere, or the dock's Scan, to capture |
| Top-right dark circle | **Profile**: name, linked HSA/FSA and Visa cards (last 4 only), insurance, the current accessibility mode, and all 1.5 settings |
| Half-circle dock, round button | Light-mint-to-mint gradient dock with a teal edge line; deep teal Talk button with a white mic icon and ring. Tap to talk, hold to speak, tap to interrupt. Cart and Scan buttons beside it |
| Frame 2: gray pill | Captions. Grows leftward out of the profile button when Rewind speaks; shows the user's last words too. Tap to repeat with a buzz. Instant with Reduce Motion |
| Frame 3: brown panel | **Transparent window** with a two-tone frame, so the product stays visible (like Google Lens / Live Text). Information sits on a solid card at the window's bottom edge, so text contrast never depends on the camera. The clear area is reserved for the 2D overlay stretch item (business spec §5). Shows onboarding steps, scan result, pill-bottle drug name and strength read-back (`confirm_strength`), cart, checkout split, declined payment, receipt |

**Onboarding (frame 1):**
1. Plain-language reason, then the phone's camera and microphone permission prompts.
2. Demo phone verification with one preset mock number (`DEMO_MODE`, `+1 (415) 555-0100`; 555-01xx numbers reach no one).
3. Insurance card by camera (card-shaped focus corners).
4. **Name clarification.** Rewind never asks for the name. A pop-up pointing at the card shows the member name read from it. Rewind says "Your name is Alex Rivera. Is that right?"
   - **Yes:** saves it and thanks the user by first name.
   - **No:** type the name, or scan again.
   - **No readable name on the card:** the user can type it.
5. Insurance and prescription-benefit read-back.
6. HSA/FSA and Visa cards by camera.

The name and insurance are stored on the phone only.

**Haptics:**
- Talk tap: medium impact.
- Answer finished: success.
- Decline, alert, or error: error.
- Every buzz comes with speech and text, and the user can turn vibration off.

Measured contrast for every new element: `app/ACCESSIBILITY.md`.

### Decisions that need team sign-off

1. **Decision 12 changed.** The persistent top-right button now opens Profile. "Tap to repeat" moved to tapping the caption pill. Long press is no longer used.
2. **Real insurance and payment cards are scanned** to test text extraction. This conflicts with business spec 6.1 ("no real insurance card is scanned") and the mock-only rule in 0.1 #1. Mitigations: only the last 4 digits ever reach the app, images are deleted after upload, and nothing is logged. The image still reaches the backend and its vision model.
3. **Name and phone at onboarding.** Not in the specs. The name comes only from the insurance card and is clarified, never asked for; the phone number is a fixed mock number; both stay on the phone.
4. **Onboarding wording is app-side** (`lib/phrases.ts`). No endpoint or `compose.py` wording exists for it.

### What is extracted from cards (team decision 2026-10-24)

| Card | Extracted | Kept |
|---|---|---|
| Insurance | `insurer_name`, `plan_name`, `member_first_name`, `member_last_name`, `member_id_last4`, and prescription benefits `rx: {bin, pcn, group, copays: [{label, amount_cents}]}` as printed | On the phone, for suggestions. Member ID last 4 only |
| Credit, debit, HSA, FSA | `network`, `card_type` (`hsa`/`fsa`/`general`), `funding` (`credit`/`debit`, if printed), `last4` | Only what adding the payment method needs. Never the full number, expiry, or security code |

All payment cards are **Visa**: HSA and FSA cards are Visa cards from the health plan, and the everyday card is a Visa credit or debit card. The type (`hsa`, `fsa`, or `general` + `credit`/`debit`) is what Rewind tells apart; the UI says "Visa HSA card", "Visa FSA card", "Visa credit", "Visa debit".

Nothing else on either card is read or stored. TypeScript shapes: `InsuranceCard` and `PaymentCardRead` in `app/src/lib/api.ts`.

### Spending order for HSA/FSA-eligible items (team decision 2026-10-24, needs Atharv)

**FSA first, then HSA, then the everyday Visa.** FSA money is the employer's and can be lost when the person leaves that job; HSA money stays with the person.

Changes this makes elsewhere:
- **Business spec 20.6** said: with both HSA and FSA linked, ask which to use. Now Rewind *suggests* the FSA (or the next card in order) and still needs a yes. It never charges silently, and every choice still requires confirmation (3.5).
- **Routing (3.5) STEP 4:**
  - Try the health cards in the order FSA, then HSA.
  - If the first can't cover the item, suggest the next one that can, using `ask_user` + `reroute` (`insufficient_balance`). If neither can, suggest the everyday Visa.
  - If nothing covers it, `blocked`.
- **Group rule 2 at checkout:**
  - For each FSA/HSA group over its balance, keep items (largest first) while they fit.
  - Move the rest to the next card in order that has room (HSA, then Visa).
  - Spoken example: "Your FSA balance is only $15.00, which doesn't cover $18.48. Want me to keep the Advil on your FSA and move the bandages to your Visa credit?"
- **Seed data (3.3), proposed:**

  | Card | id | Run 1 | Run 2 |
  |---|---|---|---|
  | FSA card (Visa) | `card_fsa_1` | $25.00 | $15.00 |
  | HSA card (Visa) | `card_hsa_1` | $340.00 | $5.00 |
  | Visa credit | `card_visa_1` | $5,000.00 | $5,000.00 |

  - **Run 1:** Advil and bandages go to the FSA; kettle corn to the Visa; the FSA ends at **$6.52**.
  - **Run 2:** the FSA can't cover $18.48. Keep the Advil on the FSA; the bandages ($5.49) don't fit the HSA ($5.00), so they move to the Visa. "No, keep my cards" shows the decline.
- **Demo script (4.4) lines change.** "Your HSA balance is $340" becomes "Your FSA balance is $25", and the run 1 result line becomes "Payment complete. Your FSA balance is now $6.52." The 3.12 test numbers ($321.52) need the same update.

Implemented in the app's mock backend (`app/src/lib/mock-backend.ts`); the real backend is unchanged until Atharv agrees.

### Proposed contract additions (Atharv and Tiea)

| Proposed | Shape | Owner |
|---|---|---|
| `POST /v1/onboarding/card-scan` | multipart `image`, `kind` (`insurance` or `payment`) → `{state: read\|unclear, framing_hint, insurance: InsuranceCard \| null, payment: PaymentCardRead \| null}` (shapes below). Never return or log a full card or member number | Tiea (vision prompt), Atharv (endpoint) |
| `item_bbox` on `ScanResult` (and `VisionExtract`) | `{x, y, w, h}` as fractions of the photo: where the item is, so the focus corners and pop-up sit on it | Tiea (vision prompt), Atharv (pass-through) |
| `POST /v1/cards` | `{type, nickname, last4, network}` → `Card` | Atharv |
| `Card.last4`, `Card.network` | optional fields on `/v1/cards` | Atharv |
| `use_proposed_split` on `/v1/checkout/confirm` | `false` charges the original cards. A group over its card's balance fails all-or-nothing with `E_CARD_DECLINED` and charges nothing | Atharv |
| `E_CARD_DECLINED` | new error code; `speech` says which card, its balance, the total, and that nothing was charged | Atharv |
| `/v1/command` "no" with a live `confirm_checkout` reroute | means "keep my cards": confirm with `use_proposed_split: false` | Atharv |

---

# PART 2 — VISION, LOOKUP, ELIGIBILITY (TIEA)

Scope: turning a camera frame into a `ScanResult`. You expose three functions. Atharv's `/v1/scan` calls them in order, in-process. You never touch HTTP, database writes outside the helpers, or routing.

## 2.1 The three functions you own

```python
# backend/vision/claude_vision.py
def extract_product(image_bytes: bytes, barcode_hint: str | None = None) -> VisionExtract

# backend/lookup/chain.py
def resolve_product(extract: VisionExtract) -> ProductResolution

# backend/eligibility/classify.py
def classify_eligibility(product: ProductResolution,
                         package_marking: str | None) -> EligibilityResult
```

These signatures are frozen. Atharv writes against them from hour 0, so **commit stubs first** that return hardcoded Advil data.

## 2.2 Helpers Atharv gives you

Call these. Do not open a Supabase client yourself.

```python
from data.db import (
    cache_get,                      # (product_key: str) -> dict | None
    cache_put,                      # (product_key: str, row: dict) -> None
    eligibility_lookup_upc,         # (upc: str) -> dict | None   exact match in eligibility_items
    eligibility_bulk_insert,        # (rows: list[dict]) -> int   used by the offline prefetch
)
```

## 2.3 Claude vision

Claude with a structured-output request. A Gemini fallback is stretch: build it last, behind one flag, only if credits become a problem.

**Prompt contract.** The model returns exactly this JSON and nothing else:

```json
{
  "name": "string | null",
  "brand": "string | null",
  "size": "string | null",
  "upc_digits": "string | null",
  "shelf_price_cents": "integer | null",
  "category": "one of the controlled values",
  "is_medication": true,
  "is_prescription_only": "boolean | null",
  "package_eligibility_marking": "eligible | none_seen",
  "multiple_products_in_frame": false,
  "price_tag_visible": true,
  "tag_may_belong_to_neighbour": false,
  "field_confidence": {"name": 0.0, "price": 0.0, "size": 0.0},
  "unreadable_reason": "dark | blurry | glare | occluded | foreign_language | null"
}
```

Prompt rules, each mapped to a row in business spec section 20.1:

- **Never infer a price that is not legible.** If no tag is readable, `shelf_price_cents` is null and `price_tag_visible` is false. A made-up price spoken to a blind shopper is the worst failure this system can produce.
- Report `multiple_products_in_frame` instead of picking one.
- Set `tag_may_belong_to_neighbour` when tag alignment is unclear. If testing shows the model cannot do this reliably, keep the field always false and say so.
- Read size and strength. For medication, strength is required; without it the item cannot be matched.
- `package_eligibility_marking` is `eligible` only when an FSA/HSA marking is printed on the package or tag. Absence is `none_seen`, never "not eligible."
- **Medical advice guard.** The system prompt says the assistant never gives dosage, interaction, or safety advice and always refers to the pharmacist. Test it with "is it safe to take this with alcohol" before the demo.

**Prescription labels.** Read drug name and strength from the pill-bottle label; the agent reads both back for confirmation, and nothing proceeds until confirmed. The demo uses a **prop label only**.

**Price sanity check.** Treat any `shelf_price_cents` outside 1 to 50000 as no price. A misread decimal point is the most likely shelf-tag error.

## 2.4 Product key and normalization

```
if upc present:        product_key = "upc:" + digits
else:                  product_key = "n:" + sha1(lower(brand|name|size) with
                                              punctuation and extra whitespace removed)[:16]
```

Write one function, `normalize_key()`, and use it in both the prefetch and the runtime, or the cache will never hit.

## 2.5 Controlled category values

Both the vision prompt and the IRS rule table use these exact strings.

```
otc_medicine        first_aid           menstrual_care      pain_relief
cold_flu_allergy    digestive_health    eye_care            foot_care
diagnostic_device   sunscreen           vitamins_supplements
personal_care       cosmetics           grocery             household
baby_care           other
```

## 2.6 Lookup chain

Per business spec section 19.2, simplified by decision 7 (no retailer API in v1):

1. Build `product_key` from the extract.
2. `cache_get(product_key)`. On a hit, reuse identity and eligibility. Reuse the cached **price** only if the row is under 24 hours old; otherwise take the price from the current shelf tag.
3. On a miss, the shelf tag is the product. No network lookup in v1.
4. If no price from either source, the state is `partial`: speak what is known and ask the user to point at the tag or say the price. A spoken price is stored with `price_source = "user_spoken"`.
5. `cache_put` the result with its source label.

**The shelf price always wins.** Never invent a price, and never block the first spoken answer on a lookup.

| State | Meaning | Agent behavior |
|---|---|---|
| `resolved` | Name, price, and eligibility known | Normal flow |
| `partial` | Name known, price or eligibility missing | Speak what is known, ask for the rest |
| `unresolved` | Product not identified | "I could not confirm this item. Try another angle, or tell me what it is" |

## 2.7 Eligibility classifier

Order matters.

```
(Revised 2026-10-24, Tiea. No barcodes; Claude Vision names the product and its category.)

1. IRS category rule on Vision's category (2.8):
       eligible / not_eligible / needs_review
       a medication outside an IRS-backed "eligible" category -> "could_not_confirm"
       needs_review -> "could_not_confirm"
       basis = "irs_category_rule"; confidence = None

2. Moss query on "brand name category" (lookup/moss_index.py). Size, strength and pack count are
   left out on purpose: they do not change whether an OTC medicine is eligible.
       accept the closest listing if score >= 0.75,
              OR score >= 0.40 and the listing's brand appears in the product's brand/name
       Moss answered, no accepted listing  -> index_checked = True, no match
       Moss unavailable or timed out       -> index_checked = False (step 1 decides alone)

3. Combine ("eligible" needs two sources):
       rule eligible + listing eligible            -> eligible, basis "semantic_match", confidence = score
       rule eligible + no listing (index answered) -> could_not_confirm, basis "no_match"
       rule eligible + listing not eligible        -> could_not_confirm, basis "package_disagreement"
       rule not_eligible                           -> not_eligible (already routes to the Visa)
       a listing never upgrades could_not_confirm; only the IRS rules can say eligible

4. Price fallback: if the shelf tag price is missing and a listing was accepted, use the listing's
   price (price_source "seeded") and speak it as "listed online at $X". A shelf tag always wins.

5. Cross-check against the package marking:
       if package_marking == "eligible" and label == "not_eligible":
           label = "could_not_confirm"; basis = "package_disagreement"
       (marking "none_seen" never overrides an index result)
```

**Medication rule (decision 3, revised 2026-10-24).** Barcodes are removed. A medication is `eligible` only when Claude Vision's category is IRS-backed `eligible` (pain_relief, cold_flu_allergy, digestive_health, menstrual_care, otc_medicine); any other category returns `could_not_confirm`. Products are keyed by `normalize_key(brand, name, size)`.

**THRESHOLD** is 0.75, with a 0.40 floor when the brand agrees. Live check on 2026-10-24 (`scripts/check_moss.py`, 26 rows): correct products scored 0.50 to 1.00 (brand-only "Allegra" 0.50, "Tums" 0.61), a wrong-brand near match scored 0.67 and was rejected, unrelated items scored 0.22 to 0.40. Re-tune on the real demo shelf.

**The index must hold both eligible and non-eligible rows.** An index of eligible items only returns a near match for everything, including kettle corn (section 24.6). Build the negative examples in from the start.

## 2.8 IRS category rule table

This is also the complete fallback if the scrape is a no-go, so it must stand alone. Rows marked "eligible" are backed by primary sources in business spec section 23.1. Everything not backed is `needs_review`.

| Category | Rule | Basis |
|---|---|---|
| `otc_medicine` | eligible | CARES Act, IRS newsroom |
| `pain_relief` | eligible | CARES Act |
| `cold_flu_allergy` | eligible | CARES Act |
| `digestive_health` | eligible | CARES Act |
| `menstrual_care` | eligible | CARES Act, IRS newsroom |
| `first_aid` | eligible | IRS Pub 502, "medical supplies such as bandages" |
| `diagnostic_device` | needs_review | not yet checked against a primary source |
| `eye_care` | needs_review | not yet checked against a primary source |
| `foot_care` | needs_review | medicated versus cosmetic differs |
| `sunscreen` | needs_review | not verified in this project's sources |
| `vitamins_supplements` | needs_review | generally needs a medical reason |
| `baby_care` | needs_review | |
| `other` | needs_review | |
| `personal_care` | not_eligible | unless medicated |
| `cosmetics` | not_eligible | |
| `grocery` | not_eligible | resolves kettle corn |
| `household` | not_eligible | |

`needs_review` always becomes `could_not_confirm` in speech. Never a guess. Move a row to `eligible` only after citing a primary source in business spec section 23.

## 2.9 Offline eligibility prefetch (Should tier)

**Runs before the demo, never during a scan.** Lives in `backend/prefetch/`, which the API never imports.

**Go/no-go test first** (section 24.2, about 30 minutes):

1. Check the target site's current terms and robots.txt (section 24.4). If collection is not allowed, stop and use the fallback.
2. Run one actor against listings that include the three demo items.
3. Check the output for UPC or GTIN, name, brand, size, category, and an eligibility field.
4. **Go:** eligibility appears for Advil and bandages, a non-eligible item is identifiable, and a stable ID is present.
5. **No-go:** stop. Use the IRS table plus hand-entered rows for the demo shelf. If the test has not passed by about hour 12, switch to the fallback (section 24.9).

Rules: keep volume small, no logins, no personal data, record the source URL and collection date on every row. Do not republish the dataset, do not call it complete, and do not describe it to judges as an integration with a retailer.

Pipeline: run actor → export JSON → normalize to `eligibility_items` → **add non-eligible examples from the same categories** → `eligibility_bulk_insert()` → build the Moss index.

Moss index (`create_index`): `id` is the UPC or the normalized key, `text` is "brand name size category," `metadata` holds `{eligible, category, upc, source_url, collected_at}`. Updating an index is not documented in the quickstart, so **rebuild rather than update** after any data change.

**Pitch wording, verbatim:** "Checked against eligibility data listed by retailers and IRS categories." Never "certified," "official," "verified," or "complete." The SIGIS list is members-only and its license bars this use; do not use or imitate it.

## 2.10 Tiea's definition of done

- Stubs committed in hour 1.
- 10 photos of the demo shelf return valid `VisionExtract` objects. An unclear photo returns low confidence and `E_VISION_UNCLEAR`, never a guessed price.
- The three demo items get the right labels. Kettle corn returns `not_eligible` or `could_not_confirm`, **never** `eligible`.
- An eligible rule with no store listing, a listing that disagrees, and a package disagreement each return `could_not_confirm`. Strength and pack size are not compared.
- On 20 to 30 extra test items, **no non-eligible item is labeled eligible.** Record how many return `could_not_confirm`; that number goes in the pitch.
- The medical-advice refusal fires reliably.

---

# PART 3 — BACKEND, SUPABASE, ROUTING, CHECKOUT (ATHARV)

Scope: FastAPI, Supabase, the cart, routing, reroute, simulated checkout, Nessie, the product cache, the voice relay, spoken wording, and `reset_demo()`. You own the only process that holds API keys.

## 3.1 Database schema (Supabase / Postgres)

Integer cents everywhere (`bigint`). IDs are application-generated text (uuid4 or fixed seed IDs).

```sql
CREATE TABLE cards (
  id                TEXT PRIMARY KEY,         -- 'card_hsa_1', 'card_visa_1'
  type              TEXT NOT NULL CHECK (type IN ('hsa','fsa','general')),
  nickname          TEXT NOT NULL,            -- 'HSA card', 'Visa credit'
  balance_cents     BIGINT NOT NULL,
  nessie_account_id TEXT,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','frozen','closed','expired')),
  is_default        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE product_cache (
  product_key            TEXT PRIMARY KEY,
  upc                    TEXT,
  normalized_name        TEXT NOT NULL,
  brand                  TEXT,
  size                   TEXT,
  category               TEXT NOT NULL,
  shelf_price_cents      BIGINT,
  eligibility_label      TEXT CHECK (eligibility_label IN
                           ('eligible','not_eligible','could_not_confirm')),
  eligibility_confidence REAL,
  eligibility_basis      TEXT,
  source                 TEXT NOT NULL,
  last_updated           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cache_upc ON product_cache(upc);

CREATE TABLE eligibility_items (            -- Tiea populates; Atharv owns the table
  product_key   TEXT PRIMARY KEY,
  upc           TEXT,
  name          TEXT NOT NULL,
  brand         TEXT,
  size          TEXT,
  category_path TEXT,
  eligible      BOOLEAN NOT NULL,           -- both values must be present in the data
  source_url    TEXT NOT NULL,
  collected_at  TIMESTAMPTZ NOT NULL,
  basis         TEXT NOT NULL CHECK (basis IN ('retailer_badge','irs_category_rule','hand_entered'))
);
CREATE INDEX idx_elig_upc ON eligibility_items(upc);

CREATE TABLE scans (
  scan_id          TEXT PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  state            TEXT NOT NULL,
  product_json     JSONB NOT NULL,
  eligibility_json JSONB NOT NULL
);

CREATE TABLE cart_items (
  id                 TEXT PRIMARY KEY,
  seq                BIGINT GENERATED ALWAYS AS IDENTITY,   -- 'remove last item' uses MAX(seq)
  scan_id            TEXT NOT NULL REFERENCES scans(scan_id),
  product_key        TEXT NOT NULL,
  display_name       TEXT NOT NULL,
  amount_cents       BIGINT NOT NULL,
  amount_basis       TEXT NOT NULL CHECK (amount_basis IN ('shelf_price','remaining_after_copay')),
  assigned_card_id   TEXT NOT NULL REFERENCES cards(id),
  eligibility_label  TEXT NOT NULL,
  user_overrode_card BOOLEAN NOT NULL DEFAULT FALSE,        -- for 'possible reimbursement'
  added_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE insurers (
  id               TEXT PRIMARY KEY,
  display_name     TEXT NOT NULL,          -- must be visibly marked mock in the UI
  has_rx_benefit   BOOLEAN NOT NULL,
  copay_rules_json JSONB NOT NULL          -- {"drug_key": {"copay_cents": 1000}}
);

CREATE TABLE prompts (
  prompt_id    TEXT PRIMARY KEY,
  scope        TEXT NOT NULL,
  scan_id      TEXT,
  payload_json JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  consumed     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE payments (
  payment_id      TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  total_cents     BIGINT NOT NULL,
  splits_json     JSONB NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('simulated_complete','failed'))
);
```

`data/db.py` wraps **all** access. No Supabase calls anywhere else: not in the API layer, not in Tiea's modules, not in the prefetch.

```python
# data/db.py — the public surface
def health() -> dict                       # {reachable, latency_ms}
def get_cards() -> list[dict]
def cache_get(product_key: str) -> dict | None
def cache_put(product_key: str, row: dict) -> None
def eligibility_lookup_upc(upc: str) -> dict | None
def eligibility_bulk_insert(rows: list[dict]) -> int
def save_scan(scan_id: str, product: dict, eligibility: dict) -> None
def get_cart() -> dict
def add_cart_item(...) -> dict
def remove_last_cart_item() -> dict
def clear_cart() -> None
def create_prompt(...) -> str
def consume_prompt(prompt_id: str, expected_scope: str) -> dict
def confirm_checkout(idempotency_key: str, splits: list[dict]) -> dict   # calls the RPC in 3.6
def reset_demo(run: int = 1) -> dict                                       # calls the RPC in 3.4
```

## 3.2 Supabase operation (no fallback database)

- **Service key on the backend only.** The app never holds a Supabase key and never talks to Supabase.
- **Row-level security:** disable it on these tables, or add a permissive policy, for the demo. A blocked insert at judging time looks identical to a bug.
- **Atomic work goes through Postgres functions.** The REST client sends one request per call, so a multi-step checkout or reset is not atomic from Python. Put checkout and reset in `functions.sql` as SQL functions and call them with `supabase.rpc(...)` (check the supabase-py RPC docs before building; unverified here).
- **In-memory cart mirror.** The backend keeps the current cart in memory for the session. Reads come from the mirror; writes go to Supabase first and update the mirror only on success. A short Supabase slowdown therefore does not stall "what's in my cart." Cards and balances are always re-read at checkout.
- **Budgets.** Every Supabase call has the 1500 ms budget in 0.7, one retry, then `E_DB_UNAVAILABLE`.
- **Health.** `/v1/health` reports Supabase as `ok`, `degraded` (over 1000 ms), or `down`.
- **What a Supabase outage means.** There is no local fallback. Scanning also needs Claude, Cartesia, and Moss, so the internet is already a single point of failure. The plan is: hotspot, then the recorded backup video (4.6).
- **Free-tier projects may pause when idle** (unverified). Open the dashboard the morning of judging and run `reset_demo()` to confirm the project is awake.

## 3.3 Seed data

Exactly these values. The tests and the demo script depend on them.

```python
CARDS = [
  {"id":"card_hsa_1",  "type":"hsa",     "nickname":"HSA card",
   "balance_cents":34000, "status":"active", "is_default":True},
  {"id":"card_visa_1", "type":"general", "nickname":"Visa credit",
   "balance_cents":500000, "status":"active", "is_default":False},
]

DEMO_PRODUCTS = [   # pre-cached so the demo cannot fail on a lookup (section 19.3)
  {"product_key":"upc:REPLACE_ADVIL","name":"Advil Ibuprofen 200mg",
   "brand":"Advil","size":"200mg","category":"pain_relief",
   "shelf_price_cents":1299,"eligibility_label":"eligible",
   "eligibility_basis":"upc_match","source":"seeded"},
  {"product_key":"upc:REPLACE_BANDAGES","name":"Bandages",
   "brand":None,"size":None,"category":"first_aid",
   "shelf_price_cents":549,"eligibility_label":"eligible",
   "eligibility_basis":"upc_match","source":"seeded"},
  {"product_key":"upc:REPLACE_KETTLE_CORN","name":"Kettle Corn",
   "brand":None,"size":None,"category":"grocery",
   "shelf_price_cents":499,"eligibility_label":"not_eligible",
   "eligibility_basis":"irs_category_rule","source":"seeded"},
]

INSURERS = [
  {"id":"mock_plan_a","display_name":"Mock Plan A (synthetic)",
   "has_rx_benefit":True,"copay_rules_json":{"omeprazole_20mg":{"copay_cents":1000}}},
  {"id":"mock_plan_b","display_name":"Mock Plan B (synthetic)",
   "has_rx_benefit":False,"copay_rules_json":{}},
]
```

Replace the `REPLACE_*` placeholders with the real UPCs from the demo packages, and the bandage price with the real shelf price. Seed matching `eligibility_items` rows for the three demo items with `basis = 'hand_entered'` and their public source pages.

## 3.4 `reset_demo()`

One Postgres function, called by RPC, so it is atomic:

```
reset_demo(run int):
  1. DELETE FROM cart_items, scans, prompts, payments
  2. Reset cards to seed values, except:
        run == 1  → card_hsa_1.balance_cents = 34000
        run == 2  → card_hsa_1.balance_cents = 1500
  3. Upsert DEMO_PRODUCTS into product_cache
  4. Upsert INSURERS
  5. Return cards and an empty cart
```

Build it in **hour 1**, before routing. After it runs, clear the in-memory cart mirror. A test asserts that two calls produce identical output.

## 3.5 Routing algorithm

> **Claim tip at checkout (added 2026-10-24, Tiea).** If an *eligible* item was paid
> on a general card (Visa), the checkout confirmation adds: "You paid $X for {items}
> with your Visa credit, and it's HSA eligible. You can file a claim with your
> {HSA|FSA} provider to pay yourself back, for example through Optum Financial or
> HealthEquity. Keep your receipt." The agent points the way only; it never files.
> Not said for not-eligible or could-not-confirm items.

`payments/routing.py`. Pure function: no I/O, no network.

```python
def route_item(
    eligibility_label: str,          # eligible | not_eligible | could_not_confirm
    amount_cents: int,
    amount_basis: str,               # shelf_price | remaining_after_copay
    cards: list[Card],
    copay_confirmed: bool = False,   # stays False until decision 4 is resolved
) -> PaymentRecommendation
```

```
STEP 0 — amount
  Non-medication, or medication with no plan copay:
      amount = shelf_price_cents,  basis = "shelf_price"
  Medication covered with a copay:
      amount = remaining out-of-pocket only,  basis = "remaining_after_copay"
      The insurer's share is NEVER routed to HSA/FSA (section 23.2)
      GATE: copay_confirmed is False, so:
            decision = "ask_user", reason_code = "copay_unconfirmed"  → return
  Covered with a ZERO copay:
      decision = "blocked", reason_code = "zero_copay_nothing_due"   → return

STEP 1 — no cards at all
  decision = "blocked", reason_code = "no_card_linked"

STEP 2 — could_not_confirm
  NEVER auto-route to HSA/FSA.
  decision = "ask_user", reason_code = "eligibility_unconfirmed",
  card_options = every active card

STEP 3 — not_eligible
  decision = "route_to_general", card_id = default general card,
  reason_code = "not_eligible"
  If the user asks for the HSA anyway: refuse, and say only that eligibility
  could not be confirmed for that card. Do not discuss tax consequences (unresearched).

STEP 4 — eligible
  health_cards = active cards with type in ('hsa','fsa')
  if none:                         route_to_general, reason "no_health_card_linked"
  FSA FIRST (revised 2026-10-24, Tiea): order health_cards FSA before HSA, because
      FSA money expires at the end of the plan year and HSA money never does.
      Scope: shelf (OTC) medicines; nothing that needs a doctor's letter.
  card = the first card in that order whose balance covers the amount
  if card exists (equality is sufficient):
      decision = "route_to_hsa", reason "fsa_first" if card is an FSA
                 else "eligible_sufficient_balance"
      An FSA pick is spoken with: "Your FSA money expires at the end of the
      plan year, so I'll use it first."
      The user can still name the other card ("put it on my HSA").
  else (including balance <= 0):
      if a general card covers it:
          decision = "ask_user", reason "eligible_insufficient_balance",
          reroute  = {from: card.id, to: default_general.id, reason: "insufficient_balance"}
      else:
          → STEP 5

STEP 5 — nothing covers it
  decision = "blocked", reason_code = "no_card_covers"
```

`requires_confirmation` is **always true**.

### Reason codes

| Code | Decision | Spoken shape |
|---|---|---|
| `eligible_sufficient_balance` | `route_to_hsa` | item, price, "HSA eligible," balance, ask |
| `eligible_insufficient_balance` | `ask_user` | warn, propose the Visa, ask |
| `not_eligible` | `route_to_general` | item, price, "Not HSA eligible," which card |
| `eligibility_unconfirmed` | `ask_user` | "I could not confirm eligibility," ask which card |
| `copay_unconfirmed` | `ask_user` | "I could not confirm that your HSA or FSA can pay the remaining charge. Which card would you like to use?" |
| `zero_copay_nothing_due` | `blocked` | plan shows no copay; confirm at the pharmacy counter |
| `no_health_card_linked` | `route_to_general` | once: "Add your HSA card in settings" |
| `multiple_health_cards` | `ask_user` | ask which; never choose silently |
| `no_card_linked` | `blocked` | prompt to link; checkout blocked |
| `no_card_covers` | `blocked` | "Please use a credit card for this item" |

### Group rules at checkout (section 6.4)

| Rule | Trigger | Behavior |
|---|---|---|
| 1. Item too large | One item exceeds a card's balance | Suggest another card for that item |
| 2. Group too large | A card's total exceeds its balance | Propose moving items; **say the amounts aloud**; ask before moving anything |
| 3. Nothing covers it | No card has enough | "Please use a credit card for this item" |

Rule 2 is the declined-card moment. For run 2, with HSA at $15.00 and a group of $18.48, keep the Advil ($12.99) on the HSA and move the bandages ($5.49) to the Visa. Algorithm: keep items in descending amount order while they fit the balance, move the rest; speak the split and require confirmation.

## 3.6 Checkout

**Preview** (`POST /v1/checkout/preview`):

1. Refetch balances from Nessie (fallback: last known, then seeded in demo mode).
2. Rerun routing for every cart item against the fresh balances.
3. If any assignment changed, report it and require re-confirmation.
4. Apply group rules 1 to 3.
5. Return the split per card, totals, and issues. Totals are **before tax**, and the agent says so.

**Confirm** (`POST /v1/checkout/confirm`):

- Requires an `idempotency_key` from the app and a live `prompt_id`.
- One Postgres function, called by RPC: insert into `payments` with the unique key; if the key already exists, return the **existing** payment unchanged; otherwise decrement every card group, write `splits_json`, set `simulated_complete`. All or nothing, in one transaction.
- Return and speak the new balances.
- If any balance crosses the low-balance threshold, emit a `priority: "alert"` `VoiceRequest`.

Empty cart: "Your cart is empty." No card linked: checkout blocked. Refunds, returns, and non-USD are out of scope.

## 3.7 Prompt lifecycle

```python
def create_prompt(scope: str, scan_id: str | None, payload: dict) -> str   # returns prompt_id
def consume_prompt(prompt_id: str, expected_scope: str) -> dict            # raises E_PROMPT_EXPIRED
```

- TTL **15 seconds**. Single use. Scope must match: a `confirm_add` prompt cannot authorize a checkout.

## 3.8 Command interpretation

`POST /v1/command`. A deterministic keyword matcher, not an LLM call.

| Transcript matches | Action |
|---|---|
| "add that," "add it," "yes" (with a live `confirm_add` prompt) | Add the scanned item to the cart |
| "skip it," "no" | Discard the scan, return to idle |
| "read it again," "repeat that" | Re-speak the last `VoiceRequest` verbatim |
| "what's in my cart" | Speak the cart grouped by card, with the before-tax total |
| "checkout" | Run preview and speak the split |
| "remove last item" | Remove the most recent cart item |
| "clear cart" | Create a `confirm_clear_cart` prompt and ask |
| "accessibility settings" | Tell the app to open the panel |
| anything else | `E_STT_LOW_CONFIDENCE` wording |

Reject a transcript below the STT confidence threshold. **Read back every command that spends or removes something** before running it.

## 3.9 Voice relay

`api/voice.py`. The backend holds the Cartesia key; the app only sends audio and text.

- `/v1/stt`: forward the audio to Cartesia Ink, return transcript and confidence.
- `/v1/tts`: split the text into sentences (the same split as `VoiceRequest.sentences`), request each from Cartesia Sonic, save each to `audio_tmp/`, and return URLs as they are ready.
- Keep one Cartesia connection warm with a keepalive every 60 seconds; reconnect on close.
- If Sonic fails, return an error envelope with `retryable: false`; the app speaks with `expo-speech`.

## 3.10 Nessie integration

`payments/nessie.py`. Treat it as untrusted and slow.

- Base URL `http://api.nessieisreal.com`, key as a `?key=` query parameter. **This comes from a student project's docs; the official docs returned 403** (section 23.3). Confirm at the Capital One booth in the first hour.
- Model the HSA as a Checking or Savings account with an HSA nickname.
- 2-second budget. On failure: last known balances and `E_NESSIE_UNAVAILABLE`. In demo mode, seeded balances.
- One adapter file, so a different API shape changes one file. **Do not block the build on Nessie.**

## 3.11 `/v1/scan` orchestration and spoken wording

```python
async def scan(image: UploadFile, barcode: str | None = None, hint_price_cents: int | None = None):
    img = await image.read()                                    # never written to disk
    extract  = vision.extract_product(img, barcode)             # Tiea
    product  = lookup.resolve_product(extract)                  # Tiea
    elig     = eligibility.classify_eligibility(product,
                   extract.package_eligibility_marking)         # Tiea
    db.save_scan(scan_id, product, elig)
    cards    = nessie.get_balances_or_last_known()
    rec      = routing.route_item(elig.label, product.amount_cents, basis, cards)
    prompt   = db.create_prompt(scope_for(rec), scan_id, {...})
    voice    = compose.compose_speech(product, elig, rec, prompt)
    return ScanResponse(scan=..., recommendation=rec, voice=voice)
```

`speech/compose.py` is the only place spoken wording is built. Template functions only, no LLM, so demo lines are deterministic.

**Confidence wording rule** (business spec section 6.2):

| Situation | Spoken |
|---|---|
| Medication in an IRS-backed category | No confidence phrase: "HSA eligible." |
| Non-medication, `upc_match` or `irs_category_rule` | "high confidence" |
| Non-medication, `semantic_match` | "high confidence" if score ≥ the high mark set in testing, else "moderate confidence" |
| `could_not_confirm` | "I could not confirm eligibility" |

## 3.12 Atharv's definition of done

- `pytest` covers group rules 1 to 3 with the demo numbers: $340.00, $15.00, $12.99, $5.49, $4.99.
- Run 1 ends at **$321.52**. Run 2 produces the documented reroute.
- `reset_demo()` runs twice with identical output.
- After reset: two cards, two insurer profiles, three cached demo products, and three demo `eligibility_items` rows exist in Supabase.
- A repeated `idempotency_key` returns the original payment and does not charge twice.
- An expired or wrong-scope `prompt_id` is rejected.
- Every money value is an integer. Search the codebase for `float`, `Decimal`, and `/ 100` before calling this done.
- `/v1/health` reports Supabase status correctly.

---

# PART 4 — INTEGRATION, TESTS, BUILD ORDER

## 4.1 Who calls whom

```
  Nak's app  ──HTTP──▶  Atharv's FastAPI  ──in-process──▶  Tiea's modules
                              │
                              ├──▶ Cartesia Ink / Sonic
                              ├──▶ Nessie
                              └──▶ Supabase

  Tiea's modules  ──▶ Claude, Moss, and Atharv's db helpers
  Tiea's prefetch ──▶ Apify   (offline only; the API never imports it)
```

**The phone never calls Claude, Cartesia, Moss, Nessie, or Supabase directly.** Cartesia's own guidance is that API keys are for trusted servers (section 23.1).

## 4.2 Hour 0, in parallel

| Owner | First commit |
|---|---|
| Atharv | `models/schemas.py` with every 0.5 model, `/v1/health` with stub data, the Supabase project with `schema.sql`, and `reset_demo()` |
| Tiea | The three functions in 2.1 as **stubs returning hardcoded Advil data** |
| Nak | `api.ts` with the 0.5 types and a call to `/v1/health` |

Within the first hour, all three run the full round trip with fake data. Then each replaces the inside of their own box.

## 4.3 Build gates

| Gate | Milestone | Owner | Hour (estimate) |
|---|---|---|---|
| 0 | Schemas, stubs, `api.ts`, Supabase schema, `reset_demo()` | all | 1 |
| 1 | Voice loop: Ink → Claude → Sonic, **latency measured** | Nak + Atharv | ~8 |
| 2 | Vision returns structured JSON from one still photo | Tiea | ~10 |
| 3 | Eligibility label from IRS rules and seeded rows | Tiea | ~12 |
| 4 | Cart and routing: groups, balances, reroute | Atharv | ~16 |
| 5 | Simulated checkout and alerts; run 1 and run 2 end to end on a phone | Atharv + Nak | ~20 |
| 6 | Polish: demo-critical accessibility, captions, framing guidance, rehearsal | everyone | ~24 |
| 7 | Should and Stretch items (Apify index, full settings panel), only if 1 to 6 are reliable | everyone | remaining |

**Gate 1 is the real gate.** If frame-to-first-audio is far above 3 seconds, shrink frames, use a faster vision model, or cut a step. Measure it.

The Apify go/no-go test (2.9) can run in parallel with Gate 2 because it is offline, but it never delays Gates 1 to 5.

## 4.4 Demo script — exact spoken lines

These are the **facts** each line must contain. The exact sentence may be phrased naturally by Claude, but every listed figure and label must appear verbatim and no other number may (see `backend/agents/speaker.py`).

**Privacy rule (team decision, 2026-10-24): card balances are never spoken.** Saying a balance aloud in a store exposes it to anyone nearby. The agent only says whether a card *can cover* an item, says "please use another card" when it can't, and plays a beep with "Your HSA card is running low. You might want to add funds." when an HSA/FSA card drops below the low-balance level. Asked directly for a balance, it declines and points to the app. Balances are still tracked to the cent internally.

**Run 1, HSA at $340.00:**

| Step | Must contain |
|---|---|
| Advil | "Advil Ibuprofen 200mg", "$12.99", "HSA eligible", "HSA card" (question: use it?) → yes |
| Bandages | Same shape, $5.49 |
| Kettle corn | "Kettle Corn", "$4.99", "Not HSA eligible", "Visa credit" |
| Checkout | "$18.48" on "HSA card", "$4.99" on "Visa credit", "before tax", "Ready to check out?" → yes |
| Result | "simulated", "$18.48" on "HSA card", "$4.99" on "Visa credit". **No balance.** |

**Run 2, HSA at $15.00:**

> Must contain "HSA card", "can't cover", "$18.48", "Advil Ibuprofen 200mg", "Bandages", "Visa credit" → yes. **Must not contain "$15.00".**

Arithmetic check (internal, not spoken): 1299 + 549 = 1848. 34000 − 1848 = 32152. Any other stored balance means routing or money handling is wrong.

## 4.5 Test matrix

`pytest`, in `backend/tests/`. Pure logic (routing, speech, classifier rules) needs no database. Data tests run against `tests/fakes/fake_db.py`, an in-memory test double of the `db.py` interface; a small set of smoke tests runs against a separate Supabase test project.

**Routing (Atharv):**

| Case | Expect |
|---|---|
| eligible, balance 34000, amount 1299 | `route_to_hsa`, after 32701 |
| eligible, balance exactly 1299 | `route_to_hsa` |
| eligible, balance 1500, amount 1848 | `ask_user` + reroute to Visa |
| eligible, balance 0 | insufficient |
| not_eligible | `route_to_general`, never HSA |
| could_not_confirm | `ask_user`, never HSA |
| medication with copay, `copay_confirmed=False` | `ask_user`, `copay_unconfirmed` |
| zero copay | `blocked`, nothing added |
| no cards | `blocked`, `no_card_linked` |
| two health cards, no default | `ask_user` |
| group $18.48 against balance $15.00 | rule 2 proposal, amounts spoken |

**Checkout and data (Atharv):** run 1 totals; a repeated idempotency key returns the original; `reset_demo()` twice is identical; a balance change between scan and checkout triggers re-confirmation; a Supabase timeout returns `E_DB_UNAVAILABLE` and the cart mirror still answers "what's in my cart."

**Speech (Atharv):** every line in 4.4 matches exactly.

**Eligibility (Tiea):** three demo items correct; kettle corn never `eligible`; an eligible rule with no store listing, a disagreeing listing, and package disagreement each return `could_not_confirm`; a medication outside the IRS-backed categories returns `could_not_confirm`; Moss down falls back to category rules.

**App (Nak), manual:** permission-denied paths; silent switch; Bluetooth; incoming call mid-sentence; 3-minute idle reconnect; barge-in; largest text size on every screen; VoiceOver and TalkBack.

## 4.6 Demo-day runbook

- **Do not update Expo Go** on the demo phone. Turn off automatic app updates.
- Log in to Expo on the phone and the laptop at the venue; test before judging opens.
- Confirm the Supabase project is awake (open the dashboard, run `reset_demo(1)`).
- Pre-test lighting on the **exact** shelf under booth light.
- Warm the Cartesia connection and run a test scan before judges arrive.
- Phone hotspot ready and rehearsed. Know the `npx expo start --tunnel` fallback.
- Second phone with the same build; chargers for both.
- `reset_demo(1)` before each run, `reset_demo(2)` before the declined-card run.
- Recorded backup video of a clean run. This is the only fallback if Supabase or the internet is down.
- **If you replay a saved result after a failed scan, say so out loud.**
- Judges will try their own item. The unresolved path must work cleanly: "I could not confirm this item."
- Say "this is a simulated payment" and that the demo items are pre-cached.

## 4.7 Confirm at booths in the first two hours

| Booth | Question | Blocks |
|---|---|---|
| Capital One | Nessie base URL, auth style, account types | Balance layer |
| Anthropic | Whether Claude credits reach every team member | Vision budget |
| Apify | Whether the track allows collecting this data, and the free-plan limit | The prefetch |
| Moss | Backend Python usage and index rebuild behavior | Classifier |
| Cartesia | API key variable name and idle-timeout figure | Reconnect logic |
| Visa | What the track accepts as a checkout; ours stays simulated | Checkout framing |

## 4.8 Working rules

- **One owner per file area** (0.3).
- **Message formats are agreed before building starts.** That is 0.5, and it is fixed.
- **Nobody adds a feature without removing one.**
- No API keys, card numbers, or full transcripts in logs.
- Camera frames are never stored.
- Everything the agent says also appears as a caption.

## 4.9 What to say about accuracy

The honest framing is also the strongest one for the Anthropic track's "thoughtful use of Claude, including where it could go wrong":

- Eligibility is checked against retailer-listed data and IRS category rules. It is not a certified list.
- When the system cannot confirm, it says so and asks. Report the measured `could_not_confirm` rate from the test set.
- The insurance-covered portion is never routed to an HSA. Copays always end with a pharmacist check.
- At IIAS stores, registers may already block ineligible items. Rewind tells the shopper in the aisle, before the register, and which card to use.
- All payments are simulated. All insurer and card data is mock.
