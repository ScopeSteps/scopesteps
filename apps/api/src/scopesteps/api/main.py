from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scopesteps.agent.client import (
    MAX_MESSAGE_CHARS,
    MICROUSD_PER_USD,
    AgentRuntime,
    RunLimits,
    ServedModel,
    create_model_provider,
)
from scopesteps.api import health
from scopesteps.api.cross_site import CrossSiteRequestGuard
from scopesteps.api.errors import ERROR_RESPONSES, register_error_handlers
from scopesteps.api.modules import load_router
from scopesteps.api.request_id import HEADER as REQUEST_ID_HEADER
from scopesteps.api.request_id import RequestIdMiddleware
from scopesteps.api.seed import LOCAL_REVIEWER_ID
from scopesteps.api.settings import Settings, get_settings
from scopesteps.api.source_usage import resolve_source_usage_reader
from scopesteps.backlog.client import MAX_EPICS, MAX_STORIES, get_decision_reader
from scopesteps.change_control.http.router import resolve_decision_reader
from scopesteps.identity.client import (
    get_actor,
    get_memberships,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.identity.domain.session import SessionPolicy
from scopesteps.identity.http.auth import (
    LocalDevelopmentAuth,
    SessionAuth,
    get_current_actor,
    resolve_memberships,
    resolve_project_access,
    resolve_project_access_resolver,
    session_cookie,
)
from scopesteps.identity.http.router import public_router as identity_public_router
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.infrastructure.database import create_database_engine, create_session_factory
from scopesteps.projects.client import get_people_recorder, get_project_reader
from scopesteps.projects.domain.limits import ProjectLimits
from scopesteps.projects.http.dependencies import resolve_people_recorder
from scopesteps.projects.http.router import resolve_project_reader
from scopesteps.sources.client import get_source_usage_reader
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
    app.state.auth = authentication(settings)
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
        message_max_chars=MAX_MESSAGE_CHARS,
    )
    app.dependency_overrides[get_actor] = get_current_actor
    app.dependency_overrides[get_decision_reader] = resolve_decision_reader
    app.dependency_overrides[get_memberships] = resolve_memberships
    app.dependency_overrides[get_project_reader] = resolve_project_reader
    app.dependency_overrides[get_project_access] = resolve_project_access
    app.dependency_overrides[get_project_access_resolver] = resolve_project_access_resolver
    app.dependency_overrides[get_people_recorder] = resolve_people_recorder
    app.dependency_overrides[get_source_usage_reader] = resolve_source_usage_reader

    # Added first so it runs innermost: its refusals still get CORS headers and a request ID.
    app.add_middleware(CrossSiteRequestGuard, trusted_origins=settings.cors_allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        # The export download name, for a web app served from another origin.
        expose_headers=[REQUEST_ID_HEADER, "Content-Disposition"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    if "identity" in settings.enabled_modules:
        app.include_router(identity_public_router, prefix=API_PREFIX, responses=ERROR_RESPONSES)
    for module_name in settings.enabled_modules:
        app.include_router(
            load_router(module_name),
            prefix=API_PREFIX,
            responses=ERROR_RESPONSES,
            dependencies=[Depends(get_current_actor)],
        )
    return app


def authentication(settings: Settings) -> LocalDevelopmentAuth | SessionAuth:
    if settings.auth_mode == "local":
        return LocalDevelopmentAuth(user_id=LOCAL_REVIEWER_ID)
    return SessionAuth(
        cookie=session_cookie(secure=not settings.is_local_environment),
        policy=SessionPolicy(
            absolute_lifetime=timedelta(minutes=settings.session_absolute_lifetime_minutes),
            idle_timeout=timedelta(minutes=settings.session_idle_timeout_minutes),
        ),
        hasher=Argon2PasswordHasher(),
    )


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
