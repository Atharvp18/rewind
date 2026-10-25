"""Turns a fact sheet into natural speech without letting the facts drift.

Code decides WHAT is said (a Facts object: a deterministic template plus the
strings that must appear verbatim). Claude Haiku decides HOW it is said. The
rendered sentence is accepted only if every required fact is present verbatim
and no number appears that was not in the facts; otherwise the template is
spoken. Facts marked fixed (refusals) are never rephrased.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MODEL = os.environ.get("SPEAK_MODEL", "claude-haiku-5-5")
TIMEOUT_S = float(os.environ.get("SPEAK_TIMEOUT_S", "10.0"))
STUB_MODE = os.environ.get("REWIND_STUB_SPEAK", "false").lower() == "true"

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class Facts:
    template: str
    must_say: list[str] = field(default_factory=list)
    fixed: bool = False
    alert: str | None = None  # e.g. "low_balance": the phone plays a beep before speaking

    def __contains__(self, item: str) -> bool:
        return item in self.template

    def __str__(self) -> str:
        return self.template


# No price read: low-vision users can't read the tag, so guide a closer photo first.
PRICE_RETRY = ("Hold your phone a little closer to the price tag on the shelf, just below the item, and take another photo. If someone nearby can read it to you, you can also just say the price.")


def say(template: str, *must_say: str, fixed: bool = False, alert: str | None = None) -> Facts:
    return Facts(template=template, must_say=[m for m in must_say if m], fixed=fixed, alert=alert)


SYSTEM_PROMPT = """\
You voice Rewind, a shopping assistant for elderly and low-vision people. \
Say the given statement the way a kind, unhurried person would say it aloud: one or two short, \
warm, plain sentences, in the middle of a conversation, not at the start of a new one.
If a conversation so far is given, answer what the person just said: pick up their words, \
do not repeat an opening you already used, and do not read out a list of things you can do. \
Sound like one person talking, never like a menu or a form.

Rules you must not break:
- Include every string under REQUIRED exactly as written, character for character.
- Do not add any number, price, balance, product, card, or claim that is not in the statement.
- Do not give advice, opinions, or explanations beyond the statement.
- If the statement asks a question, end with that question.
- Reply with the sentences only."""


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def why_invalid(rendered: str, facts: Facts) -> str | None:
    """None if the rendering is safe to speak, else the reason it is not."""
    if not rendered:
        return "empty"
    if len(rendered) > 400:
        return "too long"
    missing = [m for m in facts.must_say if m not in rendered]
    if missing:
        return f"missing {missing}"
    allowed = _numbers(facts.template).union(*(_numbers(m) for m in facts.must_say))
    extra = _numbers(rendered) - allowed
    if extra:
        return f"invented numbers {sorted(extra)}"
    return None


def validate(rendered: str, facts: Facts) -> bool:
    return why_invalid(rendered, facts) is None


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic()
    return _client


async def _render_with_claude(facts: Facts, recent: str = "") -> str:
    required = "\n".join(f"- {m}" for m in facts.must_say) or "- (none)"
    earlier = f"CONVERSATION SO FAR:\n{recent}\n\n" if recent else ""
    user = f"{earlier}STATEMENT TO SAY NEXT:\n{facts.template}\n\nREQUIRED:\n{required}"
    response = await _get_client().messages.create(
        model=MODEL,
        max_tokens=200,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in response.content if b.type == "text").strip()


async def render(facts: Facts | str, recent: str = "") -> str:
    """Natural phrasing of the facts, or the template if that cannot be done safely."""
    if isinstance(facts, str):
        return facts
    if facts.fixed or STUB_MODE:
        return facts.template
    try:
        rendered = await asyncio.wait_for(_render_with_claude(facts, recent), TIMEOUT_S)
        reason = why_invalid(rendered, facts)
        if reason is None:
            return rendered
        logger.warning("rendered speech rejected (%s); using template. rendered=%r", reason, rendered)
    except asyncio.TimeoutError:
        logger.warning("speech rendering timed out after %ss", TIMEOUT_S)
    except Exception:
        logger.exception("speech rendering failed")
    return facts.template
