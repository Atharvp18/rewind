# Rewind — Fetch.ai agents

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Rewind helps elderly and low-vision shoppers know what a product is, what it costs,
whether it is HSA/FSA eligible, and which card to pay with, before they reach the register.
These agents run that workflow inside an ASI:One conversation.

## Agents

| Agent | Name on Agentverse | Address | Role |
|---|---|---|---|
| `orchestrator_agent.py` | Rewind Shopping Assistant | `agent1qgh2lut00vnaxk78nl6fyvs3l39huakthle9z3umf8042s8tmjv3jet6wsu` | The front desk. Talks to the user over the Agent Chat Protocol, understands each message (Claude), keeps each user's session in `ctx.storage`, phrases every reply, and routes work to the specialists |
| `product_agent.py` | Rewind Product Agent | `agent1qv5swthwpdms49gh0k4hndrcjkkvk8d90z4w529md7zg973mlyj9xz44xj9` | Specialist. Shelf photo or product name → fixed pipeline (vision → lookup → eligibility) → facts + `ScanResult` |
| `payment_agent.py` | Rewind Payment Agent | `agent1qvkjw79mr7ew9neq52fhyqu2l8vheewwu4j43pcnt43f3vzpl4jsgganw52` | Specialist. Card routing (HSA/FSA vs. general), cart, low-balance alerts, simulated checkout |
| `history_agent.py` | Rewind History Agent | `agent1q2gktwmd0ya5qqrtm0p0cqxryvgtmfq0yprnhh7ssged68n6hvnnyt9y4nf` | Specialist, read-only. Answers questions about past purchases (totals, what was bought, what could be claimed back) from a Moss memory; Claude fills a fixed question form, code does the dates and sums |

```
ASI:One user ──Chat Protocol──▶ Orchestrator ──ProductRequest──▶ Product agent
                                  (ctx.storage)◀─ProductResponse──┘
                                       │
                                       ├──PaymentRequest──▶ Payment agent
                                       ◀──PaymentResponse──┘
                                       ├──HistoryRequest──▶ History agent
                                       ◀──HistoryResponse──┘
```

Workers are stateless and deterministic: they return **facts** (`FactsMsg`), never sentences.
The orchestrator turns facts into natural speech with Claude and refuses to speak any
rephrasing that drops a fact or adds a number (`speaker.py`).

## How it understands and where it stops

- **Natural language in.** One Claude Haiku call classifies each message into a fixed set of intents. No keyword matching, except a medical-term list that always triggers the pharmacist refusal.
- **Deterministic rules out.** Eligibility, card routing, and the cart are decided in code. Claude cannot override them.
- **Guardrails:** no medical advice; no help with someone else's prescription; a not-eligible item never goes on the HSA/FSA; card balances are never spoken (only "can't cover it, please use another card", plus a low-balance alert); nothing enters the cart or gets paid without the user confirming in their own words.

## Workflow inside ASI:One

1. Attach a shelf photo, or ask "are these bandages HSA eligible?"
2. The assistant says the item, price, eligibility, and asks which card.
3. Say "add it" or "put it on the Visa". Repeat for more items.
4. Ask "what's in my cart", then "checkout", and confirm.
5. It reads what went on each card. **All payments are simulated.**

"Reset demo run 2" starts a session where the HSA card can't cover the whole cart, to show the reroute.

## Run

```bash
cd backend
python3 -m pip install -r requirements.txt
cp .env.example .env     # add ANTHROPIC_API_KEY and three agent seeds
```

**Locally, no Agentverse:** `make local` runs all agents in one process with a scripted shopper.

**On Agentverse (for ASI:One):** run `make orchestrator`, `make product`, `make payment`, `make history` in four
terminals. For each, open the inspector link it prints → **Connect → Mailbox**. Then on the
orchestrator: **Agent Profile → Chat with Agent**.

Worker addresses are derived from their seeds, so the orchestrator finds them automatically.
Set `PRODUCT_AGENT_ADDRESS` / `PAYMENT_AGENT_ADDRESS` only if a worker runs with a seed you don't have.

## Tests

```bash
make test
```

## Honest limits

- Eligibility comes from IRS category rules and retailer-listed data, not a certified list. When it can't confirm, it says so and asks.
- Until the database is connected, items found only by name come back "could not confirm."
- The insurance-covered part of a medication is never routed to an HSA/FSA.
- A photo attached in ASI:One passes through Fetch.ai's Agent Storage. The phone app path never stores frames.


## History (purchase memory)

- Over-the-counter purchases only (a prescription copay is never stored).
- Source of truth: Supabase `purchase_items` (run `backend/data/migration_purchase_items.sql` once in the SQL Editor).
  Checkout copies each payment's rows into a Moss memory in the background; `History` reads Moss (exact filters:
  date, card, medicine, category; fuzzy lookup only for a named product) and falls back to the table if Moss is down.
- Set `HISTORY_AGENT_SEED` in `backend/.env`, run `python agents/history_agent.py`, Connect -> Mailbox, and paste its
  address in the table above (same as the other agents).
- Rehearse before the table exists: `python scripts/local_chat.py history` (sample purchases, no database).

