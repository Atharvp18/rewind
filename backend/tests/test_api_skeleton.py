"""Tests for main.py, api/health.py and api/envelope.py. No network."""
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.envelope import ERRORS, ApiError
from data import db
from main import create_app

ENV_NAMES = ("ANTHROPIC_API_KEY", "CARTESIA_API_KEY", "MOSS_PROJECT_ID", "MOSS_PROJECT_KEY",
             "NESSIE_API_KEY", "REWIND_STUB_VISION")


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def set_all_keys(monkeypatch):
    for name in ENV_NAMES[:-1]:
        monkeypatch.setenv(name, "x")


def probe(monkeypatch, reachable=True, latency_ms=50):
    monkeypatch.setattr(db, "health", lambda: {"reachable": reachable, "latency_ms": latency_ms})


# --- /v1/health ---------------------------------------------------------------------------

def test_health_all_ok(clean_env):
    set_all_keys(clean_env)
    probe(clean_env)
    body = TestClient(create_app()).get("/v1/health").json()
    assert body["status"] == "ok"
    assert set(body["upstreams"]) == {"claude", "cartesia", "moss", "nessie", "supabase"}
    assert set(body["upstreams"].values()) == {"ok"}


def test_health_missing_credentials_are_down(clean_env):
    probe(clean_env)
    body = TestClient(create_app()).get("/v1/health").json()
    assert body["upstreams"]["cartesia"] == "down"
    assert body["upstreams"]["moss"] == "down"
    assert body["upstreams"]["nessie"] == "down"
    assert body["status"] == "down"


def test_claude_without_key_is_degraded_in_stub_mode_and_down_otherwise(clean_env):
    probe(clean_env)
    client = TestClient(create_app())
    assert client.get("/v1/health").json()["upstreams"]["claude"] == "degraded"    # stub is the default
    clean_env.setenv("REWIND_STUB_VISION", "false")
    assert client.get("/v1/health").json()["upstreams"]["claude"] == "down"


@pytest.mark.parametrize("reachable,latency,expected", [
    (True, 50, "ok"), (True, 1000, "ok"), (True, 1001, "degraded"), (False, 5, "down")])
def test_supabase_status_thresholds(clean_env, reachable, latency, expected):
    set_all_keys(clean_env)
    probe(clean_env, reachable, latency)
    assert TestClient(create_app()).get("/v1/health").json()["upstreams"]["supabase"] == expected


def test_overall_status_is_the_worst_upstream(clean_env):
    set_all_keys(clean_env)
    probe(clean_env, latency_ms=2000)
    assert TestClient(create_app()).get("/v1/health").json()["status"] == "degraded"


# --- the error envelope -----------------------------------------------------------------

class Body(BaseModel):
    qty: int


def envelope_app():
    app = create_app()

    @app.get("/boom/api")
    def boom_api():
        raise ApiError("E_UPSTREAM_TIMEOUT", "vision took 7000 ms")

    @app.get("/boom/db")
    def boom_db():
        raise db.DBUnavailable("Supabase unreachable: ConnectTimeout")

    @app.get("/boom/prompt")
    def boom_prompt():
        raise db.PromptExpired("p1")

    @app.post("/boom/validate")
    def boom_validate(body: Body):
        return body

    @app.get("/boom/crash")
    def boom_crash():
        raise RuntimeError("secret sk-ant-123 leaked in an exception message")

    return TestClient(app, raise_server_exceptions=False)


def assert_envelope(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert set(error) == {"code", "message", "speech", "retryable"}
    assert error["code"] == code
    assert error["speech"], "speech must always be present"
    return error


def test_api_error_uses_the_table_for_status_speech_and_retryable():
    error = assert_envelope(envelope_app().get("/boom/api"), 504, "E_UPSTREAM_TIMEOUT")
    assert error["speech"] == "Sorry, that took too long. Let me try again"
    assert error["retryable"] is True


def test_database_outage_maps_to_e_db_unavailable():
    error = assert_envelope(envelope_app().get("/boom/db"), 503, "E_DB_UNAVAILABLE")
    assert error["speech"] == "I can't reach your cart right now. Let me try again"


def test_expired_prompt_maps_to_e_prompt_expired():
    assert_envelope(envelope_app().get("/boom/prompt"), 409, "E_PROMPT_EXPIRED")


def test_validation_error_is_enveloped_without_echoing_the_input():
    response = envelope_app().post("/boom/validate", json={"qty": "my-private-transcript"})
    error = assert_envelope(response, 422, "E_BAD_REQUEST")
    assert "my-private-transcript" not in error["message"]
    assert "qty" in error["message"]


def test_unknown_route_is_enveloped_as_404():
    assert_envelope(envelope_app().get("/nope"), 404, "E_NOT_FOUND")


def test_unhandled_exception_never_leaks_its_text():
    response = envelope_app().get("/boom/crash")
    error = assert_envelope(response, 500, "E_INTERNAL")
    assert "sk-ant" not in response.text
    assert error["message"] == "RuntimeError"


def test_unknown_error_code_fails_loudly_at_raise_time():
    with pytest.raises(KeyError):
        ApiError("E_MADE_UP")


def test_every_error_row_is_speakable_and_has_a_valid_status():
    for code, (status, speech, retryable) in ERRORS.items():
        assert code.startswith("E_") and 400 <= status < 600 and speech.strip()
        assert isinstance(retryable, bool)
