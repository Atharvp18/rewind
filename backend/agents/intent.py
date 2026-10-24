"""Intent classification for the Rewind agents.

Claude Haiku turns free-form speech into ONE of a fixed set of intents plus a
few entities. It never writes a reply. There is no keyword matching on what
the user said; the only hardcoded vocabulary is medical, used as a guard that
forces the medical-advice refusal no matter what the classifier returns.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

IntentName = Literal[
    # product
    "scan_product", "eligibility_question", "give_price",
    # cart & payment
    "add_to_cart", "skip", "cart_query", "checkout", "confirm", "deny",
    "choose_card", "remove_last", "clear_cart", "balance_query",
    # insurance
    "choose_plan", "insurance_question",
    # session
    "repeat", "reset_demo", "greeting",
    # guardrails: refused in code, never answered
    "medical_advice", "other_person", "route_ineligible_to_hsa",
    # catch-all
    "out_of_scope", "unclear",
]


class Entities(BaseModel):
    product: str | None = Field(None, description="Product the user named, with strength if said, e.g. 'omeprazole 20mg'")
    card: Literal["hsa", "fsa", "visa"] | None = Field(None, description="Card the user named")
    price_dollars: float | None = Field(None, description="A price the user spoke, in dollars")
    run: Literal[1, 2] | None = Field(None, description="Demo run number if resetting")
    plan: Literal["uhc_student", "sunrise_ppo", "evergreen_hsa", "harbor_choice", "basic_medical", "unknown"] | None = Field(
        None, description="Insurance plan the user named; 'unknown' if they say they don't know")
    is_prescription: bool | None = Field(
        None, description="True if the user says the item is a prescription from the pharmacy counter")


class Intent(BaseModel):
    intent: IntentName
    entities: Entities = Entities()


MODEL = os.environ.get("INTENT_MODEL", "claude-haiku-5-5")
TIMEOUT_S = float(os.environ.get("INTENT_TIMEOUT_S", "4.0"))
STUB_MODE = os.environ.get("REWIND_STUB_INTENT", "false").lower() == "true"

SYSTEM_PROMPT = """\
You classify what a shopper said to Rewind, a voice-first shopping assistant for \
elderly and low-vision people. Rewind identifies a product, says whether it is \
HSA/FSA eligible, routes it to the right card, and runs a simulated checkout.

Pick exactly one intent. Do not answer the user. Do not add fields.

Intent guide:
- scan_product: wants to identify a product, or sent/mentions a photo
- eligibility_question: asks whether an item is HSA/FSA eligible or covered
- give_price: states a price for the item being discussed ("it's four dollars")
- add_to_cart: wants the current item in the cart ("add it", "put it on my HSA")
- skip: does not want the current item
- confirm / deny: yes/no, in any words, to the question the assistant just asked
- choose_card: names which card to use when asked
- cart_query: asks what is in the cart
- checkout: wants to pay / finish
- remove_last: remove the most recent item
- clear_cart: empty the cart
- balance_query: asks a card balance
- choose_plan: names their insurance plan, or says they don't know it (plan = "unknown")
- insurance_question: asks what insurance they have or what it covers
- repeat: asks to hear the last thing again
- reset_demo: "reset demo", optionally run 1 or 2
- greeting: hello / what can you do
- medical_advice: asks about dosage, interactions, safety, side effects, or whether to take something
- other_person: asks about someone else's prescription, card, or account
- route_ineligible_to_hsa: insists on paying for a non-eligible item with the HSA/FSA
- out_of_scope: unrelated to shopping (weather, jokes, news)
- unclear: cannot tell

Insurance plans (map what the user says to one id):
- uhc_student: UnitedHealthcare, UHC, student health plan
- sunrise_ppo: Sunrise PPO
- evergreen_hsa: Evergreen HSA Plan, high-deductible plan
- harbor_choice: Harbor Choice Plan
- basic_medical: Basic Medical Plan, no prescription coverage
A medicine the user calls "my prescription", or one picked up "at the counter", sets is_prescription. \
Put the drug and strength in product, e.g. "omeprazole 20mg", and use eligibility_question.

Context tells you what the assistant just asked; a bare "yes", "sure", "nah", \
or "that one" refers to it."""


def _context(session: dict) -> str:
    pending = session.get("pending") or {}
    scan = session.get("last_scan") or {}
    lines = []
    if pending:
        lines.append(f"Assistant's pending question: {pending.get('scope')}")
    if scan:
        p = scan.get("product", {})
        lines.append(f"Item being discussed: {p.get('name')} "
                     f"(price {'known' if p.get('amount_cents') is not None else 'unknown'}, "
                     f"eligibility {scan.get('eligibility', {}).get('label')})")
    lines.append(f"Items in cart: {len(session.get('cart', []))}")
    ins = session.get("insurance")
    lines.append(f"Insurance plan on file: {ins['short_name'] if ins else 'none'}")
    return "\n".join(lines)


# The one permitted hardcoded vocabulary: medical terms. Any of these forces the
# pharmacist refusal, whatever the classifier says.
MEDICAL_TERMS = (
    "dose", "dosage", "how many should", "how much should i take", "overdose",
    "interact", "interaction", "side effect", "safe to take", "is it safe",
    "can i take", "should i take", "with alcohol", "while pregnant", "breastfeeding",
    "blood pressure", "blood thinner", "allerg", "contraindicat",
)


def medical_guard(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in MEDICAL_TERMS)


async def classify_intent(text: str, session: dict, has_image: bool = False) -> Intent:
    """Classify with Claude. On stub mode, timeout, or error the intent is `unclear`."""
    if medical_guard(text):
        return Intent(intent="medical_advice")
    if has_image and not text.strip():
        return Intent(intent="scan_product")
    if STUB_MODE:
        return Intent(intent="unclear")
    try:
        return await asyncio.wait_for(_classify_with_claude(text, session, has_image), TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("intent classification timed out after %ss", TIMEOUT_S)
    except Exception:
        logger.exception("intent classification failed")
    return Intent(intent="unclear")


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic()
    return _client


async def warm_up() -> None:
    """Open the connection before the first user message so it doesn't pay the setup cost."""
    if STUB_MODE:
        return
    try:
        await asyncio.wait_for(_classify_with_claude("hello", {}, False), 10.0)
    except Exception:
        logger.warning("intent warm-up failed; first message may be slow")


async def _classify_with_claude(text: str, session: dict, has_image: bool) -> Intent:
    user = f"Context:\n{_context(session)}\nPhoto attached: {'yes' if has_image else 'no'}\n\nUser said: {text!r}"
    response = await _get_client().messages.parse(
        model=MODEL,
        max_tokens=256,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        output_format=Intent,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return Intent(intent="unclear")
    return response.parsed_output


# --- fixed refusal wording (never rephrased) ---------------------------------

REFUSALS: dict[str, str] = {
    "medical_advice": "I can't give medical advice. Please ask the pharmacist.",
    "other_person": "I can only help with your own items and cards. For someone else's prescription, please ask the pharmacist.",
    "route_ineligible_to_hsa": "I can't put that on your HSA or FSA, because I could not confirm it is eligible. I can add it to your Visa credit instead.",
    "out_of_scope": "I can only help with shopping: what an item is, whether it's HSA eligible, your cart, and checkout.",
}
