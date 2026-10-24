import os

os.environ.setdefault("REWIND_STUB_INTENT", "true")
os.environ.setdefault("REWIND_STUB_SPEAK", "true")
os.environ.setdefault("REWIND_STUB_VISION", "true")

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
