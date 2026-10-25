"""Store check-in (PROPOSED, prototype only; see payments/store_checkin.py for the spec conflict).

POST /v1/checkin/nearby       {lat, lng} or {store_id} for the presenter demo
    -> {store, voice} asking "Are you at ...?" (scope confirm_checkin), or null
POST /v1/checkin/still-here   {store_id, lat, lng} -> {at_store}

The answer to the question goes to POST /v1/command with the prompt. Coordinates are only
compared with the seeded stores; they are never stored or logged.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api import memory
from data import db
from payments import store_checkin
from speech import compose

router = APIRouter(prefix="/v1/checkin")


class Nearby(BaseModel):
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    store_id: str | None = None          # presenter demo: "pretend I'm at this store", no GPS


class StillHere(BaseModel):
    store_id: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.post("/nearby")
def nearby(body: Nearby) -> dict | None:
    if body.store_id:
        store = store_checkin.by_id(body.store_id)
    elif body.lat is not None and body.lng is not None:
        store = store_checkin.nearest(body.lat, body.lng)
    else:
        store = None
    here = store_checkin.current()
    if store is None or (here and here["id"] == store["id"]):     # nowhere known, or already checked in
        return None
    prompt_id = db.create_prompt("confirm_checkin", None, {"store_id": store["id"]})
    voice = compose.checkin_question(store["name"], store["address"], prompt_id)
    return {"store": store_checkin.public(store), "voice": memory.remember(voice)}


@router.post("/still-here")
def still_here(body: StillHere) -> dict:
    store = store_checkin.by_id(body.store_id)
    at = store is not None and store_checkin.meters_between(
        body.lat, body.lng, store["lat"], store["lng"]) <= store_checkin.LEAVE_METERS
    here = store_checkin.current()
    if not at and here and here["id"] == body.store_id:
        store_checkin.check_out()
    return {"at_store": at}
