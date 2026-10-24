"""Checkout endpoints (technical spec 3.6)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from api import memory
from payments import checkout, nessie

router = APIRouter(prefix="/v1/checkout")


class Confirm(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    prompt_id: str


def confirmed_body(result: checkout.Confirmed) -> dict:
    new_balances = result.payment["new_balances"] if result.payment else None
    return {
        "payment_id": result.payment["payment_id"] if result.payment else None,
        "groups": [g.model_dump() for g in result.groups],
        "new_balances": new_balances,
        "voice": memory.remember(result.voice),
    }


@router.post("/preview")
def preview() -> dict:
    result = checkout.preview()
    plan = result.plan
    return {
        "groups": [g.model_dump() for g in plan.groups] if plan else [],
        "total_cents": plan.total_cents if plan else 0,
        "issues": [i.model_dump() for i in plan.issues] if plan else [],
        "voice": memory.remember(result.voice),
    }


@router.post("/confirm")
def confirm(body: Confirm, background: BackgroundTasks) -> dict:
    result = checkout.confirm(body.idempotency_key, body.prompt_id)
    if result.ledger:
        background.add_task(nessie.log_withdrawals, result.ledger)      # after the response, never blocks it
    return confirmed_body(result)
