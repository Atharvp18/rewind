"""POST /v1/frame-check: is an item in the frame (stub vision keeps tests offline)."""
import pytest
from fastapi.testclient import TestClient

from main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_a_frame_with_an_item_says_so(client):
    r = client.post("/v1/frame-check", files={"image": ("a.jpg", b"stub:advil", "image/jpeg")})
    assert r.status_code == 200 and r.json() == {"item_in_frame": True}


def test_an_empty_frame_says_so(client):
    r = client.post("/v1/frame-check", files={"image": ("a.jpg", b"stub:empty", "image/jpeg")})
    assert r.json() == {"item_in_frame": False}


def test_no_image_is_a_bad_request(client):
    r = client.post("/v1/frame-check", files={"image": ("a.jpg", b"", "image/jpeg")})
    assert r.status_code == 400 or r.status_code == 422
