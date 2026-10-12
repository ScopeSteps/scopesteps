from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scopesteps.api import health
from scopesteps.api.modules import load_router
from scopesteps.api.settings import Settings, get_settings

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    is_production = settings.app_env == "production"

    app = FastAPI(
        title="ScopeSteps API",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    for module_name in settings.enabled_modules:
        app.include_router(load_router(module_name), prefix=API_PREFIX)
    return app
