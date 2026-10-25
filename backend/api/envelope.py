"""The error envelope (technical spec 0.6) and the handlers that produce it.

Every 4xx and 5xx returns the same shape, so the app has one error handler:

    {"error": {"code": "E_PROMPT_EXPIRED", "message": "...", "speech": "...", "retryable": true}}

`speech` is always present and always safe to speak aloud. `message` is safe to log:
it never carries API keys, card numbers, or transcripts.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from data import db
from payments import nessie

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    speech: str
    retryable: bool


class ErrorEnvelope(BaseModel):
    error: ErrorBody


# code -> (HTTP status, spoken wording, retryable). Wording quoted from spec 0.6 and 0.7;
# add a row here when an endpoint needs a new code, so `speech` is never written elsewhere.
ERRORS: dict[str, tuple[int, str, bool]] = {
    "E_DB_UNAVAILABLE": (503, "I can't reach your cart right now. Let me try again", True),
    "E_PROMPT_EXPIRED": (409, "I didn't catch that in time. Shall I ask again?", True),
    "E_UPSTREAM_TIMEOUT": (504, "Sorry, that took too long. Let me try again", True),
    "E_STT_LOW_CONFIDENCE": (422, "I didn't catch that. You can say add that, skip it, or checkout.", True),
    "E_STT_UNAVAILABLE": (503, "Sorry, I couldn't hear that. Let me try again", True),
    # not retryable on purpose: the app speaks the reply with expo-speech instead (spec 3.9)
    "E_TTS_UNAVAILABLE": (503, "Sorry, my voice isn't working right now", False),
    "E_BAD_REQUEST": (422, "Sorry, I couldn't understand that request", False),
    "E_NOT_FOUND": (404, "Sorry, I couldn't find that", False),
    # presenter demo only (POST /v1/demo/decline-next): the simulated card is declined once
    "E_CARD_DECLINED": (402, "The payment didn't go through, and nothing was charged. "
                             "Say checkout to try again with another card", False),
    "E_NESSIE_UNAVAILABLE": (503, "Sorry, I can't check your balance right now. Let me try again", True),
    "E_INTERNAL": (500, "Sorry, something went wrong. Let me try again", True),
}


class ApiError(Exception):
    """Raise this from any endpoint. `code` must be a key of ERRORS."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        if code not in ERRORS:
            raise KeyError(f"unknown error code {code!r}; add it to ERRORS in api/envelope.py")
        self.code = code
        self.message = message or code


def _respond(code: str, message: str) -> JSONResponse:
    status, speech, retryable = ERRORS[code]
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, speech=speech, retryable=retryable))
    return JSONResponse(status_code=status, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _respond(exc.code, exc.message)

    @app.exception_handler(db.DBUnavailable)
    async def _db_unavailable(_: Request, exc: db.DBUnavailable) -> JSONResponse:
        return _respond("E_DB_UNAVAILABLE", str(exc))

    @app.exception_handler(nessie.NessieUnavailable)
    async def _nessie_unavailable(_: Request, exc: nessie.NessieUnavailable) -> JSONResponse:
        return _respond("E_NESSIE_UNAVAILABLE", str(exc))

    @app.exception_handler(db.PromptExpired)
    async def _prompt_expired(_: Request, exc: db.PromptExpired) -> JSONResponse:
        return _respond("E_PROMPT_EXPIRED", "prompt unknown, expired, used, or wrong scope")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # loc and msg only: pydantic's `input` can echo user data, which must not reach logs
        detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return _respond("E_BAD_REQUEST", detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "E_NOT_FOUND" if exc.status_code == 404 else "E_BAD_REQUEST"
        response = _respond(code, f"HTTP {exc.status_code}")
        response.status_code = exc.status_code
        return response

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return _respond("E_INTERNAL", type(exc).__name__)     # class name only, never the text
