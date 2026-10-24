# Rewind — Fetch.ai agents

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Rewind helps elderly and low-vision shoppers know what a product is, what it costs,
whether it is HSA/FSA eligible, and which card to pay with — before they reach the register.
These agents expose that workflow inside an ASI:One conversation.

## Agents

| Agent | Name on Agentverse | Address | Role |
|---|---|---|---|
| `orchestrator_agent.py` | Rewind Shopping Assistant | _fill in after first run_ | Entry point. Owns the session (cards, cart, last scan). Routes to the two workers and relays replies |
| `product_agent.py` | Rewind Product Agent | _fill in after first run_ | Takes a shelf photo (`ResourceContent`) or a product name, runs vision → lookup → eligibility, returns a `ScanResult` |
| `payment_agent.py` | Rewind Payment Agent | _fill in after first run_ | Cart, card routing (HSA/FSA vs. general), reroute on low balance, simulated checkout |

All three implement the Agent Chat Protocol (`chat_protocol_spec`), acknowledge every
message, honour `StartSession`/`EndSession`, and publish their manifest to Agentverse.

## Workflow inside ASI:One

1. Attach a shelf photo, or type "Is Advil HSA eligible?"
2. The assistant says the item, price, eligibility, your HSA balance, and asks which card.
3. Say "add it". Repeat for more items.
4. Say "what's in my cart", then "checkout". Confirm with "yes".
5. The assistant reads the split per card and the new balances. **All payments are simulated.**

Run 2 of the demo: say "reset demo run 2" to set the HSA balance to $15.00 and trigger the reroute.

## Run locally

```bash
cd backend
python3 -m pip install -r requirements.txt      # Python 3.10+ (python.org build on this machine)
cp .env.example .env            # set the three agent seeds
make orchestrator               # terminal 1
make product                    # terminal 2 (optional — orchestrator works alone)
make payment                    # terminal 3 (optional)
```

Each agent prints an inspector link. Open it, click **Connect → Mailbox**, then
**Agent Profile → Chat with Agent** on the orchestrator to talk through ASI:One.

To run as three separate agents, copy the product and payment addresses from their
startup logs into `PRODUCT_AGENT_ADDRESS` and `PAYMENT_AGENT_ADDRESS` in `.env`
and restart the orchestrator. Without them the orchestrator runs all logic in-process.

## Tests

```bash
make test
```

## Honest limits

- Eligibility is checked against IRS category rules and retailer-listed data. It is not a certified list.
- When the assistant cannot confirm, it says so and asks which card to use.
- The insurance-covered part of a medication is never routed to an HSA/FSA.
- Session state is in memory for now; it moves to the backend database next.
- A photo attached in ASI:One passes through Fetch.ai's Agent Storage. The phone app path never stores frames.
