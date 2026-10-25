"""Sentence splitting for spoken replies (technical spec 0.5 and 3.9).

One splitter for both sides: compose.py fills VoiceRequest.sentences with it and /v1/tts uses it
on the text it is given, so the app's captions and the audio files always line up.
"""
from __future__ import annotations

import re

# A sentence ends at . ! or ? followed by whitespace. "$12.99" and "200mg." mid-line survive
# because the period there is followed by a digit or the end, not a space.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


# A period after these is not the end of a sentence ("Dr. Lee").
_ABBREVIATIONS = ("dr.", "mr.", "mrs.", "ms.", "vs.")


def split_sentences(text: str) -> list[str]:
    merged: list[str] = []
    for piece in (s.strip() for s in _BOUNDARY.split(text.strip())):
        if not piece:
            continue
        if merged and merged[-1].lower().endswith(_ABBREVIATIONS) and merged[-1].split()[-1].lower() in _ABBREVIATIONS:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged
