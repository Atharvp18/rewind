"""Rewind History Agent: a uAgents worker.

Stateless and read-only. Receives the user's question, answers from the purchase_items table,
and returns a fact sheet. It never changes a cart, a card, or a purchase.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context

from agents import history
from agents.addresses import HISTORY_SEED, ORCHESTRATOR_AGENT_ADDRESS
from agents.messages import FactsMsg, HistoryRequest, HistoryResponse, history_protocol

logger = logging.getLogger(__name__)


@history_protocol.on_message(HistoryRequest, replies=HistoryResponse)
async def on_request(ctx: Context, sender: str, msg: HistoryRequest):
    if sender != ORCHESTRATOR_AGENT_ADDRESS:
        ctx.logger.warning("ignoring HistoryRequest from unknown sender %s", sender)
        return
    facts = await history.answer(msg.question)
    await ctx.send(sender, HistoryResponse(request_id=msg.request_id, facts=FactsMsg.of(facts)))


def build_agent(mailbox: bool = True, port: int = 8004) -> Agent:
    agent = Agent(
        name="Rewind History Agent",
        seed=HISTORY_SEED,
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        description="Answers questions about past purchases: totals, what was bought, and eligible items paid "
                    "with the Visa that could be claimed back. Read-only.",
    )
    agent.include(history_protocol, publish_manifest=True)

    @agent.on_event("startup")
    async def warm(ctx: Context):
        from lookup import purchase_memory
        if not history.STUB_HISTORY:
            await purchase_memory.warm_up()    # best effort; History falls back to the purchase table
    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
