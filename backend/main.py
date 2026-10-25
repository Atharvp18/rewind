"""FastAPI app and router registration. Atharv owns this file.

Run from backend/:  .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
API keys come from backend/.env only; the app holds none.
"""
import asyncio
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI

from api import cart, checkout, command, demo, health, prompts, scan, voice
from lookup import moss_index
from api.envelope import register_error_handlers

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    voice.store.clear()                          # drop audio left behind by a previous run
    keepalive = None
    if os.environ.get("CARTESIA_API_KEY"):
        keepalive = asyncio.create_task(voice.keepalive_loop())     # warm now, then every 60 s
    moss = None
    if os.environ.get("MOSS_PROJECT_ID"):
        moss = asyncio.create_task(moss_index.warm_up())        # the first scan must not pay for the index load
    try:
        yield
    finally:
        if moss:
            moss.cancel()
            with suppress(asyncio.CancelledError):
                await moss
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
    for module in (scan, cart, checkout, command, demo, prompts):
        app.include_router(module.router)
    return app


app = create_app()
