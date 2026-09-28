"""Application factory. Run with: uvicorn app.main:create_app --factory"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, load_settings
from app.db import init_db, make_engine, make_session_factory
from app.routes import api, web
from app.seed import seed_if_empty

# uvicorn's own logger, so startup messages appear in the container logs.
logger = logging.getLogger("uvicorn.error")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        if settings.seed_on_startup:
            with session_factory() as session:
                inserted = seed_if_empty(session)
            if inserted:
                logger.info("Seeded %d demo issues", inserted)
            else:
                logger.info("Database is not empty; skipping demo seed")
        yield
        engine.dispose()

    app = FastAPI(
        title="Call Issue Tracker",
        version="1.0.0",
        description="Record and analyze issues found in AI assistant phone calls.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory

    app.include_router(api.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
