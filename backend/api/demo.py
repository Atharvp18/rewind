"""POST /v1/demo/reset: put the database back to the seed state for run 1 or run 2 (spec 3.4)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from api import memory
from data import db
from lookup import purchase_memory
from payments import checkout, store_checkin

router = APIRouter(prefix="/v1/demo")


class Reset(BaseModel):
    run: Literal[1, 2, 3]   # 3: two accounts, HSA and Visa (data/seed.py)


@router.post("/decline-next")
def decline_next() -> dict:
    """Presenter demo: decline the next payment once, to show the declined screen. Nothing is charged."""
    checkout.decline_next()
    return {"ok": True}


@router.post("/reset")
def reset(body: Reset) -> dict:
    result = db.reset_demo(body.run)
    memory.forget()
    store_checkin.check_out()
    checkout.decline_next(False)
    purchase_memory.clear_in_background()         # History's Moss memory is not in Postgres
    return {"cards": result["cards"], "cart": result["cart"]}
