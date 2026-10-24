"""Card routing (technical spec 3.5). Pure functions: no I/O, no network, no database.

route_item()     decides which card one scanned item goes on.
plan_checkout()  applies the three group rules to the whole cart at checkout.

Money is integer cents. Eligibility comes from Tiea's classifier as a label; this module only
acts on the label. Two rules are never relaxed:
  * an item that is not confirmed eligible never goes on an HSA/FSA card, and
  * the insurer's share of a prescription is never routed to an HSA/FSA.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictInt

from models.schemas import PaymentRecommendation, Reroute

HEALTH_TYPES = ("hsa", "fsa")
LABELS = ("eligible", "not_eligible", "could_not_confirm")


class Card(BaseModel):
    """The slice of a cards row that routing needs. Extra columns (nessie_account_id) are ignored."""
    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["hsa", "fsa", "general"]
    nickname: str = ""
    balance_cents: StrictInt
    status: Literal["active", "frozen", "closed", "expired"] = "active"
    is_default: bool = False


def _cards(cards: list[Card | dict[str, Any]]) -> list[Card]:
    return [c if isinstance(c, Card) else Card(**c) for c in cards]


def _money(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer number of cents, got {value!r}")
    return value


def _default(cards: list[Card]) -> Card | None:
    """The card flagged default, else the first one, else None."""
    if not cards:
        return None
    return next((c for c in cards if c.is_default), cards[0])


def _default_general(active: list[Card]) -> Card | None:
    return _default([c for c in active if c.type == "general"])


# --- one item ---------------------------------------------------------------------------------

def route_item(
    eligibility_label: str,
    amount_cents: int,
    amount_basis: Literal["shelf_price", "remaining_after_copay"],
    cards: list[Card | dict[str, Any]],
    copay_confirmed: bool = False,
    *,
    scan_id: str = "",
) -> PaymentRecommendation:
    """Decide the card for one item (spec 3.5, steps 0 to 5).

    `copay_confirmed` stays False until the team picks a certified source for copay payments
    (business spec open item 4), so a medication with a copay always asks the user.
    Zero copay is expressed as amount_basis="remaining_after_copay" with amount_cents=0.
    """
    if eligibility_label not in LABELS:
        raise ValueError(f"unknown eligibility label {eligibility_label!r}")
    if amount_basis not in ("shelf_price", "remaining_after_copay"):
        raise ValueError(f"unknown amount basis {amount_basis!r}")
    _money(amount_cents, "amount_cents")
    if amount_cents < 0 or (amount_basis == "shelf_price" and amount_cents == 0):
        raise ValueError(f"amount_cents out of range for {amount_basis}: {amount_cents}")

    cards = _cards(cards)
    active = [c for c in cards if c.status == "active"]

    def rec(decision, reason_code, card=None, options=(), reroute=None, before=None, after=None):
        return PaymentRecommendation(
            scan_id=scan_id,
            decision=decision,
            card_id=card.id if card else None,
            amount_cents=amount_cents,
            amount_basis=amount_basis,
            balance_before_cents=before,
            balance_after_cents=after,
            reroute=reroute,
            requires_confirmation=True,           # always true: nothing is added unconfirmed
            reason_code=reason_code,
            card_options=list(options),
        )

    # STEP 0: insurance copay. Nothing due means nothing to route, whatever cards exist.
    if amount_basis == "remaining_after_copay" and amount_cents == 0:
        return rec("blocked", "zero_copay_nothing_due")

    # STEP 1: no usable card. A frozen, closed or expired card counts as not linked (spec 20.6).
    # Checked before the copay gate: asking "which card?" with no cards would be meaningless.
    if not active:
        return rec("blocked", "no_card_linked")

    # STEP 0 (cont.): a copay remainder is never sent to an HSA/FSA until a certified source says so.
    if amount_basis == "remaining_after_copay" and not copay_confirmed:
        return rec("ask_user", "copay_unconfirmed", options=[c.id for c in active])

    # STEP 2: could not confirm. Never auto-route to an HSA/FSA.
    if eligibility_label == "could_not_confirm":
        return rec("ask_user", "eligibility_unconfirmed", options=[c.id for c in active])

    general = _default_general(active)

    # STEP 3: not eligible. The general card, never an HSA/FSA, even if the user asks.
    if eligibility_label == "not_eligible":
        if general is None:
            return rec("blocked", "no_card_covers")
        return rec("route_to_general", "not_eligible", card=general,
                   before=general.balance_cents, after=general.balance_cents - amount_cents)

    # STEP 4: eligible.
    health = [c for c in active if c.type in HEALTH_TYPES]
    if not health:
        if general is None:
            return rec("blocked", "no_card_covers")
        return rec("route_to_general", "no_health_card_linked", card=general,
                   before=general.balance_cents, after=general.balance_cents - amount_cents)

    defaults = [c for c in health if c.is_default]
    if len(health) > 1 and not defaults:
        return rec("ask_user", "multiple_health_cards", options=[c.id for c in health])
    hsa = defaults[0] if defaults else health[0]

    if hsa.balance_cents >= amount_cents:         # equal counts as sufficient
        return rec("route_to_hsa", "eligible_sufficient_balance", card=hsa,
                   before=hsa.balance_cents, after=hsa.balance_cents - amount_cents)

    # balance too low, including zero or negative
    if general is not None and general.balance_cents >= amount_cents:
        return rec("ask_user", "eligible_insufficient_balance", options=[general.id],
                   reroute=Reroute(from_card_id=hsa.id, to_card_id=general.id, reason="insufficient_balance"),
                   before=hsa.balance_cents)

    # STEP 5: nothing covers it.
    return rec("blocked", "no_card_covers", before=hsa.balance_cents)


# --- the whole cart (spec 3.5, "Group rules at checkout") ------------------------------------

class CheckoutGroup(BaseModel):
    card_id: str
    nickname: str
    item_ids: list[str]
    subtotal_cents: int


class Move(BaseModel):
    item_id: str
    display_name: str
    amount_cents: int
    from_card_id: str
    to_card_id: str
    # "insufficient_balance": the item alone exceeds the card's balance (rule 1)
    # "group_exceeds_balance": each item fits but the group does not (rule 2)
    reason: Literal["insufficient_balance", "group_exceeds_balance"]


class CheckoutIssue(BaseModel):
    rule: Literal[1, 2, 3]
    card_id: str
    balance_cents: int
    group_total_cents: int
    keep_item_ids: list[str]              # items that stay on this card
    moves: list[Move]                     # rules 1 and 2: proposed, never applied without a yes
    uncovered_item_ids: list[str]         # rule 3: no card can pay these


class CheckoutPlan(BaseModel):
    groups: list[CheckoutGroup]           # the current assignments, before any proposed move
    total_cents: int                      # before tax
    issues: list[CheckoutIssue]
    ok: bool                              # True when there is nothing to ask


def plan_checkout(items: list[dict[str, Any]], cards: list[Card | dict[str, Any]]) -> CheckoutPlan:
    """Check every card's group against its balance and propose fixes.

    items: cart rows with id, display_name, amount_cents, assigned_card_id, eligibility_label.
    Nothing is changed: moves are proposals the user must confirm (see apply_moves).

    Within an over-limit card, items are kept largest first while they fit, then smaller items
    that still fit are kept too (first-fit decreasing), so as little as possible moves. Ties keep
    cart order. Moved items go to the default general card; an eligible item may also go to the
    default health card. A card that is itself over its limit is never a destination, and an
    item that is not confirmed eligible is never moved to an HSA/FSA.
    """
    cards = _cards(cards)
    by_id = {c.id: c for c in cards}
    for item in items:
        _money(item["amount_cents"], "amount_cents")
        if item["assigned_card_id"] not in by_id:
            raise ValueError(f"item {item['id']!r} is assigned to unknown card {item['assigned_card_id']!r}")

    balance = {c.id: (c.balance_cents if c.status == "active" else 0) for c in cards}   # unusable = 0
    assigned: dict[str, list[dict]] = {c.id: [] for c in cards}
    for item in items:
        assigned[item["assigned_card_id"]].append(item)
    committed = {cid: sum(i["amount_cents"] for i in group) for cid, group in assigned.items()}

    groups = [CheckoutGroup(card_id=c.id, nickname=c.nickname, item_ids=[i["id"] for i in assigned[c.id]],
                            subtotal_cents=committed[c.id])
              for c in cards if assigned[c.id]]
    over = [c for c in cards if committed[c.id] > balance[c.id]]
    over_ids = {c.id for c in over}

    usable = [c for c in cards if c.status == "active" and c.id not in over_ids]
    general = _default([c for c in usable if c.type == "general"])
    health = _default([c for c in usable if c.type in HEALTH_TYPES])

    def destinations(item: dict, source_id: str) -> list[Card]:
        found = [general] if general else []
        if health and item["eligibility_label"] == "eligible":
            found.append(health)
        return [c for c in found if c.id != source_id]

    issues: list[CheckoutIssue] = []
    for card in over:
        ordered = sorted(enumerate(assigned[card.id]), key=lambda p: (-p[1]["amount_cents"], p[0]))
        room, keep, moves, uncovered = balance[card.id], [], [], []
        for _, item in ordered:
            amount = item["amount_cents"]
            if amount <= room:
                keep.append(item)
                room -= amount
                continue
            target = next((d for d in destinations(item, card.id)
                           if balance[d.id] - committed[d.id] >= amount), None)
            if target is None:
                uncovered.append(item)
                continue
            committed[target.id] += amount
            moves.append(Move(item_id=item["id"], display_name=item["display_name"], amount_cents=amount,
                              from_card_id=card.id, to_card_id=target.id,
                              reason="insufficient_balance" if amount > balance[card.id] else "group_exceeds_balance"))
        if moves:
            rule = 1 if all(m.reason == "insufficient_balance" for m in moves) else 2
            issues.append(CheckoutIssue(rule=rule, card_id=card.id, balance_cents=balance[card.id],
                                        group_total_cents=sum(i["amount_cents"] for i in assigned[card.id]),
                                        keep_item_ids=[i["id"] for i in keep], moves=moves, uncovered_item_ids=[]))
        if uncovered:
            issues.append(CheckoutIssue(rule=3, card_id=card.id, balance_cents=balance[card.id],
                                        group_total_cents=sum(i["amount_cents"] for i in assigned[card.id]),
                                        keep_item_ids=[i["id"] for i in keep], moves=[],
                                        uncovered_item_ids=[i["id"] for i in uncovered]))

    return CheckoutPlan(groups=groups, total_cents=sum(i["amount_cents"] for i in items),
                        issues=issues, ok=not issues)


def apply_moves(items: list[dict[str, Any]], moves: list[Move]) -> list[dict[str, Any]]:
    """Return a copy of the cart with the confirmed moves applied. Call only after a voice yes."""
    target = {m.item_id: m.to_card_id for m in moves}
    return [dict(i, assigned_card_id=target.get(i["id"], i["assigned_card_id"])) for i in items]
