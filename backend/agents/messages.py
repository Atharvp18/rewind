"""Typed messages exchanged between the Rewind agents (uAgents).

Users talk to the orchestrator over the Agent Chat Protocol (ASI:One).
The orchestrator talks to the workers with these models. Workers return facts,
never finished sentences; the orchestrator phrases them (agents/speaker.py).
Every request carries a request_id that the response echoes.
"""
from __future__ import annotations

from typing import Any

from uagents import Model, Protocol

from agents.speaker import Facts


class FactsMsg(Model):
    template: str
    must_say: list[str] = []
    fixed: bool = False
    alert: str | None = None

    @classmethod
    def of(cls, f: Facts) -> "FactsMsg":
        return cls(template=f.template, must_say=list(f.must_say), fixed=f.fixed, alert=f.alert)

    def to_facts(self) -> Facts:
        return Facts(template=self.template, must_say=list(self.must_say), fixed=self.fixed, alert=self.alert)


class ProductRequest(Model):
    request_id: str
    image_url: str | None = None
    product_hint: str | None = None
    is_prescription: bool | None = None    # user said it's a prescription from the counter


class ProductResponse(Model):
    request_id: str
    facts: FactsMsg
    scan: dict[str, Any] | None = None
    card_profile: dict[str, Any] | None = None   # from an insurance card scan; no personal data
    person_name: str | None = None               # from the card; the orchestrator keeps it in memory only


class PaymentRequest(Model):
    request_id: str
    session: dict[str, Any]
    intent: dict[str, Any] | None = None   # an Intent: cart / checkout actions
    scan: dict[str, Any] | None = None     # a freshly resolved scan to recommend a card for


class PaymentResponse(Model):
    request_id: str
    facts: FactsMsg
    session: dict[str, Any]


product_protocol = Protocol(name="rewind-product", version="1.0.0")
payment_protocol = Protocol(name="rewind-payment", version="1.0.0")
