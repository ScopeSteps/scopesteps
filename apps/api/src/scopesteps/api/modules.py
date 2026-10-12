"""Registry of the modules this deployable can mount, keyed by ENABLED_MODULES name."""

from importlib import import_module

from fastapi import APIRouter

MODULE_NAMES = (
    "identity",
    "projects",
    "sources",
    "evidence",
    "backlog",
    "change_control",
    "agent",
    "audit",
)


def load_router(module_name: str) -> APIRouter:
    router: APIRouter = import_module(f"scopesteps.{module_name}.http.router").router
    return router
