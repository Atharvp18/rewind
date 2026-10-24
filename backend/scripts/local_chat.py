"""Run all Rewind agents locally and play a scripted conversation through them.

The orchestrator, product, and payment agents run in one uAgents Bureau with a
test "shopper" agent. Messages go agent-to-agent exactly as they would through
Agentverse, minus the mailbox. Uses live Claude if ANTHROPIC_API_KEY is set.

Usage:
    python scripts/local_chat.py             # a shopping trip
    python scripts/local_chat.py insurance   # prescription + insurance card flow
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uagents import Agent, Bureau, Context
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement, ChatMessage, MetadataContent, Resource, ResourceContent, StartSessionContent, TextContent,
)

from agents import orchestrator_agent, payment_agent, product_agent
from agents.addresses import ORCHESTRATOR_AGENT_ADDRESS

# Photos: with REWIND_STUB_VISION=true the stub reads the marker in the bytes.
PHOTO = "<photo:advil>"        # shelf box, reads as Advil, $12.99
CARD = "<photo:card>"          # insurance card, reads as a UnitedHealthcare card with an Rx section
BOTTLE = "<photo:rx_label>"    # pharmacy label, reads as omeprazole 20mg

SCRIPTS = {
    "shopping": [
        "hi there",
        "is it safe to take advil with my blood pressure pills",
        "how much money is left on my hsa",
        PHOTO,
        "put it on the visa",
        "<photo:tissues_far>",     # price tag too far away to read
        "<photo:tissues_close>",   # the shopper moves closer, as the agent suggests
        "the visa please",
        "what's in my cart",
        "checkout",
        "yep go ahead",
    ],
    "insurance": [
        BOTTLE,                       # prescription before any plan is known
        "yes that's right",
        "hmm I'm not sure which plan I have",
        CARD,                         # card scan: name kept in memory only
        "hello again",
        "what does my insurance cover",
        "I picked up my prescription for omeprazole 20 milligrams at the counter",
        "yes",
        "sure go ahead",
        "what's in my cart",
    ],
}
SCRIPT = SCRIPTS[sys.argv[1] if len(sys.argv) > 1 else "shopping"]

replies: asyncio.Queue = asyncio.Queue()
shopper = Agent(name="test-shopper", seed="rewind-local-test-shopper", port=8010, endpoint=["http://127.0.0.1:8010/submit"])


@shopper.on_message(ChatMessage)
async def on_reply(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    text = "".join(p.text for p in msg.content if isinstance(p, TextContent))
    alert = next((p.metadata.get("alert") for p in msg.content if isinstance(p, MetadataContent)), None)
    await replies.put((text, alert))


@shopper.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


@shopper.on_event("startup")
async def play(ctx: Context):
    await asyncio.sleep(4)  # let the orchestrator warm up
    for n, line in enumerate(SCRIPT):
        print(f"\nSHOPPER: {line}", flush=True)
        if line.startswith("<photo:"):
            kind = line[len("<photo:"):-1]
            content = [ResourceContent(resource_id=uuid4(), resource=Resource(
                uri=f"http://127.0.0.1:{PHOTO_PORT}/{kind}.jpg", metadata={"mime_type": "image/jpeg"}))]
        else:
            content = [TextContent(type="text", text=line)]
        if n == 0:   # a new chat, as ASI:One sends it: no memory from earlier runs
            content = [StartSessionContent(type="start-session"), *content]
        await ctx.send(ORCHESTRATOR_AGENT_ADDRESS, ChatMessage(
            timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content))
        try:
            text, alert = await asyncio.wait_for(replies.get(), 20)
            print(f"AGENT:   {text}" + (f"   [alert: {alert}]" if alert else ""), flush=True)
        except asyncio.TimeoutError:
            print("AGENT:   <no reply within 20 s>", flush=True)
    print("\n--- done", flush=True)
    import os
    os._exit(0)


PHOTO_PORT = 8030


def serve_dummy_photo() -> None:
    """Stand-in for ASI:One's attachment URL. Stub vision ignores the bytes."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            kind = self.path.strip("/").removesuffix(".jpg")
            self.wfile.write(b"\xff\xd8\xff\xe0 stub:" + kind.encode())

        def log_message(self, *args):
            pass

    threading.Thread(target=HTTPServer(("127.0.0.1", PHOTO_PORT), Handler).serve_forever, daemon=True).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    serve_dummy_photo()
    bureau = Bureau(port=8020, endpoint=["http://127.0.0.1:8020/submit"])
    bureau.add(orchestrator_agent.build_agent(mailbox=False, port=8003))
    bureau.add(product_agent.build_agent(mailbox=False, port=8001))
    bureau.add(payment_agent.build_agent(mailbox=False, port=8002))
    bureau.add(shopper)
    bureau.run()
