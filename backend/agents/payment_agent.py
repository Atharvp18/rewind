"""Rewind Payment Agent — a uAgents worker.

Stateless worker. Receives a classified intent plus the session (cards, cart,
last scan, pending question), applies cart and routing rules, and returns a
fact sheet plus the updated session. Nothing here matches on the user's words.

Cards and cart live in Supabase (Atharv's schema, via data/db.py). agents/store.py
loads them into the session before the rules run and writes the changes back after.
Routing is the minimal form of tech spec 3.5.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context

from agents import store
from agents.addresses import ORCHESTRATOR_AGENT_ADDRESS, PAYMENT_SEED
from agents.common import dollars
from agents.messages import FactsMsg, PaymentRequest, PaymentResponse, payment_protocol
from agents.intent import REFUSALS, Intent
from agents.insurance import COPAY_HSA, also_sold_by_prescription, coverage, describe_plan, strength_of
from agents.session import LOW_BALANCE_CENTS, plan_profile
from agents.speaker import Facts, say
from data.db import DBUnavailable

logger = logging.getLogger(__name__)

HELP = say("I can add the item you're looking at, read your cart, "
           "remove the last item, or check out. What would you like?")

# Privacy rule: balances are never spoken. The agent only says whether a card
# can cover something, and raises a beep + spoken alert when a card runs low.
BALANCE_PRIVATE = say("For your privacy, I don't say card balances out loud. "
                      "I'll tell you if a card can't cover an item, and I'll alert you when a card is running low.",
                      fixed=True)


def low_balance_alert(card: dict) -> Facts | None:
    if card["type"] in ("hsa", "fsa") and card["balance_cents"] < LOW_BALANCE_CENTS:
        return say(f"Your {card['nickname']} is running low. You might want to add funds.",
                   card["nickname"], "running low", alert="low_balance")
    return None


def _with_alert(facts: Facts, card: dict | None) -> Facts:
    """Append a low-balance alert to facts if the card is low."""
    alert = low_balance_alert(card) if card else None
    if alert is None:
        return facts
    return say(facts.template + " " + alert.template, *facts.must_say, *alert.must_say, alert="low_balance")


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


def _card_by_type(session: dict, kind: str | None) -> dict | None:
    if kind == "hsa":
        return _health_card(session)
    if kind == "visa":
        return _general_card(session)
    return None


def _route(session: dict, scan: dict) -> dict:
    """Minimal spec 3.5 routing."""
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


def _add_to_cart(session: dict, scan: dict, card_id: str, overrode: bool = False) -> Facts:
    card = _card(session, card_id)
    name = scan["product"]["name"]
    session["cart"].append({
        "id": str(uuid4()),
        "scan_id": scan["scan_id"],
        "product_key": scan["product"]["product_key"],
        "display_name": name,
        "amount_cents": scan["product"]["amount_cents"],
        "amount_basis": scan.get("amount_basis", "shelf_price"),
        "assigned_card_id": card_id,
        "eligibility_label": scan["eligibility"]["label"],
        "user_overrode_card": overrode,
        "_scan": {k: scan[k] for k in ("state", "product", "eligibility")},   # saved to scans, then dropped
    })
    session["last_scan"] = None
    session["pending"] = None
    return say(f"Added {name} to your {card['nickname']}.", name, card["nickname"])


def _groups(session: dict) -> list[dict]:
    out = []
    for card in session["cards"]:
        items = [i for i in session["cart"] if i["assigned_card_id"] == card["id"]]
        if items:
            out.append({"card": card, "items": items, "subtotal_cents": sum(i["amount_cents"] for i in items)})
    return out


def _cart_summary(session: dict) -> Facts:
    groups = _groups(session)
    if not groups:
        return say("Your cart is empty.", "empty")
    lines, must = [], []
    for g in groups:
        n, sub, nick = len(g["items"]), dollars(g["subtotal_cents"]), g["card"]["nickname"]
        lines.append(f"{n} item{'s' if n != 1 else ''} totaling {sub} on your {nick}")
        must += [sub, nick]
    if len(groups) == 1:
        return say(lines[0] + ", before tax.", *must, "before tax")
    total = dollars(sum(g["subtotal_cents"] for g in groups))
    return say(". ".join(lines) + f". {total} in all, before tax.", *must, total, "before tax")


def _balances(session: dict) -> Facts:
    if not session["cards"]:
        return say("No cards are linked yet.")
    low = [low_balance_alert(c) for c in session["cards"]]
    low = [a for a in low if a]
    if not low:
        return BALANCE_PRIVATE
    return say(BALANCE_PRIVATE.template + " " + " ".join(a.template for a in low),
               *[m for a in low for m in a.must_say], alert="low_balance")


def _checkout_preview(session: dict) -> Facts:
    if not session["cart"]:
        return say("Your cart is empty.", "empty")
    for g in _groups(session):
        card = g["card"]
        if g["subtotal_cents"] > card["balance_cents"]:
            visa = _general_card(session)
            keep, move, remaining = [], [], card["balance_cents"]
            for item in sorted(g["items"], key=lambda i: -i["amount_cents"]):
                if item["amount_cents"] <= remaining:
                    keep.append(item)
                    remaining -= item["amount_cents"]
                else:
                    move.append(item)
            sub, nick = dollars(g["subtotal_cents"]), card["nickname"]
            if visa is None or not move:
                return _with_alert(say(f"Your {nick} can't cover {sub}. Please use another card for this item.",
                                       nick, sub, "another card"), card)
            session["pending"] = {"scope": "confirm_reroute", "move_ids": [i["id"] for i in move], "to_card": visa["id"]}
            keep_names = " and ".join(i["display_name"] for i in keep) or "nothing"
            move_names = " and ".join(i["display_name"] for i in move)
            return say(f"Your {nick} can't cover all {sub}. "
                       f"Want me to keep the {keep_names} on your {nick} and move the {move_names} to your {visa['nickname']}?",
                       nick, sub, keep_names, move_names, visa["nickname"])
    session["pending"] = {"scope": "confirm_checkout"}
    summary = _cart_summary(session)
    return say(summary.template + " Ready to check out?", *summary.must_say)


def _checkout_confirm(session: dict) -> Facts:
    lines, must = ["Payment complete. This was a simulated payment."], ["simulated"]
    # Supabase debits the cards atomically (confirm_checkout); the local math only shapes the reply.
    session["checkout_splits"] = [{"card_id": g["card"]["id"], "amount_cents": g["subtotal_cents"]}
                                  for g in _groups(session)]
    for g in _groups(session):
        card = g["card"]
        card["balance_cents"] -= g["subtotal_cents"]
        lines.append(f"{dollars(g['subtotal_cents'])} went on your {card['nickname']}.")
        must += [dollars(g["subtotal_cents"]), card["nickname"]]
    alerts = [a for a in (low_balance_alert(c) for c in session["cards"]) if a]
    session["cart"], session["pending"] = [], None
    for a in alerts:
        lines.append(a.template)
        must += a.must_say
    return say(" ".join(lines), *must, alert="low_balance" if alerts else None)


def _speak_recommendation(session: dict, scan: dict, rec: dict) -> Facts:
    name = scan["product"]["name"]
    price = dollars(scan["product"]["amount_cents"])
    d, code = rec["decision"], rec["reason_code"]
    if d == "route_to_hsa":
        card = _card(session, rec["card_id"])
        session["pending"] = {"scope": "confirm_add", "card_id": card["id"]}
        return say(f"{name}, {price}. HSA eligible. Want to use your {card['nickname']}?",
                   name, price, "HSA eligible", card["nickname"])
    if d == "route_to_general":
        card = _card(session, rec["card_id"])
        session["pending"] = {"scope": "confirm_add", "card_id": card["id"]}
        why = "Not HSA eligible." if code == "not_eligible" else "No HSA card is linked."
        return say(f"{name}, {price}. {why} I'll put this on your {card['nickname']}. Okay?",
                   name, price, why.rstrip("."), card["nickname"])
    if d == "ask_user" and code == "eligible_insufficient_balance":
        hsa, visa = _health_card(session), _card(session, rec["card_id"])
        session["pending"] = {"scope": "choose_card", "card_options": [visa["id"]], "overrode": True}
        return _with_alert(say(f"{name}, {price}. HSA eligible, but your {hsa['nickname']} can't cover it. "
                               f"Please use another card. Want to put it on your {visa['nickname']}?",
                               name, price, "HSA eligible", hsa["nickname"], "another card", visa["nickname"]), hsa)
    if d == "ask_user":
        session["pending"] = {"scope": "choose_card", "card_options": rec["card_options"], "overrode": False}
        nicks = [_card(session, c)["nickname"] for c in rec["card_options"]]
        return say(f"{name}, {price}. I could not confirm eligibility. Which card would you like to use: {' or '.join(nicks)}?",
                   name, price, "could not confirm eligibility", *nicks)
    if code == "no_card_linked":
        return say("No card is linked. Add a card in settings before adding items.")
    return say(f"{name}, {price}. None of your linked cards can cover this. Please use another card for this item.",
               name, price, "another card")


# --- counter prescriptions (agents/insurance.py has the plan rules) ---------------

def _rx_start(session: dict, scan: dict) -> Facts:
    """Read the drug and strength back before anything else (spec 6.2, 20.4)."""
    p = scan["product"]
    drug, strength = p["name"], p.get("size") or strength_of(p["name"])
    if not strength:
        session["last_scan"], session["pending"] = None, None
        return say(f"I read {drug}, but I couldn't read the strength. Please read me the strength on the label, "
                   "or ask the pharmacist.", drug, "pharmacist")
    p["size"] = strength
    session["last_scan"] = scan
    session["pending"] = {"scope": "confirm_rx"}
    return say(f"I read {drug}, {strength}. Is that right?", drug, strength)


def _rx_after_confirm(session: dict) -> Facts:
    if not session.get("insurance"):
        session["pending"] = {"scope": "ask_plan"}
        return say("Do you know which insurance plan you have? You can show me your insurance card, "
                   "or tell me the plan.", "insurance")
    return _rx_coverage(session)


def _forget_drug(session: dict) -> None:
    """Drug name and strength are used for one answer, then dropped (privacy rule)."""
    session["last_scan"], session["pending"] = None, None


def _rx_coverage(session: dict) -> Facts:
    scan = session["last_scan"]
    p = scan["product"]
    facts, copay = coverage(session.get("insurance"), p["name"], p.get("size"))
    if copay is None:
        _forget_drug(session)
        return facts

    # Offer only the estimated copay, never the full price; keep no drug name.
    p["name"], p["size"], p["brand"] = "your prescription", None, None
    p["product_key"], p["upc"] = "prescription", None
    p["amount_cents"] = copay
    scan["amount_basis"] = "remaining_after_copay"
    hsa, visa = _health_card(session), _general_card(session)
    options = [c["id"] for c in (hsa, visa) if c]
    if hsa and hsa["balance_cents"] >= copay:
        session["pending"] = {"scope": "choose_card", "card_options": options, "overrode": False, "suggested": hsa["id"]}
        return say(f"{facts.template} {COPAY_HSA} Want to use your {hsa['nickname']}?",
                   *facts.must_say, COPAY_HSA, hsa["nickname"])
    if visa:
        session["pending"] = {"scope": "choose_card", "card_options": options, "overrode": bool(hsa), "suggested": visa["id"]}
        extra = f" Your {hsa['nickname']} can't cover it. Please use another card." if hsa else ""
        out = say(f"{facts.template}{extra} Want to put it on your {visa['nickname']}?",
                  *facts.must_say, visa["nickname"], *(["another card"] if hsa else []))
        return _with_alert(out, hsa) if hsa else out
    _forget_drug(session)
    return say(f"{facts.template} None of your linked cards can cover it. Please use another card.",
               *facts.must_say, "another card")


def _set_plan(session: dict, plan_id: str | None) -> None:
    if plan_id and plan_id != "unknown":
        session["insurance"] = plan_profile(plan_id, source="spoken")


def _resolve_pending(session: dict, intent: Intent) -> Facts | None:
    """Apply confirm / deny / choose_card to the pending question. None if nothing applied."""
    pending = session.get("pending")
    if not pending:
        return None
    scope, name = pending["scope"], intent.intent
    yes, no = name == "confirm", name in ("deny", "skip")

    if scope == "confirm_rx":
        if yes:
            session["last_scan"]["rx_confirmed"] = True
            return _rx_after_confirm(session)
        if no:
            _forget_drug(session)
            return say("Okay. Please read me the drug name and strength from the label, or ask the pharmacist.",
                       "pharmacist")
    elif scope == "ask_plan":
        if name == "choose_plan":
            _set_plan(session, intent.entities.plan)
            return _rx_coverage(session)
        if no:
            return _rx_coverage(session)

    if scope == "confirm_add":
        if name == "add_to_cart" and intent.entities.card:
            return None  # user named a card: let the explicit-card rules decide
        if yes or name == "add_to_cart":
            return _add_to_cart(session, session["last_scan"], pending["card_id"])
        if no:
            session["pending"], session["last_scan"] = None, None
            return say("Okay, skipped.", "skipped")
    elif scope == "choose_card":
        if no:
            session["pending"], session["last_scan"] = None, None
            return say("Okay, skipped.", "skipped")
        card = _card_by_type(session, intent.entities.card)
        if card is None and yes and pending.get("suggested"):
            card = _card(session, pending["suggested"])
        if card is None and yes and len(pending["card_options"]) == 1:
            card = _card(session, pending["card_options"][0])
        if card and card["id"] in pending["card_options"]:
            return _add_to_cart(session, session["last_scan"], card["id"], overrode=pending["overrode"])
        nicks = [_card(session, c)["nickname"] for c in pending["card_options"]]
        return say(f"Which card: {' or '.join(nicks)}?", *nicks)
    elif scope == "confirm_checkout":
        if yes:
            return _checkout_confirm(session)
        if no:
            session["pending"] = None
            return say("Okay, checkout cancelled.", "cancelled")
    elif scope == "confirm_reroute":
        if yes:
            for item in session["cart"]:
                if item["id"] in pending["move_ids"]:
                    item["assigned_card_id"], item["user_overrode_card"] = pending["to_card"], True
            session["pending"] = None
            preview = _checkout_preview(session)
            return say("Done. " + preview.template, *preview.must_say)
        if no:
            session["pending"] = None
            return say("Okay. Your cart is unchanged.", "unchanged")
    elif scope == "confirm_clear":
        if yes:
            session["cart"], session["pending"] = [], None
            return say("Cart cleared.", "cleared")
        session["pending"] = None
        return say("Okay, your cart is unchanged.", "unchanged")
    return None


def handle_intent(intent: Intent, session: dict) -> tuple[Facts, dict]:
    """Pure handler: (facts, updated session). Never mutates the input."""
    session = copy.deepcopy(session)
    name, ent = intent.intent, intent.entities

    if name in REFUSALS:
        if name == "route_ineligible_to_hsa" and session.get("last_scan"):
            visa = _general_card(session)
            if visa:
                session["pending"] = {"scope": "confirm_add", "card_id": visa["id"]}
        return say(REFUSALS[name], fixed=True), session

    applied = _resolve_pending(session, intent)
    if applied is not None:
        return applied, session

    if name == "clear_cart":
        if not session["cart"]:
            return say("Your cart is already empty.", "empty"), session
        session["pending"] = {"scope": "confirm_clear"}
        return say("Clear everything from your cart?", "cart"), session
    if name == "remove_last":
        if not session["cart"]:
            return say("Your cart is empty.", "empty"), session
        removed = session["cart"].pop()
        summary = _cart_summary(session)
        return say(f"Removed {removed['display_name']}. " + summary.template, removed["display_name"], *summary.must_say), session
    if name == "choose_plan":
        if intent.entities.plan in (None, "unknown"):
            return say("That's okay. You can show me your insurance card any time, or tell me your plan."), session
        _set_plan(session, intent.entities.plan)
        plan = describe_plan(session["insurance"])
        return say("Okay. " + plan.template, *plan.must_say), session
    if name == "insurance_question":
        return describe_plan(session.get("insurance")), session
    if name == "cart_query":
        return _cart_summary(session), session
    if name == "balance_query":
        return _balances(session), session
    if name == "checkout":
        return _checkout_preview(session), session
    if name == "skip" and session.get("last_scan"):
        session["last_scan"] = None
        return say("Okay, skipped.", "skipped"), session

    scan = session.get("last_scan")
    if name == "give_price" and scan and scan["product"].get("amount_cents") is not None:
        # A spoken price only fills a missing price; it never replaces the shelf tag.
        price = dollars(scan["product"]["amount_cents"])
        return say(f"The shelf tag says {price} for {scan['product']['name']}. I'll keep that price.",
                   price, scan["product"]["name"]), session
    if name == "give_price" and scan and ent.price_dollars is not None:
        cents = round(ent.price_dollars * 100)
        if not 1 <= cents <= 50000:
            return say("That price doesn't look right. Please say it again."), session
        scan["product"]["amount_cents"], scan["product"]["price_source"] = cents, "user_spoken"
        scan["product"]["state"] = scan["state"] = "resolved"
        return _speak_recommendation(session, scan, _route(session, scan)), session

    if name == "add_to_cart" and scan:
        pname = scan["product"]["name"]
        if scan["product"].get("amount_cents") is None:
            return say(f"I don't have a price for {pname} yet. What does the shelf tag say?", pname), session
        label = scan["eligibility"]["label"]
        chosen = _card_by_type(session, ent.card)
        if chosen and chosen["type"] in ("hsa", "fsa") and label == "not_eligible":
            return say(REFUSALS["route_ineligible_to_hsa"], fixed=True), session
        if chosen and chosen["type"] in ("hsa", "fsa") and chosen["balance_cents"] < scan["product"]["amount_cents"]:
            return _speak_recommendation(session, scan, _route(session, scan)), session
        if chosen:
            overrode = (chosen["type"] == "general" and label == "eligible") or label == "could_not_confirm"
            return _add_to_cart(session, scan, chosen["id"], overrode=overrode), session
        rec = _route(session, scan)
        if rec["decision"] in ("route_to_hsa", "route_to_general"):
            return _add_to_cart(session, scan, rec["card_id"]), session
        return _speak_recommendation(session, scan, rec), session

    return HELP, session


def recommend(session: dict, scan: dict) -> tuple[Facts, dict]:
    """Called right after a scan resolves."""
    session = copy.deepcopy(session)
    if scan["product"].get("is_prescription_only"):
        return _rx_start(session, scan), session
    session["last_scan"] = scan
    pname = scan["product"]["name"]
    if scan["product"].get("amount_cents") is None:
        session["pending"] = None
        return say(f"I see {pname} but could not read a price. Tell me the shelf price and I'll add it to your cart.",
                   pname), session
    facts = _speak_recommendation(session, scan, _route(session, scan))
    if scan["product"].get("is_medication") and also_sold_by_prescription(pname):
        line = ("If your doctor prescribed this, the pharmacy counter version may cost less through your plan. "
                "Ask the pharmacist.")
        facts = say(f"{facts.template} {line}", *facts.must_say, alert=facts.alert)
    return facts, session


@payment_protocol.on_message(PaymentRequest, replies=PaymentResponse)
async def on_request(ctx: Context, sender: str, msg: PaymentRequest):
    if sender != ORCHESTRATOR_AGENT_ADDRESS:
        ctx.logger.warning("ignoring PaymentRequest from unknown sender %s", sender)
        return
    try:
        before = await asyncio.to_thread(store.load, msg.session)
    except DBUnavailable as exc:
        ctx.logger.warning("cards unavailable: %s", exc)
        await ctx.send(sender, PaymentResponse(request_id=msg.request_id, facts=FactsMsg.of(store.DB_DOWN),
                                               session=msg.session))
        return
    if msg.scan:
        facts, session = recommend(before, msg.scan)
    elif msg.intent:
        facts, session = handle_intent(Intent.model_validate(msg.intent), before)
    else:
        facts, session = HELP, before
    failed = await asyncio.to_thread(store.save, before, session, msg.request_id)
    if failed:
        facts, session = failed, before
    session = store.strip(session)
    await ctx.send(sender, PaymentResponse(request_id=msg.request_id, facts=FactsMsg.of(facts), session=session))


def build_agent(mailbox: bool = True, port: int = 8002) -> Agent:
    agent = Agent(
        name="Rewind Payment Agent",
        seed=PAYMENT_SEED,
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        description="Routes each item to the right card (HSA/FSA or general), manages the cart, and runs a simulated checkout.",
    )
    agent.include(payment_protocol, publish_manifest=True)
    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
