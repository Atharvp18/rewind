"""Seeds and addresses for the Rewind agents.

An agent's address is derived from its seed, so the orchestrator can compute
the workers' addresses itself. Set *_AGENT_ADDRESS only to point at an agent
running elsewhere whose seed you don't have.
"""
from __future__ import annotations

import os

from uagents.crypto import Identity

import agents.common  # noqa: F401  (loads backend/.env)

ORCHESTRATOR_SEED = os.environ.get("ORCHESTRATOR_AGENT_SEED") or "rewind-orchestrator-dev-seed"
PRODUCT_SEED = os.environ.get("PRODUCT_AGENT_SEED") or "rewind-product-agent-dev-seed"
PAYMENT_SEED = os.environ.get("PAYMENT_AGENT_SEED") or "rewind-payment-agent-dev-seed"
HISTORY_SEED = os.environ.get("HISTORY_AGENT_SEED") or "rewind-history-agent-dev-seed"


def address_of(seed: str) -> str:
    return Identity.from_seed(seed, 0).address


PRODUCT_AGENT_ADDRESS = os.environ.get("PRODUCT_AGENT_ADDRESS") or address_of(PRODUCT_SEED)
PAYMENT_AGENT_ADDRESS = os.environ.get("PAYMENT_AGENT_ADDRESS") or address_of(PAYMENT_SEED)
HISTORY_AGENT_ADDRESS = os.environ.get("HISTORY_AGENT_ADDRESS") or address_of(HISTORY_SEED)
ORCHESTRATOR_AGENT_ADDRESS = address_of(ORCHESTRATOR_SEED)
