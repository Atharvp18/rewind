import os

os.environ.setdefault("REWIND_STUB_INTENT", "true")
os.environ.setdefault("REWIND_STUB_SPEAK", "true")
os.environ.setdefault("REWIND_STUB_VISION", "true")
os.environ.setdefault("REWIND_STUB_WEB", "true")

import pytest


@pytest.fixture(autouse=True)
def _offline_db(request, monkeypatch):
    """Tests never touch the real Supabase project. test_data_layer brings its own fake."""
    if request.module.__name__.endswith("test_data_layer"):
        return
    from data import db

    def unavailable():
        raise db.DBUnavailable("tests run offline")
    monkeypatch.setattr(db, "_sb", unavailable)
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)   # everyday tests never query the real index; see scripts/check_moss.py
    if not request.module.__name__.endswith(("test_history", "test_memory_hooks")):
        from lookup import purchase_memory      # no background Moss threads in unrelated tests
        monkeypatch.setattr(purchase_memory, "mirror_payment", lambda payment_id: None)
        monkeypatch.setattr(purchase_memory, "clear_in_background", lambda: None)


@pytest.fixture(autouse=True)
def _fake_moss_index(request, monkeypatch):
    """Eligibility comes only from the Moss index; everyday tests use a small fake of it."""
    if request.module.__name__.endswith("test_hsa_fsa"):
        return
    from tests.fakes import fake_moss
    import api.scan
    from lookup import moss_index
    monkeypatch.setattr(api.scan, "find_match", fake_moss.find_match)
    monkeypatch.setattr(moss_index, "find_match", fake_moss.find_match)      # product_agent imports it inside the call
