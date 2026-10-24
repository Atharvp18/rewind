"""GET /v1/health (technical spec 0.6).

Each upstream is "ok", "degraded", or "down". The app shows a banner on "down".

Supabase and Cartesia are probed live (Cartesia by the 60 s keepalive in api/voice.py). The
other three report "down" when their credentials are missing (they cannot work) and "ok" when
the credentials are present. That is a configuration
check, not a live probe: replace each with a real call as that adapter is wired in. Claude with
no key but stub vision on is "degraded": it answers, but with hardcoded data.
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from api import voice
from data import db

router = APIRouter()

Status = Literal["ok", "degraded", "down"]
_RANK = {"ok": 0, "degraded": 1, "down": 2}
SUPABASE_DEGRADED_MS = 1000           # spec 3.2: over 1000 ms is "degraded"


class Upstreams(BaseModel):
    claude: Status
    cartesia: Status
    moss: Status
    nessie: Status
    supabase: Status


class HealthResponse(BaseModel):
    status: Status
    upstreams: Upstreams


def _configured(*env_names: str) -> Status:
    return "ok" if all(os.environ.get(name) for name in env_names) else "down"


def _claude() -> Status:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "ok"
    # Tiea's vision module returns hardcoded Advil while REWIND_STUB_VISION is true (its default)
    stub = os.environ.get("REWIND_STUB_VISION", "true").lower() == "true"
    return "degraded" if stub else "down"


def _supabase() -> Status:
    probe = db.health()
    if not probe["reachable"]:
        return "down"
    return "degraded" if probe["latency_ms"] > SUPABASE_DEGRADED_MS else "ok"


@router.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:      # sync on purpose: runs in a worker thread, not the event loop
    upstreams = Upstreams(
        claude=_claude(),
        cartesia=voice.cartesia_status(),
        moss=_configured("MOSS_PROJECT_ID", "MOSS_PROJECT_KEY"),
        nessie=_configured("NESSIE_API_KEY"),
        supabase=_supabase(),
    )
    worst = max(upstreams.model_dump().values(), key=_RANK.__getitem__)
    return HealthResponse(status=worst, upstreams=upstreams)
