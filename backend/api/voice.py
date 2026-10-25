"""Voice relay to Cartesia (technical spec 3.9). The backend holds the key; the app sends audio
and text and never talks to Cartesia.

  POST /v1/stt         audio in            -> transcript   (Cartesia Ink, batch)
  POST /v1/tts         text in             -> one audio file per sentence (Cartesia Sonic)
  GET  /v1/audio/{id}  fetch one sentence  -> mp3 bytes

TTS flow: the first sentence is synthesised before /v1/tts answers, so a Cartesia failure is
reported at once (the app then speaks with expo-speech) and the first audio is ready to play.
The remaining sentences are synthesised in the background; /v1/audio/{id} waits for its file,
so the app can start playing sentence 1 while sentences 2..n are still being made.

Nothing here logs a transcript or the text being spoken.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time
import uuid
import wave
from contextlib import suppress
from pathlib import Path
from typing import Literal

import cartesia
import httpx
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.envelope import ApiError
from speech.sentences import split_sentences

logger = logging.getLogger(__name__)
router = APIRouter()

STT_MODEL = "ink-whisper"
DEFAULT_TTS_MODEL = "sonic-3"
# Small mp3 at 24 kHz: speech quality is fine and each file downloads fast.
OUTPUT_FORMAT = {"container": "mp3", "sample_rate": 24000, "bit_rate": 64000}

# Sonic-3 volume, 0.5 to 2.0 (1.0 is the default and played quietly on a phone speaker).
TTS_VOLUME = float(os.environ.get("CARTESIA_VOLUME", "1.8"))
FIRST_SENTENCE_TIMEOUT_S = 4.0       # spec 0.7 said 1.5 s; too tight on a phone connection, so the app fell back to expo-speech
LATER_SENTENCE_TIMEOUT_S = 10.0
STT_TIMEOUT_S = 6.0
KEEPALIVE_S = 60                     # spec 0.7
AUDIO_TTL_S = 600                    # spec 0.6: audio files are deleted after 10 minutes
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_SENTENCES = 20
MAX_TTS_CONCURRENCY = 3
PCM_SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)
_AUDIO_ID = re.compile(r"^[0-9a-f]{32}$")


# --- Cartesia client ----------------------------------------------------------------------------

_client: cartesia.AsyncCartesia | None = None


def get_client() -> cartesia.AsyncCartesia:
    """One shared client. Retries are off (they would blow the 1.5 s budget) and idle connections
    are kept for 2 minutes so the 60 s keepalive actually keeps the TLS session warm."""
    global _client
    if _client is None:
        _client = cartesia.AsyncCartesia(
            api_key=os.environ["CARTESIA_API_KEY"],
            max_retries=0,
            http_client=cartesia.DefaultAsyncHttpxClient(
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5, keepalive_expiry=120)),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        with suppress(Exception):
            await _client.close()
        _client = None


def _voice_id() -> str | None:
    return os.environ.get("CARTESIA_VOICE_ID") or None


def _tts_model() -> str:
    return os.environ.get("CARTESIA_TTS_MODEL") or DEFAULT_TTS_MODEL


# --- keepalive and health -----------------------------------------------------------------------

_state: dict = {"ok_at": None, "error": None}


async def warm_once() -> bool:
    """One cheap authenticated request: keeps the connection warm and checks key and voice id."""
    voice_id = _voice_id()
    if not os.environ.get("CARTESIA_API_KEY") or not voice_id:
        return False
    try:
        await get_client().voices.get(voice_id, timeout=5.0)
    except Exception as e:  # noqa: BLE001 - a failed warm-up only flips the health status
        _state.update(ok_at=None, error=type(e).__name__)
        logger.warning("Cartesia warm-up failed: %s", type(e).__name__)
        return False
    _state.update(ok_at=time.monotonic(), error=None)
    return True


async def keepalive_loop() -> None:
    while True:
        await warm_once()
        await asyncio.sleep(KEEPALIVE_S)


def cartesia_status() -> Literal["ok", "degraded", "down"]:
    """down: cannot work (no key or voice id, or the last warm-up failed).
    degraded: configured but not confirmed recently. ok: confirmed within three keepalives."""
    if not os.environ.get("CARTESIA_API_KEY") or not _voice_id() or _state["error"]:
        return "down"
    ok_at = _state["ok_at"]
    if ok_at is None or time.monotonic() - ok_at > 3 * KEEPALIVE_S:
        return "degraded"
    return "ok"


# --- speech to text -----------------------------------------------------------------------------

class STTResponse(BaseModel):
    transcript: str
    # Cartesia's batch transcription returns no confidence value, so this is always null.
    # An empty transcript is reported as E_STT_LOW_CONFIDENCE instead; commands that spend or
    # remove something are read back before they run (spec 3.8), which covers a wrong transcript.
    confidence: float | None = None


def _as_wav(data: bytes, encoding: str, sample_rate: int) -> bytes:
    """The app sends a WAV file or raw 16-bit mono PCM. Raw PCM is wrapped in a WAV header."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data
    if encoding != "pcm_s16le":
        raise ApiError("E_BAD_REQUEST", f"unsupported encoding {encoding!r}; send wav or pcm_s16le")
    if sample_rate not in PCM_SAMPLE_RATES:
        raise ApiError("E_BAD_REQUEST", f"unsupported sample_rate {sample_rate}")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(data)
    return out.getvalue()


@router.post("/v1/stt", response_model=STTResponse)
async def stt(audio: UploadFile = File(...), encoding: str = Form("pcm_s16le"),
              sample_rate: int = Form(16000)) -> STTResponse:
    if not os.environ.get("CARTESIA_API_KEY"):
        raise ApiError("E_STT_UNAVAILABLE", "CARTESIA_API_KEY is not set")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise ApiError("E_BAD_REQUEST", "audio larger than 10 MB")
    if not data:
        raise ApiError("E_STT_LOW_CONFIDENCE", "empty audio")
    wav = _as_wav(data, encoding, sample_rate)

    try:
        result = await asyncio.wait_for(
            get_client().stt.transcribe(file=("speech.wav", wav, "audio/wav"), model=STT_MODEL, language="en"),
            STT_TIMEOUT_S)
    except (asyncio.TimeoutError, cartesia.APITimeoutError, cartesia.APIConnectionError) as e:
        raise ApiError("E_UPSTREAM_TIMEOUT", f"speech to text: {type(e).__name__}") from e
    except (cartesia.BadRequestError, cartesia.UnprocessableEntityError) as e:
        # Cartesia rejected the audio itself (for example a recording with no frames, from a
        # push-to-talk released at once). To the user that is "I didn't catch that", not an outage.
        raise ApiError("E_STT_LOW_CONFIDENCE", f"audio rejected: {type(e).__name__}") from e
    except cartesia.CartesiaError as e:
        raise ApiError("E_STT_UNAVAILABLE", f"speech to text: {type(e).__name__}") from e

    transcript = (result.text or "").strip()
    if not re.search(r"\w", transcript):
        raise ApiError("E_STT_LOW_CONFIDENCE", "no words in the transcript")
    return STTResponse(transcript=transcript)


# --- text to speech -----------------------------------------------------------------------------

class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    # Interruption and replay are the app's playback queue (spec 1.4); the relay only echoes
    # nothing back, so this is accepted and not used here.
    priority: Literal["alert", "normal"] = "normal"


class SentenceAudio(BaseModel):
    index: int
    text: str
    audio_url: str


class TTSResponse(BaseModel):
    request_id: str
    sentences: list[SentenceAudio]


class AudioStore:
    """Synthesis tasks and the mp3 files they write. Files live 10 minutes (spec 0.6)."""

    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, asyncio.Task] = {}
        self.created: dict[str, float] = {}

    def path(self, audio_id: str) -> Path:
        return self.dir / f"{audio_id}.mp3"

    def register(self, audio_id: str, task: asyncio.Task) -> None:
        # Mark failures as seen: a failed sentence nobody fetched must not log "never retrieved".
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        self.tasks[audio_id] = task
        self.created[audio_id] = time.monotonic()

    def drop(self, audio_id: str) -> None:
        task = self.tasks.pop(audio_id, None)
        if task and not task.done():
            task.cancel()
        self.created.pop(audio_id, None)
        with suppress(FileNotFoundError):
            self.path(audio_id).unlink()

    def purge(self, ttl_s: float = AUDIO_TTL_S) -> None:
        now = time.monotonic()
        for audio_id in [i for i, t in self.created.items() if now - t > ttl_s]:
            self.drop(audio_id)

    def clear(self) -> None:
        """Delete every file, including ones left by a previous run."""
        for audio_id in list(self.created):
            self.drop(audio_id)
        for file in self.dir.glob("*.mp3"):
            with suppress(FileNotFoundError):
                file.unlink()


def _default_dir() -> Path:
    return Path(os.environ.get("AUDIO_TMP_DIR") or Path(__file__).resolve().parent.parent / "audio_tmp")


store = AudioStore(_default_dir())
_slot_state: dict = {"loop": None, "semaphore": None}


def _slots() -> asyncio.Semaphore:
    """At most MAX_TTS_CONCURRENCY Cartesia requests at once. Made per event loop, because a
    semaphore that waited on one loop cannot be reused on another (tests start several)."""
    loop = asyncio.get_running_loop()
    if _slot_state["loop"] is not loop:
        _slot_state.update(loop=loop, semaphore=asyncio.Semaphore(MAX_TTS_CONCURRENCY))
    return _slot_state["semaphore"]


async def _synthesize(text: str, audio_id: str, timeout_s: float) -> Path:
    async with _slots():
        response = await get_client().tts.generate(
            model_id=_tts_model(), transcript=text, voice={"id": _voice_id()},
            output_format=OUTPUT_FORMAT, language="en", timeout=timeout_s,
            generation_config={"volume": TTS_VOLUME})
        audio = await response.read()
    if not audio:
        raise RuntimeError("Cartesia returned no audio")
    path = store.path(audio_id)
    await asyncio.to_thread(path.write_bytes, audio)
    return path


def _tts_error(e: BaseException) -> ApiError:
    return ApiError("E_TTS_UNAVAILABLE", f"text to speech: {type(e).__name__}")


@router.post("/v1/tts", response_model=TTSResponse)
async def tts(body: TTSRequest, request: Request) -> TTSResponse:
    sentences = split_sentences(body.text)
    if not sentences:
        raise ApiError("E_BAD_REQUEST", "no text to speak")
    if len(sentences) > MAX_SENTENCES:
        raise ApiError("E_BAD_REQUEST", f"more than {MAX_SENTENCES} sentences")
    if not os.environ.get("CARTESIA_API_KEY") or not _voice_id():
        raise ApiError("E_TTS_UNAVAILABLE", "CARTESIA_API_KEY or CARTESIA_VOICE_ID is not set")

    store.purge()
    ids = [uuid.uuid4().hex for _ in sentences]
    for i, (audio_id, text) in enumerate(zip(ids, sentences)):
        timeout_s = FIRST_SENTENCE_TIMEOUT_S if i == 0 else LATER_SENTENCE_TIMEOUT_S
        store.register(audio_id, asyncio.create_task(_synthesize(text, audio_id, timeout_s)))

    try:
        await asyncio.wait_for(asyncio.shield(store.tasks[ids[0]]), FIRST_SENTENCE_TIMEOUT_S)
    except BaseException as e:                       # includes cancellation of this request
        for audio_id in ids:
            store.drop(audio_id)
        if isinstance(e, (Exception, asyncio.TimeoutError)):
            raise _tts_error(e) from e
        raise

    return TTSResponse(
        request_id=uuid.uuid4().hex,
        sentences=[SentenceAudio(index=i, text=text,
                                 audio_url=str(request.url_for("get_audio", audio_id=audio_id)))
                   for i, (audio_id, text) in enumerate(zip(ids, sentences))])


@router.get("/v1/audio/{audio_id}", name="get_audio")
async def get_audio(audio_id: str) -> FileResponse:
    if not _AUDIO_ID.match(audio_id):
        raise ApiError("E_NOT_FOUND", "no such audio")
    store.purge()
    task = store.tasks.get(audio_id)
    if task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(task), LATER_SENTENCE_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 - any synthesis failure reaches the app as one error
            raise _tts_error(e) from e
    path = store.path(audio_id)
    if not path.exists():
        raise ApiError("E_NOT_FOUND", "no such audio")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
