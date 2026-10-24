"""The last thing spoken, so "read it again" can repeat it verbatim (technical spec 3.8).

One process-wide slot: the demo has one shopper. A restart or a demo reset clears it.
"""
from __future__ import annotations

from models.schemas import VoiceRequest

_last: VoiceRequest | None = None


def remember(voice: VoiceRequest) -> VoiceRequest:
    global _last
    _last = voice
    return voice


def last() -> VoiceRequest | None:
    return _last


def forget() -> None:
    global _last
    _last = None
