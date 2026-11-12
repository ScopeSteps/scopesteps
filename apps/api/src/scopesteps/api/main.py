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
    CircuitBreaker,
    ModelProvider,
    OutcomeSink,
    RunLimits,
    ServedModel,
    Telemetry,
    TraceSink,
    create_model_provider,
    create_replay_provider,
    log_outcome,
    log_sink,
    otlp_telemetry,
    recording,
    request_token_limit,
)
from scopesteps.agent.http.router import resolve_change_outcome_recorder
from scopesteps.api import health
from scopesteps.api.after_approval import resolve_after_approval
from scopesteps.api.cross_site import CrossSiteRequestGuard
from scopesteps.api.errors import ERROR_RESPONSES, register_error_handlers
from scopesteps.api.member_activity import resolve_member_activity
from scopesteps.api.modules import load_router
from scopesteps.api.notification_job import NotificationJob
from scopesteps.api.project_work import resolve_project_work_reader
from scopesteps.api.publish_job import PublishJob
from scopesteps.api.redaction import redact_link_tokens_in_access_log
from scopesteps.api.request_id import HEADER as REQUEST_ID_HEADER
from scopesteps.api.request_id import RequestIdMiddleware
from scopesteps.api.request_origins import resolve_request_origins
from scopesteps.api.seed import LOCAL_REVIEWER_ID
from scopesteps.api.settings import Settings, get_settings
from scopesteps.api.source_usage import resolve_source_usage_reader
from scopesteps.backlog.client import MAX_EPICS, MAX_STORIES, get_decision_reader
from scopesteps.change_control.client import (
    get_after_approval,
    get_change_outcome_recorder,
    get_request_origins,
)
from scopesteps.change_control.http.router import resolve_decision_reader
from scopesteps.identity.application.accounts import Links
from scopesteps.identity.client import (
    get_actor,
    get_member_activity,
    get_memberships,
    get_project_access,
    get_project_access_resolver,
    get_user_directory,
    get_waiting_by_role,
)
from scopesteps.identity.domain.session import SessionPolicy
from scopesteps.identity.http.auth import (
    LocalDevelopmentAuth,
    SessionAuth,
    get_current_actor,
    resolve_memberships,
    resolve_project_access,
    resolve_project_access_resolver,
    resolve_user_directory,
    session_cookie,
)
from scopesteps.identity.http.router import public_router as identity_public_router
from scopesteps.identity.infrastructure.email import SmtpEmailSender, SmtpSettings
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.identity.infrastructure.repository import SqlUserDirectory
from scopesteps.infrastructure.database import create_database_engine, create_session_factory
from scopesteps.jira_integration.client import JiraRuntime, jira_runtime, valid_key
from scopesteps.projects.client import (
    get_people_recorder,
    get_project_reader,
    get_project_work_reader,
    get_speaker_identity_reader,
)
from scopesteps.projects.domain.limits import ProjectLimits
from scopesteps.projects.http.dependencies import (
    resolve_people_recorder,
    resolve_speaker_identity_reader,
)
from scopesteps.projects.http.router import resolve_project_reader, resolve_waiting_by_role
from scopesteps.sources.client import get_source_usage_reader
from scopesteps.sources.domain.upload import SourceLimits

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = create_database_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Tests run a tick themselves, at the time they choose.
        job: NotificationJob = app.state.notification_job
        if settings.app_env != "test":
            job.start(settings.notification_job_interval_seconds)
        publishing: PublishJob = app.state.publish_job
        if settings.app_env != "test" and settings.jira_publish_worker == "in_process":
            publishing.start(settings.jira_publish_interval_seconds)
        yield
        publishing.stop()
        job.stop()
        if telemetry is not None:
            telemetry.shutdown()
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
    app.state.links = Links(base_url=settings.app_base_url.rstrip("/"))
    app.state.email_sender = SmtpEmailSender(
        SmtpSettings(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.email_from,
            username=settings.smtp_username,
            password=None
            if settings.smtp_password is None
            else settings.smtp_password.get_secret_value(),
        )
    )
    app.state.notification_job = NotificationJob(app.state, settings.app_base_url.rstrip("/"))
    redact_link_tokens_in_access_log()
    otlp = settings.otlp_export()
    telemetry: Telemetry | None = None if otlp is None else otlp_telemetry(otlp)
    app.state.telemetry = telemetry
    app.state.agent_runtime = agent_runtime(
        settings,
        trace_sink=log_sink if telemetry is None else telemetry.sink,
        outcome_sink=log_outcome if telemetry is None else telemetry.sink,
        # The breaker logs each opening itself; export adds it as a metric to alert on.
        circuit_sink=None if telemetry is None else telemetry.sink,
    )
    app.state.jira_runtime = jira_runtime_for(settings)
    app.state.publish_job = PublishJob(app.state)
    app.state.source_limits = SourceLimits(
        max_bytes=settings.source_max_bytes,
        max_words=settings.source_max_words,
        max_document_bytes=settings.source_max_document_bytes,
    )
    app.state.project_limits = ProjectLimits(
        source_max_bytes=settings.source_max_bytes,
        source_max_document_bytes=settings.source_max_document_bytes,
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
    app.dependency_overrides[get_change_outcome_recorder] = resolve_change_outcome_recorder
    app.dependency_overrides[get_after_approval] = resolve_after_approval
    app.dependency_overrides[get_memberships] = resolve_memberships
    app.dependency_overrides[get_request_origins] = resolve_request_origins
    app.dependency_overrides[get_user_directory] = resolve_user_directory
    app.dependency_overrides[get_member_activity] = resolve_member_activity
    app.dependency_overrides[get_project_reader] = resolve_project_reader
    app.dependency_overrides[get_project_work_reader] = resolve_project_work_reader
    app.dependency_overrides[get_waiting_by_role] = resolve_waiting_by_role
    app.dependency_overrides[get_project_access] = resolve_project_access
    app.dependency_overrides[get_project_access_resolver] = resolve_project_access_resolver
    app.dependency_overrides[get_people_recorder] = resolve_people_recorder
    app.dependency_overrides[get_speaker_identity_reader] = resolve_speaker_identity_reader
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


def jira_runtime_for(settings: Settings) -> JiraRuntime:
    return jira_runtime(
        _jira_token_key(settings), settings.app_base_url, directory=SqlUserDirectory
    )


def _jira_token_key(settings: Settings) -> str | None:
    if settings.jira_token_key is None:
        return None
    key = settings.jira_token_key.get_secret_value()
    if not valid_key(key):
        # The value is never repeated: it is a secret even when it is malformed.
        raise ValueError("JIRA_TOKEN_KEY is not a Fernet key (32 bytes, URL-safe base64)")
    return key


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


def agent_runtime(
    settings: Settings,
    *,
    trace_sink: TraceSink = log_sink,
    outcome_sink: OutcomeSink = log_outcome,
    circuit_sink: TraceSink | None = None,
) -> AgentRuntime:
    provider, provider_name, model_id = _served_model(settings, trace_sink)
    backup = settings.fallback_model()
    fallback = (
        None
        if backup is None
        else ServedModel(
            create_model_provider(backup, trace_sink=trace_sink),
            backup.provider,
            backup.model_id,
            request_token_limit(backup),
        )
    )
    primary = settings.active_model()
    return AgentRuntime(
        provider=provider,
        provider_name=provider_name,
        model_id=model_id,
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
        breaker=CircuitBreaker(sink=circuit_sink),
        outcomes=outcome_sink,
        # A replay answers from a recording, so no request limit applies to it.
        max_request_tokens=None if primary is None else request_token_limit(primary),
    )


def _served_model(
    settings: Settings, trace_sink: TraceSink
) -> tuple[ModelProvider | None, str, str]:
    """The primary provider, the provider name runs pin and its model id."""
    if settings.model_provider == "replay" and settings.model_replay_file is not None:
        provider, model_id = create_replay_provider(
            settings.model_replay_file, trace_sink=trace_sink
        )
        return provider, settings.model_provider, model_id
    config = settings.active_model()
    if config is None:
        return None, settings.model_provider, ""
    provider = create_model_provider(config, trace_sink=trace_sink)
    if settings.model_record_file is not None:
        provider = recording(provider, settings.model_record_file, config)
    return provider, settings.model_provider, config.model_id


def _microusd(usd: Decimal | None) -> int | None:
    return None if usd is None else int(usd * MICROUSD_PER_USD)
