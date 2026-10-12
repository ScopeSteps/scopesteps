from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scopesteps.api import health
from scopesteps.api.errors import ERROR_RESPONSES, register_error_handlers
from scopesteps.api.modules import load_router
from scopesteps.api.request_id import HEADER as REQUEST_ID_HEADER
from scopesteps.api.request_id import RequestIdMiddleware
from scopesteps.api.seed import LOCAL_REVIEWER_ID
from scopesteps.api.settings import Settings, get_settings
from scopesteps.identity.http.auth import LocalDevelopmentAuth, get_current_actor
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = create_database_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="ScopeSteps API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
    )
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.auth = LocalDevelopmentAuth(user_id=LOCAL_REVIEWER_ID)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    for module_name in settings.enabled_modules:
        app.include_router(
            load_router(module_name),
            prefix=API_PREFIX,
            responses=ERROR_RESPONSES,
            dependencies=[Depends(get_current_actor)],
        )
    return app
