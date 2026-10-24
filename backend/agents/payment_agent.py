"""Rewind Payment Agent (Fetch.ai / ASI:One).

Stateless worker. Receives the user's command plus the session (cards, cart,
last scan, pending question) as metadata, applies cart and routing rules, and
returns the reply text plus the updated session.

Routing here is the minimal form of tech spec 3.5. It will be replaced by
Atharv's payments/routing.py when the backend is wired in.
"""
from __future__ import annotations

import copy
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, chat_protocol_spec

from agents.common import Incoming, ack, dollars, reply
from agents.session import LOW_BALANCE_CENTS, new_session

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "I'm the Rewind Payment Agent. I manage your cart and decide which card each item goes on.\n\n"
    "Say: \"add it\", \"skip it\", \"what's in my cart\", \"remove last item\", "
    "\"clear cart\", \"my balances\", or \"checkout\"."
)

YES = ("yes", "yeah", "yep", "add it", "add that", "add", "ok", "okay", "sure", "confirm", "do it")
NO = ("no", "nope", "skip", "skip it", "cancel", "never mind")


def _card(session: dict, card_id: str) -> dict:
    return next(c for c in session["cards"] if c["id"] == card_id)


def _health_card(session: dict) -> dict | None:
    cards = [c for c in session["cards"] if c["type"] in ("hsa", "fsa") and c["status"] == "active"]
    if not cards:
        return None
    defaults = [c for c in cards if c["is_default"]]
    return defaults[0] if defaults else cards[0] if len(cards) == 1 else None


def _general_card(session: dict) -> dict | None:
    cards = [c for c in session["cards"] if c["type"] == "general" and c["status"] == "active"]
    return cards[0] if cards else None


def _route(session: dict, scan: dict) -> dict:
    """Minimal spec 3.5 routing. Returns {decision, card_id, reason_code, card_options}."""
    elig = scan["eligibility"]["label"]
    amount = scan["product"]["amount_cents"]
    hsa, visa = _health_card(session), _general_card(session)
    if not session["cards"]:
        return {"decision": "blocked", "card_id": None, "reason_code": "no_card_linked", "card_options": []}
    if elig == "could_not_confirm":
        return {"decision": "ask_user", "card_id": None, "reason_code": "eligibility_unconfirmed",
                "card_options": [c["id"] for c in session["cards"]]}
    if elig == "not_eligible":
        if visa is None:
            return {"decision": "blocked", "card_id": None, "reason_code": "no_card_covers", "card_options": []}
        return {"decision": "route_to_general", "card_id": visa["id"], "reason_code": "not_eligible", "card_options": []}
    if hsa is None:
        if visa is None:
            return {"decision": "blocked", "card_id": None, "reason_code": "no_card_covers", "card_options": []}
        return {"decision": "route_to_general", "card_id": visa["id"], "reason_code": "no_health_card_linked", "card_options": []}
    if hsa["balance_cents"] >= amount:
        return {"decision": "route_to_hsa", "card_id": hsa["id"], "reason_code": "eligible_sufficient_balance", "card_options": []}
    if visa and visa["balance_cents"] >= amount:
        return {"decision": "ask_user", "card_id": visa["id"], "reason_code": "eligible_insufficient_balance",
                "card_options": [visa["id"]]}
    return {"decision": "blocked", "card_id": None, "reason_code": "no_card_covers", "card_options": []}


def _add_to_cart(session: dict, scan: dict, card_id: str, overrode: bool = False) -> str:
    card = _card(session, card_id)
    session["cart"].append({
        "id": str(uuid4()),
        "scan_id": scan["scan_id"],
        "display_name": scan["product"]["name"],
        "amount_cents": scan["product"]["amount_cents"],
        "card_id": card_id,
        "eligibility_label": scan["eligibility"]["label"],
        "user_overrode_card": overrode,
    })
    session["last_scan"] = None
    session["pending"] = None
    return f"Added {scan['product']['name']} to your {card['nickname']}."


def _groups(session: dict) -> list[dict]:
    out = []
    for card in session["cards"]:
        items = [i for i in session["cart"] if i["card_id"] == card["id"]]
        if items:
            out.append({"card": card, "items": items, "subtotal_cents": sum(i["amount_cents"] for i in items)})
    return out


def _cart_summary(session: dict) -> str:
    groups = _groups(session)
    if not groups:
        return "Your cart is empty."
    lines = []
    for g in groups:
        n = len(g["items"])
        lines.append(f"{n} item{'s' if n != 1 else ''} totaling {dollars(g['subtotal_cents'])} on your {g['card']['nickname']}.")
    total = sum(g["subtotal_cents"] for g in groups)
    lines.append(f"Total before tax: {dollars(total)}.")
    return " ".join(lines)


def _balances(session: dict) -> str:
    if not session["cards"]:
        return "No cards are linked yet."
    return " ".join(f"Your {c['nickname']} balance is {dollars(c['balance_cents'])}." for c in session["cards"])


def _checkout_preview(session: dict) -> str:
    if not session["cart"]:
        return "Your cart is empty."
    issues = []
    for g in _groups(session):
        card = g["card"]
        if g["subtotal_cents"] > card["balance_cents"]:
            visa = _general_card(session)
            keep, move = [], []
            remaining = card["balance_cents"]
            for item in sorted(g["items"], key=lambda i: -i["amount_cents"]):
                if item["amount_cents"] <= remaining:
                    keep.append(item)
                    remaining -= item["amount_cents"]
                else:
                    move.append(item)
            if visa is None or not move:
                return (f"Your {card['nickname']} balance is only {dollars(card['balance_cents'])}, which doesn't cover "
                        f"{dollars(g['subtotal_cents'])}. Please use a credit card for this item.")
            session["pending"] = {"scope": "confirm_reroute", "move_ids": [i["id"] for i in move], "to_card": visa["id"]}
            keep_names = " and ".join(i["display_name"] for i in keep) or "nothing"
            move_names = " and ".join(i["display_name"] for i in move)
            return (f"Your {card['nickname']} balance is only {dollars(card['balance_cents'])}, which doesn't cover "
                    f"{dollars(g['subtotal_cents'])}. Want me to keep the {keep_names} on your {card['nickname']} "
                    f"and move the {move_names} to your {visa['nickname']}?")
    session["pending"] = {"scope": "confirm_checkout"}
    return _cart_summary(session) + " Ready to check out?"


def _checkout_confirm(session: dict) -> str:
    alerts = []
    for g in _groups(session):
        card = g["card"]
        card["balance_cents"] -= g["subtotal_cents"]
        if card["type"] in ("hsa", "fsa") and card["balance_cents"] < LOW_BALANCE_CENTS:
            alerts.append(f"Heads up: your {card['nickname']} is now below {dollars(LOW_BALANCE_CENTS)}.")
    hsa = _health_card(session)
    session["cart"] = []
    session["pending"] = None
    msg = "Payment complete. This was a simulated payment."
    if hsa:
        msg += f" Your {hsa['nickname']} balance is now {dollars(hsa['balance_cents'])}."
    return " ".join([msg, *alerts])


def _speak_recommendation(session: dict, scan: dict, rec: dict) -> str:
    name = scan["product"]["name"]
    price = dollars(scan["product"]["amount_cents"])
    d, code = rec["decision"], rec["reason_code"]
    if d == "route_to_hsa":
        card = _card(session, rec["card_id"])
        session["pending"] = {"scope": "confirm_add", "card_id": card["id"]}
        return f"{name}, {price}. HSA eligible. Your {card['nickname']} balance is {dollars(card['balance_cents'])}. Want to use your {card['nickname']}?"
    if d == "route_to_general":
        card = _card(session, rec["card_id"])
        session["pending"] = {"scope": "confirm_add", "card_id": card["id"]}
        why = "Not HSA eligible." if code == "not_eligible" else "No HSA card is linked."
        return f"{name}, {price}. {why} I'll put this on your {card['nickname']}. Okay?"
    if d == "ask_user" and code == "eligible_insufficient_balance":
        hsa, visa = _health_card(session), _card(session, rec["card_id"])
        session["pending"] = {"scope": "choose_card", "card_options": [visa["id"]], "overrode": True}
        return (f"{name}, {price}. HSA eligible, but your {hsa['nickname']} balance is only {dollars(hsa['balance_cents'])}. "
                f"Want to put it on your {visa['nickname']} instead?")
    if d == "ask_user":
        session["pending"] = {"scope": "choose_card", "card_options": rec["card_options"], "overrode": False}
        names = " or ".join(_card(session, c)["nickname"] for c in rec["card_options"])
        return f"{name}, {price}. I could not confirm eligibility. Which card would you like to use: {names}?"
    if code == "no_card_linked":
        return "No card is linked. Add a card in settings before adding items."
    return f"{name}, {price}. No linked card covers this. Please use a credit card for this item."


def _match_card(session: dict, text: str, options: list[str]) -> str | None:
    t = text.lower()
    for cid in options:
        card = _card(session, cid)
        if card["type"] in t or card["nickname"].lower().split()[0] in t:
            return cid
    return None


def handle(text: str, session: dict) -> tuple[str, dict]:
    """Pure handler: (reply text, updated session). Mutates a copy, never the input."""
    session = copy.deepcopy(session)
    t = text.lower().strip().rstrip("?.!")
    pending = session.get("pending")

    if pending:
        scope = pending["scope"]
        if scope == "confirm_add":
            if t in YES or t.startswith(YES):
                return _add_to_cart(session, session["last_scan"], pending["card_id"]), session
            if t in NO or t.startswith(NO):
                session["pending"], session["last_scan"] = None, None
                return "Okay, skipped.", session
        elif scope == "choose_card":
            if t in NO:
                session["pending"], session["last_scan"] = None, None
                return "Okay, skipped.", session
            cid = _match_card(session, t, pending["card_options"])
            if cid is None and (t in YES) and len(pending["card_options"]) == 1:
                cid = pending["card_options"][0]
            if cid:
                return _add_to_cart(session, session["last_scan"], cid, overrode=pending["overrode"]), session
            names = " or ".join(_card(session, c)["nickname"] for c in pending["card_options"])
            return f"Which card: {names}?", session
        elif scope == "confirm_checkout":
            if t in YES:
                return _checkout_confirm(session), session
            if t in NO:
                session["pending"] = None
                return "Okay, checkout cancelled.", session
        elif scope == "confirm_reroute":
            if t in YES:
                for item in session["cart"]:
                    if item["id"] in pending["move_ids"]:
                        item["card_id"] = pending["to_card"]
                        item["user_overrode_card"] = True
                session["pending"] = None
                return "Done. " + _checkout_preview(session), session
            if t in NO:
                session["pending"] = None
                return "Okay. Your cart is unchanged.", session
        elif scope == "confirm_clear":
            if t in YES:
                session["cart"], session["pending"] = [], None
                return "Cart cleared.", session
            session["pending"] = None
            return "Okay, your cart is unchanged.", session

    if "clear cart" in t or t == "clear":
        if not session["cart"]:
            return "Your cart is already empty.", session
        session["pending"] = {"scope": "confirm_clear"}
        return "Clear everything from your cart?", session
    if "remove last" in t or "remove the last" in t:
        if not session["cart"]:
            return "Your cart is empty.", session
        removed = session["cart"].pop()
        return f"Removed {removed['display_name']}. " + _cart_summary(session), session
    if "cart" in t or "what's in" in t or "whats in" in t:
        return _cart_summary(session), session
    if "balance" in t:
        return _balances(session), session
    if "checkout" in t or "check out" in t:
        return _checkout_preview(session), session
    if any(t == y or t.startswith(y) for y in YES) and session.get("last_scan"):
        rec = _route(session, session["last_scan"])
        if rec["decision"] in ("route_to_hsa", "route_to_general"):
            return _add_to_cart(session, session["last_scan"], rec["card_id"]), session
        return _speak_recommendation(session, session["last_scan"], rec), session
    if t in NO and session.get("last_scan"):
        session["last_scan"] = None
        return "Okay, skipped.", session
    return HELP_TEXT, session


def recommend(session: dict, scan: dict) -> tuple[str, dict]:
    """Called by the orchestrator right after a scan resolves with a price."""
    session = copy.deepcopy(session)
    session["last_scan"] = scan
    if scan["product"].get("amount_cents") is None:
        session["pending"] = None
        return (f"I see {scan['product']['name']} but could not read a price. "
                "Tell me the shelf price and I'll add it to your cart."), session
    rec = _route(session, scan)
    return _speak_recommendation(session, scan, rec), session


protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def on_message(ctx: Context, sender: str, msg: ChatMessage):
    await ack(ctx, sender, msg)
    inc = Incoming(msg)
    session = inc.json("session") or new_session()
    scan = inc.json("scan")
    if scan:
        text, session = recommend(session, scan)
    else:
        text, session = handle(inc.text, session)
    passthrough = {"user": inc.metadata["user"]} if "user" in inc.metadata else {}
    await ctx.send(sender, reply(text, {**passthrough, "session": session}))


@protocol.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


def build_agent() -> Agent:
    agent = Agent(
        name="Rewind Payment Agent",
        seed=os.environ.get("PAYMENT_AGENT_SEED", "rewind-payment-agent-dev-seed"),
        port=int(os.environ.get("PAYMENT_AGENT_PORT", "8002")),
        mailbox=True,
        publish_agent_details=True,
    )
    agent.include(protocol, publish_manifest=True)
    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
