"""History: dates, answers, retrieval (Moss memory and table fallback), and the checkout mirror."""
import types
from datetime import datetime, timezone

import pytest

from agents import history
from agents.history import HistoryQuery
from lookup import purchase_memory

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)


def row(i, iso, name, cents, card="fsa", label="eligible", cat="pain_relief", med=True, overrode=False):
    return {"id": f"r{i}", "purchased_at": iso, "display_name": name, "amount_cents": cents, "card_type": card,
            "eligibility_label": label, "user_overrode_card": overrode, "category": cat, "is_medication": med}


ROWS = [
    row(1, "2026-10-23T10:00:00+00:00", "Tylenol Extra Strength", 1599),
    row(2, "2026-10-21T10:00:00+00:00", "Allegra 24 Hour", 4299, card="general", cat="cold_flu_allergy", overrode=True),
    row(3, "2026-09-14T10:00:00+00:00", "Kettle Corn", 499, card="general", label="not_eligible", cat="grocery", med=False),
    row(4, "2026-09-09T10:00:00+00:00", "Benadryl Ultra Allergy Relief", 1799, cat="cold_flu_allergy"),
]


def q(**kw):
    return HistoryQuery(**{"kind": "list", **kw})


# --- dates are resolved in code -----------------------------------------------------------

def test_period_bounds():
    assert history.period_bounds("this_month", NOW) == ("2026-10-01T00:00:00+00:00", None)
    assert history.period_bounds("last_month", NOW) == ("2026-09-01T00:00:00+00:00", "2026-10-01T00:00:00+00:00")
    assert history.period_bounds("this_year", NOW) == ("2026-01-01T00:00:00+00:00", None)
    assert history.period_bounds("last_30_days", NOW)[0] == "2026-09-24T15:00:00+00:00"
    assert history.period_bounds("last_7_days", NOW)[0] == "2026-10-17T15:00:00+00:00"
    assert history.period_bounds("all_time", NOW) == (None, None)


def test_last_month_in_january_is_december_of_the_year_before():
    jan = datetime(2027, 1, 15, tzinfo=timezone.utc)
    assert history.period_bounds("last_month", jan) == ("2026-12-01T00:00:00+00:00", "2027-01-01T00:00:00+00:00")


# --- answers: every number and date is computed ---------------------------------------------

def test_total_and_count():
    f = history.summarize(q(kind="total", period="this_month"), ROWS[:2])
    assert f.template == "You spent $58.98 on 2 items this month." and "$58.98" in f.must_say
    f = history.summarize(q(kind="count", card="fsa"), ROWS[:1])
    assert f.template == "You bought 1 item on your FSA card, for $15.99 in all."


def test_list_names_dates_and_amounts_newest_first():
    f = history.summarize(q(period="last_month", medicine_only=True), [ROWS[3]])
    assert f.template == "Last month, you bought Benadryl Ultra Allergy Relief on September 9, for $17.99."
    assert {"Benadryl Ultra Allergy Relief", "$17.99", "September 9"} <= set(f.must_say)


def test_list_more_than_five_says_how_many_more():
    many = [row(i, f"2026-10-{i:02d}T10:00:00+00:00", f"Item {i}", 100 + i) for i in range(1, 8)]
    f = history.summarize(q(), many)
    assert f.template.endswith("And 2 more.") and "Item 6" not in f.template


def test_nothing_found_is_said_plainly():
    assert history.summarize(q(medicine_only=True, period="last_month"), []).template == "I don't see any medicine last month."
    assert history.summarize(q(kind="total"), []).template == "I don't see any purchases."


def test_reimbursable_is_eligible_items_paid_on_the_visa_and_spoken_exactly():
    f = history.summarize(q(kind="reimbursable"), ROWS)
    assert "$42.99 with your Visa for 1 item that is HSA eligible" in f.template and "Allegra 24 Hour" in f.template
    assert "Kettle Corn" not in f.template                       # not eligible: nothing to claim
    assert "Optum Financial or HealthEquity" in f.template and f.fixed
    assert "I don't see" in history.summarize(q(kind="reimbursable"), ROWS[:1]).template


# --- the whole flow with the table fallback (Moss is off in the everyday tests) ---------------

async def ask(query, fetch=None, **kw):
    async def parse(question):
        return query
    return await history.answer("q", fetch=fetch or (lambda s, u, c: ROWS), now=NOW, parse=parse, **kw)


async def test_medicine_only_and_category_filters_apply_in_code():
    f = await ask(q(medicine_only=True))
    assert "Kettle Corn" not in f.template and "Tylenol" in f.template
    f = await ask(q(category="cold_flu_allergy"))
    assert "Allegra" in f.template and "Benadryl" in f.template and "Tylenol" not in f.template


async def test_dates_and_card_are_passed_to_the_fetch():
    seen = {}

    def fetch(since, until, card_type):
        seen.update(since=since, until=until, card=card_type)
        return []
    await ask(q(kind="total", period="last_month", card="visa"), fetch=fetch)
    assert seen == {"since": "2026-09-01T00:00:00+00:00", "until": "2026-10-01T00:00:00+00:00", "card": "general"}


async def test_claim_back_ignores_the_card_because_the_items_were_paid_on_the_visa():
    seen = {}

    def fetch(since, until, card_type):
        seen["card"] = card_type
        return ROWS
    f = await ask(q(kind="reimbursable", card="hsa"), fetch=fetch)       # "claim back from my HSA"
    assert seen["card"] is None and "Allegra 24 Hour" in f.template


async def test_not_understood_and_unreachable_are_said_not_guessed():
    async def parse(question):
        return None
    assert await history.answer("q", parse=parse) is history.NOT_UNDERSTOOD

    def boom(*a):
        raise RuntimeError("purchase_items does not exist yet")
    assert await ask(q(), fetch=boom) is history.UNAVAILABLE


async def test_describing_an_item_needs_moss_and_says_so_when_it_is_down():
    assert await ask(q(item="the cold medicine")) is history.ITEM_SEARCH_DOWN


async def test_moss_memory_is_used_first_with_the_filters(monkeypatch):
    seen = {}

    async def recall(since, until, card_type, medicine_only, category, item):
        seen.update(since=since, card=card_type, med=medicine_only, cat=category, item=item)
        return [ROWS[3]]
    monkeypatch.setattr(purchase_memory, "recall", recall)
    f = await ask(q(period="this_month", medicine_only=True, category="cold_flu_allergy", item="allergy pills"),
                  fetch=lambda *a: pytest.fail("the table must not be read when Moss answers"))
    assert seen == {"since": "2026-10-01T00:00:00+00:00", "card": None, "med": True,
                    "cat": "cold_flu_allergy", "item": "allergy pills"}
    assert "Benadryl" in f.template


# --- the Moss memory -----------------------------------------------------------------------------

def test_filters_combine_with_and_and_a_single_one_stands_alone():
    assert purchase_memory.build_filter() is None
    assert purchase_memory.build_filter(card_type="fsa") == {"field": "card_type", "condition": {"$eq": "fsa"}}
    f = purchase_memory.build_filter("2026-10-01", "2026-11-01", "general", True, "pain_relief")
    assert [c["field"] for c in f["$and"]] == ["purchased_at", "purchased_at", "card_type", "is_medication", "category"]
    assert f["$and"][3]["condition"] == {"$eq": "true"}


def test_a_purchase_survives_the_round_trip_through_a_moss_entry():
    doc = purchase_memory.to_doc(ROWS[1])
    assert doc.text == "Allegra 24 Hour, $42.99, on your general card"
    back = purchase_memory.from_doc(doc)
    assert back == {k: ROWS[1][k] for k in back}                 # same fields, same types


class FakeClient:
    def __init__(self, docs=(), add_fails=False):
        self.docs, self.add_fails, self.calls = list(docs), add_fails, []

    async def add_docs(self, name, docs):
        self.calls.append(("add_docs", name))
        if self.add_fails:
            raise RuntimeError("no such index")

    async def create_index(self, name, docs):
        self.calls.append(("create_index", name, len(docs)))

    async def delete_index(self, name):
        self.calls.append(("delete_index", name))

    async def load_index(self, name, **kw):
        self.calls.append(("load_index", name, kw))

    async def query(self, name, text, options):
        self.calls.append(("query", text, options.min_score, options.top_k))
        return types.SimpleNamespace(docs=self.docs)


async def test_the_first_purchase_creates_the_memory_and_later_ones_add_to_it(monkeypatch):
    fake = FakeClient(add_fails=True)
    monkeypatch.setattr(purchase_memory, "_client", lambda: fake)
    assert await purchase_memory.remember(ROWS[:2]) == 2
    assert [c[0] for c in fake.calls] == ["add_docs", "create_index"]
    fake2 = FakeClient()
    monkeypatch.setattr(purchase_memory, "_client", lambda: fake2)
    await purchase_memory.remember(ROWS[:1])
    assert [c[0] for c in fake2.calls] == ["add_docs"]


def scored(row, score):
    doc = purchase_memory.to_doc(row)
    return types.SimpleNamespace(id=doc.id, text=doc.text, metadata=doc.metadata, score=score)


async def test_recall_is_newest_first_and_never_returns_the_reset_marker(monkeypatch):
    docs = [scored(ROWS[3], 0.1), scored(ROWS[0], 0.1), scored(ROWS[1], 0.1),
            scored({**purchase_memory._MARKER}, 0.9)]
    fake = FakeClient(docs)
    monkeypatch.setattr(purchase_memory, "_client", lambda: fake)
    monkeypatch.setattr(purchase_memory, "_reader", None)
    monkeypatch.setattr(purchase_memory, "_loaded", False)
    got = await purchase_memory.recall(medicine_only=True)
    assert [r["id"] for r in got] == ["r1", "r2", "r4"]
    assert fake.calls[-1][1:] == ("purchase", None, purchase_memory.TOP_K)        # no floor: every match


async def test_a_described_item_matches_by_meaning_or_by_a_word_the_user_said(monkeypatch):
    tissues = row(9, "2026-10-24T10:00:00+00:00", "Kleenex Facial Tissues", 349, card="general", cat="personal_care", med=False)
    docs = [scored(ROWS[0], 0.20), scored(tissues, 0.30), scored(ROWS[1], 0.80)]     # Allegra close in meaning
    fake = FakeClient(docs)
    monkeypatch.setattr(purchase_memory, "_client", lambda: fake)
    monkeypatch.setattr(purchase_memory, "_reader", None)
    monkeypatch.setattr(purchase_memory, "_loaded", False)
    got = await purchase_memory.recall(item="tissues")
    assert sorted(r["id"] for r in got) == ["r2", "r9"]       # r9 by the word, r2 by the score; Tylenol is neither
    assert fake.calls[-1][1] == "tissues" and fake.calls[-1][2] is None
    assert [r["id"] for r in await purchase_memory.recall(item="the Tylenol")] == ["r1", "r2"]


def test_word_matching_ignores_short_words_and_plural_s():
    n = purchase_memory._names_it
    assert n("tissues", "Kleenex Facial Tissues") and n("tissue", "Kleenex Facial Tissues")
    assert n("the Tylenol", "Tylenol Extra Strength") and n("allergy pills", "Allegra 24 Hour Allergy Relief")
    assert not n("the cold", "Allegra 24 Hour Allergy Relief") and not n("a", "Anything")


async def test_clearing_replaces_the_memory_with_a_marker_instead_of_deleting_it(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(purchase_memory, "_client", lambda: fake)
    await purchase_memory.clear()
    assert [c[0] for c in fake.calls] == ["delete_index", "create_index"] and fake.calls[-1][2] == 1


async def test_the_memory_is_loaded_once_and_kept_fresh_not_reloaded_per_question(monkeypatch):
    fake = FakeClient([])
    monkeypatch.setattr(purchase_memory, "_client", lambda: fake)
    monkeypatch.setattr(purchase_memory, "_reader", None)
    monkeypatch.setattr(purchase_memory, "_loaded", False)
    for _ in range(3):
        await purchase_memory.recall()
    loads = [c for c in fake.calls if c[0] == "load_index"]
    assert len(loads) == 1                                    # not once per question (that took 3.5 s)
    assert loads[0][2] == {"auto_refresh": True, "polling_interval_in_seconds": purchase_memory.REFRESH_S}


async def test_no_memory_yet_means_fall_back_not_crash(monkeypatch):
    class NoIndex(FakeClient):
        async def load_index(self, name, **kw):
            raise RuntimeError("index not found")
    monkeypatch.setattr(purchase_memory, "_client", lambda: NoIndex())
    monkeypatch.setattr(purchase_memory, "_reader", None)
    monkeypatch.setattr(purchase_memory, "_loaded", False)
    with pytest.raises(purchase_memory.MemoryUnavailable):
        await purchase_memory.recall()


async def test_recall_without_moss_raises_so_history_can_fall_back(monkeypatch):
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
    with pytest.raises(purchase_memory.MemoryUnavailable):
        await purchase_memory.recall()


# --- checkout mirrors the new rows into Moss, and can never fail a checkout -----------------------

def test_the_mirror_copies_this_payments_purchase_rows_into_the_memory(monkeypatch):
    from data import db
    seen = {}
    monkeypatch.setattr(db, "get_purchases", lambda **kw: seen.setdefault("q", kw) and ROWS[:1])
    monkeypatch.setattr(purchase_memory, "remember_sync", lambda rows: seen.setdefault("rows", rows))
    purchase_memory._mirror("pay-1")
    assert seen["q"] == {"payment_id": "pay-1"} and seen["rows"] == ROWS[:1]


def test_a_missing_table_or_moss_outage_is_swallowed(monkeypatch):
    from data import db

    def boom(**kw):
        raise RuntimeError("relation purchase_items does not exist")
    monkeypatch.setattr(db, "get_purchases", boom)
    purchase_memory._mirror("pay-1")                 # must not raise
    purchase_memory.mirror_payment(None)             # nothing to do


def _record_spawns(monkeypatch):
    spawned = []
    monkeypatch.setattr(purchase_memory.subprocess, "Popen", lambda cmd, **kw: spawned.append((cmd, kw)))
    return spawned


def test_checkout_and_reset_hand_the_moss_write_to_another_process(monkeypatch):
    """A Moss write freezes its whole process for about 5 s, so it must never run in the server or the agent."""
    import sys
    spawned = _record_spawns(monkeypatch)
    purchase_memory.mirror_payment("pay-1")
    purchase_memory.clear_in_background()
    purchase_memory.mirror_payment(None)                                  # nothing to copy: no process
    assert [c[0][1:] for c in spawned] == [["-m", "lookup.purchase_memory", "mirror", "pay-1"],
                                           ["-m", "lookup.purchase_memory", "clear"]]
    assert all(c[0][0] == sys.executable and c[1]["start_new_session"] for c in spawned)


def test_a_failure_to_start_the_job_never_breaks_a_checkout(monkeypatch):
    def boom(*a, **k):
        raise OSError("no processes left")
    monkeypatch.setattr(purchase_memory.subprocess, "Popen", boom)
    purchase_memory.mirror_payment("pay-1")                               # must not raise


def test_the_job_process_runs_the_right_work(monkeypatch):
    calls = []
    monkeypatch.setattr(purchase_memory, "_mirror", lambda pid: calls.append(("mirror", pid)))
    monkeypatch.setattr(purchase_memory, "clear_sync", lambda: calls.append(("clear",)))
    assert purchase_memory.main(["mirror", "pay-9"]) == 0 and purchase_memory.main(["clear"]) == 0
    assert purchase_memory.main(["bogus"]) == 2
    assert calls == [("mirror", "pay-9"), ("clear",)]


def test_history_is_a_known_intent():
    from agents.intent import IntentName, SYSTEM_PROMPT
    assert "history_question" in IntentName.__args__ and "history_question:" in SYSTEM_PROMPT


async def test_product_agent_loads_the_eligibility_index_at_startup(monkeypatch):
    """The first scan after a restart must not pay the 2.5 s index load."""
    from agents import product_agent
    from lookup import moss_index
    loaded = []

    async def fake_warm():
        loaded.append(True)
        return True
    monkeypatch.setattr(moss_index, "warm_up", fake_warm)
    monkeypatch.setenv("MOSS_PROJECT_ID", "p")
    agent = product_agent.build_agent(mailbox=False, port=8101)
    handlers = [h for hs in agent._on_startup for h in ([hs] if callable(hs) else [])]
    assert handlers, "no startup handler registered"
    await handlers[0](None)
    assert loaded == [True]


def test_claude_calls_stop_waiting_after_ten_seconds_by_default():
    """Understanding, History questions and wording each give up after 10 s (a stall guard, not a target).

    Checked in a fresh process with the settings removed, so no other test's imports are disturbed.
    """
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k not in ("INTENT_TIMEOUT_S", "SPEAK_TIMEOUT_S")}
    code = ("from agents import history, intent, speaker; "
            "print(intent.TIMEOUT_S, history.TIMEOUT_S, speaker.TIMEOUT_S)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         cwd=os.path.dirname(os.path.dirname(__file__)))
    # .env is loaded by the agents package; it must not set these either
    assert out.stdout.split()[-3:] == ["10.0", "10.0", "10.0"], out.stderr[-300:]
