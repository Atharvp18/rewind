"""FastAPI app and router registration. Atharv owns this file.

Run from backend/:  .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
API keys come from backend/.env only; the app holds none.
"""
from dotenv import load_dotenv
from fastapi import FastAPI

from api import health
from api.envelope import register_error_handlers

load_dotenv()


def create_app() -> FastAPI:
    app = FastAPI(title="Rewind backend")
    register_error_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
