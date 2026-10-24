"""FastAPI app and router registration. Atharv owns this file.

Run from backend/:  .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
API keys come from backend/.env only; the app holds none.
"""
import asyncio
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI

from api import health, voice
from api.envelope import register_error_handlers

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    voice.store.clear()                          # drop audio left behind by a previous run
    keepalive = None
    if os.environ.get("CARTESIA_API_KEY"):
        keepalive = asyncio.create_task(voice.keepalive_loop())     # warm now, then every 60 s
    try:
        yield
    finally:
        if keepalive:
            keepalive.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive
        await voice.close_client()
        voice.store.clear()


def create_app() -> FastAPI:
    app = FastAPI(title="Rewind backend", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(voice.router)
    return app


app = create_app()
