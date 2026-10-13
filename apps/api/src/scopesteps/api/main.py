from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scopesteps.agent.client import (
    MICROUSD_PER_USD,
    AgentRuntime,
    RunLimits,
    ServedModel,
    create_model_provider,
)
from scopesteps.api import health
from scopesteps.api.errors import ERROR_RESPONSES, register_error_handlers
from scopesteps.api.modules import load_router
from scopesteps.api.request_id import HEADER as REQUEST_ID_HEADER
from scopesteps.api.request_id import RequestIdMiddleware
from scopesteps.api.seed import LOCAL_REVIEWER_ID
from scopesteps.api.settings import Settings, get_settings
from scopesteps.backlog.client import MAX_EPICS, MAX_STORIES
from scopesteps.identity.client import (
    get_actor,
    get_memberships,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.identity.http.auth import (
    LocalDevelopmentAuth,
    get_current_actor,
    resolve_memberships,
    resolve_project_access,
    resolve_project_access_resolver,
)
from scopesteps.infrastructure.database import create_database_engine, create_session_factory
from scopesteps.projects.client import get_project_reader
from scopesteps.projects.domain.limits import ProjectLimits
from scopesteps.projects.http.router import resolve_project_reader
from scopesteps.sources.domain.upload import SourceLimits

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
    app.state.agent_runtime = agent_runtime(settings)
    app.state.source_limits = SourceLimits(
        max_bytes=settings.source_max_bytes, max_words=settings.source_max_words
    )
    app.state.project_limits = ProjectLimits(
        source_max_bytes=settings.source_max_bytes,
        source_max_words=settings.source_max_words,
        run_max_turns=settings.run_max_turns,
        run_max_tool_calls=settings.run_max_tools,
        run_max_clarification_rounds=settings.run_max_clarification_rounds,
        backlog_max_epics=MAX_EPICS,
        backlog_max_stories=MAX_STORIES,
    )
    app.dependency_overrides[get_actor] = get_current_actor
    app.dependency_overrides[get_memberships] = resolve_memberships
    app.dependency_overrides[get_project_reader] = resolve_project_reader
    app.dependency_overrides[get_project_access] = resolve_project_access
    app.dependency_overrides[get_project_access_resolver] = resolve_project_access_resolver

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


def agent_runtime(settings: Settings) -> AgentRuntime:
    config = settings.active_model()
    provider = None if config is None else create_model_provider(config)
    backup = settings.fallback_model()
    fallback = (
        None
        if backup is None
        else ServedModel(create_model_provider(backup), backup.provider, backup.model_id)
    )
    return AgentRuntime(
        provider=provider,
        provider_name=settings.model_provider,
        model_id="" if config is None else config.model_id,
        limits=RunLimits(
            max_turns=settings.run_max_turns,
            max_tool_calls=settings.run_max_tools,
            max_output_tokens_per_call=settings.run_max_output_tokens,
            max_total_tokens=settings.run_max_total_tokens,
            max_cost_microusd=_microusd(settings.run_cost_limit_usd),
        ),
        max_clarification_rounds=settings.run_max_clarification_rounds,
        project_cost_limit_microusd=_microusd(settings.project_cost_limit_usd),
        lease_seconds=settings.run_lease_seconds,
        fallback=fallback,
    )


def _microusd(usd: Decimal | None) -> int | None:
    return None if usd is None else int(usd * MICROUSD_PER_USD)
