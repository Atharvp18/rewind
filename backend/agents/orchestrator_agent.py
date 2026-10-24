"""Rewind Shopping Assistant — the orchestrator users find on ASI:One. 
The front desk. It owns:
  - understanding: one Claude intent call per user message
  - memory: each user's session in uAgents ctx.storage
  - voice: the speaker phrases worker facts (Claude + validator)
  - simple guardrails that need no worker (medical advice, other people, scope)
and routes everything else to the specialists over typed uAgents messages:
  - Product agent: scan -> eligibility
  - Payment agent: card routing, cart, checkout
"""
from __future__ import annotations

import asyncio

import logging
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, chat_protocol_spec

from agents.addresses import HISTORY_AGENT_ADDRESS, ORCHESTRATOR_SEED, PAYMENT_AGENT_ADDRESS, PRODUCT_AGENT_ADDRESS
from agents.common import Incoming, ack, dollars, reply
from agents.intent import REFUSALS, Intent, classify_intent
from agents.messages import (
    HistoryRequest, HistoryResponse, PaymentRequest, PaymentResponse, ProductRequest, ProductResponse,
    history_protocol, payment_protocol, product_protocol,
)
from agents import store
from agents.payment_agent import pending_reminder
from agents.session import new_session
from data import db
from agents.speaker import Facts, render, say, PRICE_RETRY

logger = logging.getLogger(__name__)

ASSISTANT_NAME: str | None = None  # set once the team picks a name, e.g. "Rewind"

_intro = f"I'm {ASSISTANT_NAME}, your shopping helper" if ASSISTANT_NAME else "I'm your shopping helper"
WELCOME = say(f"Hi, {_intro}. Show me any item, and I'll tell you what it is, the price, "
              "and which card to use. What would you like to do?", "shopping helper")
WELCOME_BACK = say("How may I help you today?", fixed=True)  # spec 6.5-A
DIDNT_CATCH = say("I didn't catch that. You can show me an item, add the one we're looking at, "
                  "hear your cart, or check out.")
TOO_SLOW = say("Sorry, that took too long. Please try again.", fixed=True)

PRODUCT_INTENTS = {"scan_product", "eligibility_question"}
LOCAL_REFUSALS = {"medical_advice", "other_person", "out_of_scope"}
NUDGE_AFTER_S = 10.0
NUDGE_UNTIL_S = 120.0   # a user idle longer than this has left: no reminder, even after an agent restart
MAX_NUDGES = 1
WORKER_TIMEOUT_S = 12.0


# --- names: in process memory only, never written to ctx.storage ----------------
#
# ctx.storage is a file on disk. The name read from an insurance card is used to
# greet the user and is forgotten when the chat ends or the agent restarts.

_names: dict[str, str] = {}


# --- storage: one session per user, plus in-flight worker requests -------------

def load_session(ctx: Context, user: str) -> dict:
    return ctx.storage.get(f"session:{user}") or new_session()


def save_session(ctx: Context, user: str, session: dict) -> None:
    ctx.storage.set(f"session:{user}", session)
    users = ctx.storage.get("users") or []
    if user not in users:
        ctx.storage.set("users", users + [user])


def end_session(ctx: Context, user: str) -> None:
    _names.pop(user, None)
    ctx.storage.remove(f"session:{user}")
    ctx.storage.set("users", [u for u in (ctx.storage.get("users") or []) if u != user])


def track_request(ctx: Context, user: str, kind: str) -> str:
    request_id = str(uuid4())
    inflight = ctx.storage.get("inflight") or {}
    inflight[request_id] = {"user": user, "kind": kind, "sent_at": time.time()}
    ctx.storage.set("inflight", inflight)
    return request_id


def take_request(ctx: Context, request_id: str) -> dict | None:
    inflight = ctx.storage.get("inflight") or {}
    entry = inflight.pop(request_id, None)
    ctx.storage.set("inflight", inflight)
    return entry


# --- pure helpers ---------------------------------------------------------------

def greeting(session: dict, first_name: str | None = None) -> Facts:
    if session.get("greeted") or session.get("last_reply"):   # mid-conversation: keep it short
        session["greeted"] = True
        if first_name:
            return say(f"Hi {first_name}, how may I help you today?", first_name, fixed=True)
        return WELCOME_BACK
    session["greeted"] = True
    return WELCOME


def due_for_nudge(session: dict, now: float) -> bool:
    """One reminder, 10 s to 2 min after the user went quiet on an open question."""
    if session.get("nudges", 0) >= MAX_NUDGES or not session.get("pending"):
        return False
    idle = now - session.get("last_activity", now)
    return NUDGE_AFTER_S <= idle <= NUDGE_UNTIL_S


def nudge(session: dict) -> Facts | None:
    return pending_reminder(session)


def unclear_facts(session: dict) -> Facts:
    scan = session.get("last_scan")
    if scan and scan["product"].get("amount_cents") is None:
        pname = scan["product"]["name"]
        return say(f"I didn't catch that. I still need a price for {pname}. {PRICE_RETRY}", pname, fixed=True)
    return DIDNT_CATCH


# --- talking to the user ------------------------------------------------------

async def speak(ctx: Context, user: str, facts: Facts | str, session: dict | None = None) -> None:
    """Phrase the facts, remember what was said, and reply. The only place replies are sent."""
    text = await render(facts)
    session = session if session is not None else load_session(ctx, user)
    session["last_reply"] = text
    session["last_activity"] = time.time()
    session["nudges"] = 0
    save_session(ctx, user, session)
    alert = facts.alert if isinstance(facts, Facts) else None
    await ctx.send(user, reply(text, {"alert": alert} if alert else None))


# --- chat protocol: the user-facing side -------------------------------------------

chat_protocol = Protocol(spec=chat_protocol_spec)


@chat_protocol.on_message(ChatMessage)
async def on_user_message(ctx: Context, sender: str, msg: ChatMessage):
    await ack(ctx, sender, msg)
    inc = Incoming(msg)
    user = sender

    if inc.session_ended:
        end_session(ctx, user)
        return
    session = new_session() if inc.session_started else load_session(ctx, user)
    session["last_activity"] = time.time()
    save_session(ctx, user, session)
    first_name = (_names.get(user) or "").split(" ")[0] or None
    if not inc.text and not inc.image_url:
        await speak(ctx, user, greeting(session, first_name), session)
        return

    intent = await classify_intent(inc.text, session, has_image=bool(inc.image_url))
    ctx.logger.info("intent=%s entities=%s image=%s", intent.intent,
                    intent.entities.model_dump(exclude_none=True), bool(inc.image_url))
    name = intent.intent

    # Front-desk answers: no specialist needed.
    if name in LOCAL_REFUSALS:
        await speak(ctx, user, say(REFUSALS[name], fixed=True), session)
    elif name == "greeting":
        await speak(ctx, user, greeting(session, first_name), session)
    elif name == "repeat":
        await speak(ctx, user, session.get("last_reply") or greeting(session, first_name), session)
    elif name == "reset_demo":
        run = intent.entities.run if intent.entities.run in (1, 2) else 1
        try:
            await asyncio.to_thread(db.reset_demo, run)   # Atharv's seed, one transaction
            from lookup import purchase_memory
            await asyncio.to_thread(purchase_memory.clear_sync)   # the Moss memory is not in Postgres
            await speak(ctx, user, say(f"Demo reset for run {run}.", str(run), fixed=True), new_session())
        except db.DBUnavailable:
            await speak(ctx, user, store.DB_DOWN, session)
    elif name == "unclear":
        await speak(ctx, user, unclear_facts(session), session)

    # Specialists.
    elif name in PRODUCT_INTENTS:
        request_id = track_request(ctx, user, "product")
        await ctx.send(PRODUCT_AGENT_ADDRESS, ProductRequest(
            request_id=request_id,
            image_url=inc.image_url,
            product_hint=intent.entities.product,
            is_prescription=intent.entities.is_prescription,
        ))
    elif name == "history_question":
        request_id = track_request(ctx, user, "history")
        await ctx.send(HISTORY_AGENT_ADDRESS, HistoryRequest(request_id=request_id, question=inc.text))
    else:
        request_id = track_request(ctx, user, "payment")
        await ctx.send(PAYMENT_AGENT_ADDRESS, PaymentRequest(
            request_id=request_id, session=session, intent=intent.model_dump(),
        ))


@chat_protocol.on_message(ChatAcknowledgement)
async def on_user_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


# --- worker protocols: the specialist side ------------------------------------------

@product_protocol.on_message(ProductResponse)
async def on_product_response(ctx: Context, sender: str, msg: ProductResponse):
    if sender != PRODUCT_AGENT_ADDRESS:
        ctx.logger.warning("ignoring ProductResponse from unknown sender %s", sender)
        return
    entry = take_request(ctx, msg.request_id)
    if entry is None:
        return  # timed out already; the user was told
    user = entry["user"]
    session = load_session(ctx, user)
    scan = msg.scan

    if msg.card_profile is not None:
        # Insurance card: keep the plan (no personal data), keep the name in memory only.
        session["insurance"] = msg.card_profile
        if msg.person_name:
            _names[user] = msg.person_name
        if (session.get("pending") or {}).get("scope") == "ask_plan":
            # Card shown while a prescription was waiting for a plan: continue that flow.
            save_session(ctx, user, session)
            request_id = track_request(ctx, user, "payment")
            await ctx.send(PAYMENT_AGENT_ADDRESS, PaymentRequest(
                request_id=request_id, session=session, intent=Intent(intent="choose_plan").model_dump()))
            return
        await speak(ctx, user, msg.facts.to_facts(), session)
        return

    if scan and (scan["state"] == "resolved" or scan["product"].get("is_prescription_only")):
        # Price known, or a counter prescription: the Payment agent decides what happens next.
        request_id = track_request(ctx, user, "payment")
        await ctx.send(PAYMENT_AGENT_ADDRESS, PaymentRequest(request_id=request_id, session=session, scan=scan))
        return
    if scan:
        session["last_scan"] = scan
        session["pending"] = None
    await speak(ctx, user, msg.facts.to_facts(), session)


@payment_protocol.on_message(PaymentResponse)
async def on_payment_response(ctx: Context, sender: str, msg: PaymentResponse):
    if sender != PAYMENT_AGENT_ADDRESS:
        ctx.logger.warning("ignoring PaymentResponse from unknown sender %s", sender)
        return
    entry = take_request(ctx, msg.request_id)
    if entry is None:
        return
    session = dict(msg.session)
    previous = load_session(ctx, entry["user"])
    for key in ("greeted", "last_reply", "last_activity", "nudges"):
        if key in previous:
            session[key] = previous[key]
    await speak(ctx, entry["user"], msg.facts.to_facts(), session)


@history_protocol.on_message(HistoryResponse)
async def on_history_response(ctx: Context, sender: str, msg: HistoryResponse):
    if sender != HISTORY_AGENT_ADDRESS:
        ctx.logger.warning("ignoring HistoryResponse from unknown sender %s", sender)
        return
    entry = take_request(ctx, msg.request_id)
    if entry is None:
        return
    session = load_session(ctx, entry["user"])
    facts = msg.facts.to_facts()
    reminder = pending_reminder(session)    # a history answer never drops the open question
    if reminder:
        facts = say(f"{facts.template} {reminder.template}", *facts.must_say, *reminder.must_say,
                    fixed=facts.fixed, alert=facts.alert)
    await speak(ctx, entry["user"], facts, session)


# --- agent ----------------------------------------------------------------------

def build_agent(mailbox: bool = True, port: int = 8003) -> Agent:
    agent = Agent(
        name="Rewind Shopping Assistant",
        seed=ORCHESTRATOR_SEED,
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        description=("A voice-first shopping helper for elderly and low-vision shoppers: identifies an item, "
                     "says its price and whether it is HSA/FSA eligible, and which card to pay with."),
    )
    agent.include(chat_protocol, publish_manifest=True)
    agent.include(product_protocol)
    agent.include(payment_protocol)
    agent.include(history_protocol)

    @agent.on_event("startup")
    async def warm(ctx: Context):
        from agents.intent import warm_up
        ctx.storage.set("inflight", {})
        ctx.logger.info("product agent: %s", PRODUCT_AGENT_ADDRESS)
        ctx.logger.info("payment agent: %s", PAYMENT_AGENT_ADDRESS)
        ctx.logger.info("history agent: %s", HISTORY_AGENT_ADDRESS)
        await warm_up()

    @agent.on_interval(period=2.0)
    async def expire_slow_requests(ctx: Context):
        inflight = ctx.storage.get("inflight") or {}
        now = time.time()
        for request_id, entry in list(inflight.items()):
            if now - entry["sent_at"] > WORKER_TIMEOUT_S:
                take_request(ctx, request_id)
                ctx.logger.warning("%s agent did not answer request %s", entry["kind"], request_id)
                await speak(ctx, entry["user"], TOO_SLOW)

    @agent.on_interval(period=5.0)
    async def nudge_idle_users(ctx: Context):
        """After 10 s of silence on a pending question, remind the user once (spec 6.5-D)."""
        for user in ctx.storage.get("users") or []:
            session = load_session(ctx, user)
            if not due_for_nudge(session, time.time()):
                continue
            facts = nudge(session)
            if facts:
                session["nudges"] = session.get("nudges", 0) + 1
                session["last_activity"] = time.time()
                save_session(ctx, user, session)
                await ctx.send(user, reply(await render(facts)))

    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
