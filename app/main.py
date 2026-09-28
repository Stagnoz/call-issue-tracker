"""Application factory. Run with: uvicorn app.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, load_settings
from app.db import init_db, make_engine, make_session_factory
from app.routes import api


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
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
    return app
