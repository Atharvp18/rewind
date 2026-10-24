"""Moss memory of purchases, for the History agent.

Each purchased item (over-the-counter only) is one entry: a sentence for fuzzy recall ("that cold
medicine") plus fields for exact filtering (date, card, medicine or not, category). Supabase's
purchase_items table is the source of truth; checkout copies its rows here, and rebuild() can
recreate the whole memory from the table. Writing here is best-effort: it never fails a checkout.

recall() returns every entry that passes the filters (checked on a test index: filters on dates,
card, amounts and flags were exact, and recall was complete). A similarity floor applies only
when the user describes an item.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

logger = logging.getLogger(__name__)

INDEX_NAME = "rewind-purchases"
ITEM_MIN_SCORE = 0.50      # only for an item named by the user. Live check: names scored 0.70-0.87 and noise
                           # up to 0.44. Concepts ("heartburn") score poorly, so Claude maps those to a category.
REFRESH_S = 5              # how often the loaded memory picks up purchases made in another process
TOP_K = 500
TIMEOUT_S = 8.0

_reader = None
_loaded = False

# A reset cannot delete the index: a History agent that already loaded it would keep showing the old
# purchases until the next checkout recreates it (checked live). Instead the memory is replaced by one
# marker entry, which running agents pick up in about 2 s, and recall() never returns it.
MARKER_ID = "reset-marker"
_MARKER = {"id": MARKER_ID, "purchased_at": "1970-01-01T00:00:00+00:00", "display_name": "(reset marker)",
           "amount_cents": 0, "card_type": "none", "eligibility_label": "marker", "category": None,
           "is_medication": False}


class MemoryUnavailable(Exception):
    """Moss is not configured or did not answer. History falls back to the purchase table."""


def _client():
    from agents import common  # noqa: F401  (loads backend/.env)
    if not os.environ.get("MOSS_PROJECT_ID"):
        raise MemoryUnavailable("MOSS_PROJECT_ID is not set")
    from moss import MossClient
    return MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])


def _sentence(row: dict) -> str:
    cents = row["amount_cents"]
    return f"{row['display_name']}, ${cents // 100}.{cents % 100:02d}, on your {row['card_type']} card"


def to_doc(row: dict):
    from moss import DocumentInfo
    return DocumentInfo(id=row["id"], text=_sentence(row), metadata={
        "purchased_at": str(row["purchased_at"]), "amount_cents": str(row["amount_cents"]),
        "card_type": row["card_type"], "eligibility_label": row["eligibility_label"],
        "user_overrode_card": "true" if row.get("user_overrode_card") else "false",
        "category": row.get("category") or "", "is_medication": "true" if row.get("is_medication") else "false",
        "name": row["display_name"]})


def from_doc(doc) -> dict:
    m = doc.metadata or {}
    return {"id": doc.id, "purchased_at": m.get("purchased_at", ""), "display_name": m.get("name", doc.text),
            "amount_cents": int(m.get("amount_cents") or 0), "card_type": m.get("card_type", ""),
            "eligibility_label": m.get("eligibility_label", ""),
            "user_overrode_card": m.get("user_overrode_card") == "true",
            "category": m.get("category") or None, "is_medication": m.get("is_medication") == "true"}


def _f(field: str, op: str, value) -> dict:
    return {"field": field, "condition": {op: value}}


def build_filter(since=None, until=None, card_type=None, medicine_only=False, category=None):
    conditions = []
    if since:
        conditions.append(_f("purchased_at", "$gte", since))
    if until:
        conditions.append(_f("purchased_at", "$lt", until))
    if card_type:
        conditions.append(_f("card_type", "$eq", card_type))
    if medicine_only:
        conditions.append(_f("is_medication", "$eq", "true"))
    if category:
        conditions.append(_f("category", "$eq", category))
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


async def warm_up() -> bool:
    """Load the memory into this process once (about 3 s), so questions are answered from memory.

    auto_refresh keeps it current: checkout writes from the payment agent's process, not this one.
    """
    global _reader, _loaded
    if _loaded:
        return True
    try:
        _reader = _reader or _client()
        await asyncio.wait_for(_reader.load_index(INDEX_NAME, auto_refresh=True,
                                                  polling_interval_in_seconds=REFRESH_S), TIMEOUT_S)
        _loaded = True
    except Exception as exc:        # no purchases yet (no index), or Moss is down
        logger.warning("purchase memory not loaded: %s", exc)
    return _loaded


async def remember(rows: list[dict]) -> int:
    """Add purchases to the memory, creating it on the first purchase."""
    if not rows:
        return 0
    client, docs = _client(), [to_doc(r) for r in rows]
    try:
        await asyncio.wait_for(client.add_docs(INDEX_NAME, docs), TIMEOUT_S)
    except Exception:   # most likely: the index does not exist yet
        await asyncio.wait_for(client.create_index(INDEX_NAME, docs), TIMEOUT_S)
    return len(docs)


async def rebuild(rows: list[dict]) -> int:
    """Recreate the whole memory from the purchase table's rows."""
    client = _client()
    try:
        await client.delete_index(INDEX_NAME)
    except Exception:
        pass
    if not rows:
        return 0
    await client.create_index(INDEX_NAME, [to_doc(r) for r in rows])
    return len(rows)


def _names_it(item: str, name: str) -> bool:
    """True if a word the user said (4+ letters, plural s ignored) appears in the item's name.

    Meaning-based search misses obvious words ("tissues" vs "Kleenex Facial Tissues"), so a plain
    match against the user's own words counts too. No word list: the words are the user's.
    """
    stems = [w.rstrip("s") for w in re.findall(r"[a-z0-9]+", item.lower()) if len(w.rstrip("s")) >= 4]
    low = name.lower()
    return any(s in low for s in stems)


async def clear() -> None:
    """Empty the memory for a demo reset (see MARKER_ID)."""
    await rebuild([_MARKER])


def clear_sync() -> None:
    """For worker threads and the reset script. Never raises."""
    try:
        asyncio.run(clear())
    except Exception as exc:
        logger.warning("purchase memory not cleared: %s", exc)


async def recall(since=None, until=None, card_type=None, medicine_only=False, category=None,
                 item: str | None = None) -> list[dict]:
    """Purchases that pass the filters, newest first. Raises MemoryUnavailable if Moss cannot answer."""
    from moss import QueryOptions
    if not await warm_up():
        raise MemoryUnavailable("purchase memory not loaded")
    try:
        result = await asyncio.wait_for(_reader.query(
            INDEX_NAME, item or "purchase",
            QueryOptions(filter=build_filter(since, until, card_type, medicine_only, category), top_k=TOP_K)),
            TIMEOUT_S)
    except Exception as exc:
        raise MemoryUnavailable(str(exc)) from exc
    docs = [d for d in result.docs if d.id != MARKER_ID]
    if item:     # keep what is close in meaning, or shares a word the user said
        docs = [d for d in docs if d.score >= ITEM_MIN_SCORE or _names_it(item, (d.metadata or {}).get("name", d.text))]
    return sorted((from_doc(d) for d in docs), key=lambda r: r["purchased_at"], reverse=True)


def remember_sync(rows: list[dict]) -> int:
    """For worker threads (agents/store.py). Never raises."""
    try:
        return asyncio.run(remember(rows))
    except Exception as exc:
        logger.warning("purchase memory not updated: %s", exc)
        return 0
