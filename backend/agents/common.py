"""Shared helpers for the Rewind Fetch.ai agents."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from uagents import Context

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    MetadataContent,
    ResourceContent,
    StartSessionContent,
    TextContent,
)

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_TIMEOUT_S = 10.0


def now() -> datetime:
    return datetime.now(timezone.utc)


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


async def ack(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=now(), acknowledged_msg_id=msg.msg_id),
    )


class Incoming:
    """Flattened view of a ChatMessage's content parts."""

    def __init__(self, msg: ChatMessage):
        self.text = ""
        self.image_url: str | None = None
        self.resource: ResourceContent | None = None
        self.metadata: dict[str, str] = {}
        self.session_started = False
        self.session_ended = False
        for part in msg.content:
            if isinstance(part, TextContent):
                self.text += part.text
            elif isinstance(part, ResourceContent):
                if self.resource is None:
                    self.resource = part
                self.image_url = self.image_url or _find_http_url(part)
            elif isinstance(part, MetadataContent):
                self.metadata.update(part.metadata)
            elif isinstance(part, StartSessionContent):
                self.session_started = True
            elif isinstance(part, EndSessionContent):
                self.session_ended = True
        self.text = self.text.strip()

    def json(self, key: str) -> dict | None:
        raw = self.metadata.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Bad JSON in metadata key %s", key)
            return None


def _as_http_url(value: object) -> str | None:
    if isinstance(value, str):
        parts = urlparse(value)
        if parts.scheme in ("http", "https") and parts.netloc:
            return value
    return None


def _find_http_url(part: ResourceContent) -> str | None:
    resources = part.resource if isinstance(part.resource, list) else [part.resource]
    for res in resources:
        found = _as_http_url(getattr(res, "uri", None))
        if found:
            return found
        meta = getattr(res, "metadata", None) or {}
        for key in ("url", "uri", "source", "image_url"):
            found = _as_http_url(meta.get(key))
            if found:
                return found
    return None


async def download_image(url: str) -> bytes:
    """Fetch an attached image. Bytes stay in memory and are never written to disk."""
    async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT_S, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        if len(resp.content) > MAX_IMAGE_BYTES:
            raise ValueError("image larger than 10 MB")
        return resp.content


def reply(
    text: str,
    metadata: dict[str, object] | None = None,
    end_session: bool = False,
) -> ChatMessage:
    content: list = [TextContent(type="text", text=text)]
    if metadata:
        encoded = {k: v if isinstance(v, str) else json.dumps(v) for k, v in metadata.items()}
        content.append(MetadataContent(type="metadata", metadata=encoded))
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=now(), msg_id=uuid4(), content=content)
