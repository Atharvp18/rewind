"""Tests for api/voice.py. Cartesia is replaced by a fake client: no network, no key."""
import asyncio
import io
import logging
import time
import wave
from types import SimpleNamespace

import cartesia
import httpx
import pytest
from fastapi.testclient import TestClient

from api import voice
from data import db
from main import create_app

REQ = httpx.Request("POST", "http://cartesia.test")


# --- the fake Cartesia client ------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data):
        self._data = data

    async def read(self):
        return self._data


class FakeTTS:
    def __init__(self):
        self.calls, self.delays, self.fail = [], {}, set()
        self.in_flight = self.max_in_flight = 0

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        text = kwargs["transcript"]
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delays.get(text, 0))
            if text in self.fail:
                raise cartesia.APIConnectionError(request=REQ)
            return FakeResponse(b"ID3-" + text.encode())
        finally:
            self.in_flight -= 1


class FakeSTT:
    def __init__(self):
        self.calls, self.text, self.error, self.delay = [], "add that", None, 0

    async def transcribe(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


class FakeVoices:
    def __init__(self):
        self.error, self.calls = None, 0

    async def get(self, voice_id, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(id=voice_id)


class FakeCartesia:
    def __init__(self):
        self.tts, self.stt, self.voices = FakeTTS(), FakeSTT(), FakeVoices()

    async def close(self):
        pass


@pytest.fixture
def fake(monkeypatch, tmp_path):
    fake = FakeCartesia()
    monkeypatch.setattr(voice, "_client", fake)
    monkeypatch.setattr(voice, "store", voice.AudioStore(tmp_path / "audio"))
    monkeypatch.setenv("CARTESIA_API_KEY", "test-key")
    monkeypatch.setenv("CARTESIA_VOICE_ID", "v1")
    monkeypatch.delenv("CARTESIA_TTS_MODEL", raising=False)
    monkeypatch.setitem(voice._state, "ok_at", None)
    monkeypatch.setitem(voice._state, "error", None)
    return fake


@pytest.fixture
def client(fake):
    # as a context manager so every request shares one event loop and the lifespan runs
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


def wav_bytes(frames=160, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return out.getvalue()


def error_of(response, status, code):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["speech"]
    return error


# --- /v1/tts ---------------------------------------------------------------------------------------

def test_tts_returns_one_playable_url_per_sentence(client, fake):
    response = client.post("/v1/tts", json={"text": "One. Two. Three?"})
    assert response.status_code == 200
    body = response.json()
    assert [s["text"] for s in body["sentences"]] == ["One.", "Two.", "Three?"]
    assert [s["index"] for s in body["sentences"]] == [0, 1, 2] and body["request_id"]
    for sentence in body["sentences"]:
        assert sentence["audio_url"].startswith("http://testserver/v1/audio/")
        audio = client.get(sentence["audio_url"])
        assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
        assert audio.content.startswith(b"RIFF")          # raw PCM from Cartesia, made louder, in a WAV file
        assert audio.headers["cache-control"] == "no-store"


def test_tts_asks_cartesia_for_the_configured_voice_model_and_raw_pcm(client, fake):
    client.post("/v1/tts", json={"text": "Hello there."})
    call = fake.tts.calls[0]
    assert call["voice"] == {"id": "v1"} and call["model_id"] == "sonic-3" and call["language"] == "en"
    assert call["output_format"] == {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000}


def test_tts_model_can_be_overridden_from_the_environment(client, fake, monkeypatch):
    monkeypatch.setenv("CARTESIA_TTS_MODEL", "sonic-3.5")
    client.post("/v1/tts", json={"text": "Hello."})
    assert fake.tts.calls[0]["model_id"] == "sonic-3.5"


def test_tts_synthesises_the_first_sentence_first(client, fake):
    client.post("/v1/tts", json={"text": "First. Second. Third."})
    assert fake.tts.calls[0]["transcript"] == "First."


def test_tts_answers_as_soon_as_the_first_sentence_is_ready(client, fake):
    fake.tts.delays["Second."] = 0.4
    t0 = time.perf_counter()
    body = client.post("/v1/tts", json={"text": "First. Second."}).json()
    assert time.perf_counter() - t0 < 0.3                    # did not wait for sentence two
    t1 = time.perf_counter()
    late = client.get(body["sentences"][1]["audio_url"])
    assert late.status_code == 200 and late.content.startswith(b"RIFF")
    assert time.perf_counter() - t1 >= 0.1                   # the fetch waited for the file


def test_tts_failure_on_the_first_sentence_is_reported_at_once_and_not_retryable(client, fake):
    fake.tts.fail.add("One.")
    error = error_of(client.post("/v1/tts", json={"text": "One. Two."}), 503, "E_TTS_UNAVAILABLE")
    assert error["retryable"] is False                       # the app speaks with expo-speech
    assert voice.store.tasks == {} and list(voice.store.dir.glob("*.wav")) == []


def test_tts_first_sentence_timeout_is_reported_and_cleans_up(client, fake, monkeypatch):
    monkeypatch.setattr(voice, "FIRST_SENTENCE_TIMEOUT_S", 0.05)
    fake.tts.delays["One."] = 0.5
    error_of(client.post("/v1/tts", json={"text": "One. Two."}), 503, "E_TTS_UNAVAILABLE")
    assert voice.store.tasks == {} and voice.store.created == {}


def test_tts_failure_on_a_later_sentence_only_fails_that_fetch(client, fake):
    fake.tts.fail.add("Two.")
    body = client.post("/v1/tts", json={"text": "One. Two. Three."}).json()
    urls = [s["audio_url"] for s in body["sentences"]]
    assert client.get(urls[0]).status_code == 200
    error_of(client.get(urls[1]), 503, "E_TTS_UNAVAILABLE")
    assert client.get(urls[2]).status_code == 200


@pytest.mark.parametrize("missing", ["CARTESIA_API_KEY", "CARTESIA_VOICE_ID"])
def test_tts_without_credentials_fails_cleanly_without_calling_cartesia(client, fake, monkeypatch, missing):
    monkeypatch.delenv(missing)
    error_of(client.post("/v1/tts", json={"text": "Hello."}), 503, "E_TTS_UNAVAILABLE")
    assert fake.tts.calls == []


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_tts_rejects_empty_text(client, fake, text):
    error_of(client.post("/v1/tts", json={"text": text}), 422, "E_BAD_REQUEST")
    assert fake.tts.calls == []


def test_tts_rejects_too_many_sentences(client, fake):
    error_of(client.post("/v1/tts", json={"text": "Hi. " * (voice.MAX_SENTENCES + 1)}), 422, "E_BAD_REQUEST")


def test_tts_never_runs_more_than_three_requests_at_once(client, fake):
    for n in range(1, 7):
        fake.tts.delays[f"S{n}."] = 0.1
    body = client.post("/v1/tts", json={"text": " ".join(f"S{n}." for n in range(1, 7))}).json()
    for sentence in body["sentences"]:
        assert client.get(sentence["audio_url"]).status_code == 200
    assert fake.tts.max_in_flight == voice.MAX_TTS_CONCURRENCY


def test_tts_does_not_log_what_it_speaks(client, fake, caplog):
    caplog.set_level(logging.DEBUG)
    fake.tts.fail.add("Your secret diagnosis.")
    client.post("/v1/tts", json={"text": "Your secret diagnosis."})
    assert "diagnosis" not in caplog.text


# --- /v1/audio ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("audio_id", ["..%2F..%2F.env", "not-hex", "ABCDEF", "a" * 31, "a" * 33])
def test_audio_rejects_ids_that_are_not_32_hex_characters(client, audio_id):
    error_of(client.get(f"/v1/audio/{audio_id}"), 404, "E_NOT_FOUND")


def test_audio_unknown_id_is_not_found(client):
    error_of(client.get("/v1/audio/" + "a" * 32), 404, "E_NOT_FOUND")


def test_audio_files_are_deleted_by_purge_and_by_clear(client, fake):
    body = client.post("/v1/tts", json={"text": "One. Two."}).json()
    client.get(body["sentences"][1]["audio_url"])            # wait until both files exist
    assert len(list(voice.store.dir.glob("*.wav"))) == 2
    voice.store.purge(ttl_s=0)
    assert list(voice.store.dir.glob("*.wav")) == [] and voice.store.tasks == {}
    error_of(client.get(body["sentences"][0]["audio_url"]), 404, "E_NOT_FOUND")
    (voice.store.dir / ("b" * 32 + ".wav")).write_bytes(b"left over from a previous run")
    voice.store.clear()
    assert list(voice.store.dir.glob("*.wav")) == []


# --- /v1/stt -------------------------------------------------------------------------------------------

def post_audio(client, data, **form):
    return client.post("/v1/stt", files={"audio": ("speech.bin", data, "application/octet-stream")}, data=form)


def test_stt_passes_a_wav_through_and_returns_the_transcript(client, fake):
    wav = wav_bytes()
    response = post_audio(client, wav)
    assert response.status_code == 200
    assert response.json() == {"transcript": "add that", "confidence": None}
    call = fake.stt.calls[0]
    assert call["file"] == ("speech.wav", wav, "audio/wav")
    assert call["model"] == "ink-whisper" and call["language"] == "en"


def test_stt_wraps_raw_pcm_in_a_wav_header(client, fake):
    pcm = b"\x01\x00" * 100
    assert post_audio(client, pcm, sample_rate="16000").status_code == 200
    sent = fake.stt.calls[0]["file"][1]
    with wave.open(io.BytesIO(sent)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, 100)
        assert w.readframes(100) == pcm


def test_stt_trims_the_transcript(client, fake):
    fake.stt.text = "  checkout \n"
    assert post_audio(client, wav_bytes()).json()["transcript"] == "checkout"


def test_stt_rejects_unsupported_pcm_encoding_and_sample_rate(client, fake):
    error_of(post_audio(client, b"\x00\x00" * 50, encoding="pcm_f32le"), 422, "E_BAD_REQUEST")
    error_of(post_audio(client, b"\x00\x00" * 50, sample_rate="12345"), 422, "E_BAD_REQUEST")
    assert fake.stt.calls == []


def test_stt_empty_audio_is_low_confidence_without_calling_cartesia(client, fake):
    error_of(post_audio(client, b""), 422, "E_STT_LOW_CONFIDENCE")
    assert fake.stt.calls == []


@pytest.mark.parametrize("heard", ["", "   ", "...", "?!"])
def test_stt_a_transcript_with_no_words_is_low_confidence(client, fake, heard):
    fake.stt.text = heard
    error_of(post_audio(client, wav_bytes()), 422, "E_STT_LOW_CONFIDENCE")


@pytest.mark.parametrize("rejected", [cartesia.BadRequestError, cartesia.UnprocessableEntityError])
def test_stt_audio_that_cartesia_rejects_is_low_confidence_not_an_outage(client, fake, rejected):
    status = 400 if rejected is cartesia.BadRequestError else 422
    fake.stt.error = rejected("Invalid file format", response=httpx.Response(status, request=REQ), body=None)
    error = error_of(post_audio(client, wav_bytes(frames=0)), 422, "E_STT_LOW_CONFIDENCE")
    assert error["retryable"] is True


def test_stt_without_a_key_is_unavailable_not_an_internal_error(client, fake, monkeypatch):
    monkeypatch.delenv("CARTESIA_API_KEY")
    error_of(post_audio(client, wav_bytes()), 503, "E_STT_UNAVAILABLE")
    assert fake.stt.calls == []


def test_stt_oversized_audio_is_rejected(client, fake, monkeypatch):
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 10)
    error_of(post_audio(client, b"\x00" * 11), 422, "E_BAD_REQUEST")
    assert fake.stt.calls == []


def test_stt_timeouts_are_retryable_gateway_timeouts(client, fake, monkeypatch):
    fake.stt.error = cartesia.APITimeoutError(request=REQ)
    assert error_of(post_audio(client, wav_bytes()), 504, "E_UPSTREAM_TIMEOUT")["retryable"] is True
    fake.stt.error = None
    monkeypatch.setattr(voice, "STT_TIMEOUT_S", 0.05)
    fake.stt.delay = 0.5
    error_of(post_audio(client, wav_bytes()), 504, "E_UPSTREAM_TIMEOUT")


def test_stt_other_cartesia_errors_are_reported_as_unavailable(client, fake):
    fake.stt.error = cartesia.AuthenticationError("bad key", response=httpx.Response(401, request=REQ), body=None)
    assert error_of(post_audio(client, wav_bytes()), 503, "E_STT_UNAVAILABLE")["retryable"] is True


def test_stt_does_not_log_the_transcript_or_the_error_text(client, fake, caplog):
    caplog.set_level(logging.DEBUG)
    fake.stt.text = "my private prescription"
    post_audio(client, wav_bytes())
    fake.stt.error = cartesia.CartesiaError("leaked sk-secret-123")
    response = post_audio(client, wav_bytes())
    assert "prescription" not in caplog.text and "sk-secret" not in caplog.text
    assert "sk-secret" not in response.text


# --- keepalive and health status -------------------------------------------------------------------------

def test_status_matrix(fake, monkeypatch):
    assert voice.cartesia_status() == "degraded"                       # configured, not confirmed yet
    voice._state["ok_at"] = time.monotonic()
    assert voice.cartesia_status() == "ok"
    voice._state["ok_at"] = time.monotonic() - 3 * voice.KEEPALIVE_S - 1
    assert voice.cartesia_status() == "degraded"                       # stale
    voice._state.update(ok_at=time.monotonic(), error="AuthenticationError")
    assert voice.cartesia_status() == "down"
    voice._state["error"] = None
    monkeypatch.delenv("CARTESIA_VOICE_ID")
    assert voice.cartesia_status() == "down"
    monkeypatch.setenv("CARTESIA_VOICE_ID", "v1")
    monkeypatch.delenv("CARTESIA_API_KEY")
    assert voice.cartesia_status() == "down"


async def test_warm_once_success_marks_ok_and_clears_an_old_error(fake):
    voice._state["error"] = "APIConnectionError"
    assert await voice.warm_once() is True
    assert voice._state["error"] is None and voice.cartesia_status() == "ok"
    assert fake.voices.calls == 1


async def test_warm_once_failure_marks_down_without_raising(fake):
    fake.voices.error = cartesia.AuthenticationError("bad", response=httpx.Response(401, request=REQ), body=None)
    assert await voice.warm_once() is False
    assert voice._state["error"] == "AuthenticationError" and voice.cartesia_status() == "down"


async def test_warm_once_without_credentials_does_nothing(fake, monkeypatch):
    monkeypatch.delenv("CARTESIA_VOICE_ID")
    assert await voice.warm_once() is False and fake.voices.calls == 0


def test_the_app_warms_cartesia_on_startup_and_health_reports_it(fake, monkeypatch):
    monkeypatch.setattr(db, "health", lambda: {"reachable": True, "latency_ms": 5})   # no real Supabase call
    with TestClient(create_app()) as c:
        for _ in range(40):
            if voice.cartesia_status() == "ok":
                break
            time.sleep(0.05)
        assert c.get("/v1/health").json()["upstreams"]["cartesia"] == "ok"
    assert fake.voices.calls >= 1
