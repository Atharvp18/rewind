"""History: answers questions about past purchases. Read-only; it never moves money.

Claude turns the question into a small fixed form (HistoryQuery). Code does everything else:
resolves the dates, filters the purchases, adds up the amounts, and builds the fact sheet.
Claude never picks a date or a number. Moss helps only to find items by description
("cold medicine") in the purchases already filtered by date and card.

Purchases come from Atharv's purchase_items table (data/db.get_purchases). A prescription is
stored as "your prescription", so History can total it but never says which medicine.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from pydantic import BaseModel, Field

from agents.common import dollars
from agents.speaker import Facts, say

logger = logging.getLogger(__name__)

MODEL = os.environ.get("INTENT_MODEL", "claude-haiku-5-5")
TIMEOUT_S = float(os.environ.get("INTENT_TIMEOUT_S", "10.0"))
STUB_HISTORY = os.environ.get("REWIND_STUB_HISTORY", "false").lower() == "true"
CLAIM_EXAMPLES = "Optum Financial or HealthEquity"

Period = Literal["last_7_days", "this_month", "last_month", "last_30_days", "this_year", "all_time"]


class HistoryQuery(BaseModel):
    kind: Literal["total", "count", "list", "reimbursable"] = Field(
        description="total: how much was spent; count: how many items; list: what was bought; "
                    "reimbursable: eligible items paid with the Visa that could be claimed back")
    period: Period = Field("all_time", description="The time range the user asked about")
    card: Literal["hsa", "fsa", "visa"] | None = Field(None, description="Only purchases on this card")
    medicine_only: bool = Field(False, description="True if they ask about medicine, medication or pills")
    category: Literal["pain_relief", "cold_flu_allergy", "digestive_health", "first_aid", "otc_medicine",
                      "menstrual_care", "eye_care", "foot_care", "vitamins_supplements", "personal_care",
                      "grocery"] | None = Field(None, description="A category they named, e.g. allergy stuff")
    item: str | None = Field(None, description="A specific item or product they describe, in their words, "
                                              "e.g. 'the cold medicine' or 'Tylenol'. Leave empty for all items.")


SYSTEM_PROMPT = """\
You turn a shopper's question about their past purchases into a form. The shopper uses Rewind, \
a shopping assistant for elderly and low-vision people who pay with an HSA card, an FSA card, \
or a Visa credit card. Do not answer the question. Do not invent dates.

kind:
- total: how much they spent
- count: how many items they bought
- list: what they bought, or what they bought most recently
- reimbursable: items that were HSA/FSA eligible but paid with the Visa, so the money could be \
claimed back from the HSA or FSA

period: last_7_days (for "this week" or "last week"), this_month, last_month, last_30_days, this_year, \
or all_time when they name no time.
card: hsa, fsa, or visa only if they name one.
medicine_only: true when they say medicine, medication, pills or "pharmacy stuff".
category: only when they name a kind: pain, allergy/cold/flu, stomach/digestive, bandages/first aid, etc.
Prefer category for a KIND of thing: heartburn, stomach, antacid -> digestive_health; headache, pain, \
fever -> pain_relief; allergy, cold, flu, sinus -> cold_flu_allergy; bandages, cuts -> first_aid.
item: only a specific product or brand NAME they say ("Tylenol", "the Allegra"). "Some medicine" alone is \
medicine_only, not an item.

Examples:
- "I bought some medicine last month and forgot what it was" -> kind list, period last_month, medicine_only true
- "how much did I spend on my FSA this month" -> kind total, period this_month, card fsa
- "what could I claim back" -> kind reimbursable"""

NOT_UNDERSTOOD = say("I didn't catch what you want to know about your purchases. "
                     "You can ask how much you spent, what you bought, or what you could claim back.", fixed=True)
UNAVAILABLE = say("I can't reach your purchase history right now. Please try again in a moment.", fixed=True)
ITEM_SEARCH_DOWN = say("I can't search by item right now, but I can still tell you totals. "
                       "Ask how much you spent this month.", fixed=True)

PERIOD_WORDS = {"last_7_days": "in the last 7 days", "this_month": "this month", "last_month": "last month",
                "last_30_days": "in the last 30 days", "this_year": "this year", "all_time": ""}
CARD_TYPE = {"hsa": "hsa", "fsa": "fsa", "visa": "general"}
CARD_WORDS = {"hsa": "on your HSA card", "fsa": "on your FSA card", "visa": "on your Visa"}


# --- dates: resolved in code, in UTC -----------------------------------------------

def period_bounds(period: str, now: datetime) -> tuple[str | None, str | None]:
    """(since, until) as ISO timestamps; until is exclusive. None means open-ended."""
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "this_month":
        return first_of_month.isoformat(), None
    if period == "last_month":
        last_month_end = first_of_month
        last_month_start = (first_of_month - timedelta(days=1)).replace(day=1)
        return last_month_start.isoformat(), last_month_end.isoformat()
    if period == "last_7_days":
        return (now - timedelta(days=7)).isoformat(), None
    if period == "last_30_days":
        return (now - timedelta(days=30)).isoformat(), None
    if period == "this_year":
        return first_of_month.replace(month=1).isoformat(), None
    return None, None


# --- understanding: Claude fills the form -----------------------------------------------

_client = None


async def parse_question(question: str) -> HistoryQuery | None:
    """Claude Haiku, fixed output form. None on timeout, error or stub mode."""
    if os.environ.get("REWIND_STUB_INTENT", "false").lower() == "true":
        return None
    global _client
    try:
        if _client is None:
            import anthropic
            _client = anthropic.AsyncAnthropic()
        response = await asyncio.wait_for(_client.messages.parse(
            model=MODEL, max_tokens=256, output_config={"effort": "low"}, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"User asked: {question!r}"}],
            output_format=HistoryQuery), TIMEOUT_S)
        return None if response.stop_reason == "refusal" else response.parsed_output
    except Exception as exc:
        logger.warning("history question not parsed: %s", exc)
        return None


# --- recalling purchases: Moss memory first, the purchase table as the fallback ---------------

def _passes(row: dict, q: HistoryQuery) -> bool:
    return (not q.medicine_only or row.get("is_medication")) and (not q.category or row.get("category") == q.category)


async def _recall(q: HistoryQuery, since, until, card_type, fetch) -> list[dict] | None:
    """Matching purchases, newest first. None only when an item description needs Moss and Moss is down."""
    if not STUB_HISTORY:
        try:
            from lookup import purchase_memory
            return await purchase_memory.recall(since, until, card_type, q.medicine_only, q.category, q.item)
        except Exception as exc:        # Moss down, or the memory does not exist yet
            logger.warning("Moss memory unavailable, using the purchase table: %s", exc)
    if q.item and not STUB_HISTORY:
        return None                     # finding an item by description needs Moss
    rows = await asyncio.to_thread(fetch or (_fetch_stub if STUB_HISTORY else _fetch_db), since, until, card_type)
    rows = [r for r in rows if _passes(r, q)]
    if q.item:                          # stub mode only: a plain substring stands in for Moss
        rows = [r for r in rows if q.item.lower() in r["display_name"].lower()]
    return rows


# --- the answer: plain code ---------------------------------------------------------------

def _suffix(query: HistoryQuery) -> str:
    parts = []
    if query.item:
        parts.append(f"matching {query.item}")
    if query.card:
        parts.append(CARD_WORDS[query.card])
    if PERIOD_WORDS[query.period]:
        parts.append(PERIOD_WORDS[query.period])
    return (" " + " ".join(parts)) if parts else ""


def _items(n: int) -> str:
    return "1 item" if n == 1 else f"{n} items"


def _date(iso: str) -> str:
    d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return f"{d:%B} {d.day}"


def _lead(query: HistoryQuery) -> str:
    when = {"last_7_days": "In the last 7 days", "this_month": "This month", "last_month": "Last month", "last_30_days": "In the last 30 days",
            "this_year": "This year"}.get(query.period)
    return f"{when}, you bought" if when else "You bought"


def summarize(query: HistoryQuery, purchases: list[dict]) -> Facts:
    """Fact sheet from the purchases. Every number and date here is computed, never read from Claude."""
    where = _suffix(query)
    if query.kind == "reimbursable":
        owed = [p for p in purchases if p["card_type"] == "general" and p["eligibility_label"] == "eligible"]
        if not owed:
            return say(f"I don't see any HSA-eligible items that you paid for with your Visa{where}.", "Visa")
        total = dollars(sum(p["amount_cents"] for p in owed))
        names = " and ".join(p["display_name"] for p in owed[:3]) + (f", and {len(owed) - 3} more" if len(owed) > 3 else "")
        return say(f"You paid {total} with your Visa for {_items(len(owed))} that {'is' if len(owed) == 1 else 'are'} HSA eligible: {names}. "
                   f"You can file a claim with your HSA or FSA provider to pay yourself back, for example through "
                   f"{CLAIM_EXAMPLES}. Keep your receipts.",
                   total, names, "file a claim", CLAIM_EXAMPLES, "receipts", fixed=True)   # code wrote every word
    if not purchases:
        what = "medicine" if query.medicine_only and not query.item else "purchases"
        return say(f"I don't see any {what}{where}.", f"don't see any {what}")
    total = dollars(sum(p["amount_cents"] for p in purchases))
    if query.kind == "total":
        return say(f"You spent {total} on {_items(len(purchases))}{where}.", total)
    if query.kind == "count":
        return say(f"You bought {_items(len(purchases))}{where}, for {total} in all.", total)
    shown = purchases[:5]                                   # newest first
    parts = [f"{p['display_name']} on {_date(p['purchased_at'])}, for {dollars(p['amount_cents'])}" for p in shown]
    listing = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f", and {parts[-1]}"
    more = f" And {len(purchases) - 5} more." if len(purchases) > 5 else ""
    return say(f"{_lead(query)} {listing}.{more}",
               *[p["display_name"] for p in shown], *[dollars(p["amount_cents"]) for p in shown],
               *[_date(p["purchased_at"]) for p in shown])


# --- stub data for rehearsing before the purchase_items table exists ----------------------

def _stub_rows(now: datetime) -> list[dict]:
    def row(i, days, name, cents, card, label, cat, med, overrode=False):
        return {"id": f"stub{i}", "purchased_at": (now - timedelta(days=days)).isoformat(),
                "display_name": name, "amount_cents": cents, "card_type": card,
                "eligibility_label": label, "user_overrode_card": overrode, "category": cat, "is_medication": med}
    return [row(1, 1, "Tylenol Extra Strength", 1599, "fsa", "eligible", "pain_relief", True),
            row(2, 3, "Allegra 24 Hour Allergy Relief", 4299, "general", "eligible", "cold_flu_allergy", True, True),
            row(3, 4, "Tums Ultra Strength", 999, "hsa", "eligible", "digestive_health", True),
            row(4, 40, "Kettle Corn", 499, "general", "not_eligible", "grocery", False),
            row(5, 41, "Band-Aid Adhesive Bandages", 1299, "general", "eligible", "first_aid", False, True),
            row(6, 45, "Benadryl Ultra Allergy Relief", 1799, "fsa", "eligible", "cold_flu_allergy", True)]


def _fetch_stub(since, until, card_type) -> list[dict]:
    rows = _stub_rows(datetime.now(timezone.utc))
    return [r for r in rows if (not since or r["purchased_at"] >= since) and (not until or r["purchased_at"] < until)
            and (not card_type or r["card_type"] == card_type)]


def _fetch_db(since, until, card_type) -> list[dict]:
    from data import db
    return db.get_purchases(since, until, card_type)


async def answer(question: str, fetch: Callable | None = None, now: datetime | None = None,
                 parse: Callable | None = None) -> Facts:
    """The whole flow: question -> form -> purchases -> facts."""
    query = await (parse or parse_question)(question)
    if query is None:
        return NOT_UNDERSTOOD
    since, until = period_bounds(query.period, now or datetime.now(timezone.utc))
    # "claim back from my HSA" names the account to claim FROM; the items were paid on the Visa.
    card_type = None if query.kind == "reimbursable" else CARD_TYPE.get(query.card)
    try:
        rows = await _recall(query, since, until, card_type, fetch)
    except Exception as exc:        # database down, or the purchase_items table does not exist yet
        logger.warning("purchase history unavailable: %s", exc)
        return UNAVAILABLE
    if rows is None:
        return ITEM_SEARCH_DOWN
    return summarize(query, rows)
