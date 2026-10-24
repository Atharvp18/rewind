"""Rewind Shopping Assistant — the orchestrator users find on ASI:One.

Owns per-user session state. Classifies each message, forwards it to the
Product or Payment agent with the session attached as metadata, and relays
the worker's reply back to the user. If worker addresses are not configured
it calls the same handler functions in-process, so one process still demos.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    TextContent,
    chat_protocol_spec,
)

from agents import payment_agent, product_agent
from agents.common import Incoming, ack, now, reply
from agents.session import SessionStore, find_demo_item

logger = logging.getLogger(__name__)

PRODUCT_AGENT_ADDRESS = os.environ.get("PRODUCT_AGENT_ADDRESS", "")
PAYMENT_AGENT_ADDRESS = os.environ.get("PAYMENT_AGENT_ADDRESS", "")

WELCOME = (
    "Hi, I'm Rewind. Point me at a product — attach a shelf photo or name the item — "
    "and I'll tell you the price, whether it's HSA/FSA eligible, and which card to use. "
    "Then say \"add it\", \"what's in my cart\", or \"checkout\"."
)

PAYMENT_WORDS = ("cart", "checkout", "check out", "balance", "remove last", "clear", "card")
PRODUCT_WORDS = ("eligible", "eligibility", "hsa", "fsa", "scan", "what is", "is this", "cover")
RESET_WORDS = ("reset demo", "reset run")

sessions = SessionStore()


def classify(inc: Incoming, session: dict) -> str:
    """Deterministic intent routing. Returns 'product', 'payment', 'reset', or 'general'."""
    if inc.image_url:
        return "product"
    t = inc.text.lower()
    if not t:
        return "general"
    if any(w in t for w in RESET_WORDS):
        return "reset"
    if session.get("pending") or session.get("last_scan"):
        return "payment"
    if any(w in t for w in PAYMENT_WORDS):
        return "payment"
    if any(w in t for w in PRODUCT_WORDS) or find_demo_item(t):
        return "product"
    if t in ("help", "what can you do", "hi", "hello", "hey", "start"):
        return "general"
    return "general"


def _forward(user: str, inc: Incoming, session: dict, extra: dict | None = None) -> ChatMessage:
    content: list = []
    if inc.text:
        content.append(TextContent(type="text", text=inc.text))
    if inc.resource is not None:
        content.append(inc.resource)
    meta = {"user": user, "session": json.dumps(session)}
    if extra:
        meta.update({k: json.dumps(v) for k, v in extra.items()})
    content.append(MetadataContent(type="metadata", metadata=meta))
    from uuid import uuid4
    return ChatMessage(timestamp=now(), msg_id=uuid4(), content=content)


async def _send_to_user(ctx: Context, user: str, text: str) -> None:
    sessions.get(user)["last_reply"] = text
    await ctx.send(user, reply(text))


async def _run_product(ctx: Context, user: str, inc: Incoming, session: dict) -> None:
    if PRODUCT_AGENT_ADDRESS:
        await ctx.send(PRODUCT_AGENT_ADDRESS, _forward(user, inc, session))
        return
    text, meta = await product_agent.handle(inc)
    await _after_product(ctx, user, text, meta.get("scan") if meta else None)


async def _after_product(ctx: Context, user: str, text: str, scan: dict | None) -> None:
    session = sessions.get(user)
    if scan and scan["state"] == "resolved":
        rec_text, session = await _run_payment_recommend(user, session, scan)
        sessions._sessions[user] = session
        await _send_to_user(ctx, user, rec_text)
        return
    if scan:
        session["last_scan"] = scan
    await _send_to_user(ctx, user, text)


async def _run_payment_recommend(user: str, session: dict, scan: dict) -> tuple[str, dict]:
    return payment_agent.recommend(session, scan)


async def _run_payment(ctx: Context, user: str, inc: Incoming, session: dict) -> None:
    if PAYMENT_AGENT_ADDRESS:
        await ctx.send(PAYMENT_AGENT_ADDRESS, _forward(user, inc, session))
        return
    text, session = payment_agent.handle(inc.text, session)
    sessions._sessions[user] = session
    await _send_to_user(ctx, user, text)


protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def on_message(ctx: Context, sender: str, msg: ChatMessage):
    await ack(ctx, sender, msg)
    inc = Incoming(msg)

    # Reply coming back from a worker agent: update session and relay to the user.
    if sender in (PRODUCT_AGENT_ADDRESS, PAYMENT_AGENT_ADDRESS) and "user" in inc.metadata:
        user = inc.metadata["user"]
        if sender == PAYMENT_AGENT_ADDRESS:
            session = inc.json("session")
            if session:
                sessions._sessions[user] = session
            await _send_to_user(ctx, user, inc.text)
        else:
            scan = inc.json("scan")
            if scan and scan["state"] == "resolved" and PAYMENT_AGENT_ADDRESS:
                session = sessions.get(user)
                await ctx.send(PAYMENT_AGENT_ADDRESS, _forward(user, Incoming(msg), session, {"scan": scan}))
                return
            await _after_product(ctx, user, inc.text, scan)
        return

    user = sender
    if inc.session_started:
        sessions.reset(user)
    if inc.session_ended:
        sessions.end(user)
        return
    session = sessions.get(user)

    intent = classify(inc, session)
    ctx.logger.info("intent=%s text=%r image=%s", intent, inc.text[:60], bool(inc.image_url))

    if intent == "reset":
        run = 2 if "2" in inc.text else 1
        sessions.reset(user, run)
        await _send_to_user(ctx, user, f"Demo reset for run {run}. " + payment_agent._balances(sessions.get(user)))
    elif intent == "product":
        await _run_product(ctx, user, inc, session)
    elif intent == "payment":
        await _run_payment(ctx, user, inc, session)
    elif inc.text.lower().strip() in ("repeat that", "read it again", "again"):
        await _send_to_user(ctx, user, session.get("last_reply") or WELCOME)
    else:
        await _send_to_user(ctx, user, WELCOME)


@protocol.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


def build_agent() -> Agent:
    agent = Agent(
        name="Rewind Shopping Assistant",
        seed=os.environ.get("ORCHESTRATOR_AGENT_SEED", "rewind-orchestrator-dev-seed"),
        port=int(os.environ.get("ORCHESTRATOR_AGENT_PORT", "8003")),
        mailbox=True,
        publish_agent_details=True,
    )
    agent.include(protocol, publish_manifest=True)
    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
